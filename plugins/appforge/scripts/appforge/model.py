"""Loading, normalisation and validation of an appforge domain model (app.yaml).

The model is the single source of truth of a generated application. This module
turns the YAML written by the developer into a normalised dictionary (every
optional attribute filled in, labels expanded to every locale) and checks it
against the metamodel rules. Generators only ever see normalised models.
"""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

IDENT = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
ENTITY_NAME = re.compile(r"^[A-Z][A-Za-z0-9]{1,39}$")
ENUM_NAME = ENTITY_NAME
EVENT_NAME = re.compile(r"^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$")
SLUG = re.compile(r"^[a-z][a-z0-9-]{1,49}$")
CODE_PREFIX = re.compile(r"^[A-Z]{2,6}$")
OFFSET = re.compile(r"^\s*([a-z][a-z0-9_]*)\s*(?:([+-])\s*(\d+)\s*([dhm]))?\s*$")

FIELD_TYPES = {
    "string", "text", "email", "url", "int", "number", "money", "bool", "date", "datetime", "enum", "ref", "json",
}
RESERVED_FIELDS = {"id", "state", "created_by", "created_at", "updated_at", "data", "entity", "type"}
RESERVED_ROLES = {"admin"}
STATE_KINDS = {"initial", "normal", "final"}
CLAUSE_OPS = {"eq", "neq", "in", "not_in", "gt", "gte", "lt", "lte", "is_true", "is_false", "is_set", "is_empty"}
UNARY_OPS = {"is_true", "is_false", "is_set", "is_empty"}
REACTION_KINDS = {"notify", "set", "transition", "schedule", "broadcast", "custom"}
PERMISSION_ACTIONS = ("read", "create", "update", "delete")
AUTO_EVENTS_ALL = ("created", "updated", "deleted")
AUTO_EVENTS_PROCESS = ("transitioned", "completed", "reminder")
STATE_COLORS = ["#64748b", "#2563eb", "#7c3aed", "#d97706", "#0891b2", "#16a34a", "#dc2626", "#db2777"]


class ModelError(Exception):
    """Raised when the model cannot be loaded at all (syntax, missing file)."""


@dataclass
class Report:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def error(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")

    @property
    def ok(self) -> bool:
        return not self.errors

    def render(self) -> str:
        lines = [f"ERROR   {e}" for e in self.errors] + [f"WARNING {w}" for w in self.warnings]
        if not lines:
            return "Model OK"
        summary = f"{len(self.errors)} error(s), {len(self.warnings)} warning(s)"
        return "\n".join(lines + [summary])


# --------------------------------------------------------------------------- #
# Naming helpers
# --------------------------------------------------------------------------- #
def snake(name: str) -> str:
    s = re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name)
    s = re.sub(r"(?<=[A-Z])([A-Z][a-z])", r"_\1", s)
    return s.lower()


def pluralize(word: str) -> str:
    if re.search(r"[^aeiou]y$", word):
        return word[:-1] + "ies"
    if re.search(r"(s|x|z|sh|ch)$", word):
        return word + "es"
    return word + "s"


def humanize(key: str) -> str:
    words = re.sub(r"[_\-]+", " ", snake(key) if key[:1].isupper() else key).strip()
    return words[:1].upper() + words[1:]


def parse_offset(expr: str) -> tuple[str, str] | None:
    """'start_date - 3d' -> ('start_date', "-'3 days'::interval"). None if invalid."""
    m = OFFSET.match(str(expr))
    if not m:
        return None
    fld, sign, amount, unit = m.groups()
    if not sign:
        return fld, ""
    unit_name = {"d": "days", "h": "hours", "m": "minutes"}[unit]
    return fld, f" {sign} interval '{amount} {unit_name}'"


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def import_yaml():
    """PyYAML if installed, else the vendored pure-Python copy (scripts/vendor)."""
    try:
        import yaml  # type: ignore
        return yaml
    except ImportError:
        import sys
        vendor = str(Path(__file__).resolve().parents[1] / "vendor")
        if vendor not in sys.path:
            sys.path.append(vendor)
        import yaml  # type: ignore
        return yaml


def metamodel_beside(path: str | Path) -> Path | None:
    """domain.ecore.yaml next to an app.yaml: the structure of the domain lives there."""
    path = Path(path)
    if path.name not in ("app.yaml", "app.yml"):
        return None
    meta = path.resolve().parent / "domain.ecore.yaml"
    return meta if meta.exists() else None


def load(path: str | Path) -> dict[str, Any]:
    """The raw appforge model: app.yaml, composed with domain.ecore.yaml when present."""
    raw = load_file(path)
    meta = metamodel_beside(path)
    if meta is not None:
        from . import ecore
        raw = ecore.compose(ecore.load(meta), raw)
    return raw


def load_file(path: str | Path) -> dict[str, Any]:
    """One YAML/JSON file as written (no composition)."""
    path = Path(path)
    if not path.exists():
        raise ModelError(f"model file not found: {path}")
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".json":
        return json.loads(text)
    yaml = import_yaml()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ModelError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ModelError(f"{path}: the model must be a mapping")
    _fix_on_keys(data)
    return data


