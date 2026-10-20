"""The behaviour model (`behavior.yaml`), read and checked against the domain metamodel (`domain.ecore.yaml`).

Where the metamodel says *what* the domain is, the behaviour model says what happens: roles, derivations of
the attributes marked `derived` in the metamodel, workflows (states, transitions, guards, timed transitions),
domain events, reactions (who is notified when) and webhook subscriptions. Every name in it is a concept of
the metamodel: classes, attributes and references are navigated with typed paths (`expr.py`), so a change of
the domain that breaks the behaviour is reported by `validate()`.

    roles:        {office: {label}, director: {scope: Department}}
    derivations:  {Invitation: {dataComplete: "reason.isSet() and fundsTotal = totalAmount"}}
    workflows:    {Invitation: {state: state, states: {...}, transitions: {...}, revert: {...}}}
    events:       {Invitation: {visit_ended: {doc}}}
    reactions:    [{name, event: Invitation.transitioned, when: "transition = submit", notify: [director], template}]
    subscriptions: [{name: n8n, url_env: N8N_WEBHOOK_URL, events: [Invitation.*]}]

Principals (`by`, `owner`, `editable_by`, `notify`, `revert.by`): `admin`, `creator`, a role (`director`, or
`director@department` when the class has several references to the role's scope class), or a navigation
written with `self.` (`self.issuer`: a User; in `notify` also an Email attribute, `self.guest.email`).
"""

from __future__ import annotations

import copy
import re
from pathlib import Path
from typing import Any

from . import core as M
from . import ecore as E
from . import expr as X

BEHAVIOR_FILE = E.BEHAVIOR_FILE
TOP_KEYS = {"metamodel", "doc", "roles", "derivations", "workflows", "events", "reactions", "subscriptions"}
ROLE_KEYS = {"label", "scope", "doc"}
WORKFLOW_KEYS = {"state", "states", "transitions", "revert", "doc"}
STATE_KEYS = {"initial", "final", "label", "doc", "owner", "editable_by", "reminder", "color"}
TRANSITION_KEYS = {"from", "to", "by", "when", "guard", "comment", "at", "emits", "label", "doc"}
REVERT_KEYS = {"by", "final_by", "comment"}
REMINDER_KEYS = {"after", "template"}
EVENT_KEYS = {"doc", "label"}
REACTION_KEYS = {"name", "event", "when", "notify", "template", "doc"}   # not `on`: a boolean in YAML 1.1
SUBSCRIPTION_KEYS = {"name", "url_env", "url", "events", "doc"}
LIFECYCLE_EVENTS = ("created", "updated", "deleted")
WORKFLOW_EVENTS = ("transitioned", "completed", "reverted", "reminder")
SYSTEM_EVENTS = ("user.*", "webhook.test")          # emitted by the application core, not by a class
BUILTIN_PRINCIPALS = {"admin", "creator"}
COMMENT = ("required", "optional")

IDENT = re.compile(r"^[a-z][a-z0-9_]*$")
DURATION = re.compile(r"^\+?(\d+)([dhw])$")
AT = re.compile(r"^(?P<path>[A-Za-z_][A-Za-z0-9_.]*)\s*(?:(?P<sign>[+-])\s*(?P<n>\d+)(?P<unit>[dhw]))?$")
ROLE_AT = re.compile(r"^(?P<role>[a-z][a-z0-9_]*)(?:@(?P<path>[A-Za-z_][A-Za-z0-9_.]*))?$")
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


# --------------------------------------------------------------------------- #
# Loading and canonical form
# --------------------------------------------------------------------------- #
def load(path: str | Path) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        raise M.ModelError(f"{p} not found")
    return loads(p.read_text(encoding="utf-8"))


def loads(text: str) -> dict[str, Any]:
    return M.loads(text)


class _Flow(dict):
    """A mapping written on one line (flow style) by dumps()."""


def _dumper():
    yaml, Dumper = E._flow_dumper()
    Dumper.add_representer(_Flow, lambda d, data: d.represent_mapping("tag:yaml.org,2002:map", data.items(), flow_style=True))
    return yaml, Dumper


def _expr_text(x: Any) -> str:
    """An expression as one line: its canonical text when it parses, else its words joined by one space."""
    try:
        return X.to_text(X.parse(str(x)))
    except X.ExprError:
        return " ".join(str(x).split())


def _tidy(raw: dict[str, Any]) -> dict[str, Any]:
    """Expressions on one line (a folded `>` text keeps its newlines when loaded) before writing the file."""
    r = copy.deepcopy(raw)
    for cn, ders in _mapping(r.get("derivations")).items():
        r["derivations"][cn] = {an: " ".join(str(x).split()) for an, x in _mapping(ders).items()}
    for w in _mapping(r.get("workflows")).values():
        for t in _mapping(_mapping(w).get("transitions")).values():
            for k in ("when", "guard"):
                if isinstance(_mapping(t).get(k), str):
                    t[k] = " ".join(t[k].split())
    for rx in _list(r.get("reactions")):
        if isinstance(_mapping(rx).get("when"), str):
            rx["when"] = " ".join(rx["when"].split())
    return r


def _clean(v: Any) -> Any:
    """Drops what the notation leaves implicit: None, empty strings and lists, false flags. An empty mapping
    stays: `boss: {}` declares a role, `expired: {}` an event."""
    if isinstance(v, dict):
        out = {}
        for k, x in v.items():
            if k in ("initial", "final") and x is False:
                continue
            c = _clean(x)
            if c is None or c == "" or c == []:
                continue
            out[k] = c
        return out
    if isinstance(v, list):
        return [_clean(x) for x in v if x is not None and x != ""]
    return v


def from_editor(doc: dict[str, Any]) -> dict[str, Any]:
    """A behaviour proposal saved by the web modeler, back to the structure of behavior.yaml: typed expressions
    ({text, type, ast, sql}) become their text, the runtime keys (entities, uses) go, implicit values are dropped,
    a `from` of one state is written as that state."""
    def text(x: Any) -> Any:
        return x["text"] if isinstance(x, dict) and "text" in x and ("type" in x or "ast" in x) else x

    raw: dict[str, Any] = {}
    for key in ("metamodel", "doc"):
        if doc.get(key):
            raw[key] = doc[key]
    raw["roles"] = {rn: {k: v for k, v in (r or {}).items()} for rn, r in _mapping(doc.get("roles")).items()}
    raw["derivations"] = {cn: {an: text(ex) for an, ex in _mapping(ders).items()} for cn, ders in _mapping(doc.get("derivations")).items()}
    raw["workflows"] = {}
    for cn, w in _mapping(doc.get("workflows")).items():
        w = _mapping(w)
        states = {sn: {k: v for k, v in _mapping(st).items()} for sn, st in _mapping(w.get("states")).items()}
        transitions = {}
        for tn, t in _mapping(w.get("transitions")).items():
            t = {k: (text(v) if k in ("when", "guard") else v) for k, v in _mapping(t).items()}
            if isinstance(t.get("from"), list) and len(t["from"]) == 1:
                t["from"] = t["from"][0]
            transitions[tn] = t
        raw["workflows"][cn] = {**{k: v for k, v in w.items() if k not in ("states", "transitions")}, "states": states, "transitions": transitions}
    raw["events"] = {cn: {en: (ev or {}) for en, ev in _mapping(evs).items()} for cn, evs in _mapping(doc.get("events")).items()}
    raw["reactions"] = [{k: (text(v) if k == "when" else v) for k, v in _mapping(r).items()} for r in _list(doc.get("reactions"))]
    raw["subscriptions"] = [dict(_mapping(sub)) for sub in _list(doc.get("subscriptions"))]
    return _clean(raw)


def dumps(raw: dict[str, Any]) -> str:
    """behavior.yaml from its structure: one section per key, one block per class, states, transitions,
    reactions and subscriptions one per line (flow style), as the notation reference writes them.
    Comments are not kept: callers back the file up and say so."""
    yaml, Dumper = _dumper()
    dump = lambda v: yaml.dump(v, Dumper=Dumper, sort_keys=False, allow_unicode=True, width=200).rstrip("\n")  # noqa: E731
    block = E._Block                                                     # a mapping written one key per line
    flow_map = lambda m: block({k: (_Flow(v) if isinstance(v, dict) else v) for k, v in m.items()})  # noqa: E731
    r = _clean(_tidy(raw))
    out = ["# Behaviour of the domain (behavior.yaml): roles, derivations, workflows, events, reactions.",
           "# Edit it from the prompt (/modeler:metamodel), in the app's modeler (/admin/model) or by hand; `npm run",
           "# model:validate` checks it against domain.ecore.yaml.", ""]
    for key in ("metamodel", "doc"):
        if r.get(key):   # a scalar: never a flow mapping at the top level (it would end the document)
            scalar = yaml.safe_dump(r[key], allow_unicode=True, width=1000).strip()
            out.append(f"{key}: {scalar.split(chr(10))[0] if scalar.endswith('...') else scalar}")
    if r.get("roles"):
        out += ["", dump(block({"roles": flow_map(r["roles"])}))]
    if r.get("derivations"):
        out += ["", "derivations:"]
        for cn, ders in r["derivations"].items():
            out += ["  " + line for line in dump(block({cn: block(ders)})).split("\n")]
    if r.get("workflows"):
        out += ["", "workflows:"]
        for cn, w in r["workflows"].items():
            body = block({k: v for k, v in w.items() if k not in ("states", "transitions", "revert")})
            body["states"] = flow_map(w.get("states", {}))
            body["transitions"] = flow_map(w.get("transitions", {}))
            if w.get("revert"):
                body["revert"] = _Flow(w["revert"])
            out += ["  " + line for line in dump(block({cn: body})).split("\n")]
    if r.get("events"):
        out += ["", "events:"]
        for cn, evs in r["events"].items():
            out += ["  " + line for line in dump(block({cn: flow_map(evs)})).split("\n")]
    for key in ("reactions", "subscriptions"):
        if r.get(key):
            out += ["", f"{key}:"] + ["  - " + dump(_Flow(item)) for item in r[key]]
    return "\n".join(out).rstrip("\n") + "\n"


