"""The SQL engine of the behaviour model: PostgreSQL functions and triggers generated from `behavior.yaml`.

`engine_sql()` writes one idempotent migration (`create or replace`, `create … if not exists`, `drop trigger if
exists`) that runs the behaviour inside the database, as the modelled applications already do by hand:

- derived attributes: a `before insert or update` trigger per class computes them (in dependency order), and a
  trigger on each referenced table refreshes them when the rows they navigate to change;
- workflows: the state is set on insert and changes only through `<entity>_perform_transition(id, key, comment)`,
  which checks who performs it (`<entity>_principals`), the condition, the guard and the comment, writes
  `workflow_history`, emits `<entity>.transitioned` (and `.completed`, and the transition's own events) with the
  recipients of the reactions; `<entity>_available_transitions(id)` lists what the current user can do;
  `<entity>_run_timed_transitions()` and `<entity>_run_reminders()` are for the scheduler; `<entity>_revert`
  brings a record back to a state it has been in;
- events: `<entity>_emit(type, row, extra)` adds the recipients (`<entity>_recipients`) and calls the
  application's `emit_entity_event`; a lifecycle trigger emits `created`, `updated`, `deleted`.

The engine relies on a small contract the application provides (fallbacks are created when missing):
`current_profile_id()`, `is_admin()`, `has_role(role, scope)`, `role_members(role, scope)`,
`emit_entity_event(entity, id, type, extra)`. Messages are in the language of the metamodel.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import behavior as B
from . import core as M
from . import ecore as E
from . import expr as X

TODO = "TODO(modeler)"
HISTORY = "workflow_history"
REMINDERS = "workflow_reminders"
MESSAGES = {
    "it": {"not_found": "Record non trovato", "unknown": "Transizione sconosciuta: %", "unavailable": "Transizione non disponibile: %",
           "forbidden": "Operazione non consentita", "timed": "Transizione automatica: non eseguibile a mano",
           "guard": "Requisiti non soddisfatti: %", "required": "Campi richiesti nello stato %: %", "comment": "Commento obbligatorio",
           "state": "Lo stato cambia solo con le transizioni (%_perform_transition)", "revert": "Stato non raggiungibile: %"},
    "en": {"not_found": "Record not found", "unknown": "Unknown transition: %", "unavailable": "Transition not available: %",
           "forbidden": "Operation not allowed", "timed": "Automatic transition: it cannot be performed by hand",
           "guard": "Requirements not met: %", "required": "Required in state %: %", "comment": "Comment required",
           "state": "The state changes only through the transitions (%_perform_transition)", "revert": "State not reachable: %"},
}


def _lit(s: str) -> str:
    return "'" + s.replace("'", "''") + "'"


def _arr(items: list[str]) -> str:
    return "array[" + ", ".join(_lit(x) for x in items) + "]::text[]" if items else "'{}'::text[]"


def _fn(name: str, args: str, returns: str, body: str, language: str = "plpgsql", stable: bool = False) -> str:
    head = (f"create or replace function public.{name}({args})\nreturns {returns}\nlanguage {language}\n"
            + ("stable\n" if stable else "") + "security definer\nset search_path = ''\nas $$\n")
    return head + body.rstrip("\n") + "\n$$;\n"


class _Class:
    """What the generator needs about one class: table, entity key, state column, its workflow and reactions."""

    def __init__(self, e: dict[str, Any], b: dict[str, Any], cname: str, schema: str):
        self.e, self.b, self.cname, self.schema = e, b, cname, schema
        self.key = M.snake(cname)
        c = e["classes"][cname]
        self.table = f"{schema}.{c.get('table') or E.default_table(cname, e['language'])}"
        self.attrs, self.refs = E.features(e, cname)
        self.w = b["workflows"].get(cname)
        self.state_col = E.field_key(self.w["state"], self.attrs[self.w["state"]]) if self.w else None
        self.reactions = [r for r in b["reactions"] if str(r["event"]).split(".")[0] == cname]
        self.derivations = b["derivations"].get(cname, {})
        self.created_by = next((E.field_key(rn, r) for rn, r in self.refs.items()
                                if rn in ("createdBy", "created_by") and r["type"] in E.BUILTIN_CLASSES), None)

    def ctx(self, alias: str = "r", **variables: str) -> X.SqlContext:
        return X.SqlContext(self.e, self.cname, alias=alias, schema=self.schema, variables=variables)

    def principals_used(self) -> list[str]:
        """The principals that act on the class (workflow); recipients of notifications are resolved separately."""
        out: list[str] = []
        if self.w:
            for s in self.w["states"].values():
                out += s["owner"] + s["editable_by"]
            for t in self.w["transitions"].values():
                out += t["by"]
            if self.w.get("revert"):
                out += self.w["revert"]["by"] + self.w["revert"]["final_by"]
        seen: list[str] = []
        for p in out:
            if p not in seen:
                seen.append(p)
        return seen

    def scope_sql(self, role: str, path: str | None, alias: str = "r") -> str:
        """The id of the scope instance of a role, from a row of the class."""
        scope = self.b["roles"][role]["scope"]
        if path is None:
            refs = B._scope_reference(self.e, self.cname, scope)
            path = refs[0]
        node, _ = X.check(path, X.Context(self.e, self.cname))
        return X.compile_path(node, self.ctx(alias)).ids()

    def principal_case(self, p: str, alias: str = "r") -> str | None:
        """`case when <the current user is p> then '<key>' end`."""
        key = B.principal_key(p)
        if p == "admin":
            return "case when public.is_admin() then 'admin' end"
        if p == "creator":
            if not self.created_by:
                return None
            return f"case when {alias}.{self.created_by} = public.current_profile_id() then 'creator' end"
        if p.startswith("self."):
            node, t = X.check(p, X.Context(self.e, self.cname))
            if not t.endswith(X.CLASS + "User"):
                return None                                  # an Email attribute: a recipient, not an actor
            ps = X.compile_path(node, self.ctx(alias))
            if t.startswith(X.COLLECTION):
                return f"case when {ps.members('public.current_profile_id()')} then {_lit(key)} end"
            return f"case when {ps.ids()} = public.current_profile_id() then {_lit(key)} end"
        m = B.ROLE_AT.match(p)
        role, path = m.group("role"), m.group("path")
        scope = "null" if self.b["roles"][role].get("scope") is None else self.scope_sql(role, path, alias)
        return f"case when public.has_role({_lit(role)}, {scope}) then {_lit(key)} end"

    def recipient_select(self, p: str) -> str | None:
        """One branch of the recipients union: email and principal key for the users `p` denotes."""
        key = B.principal_key(p)
        test = f"{_lit(key)} = any (p_to)"
        if p == "creator":
            if not self.created_by:
                return None
            return f"select p.email as email, 'creator' as kind from public.profiles p where {test} and p.id = r.{self.created_by}"
        if p.startswith("self."):
            node, t = X.check(p, X.Context(self.e, self.cname))
            ps = X.compile_path(node, self.ctx())
            base = t[len(X.COLLECTION):] if t.startswith(X.COLLECTION) else t
            if base == "email":
                value = ps.value if not ps.frm else None
                if value is not None:
                    return f"select {value} as email, {_lit(key)} as kind where {test}"
                return f"select {ps.value} as email, {_lit(key)} as kind {ps.sub} and {test}"
            if not ps.frm:
                return None
            if ps.last_fk is not None and len(ps.frm) == 1:
                return f"select p.email as email, {_lit(key)} as kind from public.profiles p where {test} and p.id = {ps.last_fk}"
            return (f"select p.email as email, {_lit(key)} as kind from {' '.join(ps.frm)} join public.profiles p on p.id = {ps.alias}.id "
                    f"where {' and '.join(ps.where)} and {test}")
        m = B.ROLE_AT.match(p)
        role, path = m.group("role"), m.group("path")
        if role == "admin":
            scope = "null"
        else:
            scope = "null" if self.b["roles"][role].get("scope") is None else self.scope_sql(role, path)
        return (f"select p.email as email, {_lit(key)} as kind from public.role_members({_lit(role)}, {scope}) m "
                f"join public.profiles p on p.id = m where {test}")


# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #
def _contract(schema: str) -> str:
    return f"""-- ===================== Contract with the application =====================
