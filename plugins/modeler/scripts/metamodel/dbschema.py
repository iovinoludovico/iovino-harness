"""Metamodel <-> live database: reverse engineering and drift detection.

Both read the catalog of a PostgreSQL database (a local `supabase start`, a scratch
database where the migrations were applied, or any DSN) through `psql`.
"""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from . import ecore as E
from . import core as M

# tables never described by the metamodel: the users (the built-in User) and the modeler's own proposals;
# the app's other infrastructure tables are excluded with --exclude (`table.column` excludes one technical column)
INTERNAL_TABLES = {"profiles", "model_change_requests", "schema_migrations"}
STANDARD_COLUMNS = E.STANDARD_COLUMNS
USER_TABLES = {("public", "profiles"), ("auth", "users")}


def split_exclude(exclude: set[str] | None) -> tuple[set[str], set[tuple[str, str]]]:
    """Entries of --exclude / MODELER_EXCLUDE: whole tables, and `table.column` for single technical columns."""
    tables: set[str] = set()
    columns: set[tuple[str, str]] = set()
    for x in exclude or set():
        if "." in x:
            t, c = x.split(".", 1)
            columns.add((t, c))
        else:
            tables.add(x)
    return tables, columns


ON_DELETE = {"c": "cascade", "n": "set_null", "r": "restrict", "a": "restrict", "d": "set_null"}

CATALOG_SQL = """
select json_build_object(
 'tables', (select coalesce(json_agg(table_name order by table_name), '[]') from information_schema.tables
            where table_schema = '{s}' and table_type = 'BASE TABLE'),
 'columns', (select coalesce(json_agg(json_build_object('table', table_name, 'name', column_name, 'pos', ordinal_position,
            'type', data_type, 'udt', udt_name, 'nullable', is_nullable = 'YES', 'default', column_default,
            'maxlen', character_maximum_length) order by table_name, ordinal_position), '[]')
            from information_schema.columns where table_schema = '{s}'),
 'constraints', (select coalesce(json_agg(json_build_object('table', cl.relname, 'name', con.conname, 'type', con.contype,
            'columns', (select array_agg(a.attname order by k.ord) from unnest(con.conkey) with ordinality k(n, ord)
                        join pg_attribute a on a.attrelid = con.conrelid and a.attnum = k.n),
            'ftable', fcl.relname, 'fschema', fns.nspname, 'on_delete', con.confdeltype,
            'def', pg_get_constraintdef(con.oid))), '[]')
            from pg_constraint con join pg_class cl on cl.oid = con.conrelid
            join pg_namespace ns on ns.oid = cl.relnamespace
            left join pg_class fcl on fcl.oid = con.confrelid left join pg_namespace fns on fns.oid = fcl.relnamespace
            where ns.nspname = '{s}' and con.contype in ('f', 'u', 'p', 'c')),
 'unique_indexes', (select coalesce(json_agg(json_build_object('table', cl.relname, 'name', ic.relname,
            'columns', (select array_agg(a.attname order by k.ord) from unnest(ix.indkey::int2[]) with ordinality k(n, ord)
                        join pg_attribute a on a.attrelid = ix.indrelid and a.attnum = k.n),
            'expressions', ix.indexprs is not null, 'def', pg_get_indexdef(ix.indexrelid))), '[]')
            from pg_index ix join pg_class cl on cl.oid = ix.indrelid join pg_class ic on ic.oid = ix.indexrelid
            join pg_namespace ns on ns.oid = cl.relnamespace
            where ns.nspname = '{s}' and ix.indisunique and not ix.indisprimary
            and not exists (select 1 from pg_constraint c where c.conindid = ix.indexrelid)),
 'enums', (select coalesce(json_agg(json_build_object('name', t.typname, 'values',
            (select array_agg(e.enumlabel order by e.enumsortorder) from pg_enum e where e.enumtypid = t.oid))), '[]')
            from pg_type t join pg_namespace n on n.oid = t.typnamespace where t.typtype = 'e' and n.nspname = '{s}')
)
"""


class DbError(Exception):
    pass


def composite_uniques(cat: dict[str, Any], table: str) -> list[dict[str, Any]]:
    """Unique constraints and unique indexes of a table on two or more plain columns:
    [{"columns", "nulls_not_distinct", "partial"}]. Indexes on expressions are not comparable: skipped."""
    items = [(c["columns"], c.get("def") or "") for c in cat["constraints"] if c["table"] == table and c["type"] == "u"]
    items += [(i["columns"], i.get("def") or "") for i in cat.get("unique_indexes", [])
              if i["table"] == table and not i.get("expressions")]
    return [{"columns": list(cols), "nulls_not_distinct": "NULLS NOT DISTINCT" in defn.upper(),
             "partial": " WHERE " in defn.upper()}
            for cols, defn in items if len(cols or []) >= 2]


