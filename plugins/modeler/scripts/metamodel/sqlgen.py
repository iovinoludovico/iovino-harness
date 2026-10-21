"""Draft of a PostgreSQL migration from the difference between two metamodels.

`migration(old, new)` compares the storage of the two metamodels (`ecore.storage`) and writes the DDL that moves
a database from the old structure to the new one: tables, columns, foreign keys, join tables, enum literals and
renames (`renamed_from`). Changes that can lose data (drops, type changes, a column becoming required on a filled
table, removed literals) are written commented out under a `TODO(modeler)` line, as are row-level security
policies, which depend on the application. The result is a draft to review, then checked with `drift`.
"""

from __future__ import annotations

import json
from typing import Any

from . import __version__
from . import core as M
from . import ecore as E

TODO = "TODO(modeler)"
SQL_TYPES = {"string": "text", "text": "text", "email": "text", "url": "text", "int": "integer", "number": "numeric",
             "money": "numeric(12,2)", "bool": "boolean", "date": "date", "datetime": "timestamptz", "json": "jsonb",
             "enum": "text", "ref": "uuid"}
USER_TABLE = "profiles"


def _q(name: str) -> str:
    """Identifier, quoted only when needed."""
    return name if name.isidentifier() and name == name.lower() else '"' + name.replace('"', '""') + '"'


def _lit(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, (dict, list)):
        return "'" + json.dumps(value).replace("'", "''") + "'::jsonb"
    return "'" + str(value).replace("'", "''") + "'"


def _sql_type(f: dict[str, Any]) -> str:
    if f["type"] in ("string", "email", "url") and f.get("max_length"):
        return f"varchar({int(f['max_length'])})"
    return SQL_TYPES.get(f["type"], "text")


def _target_table(st: dict[str, Any], f: dict[str, Any]) -> str:
    return USER_TABLE if f["to"] == "User" else st["entities"][f["to"]]["table"]


def _on_delete(f: dict[str, Any]) -> str:
    return {"restrict": "restrict", "set_null": "set null", "cascade": "cascade"}.get(f.get("on_delete") or "", "restrict")


def _coldef(st: dict[str, Any], table: str, f: dict[str, Any], not_null: bool) -> str:
    parts = [_q(f["key"]), _sql_type(f)]
    if not_null:
        parts.append("not null")
    if f.get("default") is not None:
        parts.append(f"default {_lit(f['default'])}")
    if f["unique"]:
        parts.append("unique")
    if f["type"] == "enum":
        values = ", ".join(_lit(v) for v in st["enums"][f["enum"]])
        parts.append(f"check ({_q(f['key'])} in ({values}))")
    if f["type"] == "ref":
        parts.append(f"references public.{_q(_target_table(st, f))} (id) on delete {_on_delete(f)}")
    return " ".join(parts)


def _unique_name(table: str, columns: list[str]) -> str:
    return _q(f"{table}_{'_'.join(columns)}_key"[:63])


def _add_unique(table: str, columns: list[str]) -> str:
    """Columns unique together; nulls not distinct, so a default row (null in a column) cannot be repeated."""
    cols = ", ".join(_q(c) for c in columns)
    return f"alter table public.{_q(table)} add constraint {_unique_name(table, columns)} unique nulls not distinct ({cols});"


def _index(table: str, column: str) -> str:
    name = f"{table}_{column}_idx"[:63]
    return f"create index if not exists {_q(name)} on public.{_q(table)} ({_q(column)});"


def _join_table(st: dict[str, Any], cname: str, ent: dict[str, Any], f: dict[str, Any]) -> tuple[str, list[str]]:
    name = f.get("join_table") or f"{ent['table']}_{f['key']}"
    target = _target_table(st, f)
    a = f"{M.snake(cname)}_id"
    b = f"{f['key']}_id" if f["to"] == cname else f"{M.snake(f['to'])}_id"
    sql = [f"create table public.{_q(name)} (",
           f"  {_q(a)} uuid not null references public.{_q(ent['table'])} (id) on delete cascade,",
           f"  {_q(b)} uuid not null references public.{_q(target)} (id) on delete cascade,",
           f"  primary key ({_q(a)}, {_q(b)})",
           ");",
           f"alter table public.{_q(name)} enable row level security;",
           _index(name, b)]
    return name, sql


def _commented(lines: list[str]) -> list[str]:
    return [f"-- {line}" for line in lines]


