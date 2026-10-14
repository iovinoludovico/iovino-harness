"""Model evolution: structural delta between the last generated model (lock) and
the current one.

Additive changes are translated into SQL automatically. Destructive or ambiguous
changes (drops, renames, type changes, required without default...) are never
guessed: they are returned as *manual operations* with a suggested, commented
SQL, to be completed in a hand-written migration (the agent does it with the
`evolve` skill) before the behaviour layer is regenerated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from . import sqlgen as S
from . import model as M


@dataclass
class Delta:
    pre: list[str] = field(default_factory=list)        # must commit before the rest (enum values)
    auto: list[str] = field(default_factory=list)       # additive DDL
    manual: list[dict[str, str]] = field(default_factory=list)  # {op, target, why, sql}
    ops: list[str] = field(default_factory=list)        # human-readable list of detected operations

    @property
    def empty(self) -> bool:
        return not (self.pre or self.auto or self.manual)

    def man(self, op: str, target: str, why: str, sql: str = "", phase: str = "pre") -> None:
        """phase pre = before the generated evolve migration, post = after it (e.g. backfill of a new column)."""
        self.manual.append({"op": op, "target": target, "why": why, "sql": sql, "phase": phase})
        self.ops.append(f"MANUAL {op} {target}: {why}")


STRUCT_KEYS = ("type", "required", "unique", "enum", "to", "many", "on_delete", "min", "max", "max_length")


def compute(old: dict[str, Any], new: dict[str, Any]) -> Delta:
    d = Delta()

    # roles
    for key in new["roles"]:
        if key not in old["roles"]:
            d.pre.append(f"alter type public.app_role add value if not exists {S.q(key)};")
            d.ops.append(f"ADD role {key}")
        elif old["roles"][key]["scoped"] != new["roles"][key]["scoped"]:
            d.man("CHANGE_ROLE_SCOPE", f"role {key}", "existing role assignments must be migrated by hand",
                  f"-- update/delete public.user_roles where role = {S.q(key)} ...")
    for key in old["roles"]:
        if key not in new["roles"]:
            d.man("REMOVE_ROLE", f"role {key}", "Postgres cannot drop an enum value: keep it unused or recreate the type",
                  f"-- delete from public.user_roles where role = {S.q(key)};")

    # scope
    old_sc, new_sc = (old.get("scope") or {}).get("entity"), (new.get("scope") or {}).get("entity")
    if old_sc != new_sc:
        if new_sc and not old_sc and new_sc in new["entities"]:
            # the scope FK is added after the entities below
            pass
        else:
            d.man("CHANGE_SCOPE", "scope", f"scope entity changed from {old_sc} to {new_sc}: role assignments must be remapped",
                  "-- alter table public.user_roles drop constraint if exists user_roles_scope_fkey; ...")

    # enums
    for name, en in new["enums"].items():
        if name not in old["enums"]:
            d.auto.append(S.enum_sql(en))
            d.ops.append(f"ADD enum {name}")
            continue
        old_vals = [v["key"] for v in old["enums"][name]["values"]]
        for v in en["values"]:
            if v["key"] not in old_vals:
                d.pre.append(f"alter type public.{en['type']} add value if not exists {S.q(v['key'])};")
                d.ops.append(f"ADD enum value {name}.{v['key']}")
        for v in old_vals:
            if v not in [x["key"] for x in en["values"]]:
                d.man("REMOVE_ENUM_VALUE", f"{name}.{v}", "Postgres cannot drop an enum value: remap the rows and recreate the type",
                      f"-- update ... set <col> = '<other>' where <col> = {S.q(v)};")
    for name in old["enums"]:
        if name not in new["enums"]:
            d.man("REMOVE_ENUM", name, "drop the type after removing the columns that use it",
                  f"-- drop type public.{old['enums'][name]['type']};")

    # entities
    new_entities = []
    for name, e in new["entities"].items():
        if name not in old["entities"]:
            new_entities.append(e)
            d.auto.append(S.entity_structure_sql(new, e))
            d.ops.append(f"ADD entity {name}")
    for e in new_entities:  # references after all new tables exist
        refs = S.entity_refs_sql(new, e)
        if refs:
            d.auto.append(refs)
    for name, oe in old["entities"].items():
        ne = new["entities"].get(name)
        if not ne:
            d.man("REMOVE_ENTITY", name, "dropping a table loses data; rename it if the entity was renamed",
                  f"-- alter table public.{oe['table']} rename to <new_table>;  (rename)\n-- drop table public.{oe['table']} cascade;  (removal)")
            continue
        _entity_delta(old, new, oe, ne, d)

    if new_sc and new_sc != old_sc and not old_sc:
        sc = new["entities"][new_sc]
        d.auto.append(f"alter table public.user_roles add constraint user_roles_scope_fkey\n"
                      f"  foreign key (scope_id) references public.{sc['table']} (id) on delete cascade;")
        d.ops.append(f"ADD scope {new_sc}")
    return d


def _entity_delta(old: dict[str, Any], new: dict[str, Any], oe: dict[str, Any], ne: dict[str, Any], d: Delta) -> None:
    t = ne["table"]
    if oe["table"] != ne["table"]:
        d.man("RENAME_TABLE", ne["name"], f"table renamed from {oe['table']} to {t}",
              f"alter table public.{oe['table']} rename to {t};")
        return
    if oe["kind"] != ne["kind"]:
        if ne["kind"] == "process" and ne["workflow"]:
            initial = next(k for k, s in ne["workflow"]["states"].items() if s["kind"] == "initial")
            d.auto.append(f"alter table public.{t} add column state text not null default {S.q(initial)};\n"
                          f"alter table public.{t} alter column state drop default;\n"
                          f"create index {t}_state_idx on public.{t} (state);")
            d.ops.append(f"CHANGE {ne['name']} registry → process (state column added)")
        else:
            d.man("REMOVE_WORKFLOW", ne["name"], "the state column and the history would be lost",
                  f"-- alter table public.{t} drop column state;")
    if not oe["code_prefix"] and ne["code_prefix"]:
        d.auto.append(f"alter table public.{t} add column code text unique;\n"
                      f"update public.{t} set code = public.next_code({S.q(ne['code_prefix'])}) where code is null;\n"
                      f"alter table public.{t} alter column code set not null;")
        d.ops.append(f"ADD code to {ne['name']}")
    elif oe["code_prefix"] and ne["code_prefix"] and oe["code_prefix"] != ne["code_prefix"]:
        d.ops.append(f"CHANGE code prefix of {ne['name']} (new records only)")

    renamed: set[str] = set()
    for key, f in ne["fields"].items():
        of = oe["fields"].get(key)
        src = f.get("renamed_from")
        if not of and src and src in oe["fields"] and src not in ne["fields"]:
            of = oe["fields"][src]
            renamed.add(src)
            d.auto.append(_rename_field_sql(oe, of, key))
            d.ops.append(f"RENAME field {ne['name']}.{src} → {key}")
        if not of:
            _add_field(new, ne, f, d)
            continue
        changed = [k for k in STRUCT_KEYS if of.get(k) != f.get(k)]
        if of.get("default") != f.get("default") and not f["many"]:
            if f["default"] is None:
                d.auto.append(f"alter table public.{t} alter column {key} drop default;")
            else:
                d.auto.append(f"alter table public.{t} alter column {key} set default {S.literal(new, f, f['default'])};")
            d.ops.append(f"CHANGE default {ne['name']}.{key}")
        if not changed:
            continue
        if changed == ["required"] and not f["many"]:
            if f["required"]:
                d.man("SET_REQUIRED", f"{ne['name']}.{key}", "existing rows may be null: backfill, then set not null",
                      f"update public.{t} set {key} = <value> where {key} is null;\nalter table public.{t} alter column {key} set not null;")
            else:
                d.auto.append(f"alter table public.{t} alter column {key} drop not null;")
                d.ops.append(f"CHANGE {ne['name']}.{key} optional")
            continue
        if changed == ["unique"]:
            if f["unique"]:
                d.auto.append(f"alter table public.{t} add constraint {t}_{key}_key unique ({key});")
            else:
                d.auto.append(f"alter table public.{t} drop constraint if exists {t}_{key}_key;")
            d.ops.append(f"CHANGE unique {ne['name']}.{key}")
            continue
        if set(changed) <= {"min", "max", "max_length"}:
            d.man("CHANGE_CHECK", f"{ne['name']}.{key}", "column checks changed: verify existing data, then replace the constraint",
                  f"-- alter table public.{t} drop constraint <old check>; alter table public.{t} add check (...);")
            continue
        if changed == ["on_delete"] and f["type"] == "ref" and not f["many"]:
            d.auto.append(f"alter table public.{t} drop constraint if exists {t}_{key}_fkey;\n" + S.fk_sql(new, ne, f).split("create index")[0])
            d.ops.append(f"CHANGE on_delete {ne['name']}.{key}")
            continue
        d.man("CHANGE_FIELD", f"{ne['name']}.{key}", f"changed {', '.join(changed)}: data conversion needed",
              f"-- alter table public.{t} alter column {key} type {S.col_type(new, f)} using <conversion>;")
    for key, of in oe["fields"].items():
        if key not in ne["fields"] and key not in renamed:
            target = S.join_table_name(oe, of) if of["many"] else None
            sql = (f"-- drop table public.{target};" if target else
                   f"-- alter table public.{t} rename column {key} to <new_name>;  (rename)\n-- alter table public.{t} drop column {key};  (removal)")
            d.man("REMOVE_FIELD", f"{ne['name']}.{key}", "dropping loses data; rename the column if the field was renamed", sql)

    for i, ix in enumerate(ne["indexes"]):
        if ix not in oe["indexes"]:
            d.auto.append(f"create index if not exists {t}_ix_{'_'.join(ix)} on public.{t} ({', '.join(ix)});")
            d.ops.append(f"ADD index {ne['name']}({', '.join(ix)})")

    # workflow states removed: rows in those states must move
    if oe["workflow"] and ne["workflow"]:
        moved = {}
        for nk, nst in ne["workflow"]["states"].items():
            src = nst.get("renamed_from")
            if nk not in oe["workflow"]["states"] and src in oe["workflow"]["states"] and src not in ne["workflow"]["states"]:
                moved[src] = nk
        if moved:
            sql = [f"alter table public.{t} drop constraint if exists {t}_state_check;",
                   "select set_config('app.in_transition', 'on', true);"]
            for a, b in moved.items():
                sql += [f"update public.{t} set state = {S.q(b)} where state = {S.q(a)};",
                        f"update public.record_history set from_state = {S.q(b)} where entity = {S.q(ne['snake'])} and from_state = {S.q(a)};",
                        f"update public.record_history set to_state = {S.q(b)} where entity = {S.q(ne['snake'])} and to_state = {S.q(a)};",
                        f"update public.reminders_sent set state = {S.q(b)} where entity = {S.q(ne['snake'])} and state = {S.q(a)};"]
                d.ops.append(f"RENAME state {ne['name']}.{a} → {b}")
            sql.append("select set_config('app.in_transition', 'off', true);")
            d.auto.append("\n".join(sql))
        for st in oe["workflow"]["states"]:
            if st not in ne["workflow"]["states"] and st not in moved:
                d.man("REMOVE_STATE", f"{ne['name']}.{st}", "records in this state must be moved before the state check is replaced",
                      f"update public.{t} set state = '<other state>' where state = {S.q(st)};  -- runs with app.in_transition = on\n"
                      f"-- select set_config('app.in_transition', 'on', true); before the update")


def _rename_field_sql(oe: dict[str, Any], of: dict[str, Any], new_key: str) -> str:
    """Renames a column (or the join table of a many-reference) and its named constraints/indexes."""
    t, old = oe["table"], of["key"]
    if of["many"]:
        return (f"alter table public.{t}_{old} rename to {t}_{new_key};\n"
                f"alter index if exists public.{t}_{old}_target_idx rename to {t}_{new_key}_target_idx;")
    out = [f"alter table public.{t} rename column {old} to {new_key};"]
    for suffix in ("fkey", "key"):
        out.append(f"do $$ begin\n  if exists (select 1 from pg_constraint where conname = '{t}_{old}_{suffix}') then\n"
                   f"    alter table public.{t} rename constraint {t}_{old}_{suffix} to {t}_{new_key}_{suffix};\n  end if;\nend $$;")
    out.append(f"alter index if exists public.{t}_{old}_idx rename to {t}_{new_key}_idx;")
    return "\n".join(out)


def _add_field(m: dict[str, Any], e: dict[str, Any], f: dict[str, Any], d: Delta) -> None:
    t, key = e["table"], f["key"]
    if f["many"]:
        d.auto.append(S.join_table_sql(m, e, f))
        d.ops.append(f"ADD many-reference {e['name']}.{key}")
        return
    col = S.column_sql(m, e, f)
    if f["required"] and f["default"] is None and f["type"] != "bool":
        col = col.replace(" not null", "")
        d.auto.append(f"alter table public.{t} add column {col};")
        d.man("SET_REQUIRED", f"{e['name']}.{key}", "new required field without default: backfill existing rows, then set not null",
              f"update public.{t} set {key} = <value> where {key} is null;\nalter table public.{t} alter column {key} set not null;",
              phase="post")
    else:
        d.auto.append(f"alter table public.{t} add column {col};")
    if f["type"] == "ref":
        d.auto.append(S.fk_sql(m, e, f))
    d.ops.append(f"ADD field {e['name']}.{key}")
