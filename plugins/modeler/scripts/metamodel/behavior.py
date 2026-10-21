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
TOP_KEYS = {"metamodel", "doc", "roles", "view_as", "derivations", "workflows", "events", "reactions", "subscriptions", "templates"}
TEMPLATE_KEYS = {"subject", "body"}
LANG_RE = re.compile(r"^[a-z]{2}$")
PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][\w.]*)\s*\}\}")
# the variables a notification text may use besides the record's own paths (`{{self.path}}` or `{{<entity>.path}}`)
TEMPLATE_VARS = {"actor.name", "actor.email", "comment", "url"}
TRANSITION_VARS = {"transition.key", "transition.label", "transition.from", "transition.to"}
REMINDER_VARS = {"reminder.days", "reminder.count", "reminder.state"}
STATE_VARS = {"state.key", "state.label"}
ROLE_KEYS = {"label", "scope", "doc"}
VIEW_AS_KEYS = {"users_by", "doc"}   # «view as»: who may use the application as another user
WORKFLOW_KEYS = {"state", "states", "transitions", "revert", "doc"}
STATE_KEYS = {"initial", "final", "label", "doc", "owner", "editable_by", "reminder", "color", "requires", "model"}
MODEL_KEYS = {"lower", "readonly", "hidden", "in"}   # the overlay of a state on a feature (`states.<key>.model`)
TRANSITION_KEYS = {"from", "to", "by", "when", "guard", "comment", "at", "emits", "label", "doc", "notify", "template"}
NOTIFY_KEYS = {"to", "template", "when"}            # `notify: {to, template, when}` on a transition (the long form of `notify: [...]`)
INTERNAL_KEYS = {"notify_when", "notifies", "_notify_extra", "_transition"}   # canonical/runtime keys, never written in the file
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
            n = _mapping(t).get("notify")
            if isinstance(n, dict) and isinstance(n.get("when"), str):
                n["when"] = " ".join(n["when"].split())
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
    if doc.get("view_as") is not None:
        raw["view_as"] = dict(_mapping(doc["view_as"]))
    raw["derivations"] = {cn: {an: text(ex) for an, ex in _mapping(ders).items()} for cn, ders in _mapping(doc.get("derivations")).items()}
    raw["workflows"] = {}
    for cn, w in _mapping(doc.get("workflows")).items():
        w = _mapping(w)
        states = {sn: {k: v for k, v in _mapping(st).items()} for sn, st in _mapping(w.get("states")).items()}
        transitions = {}
        for tn, t in _mapping(w.get("transitions")).items():
            t = {k: (text(v) if k in ("when", "guard", "notify_when") else v) for k, v in _mapping(t).items()
                 if k not in ("notifies", "_notify_extra")}
            if isinstance(t.get("from"), list) and len(t["from"]) == 1:
                t["from"] = t["from"][0]
            nwhen = t.pop("notify_when", None)
            if nwhen and t.get("notify"):          # a notification with its own condition: the long form
                t["notify"] = {"to": t["notify"], "template": t.pop("template", None), "when": nwhen}
            transitions[tn] = t
        raw["workflows"][cn] = {**{k: v for k, v in w.items() if k not in ("states", "transitions")}, "states": states, "transitions": transitions}
    raw["events"] = {cn: {en: (ev or {}) for en, ev in _mapping(evs).items()} for cn, evs in _mapping(doc.get("events")).items()}
    raw["reactions"] = [{k: (text(v) if k == "when" else v) for k, v in _mapping(r).items()} for r in _list(doc.get("reactions"))
                        if not _mapping(r).get("_transition")]      # the notification of a transition is written on the transition
    raw["subscriptions"] = [dict(_mapping(sub)) for sub in _list(doc.get("subscriptions"))]
    raw["templates"] = {k: {lang: dict(_mapping(tx)) for lang, tx in _mapping(langs).items()} for k, langs in _mapping(doc.get("templates")).items()}
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
           "# Edit it from the prompt (/modeler:behavior), in the app's modeler (/admin/model) or by hand; `npm run",
           "# model:validate` checks it against domain.ecore.yaml.", ""]
    for key in ("metamodel", "doc"):
        if r.get(key):   # a scalar: never a flow mapping at the top level (it would end the document)
            scalar = yaml.safe_dump(r[key], allow_unicode=True, width=1000).strip()
            out.append(f"{key}: {scalar.split(chr(10))[0] if scalar.endswith('...') else scalar}")
    if r.get("roles"):
        out += ["", dump(block({"roles": flow_map(r["roles"])}))]
    if r.get("view_as") is not None:
        out += ["", dump(block({"view_as": _Flow(r["view_as"] if isinstance(r["view_as"], dict) else {})}))]
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
    if r.get("templates"):
        out += ["", "templates:"]
        for key, langs in r["templates"].items():
            out += ["  " + line for line in dump(block({key: block({lang: block(tx) for lang, tx in langs.items()})})).split("\n")]
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
    av, bv = a["view_as"], b["view_as"]
    if bv is not None and av is None:
        out.append(f"+ view_as (users_by: {', '.join(bv['users_by']) or 'nobody'})")
    elif bv is not None and av is not None and not same(av["users_by"], bv["users_by"]):
        out.append(f"~ view_as: users_by {', '.join(bv['users_by']) or 'nobody'}")
    elif bv is None and av is not None:
        out.append("- view_as")
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
                ks = changed_keys(ow["states"][sn], st, ("initial", "final", "label", "color", "owner", "editable_by", "reminder", "requires", "model"))
                if ks:
                    out.append(f"~ state {cn}.{sn}: {', '.join(ks)}")
        out += [f"- state {cn}.{sn}" for sn in ow["states"] if sn not in w["states"]]
        for tn, tr in w["transitions"].items():
            if tn not in ow["transitions"]:
                out.append(f"+ transition {cn}.{tn}: {', '.join(tr['from'])} -> {tr['to']}")
            else:
                ks = changed_keys(ow["transitions"][tn], tr, ("from", "to", "by", "when", "guard", "comment", "at", "emits", "label", "notify", "template"))
                if "notify" not in ks and not same(ow["transitions"][tn].get("notify_when"), tr.get("notify_when"), "when"):
                    ks.append("notify")          # the condition of the notification changed
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
    explicit = lambda lst: [r for r in lst if not r.get("_transition")]   # noqa: E731  (a transition's notification is diffed with it)
    ar, br = by_name(explicit(a["reactions"])), by_name(explicit(b["reactions"]))
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
    for k, langs in b["templates"].items():
        if k not in a["templates"]:
            out.append(f"+ template {k} ({', '.join(langs)})")
        else:
            ks = [lang for lang in sorted(set(langs) | set(a["templates"][k])) if not same(a["templates"][k].get(lang), langs.get(lang))]
            if ks:
                out.append(f"~ template {k}: {', '.join(ks)}")
    out += [f"- template {k}" for k in a["templates"] if k not in b["templates"]]
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
    out["view_as"] = None
    if raw.get("view_as") is not None:
        v = _mapping(raw["view_as"]) if isinstance(raw["view_as"], dict) else {"_invalid": raw["view_as"]}
        out["view_as"] = {**copy.deepcopy(v), "users_by": [str(x) for x in _list(v.get("users_by"))]}
    for cn, dspec in _mapping(raw.get("derivations")).items():
        out["derivations"][str(cn)] = {str(an): ex for an, ex in _mapping(dspec).items()}
    synthetic: list[dict[str, Any]] = []        # the notification of a transition, as the reaction it stands for
    for cn, wspec in _mapping(raw.get("workflows")).items():
        w = _mapping(wspec)
        states: dict[str, Any] = {}
        for sn, sspec in _mapping(w.get("states")).items():
            s = _mapping(sspec) if sspec is not None else {}
            rem = s.get("reminder")
            states[str(sn)] = {**copy.deepcopy(s), "initial": bool(s.get("initial", False)), "final": bool(s.get("final", False)),
                               "owner": [str(x) for x in _list(s.get("owner"))],
                               "editable_by": [str(x) for x in _list(s.get("editable_by"))],
                               "requires": [str(x) for x in _list(s.get("requires"))],
                               "model": _model_spec(s.get("model")),
                               "reminder": _mapping(rem) if isinstance(rem, dict) else ({"after": rem} if rem else None)}
        transitions: dict[str, Any] = {}
        for tn, tspec in _mapping(w.get("transitions")).items():
            t = _mapping(tspec) if tspec is not None else {}
            # `notify: [principals]` + `template: key`, or `notify: {to, template, when}` for a condition of its own
            n = t.get("notify")
            if isinstance(n, dict):
                to, template, nwhen = [str(x) for x in _list(n.get("to"))], n.get("template", t.get("template")), n.get("when")
                extra_n = sorted(str(k) for k in set(n) - NOTIFY_KEYS)
            else:
                to, template, nwhen, extra_n = [str(x) for x in _list(n)], t.get("template"), None, []
            transitions[str(tn)] = {**copy.deepcopy(t), "from": [str(x) for x in _list(t.get("from"))],
                                    "to": str(t["to"]) if t.get("to") is not None else None,
                                    "by": [str(x) for x in _list(t.get("by"))],
                                    "when": t.get("when"), "guard": t.get("guard"), "comment": t.get("comment"),
                                    "at": t.get("at"), "emits": [str(x) for x in _list(t.get("emits"))],
                                    "notify": to, "template": template, "notify_when": nwhen, "_notify_extra": extra_n}
            if to:
                cond = f"transition = {tn}" + (f" and ({' '.join(str(nwhen).split())})" if nwhen else "")
                synthetic.append({"name": f"notify_{tn}", "event": f"{cn}.transitioned", "when": cond, "notify": list(to),
                                  "template": template, "_transition": str(tn)})
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
    out["reactions"] += synthetic                # after the explicit ones: the first reaction wins a shared address
    for s in _list(raw.get("subscriptions")):
        s = _mapping(s)
        out["subscriptions"].append({**copy.deepcopy(s), "name": s.get("name"), "url_env": s.get("url_env"),
                                     "url": s.get("url"), "events": [str(x) for x in _list(s.get("events"))]})
    out["templates"] = {}
    for key, spec in _mapping(raw.get("templates")).items():
        langs: dict[str, Any] = {}
        for lang, texts in _mapping(spec).items():
            tx = _mapping(texts) if isinstance(texts, dict) else {"subject": texts}
            langs[str(lang)] = {**copy.deepcopy(tx), "subject": "" if tx.get("subject") is None else str(tx["subject"]),
                                "body": "" if tx.get("body") is None else str(tx["body"])}
        out["templates"][str(key)] = langs
    return out