def dump(raw: dict[str, Any], path: str | Path) -> None:
    Path(path).write_text(dumps(raw), encoding="utf-8")


def diff(old: dict[str, Any], new: dict[str, Any]) -> list[str]:
    """Human-readable changes between two behaviour models (for reviews and proposals), on the canonical form."""
    a, b = expand(old), expand(new)
    out: list[str] = []
    EXPR = ("when", "guard", "at")

    def same(x: Any, y: Any, key: str | None = None) -> bool:
        if key in EXPR and isinstance(x, str) and isinstance(y, str):
            return _expr_text(x) == _expr_text(y)          # the same expression written differently
        return json_text({"v": x}) == json_text({"v": y})

    def changed_keys(x: dict[str, Any], y: dict[str, Any], keys: tuple[str, ...]) -> list[str]:
        return [k for k in keys if not same(x.get(k), y.get(k), k)]

    for rn in b["roles"]:
        if rn not in a["roles"]:
            out.append(f"+ role {rn}" + (f" (per {b['roles'][rn]['scope']})" if b["roles"][rn].get("scope") else ""))
        elif changed_keys(a["roles"][rn], b["roles"][rn], ("scope", "label")):
            out.append(f"~ role {rn}: {', '.join(changed_keys(a['roles'][rn], b['roles'][rn], ('scope', 'label')))}")
    out += [f"- role {rn}" for rn in a["roles"] if rn not in b["roles"]]
    for cn in b["derivations"]:
        for an, ex in b["derivations"][cn].items():
            old_ex = a["derivations"].get(cn, {}).get(an)
            if old_ex is None:
                out.append(f"+ derivation {cn}.{an} = {_expr_text(ex)}")
            elif _expr_text(old_ex) != _expr_text(ex):
                out.append(f"~ derivation {cn}.{an} = {_expr_text(ex)}")
    for cn in a["derivations"]:
        out += [f"- derivation {cn}.{an}" for an in a["derivations"][cn] if an not in b["derivations"].get(cn, {})]
    for cn, w in b["workflows"].items():
        ow = a["workflows"].get(cn)
        if ow is None:
            out.append(f"+ workflow {cn} on {w['state']}: {len(w['states'])} states, {len(w['transitions'])} transitions")
            continue
        if ow["state"] != w["state"]:
            out.append(f"~ workflow {cn}: state attribute {ow['state']} -> {w['state']}")
        for sn, st in w["states"].items():
            if sn not in ow["states"]:
                out.append(f"+ state {cn}.{sn}")
            else:
                ks = changed_keys(ow["states"][sn], st, ("initial", "final", "label", "color", "owner", "editable_by", "reminder"))
                if ks:
                    out.append(f"~ state {cn}.{sn}: {', '.join(ks)}")
        out += [f"- state {cn}.{sn}" for sn in ow["states"] if sn not in w["states"]]
        for tn, tr in w["transitions"].items():
            if tn not in ow["transitions"]:
                out.append(f"+ transition {cn}.{tn}: {', '.join(tr['from'])} -> {tr['to']}")
            else:
                ks = changed_keys(ow["transitions"][tn], tr, ("from", "to", "by", "when", "guard", "comment", "at", "emits", "label"))
                if ks:
                    out.append(f"~ transition {cn}.{tn}: {', '.join(ks)}")
        out += [f"- transition {cn}.{tn}" for tn in ow["transitions"] if tn not in w["transitions"]]
        if not same(ow.get("revert"), w.get("revert")):
            out.append(f"~ workflow {cn}: revert")
    out += [f"- workflow {cn}" for cn in a["workflows"] if cn not in b["workflows"]]
    for cn, evs in b["events"].items():
        out += [f"+ event {cn}.{en}" for en in evs if en not in a["events"].get(cn, {})]
    for cn, evs in a["events"].items():
        out += [f"- event {cn}.{en}" for en in evs if en not in b["events"].get(cn, {})]
    by_name = lambda lst: {str(r.get("name") or i): r for i, r in enumerate(lst)}  # noqa: E731
    ar, br = by_name(a["reactions"]), by_name(b["reactions"])
    for name, r in br.items():
        if name not in ar:
            out.append(f"+ reaction {name} on {r.get('event')}")
        elif changed_keys(ar[name], r, ("event", "when", "notify", "template")):
            out.append(f"~ reaction {name}: {', '.join(changed_keys(ar[name], r, ('event', 'when', 'notify', 'template')))}")
    out += [f"- reaction {name}" for name in ar if name not in br]
    asub, bsub = by_name(a["subscriptions"]), by_name(b["subscriptions"])
    out += [f"+ subscription {n}" for n in bsub if n not in asub]
    out += [f"~ subscription {n}" for n in bsub if n in asub and not same(asub[n], bsub[n])]
    out += [f"- subscription {n}" for n in asub if n not in bsub]
    return out


def behavior_path(meta_path: str | Path) -> Path:
    """Where the behaviour model of a metamodel lives: next to it."""
    return Path(meta_path).parent / BEHAVIOR_FILE


def _list(v: Any) -> list[Any]:
    if v is None:
        return []
    return list(v) if isinstance(v, list) else [v]


def _mapping(v: Any) -> dict[str, Any]:
    return dict(v) if isinstance(v, dict) else {}


def expand(raw: dict[str, Any]) -> dict[str, Any]:
    """Canonical form: every list a list, every element a full mapping. Never raises (validate() reports)."""
    out: dict[str, Any] = {
        "metamodel": raw.get("metamodel") or E.METAMODEL_FILE,
        "doc": raw.get("doc") or "",
        "roles": {}, "derivations": {}, "workflows": {}, "events": {}, "reactions": [], "subscriptions": [],
    }
    for rn, rspec in _mapping(raw.get("roles")).items():
        r = _mapping(rspec) if rspec is not None else {}
        out["roles"][str(rn)] = {**copy.deepcopy(r), "scope": r.get("scope"), "label": r.get("label"), "doc": r.get("doc") or ""}
    for cn, dspec in _mapping(raw.get("derivations")).items():
        out["derivations"][str(cn)] = {str(an): ex for an, ex in _mapping(dspec).items()}
    for cn, wspec in _mapping(raw.get("workflows")).items():
        w = _mapping(wspec)
        states: dict[str, Any] = {}
        for sn, sspec in _mapping(w.get("states")).items():
            s = _mapping(sspec) if sspec is not None else {}
            rem = s.get("reminder")
            states[str(sn)] = {**copy.deepcopy(s), "initial": bool(s.get("initial", False)), "final": bool(s.get("final", False)),
                               "owner": [str(x) for x in _list(s.get("owner"))],
                               "editable_by": [str(x) for x in _list(s.get("editable_by"))],
                               "reminder": _mapping(rem) if isinstance(rem, dict) else ({"after": rem} if rem else None)}
        transitions: dict[str, Any] = {}
        for tn, tspec in _mapping(w.get("transitions")).items():
            t = _mapping(tspec) if tspec is not None else {}
            transitions[str(tn)] = {**copy.deepcopy(t), "from": [str(x) for x in _list(t.get("from"))],
                                    "to": str(t["to"]) if t.get("to") is not None else None,
                                    "by": [str(x) for x in _list(t.get("by"))],
                                    "when": t.get("when"), "guard": t.get("guard"), "comment": t.get("comment"),
                                    "at": t.get("at"), "emits": [str(x) for x in _list(t.get("emits"))]}
        rev = w.get("revert")
        revert = None
        if rev:
            rv = _mapping(rev) if isinstance(rev, dict) else {}
            revert = {**copy.deepcopy(rv), "by": [str(x) for x in _list(rv.get("by"))],
                      "final_by": [str(x) for x in _list(rv.get("final_by"))], "comment": rv.get("comment")}
        out["workflows"][str(cn)] = {**{k: copy.deepcopy(v) for k, v in w.items() if k not in ("states", "transitions", "revert")},
                                     "state": w.get("state"), "states": states, "transitions": transitions, "revert": revert}
    for cn, espec in _mapping(raw.get("events")).items():
        evs: dict[str, Any] = {}
        for en, ev in (_mapping(espec).items() if isinstance(espec, dict) else [(x, None) for x in _list(espec)]):
            evs[str(en)] = _mapping(ev) if ev is not None else {}
        out["events"][str(cn)] = evs
    for r in _list(raw.get("reactions")):
        r = _mapping(r)
        out["reactions"].append({**copy.deepcopy(r), "name": r.get("name"), "event": r.get("event"), "when": r.get("when"),
                                 "notify": [str(x) for x in _list(r.get("notify"))], "template": r.get("template")})
    for s in _list(raw.get("subscriptions")):
        s = _mapping(s)
        out["subscriptions"].append({**copy.deepcopy(s), "name": s.get("name"), "url_env": s.get("url_env"),
                                     "url": s.get("url"), "events": [str(x) for x in _list(s.get("events"))]})
    return out