def dump(raw: dict[str, Any], path: str | Path) -> None:
    """Writes a raw model back to YAML (used by the Studio). Comments are not preserved."""
    yaml = import_yaml()
    path = Path(path)
    header = "# yaml-language-server: $schema=.appforge/app.schema.json\n# Domain model (appforge). Edit here, in the Studio (/appforge:studio) or with /appforge:model.\n"
    text = yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)
    path.write_text(header + text, encoding="utf-8")


def dumps(raw: dict[str, Any]) -> str:
    yaml = import_yaml()
    return yaml.safe_dump(raw, sort_keys=False, allow_unicode=True, default_flow_style=False, width=120)


def loads(text: str) -> dict[str, Any]:
    yaml = import_yaml()
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise ModelError(f"invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise ModelError("the model must be a mapping")
    _fix_on_keys(data)
    return data


def _fix_on_keys(data: dict[str, Any]) -> None:
    """YAML 1.1 reads a bare `on:` key as the boolean true: restore it in reactions."""
    for r in data.get("reactions") or []:
        if isinstance(r, dict) and True in r:
            r["on"] = r.pop(True)


# --------------------------------------------------------------------------- #
# Normalisation
# --------------------------------------------------------------------------- #
def _labels(value: Any, key: str, locales: list[str]) -> dict[str, str]:
    """A label given as string or {locale: text} → text for every locale."""
    if isinstance(value, str):
        out = {locales[0]: value}
    elif isinstance(value, dict):
        out = {str(k): str(v) for k, v in value.items() if v is not None}
    else:
        out = {}
    fallback = out.get(locales[0]) or next(iter(out.values()), None) or humanize(key)
    return {loc: out.get(loc, fallback) for loc in locales}


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    return list(value) if isinstance(value, (list, tuple)) else [value]


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    """Returns a fully expanded copy of the model. Never raises on bad input:
    shapes that cannot be normalised are left as they are for validate()."""
    m = copy.deepcopy(raw)
    app = m.setdefault("app", {}) or {}
    m["app"] = app
    locales = [str(x) for x in _as_list(app.get("locales"))] or ["it", "en"]
    app["locales"] = locales
    app.setdefault("name", humanize(str(app.get("slug", "app"))))
    app.setdefault("slug", re.sub(r"[^a-z0-9-]+", "-", str(app["name"]).lower()).strip("-") or "app")
    app.setdefault("description", "")
    app.setdefault("timezone", "Europe/Rome")
    auth = app.setdefault("auth", {}) or {}
    app["auth"] = auth
    auth["providers"] = _as_list(auth.get("providers")) or ["google"]
    auth["allowed_domains"] = [str(d).lower() for d in _as_list(auth.get("allowed_domains"))]
    auth.setdefault("approval", "manual")
    auth["admins"] = [str(a).lower() for a in _as_list(auth.get("admins"))]
    ev = app.setdefault("events", {}) or {}
    app["events"] = ev
    ev.setdefault("source", "/" + str(app["slug"]))
    ev.setdefault("type_prefix", "app." + str(app["slug"]).replace("-", "_") + ".")
    ev.setdefault("retention_days", 365)
    dep = app.setdefault("deploy", {}) or {}
    app["deploy"] = dep
    dep.setdefault("image", f"ghcr.io/OWNER/{app['slug']}")
    dep.setdefault("base_url", "http://localhost:3000")
    dep.setdefault("platforms", ["linux/amd64"])

    # Roles (admin is implicit and always first)
    roles_in = m.get("roles") or {}
    roles: dict[str, Any] = {}
    admin_in = roles_in.get("admin") if isinstance(roles_in, dict) else None
    admin_label = admin_in.get("label") if isinstance(admin_in, dict) else admin_in
    roles["admin"] = {
        "label": _labels(admin_label or {"it": "Amministratore", "en": "Administrator"}, "admin", locales),
        "scoped": False,
        "description": "Amministratore: può tutto",
    }
    if isinstance(roles_in, dict):
        for key, spec in roles_in.items():
            if key == "admin":
                continue
            spec = spec if isinstance(spec, dict) else {"label": spec}
            roles[key] = {
                "label": _labels(spec.get("label"), key, locales),
                "scoped": bool(spec.get("scoped", False)),
                "description": spec.get("description", ""),
            }
    m["roles"] = roles

    # Enums
    enums_in = m.get("enums") or {}
    enums: dict[str, Any] = {}
    if isinstance(enums_in, dict):
        for name, spec in enums_in.items():
            if isinstance(spec, list):
                spec = {"values": spec}
            spec = spec or {}
            values = []
            for v in _as_list(spec.get("values")):
                if isinstance(v, dict):
                    if "key" in v:
                        values.append({"key": str(v["key"]), "label": _labels(v.get("label"), str(v["key"]), locales)})
                    elif len(v) == 1:  # {hourly: {it: Orario}}
                        k, lab = next(iter(v.items()))
                        values.append({"key": str(k), "label": _labels(lab, str(k), locales)})
                else:
                    values.append({"key": str(v), "label": _labels((spec.get("labels") or {}).get(v), str(v), locales)})
            enums[name] = {"name": name, "type": snake(name), "label": _labels(spec.get("label"), name, locales), "values": values}
    m["enums"] = enums

    # Entities
    entities_in = m.get("entities") or {}
    entities: dict[str, Any] = {}
    if isinstance(entities_in, dict):
        for order, (name, spec) in enumerate(entities_in.items()):
            spec = spec or {}
            sn = snake(name)
            ent = {
                "name": name,
                "snake": sn,
                "table": spec.get("table") or pluralize(sn),
                "kind": spec.get("kind") or ("process" if spec.get("workflow") else "registry"),
                "label": _labels(spec.get("label"), name, locales),
                "plural": _labels(spec.get("plural"), pluralize(name) if not spec.get("plural") else name, locales),
                "code_prefix": spec.get("code_prefix"),
                "scope_field": spec.get("scope_field"),
                "icon": spec.get("icon", "file"),
                "menu": spec.get("menu", True),
                "order": spec.get("order", (order + 1) * 10),
                "description": spec.get("description", ""),
                "fields": {},
                "permissions": {},
                "workflow": None,
                "indexes": [list(_as_list(ix)) for ix in _as_list(spec.get("indexes"))],
                "ui_spec": spec.get("ui"),
            }
            if not spec.get("plural"):
                ent["plural"] = {loc: pluralize(lbl) if loc == "en" else lbl for loc, lbl in ent["label"].items()}
            for pos, (fkey, fspec) in enumerate((spec.get("fields") or {}).items()):
                if isinstance(fspec, str):
                    fspec = {"type": fspec}
                fspec = fspec or {}
                ftype = fspec.get("type", "string")
                fld = {
                    "key": fkey,
                    "type": ftype,
                    "label": _labels(fspec.get("label"), fkey, locales),
                    "required": bool(fspec.get("required", False)),
                    "unique": bool(fspec.get("unique", False)),
                    "list": bool(fspec.get("list", pos < 4)),
                    "default": fspec.get("default"),
                    "help": _labels(fspec.get("help"), "", locales) if fspec.get("help") else None,
                    "enum": fspec.get("enum"),
                    "to": fspec.get("to"),
                    "many": bool(fspec.get("many", False)),
                    "on_delete": fspec.get("on_delete"),
                    "min": fspec.get("min"),
                    "max": fspec.get("max"),
                    "max_length": fspec.get("max_length"),
                    "readonly": bool(fspec.get("readonly", False)),
                    "renamed_from": fspec.get("renamed_from"),
                    "order": pos,
                }
                if ftype == "ref" and not fld["on_delete"]:
                    fld["on_delete"] = "set_null" if not fld["required"] else "restrict"
                ent["fields"][fkey] = fld
            display = spec.get("display")
            if not display:
                if ent["kind"] == "process" and ent["code_prefix"]:
                    display = "code"
                else:
                    display = next((k for k, f in ent["fields"].items() if f["type"] in ("string", "email") and not f["many"]), "id")
            ent["display"] = display
            perms_in = spec.get("permissions") or {}
            defaults = {"read": ["all"], "create": ["admin"], "update": ["admin"], "delete": ["admin"]}
            for action in PERMISSION_ACTIONS:
                principals = [str(p) for p in _as_list(perms_in.get(action, defaults[action]))]
                if "admin" not in principals and "all" not in principals:
                    principals = ["admin"] + principals
                ent["permissions"][action] = principals
            wf = spec.get("workflow")
            if wf:
                ent["workflow"] = _normalize_workflow(wf, locales)
            entities[name] = ent
    m["entities"] = entities

    # Scope
    scope = m.get("scope")
    if isinstance(scope, str):
        scope = {"entity": scope}
    m["scope"] = scope or None

    # Custom events
    events_in = m.get("events") or {}
    events: dict[str, Any] = {}
    if isinstance(events_in, dict):
        for ename, spec in events_in.items():
            spec = spec if isinstance(spec, dict) else {"description": spec}
            entity = spec.get("entity")
            if not entity:
                prefix = str(ename).split(".")[0]
                entity = next((n for n, e in entities.items() if e["snake"] == prefix), None)
            events[ename] = {
                "type": ename,
                "entity": entity,
                "description": spec.get("description") or humanize(str(ename).split(".")[-1]),
                "category": spec.get("category", "domain"),
            }
    m["events"] = events

    # Reactions
    reactions = []
    for i, r in enumerate(_as_list(m.get("reactions"))):
        r = dict(r or {})
        if True in r:  # YAML 1.1 reads a bare `on:` key as the boolean true
            r["on"] = r.pop(True)
        r.setdefault("name", f"reaction_{i + 1}")
        r["to"] = [str(p) for p in _as_list(r.get("to"))]
        when = r.get("when")
        if isinstance(when, list):
            when = {"clauses": when}
        r["when"] = when or {}
        reactions.append(r)
    m["reactions"] = reactions

    subs = []
    for s in _as_list(m.get("subscriptions")):
        s = dict(s or {})
        s["events"] = [str(e) for e in _as_list(s.get("events"))] or ["*"]
        subs.append(s)
    m["subscriptions"] = subs
    m.setdefault("version", 1)
    from . import ui
    ui.apply_defaults(m)
    return m


def _normalize_workflow(wf: dict[str, Any], locales: list[str]) -> dict[str, Any]:
    states: dict[str, Any] = {}
    states_in = wf.get("states") or {}
    if isinstance(states_in, list):
        states_in = {str(s): {} for s in states_in}
    for i, (key, spec) in enumerate(states_in.items()):
        spec = spec or {}
        rem = spec.get("reminder")
        if isinstance(rem, int):
            rem = {"after_days": rem}
        states[key] = {
            "key": key,
            "label": _labels(spec.get("label"), key, locales),
            "kind": spec.get("kind", "initial" if i == 0 else "normal"),
            "owner": [str(p) for p in _as_list(spec.get("owner"))],
            "editable_by": [str(p) for p in _as_list(spec.get("editable_by"))],
            "color": spec.get("color") or STATE_COLORS[i % len(STATE_COLORS)],
            "renamed_from": spec.get("renamed_from"),
            "reminder": ({"after_days": int(rem.get("after_days", 7)), "template": rem.get("template") or f"{key}_reminder"}
                         if isinstance(rem, dict) else None),
            "order": i,
        }
    transitions: dict[str, Any] = {}
    for i, (key, spec) in enumerate((wf.get("transitions") or {}).items()):
        spec = spec or {}
        frm = spec.get("from", "*")
        frm_list = list(states.keys()) if frm == "*" else [str(s) for s in _as_list(frm)]
        if frm == "*":
            frm_list = [s for s in frm_list if states[s]["kind"] != "final" and s != spec.get("to")]
        trig = spec.get("trigger", "manual")
        if isinstance(trig, dict):
            trig = {"kind": "timed", "at": trig.get("at"), "offset": trig.get("offset", "")}
        else:
            trig = {"kind": "manual"}
        comment = spec.get("comment", "optional")
        if comment is True:
            comment = "required"
        transitions[key] = {
            "key": key,
            "label": _labels(spec.get("label"), key, locales),
            "from": frm_list,
            "to": spec.get("to"),
            "by": [str(p) for p in _as_list(spec.get("by"))],
            "trigger": trig,
            "comment": comment,
            "guard": _as_list(spec.get("guard")),
            "condition": _as_list(spec.get("condition")),
            "emits": [str(e) for e in _as_list(spec.get("emits"))],
            "order": i,
        }
    return {"states": states, "transitions": transitions}


# --------------------------------------------------------------------------- #
# Derived information used by validators and generators
# --------------------------------------------------------------------------- #
def auto_events(m: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Events every entity emits automatically, keyed by type."""
    out: dict[str, dict[str, Any]] = {}
    for name, e in m["entities"].items():
        for suffix in AUTO_EVENTS_ALL:
            out[f"{e['snake']}.{suffix}"] = {"type": f"{e['snake']}.{suffix}", "entity": name, "category": "domain",
                                             "description": {"created": f"Nuovo record {name}",
                                                             "updated": f"{name} modificato (data.changed elenca i campi)",
                                                             "deleted": f"{name} eliminato"}[suffix]}
        if e["kind"] == "process":
            for suffix in AUTO_EVENTS_PROCESS:
                out[f"{e['snake']}.{suffix}"] = {"type": f"{e['snake']}.{suffix}", "entity": name, "category": "workflow",
                                                 "description": {"transitioned": f"Cambio di stato di {name} (transition, actor, comment, recipients)",
                                                                 "completed": f"{name} ha raggiunto uno stato finale",
                                                                 "reminder": f"Sollecito: {name} fermo in uno stato con sollecito"}[suffix]}
    return out


def all_events(m: dict[str, Any]) -> dict[str, dict[str, Any]]:
    out = auto_events(m)
    out.update(m["events"])
    out["user.approval_requested"] = {"type": "user.approval_requested", "entity": None, "category": "system",
                                      "description": "Primo accesso di un utente non pre-registrato"}
    out["user.approved"] = {"type": "user.approved", "entity": None, "category": "system", "description": "Utente abilitato"}
    out["user.role_assigned"] = {"type": "user.role_assigned", "entity": None, "category": "system", "description": "Ruolo assegnato"}
    out["user.role_revoked"] = {"type": "user.role_revoked", "entity": None, "category": "system", "description": "Ruolo revocato"}
    out["webhook.test"] = {"type": "webhook.test", "entity": None, "category": "system", "description": "Evento di prova"}
    return out


def entity_by_snake(m: dict[str, Any], sn: str) -> dict[str, Any] | None:
    return next((e for e in m["entities"].values() if e["snake"] == sn), None)


def event_entity(m: dict[str, Any], etype: str) -> dict[str, Any] | None:
    ev = all_events(m).get(etype)
    if ev and ev.get("entity"):
        return m["entities"].get(ev["entity"])
    return None


def scope_entity(m: dict[str, Any]) -> dict[str, Any] | None:
    sc = m.get("scope")
    return m["entities"].get(sc["entity"]) if sc and sc.get("entity") else None


def ref_target_table(m: dict[str, Any], to: str) -> str:
    return "profiles" if to == "User" else m["entities"][to]["table"]


def email_field(m: dict[str, Any], entity: str) -> str | None:
    if entity == "User":
        return "email"
    e = m["entities"].get(entity)
    if not e:
        return None
    return next((k for k, f in e["fields"].items() if f["type"] == "email" and not f["many"]), None)


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate(m: dict[str, Any]) -> Report:
    rep = Report()
    app = m["app"]
    if not SLUG.match(str(app.get("slug", ""))):
        rep.error("app.slug", f"'{app.get('slug')}' must be kebab-case (a-z, 0-9, -)")
    if app["auth"]["approval"] not in ("manual", "auto"):
        rep.error("app.auth.approval", "must be 'manual' or 'auto'")
    for p in app["auth"]["providers"]:
        if p not in ("google", "email"):
            rep.error("app.auth.providers", f"unknown provider '{p}' (google | email)")
    if not app["auth"]["allowed_domains"]:
        rep.warn("app.auth.allowed_domains", "empty: every email domain will be able to sign up")
    if not app["auth"]["admins"]:
        rep.warn("app.auth.admins", "no bootstrap admin: the first administrator must be created by hand in SQL")
    for loc in app["locales"]:
        if not re.match(r"^[a-z]{2}$", loc):
            rep.error("app.locales", f"'{loc}' is not a two-letter language code")

    for key, role in m["roles"].items():
        if not IDENT.match(key):
            rep.error(f"roles.{key}", "role keys must be snake_case identifiers")
    scope = m.get("scope")
    sc_ent = None
    if scope:
        sc_ent = m["entities"].get(scope.get("entity"))
        if not sc_ent:
            rep.error("scope.entity", f"unknown entity '{scope.get('entity')}'")
        elif sc_ent["kind"] != "registry":
            rep.error("scope.entity", "the scope entity must be a registry (no workflow)")
    if any(r["scoped"] for r in m["roles"].values()) and not sc_ent:
        rep.error("roles", "scoped roles require a 'scope' entity")

    for name, en in m["enums"].items():
        if not ENUM_NAME.match(name):
            rep.error(f"enums.{name}", "enum names must be PascalCase")
        keys = [v["key"] for v in en["values"]]
        if not keys:
            rep.error(f"enums.{name}", "an enum needs at least one value")
        if len(set(keys)) != len(keys):
            rep.error(f"enums.{name}", "duplicate values")
        for k in keys:
            if not re.match(r"^[a-z][a-z0-9_]*$", k):
                rep.error(f"enums.{name}", f"value '{k}' must be snake_case")
        if name in m["entities"]:
            rep.error(f"enums.{name}", "an entity has the same name")

    tables = {}
    for name, e in m["entities"].items():
        where = f"entities.{name}"
        if not ENTITY_NAME.match(name):
            rep.error(where, "entity names must be PascalCase (e.g. Invitation)")
        if name == "User":
            rep.error(where, "'User' is built in (the application users): reference it with `to: User`")
        if e["table"] in tables or e["table"] in CORE_TABLES:
            rep.error(where, f"table name '{e['table']}' clashes with {tables.get(e['table'], 'a core table')}")
        tables[e["table"]] = name
        if e["kind"] not in ("registry", "process"):
            rep.error(where, "kind must be 'registry' or 'process'")
        if e["kind"] == "process" and not e["workflow"]:
            rep.error(where, "a process entity needs a workflow")
        if e["kind"] == "registry" and e["workflow"]:
            rep.error(where, "a registry cannot have a workflow (use kind: process)")
        if e["code_prefix"] and not CODE_PREFIX.match(str(e["code_prefix"])):
            rep.error(where, "code_prefix must be 2-6 upper-case letters")
        if not e["fields"]:
            rep.warn(where, "no fields")
        if e["display"] not in e["fields"] and e["display"] not in ("code", "id"):
            rep.error(where, f"display field '{e['display']}' does not exist")
        _validate_fields(m, name, e, rep)
        if e["scope_field"]:
            f = e["fields"].get(e["scope_field"])
            if not f:
                rep.error(where, f"scope_field '{e['scope_field']}' does not exist")
            elif not sc_ent or f["type"] != "ref" or f["to"] != sc_ent["name"] or f["many"]:
                rep.error(where, f"scope_field '{e['scope_field']}' must be a single reference to the scope entity")
        for action, principals in e["permissions"].items():
            for p in principals:
                _check_principal(m, e, p, f"{where}.permissions.{action}", rep, for_notify=False)
        for ix in e["indexes"]:
            for col in ix:
                if col not in e["fields"] and col not in ("code", "state", "created_at", "created_by"):
                    rep.error(f"{where}.indexes", f"unknown field '{col}'")
        if e["workflow"]:
            _validate_workflow(m, e, rep)

    events = all_events(m)
    for ename, ev in m["events"].items():
        where = f"events.{ename}"
        if not EVENT_NAME.match(ename):
            rep.error(where, "event names are '<entity>.<name>' in snake_case (e.g. invitation.visit_ended)")
        if ename in auto_events(m):
            rep.error(where, "this event is emitted automatically: do not declare it")
        if ev["entity"] and ev["entity"] not in m["entities"]:
            rep.error(where, f"unknown entity '{ev['entity']}'")
        if not ev["entity"]:
            rep.error(where, "cannot infer the entity: add `entity: <Entity>`")
        elif m["entities"].get(ev["entity"]) and not ename.startswith(m["entities"][ev["entity"]]["snake"] + "."):
            rep.warn(where, f"name does not start with '{m['entities'][ev['entity']]['snake']}.'")

    names = set()
    for r in m["reactions"]:
        _validate_reaction(m, r, events, rep)
        if r["name"] in names:
            rep.error(f"reactions.{r['name']}", "duplicate reaction name")
        names.add(r["name"])

    for s in m["subscriptions"]:
        where = f"subscriptions.{s.get('name', '?')}"
        if not s.get("name"):
            rep.error(where, "a subscription needs a name")
        if not s.get("url") and not s.get("url_env"):
            rep.error(where, "a subscription needs `url` or `url_env`")
        for pat in s["events"]:
            if pat != "*" and not any(_glob(pat, t) for t in events):
                rep.warn(where, f"pattern '{pat}' matches no event")

    for cycle in reaction_cycles(m):
        rep.error("reactions", "cycle between reactions: " + " → ".join(cycle))
    from . import ui
    ui.validate(m, rep)
    return rep


CORE_TABLES = {
    "app_settings", "profiles", "user_roles", "event_types", "events", "webhook_endpoints", "webhook_deliveries",
    "scheduled_events", "code_counters", "reminders_sent", "record_history", "model_change_requests",
}


def _glob(pattern: str, value: str) -> bool:
    return re.fullmatch(re.escape(pattern).replace(r"\*", ".*"), value) is not None


def _validate_fields(m: dict[str, Any], name: str, e: dict[str, Any], rep: Report) -> None:
    for key, f in e["fields"].items():
        where = f"entities.{name}.fields.{key}"
        if not IDENT.match(key):
            rep.error(where, "field keys must be snake_case")
        if key in RESERVED_FIELDS or (key == "code" and e["code_prefix"]):
            rep.error(where, f"'{key}' is reserved (standard column)")
        if f["type"] not in FIELD_TYPES:
            rep.error(where, f"unknown type '{f['type']}' ({', '.join(sorted(FIELD_TYPES))})")
            continue
        if f["type"] == "enum":
            if f["enum"] not in m["enums"]:
                rep.error(where, f"unknown enum '{f['enum']}'")
            elif f["default"] is not None and f["default"] not in [v["key"] for v in m["enums"][f["enum"]]["values"]]:
                rep.error(where, f"default '{f['default']}' is not a value of {f['enum']}")
        elif f["enum"]:
            rep.warn(where, "`enum` is ignored when type is not enum")
        if f["type"] == "ref":
            if f["to"] != "User" and f["to"] not in m["entities"]:
                rep.error(where, f"unknown reference target '{f['to']}' (an entity or User)")
            if f["on_delete"] not in ("cascade", "restrict", "set_null"):
                rep.error(where, "on_delete must be cascade | restrict | set_null")
            if f["on_delete"] == "set_null" and f["required"]:
                rep.error(where, "a required reference cannot use on_delete: set_null")
            if f["many"] and f["unique"]:
                rep.error(where, "a many-reference cannot be unique")
        elif f["many"]:
            rep.error(where, "`many` is only valid for references")
        if f["unique"] and f["type"] in ("json", "text"):
            rep.warn(where, "unique on a long text/json column")
        if f["min"] is not None and f["type"] not in ("int", "number", "money"):
            rep.error(where, "`min` only applies to numbers")


def _check_principal(m: dict[str, Any], e: dict[str, Any] | None, p: str, where: str, rep: Report, for_notify: bool) -> None:
    if p in ("all", "creator") or p in m["roles"]:
        if p == "all" and for_notify:
            rep.error(where, "'all' cannot be notified")
        return
    if p.startswith("email:"):
        if not for_notify:
            rep.error(where, "email: principals are only valid as notification recipients")
        elif "@" not in p:
            rep.error(where, f"invalid email in '{p}'")
        return
    if p.startswith("field:"):
        fk = p.split(":", 1)[1]
        f = (e or {}).get("fields", {}).get(fk) if e else None
        if not f or f["type"] != "ref":
            rep.error(where, f"'{p}': field '{fk}' is not a reference of {e['name'] if e else '?'}")
            return
        if f["to"] != "User":
            if not for_notify:
                rep.error(where, f"'{p}': permissions can only use references to User")
            elif not email_field(m, f["to"]):
                rep.error(where, f"'{p}': {f['to']} has no email field to notify")
        return
    rep.error(where, f"unknown principal '{p}' (all, creator, <role>, field:<ref>, email:<address>)")


def _validate_clause(m: dict[str, Any], e: dict[str, Any], clause: Any, where: str, rep: Report) -> None:
    if not isinstance(clause, dict) or "field" not in clause or "op" not in clause:
        rep.error(where, "a clause is {field, op, value}")
        return
    fk, op = clause["field"], clause["op"]
    f = e["fields"].get(fk)
    if not f and fk not in ("state", "code", "created_by"):
        rep.error(where, f"unknown field '{fk}'")
        return
    if op not in CLAUSE_OPS:
        rep.error(where, f"unknown operator '{op}' ({', '.join(sorted(CLAUSE_OPS))})")
        return
    if op in UNARY_OPS:
        if "value" in clause:
            rep.warn(where, f"'{op}' takes no value")
        if op in ("is_true", "is_false") and f and f["type"] != "bool":
            rep.error(where, f"'{op}' needs a boolean field")
        return
    if "value" not in clause:
        rep.error(where, f"'{op}' needs a value")
        return
    if op in ("in", "not_in") and not isinstance(clause["value"], list):
        rep.error(where, f"'{op}' needs a list value")
    if op in ("gt", "gte", "lt", "lte") and f and f["type"] not in ("int", "number", "money", "date", "datetime"):
        rep.error(where, f"'{op}' needs a numeric or date field")
    if f and f.get("many"):
        rep.error(where, "clauses cannot test many-references")
    if f and f["type"] == "enum" and f["enum"] in m["enums"]:
        allowed = {v["key"] for v in m["enums"][f["enum"]]["values"]}
        vals = clause["value"] if isinstance(clause["value"], list) else [clause["value"]]
        for v in vals:
            if v not in allowed:
                rep.error(where, f"'{v}' is not a value of {f['enum']}")


def _validate_workflow(m: dict[str, Any], e: dict[str, Any], rep: Report) -> None:
    wf = e["workflow"]
    where = f"entities.{e['name']}.workflow"
    states, transitions = wf["states"], wf["transitions"]
    if not states:
        rep.error(where, "no states")
        return
    initials = [k for k, s in states.items() if s["kind"] == "initial"]
    if len(initials) != 1:
        rep.error(where, f"exactly one initial state is required (found {len(initials)})")
    if not any(s["kind"] == "final" for s in states.values()):
        rep.warn(where, "no final state: records never complete")
    for k, s in states.items():
        if not IDENT.match(k):
            rep.error(f"{where}.states.{k}", "state keys must be snake_case")
        if s["kind"] not in STATE_KINDS:
            rep.error(f"{where}.states.{k}", "kind must be initial | normal | final")
        for p in s["owner"] + s["editable_by"]:
            _check_principal(m, e, p, f"{where}.states.{k}", rep, for_notify=False)
        if s["reminder"] and not s["owner"]:
            rep.error(f"{where}.states.{k}", "a reminder needs an owner to notify")
        if s["reminder"] and s["kind"] == "final":
            rep.warn(f"{where}.states.{k}", "reminder on a final state")
    for k, t in transitions.items():
        tw = f"{where}.transitions.{k}"
        if not IDENT.match(k):
            rep.error(tw, "transition keys must be snake_case")
        if t["to"] not in states:
            rep.error(tw, f"unknown target state '{t['to']}'")
        if not t["from"]:
            rep.error(tw, "no source state")
        for s in t["from"]:
            if s not in states:
                rep.error(tw, f"unknown source state '{s}'")
            elif states[s]["kind"] == "final":
                rep.warn(tw, f"leaves the final state '{s}'")
        if t["trigger"]["kind"] == "manual":
            if not t["by"]:
                rep.error(tw, "a manual transition needs `by` (who can fire it)")
            for p in t["by"]:
                _check_principal(m, e, p, tw, rep, for_notify=False)
        else:
            parsed = parse_offset(f"{t['trigger']['at']} {t['trigger'].get('offset') or ''}".strip())
            fld = e["fields"].get(t["trigger"]["at"])
            if not fld or fld["type"] not in ("date", "datetime"):
                rep.error(tw, f"timed trigger: '{t['trigger']['at']}' must be a date/datetime field")
            if parsed is None:
                rep.error(tw, "timed trigger: offset must look like '+1d', '-3d', '+2h'")
            if t["by"]:
                rep.warn(tw, "`by` is ignored on timed transitions (run by the system)")
        if t["comment"] not in ("optional", "required", "none"):
            rep.error(tw, "comment must be optional | required | none")
        for c in t["guard"]:
            _validate_clause(m, e, c, f"{tw}.guard", rep)
        for c in t["condition"]:
            _validate_clause(m, e, c, f"{tw}.condition", rep)
        for ev in t["emits"]:
            if ev not in m["events"]:
                rep.error(tw, f"emits undeclared event '{ev}' (declare it under events:)")
    # keys unique per (from, key) is implied by dict; reachability:
    initial = initials[0] if initials else None
    if initial:
        seen, todo = {initial}, [initial]
        while todo:
            cur = todo.pop()
            for t in transitions.values():
                if cur in t["from"] and t["to"] in states and t["to"] not in seen:
                    seen.add(t["to"])
                    todo.append(t["to"])
        for k in states:
            if k not in seen:
                rep.error(f"{where}.states.{k}", "unreachable from the initial state")
    for k, s in states.items():
        if s["kind"] != "final" and not any(k in t["from"] for t in transitions.values()):
            rep.warn(f"{where}.states.{k}", "dead end: no outgoing transition and not final")


def _validate_reaction(m: dict[str, Any], r: dict[str, Any], events: dict[str, Any], rep: Report) -> None:
    where = f"reactions.{r['name']}"
    if not IDENT.match(str(r["name"])):
        rep.error(where, "reaction names must be snake_case")
    on = r.get("on")
    if on not in events:
        rep.error(where, f"unknown event '{on}'")
        return
    kind = r.get("do")
    if kind not in REACTION_KINDS:
        rep.error(where, f"`do` must be one of {', '.join(sorted(REACTION_KINDS))}")
        return
    ent = event_entity(m, on)
    if kind != "notify" and kind != "broadcast" and kind != "custom" and not ent:
        rep.error(where, f"'{kind}' needs an event about an entity")
        return
    when = r["when"]
    for k in when:
        if k not in ("transition", "to", "from", "clauses"):
            rep.error(where, f"unknown `when` key '{k}' (transition, to, from, clauses)")
    if ("transition" in when or "to" in when or "from" in when):
        if not ent or not ent["workflow"] or not on.endswith((".transitioned", ".completed", ".reminder")):
            rep.error(where, "`when.transition/to/from` only apply to workflow events")
        else:
            wf = ent["workflow"]
            for t in _as_list(when.get("transition")):
                if t not in wf["transitions"]:
                    rep.error(where, f"unknown transition '{t}'")
            for s in _as_list(when.get("to")) + _as_list(when.get("from")):
                if s not in wf["states"]:
                    rep.error(where, f"unknown state '{s}'")
    for c in _as_list(when.get("clauses")):
        if ent:
            _validate_clause(m, ent, c, f"{where}.when", rep)
        else:
            rep.error(where, "`when.clauses` need an event about an entity")
    if kind == "notify":
        if not r["to"]:
            rep.error(where, "notify needs `to` (recipients)")
        if not r.get("template"):
            rep.error(where, "notify needs `template` (the template key used by the sender)")
        for p in r["to"]:
            if p in m["roles"] or p.startswith("email:") or p in ("creator",):
                _check_principal(m, ent, p, where, rep, for_notify=True)
            elif ent:
                _check_principal(m, ent, p, where, rep, for_notify=True)
            else:
                rep.error(where, f"'{p}' needs an event about an entity")
    elif kind == "set":
        values = r.get("set")
        if not isinstance(values, dict) or not values:
            rep.error(where, "set needs `set: {field: value}`")
        else:
            for fk, val in values.items():
                f = ent["fields"].get(fk)
                if not f:
                    rep.error(where, f"unknown field '{fk}'")
                elif f["many"] or f["type"] == "json":
                    rep.error(where, f"cannot set '{fk}' ({f['type']})")
                elif isinstance(val, str) and val.startswith("="):
                    if val not in ("=now", "=today", "=actor", "=null"):
                        rep.error(where, f"unknown expression '{val}' (=now, =today, =actor, =null)")
    elif kind == "transition":
        t = r.get("transition")
        if not ent["workflow"] or t not in ent["workflow"]["transitions"]:
            rep.error(where, f"unknown transition '{t}' of {ent['name']}")
    elif kind == "schedule":
        ev = r.get("event")
        if ev not in m["events"]:
            rep.error(where, f"schedule needs a declared custom event (got '{ev}')")
        elif m["events"][ev]["entity"] != ent["name"]:
            rep.error(where, f"scheduled event '{ev}' must be about {ent['name']}")
        parsed = parse_offset(str(r.get("at", "")))
        if not parsed:
            rep.error(where, "schedule needs `at: <date field> [+/-N(d|h|m)]`")
        else:
            f = ent["fields"].get(parsed[0])
            if parsed[0] not in ("created_at", "updated_at") and (not f or f["type"] not in ("date", "datetime")):
                rep.error(where, f"'{parsed[0]}' is not a date/datetime field")
    elif kind == "broadcast":
        if not re.match(r"^[a-z][a-z0-9_:-]*$", str(r.get("channel", ""))):
            rep.error(where, "broadcast needs `channel` (lower-case name)")
    elif kind == "custom":
        if not IDENT.match(str(r.get("handler", ""))):
            rep.error(where, "custom needs `handler: <snake_case name>`")


def reaction_emits(m: dict[str, Any], r: dict[str, Any]) -> list[str]:
    """Events a reaction can emit synchronously (within the same transaction)."""
    ent = event_entity(m, r.get("on", ""))
    if not ent:
        return []
    if r.get("do") == "set":
        return [f"{ent['snake']}.updated"]
    if r.get("do") == "transition" and ent["workflow"]:
        t = ent["workflow"]["transitions"].get(r.get("transition"))
        if not t:
            return []
        out = [f"{ent['snake']}.transitioned"] + t["emits"]
        if ent["workflow"]["states"].get(t["to"], {}).get("kind") == "final":
            out.append(f"{ent['snake']}.completed")
        return out
    return []


def reaction_cycles(m: dict[str, Any]) -> list[list[str]]:
    graph: dict[str, set[str]] = {}
    for r in m["reactions"]:
        if r.get("on"):
            graph.setdefault(r["on"], set()).update(reaction_emits(m, r))
    cycles, state = [], {}

    def visit(node: str, path: list[str]) -> None:
        state[node] = 1
        for nxt in graph.get(node, ()):
            if state.get(nxt) == 1:
                cycles.append(path[path.index(nxt):] + [nxt] if nxt in path else [node, nxt])
            elif not state.get(nxt):
                visit(nxt, path + [nxt])
        state[node] = 2

    for n in list(graph):
        if not state.get(n):
            visit(n, [n])
    return cycles


def load_and_validate(path: str | Path) -> tuple[dict[str, Any], Report]:
    meta = metamodel_beside(path)
    if meta is None:
        raw = load(path)
        m = normalize(raw)
        return m, validate(m)
    from . import ecore
    mm = ecore.load(meta)
    rep = ecore.validate(mm)
    rep.errors = [f"domain.ecore.yaml {x}" for x in rep.errors]
    rep.warnings = [f"domain.ecore.yaml {x}" for x in rep.warnings]
    try:
        raw = ecore.compose(mm, load_file(path), rep)
    except Exception as exc:  # a broken metamodel can have shapes compose cannot read
        if rep.ok:
            raise
        rep.error("domain.ecore.yaml", f"cannot be composed until the errors above are fixed ({exc})")
        return normalize({"app": load_file(path).get("app") or {}}), rep
    m = normalize(raw)
    rep2 = validate(m)
    rep.errors += rep2.errors
    rep.warnings += rep2.warnings
    return m, rep