# --------------------------------------------------------------------------- #
# Events and contexts
# --------------------------------------------------------------------------- #
def _model_spec(v: Any) -> dict[str, Any]:
    """`model` of a state in canonical form: {feature: {lower, readonly, hidden, in, …}}; unknown keys are kept for
    validate, a value that is not a mapping becomes {"_invalid": value}."""
    out: dict[str, Any] = {}
    for f, spec in _mapping(v).items():
        o = dict(spec) if isinstance(spec, dict) else {"_invalid": spec}
        o["lower"] = o.get("lower")
        o["readonly"] = bool(o.get("readonly", False))
        o["hidden"] = bool(o.get("hidden", False))
        o["in"] = [str(x) for x in _list(o.get("in"))] if o.get("in") is not None else None
        out[str(f)] = o
    return out


EMPTY_OVERLAY = {"lower": None, "readonly": False, "hidden": False, "in": None}


def state_overlay(s: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """The class as seen from a state: `model` merged with `requires` (the shorthand for `lower: 1`), per feature
    {lower (0, 1 or None), readonly, hidden (implies readonly), in (literals or None)}. Only the features the state
    changes; the metamodel says the rest. Works on an expanded or a raw state."""
    out: dict[str, dict[str, Any]] = {}
    for f in _list(s.get("requires")):
        out.setdefault(str(f), dict(EMPTY_OVERLAY))["lower"] = 1
    for f, o in _model_spec(s.get("model")).items():
        cur = out.setdefault(f, dict(EMPTY_OVERLAY))
        if o["lower"] is not None:
            cur["lower"] = o["lower"]
        cur["hidden"] = cur["hidden"] or o["hidden"]
        cur["readonly"] = cur["readonly"] or o["readonly"] or o["hidden"]
        if o["in"] is not None:
            cur["in"] = list(o["in"])
    return out


def required_features(s: dict[str, Any]) -> list[str]:
    """The features a state requires: `requires` and the `lower: 1` of its `model`."""
    return [f for f, o in state_overlay(s).items() if o["lower"] == 1]


def refine(metamodel: dict[str, Any], cname: str, s: dict[str, Any]) -> dict[str, Any]:
    """The metamodel as seen from a state of `cname` (the expanded metamodel with the state's overlay applied to the
    class: `lower: 1`, `changeable: false` for read only, hidden features removed, `in` as the allowed literals)."""
    e = copy.deepcopy(E.expand(metamodel))
    attrs, refs = E.features(e, cname)
    for f, o in state_overlay(s).items():
        spec = attrs.get(f) or refs.get(f)
        if spec is None:
            continue
        group = "attributes" if f in attrs else "references"
        owner = e["classes"][spec["_owner"]][group]
        if o["hidden"]:
            owner.pop(f, None)
            continue
        if o["lower"] == 1:
            owner[f]["lower"] = 1
        if o["readonly"]:
            owner[f]["changeable"] = False
        if o["in"] is not None:
            owner[f]["in"] = list(o["in"])
    return e


def state_matrix(b: dict[str, Any], e: dict[str, Any], cname: str) -> list[dict[str, Any]]:
    """Feature × state of a workflow: [{feature, states: {state: overlay}}], one row per feature at least one
    state changes, in the order of the class."""
    w = b["workflows"].get(cname)
    if not w:
        return []
    attrs, refs = E.features(e, cname)
    overlays = {sn: state_overlay(s) for sn, s in w["states"].items()}
    out = []
    for f in list(attrs) + list(refs):
        cells = {sn: ov[f] for sn, ov in overlays.items() if f in ov}
        if cells:
            out.append({"feature": f, "states": cells})
    return out


def domain_annotations(raw: dict[str, Any], metamodel: dict[str, Any]) -> dict[str, Any]:
    """What docs/DOMAIN.md says of the workflow states next to each feature: {Class: {feature: [{state, label,
    lower, readonly, hidden, in}]}} (the label as written in the model: a string or {it, en})."""
    e, b = E.expand(metamodel), expand(raw)
    out: dict[str, Any] = {}
    for cname, w in b["workflows"].items():
        if cname not in e["classes"]:
            continue
        for row in state_matrix(b, e, cname):
            out.setdefault(cname, {})[row["feature"]] = [
                {"state": sn, "label": w["states"][sn].get("label"), **o} for sn, o in row["states"].items()]
    return out


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
    _check_view_as(b, rep)
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
    _check_templates(b, e, rep)
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
                                f"of the workflow (e.g. `{rn}.notEmpty()` or `{rn}.size() >= {r['lower']}`) or list it in the "
                                f"`requires` of a state")