# --------------------------------------------------------------------------- #
# Events and contexts
# --------------------------------------------------------------------------- #
def events_of(b: dict[str, Any], cname: str) -> list[str]:
    """The events a class can emit: lifecycle, workflow (if it has one) and the declared ones."""
    out = list(LIFECYCLE_EVENTS)
    if cname in b["workflows"]:
        out += list(WORKFLOW_EVENTS)
    out += [x for x in b["events"].get(cname, {}) if x not in out]
    return out


def context(e: dict[str, Any], b: dict[str, Any], cname: str, event: str | None = None) -> X.Context:
    """Where an expression of `cname` is read; in a reaction on `<Class>.transitioned`, `transition` names the
    transition that fired."""
    ctx = X.Context(e, cname)
    if event == "transitioned" and cname in b["workflows"]:
        ctx.variables["transition"] = X.ENUM + "@transition"
        ctx.names["@transition"] = list(b["workflows"][cname]["transitions"])
    return ctx


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate(raw: dict[str, Any], metamodel: dict[str, Any]) -> M.Report:
    """Checks the behaviour model against the metamodel (raw YAML of both). The metamodel itself must be valid."""
    rep = M.Report()
    unknown = set(raw) - TOP_KEYS
    if unknown:
        rep.error("behavior", f"unknown top-level keys: {', '.join(sorted(map(str, unknown)))} "
                  f"(allowed: {', '.join(sorted(TOP_KEYS))})")
    e = E.expand(metamodel)
    b = expand(raw)
    _check_roles(b, e, rep)
    _check_derivations(b, e, rep)
    for cname, w in b["workflows"].items():
        _check_workflow(b, e, cname, w, rep)
    _check_multiplicities(b, e, rep)
    for cname, evs in b["events"].items():
        where = f"events.{cname}"
        if cname not in e["classes"]:
            rep.error(where, f"unknown class {cname}")
            continue
        for en, ev in evs.items():
            if not IDENT.match(en):
                rep.error(f"{where}.{en}", "event names are lowercase identifiers (letters, digits, _)")
            if en in LIFECYCLE_EVENTS or en in WORKFLOW_EVENTS:
                rep.error(f"{where}.{en}", f"'{en}' is a built-in event of every class (lifecycle/workflow): do not declare it")
            extra = set(ev) - EVENT_KEYS
            if extra:
                rep.error(f"{where}.{en}", f"unknown keys: {', '.join(sorted(map(str, extra)))}")
    _check_reactions(b, e, rep)
    _check_subscriptions(b, e, rep)
    return rep


def _check_multiplicities(b: dict[str, Any], e: dict[str, Any], rep: M.Report) -> None:
    """A collection with a minimum (`lower > 0`): the database stores it as many, so the model enforces the minimum
    only through a guard of the workflow (the parts of a record come after the record itself: a check at insert is
    impossible). Reported as a warning until the guard is there (a finite maximum is reported by the metamodel's
    own validate: it is stored as many)."""
    u = uses(b, e)
    for cname, c in e["classes"].items():
        if cname in E.BUILTIN_CLASSES:
            continue
        for rn, r in (c.get("references") or {}).items():
            if r["upper"] == 1:
                continue
            if r["lower"] <= 0:
                continue
            where, mult = f"{cname}.{rn}", f"{r['lower']}..*"
            if cname not in b["workflows"]:
                rep.warn(where, f"minimum of the collection ({mult}) is not enforced by the model (no workflow): "
                                "a rule of the application at its definitive save")
            elif not _guarded(u, cname, rn):
                rep.warn(where, f"minimum of the collection ({mult}) not enforced: add a guard on the first transition "
                                f"of the workflow (e.g. `{rn}.notEmpty()` or `{rn}.size() >= {r['lower']}`)")


def _guarded(u: dict[str, Any], cname: str, rn: str) -> bool:
    """The collection is read by a guard, directly or through a derived attribute of the same class that a guard reads."""
    bucket = u.get(cname) or {}
    entries = (bucket.get("references") or {}).get(rn, [])
    if any(x["kind"] == "guard" for x in entries):
        return True
    attrs = bucket.get("attributes") or {}
    for x in entries:
        if x["kind"] == "derivation" and x["of"].startswith(cname + "."):
            if any(y["kind"] == "guard" for y in attrs.get(x["of"].split(".", 1)[1], [])):
                return True
    return False


def _check_roles(b: dict[str, Any], e: dict[str, Any], rep: M.Report) -> None:
    for rn, r in b["roles"].items():
        where = f"roles.{rn}"
        if not IDENT.match(rn):
            rep.error(where, "role names are lowercase identifiers (letters, digits, _)")
        if rn in BUILTIN_PRINCIPALS:
            rep.error(where, f"'{rn}' is built in (every application has it): do not declare it")
        extra = set(r) - ROLE_KEYS
        if extra:
            rep.error(where, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(sorted(ROLE_KEYS))})")
        scope = r.get("scope")
        if scope is not None:
            if scope in E.BUILTIN_CLASSES:
                rep.error(where, f"scope {scope}: a role is held per instance of a domain class, not per user")
            elif scope not in e["classes"]:
                rep.error(where, f"scope: unknown class {scope}")


def _attribute(e: dict[str, Any], cname: str, an: str) -> dict[str, Any] | None:
    attrs, _ = E.features(e, cname)
    return attrs.get(an)


def _check_derivations(b: dict[str, Any], e: dict[str, Any], rep: M.Report) -> None:
    for cname, ders in b["derivations"].items():
        where = f"derivations.{cname}"
        if cname not in e["classes"]:
            rep.error(where, f"unknown class {cname}")
            continue
        attrs, _ = E.features(e, cname)
        deps: dict[str, set[str]] = {}
        for an, text in ders.items():
            w = f"{where}.{an}"
            a = attrs.get(an)
            if a is None:
                rep.error(w, f"'{an}' is not an attribute of {cname}")
                continue
            if not a.get("derived"):
                rep.error(w, f"{cname}.{an} is not derived: mark it `derived: true` in the metamodel (or drop the formula)")
            if not isinstance(text, str) or not text.strip():
                rep.error(w, "the derivation is an expression (text)")
                continue
            try:
                node, _ = X.check(text, X.Context(e, cname), expect=X.feature_type(a, e, False))
            except X.ExprError as exc:
                rep.error(w, str(exc))
                continue
            deps[an] = {ref[1] for ref in X.features_used(node) if len(ref) == 2 and ref[0] == cname and ref[1] in ders}
        cycle = _cycle(deps)
        if cycle:
            rep.error(f"{where}.{cycle[0]}", f"derivations depend on each other: {' -> '.join(cycle)}")
        for an, a in attrs.items():
            if a.get("derived") and an not in ders:
                rep.warn(f"{where}.{an}", "derived attribute without a derivation: computed in code (a customization)")
    for cname, c in e["classes"].items():
        if cname in b["derivations"]:
            continue
        for an, a in c["attributes"].items():
            if a.get("derived"):
                rep.warn(f"derivations.{cname}.{an}", "derived attribute without a derivation: computed in code (a customization)")


def _cycle(deps: dict[str, set[str]]) -> list[str] | None:
    """The first cycle of a dependency graph (a -> b means a uses b), as [a, b, …, a]; None if acyclic."""
    state: dict[str, int] = {}                  # 1 = on the current path, 2 = done

    def visit(n: str, path: list[str]) -> list[str] | None:
        state[n] = 1
        for m in sorted(deps.get(n, set())):
            if state.get(m) == 1:
                return path[path.index(m):] + [m]
            if m not in state:
                found = visit(m, path + [m])
                if found:
                    return found
        state[n] = 2
        return None

    for n in deps:
        if n not in state:
            found = visit(n, [n])
            if found:
                return found
    return None


def _scope_reference(e: dict[str, Any], cname: str, scope: str) -> list[str]:
    """Single-valued references of a class (own or inherited) that lead to the scope class."""
    _, refs = E.features(e, cname)
    return [rn for rn, r in refs.items() if r["upper"] == 1 and (r["type"] == scope or E.resolve_type(e, r["type"]) == scope)]