-- The engine calls these functions; the application normally provides them (users, roles, event outbox).
-- A fallback is created only where none exists.
do $do$
begin
  if to_regprocedure('public.current_profile_id()') is null then
    -- {TODO}: the current user's profile id (the fallback reads the setting app.profile_id)
    create function public.current_profile_id() returns uuid language sql stable security definer set search_path = '' as
      'select nullif(current_setting(''app.profile_id'', true), '''')::uuid';
  end if;
  if to_regprocedure('public.has_role(text,uuid)') is null and to_regprocedure('public.has_role(public.app_role,uuid)') is null then
    if to_regclass('{schema}.user_roles') is not null then
      create function public.has_role(p_role text, p_scope uuid default null) returns boolean language sql stable security definer set search_path = '' as
        'select exists (select 1 from {schema}.user_roles ur where ur.profile_id = public.current_profile_id() and ur.role::text = p_role
                          and (p_scope is null or ur.scope_id is null or ur.scope_id = p_scope))';
    else
      -- {TODO}: has_role(role, scope): does the current user hold the role (in that scope)? Replace this stub.
      create function public.has_role(p_role text, p_scope uuid default null) returns boolean language plpgsql stable security definer set search_path = '' as
        'begin raise exception ''has_role() is not defined: the application provides the roles''; end';
    end if;
  end if;
  if to_regprocedure('public.is_admin()') is null then
    create function public.is_admin() returns boolean language sql stable security definer set search_path = '' as
      'select public.has_role(''admin'', null)';
  end if;
  if to_regprocedure('public.role_members(text,uuid)') is null then
    if to_regclass('{schema}.user_roles') is not null then
      create function public.role_members(p_role text, p_scope uuid default null) returns setof uuid language sql stable security definer set search_path = '' as
        'select ur.profile_id from {schema}.user_roles ur where ur.role::text = p_role
          and (p_scope is null or ur.scope_id is null or ur.scope_id = p_scope)';
    else
      -- {TODO}: role_members(role, scope): the users holding the role (in that scope). Replace this stub.
      create function public.role_members(p_role text, p_scope uuid default null) returns setof uuid language plpgsql stable security definer set search_path = '' as
        'begin raise exception ''role_members() is not defined: the application provides the roles''; end';
    end if;
  end if;
  if to_regprocedure('public.emit_entity_event(text,uuid,text,jsonb)') is null then
    -- the engine's own outbox when the application has none
    if to_regclass('{schema}.events') is null then
      create table {schema}.events (id uuid primary key default gen_random_uuid(), type text not null, entity text, entity_id uuid,
        data jsonb not null default '{{}}'::jsonb, actor_id uuid, occurred_at timestamptz not null default now());
      alter table {schema}.events enable row level security;
    end if;
    create function public.emit_entity_event(p_entity text, p_id uuid, p_type text, p_extra jsonb default '{{}}'::jsonb) returns uuid
      language sql security definer set search_path = '' as
      'insert into {schema}.events (type, entity, entity_id, data, actor_id) values (p_type, p_entity, p_id, coalesce(p_extra, ''{{}}''::jsonb),
         public.current_profile_id()) returning id';
  end if;
end
$do$;

-- ===================== Tables of the engine =====================
create table if not exists {schema}.{HISTORY} (
  id         uuid primary key default gen_random_uuid(),
  entity     text not null,
  entity_id  uuid not null,
  kind       text not null default 'transition' check (kind in ('transition', 'revert', 'system')),
  transition text,
  from_state text,
  to_state   text not null,
  actor_id   uuid,
  comment    text,
  created_at timestamptz not null default now()
);
create index if not exists {HISTORY}_entity_idx on {schema}.{HISTORY} (entity, entity_id, created_at desc);
alter table {schema}.{HISTORY} enable row level security;
drop policy if exists {HISTORY}_read on {schema}.{HISTORY};
create policy {HISTORY}_read on {schema}.{HISTORY} for select to authenticated using (public.current_profile_id() is not null);
grant select on {schema}.{HISTORY} to authenticated;

create table if not exists {schema}.{REMINDERS} (
  entity    text not null,
  entity_id uuid not null,
  state     text not null,
  count     int not null default 1,
  last_at   timestamptz not null default now(),
  primary key (entity, entity_id, state)
);
alter table {schema}.{REMINDERS} enable row level security;
"""


def _derivation_order(cls: _Class) -> list[str]:
    """Derived attributes in dependency order (a derivation after the ones of the same class it uses)."""
    deps: dict[str, set[str]] = {}
    nodes: dict[str, dict[str, Any]] = {}
    ctx = X.Context(cls.e, cls.cname)
    for an, text in cls.derivations.items():
        node, _ = X.check(str(text), ctx, X.feature_type(cls.attrs[an], cls.e, False))
        nodes[an] = node
        deps[an] = {ref[1] for ref in X.features_used(node) if len(ref) == 2 and ref[1] in cls.derivations and ref[1] != an}
    order: list[str] = []
    while len(order) < len(deps):
        ready = [a for a in deps if a not in order and deps[a] <= set(order)]
        if not ready:
            raise X.ExprError(f"derivations of {cls.cname} depend on each other")
        order += sorted(ready, key=list(deps).index)
    return order


def _derivations(cls: _Class, notes: list[str]) -> str:
    if not cls.derivations:
        return ""
    ctx = X.Context(cls.e, cls.cname)
    lines = [f"-- ---- {cls.cname}: derived attributes ----",
             f"create or replace function public.{cls.key}_derive()", "returns trigger", "language plpgsql", "set search_path = ''", "as $$", "begin"]
    refresh: dict[str, set[str]] = {}            # referenced class -> references of this class that lead to it
    for an in _derivation_order(cls):
        node, t = X.check(str(cls.derivations[an]), ctx, X.feature_type(cls.attrs[an], cls.e, False))
        sql = X.to_sql(node, cls.ctx("new"))
        if t == X.BOOL:
            sql = f"coalesce({sql}, false)"
        lines.append(f"  new.{E.field_key(an, cls.attrs[an])} := {sql};")
        for ref in X.features_used(node):
            if len(ref) > 2 and ref[1] in cls.refs:
                target = E.resolve_type(cls.e, cls.refs[ref[1]]["type"]) or cls.refs[ref[1]]["type"]
                refresh.setdefault(target, set()).add(ref[1])
                if len(ref) > 3:
                    notes.append(f"{cls.cname}.{an} navigates {'.'.join(ref[1:])}: only a change of the first hop "
                                 f"({ref[1]}) refreshes it")
    lines += ["  return new;", "end;", "$$;",
              f"drop trigger if exists {cls.key}_20_derive on {cls.table};",
              f"create trigger {cls.key}_20_derive before insert or update on {cls.table} for each row execute function public.{cls.key}_derive();", ""]
    store = X.ref_store(cls.e)
    for target, refs in sorted(refresh.items()):
        if target in E.BUILTIN_CLASSES:
            notes.append(f"{cls.cname}: derivations read the users ({', '.join(sorted(refs))}): a change of a profile does not refresh them")
            continue
        tcls = _Class(cls.e, cls.b, target, cls.schema)
        conds: list[str] = []
        for rn in sorted(refs):
            how = store[(cls.cname, rn)]
            if how["kind"] == "fk":
                conds.append(f"x.{how['column']} in (new.id, old.id)")
            elif how["kind"] == "inverse":
                conds.append(f"x.id in (new.{how['column']}, old.{how['column']})")
            else:
                notes.append(f"{cls.cname} via {rn}: a many-to-many reference is not refreshed when the join table changes ({TODO})")
        if not conds:
            continue
        fname = f"{tcls.key}_refresh_{cls.key}"
        lines += [f"-- a change of {target} refreshes the derived attributes of {cls.cname} ({', '.join(sorted(refs))})",
                  f"create or replace function public.{fname}()", "returns trigger", "language plpgsql", "security definer", "set search_path = ''", "as $$", "begin",
                  f"  update {cls.table} x set id = x.id where {' or '.join(conds)};", "  return null;", "end;", "$$;",
                  f"drop trigger if exists {fname} on {tcls.table};",
                  f"create trigger {fname} after insert or update or delete on {tcls.table} for each row execute function public.{fname}();", ""]
    return "\n".join(lines) + "\n"


def _principals(cls: _Class, notes: list[str]) -> str:
    cases = ["case when public.current_profile_id() is not null then 'all' end", "case when public.is_admin() then 'admin' end"]
    if cls.created_by:
        cases.append(f"case when r.{cls.created_by} = public.current_profile_id() then 'creator' end")
    for p in cls.principals_used():
        if p in ("admin", "creator"):
            if p == "creator" and not cls.created_by:
                notes.append(f"{cls.cname}: 'creator' needs a reference createdBy: User ({TODO}: nobody is the creator)")
            continue
        c = cls.principal_case(p)
        if c and c not in cases:
            cases.append(c)
    body = "  select array_remove(array[\n    " + ",\n    ".join(cases) + "\n  ]::text[], null);"
    return (f"-- ---- {cls.cname}: who the current user is for a record ----\n"
            + _fn(f"{cls.key}_principals", f"r {cls.table}", "text[]", body, "sql", stable=True))


def _template_vars(cls: _Class) -> str:
    """<entity>_template_vars(r, p_extra): the values the placeholders of the notification texts resolve to, as a
    jsonb {placeholder: text}: the record's paths the templates of this class use (`self.<path>` and
    `<entity>.<path>`), the actor, the comment, the url (public.record_url(entity, id) when the application has it),
    the transition and the state (labels in the language of the metamodel), the reminder."""
    lang = cls.e.get("language") or "en"
    uses = B.template_uses(cls.b)
    paths: dict[str, str] = {}
    for key, langs in cls.b["templates"].items():
        if not any(u[0] == cls.cname for u in uses.get(key, [])):
            continue
        for tx in langs.values():
            for field in ("subject", "body"):
                for name in B.PLACEHOLDER.findall(tx.get(field) or ""):
                    head, _, path = name.partition(".")
                    if head in ("self", cls.key) and path and path != "id" and path not in paths:
                        try:
                            node, _ = X.check(path, X.Context(cls.e, cls.cname))
                            paths[path] = f"({X.to_sql(node, cls.ctx())})::text"
                        except X.ExprError:
                            continue                                   # validate reports it
    pairs = [("'self.id'", "r.id::text"), (_lit(f"{cls.key}.id"), "r.id::text"),
             ("'actor.email'", "(select p.email from public.profiles p where p.id = (p_extra ->> 'actor')::uuid)"),
             ("'actor.name'", "(select coalesce(to_jsonb(p) ->> 'full_name', to_jsonb(p) ->> 'name', to_jsonb(p) ->> 'display_name', p.email) "
                              "from public.profiles p where p.id = (p_extra ->> 'actor')::uuid)"),
             ("'comment'", "p_extra ->> 'comment'"), ("'url'", "v_url")]
    for path, sql in paths.items():
        pairs += [(_lit(f"self.{path}"), sql), (_lit(f"{cls.key}.{path}"), sql)]
    if cls.w:
        tl = "\n".join(f"      when {_lit(tn)} then {_lit(B._lbl(tr, tn, lang))}" for tn, tr in cls.w["transitions"].items())
        sl = "\n".join(f"      when {_lit(sn)} then {_lit(B._lbl(st, sn, lang))}" for sn, st in cls.w["states"].items())
        pairs += [("'transition.key'", "p_extra -> 'transition' ->> 'key'"), ("'transition.from'", "p_extra -> 'transition' ->> 'from'"),
                  ("'transition.to'", "p_extra -> 'transition' ->> 'to'"),
                  ("'transition.label'", f"case p_extra -> 'transition' ->> 'key'\n{tl}\n    end"),
                  ("'state.key'", f"r.{cls.state_col}"), ("'state.label'", f"case r.{cls.state_col}\n{sl}\n    end"),
                  ("'reminder.days'", "extract(day from (p_extra -> 'reminder' ->> 'after')::interval)::int::text"),
                  ("'reminder.count'", "p_extra -> 'reminder' ->> 'count'"), ("'reminder.state'", "p_extra -> 'reminder' ->> 'state'")]
    obj = ",\n    ".join(f"{k}, {v}" for k, v in pairs)
    body = f"""declare
  v_url text;
begin
  if to_regprocedure('public.record_url(text,uuid)') is not null then
    execute 'select public.record_url($1, $2)' into v_url using {_lit(cls.key)}, r.id;
  end if;
  return jsonb_strip_nulls(jsonb_build_object(
    {obj}));
end;"""
    return _fn(f"{cls.key}_template_vars", f"r {cls.table}, p_extra jsonb default '{{}}'::jsonb", "jsonb", body, stable=True)


RENDER_TEMPLATE = """-- ---- render_template: the placeholders {{name}} of a notification text replaced by the values ----
create or replace function public.render_template(p_text text, p_vars jsonb)
returns text
language plpgsql
immutable
set search_path = ''
as $$
declare
  v text := p_text;
  m text[];
begin
  if p_text is null then return null; end if;
  for m in select regexp_matches(p_text, '\\{\\{\\s*([A-Za-z_][A-Za-z0-9_.]*)\\s*\\}\\}', 'g') loop
    v := regexp_replace(v, '\\{\\{\\s*' || replace(m[1], '.', '\\.') || '\\s*\\}\\}',
                        replace(coalesce(p_vars ->> m[1], ''), '\\', '\\\\'), 'g');
  end loop;
  return v;
end;
$$;

"""


def _recipients(cls: _Class) -> str:
    branches: list[str] = []
    seen: set[str] = set()
    reminded = {s: spec for s, spec in (cls.w or {"states": {}})["states"].items() if spec.get("reminder")}
    wanted = [p for r in cls.reactions for p in r["notify"]] + [p for spec in reminded.values() for p in spec["owner"]]
    for p in wanted:
        if p in seen:
            continue
        seen.add(p)
        sel = cls.recipient_select(p)
        if sel:
            branches.append(sel)
    if not branches:
        branches.append("select null::text as email, null::text as kind where false")
    lang = cls.e.get("language") or "en"
    tpls = {k: langs for k, langs in cls.b["templates"].items() if any(u[0] == cls.cname for u in B.template_uses(cls.b).get(k, []))}
    subj = "\n".join(f"    when {_lit(k)} then {_lit(langs[lang]['subject'])}" for k, langs in tpls.items() if langs.get(lang))
    bdy = "\n".join(f"    when {_lit(k)} then {_lit(langs[lang]['body'])}" for k, langs in tpls.items() if langs.get(lang))
    body = f"""declare
  v_vars jsonb;
  v_subject text;
  v_body text;
  v_subject_o text;
  v_body_o text;
  v_rows jsonb;
begin
  -- the texts of the model (language of the metamodel: {lang}); a row of notification_templates (key x locale) overrides them
  v_subject := case p_template
{subj or "    when null then null"}
  end;
  v_body := case p_template
{bdy or "    when null then null"}
  end;
  if to_regclass('public.notification_templates') is not null then
    execute 'select t.subject, t.body from public.notification_templates t where t.key = $1 and t.locale = $2'
      into v_subject_o, v_body_o using p_template, {_lit(lang)};
    if v_subject_o is not null then v_subject := v_subject_o; v_body := coalesce(v_body_o, v_body); end if;
  end if;
  v_vars := public.{cls.key}_template_vars(r, coalesce(p_extra, '{{}}'::jsonb));
  select coalesce(jsonb_agg(jsonb_build_object('email', email, 'principal', kind, 'template', p_template,
           'subject', public.render_template(v_subject, v_vars), 'body', public.render_template(v_body, v_vars)) order by email), '[]'::jsonb)
    into v_rows
    from (select distinct on (email) email, kind from (
    {chr(10).join('    union all' + chr(10) + '    ' + br if i else '    ' + br for i, br in enumerate(branches))}
    ) s where email is not null order by email, kind) d;
  return v_rows;
end;"""
    out = (f"-- ---- {cls.cname}: the values the notification texts may use ----\n" + _template_vars(cls)
           + f"-- ---- {cls.cname}: recipients of a notification (emails of the principals, subject and body rendered) ----\n"
           + _fn(f"{cls.key}_recipients", f"r {cls.table}, p_to text[], p_template text, p_extra jsonb default '{{}}'::jsonb", "jsonb", body, stable=True))
    # the reactions: which recipients an event carries
    lines = ["declare", "  v jsonb := '[]'::jsonb;", "begin"]
    for r in cls.reactions:
        event = str(r["event"]).split(".")[1]
        cond = "true"
        if r.get("when") is not None:
            node, _ = X.check(str(r["when"]), B.context(cls.e, cls.b, cls.cname, event), X.BOOL)
            cond = f"coalesce({X.to_sql(node, cls.ctx(transition=chr(40) + chr(112) + '_extra -> ' + chr(39) + 'transition' + chr(39) + ' ->> ' + chr(39) + 'key' + chr(39) + chr(41)))}, false)"
        lines += [f"  -- {r['name']}",
                  f"  if p_type = {_lit(cls.key + '.' + event)} and {cond} then",
                  f"    v := v || public.{cls.key}_recipients(r, {_arr([B.principal_key(p) for p in r['notify']])}, {_lit(str(r['template']))}, p_extra);",
                  "  end if;"]
    if reminded:
        cases = "\n".join(f"      when {_lit(st)} then {_arr([B.principal_key(p) for p in spec['owner']])}" for st, spec in reminded.items())
        lines += ["  -- a reminder goes to the owners of the state",
                  f"  if p_type = {_lit(cls.key + '.reminder')} then",
                  f"    v := v || public.{cls.key}_recipients(r, case r.{cls.state_col}\n{cases}\n      else '{{}}'::text[] end, p_extra -> 'reminder' ->> 'template', p_extra);",
                  "  end if;"]
    lines += ["  -- one entry per address (the first reaction wins)",
              "  return coalesce((select jsonb_agg(x) from (select distinct on (x ->> 'email') x from jsonb_array_elements(v) x order by x ->> 'email') d), '[]'::jsonb);",
              "end;"]
    out += _fn(f"{cls.key}_notifications", f"p_type text, r {cls.table}, p_extra jsonb", "jsonb", "\n".join(lines))
    out += _fn(f"{cls.key}_emit", f"p_type text, r {cls.table}, p_extra jsonb default '{{}}'::jsonb", "uuid",
               f"  select public.emit_entity_event({_lit(cls.key)}, r.id, p_type,\n"
               f"    coalesce(p_extra, '{{}}'::jsonb) || jsonb_build_object('recipients', public.{cls.key}_notifications(p_type, r, coalesce(p_extra, '{{}}'::jsonb))));",
               "sql")
    lines = ["begin",
             f"  if tg_op = 'INSERT' then perform public.{cls.key}_emit({_lit(cls.key + '.created')}, new); return new; end if;",
             f"  if tg_op = 'UPDATE' then perform public.{cls.key}_emit({_lit(cls.key + '.updated')}, new); return new; end if;",
             f"  perform public.{cls.key}_emit({_lit(cls.key + '.deleted')}, old); return old;",
             "end;"]
    out += _fn(f"{cls.key}_lifecycle", "", "trigger", "\n".join(lines))
    out += (f"drop trigger if exists {cls.key}_90_lifecycle on {cls.table};\n"
            f"create trigger {cls.key}_90_lifecycle after insert or update or delete on {cls.table} for each row execute function public.{cls.key}_lifecycle();\n")
    return out


def _requires(cls: _Class, state: dict[str, Any], alias: str) -> list[tuple[str, str]]:
    """The fields a state requires (`requires`), each with the SQL that tests it on `alias` (`is not null`,
    `exists (…)` for a collection)."""
    out: list[tuple[str, str]] = []
    for f, text in B.requires_tests(cls.e, cls.cname, state):
        node, _ = X.check(text, X.Context(cls.e, cls.cname), X.BOOL)
        out.append((f, X.to_sql(node, cls.ctx(alias))))
    return out


def _workflow(cls: _Class, msgs: dict[str, str], notes: list[str]) -> str:
    w = cls.w
    assert w is not None
    k, tbl, sc = cls.key, cls.table, cls.state_col
    initial = next(s for s, spec in w["states"].items() if spec["initial"])
    finals = [s for s, spec in w["states"].items() if spec["final"]]
    ctx = X.Context(cls.e, cls.cname)
    out = f"-- ---- {cls.cname}: workflow ----\n"
    # the state is set on insert and changes only through the transitions
    required: list[str] = []                                   # fields a state requires while the record is there
    for sn, s in w["states"].items():
        for f, sql_new in _requires(cls, s, "new"):
            if cls.attrs.get(f, cls.refs.get(f, {})).get("upper", 1) == 1:
                required.append(f"  if new.{sc} = {_lit(sn)} and not coalesce({sql_new}, false) then\n"
                                f"    raise exception {_lit(msgs['required'])}, {_lit(sn)}, {_lit(f)} using errcode = '23514';\n  end if;")
    out += _fn(f"{k}_workflow_guard", "", "trigger", f"""begin
  if tg_op = 'INSERT' then
    if new.{sc} is null then new.{sc} := {_lit(initial)}; end if;
  elsif new.{sc} is distinct from old.{sc} and coalesce(current_setting('app.in_transition', true), '') <> 'on' then
    raise exception {_lit(msgs['state'].replace('%', k))};
  end if;
{chr(10).join(required) + chr(10) if required else ''}  return new;
end;""")
    out += (f"drop trigger if exists {k}_10_workflow on {tbl};\n"
            f"create trigger {k}_10_workflow before insert or update on {tbl} for each row execute function public.{k}_workflow_guard();\n")
    # who may edit a record in its state
    cases = "\n".join(f"    when {_lit(s)} then {_arr([B.principal_key(p) for p in spec['editable_by']])}" for s, spec in w["states"].items())
    out += _fn(f"{k}_can_edit", f"r {tbl}", "boolean",
               f"  select public.{k}_principals(r) && (array['admin'] || case r.{sc}\n{cases}\n    else '{{}}'::text[] end);", "sql", stable=True)
    # one block per transition
    blocks: list[str] = []
    avail: list[str] = []
    for tn, t in w["transitions"].items():
        cond = "true"
        guard = "true"
        if t.get("when") is not None:
            node, _ = X.check(str(t["when"]), ctx, X.BOOL)
            cond = f"coalesce({X.to_sql(node, cls.ctx())}, false)"
        if t.get("guard") is not None:
            node, _ = X.check(str(t["guard"]), ctx, X.BOOL)
            guard = f"coalesce({X.to_sql(node, cls.ctx())}, false)"
        timed = t.get("at") is not None
        req = _requires(cls, w["states"].get(t["to"]) or {}, "r")     # the fields the target state requires
        missing = ("array_remove(array[" + ", ".join(f"case when not coalesce({sql}, false) then {_lit(f)} end" for f, sql in req)
                   + "]::text[], null)") if req else "'{}'::text[]"
        blocks.append(f"""  {'if' if not blocks else 'elsif'} p_key = {_lit(tn)} then
    v_from := {_arr(t['from'])}; v_to := {_lit(t['to'])}; v_allowed := {_arr([B.principal_key(p) for p in t['by']])};
    v_timed := {'true' if timed else 'false'}; v_comment := {_lit(t.get('comment') or 'optional')}; v_emits := {_arr([f'{k}.{ev}' for ev in t['emits']])};
    v_cond := {cond};
    v_guard := {guard}; v_guard_text := {_lit(X.to_text(X.parse(str(t['guard']))) if t.get('guard') is not None else '')};
    v_missing := {missing};""")
        if not timed:
            label = t.get("label") if isinstance(t.get("label"), dict) else {}
            guard_ok = f"({guard} and cardinality({missing}) = 0)" if req else guard
            missing_key = f", 'missing', to_jsonb({missing})" if req else ""
            avail.append(f"""    select jsonb_build_object('key', {_lit(tn)}, 'to', {_lit(t['to'])}, 'label', {_lit(B.json_text(label))}::jsonb,
                             'comment', {_lit(t.get('comment') or 'optional')}, 'guard_ok', {guard_ok}, 'guard', {_lit(X.to_text(X.parse(str(t['guard']))) if t.get('guard') is not None else '')}{missing_key}) as j
     where r.{sc} = any ({_arr(t['from'])}) and {cond} and v_p && (array['admin'] || {_arr([B.principal_key(p) for p in t['by']])})""")
    final_test = f"v_to = any ({_arr(finals)})"
    out += _fn(f"{k}_perform_transition", "p_id uuid, p_key text, p_comment text default null, p_system boolean default false", "uuid", f"""declare
  r public.{tbl.split('.', 1)[1]}%rowtype;
  v_from text[]; v_to text; v_allowed text[]; v_timed boolean; v_comment text; v_emits text[];
  v_cond boolean; v_guard boolean; v_guard_text text; v_missing text[];
  v_state text; v_hist uuid; v_extra jsonb; v_ev text;
  v_actor uuid := public.current_profile_id();
begin
  select * into r from {tbl} where id = p_id for update;
  if not found then raise exception {_lit(msgs['not_found'])}; end if;
{chr(10).join(blocks)}
  else
    raise exception {_lit(msgs['unknown'])}, p_key;
  end if;
  if not (r.{sc} = any (v_from)) then raise exception {_lit(msgs['unavailable'])}, p_key; end if;
  if v_timed and not p_system then raise exception {_lit(msgs['timed'])}; end if;
  if not v_timed and not p_system and not (public.{k}_principals(r) && (array['admin'] || v_allowed)) then
    raise exception {_lit(msgs['forbidden'])} using errcode = '42501';
  end if;
  if not v_cond then raise exception {_lit(msgs['unavailable'])}, p_key; end if;
  if not v_guard then raise exception {_lit(msgs['guard'])}, v_guard_text; end if;
  if cardinality(v_missing) > 0 then raise exception {_lit(msgs['required'])}, v_to, array_to_string(v_missing, ', ') using errcode = '23514'; end if;
  if v_comment = 'required' and nullif(trim(coalesce(p_comment, '')), '') is null then raise exception {_lit(msgs['comment'])}; end if;
  v_state := r.{sc};
  perform set_config('app.in_transition', 'on', true);
  update {tbl} set {sc} = v_to where id = p_id;
  perform set_config('app.in_transition', 'off', true);
  insert into {cls.schema}.{HISTORY} (entity, entity_id, kind, transition, from_state, to_state, actor_id, comment)
  values ({_lit(k)}, p_id, case when p_system and v_actor is null then 'system' else 'transition' end, p_key, v_state, v_to, v_actor,
          nullif(trim(coalesce(p_comment, '')), ''))
  returning id into v_hist;
  select * into r from {tbl} where id = p_id;
  v_extra := jsonb_build_object('transition', jsonb_build_object('key', p_key, 'from', v_state, 'to', v_to, 'timed', v_timed),
                                'actor', v_actor, 'comment', nullif(trim(coalesce(p_comment, '')), ''));
  perform public.{k}_emit({_lit(k + '.transitioned')}, r, v_extra);
  if {final_test} then perform public.{k}_emit({_lit(k + '.completed')}, r, v_extra); end if;
  foreach v_ev in array v_emits loop perform public.{k}_emit(v_ev, r, v_extra); end loop;
  return v_hist;
end;""")
    out += _fn(f"{k}_available_transitions", "p_id uuid", "jsonb", f"""declare
  r public.{tbl.split('.', 1)[1]}%rowtype;
  v_p text[];
begin
  select * into r from {tbl} where id = p_id;
  if not found then return '[]'::jsonb; end if;
  v_p := public.{k}_principals(r);
  return coalesce((select jsonb_agg(t.j) from (
{chr(10).join('    union all'.join([a]) if i == 0 else '    union all' + chr(10) + a for i, a in enumerate(avail))}
  ) t), '[]'::jsonb);
end;""", stable=True)
    # timed transitions and reminders
    timed_loops: list[str] = []
    for tn, t in w["transitions"].items():
        if t.get("at") is None:
            continue
        m = B.AT.match(str(t["at"]).strip())
        col = E.field_key(m.group("path"), cls.attrs[m.group("path")])
        offset = B.offset_interval(f"{m.group('n')}{m.group('unit')}") if m.group("n") else ""
        due = f"x.{col}" + (f" + interval {_lit(offset)}" if offset else "")
        if m.group("sign") == "-":
            due = f"x.{col} - interval {_lit(offset)}"
        timed_loops.append(f"""  for v_id in select x.id from {tbl} x where x.{sc} = any ({_arr(t['from'])}) and {due} <= now() loop
    begin
      perform public.{k}_perform_transition(v_id, {_lit(tn)}, null, true);
      v_count := v_count + 1;
    exception when others then
      raise warning 'timed transition {k}.{tn} on % skipped: %', v_id, sqlerrm;
    end;
  end loop;""")
    out += _fn(f"{k}_run_timed_transitions", "", "int", "declare\n  v_id uuid;\n  v_count int := 0;\nbegin\n"
               + ("\n".join(timed_loops) if timed_loops else "  -- no timed transitions") + "\n  return v_count;\nend;")
    rem_states = {s: spec["reminder"] for s, spec in w["states"].items() if spec.get("reminder")}
    rem_cases = "\n".join(f"      when {_lit(s)} then interval {_lit(B.offset_interval(spec['after']))}" for s, spec in rem_states.items())
    tmpl_cases = "\n".join(f"      when {_lit(s)} then {_lit(spec.get('template') or s + '_reminder')}" for s, spec in rem_states.items())
    if rem_states:
        body = f"""declare
  v_rec record;
  r public.{tbl.split('.', 1)[1]}%rowtype;
  v_n int;
  v_count int := 0;
begin
  for v_rec in
    select x.id, x.{sc} as state,
           case x.{sc}
{rem_cases}
           end as after,
           case x.{sc}
{tmpl_cases}
           end as template
      from {tbl} x
     where x.{sc} = any ({_arr(list(rem_states))})
       and coalesce((select max(h.created_at) from {cls.schema}.{HISTORY} h where h.entity = {_lit(k)} and h.entity_id = x.id), x.created_at)
           <= now() - (case x.{sc}
{rem_cases}
           end)
       and not exists (select 1 from {cls.schema}.{REMINDERS} rs where rs.entity = {_lit(k)} and rs.entity_id = x.id and rs.state = x.{sc}
                         and rs.last_at > now() - (case x.{sc}
{rem_cases}
           end))
  loop
    select * into r from {tbl} where id = v_rec.id;
    insert into {cls.schema}.{REMINDERS} as rs (entity, entity_id, state) values ({_lit(k)}, v_rec.id, v_rec.state)
    on conflict (entity, entity_id, state) do update set count = rs.count + 1, last_at = now()
    returning count into v_n;
    perform public.{k}_emit({_lit(k + '.reminder')}, r, jsonb_build_object('reminder', jsonb_build_object('state', v_rec.state, 'after', v_rec.after::text,
                                                                                           'template', v_rec.template, 'count', v_n)));
    v_count := v_count + 1;
  end loop;
  return v_count;
end;"""
    else:
        body = "begin\n  return 0;  -- no state has a reminder\nend;"
    out += _fn(f"{k}_run_reminders", "", "int", body)
    rv = w.get("revert")
    if rv:
        out += _fn(f"{k}_revert", "p_id uuid, p_state text, p_comment text default null", "uuid", f"""declare
  r public.{tbl.split('.', 1)[1]}%rowtype;
  v_hist uuid;
  v_actor uuid := public.current_profile_id();
begin
  select * into r from {tbl} where id = p_id for update;
  if not found then raise exception {_lit(msgs['not_found'])}; end if;
  if not (public.{k}_principals(r) && (array['admin'] || case when r.{sc} = any ({_arr(finals)}) then {_arr([B.principal_key(p) for p in rv['final_by']])}
                                                           else {_arr([B.principal_key(p) for p in rv['by']])} end)) then
    raise exception {_lit(msgs['forbidden'])} using errcode = '42501';
  end if;
  if p_state = r.{sc} or not exists (select 1 from {cls.schema}.{HISTORY} h where h.entity = {_lit(k)} and h.entity_id = p_id
                                    and (h.from_state = p_state or h.to_state = p_state)) then
    raise exception {_lit(msgs['revert'])}, p_state;
  end if;
  {"if nullif(trim(coalesce(p_comment, '')), '') is null then raise exception " + _lit(msgs['comment']) + "; end if;" if rv.get('comment') == 'required' else ''}
  insert into {cls.schema}.{HISTORY} (entity, entity_id, kind, from_state, to_state, actor_id, comment)
  values ({_lit(k)}, p_id, 'revert', r.{sc}, p_state, v_actor, nullif(trim(coalesce(p_comment, '')), '')) returning id into v_hist;
  perform set_config('app.in_transition', 'on', true);
  update {tbl} set {sc} = p_state where id = p_id;
  perform set_config('app.in_transition', 'off', true);
  select * into r from {tbl} where id = p_id;
  perform public.{k}_emit({_lit(k + '.reverted')}, r, jsonb_build_object('revert', jsonb_build_object('to', p_state), 'actor', v_actor,
                                                                        'comment', nullif(trim(coalesce(p_comment, '')), '')));
  return v_hist;
end;""")
    notes.append(f"{cls.cname}: schedule public.{k}_run_timed_transitions() and public.{k}_run_reminders() (pg_cron, see the end of the file)")
    return out


def engine_sql(raw: dict[str, Any], metamodel: dict[str, Any], schema: str = "public") -> tuple[str, list[str]]:
    """The SQL of the behaviour (one idempotent migration) and the notes to review. Assumes a valid model."""
    e = E.expand(metamodel)
    b = B.expand(raw)
    msgs = MESSAGES.get(e["language"]) or MESSAGES["en"]
    notes: list[str] = []
    classes = []
    for cname in e["classes"]:
        if e["classes"][cname]["abstract"] or cname in E.BUILTIN_CLASSES:
            continue
        cls = _Class(e, b, cname, schema)
        if cls.w or cls.derivations or cls.reactions:
            classes.append(cls)
    head = (f"-- Behaviour engine generated from {B.BEHAVIOR_FILE} by the modeler ({dt.date.today():%Y-%m-%d}).\n"
            "-- Idempotent: regenerate it with `modeler engine --write` after every change of the behaviour; do not edit by hand.\n"
            "-- Functions: <entity>_perform_transition, _available_transitions, _revert, _run_timed_transitions, _run_reminders,\n"
            "-- _principals, _can_edit, _template_vars, _recipients (subject and body of the notification texts rendered), _emit;\n"
            "-- triggers: state and derived attributes before insert/update, lifecycle events after.\n\n")
    parts = [head, _contract(schema), RENDER_TEMPLATE]
    events: list[str] = []
    for cls in classes:
        parts.append(f"\n-- ===================== {cls.cname} ({cls.table}) =====================\n")
        parts.append(_principals(cls, notes))
        parts.append(_recipients(cls))
        parts.append(_derivations(cls, notes))
        if cls.w:
            parts.append(_workflow(cls, msgs, notes))
        events += [f"{cls.key}.{ev}" for ev in B.events_of(b, cls.cname)]
    tail = ["", "-- ===================== To review ====================="]
    tail.append(f"-- {TODO}: if the application keeps a catalogue of event types (table event_types), register: {', '.join(events)}")
    tail.append(f"-- {TODO}: row level security: the engine gives <entity>_can_edit(r) for the update policies; read, create and delete "
                "are not modelled")
    for cls in classes:
        if cls.w:
            tail.append(f"-- {TODO}: scheduling (pg_cron):")
            tail.append(f"--   select cron.schedule('{cls.key}_timed', '0 1 * * *', $$select public.{cls.key}_run_timed_transitions()$$);")
            tail.append(f"--   select cron.schedule('{cls.key}_reminders', '0 7 * * *', $$select public.{cls.key}_run_reminders()$$);")
    for n in notes:
        if TODO in n:
            tail.append(f"-- {n}")
    return "\n".join(parts) + "\n".join(tail) + "\n", notes