def _guarded(u: dict[str, Any], cname: str, rn: str) -> bool:
    """The collection is read by a guard, directly or through a derived attribute of the same class that a guard reads,
    or a state of the workflow requires it (`requires`: an implicit guard of every transition entering the state)."""
    bucket = u.get(cname) or {}
    entries = (bucket.get("references") or {}).get(rn, [])
    if any(x["kind"] in ("guard", "requires") for x in entries):
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


def _check_view_as(b: dict[str, Any], rep: M.Report) -> None:
    """`view_as: {users_by: [admin, office]}`: who may use the application as another user (the administrators
    and roles without scope); restricting one's own session to one of one's roles needs no declaration."""
    v = b["view_as"]
    if v is None:
        return
    where = "view_as"
    if "_invalid" in v:
        rep.error(where, "a mapping: {users_by: [admin, <role>]}")
        return
    extra = set(v) - VIEW_AS_KEYS
    if extra:
        rep.error(where, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(sorted(VIEW_AS_KEYS))})")
    seen: set[str] = set()
    for p in v["users_by"]:
        fw = f"{where}.users_by"
        if p in seen:
            rep.error(fw, f"'{p}' listed twice")
        seen.add(p)
        if p == "admin":
            continue
        if p == "creator" or p.startswith("self.") or "@" in p:
            rep.error(fw, f"'{p}': only admin or a role declared in roles without scope (who may act as another user is not a property of a record)")
        elif p not in b["roles"]:
            rep.error(fw, f"unknown role '{p}'")
        elif b["roles"][p].get("scope") is not None:
            rep.error(fw, f"'{p}' is held per {b['roles'][p]['scope']}: acting as another user needs a role without scope")
    if not v["users_by"]:
        rep.warn(where, "users_by is empty: nobody acts as another user; the session can still be restricted to one of the user's roles")


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
        _check_state_model(e, cname, sa, sn, s, states, transitions, sw, rep)
    ctx = X.Context(e, cname)
    reach: dict[str, set[str]] = {s: set() for s in states}
    for tn, t in transitions.items():
        tw = f"{where}.transitions.{tn}"
        if not IDENT.match(tn):
            rep.error(tw, "transition keys are lowercase identifiers (letters, digits, _)")
        extra = set(t) - TRANSITION_KEYS - INTERNAL_KEYS
        if extra:
            rep.error(tw, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(sorted(TRANSITION_KEYS))})")
        if t.get("_notify_extra"):
            rep.error(f"{tw}.notify", f"unknown keys: {', '.join(t['_notify_extra'])} (allowed: {', '.join(sorted(NOTIFY_KEYS))})")
        if t.get("template") is not None and not t["notify"]:
            rep.error(f"{tw}.template", "a template without notify: who is notified? (notify: [principals], or notify: {to, template, when})")
        if t.get("notify_when") is not None:
            if not t["notify"]:
                rep.error(f"{tw}.notify", "when without to: who is notified?")
            else:
                _check_expr(e, context(e, b, cname, "transitioned"), t["notify_when"], f"{tw}.notify.when", rep)
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