def _check_principal(b: dict[str, Any], e: dict[str, Any], cname: str, p: str, where: str, rep: M.Report,
                     notify: bool = False) -> None:
    if p == "creator":
        _, refs = E.features(e, cname) if cname in e["classes"] else ({}, {})
        if not any(rn in ("createdBy", "created_by") and r["type"] in E.BUILTIN_CLASSES for rn, r in refs.items()):
            rep.error(where, f"'creator' needs a reference createdBy: User on {cname} (who created the record)")
        return
    if p in BUILTIN_PRINCIPALS:
        return
    if p.startswith("self.") or p == "self":
        if p == "self":
            rep.error(where, "'self' is the record: navigate to a user (self.<reference>)")
            return
        try:
            _, t = X.check(p, X.Context(e, cname))
        except X.ExprError as exc:
            rep.error(where, f"'{p}': {exc}")
            return
        base = t[len(X.COLLECTION):] if t.startswith(X.COLLECTION) else t
        ok = base == X.CLASS + "User" or (notify and base == "email")
        if not ok:
            want = "a User reference or an Email attribute" if notify else "a User reference"
            rep.error(where, f"'{p}' is {X.type_name(t)}: a principal path leads to {want}")
        return
    m = ROLE_AT.match(p)
    if not m:
        rep.error(where, f"'{p}': admin, creator, a role (role or role@reference) or a navigation self.<path>")
        return
    role, path = m.group("role"), m.group("path")
    r = b["roles"].get(role)
    if r is None:
        attrs, refs = E.features(e, cname) if cname in e["classes"] else ({}, {})
        hint = f" (the reference {cname}.{role}: write self.{role})" if role in refs or role in attrs else ""
        rep.error(where, f"unknown role '{role}'{hint}; roles: {', '.join(b['roles']) or 'none declared'}")
        return
    scope = r.get("scope")
    if scope is None:
        if path:
            rep.error(where, f"role {role} has no scope: write it without @{path}")
        return
    if scope not in e["classes"] or cname not in e["classes"]:
        return                                              # reported elsewhere
    if path:
        try:
            _, t = X.check(path, X.Context(e, cname))
        except X.ExprError as exc:
            rep.error(where, f"'{p}': {exc}")
            return
        if t != X.CLASS + scope:
            rep.error(where, f"'{p}': {path} is {X.type_name(t)}, the scope of {role} is {scope}")
        return
    refs = _scope_reference(e, cname, scope)
    if not refs:
        rep.error(where, f"role {role} is held per {scope}, and {cname} has no reference to {scope}: "
                         f"write {role}@<reference path>")
    elif len(refs) > 1:
        rep.error(where, f"role {role} is held per {scope}, and {cname} has several references to it "
                         f"({', '.join(refs)}): write {role}@{refs[0]}")


def _check_expr(e: dict[str, Any], ctx: X.Context, text: Any, where: str, rep: M.Report) -> dict[str, Any] | None:
    if not isinstance(text, str) or not text.strip():
        rep.error(where, "an expression (text)")
        return None
    try:
        node, _ = X.check(text, ctx, expect=X.BOOL)
    except X.ExprError as exc:
        rep.error(where, str(exc))
        return None
    return node


def _check_workflow(b: dict[str, Any], e: dict[str, Any], cname: str, w: dict[str, Any], rep: M.Report) -> None:
    where = f"workflows.{cname}"
    if cname not in e["classes"]:
        rep.error(where, f"unknown class {cname}")
        return
    c = e["classes"][cname]
    if c["abstract"]:
        rep.error(where, f"{cname} is abstract: a workflow belongs to a concrete class")
    extra = set(w) - WORKFLOW_KEYS
    if extra:
        rep.error(where, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(sorted(WORKFLOW_KEYS))})")
    states, transitions = w["states"], w["transitions"]
    # the state attribute
    sa = w.get("state")
    if not sa:
        rep.error(where, "state: the attribute of the class that holds the state")
    else:
        a = _attribute(e, cname, str(sa))
        if a is None:
            rep.error(f"{where}.state", f"'{sa}' is not an attribute of {cname}")
        elif a["type"] in e["enums"]:
            lits = [lit["name"] for lit in e["enums"][a["type"]]["literals"]]
            missing = [x for x in states if x not in lits]
            extra_l = [x for x in lits if x not in states]
            if missing:
                rep.error(f"{where}.states", f"not literals of {a['type']}: {', '.join(missing)}")
            if extra_l:
                rep.error(f"{where}.states", f"literals of {a['type']} without a state: {', '.join(extra_l)}")
        elif a["type"] != "EString":
            rep.error(f"{where}.state", f"'{sa}' is {a['type']}: the state attribute is an EString or an enum")
        elif a["upper"] != 1:
            rep.error(f"{where}.state", f"'{sa}' is multi-valued")
    if not states:
        rep.error(f"{where}.states", "no states")
    initial = [s for s, spec in states.items() if spec["initial"]]
    final = [s for s, spec in states.items() if spec["final"]]
    if states and len(initial) != 1:
        rep.error(f"{where}.states", f"exactly one state is `initial: true` (found {len(initial)})")
    if states and not final:
        rep.error(f"{where}.states", "at least one state is `final: true`")
    for sn, s in states.items():
        sw = f"{where}.states.{sn}"
        if not IDENT.match(sn):
            rep.error(sw, "state keys are lowercase identifiers (letters, digits, _)")
        extra = set(s) - STATE_KEYS
        if extra:
            rep.error(sw, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(sorted(STATE_KEYS))})")
        if s["initial"] and s["final"]:
            rep.error(sw, "a state is initial or final, not both")
        for key in ("owner", "editable_by"):
            for p in s[key]:
                _check_principal(b, e, cname, p, f"{sw}.{key}", rep)
        rem = s.get("reminder")
        if rem is not None:
            extra = set(rem) - REMINDER_KEYS
            if extra:
                rep.error(f"{sw}.reminder", f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: after, template)")
            if not isinstance(rem.get("after"), str) or not DURATION.match(rem["after"]):
                rep.error(f"{sw}.reminder", "after: a duration such as 7d, 12h or 2w")
            if rem.get("template") is not None and not IDENT.match(str(rem["template"])):
                rep.error(f"{sw}.reminder", "template: a lowercase identifier")
            if s["final"]:
                rep.warn(f"{sw}.reminder", "a final state is never reminded")
    ctx = X.Context(e, cname)
    reach: dict[str, set[str]] = {s: set() for s in states}
    for tn, t in transitions.items():
        tw = f"{where}.transitions.{tn}"
        if not IDENT.match(tn):
            rep.error(tw, "transition keys are lowercase identifiers (letters, digits, _)")
        extra = set(t) - TRANSITION_KEYS
        if extra:
            rep.error(tw, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(sorted(TRANSITION_KEYS))})")
        if not t["from"]:
            rep.error(tw, "from: one or more states")
        for s in t["from"]:
            if s not in states:
                rep.error(tw, f"from: unknown state '{s}'")
            elif states[s]["final"]:
                rep.warn(tw, f"leaves the final state '{s}'")
        if t["to"] is None:
            rep.error(tw, "to: the target state")
        elif t["to"] not in states:
            rep.error(tw, f"to: unknown state '{t['to']}'")
        else:
            for s in t["from"]:
                if s in reach:
                    reach[s].add(t["to"])
        if not t["by"] and t["at"] is None:
            rep.error(tw, "who performs it: `by` (principals), or `at` for a timed transition")
        for p in t["by"]:
            _check_principal(b, e, cname, p, f"{tw}.by", rep)
        if t["at"] is not None:
            m = AT.match(str(t["at"]).strip())
            if not m:
                rep.error(f"{tw}.at", f"'{t['at']}': a date attribute with an optional offset, e.g. endDate + 1d")
            else:
                try:
                    _, at_t = X.check(m.group("path"), ctx)
                    if at_t not in X.TEMPORAL:
                        rep.error(f"{tw}.at", f"'{m.group('path')}' is {X.type_name(at_t)}: a Date or DateTime attribute")
                except X.ExprError as exc:
                    rep.error(f"{tw}.at", str(exc))
        for key in ("when", "guard"):
            if t.get(key) is not None:
                _check_expr(e, ctx, t[key], f"{tw}.{key}", rep)
        if t.get("comment") is not None and t["comment"] not in COMMENT:
            rep.error(f"{tw}.comment", "required or optional")
        declared = b["events"].get(cname, {})
        for ev in t["emits"]:
            if ev not in declared:
                rep.error(f"{tw}.emits", f"'{ev}' is not declared in events.{cname} "
                                         f"({', '.join(declared) or 'none'}); built-in events are emitted anyway")
    if states and len(initial) == 1:
        seen = {initial[0]}
        todo = [initial[0]]
        while todo:
            for n in reach.get(todo.pop(), set()):
                if n not in seen:
                    seen.add(n)
                    todo.append(n)
        for s in states:
            if s not in seen:
                rep.error(f"{where}.states.{s}", f"unreachable from '{initial[0]}'")
    rv = w.get("revert")
    if rv is not None:
        rw = f"{where}.revert"
        extra = set(rv) - REVERT_KEYS
        if extra:
            rep.error(rw, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: by, final_by, comment)")
        if not rv["by"]:
            rep.error(rw, "by: who can bring a record back to a previous state")
        for key in ("by", "final_by"):
            for p in rv[key]:
                _check_principal(b, e, cname, p, f"{rw}.{key}", rep)
        if rv.get("comment") is not None and rv["comment"] not in COMMENT:
            rep.error(f"{rw}.comment", "required or optional")


