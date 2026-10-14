"""Mapping between the concepts of the model and the UI components of the generated app.

Every field gets a widget and every entity a set of views by a deterministic default
mapping (type, constraints, relations, workflow). `entities.<Entity>.ui` in app.yaml
overrides it; `suggest()` proposes alternatives that fit the model (calendar for
date ranges, kanban for workflows and status enums, cards for entities with images,
related panels for inverse references ...). The generic pages of the app render
whatever src/lib/model.ts says, so the mapping is the only thing to change.
"""

from __future__ import annotations

import re
from typing import Any

from . import model as M

# widget -> field types it can render
WIDGETS: dict[str, set[str]] = {
    "text": {"string"}, "textarea": {"string", "text"}, "email": {"email"}, "url": {"url"}, "image": {"url"},
    "number": {"int", "number", "money"}, "slider": {"int", "number"}, "currency": {"money", "number"},
    "checkbox": {"bool"}, "switch": {"bool"}, "date": {"date"}, "datetime": {"datetime"},
    "select": {"enum"}, "radio": {"enum"}, "ref-select": {"ref"}, "ref-checklist": {"ref"}, "json": {"json"},
    "tags": {"json"},
}
VIEWS = ("table", "cards", "kanban", "calendar")
UI_KEYS = {"view", "views", "widgets", "kanban", "calendar", "cards", "related"}

IMAGE_NAME = re.compile(r"(^|_)(photo|image|picture|avatar|logo|foto|immagine|icona)(_|$)")
LONG_TEXT_NAME = re.compile(r"(^|_)(description|notes?|descrizione|note|testo|body|abstract|bio)(_|$)")
STATUS_NAME = re.compile(r"(^|_)(status|stato|fase|phase|stage|priority|priorita|livello|level)(_|$)")
START_NAME = re.compile(r"(^|_)(start|starts|begin|from|inizio|dal|data_inizio|valid_from|check_in|arrival)(_|$)")
END_NAME = re.compile(r"(^|_)(end|ends|until|to|fine|al|data_fine|valid_until|check_out|departure|due|scadenza)(_|$)")
DAY_NAME = re.compile(r"^(date|data|day|giorno|when|quando|scheduled_(at|on)|starts_at)$")


def default_widget(m: dict[str, Any], f: dict[str, Any]) -> str:
    t = f["type"]
    if t == "ref":
        return "ref-checklist" if f["many"] else "ref-select"
    if t == "enum":
        n = len(m["enums"].get(f["enum"], {}).get("values", []))
        return "radio" if 0 < n <= 4 else "select"
    if t == "url":
        return "image" if IMAGE_NAME.search(f["key"]) else "url"
    if t in ("int", "number"):
        if f["min"] is not None and f["max"] is not None and 0 < float(f["max"]) - float(f["min"]) <= 20:
            return "slider"
        return "number"
    return {"string": "text", "text": "textarea", "email": "email", "money": "currency", "bool": "switch",
            "date": "date", "datetime": "datetime", "json": "json"}.get(t, "text")


def _inverse_refs(m: dict[str, Any], name: str) -> list[dict[str, Any]]:
    """Fields of other entities that point to `name` (single references)."""
    out = []
    for other, e in m["entities"].items():
        for f in e["fields"].values():
            if f["type"] == "ref" and f["to"] == name and not f["many"]:
                out.append({"entity": e["snake"], "name": other, "field": f["key"], "cascade": f["on_delete"] == "cascade"})
    return out


def _date_range(e: dict[str, Any]) -> dict[str, str] | None:
    dates = [f for f in e["fields"].values() if f["type"] in ("date", "datetime")]
    start = next((f for f in dates if START_NAME.search(f["key"])), None)
    if start:
        end = next((f for f in dates if f is not start and END_NAME.search(f["key"])), None)
        return {"start": start["key"], **({"end": end["key"]} if end else {})}
    day = next((f for f in dates if DAY_NAME.match(f["key"])), None)
    return {"start": day["key"]} if day else None