def migration(old_meta: dict[str, Any], new_meta: dict[str, Any], origin: str = "previous metamodel") -> tuple[str, list[str]]:
    """(SQL draft, notes). An empty draft (no statements) means the storage did not change."""
    old, new = E.storage(old_meta), E.storage(new_meta)
    notes: list[str] = []
    created: list[str] = []          # new tables
    new_refs: list[str] = []         # foreign keys of the new tables (after every table exists)
    changed: list[str] = []          # existing tables
    joins: list[str] = []
    enums: list[str] = []
    risky: list[str] = []            # commented out: data loss or app decisions
    rls: list[str] = []

    old_by_table = {ent["table"]: (c, ent) for c, ent in old["entities"].items()}
    for cname, ent in new["entities"].items():
        t = ent["table"]
        prev = old["entities"].get(cname)
        if prev is None and t in old_by_table:
            prev = old_by_table[t][1]          # class renamed but the table kept its name
        if prev is None:
            cols = [f"  {_coldef(new, t, f, f['required'])}," for f in ent["fields"].values()
                    if f["type"] != "ref"]
            created += [f"create table public.{_q(t)} (",
                        "  id uuid primary key default gen_random_uuid(),",
                        *cols,
                        "  created_at timestamptz not null default now(),",
                        "  updated_at timestamptz not null default now()",
                        ");",
                        f"alter table public.{_q(t)} enable row level security;"]
            rls.append(t)
            for f in ent["fields"].values():
                if f["type"] == "ref" and not f["many"]:
                    new_refs += [f"alter table public.{_q(t)} add column {_coldef(new, t, f, f['required'])};",
                                 _index(t, f["key"])]
                elif f["type"] == "ref":
                    name, sql = _join_table(new, cname, ent, f)
                    joins += sql
                    rls.append(name)
            new_refs += [_add_unique(t, cols) for cols in ent.get("unique", [])]   # after the reference columns
            continue
        pt = prev["table"]
        if pt != t:
            changed.append(f"alter table public.{_q(pt)} rename to {_q(t)};")
        pf = prev["fields"]
        renamed_new: set[str] = set()
        renamed_old: set[str] = set()
        for key, f in ent["fields"].items():
            if key in pf or not f.get("renamed_from"):
                continue
            src = next((k for k, g in pf.items() if g.get("feature") == f["renamed_from"]), None)
            if src and src not in ent["fields"] and not f["many"]:
                changed.append(f"alter table public.{_q(t)} rename column {_q(src)} to {_q(key)};")
                renamed_new.add(key)
                renamed_old.add(src)
        for key, f in ent["fields"].items():
            if key in renamed_new:
                g = pf[next(k for k in renamed_old if pf[k].get("feature") == f["renamed_from"])]
                _compare(new, t, g, f, changed, risky)
                continue
            if key not in pf:
                if f["type"] == "ref" and f["many"]:
                    name, sql = _join_table(new, cname, ent, f)
                    joins += sql
                    rls.append(name)
                elif f["required"] and f.get("default") is None:
                    changed.append(f"alter table public.{_q(t)} add column {_coldef(new, t, f, False)};")
                    risky += [f"-- {TODO}: {t}.{key} is required: fill the existing rows, then enable the constraint",
                              f"-- update public.{_q(t)} set {_q(key)} = <value> where {_q(key)} is null;",
                              f"-- alter table public.{_q(t)} alter column {_q(key)} set not null;"]
                    notes.append(f"{t}.{key}: required column added as nullable (backfill needed)")
                else:
                    changed.append(f"alter table public.{_q(t)} add column {_coldef(new, t, f, f['required'])};")
                if f["type"] == "ref" and not f["many"]:
                    changed.append(_index(t, key))
                continue
            _compare(new, t, pf[key], f, changed, risky)
        for key, g in pf.items():
            if key in ent["fields"] or key in renamed_old:
                continue
            if g["type"] == "ref" and g["many"]:
                name = g.get("join_table") or f"{pt}_{key}"
                risky += [f"-- {TODO}: {cname}.{key} removed: dropping the join table deletes its rows",
                          f"-- drop table public.{_q(name)};"]
            else:
                risky += [f"-- {TODO}: {cname}.{key} removed: dropping the column deletes its data",
                          f"-- alter table public.{_q(t)} drop column {_q(key)};"]
            notes.append(f"{t}.{key}: removed from the metamodel (drop left commented)")
        before = prev.get("unique", [])
        for cols in ent.get("unique", []):
            if cols not in before:
                changed.append(_add_unique(t, cols))
                notes.append(f"{t}: unique ({', '.join(cols)}) added: it fails if the table already has duplicates")
        for cols in before:
            if cols not in ent.get("unique", []):
                changed.append(f"alter table public.{_q(t)} drop constraint if exists {_unique_name(t, cols)};")
    for cname, ent in old["entities"].items():
        if cname not in new["entities"] and ent["table"] not in {e["table"] for e in new["entities"].values()}:
            risky += [f"-- {TODO}: class {cname} removed (or renamed: then rename the table instead and keep the data)",
                      f"-- drop table public.{_q(ent['table'])};"]
            notes.append(f"{ent['table']}: class {cname} removed (drop left commented)")
    for en, values in new["enums"].items():
        before = old["enums"].get(en)
        if before is None:
            continue
        added = [v for v in values if v not in before]
        removed = [v for v in before if v not in values]
        users = [(ent["table"], f["key"]) for c, ent in new["entities"].items() if c in old["entities"]
                 for f in ent["fields"].values() if f.get("enum") == en and f["key"] in old["entities"][c]["fields"]]
        if added and users:
            enums += _enum_literals(M.snake(en), added, values, users)
        if removed:
            risky += [f"-- {TODO}: literals {', '.join(removed)} removed from {en}: migrate the rows that use them, "
                      "then narrow the check / recreate the type"]
            notes.append(f"enum {en}: literals removed ({', '.join(removed)})")
    roles = _roles(old.get("roles"), new.get("roles"), risky, notes)
    for t in rls:
        risky.append(f"-- {TODO}: row level security is on for {t} with no policy (nobody can read it): add the "
                     "policies and grants following the app's conventions")
    sections = [("New tables", created), ("References of the new tables", new_refs), ("Changed tables", changed),
                ("Join tables", joins), ("Enum literals", enums), ("Roles", roles), ("To review", risky)]
    body = [f"-- {title}\n" + "\n".join(lines) for title, lines in sections if lines]
    if not any(lines for title, lines in sections if title != "To review") and not risky:
        return "", notes
    header = (f"-- Migration drafted by modeler {__version__} from the metamodel difference ({origin} -> domain.ecore.yaml).\n"
              f"-- Review it: every {TODO} line needs a decision (policies, backfills, destructive steps).\n")
    return header + "\n\n".join(body) + "\n", notes