def _check_reactions(b: dict[str, Any], e: dict[str, Any], rep: M.Report) -> None:
    names: set[str] = set()
    for i, r in enumerate(b["reactions"]):
        name = r.get("name")
        where = f"reactions[{i}]" + (f" {name}" if name else "")
        if not isinstance(name, str) or not IDENT.match(name):
            rep.error(where, "name: a lowercase identifier")
        elif name in names:
            rep.error(where, f"reaction '{name}' declared twice")
        else:
            names.add(name)
        extra = set(r) - REACTION_KEYS
        if extra:
            rep.error(where, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(sorted(REACTION_KEYS))})")
        on = r.get("event")
        if not isinstance(on, str) or on.count(".") != 1:
            rep.error(where, "event: <Class>.<event>, e.g. Invitation.transitioned")
            continue
        cname, event = on.split(".")
        if cname not in e["classes"]:
            rep.error(where, f"event: unknown class {cname}")
            continue
        known = events_of(b, cname)
        if event not in known:
            rep.error(where, f"event: {cname} has no event '{event}' ({', '.join(known)})")
            continue
        ctx = context(e, b, cname, event)
        if r.get("when") is not None:
            _check_expr(e, ctx, r["when"], f"{where}.when", rep)
        if not r["notify"]:
            rep.error(where, "notify: who is notified (principals; a reaction does one thing: notify)")
        else:
            _check_recipients_event(b, e, cname, event, where, rep)
            if b["subscriptions"] and not any(p in (f"{cname}.*", on) for s in b["subscriptions"] for p in s["events"]):
                rep.warn(where, f"notifies on {on} but no subscription receives it: add {cname}.* or {on} to the "
                                "events of a subscription")
        for p in r["notify"]:
            _check_principal(b, e, cname, p, f"{where}.notify", rep, notify=True)
        if r.get("template") is None:
            rep.error(where, "template: the key of the message template the subscriber renders")
        elif not IDENT.match(str(r["template"])):
            rep.error(f"{where}.template", "a lowercase identifier")


def _check_recipients_event(b: dict[str, Any], e: dict[str, Any], cname: str, event: str, where: str, rep: M.Report) -> None:
    """The recipients of a user's action travel on `<Class>.transitioned` (`when: transition = <key>`): a subscriber of
    the state change gets them in `recipients`. A reaction with `notify` on an event a transition emits (`emits`)
    hides them from that subscriber; on both events it notifies twice."""
    w = b["workflows"].get(cname)
    if not w or event in WORKFLOW_EVENTS or event in LIFECYCLE_EVENTS:
        return
    named = transition_reactions(b, e, cname)
    for tn, tr in w["transitions"].items():
        if event not in tr["emits"]:
            continue
        rep.warn(where, f"recipients on {cname}.{event}, a secondary event of transition `{tn}`: subscribers of "
                        f"{cname}.transitioned get none; move the reaction to {cname}.transitioned with "
                        f"`when: transition = {tn}`")
        if named.get(tn):
            rep.warn(where, f"transition `{tn}` notifies on both {cname}.transitioned ({', '.join(named[tn])}) "
                            f"and {cname}.{event}: double notifications")


def transition_reactions(b: dict[str, Any], e: dict[str, Any], cname: str) -> dict[str, list[str]]:
    """{transition key: [reaction names]} for the reactions on `<Class>.transitioned` whose `when` names the
    transition (`transition = x`, `transition in [a, b]`). A `when` that does not type-check contributes nothing."""
    out: dict[str, list[str]] = {}
    for r in b["reactions"]:
        if r.get("event") != f"{cname}.transitioned" or not r.get("when"):
            continue
        try:
            node, _ = X.check(str(r["when"]), context(e, b, cname, "transitioned"), X.BOOL)
        except X.ExprError:
            continue
        for key in _transition_keys(node) or []:
            out.setdefault(key, []).append(str(r.get("name")))
    return out


def _check_subscriptions(b: dict[str, Any], e: dict[str, Any], rep: M.Report) -> None:
    names: set[str] = set()
    for i, s in enumerate(b["subscriptions"]):
        name = s.get("name")
        where = f"subscriptions[{i}]" + (f" {name}" if name else "")
        if not isinstance(name, str) or not IDENT.match(name):
            rep.error(where, "name: a lowercase identifier")
        elif name in names:
            rep.error(where, f"subscription '{name}' declared twice")
        else:
            names.add(name)
        extra = set(s) - SUBSCRIPTION_KEYS
        if extra:
            rep.error(where, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(sorted(SUBSCRIPTION_KEYS))})")
        if not s.get("url_env") and not s.get("url"):
            rep.error(where, "url_env (the environment variable holding the webhook URL) or url")
        elif s.get("url_env") and not ENV_NAME.match(str(s["url_env"])):
            rep.error(where, f"url_env '{s['url_env']}': an environment variable name (UPPER_CASE)")
        if not s["events"]:
            rep.error(where, "events: patterns such as Invitation.*, Invitation.transitioned, user.*")
        for pat in s["events"]:
            if pat in SYSTEM_EVENTS:
                continue
            if pat.count(".") != 1:
                rep.error(f"{where}.events", f"'{pat}': <Class>.<event> or <Class>.*")
                continue
            cname, event = pat.split(".")
            if cname not in e["classes"]:
                rep.error(f"{where}.events", f"'{pat}': unknown class {cname}")
            elif event != "*" and event not in events_of(b, cname):
                rep.error(f"{where}.events", f"'{pat}': {cname} has no event '{event}' ({', '.join(events_of(b, cname))})")


# --------------------------------------------------------------------------- #
# Views: docs/BEHAVIOR.md, runtime JSON, SQL
# --------------------------------------------------------------------------- #
DOC_TEXT: dict[str, dict[str, str]] = {
    "it": {
        "title": "Comportamento del dominio {package}",
        "note": "Generato da `behavior.yaml` con `npm run model:sync`: il comportamento si modifica nel modello, non qui.",
        "roles": "Ruoli", "role": "Ruolo", "label": "Etichetta", "scope": "Ambito", "scope_global": "globale",
        "scope_per": "per {cls}", "builtin_roles": "Oltre ai ruoli predefiniti `admin` (amministratori) e `creator` (chi ha creato il record).",
        "workflow": "Workflow di {cls}", "state_attr": "Lo stato è l'attributo `{attr}`.",
        "states": "Stati", "state": "Stato", "kind": "Tipo", "initial": "iniziale", "final": "finale",
        "owner": "In attesa di", "editable_by": "Modificabile da", "reminder": "Sollecito", "reminder_text": "dopo {after} (`{template}`)",
        "transitions": "Transizioni", "transition": "Transizione", "from_to": "Da → A", "by": "Chi", "when": "Condizione",
        "guard": "Requisito", "comment": "Commento", "at": "Scadenza", "emits": "Eventi", "notifies": "Avvisa", "system": "sistema: {at}",
        "revert": "Ritorno a uno stato precedente: {by}; da uno stato finale: {final_by}; commento {comment}.",
        "comment_required": "obbligatorio", "comment_optional": "facoltativo",
        "derivations": "Attributi calcolati", "attribute": "Attributo", "formula": "Formula", "in_code": "*calcolato nel codice*",
        "events": "Eventi", "event": "Evento", "description": "Descrizione", "builtin_events": "predefinito",
        "lifecycle": "Ogni classe emette `created`, `updated`, `deleted`; una classe con workflow anche `transitioned`, `completed`, `reverted`, `reminder`.",
        "reactions": "Reazioni", "name": "Nome", "recipients": "Destinatari", "template": "Template", "notify": "notifica",
        "subscriptions": "Sottoscrizioni", "url": "URL", "patterns": "Eventi",
        "involved": "Classi coinvolte nel comportamento", "feature": "Attributo o riferimento", "used_by": "Usato da",
        "involved_note": "Classi senza workflow di cui il comportamento legge o usa attributi e riferimenti (formule, condizioni, destinatari, ambiti dei ruoli).",
    },
    "en": {
        "title": "Behaviour of the domain {package}",
        "note": "Generated from `behavior.yaml` by `npm run model:sync`: the behaviour changes in the model, not here.",
        "roles": "Roles", "role": "Role", "label": "Label", "scope": "Scope", "scope_global": "global",
        "scope_per": "per {cls}", "builtin_roles": "Besides the built-in roles `admin` (administrators) and `creator` (who created the record).",
        "workflow": "Workflow of {cls}", "state_attr": "The state is the attribute `{attr}`.",
        "states": "States", "state": "State", "kind": "Kind", "initial": "initial", "final": "final",
        "owner": "Waiting for", "editable_by": "Editable by", "reminder": "Reminder", "reminder_text": "after {after} (`{template}`)",
        "transitions": "Transitions", "transition": "Transition", "from_to": "From → To", "by": "Who", "when": "Condition",
        "guard": "Requirement", "comment": "Comment", "at": "Due", "emits": "Events", "notifies": "Notifies", "system": "system: {at}",
        "revert": "Back to a previous state: {by}; from a final state: {final_by}; comment {comment}.",
        "comment_required": "required", "comment_optional": "optional",
        "derivations": "Derived attributes", "attribute": "Attribute", "formula": "Formula", "in_code": "*computed in code*",
        "events": "Events", "event": "Event", "description": "Description", "builtin_events": "built in",
        "lifecycle": "Every class emits `created`, `updated`, `deleted`; a class with a workflow also `transitioned`, `completed`, `reverted`, `reminder`.",
        "reactions": "Reactions", "name": "Name", "recipients": "Recipients", "template": "Template", "notify": "notify",
        "subscriptions": "Subscriptions", "url": "URL", "patterns": "Events",
        "involved": "Classes involved in the behaviour", "feature": "Attribute or reference", "used_by": "Used by",
        "involved_note": "Classes without a workflow whose attributes and references the behaviour reads or points to (formulas, conditions, recipients, role scopes).",
    },
}
MARKDOWN_MARK = "<!-- modeler: generated from behavior.yaml by model:sync -->"