def apply_defaults(m: dict[str, Any]) -> None:
    """Fills entities[*]['ui'] with the effective mapping (defaults + overrides). Never raises."""
    for name, e in m["entities"].items():
        spec = e.get("ui_spec") or {}
        spec = spec if isinstance(spec, dict) else {}
        widgets_in = spec.get("widgets") if isinstance(spec.get("widgets"), dict) else {}
        widgets = {k: str(widgets_in.get(k) or default_widget(m, f)) for k, f in e["fields"].items()}
        views = [str(v) for v in M._as_list(spec.get("views"))] or (["table", "kanban"] if e["workflow"] else ["table"])
        view = str(spec.get("view") or views[0])
        if view not in views:
            views = [view] + views
        kanban = spec.get("kanban") if isinstance(spec.get("kanban"), dict) else {}
        group_by = kanban.get("group_by") or ("state" if e["workflow"] else None)
        if "kanban" in views and not group_by:
            group_by = next((k for k, f in e["fields"].items() if f["type"] == "enum"), None)
        calendar = spec.get("calendar") if isinstance(spec.get("calendar"), dict) else None
        if "calendar" in views and not calendar:
            calendar = _date_range(e)
        cards = spec.get("cards") if isinstance(spec.get("cards"), dict) else {}
        image = cards.get("image") or next((k for k, w in widgets.items() if w == "image"), None)
        related_in = spec.get("related")
        inverse = _inverse_refs(m, name)
        if related_in is False:
            related = []
        elif related_in is None:   # containment (cascade) children are shown on the parent by default
            related = [{"entity": r["entity"], "field": r["field"]} for r in inverse if r["cascade"]]
        else:
            related = []
            for item in M._as_list(related_in):
                if isinstance(item, str):   # "Entity.field" or "Entity" (its only reference to us)
                    ent_name, _, fld = item.partition(".")
                    match = [r for r in inverse if r["name"] == ent_name and (not fld or r["field"] == fld)]
                    related += [{"entity": r["entity"], "field": r["field"]} for r in match[:1]] or [{"entity": "?" + item, "field": fld}]
        e["ui"] = {
            "view": view, "views": views, "widgets": widgets,
            "kanban": {"group_by": group_by} if "kanban" in views else None,
            "calendar": calendar if "calendar" in views else None,
            "cards": {"title": cards.get("title") or e["display"], "subtitle": cards.get("subtitle"), "image": image}
            if "cards" in views else None,
            "related": related,
        }


def validate(m: dict[str, Any], rep: M.Report) -> None:
    for name, e in m["entities"].items():
        where = f"entities.{name}.ui"
        spec = e.get("ui_spec")
        if spec is None:
            continue
        if not isinstance(spec, dict):
            rep.error(where, "must be a mapping")
            continue
        bad = set(spec) - UI_KEYS
        if bad:
            rep.error(where, f"unknown keys: {', '.join(sorted(bad))} (allowed: {', '.join(sorted(UI_KEYS))})")
        ui = e["ui"]
        for v in ui["views"]:
            if v not in VIEWS:
                rep.error(where, f"unknown view '{v}' ({', '.join(VIEWS)})")
        for k, w in (spec.get("widgets") or {}).items():
            f = e["fields"].get(k)
            if not f:
                rep.error(f"{where}.widgets", f"unknown field '{k}'")
            elif w not in WIDGETS:
                rep.error(f"{where}.widgets.{k}", f"unknown widget '{w}' ({', '.join(sorted(WIDGETS))})")
            elif f["type"] not in WIDGETS[w]:
                ok = sorted(x for x, types in WIDGETS.items() if f["type"] in types)
                rep.error(f"{where}.widgets.{k}", f"'{w}' cannot render a {f['type']} field (use {', '.join(ok)})")
        if ui["kanban"] is not None:
            g = ui["kanban"]["group_by"]
            if not g:
                rep.error(where, "kanban needs `kanban: {group_by: <enum field>}` (or a workflow)")
            elif g != "state" and (g not in e["fields"] or e["fields"][g]["type"] != "enum"):
                rep.error(f"{where}.kanban.group_by", f"'{g}' must be 'state' (workflow) or an enum field")
            elif g == "state" and not e["workflow"]:
                rep.error(f"{where}.kanban.group_by", "'state' requires a workflow")
        if ui["calendar"] is not None or "calendar" in ui["views"]:
            cal = ui["calendar"] or {}
            if not cal.get("start"):
                rep.error(where, "calendar needs `calendar: {start: <date field>, end: <date field>}`")
            for k in ("start", "end"):
                if cal.get(k) and (cal[k] not in e["fields"] or e["fields"][cal[k]]["type"] not in ("date", "datetime")):
                    rep.error(f"{where}.calendar.{k}", f"'{cal[k]}' is not a date/datetime field")
        if ui["cards"]:
            for k in ("title", "subtitle", "image"):
                v = ui["cards"].get(k)
                if v and v not in e["fields"] and v not in ("code", "id"):
                    rep.error(f"{where}.cards.{k}", f"unknown field '{v}'")
        for r in ui["related"]:
            if r["entity"].startswith("?"):
                rep.error(f"{where}.related", f"'{r['entity'][1:]}' does not reference {name}")