def _check_state_model(e: dict[str, Any], cname: str, sa: Any, sn: str, s: dict[str, Any], states: dict[str, Any],
                       transitions: dict[str, Any], where: str, rep: M.Report) -> None:
    """`requires` and `model`: the class as seen from the state only tightens the metamodel. A required feature
    (`requires`, `lower: 1`) must be set to enter the state and while the record stays there: not derived (computed
    after the check), not the state attribute, not already required by the metamodel, not repeated by a guard of
    an entering transition. `readonly`/`hidden` (enforced on single-valued features), `in` (a single-valued enum
    attribute, a subset of its literals). Along the path (docs/research/state-indexed-refinement.md, P3): what the
    target asks must be reachable from the source. A record in a state can only hold the values the state allows
    (`in`, null when not required): when the source's and the target's sets are disjoint the transition can never
    fire (error, whatever readonly says); when the source is read only and allows more than the target, the
    records that entered it with another value are stuck (warning)."""
    attrs, refs = E.features(e, cname)
    seen: set[str] = set()
    for f in s["requires"]:
        if f in seen:
            rep.error(f"{where}.requires", f"'{f}' listed twice")
        seen.add(f)
    model = s.get("model") or {}
    for f, o in model.items():
        if "_invalid" in o:
            rep.error(f"{where}.model.{f}", "a mapping: {lower: 1, readonly: true, hidden: true, in: [a, b]}")
            continue
        extra = set(o) - MODEL_KEYS
        if extra:
            rep.error(f"{where}.model.{f}", f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: {', '.join(sorted(MODEL_KEYS))})")
    overlay = state_overlay(s)
    for f, o in overlay.items():
        fw = f"{where}.requires" if f in seen and f not in model else f"{where}.model.{f}"
        spec = attrs.get(f) or refs.get(f)
        if spec is None:
            rep.error(fw, f"'{f}' is not a feature of {cname}")
            continue
        if f == sa:
            rep.error(fw, f"'{f}' is the state attribute")
            continue
        single = spec.get("upper", 1) == 1
        if spec.get("derived"):
            if o["lower"] == 1 or o["in"] is not None:
                rep.error(fw, f"'{f}' is derived: a derived attribute is computed after the check; test it in a guard instead")
            elif o["readonly"] and not o["hidden"]:
                rep.error(fw, f"'{f}' is derived: already read only")
            continue
        if o["lower"] not in (None, 0, 1):
            rep.error(fw, "lower: 0 or 1 (a state requires a feature or leaves it as the metamodel says)")
        elif o["lower"] == 0 and int(spec.get("lower") or 0) >= 1:
            rep.error(fw, f"'{f}' is required by the metamodel (lower {spec['lower']}): a state cannot relax it")
        elif o["lower"] == 1:
            if o["hidden"]:
                rep.error(fw, f"'{f}' hidden and required: a hidden feature cannot be set")
            if int(spec.get("lower") or 0) >= 1:
                rep.warn(fw, f"'{f}' is already required by the metamodel (lower {spec['lower']}): the state adds nothing")
            if s["initial"]:
                rep.warn(fw, f"'{f}' required from the initial state: that is `lower: 1` in the metamodel (required from creation)")
        if o["readonly"] and not single:
            rep.warn(fw, f"'{f}' is a collection: {'hidden' if o['hidden'] else 'readonly'} is not enforced by the engine (its parts have "
                         "their own table), only reported to the application")
        elif o["readonly"] and not o["hidden"] and spec.get("changeable") is False:
            rep.warn(fw, f"'{f}' is already read only in the metamodel (changeable: false): the state adds nothing")
        if o["in"] is not None:
            if f in refs or not single or spec.get("type") not in e["enums"]:
                rep.error(fw, f"in: only for a single-valued enum attribute ('{f}' is {spec.get('type')}{'' if single else '[*]'})")
            else:
                lits = [lit["name"] for lit in e["enums"][spec["type"]]["literals"]]
                unknown = [x for x in o["in"] if x not in lits]
                if not o["in"]:
                    rep.error(fw, "in: at least one literal")
                elif unknown:
                    rep.error(fw, f"in: not literals of {spec['type']}: {', '.join(unknown)}")
                elif set(o["in"]) == set(lits):
                    rep.warn(fw, f"in: all the literals of {spec['type']}: the state adds nothing")
    required = {f for f, o in overlay.items() if o["lower"] == 1 and (attrs.get(f) or refs.get(f)) is not None}
    if required:
        ctx = X.Context(e, cname)
        for tn, t in transitions.items():
            if t.get("to") != sn or t.get("guard") is None:
                continue
            try:
                node, _ = X.check(str(t["guard"]), ctx, X.BOOL)
            except X.ExprError:
                continue
            repeated = sorted({n["segs"][0] for n in _walk(node)
                               if n.get("k") == "path" and n.get("call") in ("isSet", "notEmpty") and len(n.get("segs") or []) == 1
                               and n["segs"][0] in required})
            if repeated:
                rep.warn(f"{where}.requires", f"the guard of `{tn}` repeats {', '.join(repeated)}: `requires` already checks them on entering {sn}")
    # along the path: what the target asks must be reachable from the source (P3)
    for tn, t in transitions.items():
        if t.get("to") != sn:
            continue
        for src in t["from"]:
            if src == sn or src not in states:
                continue
            before = state_overlay(states[src])
            for f, o in overlay.items():
                spec = attrs.get(f) or refs.get(f)
                if spec is None or spec.get("derived"):
                    continue
                prev = before.get(f)
                fw = f"{where}.model.{f}"
                static_required = int(spec.get("lower") or 0) >= 1
                null_src = not static_required and (prev is None or prev["lower"] != 1)
                null_tgt = not static_required and o["lower"] != 1
                if (o["in"] is not None and prev is not None and prev["in"] is not None
                        and not (set(prev["in"]) & set(o["in"])) and not (null_src and null_tgt)):
                    rep.error(fw, f"'{f}' is {', '.join(prev['in'])} in {src} but {sn} allows only {', '.join(o['in'])}: `{tn}` can never fire")
                    continue
                if not prev or not prev["readonly"]:
                    continue
                if o["lower"] == 1 and null_src:
                    rep.warn(fw, f"'{f}' cannot be set in {src} but {sn} requires it (`{tn}`): require it before {src} or let {src} change it")
                if o["in"] is not None and (prev["in"] is None or not set(prev["in"]) <= set(o["in"])):
                    rep.warn(fw, f"'{f}' cannot be changed in {src} but {sn} allows only {', '.join(o['in'])} (`{tn}`)")