def _lbl(spec: dict[str, Any], key: str, lang: str) -> str:
    return E._label(spec.get("label"), lang) or key


def _code(v: Any) -> str:
    return f"`{v}`" if v not in (None, "") else ""


def mermaid_workflow(w: dict[str, Any], lang: str) -> str:
    """The workflow as a Mermaid state diagram."""
    lines = ["stateDiagram-v2"]
    initial = [s for s, spec in w["states"].items() if spec["initial"]]
    for sn, s in w["states"].items():
        label = _lbl(s, sn, lang)
        if label != sn:
            lines.append(f"  {sn}: {label}")
    for sn in initial:
        lines.append(f"  [*] --> {sn}")
    for sn, s in w["states"].items():
        if s["final"]:
            lines.append(f"  {sn} --> [*]")
    for tn, t in w["transitions"].items():
        label = _lbl(t, tn, lang)
        suffix = " (auto)" if t.get("at") is not None else ""
        for src in t["from"]:
            lines.append(f"  {src} --> {t['to']}: {label}{suffix}")
    return "\n".join(lines) + "\n"


def to_markdown(raw: dict[str, Any], metamodel: dict[str, Any], lang: str | None = None) -> str:
    """The behaviour explained: roles, one section per workflow (diagram, states, transitions), derivations, events,
    reactions, subscriptions. Deterministic. Assumes a valid behaviour model."""
    e = E.expand(metamodel)
    b = expand(raw)
    lang = lang or e["language"]
    t = DOC_TEXT.get(lang) or DOC_TEXT["en"]
    out = [f"# {t['title'].format(package=e['package'])}", ""]
    if b["doc"]:
        out += [str(b["doc"]), ""]
    out += [f"> {t['note']}", ""]
    if b["roles"]:
        rows = [[rn, E._label(r.get("label"), lang), t["scope_per"].format(cls=r["scope"]) if r.get("scope") else t["scope_global"]]
                for rn, r in b["roles"].items()]
        out += [f"## {t['roles']}", ""] + E._table([t["role"], t["label"], t["scope"]], rows) + ["", t["builtin_roles"], ""]
    for cname, w in b["workflows"].items():
        out += [f"## {t['workflow'].format(cls=cname)}", "", t["state_attr"].format(attr=w["state"]), "",
                "```mermaid", mermaid_workflow(w, lang).rstrip("\n"), "```", ""]
        rows = []
        for sn, s in w["states"].items():
            kind = t["initial"] if s["initial"] else t["final"] if s["final"] else ""
            rem = s.get("reminder")
            rem_text = t["reminder_text"].format(after=rem["after"], template=rem.get("template") or f"{sn}_reminder") if rem else ""
            rows.append([_code(sn), _lbl(s, sn, lang), kind, ", ".join(_code(p) for p in s["owner"]),
                         ", ".join(_code(p) for p in s["editable_by"]), rem_text])
        out += [f"### {t['states']}", ""] + E._table([t["state"], t["label"], t["kind"], t["owner"], t["editable_by"], t["reminder"]], rows) + [""]
        rows = []
        named = transition_reactions(b, e, cname)                  # who is notified on the state change, per transition
        by_name = {r.get("name"): r for r in b["reactions"]}
        for tn, tr in w["transitions"].items():
            who = ", ".join(_code(p) for p in tr["by"]) if tr["by"] else t["system"].format(at=_code(tr["at"]))
            comment = t["comment_required"] if tr.get("comment") == "required" else ""
            notifies = "; ".join(f"{', '.join(_code(p) for p in by_name[n]['notify'])} ({_code(by_name[n].get('template'))})"
                                 for n in named.get(tn, []) if n in by_name)
            rows.append([_code(tn), _lbl(tr, tn, lang), f"{', '.join(tr['from'])} → {tr['to']}", who,
                         _code(tr.get("when")), _code(tr.get("guard")), comment,
                         ", ".join(_code(x) for x in tr["emits"]), notifies])
        out += [f"### {t['transitions']}", ""] + E._table(
            [t["transition"], t["label"], t["from_to"], t["by"], t["when"], t["guard"], t["comment"], t["emits"], t["notifies"]], rows) + [""]
        rv = w.get("revert")
        if rv:
            out += [t["revert"].format(by=", ".join(_code(p) for p in rv["by"]),
                                       final_by=", ".join(_code(p) for p in rv["final_by"]) or "—",
                                       comment=t["comment_required"] if rv.get("comment") == "required" else t["comment_optional"]), ""]
    derived: list[list[str]] = []
    for cname, c in e["classes"].items():
        attrs, _ = E.features(e, cname)
        for an, a in attrs.items():
            if a.get("derived") and (an in c["attributes"]):
                formula = b["derivations"].get(cname, {}).get(an)
                derived.append([cname, _code(an), _code(formula) if formula else t["in_code"]])
    if derived:
        out += [f"## {t['derivations']}", ""] + E._table(["Class" if lang == "en" else "Classe", t["attribute"], t["formula"]], derived) + [""]
    # classes without a workflow whose features the behaviour reads or points to: the only involvement not visible elsewhere
    involved: list[list[str]] = []
    for cname, groups in uses(b, e).items():
        if cname in b["workflows"]:
            continue
        for group in ("attributes", "references"):
            for fn, us in groups[group].items():
                involved.append([cname, _code(fn), ", ".join(f"{u['kind']}: {_code(u['of'])}" for u in us)])
        if groups["class"]:
            involved.append([cname, "—", ", ".join(f"{u['kind']}: {_code(u['of'])}" for u in groups["class"])])
    if involved:
        out += [f"## {t['involved']}", "", t["involved_note"], ""] + E._table(
            ["Class" if lang == "en" else "Classe", t["feature"], t["used_by"]], involved) + [""]
    out += [f"## {t['events']}", "", t["lifecycle"], ""]
    rows = [[cname, _code(en), str(ev.get("doc") or "")] for cname, evs in b["events"].items() for en, ev in evs.items()]
    if rows:
        out += E._table(["Class" if lang == "en" else "Classe", t["event"], t["description"]], rows) + [""]
    if b["reactions"]:
        rows = [[_code(r["name"]), _code(r["event"]), _code(r.get("when")), ", ".join(_code(p) for p in r["notify"]), _code(r.get("template"))]
                for r in b["reactions"]]
        out += [f"## {t['reactions']}", ""] + E._table([t["name"], t["event"], t["when"], t["recipients"], t["template"]], rows) + [""]
    if b["subscriptions"]:
        rows = [[_code(s["name"]), _code(f"${s['url_env']}" if s.get("url_env") else s.get("url")), ", ".join(_code(p) for p in s["events"])]
                for s in b["subscriptions"]]
        out += [f"## {t['subscriptions']}", ""] + E._table([t["name"], t["url"], t["patterns"]], rows) + [""]
    return "\n".join(out).rstrip("\n") + "\n"


def markdown_document(raw: dict[str, Any], metamodel: dict[str, Any], lang: str | None = None) -> str:
    return MARKDOWN_MARK + "\n" + to_markdown(raw, metamodel, lang)


def _typed(text: Any, ctx: X.Context, sql_ctx: X.SqlContext, expect: str | None = None) -> dict[str, Any] | None:
    if text is None:
        return None
    node, t = X.check(str(text), ctx, expect)
    return {"text": X.to_text(node), "type": t, "ast": node, "sql": X.to_sql(node, sql_ctx)}