def suggest(m: dict[str, Any]) -> list[dict[str, Any]]:
    """Alternative components that fit the model. Each: entity, what, why, ui (snippet to merge)."""
    out: list[dict[str, Any]] = []
    for name, e in m["entities"].items():
        ui = e["ui"]
        views = ui["views"]
        rng = _date_range(e)
        if rng and "calendar" not in views:
            why = (f"{rng['start']} → {rng['end']} is a date range" if rng.get("end") else f"{rng['start']} is the day of the record")
            out.append({"entity": name, "what": "calendar view", "why": why,
                        "ui": {"views": views + ["calendar"], "calendar": rng}})
        if not e["workflow"] and "kanban" not in views:
            st = next((k for k, f in e["fields"].items() if f["type"] == "enum" and STATUS_NAME.search(k)), None)
            if st:
                out.append({"entity": name, "what": f"kanban by {st}", "why": f"{st} is a status-like enum: columns per value",
                            "ui": {"views": views + ["kanban"], "kanban": {"group_by": st}}})
        if e["workflow"] and ui["view"] != "kanban" and len(e["workflow"]["states"]) >= 3:
            out.append({"entity": name, "what": "kanban as the default view",
                        "why": f"{len(e['workflow']['states'])} workflow states: the board shows where each record is",
                        "ui": {"view": "kanban"}})
        image = next((k for k, w in ui["widgets"].items() if w == "image"), None)
        has_email = any(f["type"] == "email" for f in e["fields"].values())
        if "cards" not in views and (image or (has_email and len(e["fields"]) <= 8)):
            out.append({"entity": name, "what": "cards view",
                        "why": f"{image} is an image" if image else "a contact-like record (name and email)",
                        "ui": {"views": views + ["cards"], "cards": {"title": e["display"], **({"image": image} if image else {})}}})
        shown = {(r["entity"], r["field"]) for r in ui["related"]}
        for r in _inverse_refs(m, name):
            if (r["entity"], r["field"]) not in shown:
                out.append({"entity": name, "what": f"related {r['name']} on the detail page",
                            "why": f"{r['name']}.{r['field']} references {name}",
                            "ui": {"related": [f"{x['name']}.{x['field']}" for x in _inverse_refs(m, name)
                                               if (x["entity"], x["field"]) in shown
                                               or (x["entity"], x["field"]) == (r["entity"], r["field"])]}})
        for k, f in e["fields"].items():
            w = ui["widgets"][k]
            if f["type"] == "string" and w == "text" and LONG_TEXT_NAME.search(k):
                out.append({"entity": name, "what": f"textarea for {k}", "why": f"{k} reads like free text",
                            "ui": {"widgets": {k: "textarea"}}})
            if f["type"] == "enum" and w == "select":
                n = len(m["enums"].get(f["enum"], {}).get("values", []))
                if n <= 6:
                    out.append({"entity": name, "what": f"radio buttons for {k}", "why": f"{n} values fit on one line",
                                "ui": {"widgets": {k: "radio"}}})
            if f["type"] == "ref" and f["many"] and w == "ref-checklist":
                target = m["entities"].get(f["to"])
                if target and target["kind"] == "process":
                    out.append({"entity": name, "what": f"searchable multi-select for {k}",
                                "why": f"{f['to']} records grow over time: a checklist becomes long",
                                "ui": {"widgets": {k: "ref-select"}}})
            if f["type"] in ("int", "number") and w == "number" and f["min"] is not None and f["max"] is not None:
                out.append({"entity": name, "what": f"slider for {k}", "why": f"bounded between {f['min']} and {f['max']}",
                            "ui": {"widgets": {k: "slider"}}})
    return out


def describe(m: dict[str, Any]) -> str:
    lines = []
    for name, e in m["entities"].items():
        ui = e["ui"]
        lines.append(f"{name}: views {', '.join(ui['views'])} (default {ui['view']})"
                     + (f"; kanban by {ui['kanban']['group_by']}" if ui["kanban"] else "")
                     + (f"; calendar {ui['calendar']}" if ui["calendar"] else ""))
        for k, w in ui["widgets"].items():
            f = e["fields"][k]
            mark = "" if w == default_widget(m, f) else "  (override)"
            lines.append(f"   {k:<24} {f['type'] + ('[]' if f['many'] else ''):<10} → {w}{mark}")
        for r in ui["related"]:
            lines.append(f"   related: {r['entity']} via {r['field']}")
    return "\n".join(lines)