# the published versions of the runtime workflow engine (tables workflow_versions/states/transitions of the app);
# `null` when the app has no such tables (its workflows are code)
WORKFLOW_SQL = """
select json_build_object(
 'versions', (select coalesce(json_agg(json_build_object('id', v.id, 'entity', v.entity, 'version', v.version, 'status', v.status)
                              order by v.entity), '[]') from {s}.workflow_versions v where v.status = 'published'),
 'states', (select coalesce(json_agg(json_build_object('version_id', st.version_id, 'key', st.key, 'kind', st.kind,
                            'owner', st.owner, 'editable_by', st.editable_by, 'reminder_days', st.reminder_days,
                            'reminder_template', st.reminder_template) order by st.sort, st.key), '[]')
            from {s}.workflow_states st join {s}.workflow_versions v on v.id = st.version_id where v.status = 'published'),
 'transitions', (select coalesce(json_agg(json_build_object('version_id', tr.version_id, 'key', tr.key, 'from_states', tr.from_states,
                                 'to_state', tr.to_state, 'allowed', tr.allowed, 'trigger', tr.trigger, 'at_field', tr.at_field,
                                 'at_offset', tr.at_offset, 'comment', tr.comment, 'guard', tr.guard, 'condition', tr.condition,
                                 'emits', tr.emits) order by tr.sort, tr.key), '[]')
                 from {s}.workflow_transitions tr join {s}.workflow_versions v on v.id = tr.version_id where v.status = 'published')
)
"""
HAS_WORKFLOW_SQL = "select to_json(to_regclass('{s}.workflow_versions') is not null)"


