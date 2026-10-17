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
        for p in r["notify"]:
            _check_principal(b, e, cname, p, f"{where}.notify", rep, notify=True)
        if r.get("template") is None:
            rep.error(where, "template: the key of the message template the subscriber renders")
        elif not IDENT.match(str(r["template"])):
            rep.error(f"{where}.template", "a lowercase identifier")


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