def _compare(st: dict[str, Any], t: str, g: dict[str, Any], f: dict[str, Any], changed: list[str], risky: list[str]) -> None:
    key = f["key"]
    col = f"public.{_q(t)}"
    if (g["type"], g.get("enum"), g.get("to"), g["many"]) != (f["type"], f.get("enum"), f.get("to"), f["many"]) \
            or _sql_type(g) != _sql_type(f):
        risky += [f"-- {TODO}: {t}.{key} changes type ({g.get('enum') or g['type']} -> {f.get('enum') or f['type']}): "
                  "convert the data explicitly",
                  f"-- alter table {col} alter column {_q(key)} type {_sql_type(f)} using {_q(key)}::{_sql_type(f)};"]
        return
    if g["required"] and not f["required"]:
        changed.append(f"alter table {col} alter column {_q(key)} drop not null;")
    elif f["required"] and not g["required"]:
        risky += [f"-- {TODO}: {t}.{key} becomes required: fill the empty rows first",
                  f"-- update {col} set {_q(key)} = <value> where {_q(key)} is null;",
                  f"-- alter table {col} alter column {_q(key)} set not null;"]
    if g["unique"] != f["unique"]:
        name = _q(f"{t}_{key}_key"[:63])
        changed.append(f"alter table {col} add constraint {name} unique ({_q(key)});" if f["unique"]
                       else f"alter table {col} drop constraint if exists {name};")
    if g.get("default") != f.get("default"):
        changed.append(f"alter table {col} alter column {_q(key)} set default {_lit(f['default'])};"
                       if f.get("default") is not None else f"alter table {col} alter column {_q(key)} drop default;")
    if f["type"] == "ref" and (g.get("on_delete") or "") != (f.get("on_delete") or ""):
        name = _q(f"{t}_{key}_fkey"[:63])
        changed += [f"alter table {col} drop constraint if exists {name};",
                    f"alter table {col} add constraint {name} foreign key ({_q(key)}) references "
                    f"public.{_q(_target_table(st, f))} (id) on delete {_on_delete(f)};"]