def _query_json(dsn: str, sql: str) -> Any:
    try:
        out = subprocess.run(["psql", dsn, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", sql],
                             capture_output=True, text=True, timeout=60)
    except FileNotFoundError as exc:
        raise DbError("psql not found: install the PostgreSQL client") from exc
    if out.returncode != 0:
        raise DbError(out.stderr.strip() or "psql failed")
    return json.loads(out.stdout.strip())


def _check_schema(schema: str) -> None:
    if not re.match(r"^[a-z_][a-z0-9_]*$", schema):
        raise DbError(f"invalid schema name: {schema}")


def catalog(dsn: str, schema: str = "public") -> dict[str, Any]:
    _check_schema(schema)
    return _query_json(dsn, CATALOG_SQL.format(s=schema))


def workflow_catalog(dsn: str, schema: str = "public") -> dict[str, Any] | None:
    """The published workflow versions with their states and transitions; None if the app has no workflow tables."""
    _check_schema(schema)
    if not _query_json(dsn, HAS_WORKFLOW_SQL.format(s=schema)):   # a missing table fails the whole query, even in a CASE
        return None
    return _query_json(dsn, WORKFLOW_SQL.format(s=schema))


# --------------------------------------------------------------------------- #
# Naming
# --------------------------------------------------------------------------- #
def singular(word: str) -> str:
    if word.endswith("ies"):
        return word[:-3] + "y"
    if re.search(r"(sses|shes|ches|xes|zes)$", word):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def class_name(table: str) -> str:
    parts = table.split("_")
    parts[-1] = singular(parts[-1])
    return "".join(p[:1].upper() + p[1:] for p in parts if p)


def feature_name(column: str) -> str:
    parts = column.split("_")
    return parts[0] + "".join(p[:1].upper() + p[1:] for p in parts[1:])


def _default_literal(expr: str | None) -> Any:
    if expr is None:
        return None
    m = re.match(r"^'(.*)'::[\w .\"]+$", expr)
    if m:
        return m.group(1).replace("''", "'")
    if expr in ("true", "false"):
        return expr == "true"
    if re.match(r"^-?\d+$", expr):
        return int(expr)
    if re.match(r"^-?\d+\.\d+$", expr):
        return float(expr)
    return None


def _datatype(col: dict[str, Any], enums: dict[str, str]) -> tuple[str, bool]:
    """(data type or enum name, multi-valued)."""
    udt = col["udt"]
    many = col["type"] == "ARRAY"
    if many:
        udt = udt.lstrip("_")
    if udt in enums:
        return enums[udt], many
    name = col["name"]
    if udt in ("text", "varchar", "bpchar", "citext", "name"):
        if name == "email" or name.endswith("_email"):
            return "Email", many
        if re.search(r"(^|_)(url|link|website|site)($|_)", name):
            return "URL", many
        if name in ("notes", "note", "description", "descrizione", "body", "content", "testo", "message"):
            return "Text", many
        return "EString", many
    return {
        "int2": "EShort", "int4": "EInt", "int8": "ELong", "numeric": "EBigDecimal", "float4": "EFloat",
        "float8": "EDouble", "bool": "EBoolean", "date": "Date", "timestamptz": "EDate", "timestamp": "EDate",
        "json": "JSON", "jsonb": "JSON", "uuid": "EString", "time": "EString", "timetz": "EString",
    }.get(udt, "EString"), many


CHECK_IN = re.compile(r"\(\(?(\w+)\)?(?:::text)?\s*=\s*ANY\s*\(\(?ARRAY\[(.+?)\]\)?(?:::text\[\])?\)\)", re.S)


def _check_enum(defn: str) -> tuple[str, list[str]] | None:
    m = CHECK_IN.search(defn)
    if not m:
        return None
    values = re.findall(r"'((?:[^']|'')*)'", m.group(2))
    return (m.group(1), [v.replace("''", "'") for v in values]) if values else None


# --------------------------------------------------------------------------- #
# Reverse engineering
# --------------------------------------------------------------------------- #
def reverse(cat: dict[str, Any], package: str = "domain", exclude: set[str] | None = None,
            include: set[str] | None = None) -> tuple[dict[str, Any], list[str]]:
    """Metamodel describing the tables of a database, plus notes for the developer."""
    notes: list[str] = []
    exclude, excluded_columns = split_exclude(exclude)
    exclude |= INTERNAL_TABLES
    tables = [t for t in cat["tables"] if t not in exclude and (not include or t in include)]
    cols: dict[str, list[dict[str, Any]]] = {}
    for c in cat["columns"]:
        if (c["table"], c["name"]) not in excluded_columns:
            cols.setdefault(c["table"], []).append(c)
    cons: dict[str, list[dict[str, Any]]] = {}
    for c in cat["constraints"]:
        cons.setdefault(c["table"], []).append(c)
    pg_enums = {e["name"]: "".join(p[:1].upper() + p[1:] for p in e["name"].split("_")) for e in cat["enums"]}
    enums: dict[str, Any] = {pg_enums[e["name"]]: list(e["values"]) for e in cat["enums"]}

    def fks(t: str) -> list[dict[str, Any]]:
        return [c for c in cons.get(t, []) if c["type"] == "f" and len(c["columns"] or []) == 1]

    def is_user_table(fk: dict[str, Any]) -> bool:
        return (fk["fschema"], fk["ftable"]) in USER_TABLES

    # join tables: two single-column FKs and nothing else of substance
    join_tables: dict[str, tuple[dict[str, Any], dict[str, Any]]] = {}
    for t in tables:
        f = fks(t)
        rest = [c["name"] for c in cols.get(t, []) if c["name"] not in {x["columns"][0] for x in f}
                and c["name"] not in ("id", "position", "created_at", "created_by", "sort_order")]
        if len(f) == 2 and not rest and all(x["ftable"] in tables or is_user_table(x) for x in f):
            join_tables[t] = (f[0], f[1])
    classes: dict[str, Any] = {}
    cls_of = {t: class_name(t) for t in tables if t not in join_tables}
    for t in cls_of:
        if M.pluralize(M.snake(cls_of[t])) != t:
            classes.setdefault(cls_of[t], {})["table"] = t
    for t, cname in cls_of.items():
        c = classes.setdefault(cname, {})
        attrs: dict[str, Any] = {}
        refs: dict[str, Any] = {}
        tfks = {x["columns"][0]: x for x in fks(t)}
        uniques = {x["columns"][0] for x in cons.get(t, []) if x["type"] in ("u", "p") and len(x["columns"] or []) == 1}
        checks = {}
        for x in cons.get(t, []):
            if x["type"] == "c":
                ce = _check_enum(x["def"] or "")
                if ce:
                    checks[ce[0]] = ce[1]
        skipped = []
        feature_of: dict[str, str] = {}   # column -> feature, for the unique groups
        for col in cols.get(t, []):
            name = col["name"]
            if name in STANDARD_COLUMNS:
                continue
            fname = feature_name(name)
            if name in tfks:
                fk = tfks[name]
                target = "User" if is_user_table(fk) else cls_of.get(fk["ftable"])
                if not target:
                    skipped.append(f"{name} (references {fk['fschema']}.{fk['ftable']}, not described)")
                    continue
                rname = feature_name(name[:-3]) if name.endswith("_id") and len(name) > 3 else fname
                r: dict[str, Any] = {"type": target}
                if not col["nullable"]:
                    r["lower"] = 1
                if M.snake(rname) != name:
                    r["column"] = name
                od = ON_DELETE.get(fk["on_delete"] or "a", "restrict")
                if od == "cascade" and target != "User":
                    # the referenced record owns this one: containment on the owner side
                    owner = classes.setdefault(target, {})
                    back = feature_name(t)
                    owner_refs = owner.setdefault("references", {})
                    while back in owner_refs or back in (owner.get("attributes") or {}):
                        back += "Items"
                    owner_refs[back] = {"type": cname, "upper": 1 if name in uniques else -1,
                                        "containment": True, "opposite": rname}
                    r["opposite"] = back
                elif od != ("restrict" if not col["nullable"] else "set_null"):
                    r["on_delete"] = od
                if name in uniques and "opposite" not in r:
                    r["unique"] = True
                refs[rname] = r
                feature_of[name] = rname
                continue
            dtype, many = _datatype(col, pg_enums)
            if name in checks and dtype == "EString":
                en = "".join(p[:1].upper() + p[1:] for p in name.split("_"))
                if en in enums and enums[en] != checks[name]:
                    en = cname + en
                enums[en] = checks[name]
                dtype = en
            a: dict[str, Any] = {"type": dtype}
            if not col["nullable"] and dtype != "EBoolean":
                a["lower"] = 1
            if many:
                a["upper"] = -1
            if name in uniques:
                a["unique"] = True
            if col["maxlen"]:
                a["max_length"] = col["maxlen"]
            d = _default_literal(col["default"])
            if d is not None:
                a["default"] = d
            if M.snake(fname) != name:
                a["column"] = name
            attrs[fname] = a
            feature_of[name] = fname
        groups = []
        nullable = {col["name"] for col in cols.get(t, []) if col["nullable"]}
        for u in composite_uniques(cat, t):
            names = ", ".join(u["columns"])
            if u["partial"] or not all(col in feature_of for col in u["columns"]):
                notes.append(f"{t}: unique ({names}) not described (partial, or on columns not in the metamodel)")
                continue
            groups.append([feature_of[col] for col in u["columns"]])
            if not u["nulls_not_distinct"] and nullable & set(u["columns"]):
                notes.append(f"{t}: unique ({names}) treats empty values as distinct: rows with an empty column can "
                             "repeat; the metamodel means nulls not distinct (drift will report it)")
        if groups:
            c["unique"] = groups
        if attrs:
            c["attributes"] = attrs
        if refs:
            c.setdefault("references", {}).update(refs)
        if skipped:
            notes.append(f"{t}: not described: " + "; ".join(skipped))
    for jt, (a, b) in join_tables.items():
        src = "User" if is_user_table(a) else cls_of.get(a["ftable"])
        dst = "User" if is_user_table(b) else cls_of.get(b["ftable"])
        if not src or src == "User":
            src, dst, a, b = dst, src, b, a
        if not src or not dst or src == "User":
            notes.append(f"{jt}: join table between two non-described tables, skipped")
            continue
        prefix = a["ftable"] + "_"
        rname = feature_name(jt[len(prefix):] if jt.startswith(prefix) else jt)
        refs = classes.setdefault(src, {}).setdefault("references", {})
        refs[rname] = {"type": dst, "upper": -1, "join_table": jt}
        notes.append(f"{jt}: many-to-many {src}.{rname} -> {dst}")
    ordered = {cls_of[t]: classes[cls_of[t]] for t in tables if t in cls_of}
    raw = {"package": package, "classes": ordered}
    used = {a["type"] for c in ordered.values() for a in (c.get("attributes") or {}).values()}
    enums = {k: v for k, v in enums.items() if k in used}
    if enums:
        raw["enums"] = enums
    return E.compact(raw), notes


# --------------------------------------------------------------------------- #
# Drift
# --------------------------------------------------------------------------- #
COMPATIBLE = {
    "string": {"text", "varchar", "bpchar", "citext"}, "text": {"text", "varchar", "citext"},
    "email": {"text", "varchar", "citext"}, "url": {"text", "varchar"}, "int": {"int2", "int4", "int8"},
    "number": {"numeric", "float4", "float8", "int4", "int8"}, "money": {"numeric"}, "bool": {"bool"},
    "date": {"date"}, "datetime": {"timestamptz", "timestamp"}, "json": {"json", "jsonb", "_text", "_int4", "_uuid"},
    "ref": {"uuid", "int4", "int8"},
}


def drift(meta: dict[str, Any], cat: dict[str, Any], exclude: set[str] | None = None) -> list[str]:
    """Differences between the metamodel and the database (empty list = aligned)."""
    m = E.storage(meta)
    e = E.expand(meta)
    out: list[str] = []
    exclude, excluded_columns = split_exclude(exclude)
    tables = set(cat["tables"])
    cols: dict[str, dict[str, dict[str, Any]]] = {}
    for c in cat["columns"]:
        if (c["table"], c["name"]) not in excluded_columns:
            cols.setdefault(c["table"], {})[c["name"]] = c
    fk_of: dict[tuple[str, str], dict[str, Any]] = {}
    for c in cat["constraints"]:
        if c["type"] == "f" and len(c["columns"] or []) == 1:
            fk_of[(c["table"], c["columns"][0])] = c
    described = set()
    join_tables = {r.get("join_table") for c in e["classes"].values() for r in c["references"].values() if r.get("join_table")}
    for name, ent in m["entities"].items():
        t = ent["table"]
        described.add(t)
        if t not in tables:
            out.append(f"MISSING TABLE {t} (class {name})")
            continue
        seen = set()
        for f in ent["fields"].values():
            key = f["key"]
            if f["many"]:
                continue
            seen.add(key)
            col = cols[t].get(key)
            if not col:
                out.append(f"MISSING COLUMN {t}.{key} ({name}.{key})")
                continue
            udt = col["udt"]
            if f["type"] == "enum":
                if udt not in (M.snake(f["enum"]), "text", "varchar"):
                    out.append(f"TYPE {t}.{key}: database {udt}, metamodel enum {f['enum']}")
            elif udt not in COMPATIBLE.get(f["type"], {udt}):
                out.append(f"TYPE {t}.{key}: database {udt}, metamodel {f['type']}")
            if f["required"] and col["nullable"] and f["type"] != "bool":
                out.append(f"NULLABLE {t}.{key}: required in the metamodel, nullable in the database")
            if not f["required"] and not col["nullable"] and f["type"] != "bool" and col["default"] is None:
                out.append(f"NOT NULL {t}.{key}: optional in the metamodel, not null in the database")
            if f["type"] == "ref":
                fk = fk_of.get((t, key))
                target = "profiles" if f["to"] == "User" else m["entities"].get(f["to"], {}).get("table")
                if not fk:
                    out.append(f"NO FOREIGN KEY {t}.{key} -> {target}")
                elif fk["ftable"] != target and not (f["to"] == "User" and fk["ftable"] == "users"):
                    out.append(f"FOREIGN KEY {t}.{key}: database -> {fk['ftable']}, metamodel -> {target}")
        # unique groups of the metamodel (a unique combination only in the database is not reported)
        in_db = [u for u in composite_uniques(cat, t) if not u["partial"]]
        for group in ent.get("unique", []):
            match = next((u for u in in_db if set(u["columns"]) == set(group)), None)
            if not match:
                out.append(f"MISSING UNIQUE {t} ({', '.join(group)})")
            elif not match["nulls_not_distinct"] and any(cols[t].get(k, {}).get("nullable") for k in group):
                out.append(f"UNIQUE {t} ({', '.join(group)}): nulls are distinct in the database, "
                           "so rows with an empty column can repeat (use nulls not distinct)")
        extra = sorted(set(cols[t]) - seen - STANDARD_COLUMNS)
        if extra:
            out.append(f"NOT IN METAMODEL {t}: columns {', '.join(extra)}")
    ignored = INTERNAL_TABLES | exclude | described | {j for j in join_tables if j}
    for name, ent in m["entities"].items():
        for f in ent["fields"].values():
            if f["many"]:
                ignored.add(f.get("join_table") or f"{ent['table']}_{f['key']}")
    for t in sorted(tables - ignored):
        out.append(f"NOT IN METAMODEL table {t}")
    return out