def uses(b: dict[str, Any], e: dict[str, Any]) -> dict[str, Any]:
    """Which features of which classes the behaviour reads or points to:
    {Class: {attributes: {name: [{kind, of}]}, references: {name: [{kind, of}]}, class: [{kind: "scope", of: role}]}}.
    `kind` says how (derivation, when, guard, at, by, owner, editable_by, revert, notify, scope), `of` where
    (Class.attribute, Class.transition, Class.state, reaction name, role). Computed on the typed trees, so every hop
    of a path is attributed to the class that owns the feature; an expression that does not type-check contributes
    nothing (validate() reports it). Only classes with at least one entry appear."""
    out: dict[str, Any] = {}

    def add(cname: str, group: str | None, name: str | None, kind: str, of: str) -> None:
        if cname in E.BUILTIN_CLASSES or cname not in e["classes"]:
            return
        bucket = out.setdefault(cname, {"attributes": {}, "references": {}, "class": []})
        lst = bucket[group].setdefault(name, []) if group and name else bucket["class"]
        entry = {"kind": kind, "of": of}
        if entry not in lst:
            lst.append(entry)

    def mark(node: dict[str, Any], kind: str, of: str) -> None:
        for owner, seg in X.hops_used(node):
            if owner not in e["classes"]:
                continue
            attrs, _ = E.features(e, owner)
            add(owner, "attributes" if seg in attrs else "references", seg, kind, of)

    def expr(text: Any, ctx: X.Context, kind: str, of: str, expect: str | None = None) -> None:
        try:
            node, _ = X.check(str(text), ctx, expect)
        except X.ExprError:
            return
        mark(node, kind, of)

    def principal(p: str, cname: str, kind: str, of: str) -> None:
        if cname not in e["classes"]:
            return
        if p == "creator":
            _, refs = E.features(e, cname)
            for rn in ("createdBy", "created_by"):
                if rn in refs:
                    add(cname, "references", rn, kind, of)
            return
        if p in BUILTIN_PRINCIPALS:
            return
        if p.startswith("self."):
            expr(p, X.Context(e, cname), kind, of)
            return
        m = ROLE_AT.match(p)
        role_spec = b["roles"].get(m.group("role")) if m else None
        if not m or role_spec is None:
            return
        if m.group("path"):
            expr(m.group("path"), X.Context(e, cname), kind, of)
            return
        scope = role_spec.get("scope")
        if scope in e["classes"]:
            for rn in _scope_reference(e, cname, scope):
                add(cname, "references", rn, kind, of)

    for cname, ders in b["derivations"].items():
        if cname not in e["classes"]:
            continue
        attrs, _ = E.features(e, cname)
        for an, text in ders.items():
            expect = X.feature_type(attrs[an], e, False) if an in attrs else None
            expr(text, X.Context(e, cname), "derivation", f"{cname}.{an}", expect)
    for cname, w in b["workflows"].items():
        if cname not in e["classes"]:
            continue
        ctx = X.Context(e, cname)
        for sn, s in w["states"].items():
            for p in s["owner"]:
                principal(p, cname, "owner", f"{cname}.{sn}")
            for p in s["editable_by"]:
                principal(p, cname, "editable_by", f"{cname}.{sn}")
        for tn, t in w["transitions"].items():
            of = f"{cname}.{tn}"
            for p in t["by"]:
                principal(p, cname, "by", of)
            if t.get("when") is not None:
                expr(t["when"], ctx, "when", of, X.BOOL)
            if t.get("guard") is not None:
                expr(t["guard"], ctx, "guard", of, X.BOOL)
            if t.get("at") is not None:
                m = AT.match(str(t["at"]).strip())
                if m:
                    expr(m.group("path"), ctx, "at", of)
        rv = w.get("revert")
        if rv:
            for p in list(rv["by"]) + list(rv["final_by"]):
                principal(p, cname, "revert", cname)
    for r in b["reactions"]:
        ev = str(r.get("event") or "")
        if "." not in ev:
            continue
        cname, event = ev.split(".", 1)
        name = str(r.get("name") or ev)
        if r.get("when") is not None and cname in e["classes"]:
            expr(r["when"], context(e, b, cname, event), "when", name, X.BOOL)
        for p in r.get("notify") or []:
            principal(str(p), cname, "notify", name)
    for rn, r in b["roles"].items():
        if r.get("scope") in e["classes"]:
            add(str(r["scope"]), None, None, "scope", rn)
    return out


def runtime_json(raw: dict[str, Any], metamodel: dict[str, Any]) -> dict[str, Any]:
    """The behaviour as the application reads it: canonical form, every expression typed (text, type, tree, SQL),
    the entity key of each class (snake_case: event prefix, workflow entity). Assumes a valid behaviour model."""
    e = E.expand(metamodel)
    b = expand(raw)
    b["entities"] = {cname: M.snake(cname) for cname in list(b["workflows"]) + list(b["derivations"]) + list(b["events"])}
    b["uses"] = uses(b, e)                 # on the texts, before they become typed dicts below
    for cname, ders in b["derivations"].items():
        attrs, _ = E.features(e, cname)
        ctx = X.Context(e, cname)
        b["derivations"][cname] = {an: _typed(text, ctx, X.SqlContext(e, cname), X.feature_type(attrs[an], e, False))
                                   for an, text in ders.items()}
    for cname, w in b["workflows"].items():
        ctx, sql_ctx = X.Context(e, cname), X.SqlContext(e, cname)
        for tr in w["transitions"].values():
            for key in ("when", "guard"):
                tr[key] = _typed(tr.get(key), ctx, sql_ctx, X.BOOL)
    for r in b["reactions"]:
        cname, event = str(r["event"]).split(".")
        ctx = context(e, b, cname, event)
        sql_ctx = X.SqlContext(e, cname, variables={"transition": "(p_extra -> 'transition' ->> 'key')"})
        r["when"] = _typed(r.get("when"), ctx, sql_ctx, X.BOOL)
    return b


# --------------------------------------------------------------------------- #
# The runtime workflow engine: principals, clauses, offsets, drift against the published version
# --------------------------------------------------------------------------- #
CLAUSE_OPS = {"=": "eq", "<>": "neq", "<": "lt", "<=": "lte", ">": "gt", ">=": "gte"}


def json_text(value: Any) -> str:
    import json
    return json.dumps(value if isinstance(value, dict) else {}, ensure_ascii=False, sort_keys=True)


def principal_key(p: str) -> str:
    """A principal as the engine stores it: roles and built-ins as they are, `self.issuer` -> `field:issuer`,
    `director@department` -> `director@department`."""
    return "field:" + p[len("self."):] if p.startswith("self.") else p


def offset_interval(offset: str | None) -> str:
    """`+1d`, `12h`, `2w` -> the interval text the engine stores ('1 days', '12 hours', '2 weeks'); '' for none."""
    if not offset:
        return ""
    m = DURATION.match(offset.strip().replace(" ", ""))
    if not m:
        return offset
    n, unit = m.group(1), {"d": "days", "h": "hours", "w": "weeks"}[m.group(2)]
    return f"{int(n)} {unit}"


def clauses(node: dict[str, Any], e: dict[str, Any], cname: str) -> list[dict[str, Any]]:
    """A typed boolean tree as the engine's clauses [{field, op, value}] on the columns of the class: a conjunction of
    atoms on single-valued own attributes (or references with isSet/isEmpty). Anything else raises ExprError with
    the advice to move the logic into a derived attribute."""
    attrs, refs = E.features(e, cname)
    out: list[dict[str, Any]] = []

    def column(p: dict[str, Any]) -> str:
        if p["k"] != "path" or len(p["segs"]) != 1 or (p.get("ref") or [""])[0].startswith("@"):
            raise X.ExprError("a clause tests one attribute of the record: move navigations and calculations into a derived attribute", p["pos"])
        seg = p["segs"][0]
        spec = attrs.get(seg) or refs.get(seg)
        if spec is None or spec["upper"] != 1:
            raise X.ExprError(f"'{seg}' is not a single-valued feature of {cname}", p["pos"])
        return E.field_key(seg, spec)

    def value(lit: dict[str, Any]) -> Any:
        if lit["k"] != "lit":
            raise X.ExprError("a clause compares with a literal: move a comparison between attributes into a derived attribute", lit["pos"])
        return E.literal_key(str(lit["v"])) if lit["t"].startswith(X.ENUM) else lit["v"]

    def atom(n: dict[str, Any], negate: bool = False) -> None:
        k = n["k"]
        if k == "and" and not negate:
            for x in n["items"]:
                atom(x)
            return
        if k == "not":
            atom(n["x"], not negate)
            return
        if k == "path" and n["call"] is None:
            out.append({"field": column(n), "op": "is_false" if negate else "is_true"})
            return
        if k == "path" and n["call"] in ("isSet", "isEmpty"):
            empty = (n["call"] == "isEmpty") != negate
            out.append({"field": column(n), "op": "is_empty" if empty else "is_set"})
            return
        if k == "cmp":
            left, right = (n["l"], n["r"]) if n["r"]["k"] == "lit" else (n["r"], n["l"])
            op = n["op"]
            if left is n["r"] and op in ("<", "<=", ">", ">="):
                op = {"<": ">", "<=": ">=", ">": "<", ">=": "<="}[op]
            col, val = column(left), value(right)
            if right["t"] == X.BOOL and op in ("=", "<>"):
                truth = bool(val) == (op == "=")
                out.append({"field": col, "op": "is_false" if truth == negate else "is_true"})
                return
            if negate:
                flip = {"=": "<>", "<>": "=", "<": ">=", "<=": ">", ">": "<=", ">=": "<"}
                op = flip[op]
            out.append({"field": col, "op": CLAUSE_OPS[op], "value": val})
            return
        if k == "in":
            out.append({"field": column(n["x"]), "op": "not_in" if negate else "in", "value": [value(i) for i in n["items"]]})
            return
        if k == "lit" and n["t"] == X.BOOL:
            if bool(n["v"]) == negate:
                raise X.ExprError("a clause that is always false", n["pos"])
            return
        raise X.ExprError(f"'{X.to_text(n)}' is not a clause: a guard is a conjunction of tests on single attributes "
                          "(or, arithmetic and navigations go into a derived attribute)", n["pos"])

    atom(node)
    return out