def _walk(node: Any):
    """Every dict of an expression tree, depth first."""
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def requires_tests(e: dict[str, Any], cname: str, s: dict[str, Any]) -> list[tuple[str, str]]:
    """Each feature a state requires (`requires`, `lower: 1` of its `model`) with the expression that tests it:
    `f.isSet()` for a single value, `f.notEmpty()` for a collection (unknown features are skipped: validate reports them)."""
    attrs, refs = E.features(e, cname)
    out: list[tuple[str, str]] = []
    for f in required_features(s):
        spec = attrs.get(f) or refs.get(f)
        if spec is not None:
            out.append((f, f"{f}.isSet()" if spec.get("upper", 1) == 1 else f"{f}.notEmpty()"))
    return out


def _check_reactions(b: dict[str, Any], e: dict[str, Any], rep: M.Report) -> None:
    names: set[str] = set()
    for i, r in enumerate(b["reactions"]):
        name = r.get("name")
        tn = r.get("_transition")
        if tn:                                   # the notification declared on a transition (notify/template)
            where = f"workflows.{str(r.get('event')).split('.')[0]}.transitions.{tn}.notify"
            if name in names:
                rep.error(where, f"the notification of transition `{tn}` is the reaction `{name}`: rename the reaction "
                                 "declared with that name")
            names.add(name)
        else:
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
        if r.get("when") is not None and not tn:          # a transition's own condition is checked with the transition
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


def template_uses(b: dict[str, Any]) -> dict[str, list[tuple[str, str, str]]]:
    """{template key: [(class, event, "reaction <name>" | "reminder of <state>")]}: where each notification text is used."""
    out: dict[str, list[tuple[str, str, str]]] = {}
    for r in b["reactions"]:
        on = str(r.get("event") or "")
        if r.get("template") and on.count(".") == 1:
            cname, event = on.split(".")
            used_by = f"transition {cname}.{r['_transition']}" if r.get("_transition") else f"reaction {r.get('name')}"
            out.setdefault(str(r["template"]), []).append((cname, event, used_by))
    for cname, w in b["workflows"].items():
        for sn, s in w["states"].items():
            rem = s.get("reminder")
            if rem:
                out.setdefault(str(rem.get("template") or f"{sn}_reminder"), []).append((cname, "reminder", f"reminder of {cname}.{sn}"))
    return out


def template_variables(b: dict[str, Any], cname: str, event: str) -> set[str]:
    """The event variables a text sent on `<cname>.<event>` may use (besides the record's own paths)."""
    allowed = set(TEMPLATE_VARS)
    w = b["workflows"].get(cname)
    if w:
        allowed |= STATE_VARS
        emitted = {ev for t in w["transitions"].values() for ev in t["emits"]}
        if event in ("transitioned", "completed") or event in emitted:
            allowed |= TRANSITION_VARS
        if event == "reminder":
            allowed |= REMINDER_VARS
    return allowed