def _roles(old: dict[str, Any] | None, new: dict[str, Any] | None, risky: list[str], notes: list[str]) -> list[str]:
    """The roles of the metamodel in the database: the enum `app_role` and the table `user_roles` (created when the
    application has none: an appforge app already has both), a new literal per added role; a removed role is left to
    review (Postgres cannot drop an enum value: its rows must be migrated first)."""
    if not new:
        if old:
            risky.append(f"-- {TODO}: the roles left the metamodel: {old['enum']} and {old['table']} stay (drop them by hand if the app no longer uses them)")
            notes.append("roles removed from the metamodel (type and table kept)")
        return []
    enum, table = _q(new["enum"]), _q(new["table"])
    lines: list[str] = []
    if not old:
        values = ", ".join(_lit(v) for v in new["values"])
        lines += ["do $$", "begin",
                  "  if not exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace",
                  f"                 where n.nspname = 'public' and t.typname = {_lit(new['enum'])}) then",
                  f"    create type public.{enum} as enum ({values});",
                  "  end if;",
                  "end $$;",
                  f"create table if not exists public.{table} (",
                  "  id         uuid primary key default gen_random_uuid(),",
                  "  profile_id uuid not null,",
                  f"  role       public.{enum} not null,",
                  "  scope_id   uuid,",
                  "  created_at timestamptz not null default now(),",
                  f"  constraint {_q(new['table'] + '_unique')} unique nulls not distinct (profile_id, role, scope_id)",
                  ");",
                  "do $$", "begin",
                  f"  if to_regclass('public.profiles') is not null and not exists (select 1 from pg_constraint where conname = {_lit(new['table'] + '_profile_fk')}) then",
                  f"    alter table public.{table} add constraint {_q(new['table'] + '_profile_fk')} foreign key (profile_id) references public.profiles (id) on delete cascade;",
                  "  end if;",
                  "end $$;",
                  f"create index if not exists {_q(new['table'] + '_profile_idx')} on public.{table} (profile_id);",
                  f"create index if not exists {_q(new['table'] + '_scope_idx')} on public.{table} (scope_id);",
                  f"alter table public.{table} enable row level security;"]
        risky.append(f"-- {TODO}: {new['table']}: if the table was just created, add its policies (administrators manage, a user reads "
                     "their own rows) and grants; the engine's has_role/role_members read it when the app defines none")
        notes.append(f"roles: {new['enum']} and {new['table']} created if missing")
    added = [v for v in new["values"] if not old or v not in old["values"]]
    # idempotent: an existing type (appforge) gains the roles it lacks; a type just created already has them
    lines += [f"alter type public.{enum} add value if not exists {_lit(v)};" for v in added]
    removed = [v for v in (old["values"] if old else []) if v not in new["values"]]
    if removed:
        risky.append(f"-- {TODO}: roles {', '.join(removed)} removed from the metamodel: migrate the rows of {new['table']} that hold them "
                     f"(the value stays in {new['enum']}: Postgres cannot drop an enum value)")
        notes.append(f"roles removed: {', '.join(removed)} (rows to migrate)")
    return lines


def _enum_literals(type_name: str, added: list[str], values: list[str], users: list[tuple[str, str]]) -> list[str]:
    """New literals: on a Postgres enum type add them, on text columns widen the check constraint."""
    lines = ["do $$",
             "begin",
             f"  if exists (select 1 from pg_type t join pg_namespace n on n.oid = t.typnamespace",
             f"             where n.nspname = 'public' and t.typname = {_lit(type_name)}) then"]
    lines += [f"    alter type public.{_q(type_name)} add value if not exists {_lit(v)};" for v in added]
    lines.append("  else")
    allowed = ", ".join(_lit(v) for v in values)
    for table, column in users:
        check = _q(f"{table}_{column}_check"[:63])
        lines += [f"    alter table public.{_q(table)} drop constraint if exists {check};",
                  f"    alter table public.{_q(table)} add constraint {check} check ({_q(column)} in ({allowed}));"]
    lines += ["  end if;", "end $$;"]
    return lines