def engine_version(raw: dict[str, Any], metamodel: dict[str, Any], cname: str) -> dict[str, Any]:
    """The workflow of a class as the runtime engine stores a version: states and transitions with the engine's
    principals, clauses, trigger, offset and event names. Reactions on `<Class>.transitioned` naming one transition
    become its `notify`. Raises ExprError for a guard the engine cannot evaluate."""
    e = E.expand(metamodel)
    b = expand(raw)
    w = b["workflows"][cname]
    entity = M.snake(cname)
    ctx = X.Context(e, cname)
    states = []
    for i, (sn, s) in enumerate(w["states"].items()):
        rem = s.get("reminder")
        days = None
        if rem and isinstance(rem.get("after"), str):
            m = DURATION.match(rem["after"])
            days = int(m.group(1)) * {"d": 1, "h": 0, "w": 7}[m.group(2)] if m else None
        states.append({"key": sn, "labels": s.get("label") if isinstance(s.get("label"), dict) else {},
                       "kind": "initial" if s["initial"] else "final" if s["final"] else "normal",
                       "color": s.get("color") or "#64748b", "owner": [principal_key(p) for p in s["owner"]],
                       "editable_by": [principal_key(p) for p in s["editable_by"]],
                       "reminder_days": days, "reminder_template": (rem or {}).get("template"), "sort": i})
    notify: dict[str, list[dict[str, Any]]] = {}
    for r in b["reactions"]:
        if r["event"] != f"{cname}.transitioned" or not r.get("when"):
            continue
        node, _ = X.check(str(r["when"]), context(e, b, cname, "transitioned"), X.BOOL)
        keys = _transition_keys(node)
        for key in keys or []:
            notify.setdefault(key, []).append({"to": [principal_key(p) for p in r["notify"]], "template": r["template"]})
    transitions = []
    for i, (tn, tr) in enumerate(w["transitions"].items()):
        guard = clauses(X.check(str(tr["guard"]), ctx, X.BOOL)[0], e, cname) if tr.get("guard") else []
        cond = clauses(X.check(str(tr["when"]), ctx, X.BOOL)[0], e, cname) if tr.get("when") else []
        at_field, at_offset = None, ""
        if tr.get("at") is not None:
            m = AT.match(str(tr["at"]).strip())
            if m:
                attrs, _ = E.features(e, cname)
                at_field = E.field_key(m.group("path"), attrs.get(m.group("path")))
                at_offset = offset_interval(f"{m.group('n')}{m.group('unit')}") if m.group("n") else ""
        transitions.append({"key": tn, "labels": tr.get("label") if isinstance(tr.get("label"), dict) else {},
                            "from_states": list(tr["from"]), "to_state": tr["to"],
                            "allowed": [principal_key(p) for p in tr["by"]],
                            "trigger": "timed" if tr.get("at") is not None else "manual", "at_field": at_field, "at_offset": at_offset,
                            "comment": tr.get("comment") or "optional", "guard": guard, "condition": cond,
                            "emits": [f"{entity}.{ev}" for ev in tr["emits"]], "notify": notify.get(tn, []), "sort": i})
    return {"entity": entity, "states": states, "transitions": transitions}


def _transition_keys(node: dict[str, Any]) -> list[str] | None:
    """The transition keys a reaction's `when` names (`transition = x`, `transition in [a, b]`); None if it is
    another kind of condition."""
    if node["k"] == "cmp" and node["op"] == "=":
        sides = [node["l"], node["r"]]
        var = next((s for s in sides if s["k"] == "path" and (s.get("ref") or [""])[0] == "@transition"), None)
        lit = next((s for s in sides if s["k"] == "lit"), None)
        if var is not None and lit is not None:
            return [str(lit["v"])]
    if node["k"] == "in" and node["x"]["k"] == "path" and (node["x"].get("ref") or [""])[0] == "@transition":
        return [str(i["v"]) for i in node["items"] if i["k"] == "lit"]
    return None


def workflow_drift(raw: dict[str, Any], metamodel: dict[str, Any], catalog: dict[str, Any]) -> list[str]:
    """Differences between the workflows of the behaviour model and the published versions in the database
    (`dbschema.workflow_catalog`): states (kind, owner, editable_by, reminder), transitions (from/to, allowed, trigger,
    guard, condition, emits). Labels, colours and notifications are not compared. Empty list = aligned."""
    out: list[str] = []
    b = expand(raw)
    published = {v["entity"]: v for v in catalog.get("versions", []) if v.get("status") == "published"}
    for cname in b["workflows"]:
        entity = M.snake(cname)
        v = published.get(entity)
        if v is None:
            out.append(f"WORKFLOW {entity}: no published version in the database (behavior.yaml has one for {cname})")
            continue
        try:
            model = engine_version(raw, metamodel, cname)
        except X.ExprError as exc:
            out.append(f"WORKFLOW {entity}: a guard the engine cannot evaluate: {exc}")
            continue
        db_states = {s["key"]: s for s in catalog.get("states", []) if s["version_id"] == v["id"]}
        db_trans = {t["key"]: t for t in catalog.get("transitions", []) if t["version_id"] == v["id"]}
        for s in model["states"]:
            d = db_states.get(s["key"])
            if d is None:
                out.append(f"MISSING STATE {entity}.{s['key']} (version {v['version']})")
                continue
            for key in ("kind", "owner", "editable_by", "reminder_days", "reminder_template"):
                a, bb = s.get(key), d.get(key)
                if key in ("owner", "editable_by"):
                    a, bb = sorted(a or []), sorted(bb or [])
                if a != bb and not (key == "reminder_template" and s.get("reminder_days") is None):
                    out.append(f"STATE {entity}.{s['key']}: {key} database {bb!r}, model {a!r}")
        for key in db_states:
            if key not in {s["key"] for s in model["states"]}:
                out.append(f"NOT IN MODEL state {entity}.{key}")
        for t in model["transitions"]:
            d = db_trans.get(t["key"])
            if d is None:
                out.append(f"MISSING TRANSITION {entity}.{t['key']}")
                continue
            for key in ("from_states", "to_state", "allowed", "trigger", "at_field", "at_offset", "comment", "guard", "condition", "emits"):
                a, bb = t.get(key), d.get(key)
                if key in ("from_states", "allowed", "emits"):
                    a, bb = sorted(a or []), sorted(bb or [])
                if key in ("guard", "condition"):
                    a, bb = sorted(map(_clause_key, a or [])), sorted(map(_clause_key, bb or []))
                if key == "at_offset":
                    a, bb = (a or "").strip(), (bb or "").strip()
                if a != bb:
                    out.append(f"TRANSITION {entity}.{t['key']}: {key} database {bb!r}, model {a!r}")
        for key in db_trans:
            if key not in {t["key"] for t in model["transitions"]}:
                out.append(f"NOT IN MODEL transition {entity}.{key}")
    for entity in published:
        if entity not in {M.snake(c) for c in b["workflows"]}:
            out.append(f"NOT IN MODEL workflow {entity} (published version in the database)")
    return out


def _clause_key(c: dict[str, Any]) -> str:
    v = c.get("value")
    return f"{c.get('field')} {c.get('op')} {sorted(map(str, v)) if isinstance(v, list) else v}"


def sql_view(raw: dict[str, Any], metamodel: dict[str, Any]) -> str:
    """Derivations, guards, conditions and reaction conditions as PostgreSQL on a row `r` of each class: a preview
    of what the engine evaluates (to paste into functions, triggers or generated columns)."""
    e = E.expand(metamodel)
    b = expand(raw)
    out: list[str] = []
    for cname, ders in b["derivations"].items():
        attrs, _ = E.features(e, cname)
        ctx = X.Context(e, cname)
        out.append(f"-- {cname}: derived attributes (r = a row of {X.SqlContext(e, cname).table(cname)})")
        for an, text in ders.items():
            node, t = X.check(str(text), ctx, X.feature_type(attrs[an], e, False))
            sql = X.to_sql(node, X.SqlContext(e, cname))
            out.append(f"--   {an}")
            out.append(f"{E.field_key(an, attrs[an])} := {f'coalesce({sql}, false)' if t == X.BOOL else sql};")
        out.append("")
    for cname, w in b["workflows"].items():
        ctx, sql_ctx = X.Context(e, cname), X.SqlContext(e, cname)
        out.append(f"-- {cname}: transitions (condition hides, guard blocks)")
        for tn, tr in w["transitions"].items():
            for key in ("when", "guard"):
                if tr.get(key) is not None:
                    node, _ = X.check(str(tr[key]), ctx, X.BOOL)
                    out.append(f"--   {tn}.{key}: {X.to_text(node)}")
                    out.append(f"coalesce({X.to_sql(node, sql_ctx)}, false)")
        out.append("")
    if b["reactions"]:
        out.append("-- reactions (p_extra: the event's data)")
        for r in b["reactions"]:
            cname, event = str(r["event"]).split(".")
            if r.get("when") is None:
                continue
            node, _ = X.check(str(r["when"]), context(e, b, cname, event), X.BOOL)
            sql_ctx = X.SqlContext(e, cname, variables={"transition": "(p_extra -> 'transition' ->> 'key')"})
            out.append(f"--   {r['name']} on {r['event']}: {X.to_text(node)}")
            out.append(f"coalesce({X.to_sql(node, sql_ctx)}, false)")
    return "\n".join(out).rstrip("\n") + "\n"