def _check_templates(b: dict[str, Any], e: dict[str, Any], rep: M.Report) -> None:
    """`templates`: the texts of the notifications, per language, with placeholders on the record and the event.
    Without the section the subscriber renders the texts (said in the notation); with it, every template a reaction
    or a reminder names must have texts in the metamodel's language, and every placeholder must exist."""
    uses = template_uses(b)
    tpls = b["templates"]
    lang0 = e.get("language") or "it"
    if tpls:
        for key, where in uses.items():
            if key not in tpls:
                rep.warn(f"templates.{key}", f"no texts for template `{key}` (used by {', '.join(u[2] for u in where)}): add it to templates:")
    for key, langs in tpls.items():
        where = f"templates.{key}"
        if not IDENT.match(str(key)):
            rep.error(where, "template keys are lowercase identifiers (letters, digits, _)")
        if key not in uses:
            rep.warn(where, "not used by any reaction or reminder")
        if not langs:
            rep.error(where, "the texts per language: {it: {subject, body}}")
        elif lang0 not in langs:
            rep.warn(where, f"no texts in the language of the metamodel ({lang0})")
        for lang, tx in langs.items():
            lw = f"{where}.{lang}"
            if not LANG_RE.match(str(lang)):
                rep.error(lw, "a language code (it, en, …)")
            extra = set(tx) - TEMPLATE_KEYS
            if extra:
                rep.error(lw, f"unknown keys: {', '.join(sorted(map(str, extra)))} (allowed: subject, body)")
            if not tx.get("subject"):
                rep.error(lw, "subject: the subject of the message")
            for field in ("subject", "body"):
                for name in PLACEHOLDER.findall(tx.get(field) or ""):
                    _check_placeholder(b, e, name, uses.get(key, []), f"{lw}.{field}", rep)


def uses_url(raw: dict[str, Any]) -> bool:
    """Whether a notification text uses `{{url}}`: the application must then define `public.record_url(entity, id)`
    (one SQL map of its pages); the engine calls it when it exists, otherwise the placeholder renders empty."""
    return any("{{url}}" in (tx.get(field) or "") for langs in expand(raw)["templates"].values()
               for tx in langs.values() for field in ("subject", "body"))


def _check_placeholder(b: dict[str, Any], e: dict[str, Any], name: str, where: list[tuple[str, str, str]], fw: str, rep: M.Report) -> None:
    for cname, event, use in where:
        entity = M.snake(cname)
        if name in template_variables(b, cname, event):
            continue
        if "." in name and name.split(".", 1)[0] in ("self", entity):
            path = name.split(".", 1)[1]
            if path == "id":                                   # every record has an id (not a feature of the metamodel)
                continue
            try:
                _, t = X.check(path, X.Context(e, cname))
            except X.ExprError as exc:
                rep.error(fw, f"{{{{{name}}}}}: {exc}")
                continue
            if t.startswith(X.COLLECTION):
                rep.error(fw, f"{{{{{name}}}}}: a collection; a placeholder is a single value (size(), sum() or a path to one)")
            continue
        if name in TRANSITION_VARS:
            rep.error(fw, f"{{{{{name}}}}}: transition.* only on <Class>.transitioned, .completed or an event a transition emits ({use} is on {cname}.{event})")
        elif name in REMINDER_VARS:
            rep.error(fw, f"{{{{{name}}}}}: reminder.* only on <Class>.reminder ({use} is on {cname}.{event})")
        else:
            rep.error(fw, f"{{{{{name}}}}}: unknown placeholder; use {{{{self.<path>}}}} or {{{{{entity}.<path>}}}}, "
                          f"{', '.join(sorted(template_variables(b, cname, event)))}")


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
        "view_as": "**Vedi come**: chiunque può limitare la propria sessione a uno dei suoi ruoli; {who} possono usare l'app come un altro utente, con le azioni intestate all'utente reale (`impersonated_by`) e registrate (`view_as_log`).",
        "nobody": "nessuno",
        "scope_per": "per {cls}", "builtin_roles": "Oltre ai ruoli predefiniti `admin` (amministratori) e `creator` (chi ha creato il record).",
        "workflow": "Workflow di {cls}", "state_attr": "Lo stato è l'attributo `{attr}`.",
        "states": "Stati", "state": "Stato", "kind": "Tipo", "initial": "iniziale", "final": "finale",
        "owner": "In attesa di", "editable_by": "Modificabile da", "reminder": "Sollecito", "reminder_text": "dopo {after} (`{template}`)",
        "requires": "Richiede",
        "state_model": "Il metamodello per stato",
        "state_model_note": "Come la classe appare in ogni stato (`model` dello stato): ● richiesto, 🔒 sola lettura, ○ assente (non mostrato né modificabile, il valore resta), {a, b} valori ammessi; vuoto: come nel metamodello.",
        "transitions": "Transizioni", "transition": "Transizione", "from_to": "Da → A", "by": "Chi", "when": "Condizione",
        "guard": "Requisito", "comment": "Commento", "at": "Scadenza", "emits": "Eventi", "notifies": "Avvisa", "system": "sistema: {at}",
        "revert": "Ritorno a uno stato precedente: {by}; da uno stato finale: {final_by}; commento {comment}.",
        "comment_required": "obbligatorio", "comment_optional": "facoltativo",
        "derivations": "Attributi calcolati", "attribute": "Attributo", "formula": "Formula", "in_code": "*calcolato nel codice*",
        "events": "Eventi", "event": "Evento", "description": "Descrizione", "builtin_events": "predefinito",
        "lifecycle": "Ogni classe emette `created`, `updated`, `deleted`; una classe con workflow anche `transitioned`, `completed`, `reverted`, `reminder`.",
        "reactions": "Reazioni", "name": "Nome", "recipients": "Destinatari", "template": "Template", "notify": "notifica",
        "templates": "Testi delle notifiche", "templates_note": "Oggetto e corpo per lingua; i segnaposto `{{…}}` sono dati del record (`self.…`) e dell'evento (`transition.label`, `actor.name`, `comment`, `url`, `reminder.days`). Il motore li rende per destinatario; una riga di `notification_templates` (chiave × lingua) li sovrascrive.",
        "language": "Lingua", "subject": "Oggetto", "body": "Corpo",
        "subscriptions": "Sottoscrizioni", "url": "URL", "patterns": "Eventi",
        "involved": "Classi coinvolte nel comportamento", "feature": "Attributo o riferimento", "used_by": "Usato da",
        "involved_note": "Classi senza workflow di cui il comportamento legge o usa attributi e riferimenti (formule, condizioni, destinatari, ambiti dei ruoli).",
    },
    "en": {
        "title": "Behaviour of the domain {package}",
        "note": "Generated from `behavior.yaml` by `npm run model:sync`: the behaviour changes in the model, not here.",
        "roles": "Roles", "role": "Role", "label": "Label", "scope": "Scope", "scope_global": "global",
        "view_as": "**View as**: anyone may restrict their session to one of their roles; {who} may use the application as another user, with what they do attributed to the real user (`impersonated_by`) and logged (`view_as_log`).",
        "nobody": "nobody",
        "scope_per": "per {cls}", "builtin_roles": "Besides the built-in roles `admin` (administrators) and `creator` (who created the record).",
        "workflow": "Workflow of {cls}", "state_attr": "The state is the attribute `{attr}`.",
        "states": "States", "state": "State", "kind": "Kind", "initial": "initial", "final": "final",
        "owner": "Waiting for", "editable_by": "Editable by", "reminder": "Reminder", "reminder_text": "after {after} (`{template}`)",
        "requires": "Requires",
        "state_model": "The class as seen from each state",
        "state_model_note": "What the class looks like in every state (`model` of the state): ● required, 🔒 read only, ○ hidden (not shown nor editable, the value stays), {a, b} the allowed literals; empty: as in the metamodel.",
        "transitions": "Transitions", "transition": "Transition", "from_to": "From → To", "by": "Who", "when": "Condition",
        "guard": "Requirement", "comment": "Comment", "at": "Due", "emits": "Events", "notifies": "Notifies", "system": "system: {at}",
        "revert": "Back to a previous state: {by}; from a final state: {final_by}; comment {comment}.",
        "comment_required": "required", "comment_optional": "optional",
        "derivations": "Derived attributes", "attribute": "Attribute", "formula": "Formula", "in_code": "*computed in code*",
        "events": "Events", "event": "Event", "description": "Description", "builtin_events": "built in",
        "lifecycle": "Every class emits `created`, `updated`, `deleted`; a class with a workflow also `transitioned`, `completed`, `reverted`, `reminder`.",
        "reactions": "Reactions", "name": "Name", "recipients": "Recipients", "template": "Template", "notify": "notify",
        "templates": "Notification texts", "templates_note": "Subject and body per language; the placeholders `{{…}}` are data of the record (`self.…`) and of the event (`transition.label`, `actor.name`, `comment`, `url`, `reminder.days`). The engine renders them per recipient; a row of `notification_templates` (key × language) overrides them.",
        "language": "Language", "subject": "Subject", "body": "Body",
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


def overlay_mark(o: dict[str, Any] | None) -> str:
    """One cell of the feature × state table: ● required, 🔒 read only, ○ hidden, {a, b} the allowed literals."""
    if not o:
        return ""
    parts = []
    if o.get("lower") == 1:
        parts.append("●")
    if o.get("hidden"):
        parts.append("○")
    elif o.get("readonly"):
        parts.append("🔒")
    if o.get("in") is not None:
        parts.append("{" + ", ".join(o["in"]) + "}")
    return " ".join(parts)


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
    if b["view_as"] is not None:
        who = ", ".join(_code(p) for p in b["view_as"]["users_by"]) or t["nobody"]
        out += [t["view_as"].format(who=who), ""]
    for cname, w in b["workflows"].items():
        out += [f"## {t['workflow'].format(cls=cname)}", "", t["state_attr"].format(attr=w["state"]), "",
                "```mermaid", mermaid_workflow(w, lang).rstrip("\n"), "```", ""]
        rows = []
        for sn, s in w["states"].items():
            kind = t["initial"] if s["initial"] else t["final"] if s["final"] else ""
            rem = s.get("reminder")
            rem_text = t["reminder_text"].format(after=rem["after"], template=rem.get("template") or f"{sn}_reminder") if rem else ""
            rows.append([_code(sn), _lbl(s, sn, lang), kind, ", ".join(_code(p) for p in s["owner"]),
                         ", ".join(_code(p) for p in s["editable_by"]), ", ".join(_code(f) for f in required_features(s)), rem_text])
        out += [f"### {t['states']}", ""] + E._table(
            [t["state"], t["label"], t["kind"], t["owner"], t["editable_by"], t["requires"], t["reminder"]], rows) + [""]
        matrix = state_matrix(b, e, cname)
        if matrix:
            out += [f"### {t['state_model']}", "", t["state_model_note"], ""] + E._table(
                [t["feature"]] + [_lbl(s, sn, lang) for sn, s in w["states"].items()],
                [[_code(row["feature"])] + [overlay_mark(row["states"].get(sn)) for sn in w["states"]] for row in matrix]) + [""]
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
    explicit = [r for r in b["reactions"] if not r.get("_transition")]   # a transition's notification is in its row above
    if explicit:
        rows = [[_code(r["name"]), _code(r["event"]), _code(r.get("when")), ", ".join(_code(p) for p in r["notify"]), _code(r.get("template"))]
                for r in explicit]
        out += [f"## {t['reactions']}", ""] + E._table([t["name"], t["event"], t["when"], t["recipients"], t["template"]], rows) + [""]
    if b["subscriptions"]:
        rows = [[_code(s["name"]), _code(f"${s['url_env']}" if s.get("url_env") else s.get("url")), ", ".join(_code(p) for p in s["events"])]
                for s in b["subscriptions"]]
        out += [f"## {t['subscriptions']}", ""] + E._table([t["name"], t["url"], t["patterns"]], rows) + [""]
    if b["templates"]:
        cell = lambda x: str(x or "").replace("|", "\\|").replace("\n", "<br>")  # noqa: E731
        rows = [[_code(k), lang, cell(tx.get("subject")), cell(tx.get("body"))] for k, langs in b["templates"].items() for lang, tx in langs.items()]
        out += [f"## {t['templates']}", "", t["templates_note"], ""] + E._table([t["template"], t["language"], t["subject"], t["body"]], rows) + [""]
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
    `kind` says how (derivation, when, guard, at, by, owner, editable_by, requires, allowed, readonly, hidden, revert,
    notify, scope), `of` where
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
        attrs, refs = E.features(e, cname)
        for sn, s in w["states"].items():
            for p in s["owner"]:
                principal(p, cname, "owner", f"{cname}.{sn}")
            for p in s["editable_by"]:
                principal(p, cname, "editable_by", f"{cname}.{sn}")
            for f, o in state_overlay(s).items():
                if f not in attrs and f not in refs:
                    continue
                group = "attributes" if f in attrs else "references"
                if o["lower"] == 1:
                    add(cname, group, f, "requires", f"{cname}.{sn}")
                if o["in"] is not None:
                    add(cname, group, f, "allowed", f"{cname}.{sn}")
                if o["hidden"]:
                    add(cname, group, f, "hidden", f"{cname}.{sn}")
                elif o["readonly"]:
                    add(cname, group, f, "readonly", f"{cname}.{sn}")
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
        name = f"{cname}.{r['_transition']}" if r.get("_transition") else str(r.get("name") or ev)
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
        named = transition_reactions(b, e, cname)          # who is notified when each transition fires (both forms)
        by_name = {r.get("name"): r for r in b["reactions"]}
        tctx = context(e, b, cname, "transitioned")
        tsql = X.SqlContext(e, cname, variables={"transition": "(p_extra -> 'transition' ->> 'key')"})
        for tn, tr in w["transitions"].items():
            for key in ("when", "guard"):
                tr[key] = _typed(tr.get(key), ctx, sql_ctx, X.BOOL)
            tr["notify_when"] = _typed(tr.get("notify_when"), tctx, tsql, X.BOOL)
            tr["notifies"] = [{"name": n, "notify": list(by_name[n]["notify"]), "template": by_name[n].get("template"),
                               "own": bool(by_name[n].get("_transition"))} for n in named.get(tn, []) if n in by_name]
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
                       "editable_by": [principal_key(p) for p in s["editable_by"]], "requires": required_features(s),
                       "model": state_overlay(s),
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
    if node["k"] == "and":                       # `transition = x and <a condition of its own>`
        for item in node["items"]:
            keys = _transition_keys(item)
            if keys is not None:
                return keys
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


def _sql_lit(v: str) -> str:
    return "'" + str(v).replace("'", "''") + "'"


def state_columns(e: dict[str, Any], cname: str, s: dict[str, Any]) -> list[tuple[str, str, dict[str, Any]]]:
    """The single-valued features a state's overlay touches, with their stored column: [(feature, column, overlay)]
    (collections are checked only on entering, through `requires_tests`; unknown features are skipped)."""
    attrs, refs = E.features(e, cname)
    out = []
    for f, o in state_overlay(s).items():
        spec = attrs.get(f) or refs.get(f)
        if spec is None or spec.get("upper", 1) != 1 or spec.get("derived"):
            continue
        out.append((f, E.field_key(f, spec), o))
    return out


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
        attrs, refs = E.features(e, cname)
        for sn, s in w["states"].items():
            tests = requires_tests(e, cname, s)
            if tests:
                out.append(f"--   {sn}.requires: {', '.join(f for f, _ in tests)} (to enter the state, and while the record is there)")
            for f, text in tests:
                node, _ = X.check(text, ctx, X.BOOL)
                out.append(f"coalesce({X.to_sql(node, sql_ctx)}, false)  -- {f}")
            for f, col, o in state_columns(e, cname, s):
                if o["in"] is not None:
                    out.append(f"--   {sn}.{f} in: {', '.join(o['in'])} (to enter the state, and while the record is there)")
                    out.append(f"coalesce(r.{col} is null or r.{col} in ({', '.join(_sql_lit(E.literal_key(x)) for x in o['in'])}), false)  -- {f}")
            ro = [(f, col) for f, col, o in state_columns(e, cname, s) if o["readonly"]]
            if ro:
                out.append(f"--   {sn}: read only: {', '.join(f for f, _ in ro)} (an update that changes them is refused while the record is there)")
            for f, col in ro:
                out.append(f"new.{col} is distinct from old.{col}  -- {f}")
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
