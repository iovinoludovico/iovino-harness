"""Command line interface: python3 scripts/appforge.py <command> ...

Every command prints plain text for people and agents; --json prints machine
readable output. Exit code 0 = ok, 1 = problems found, 2 = usage/model error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import model as M
from . import project as P
from .dbschema import DbError


def _print(obj, as_json: bool) -> None:
    if as_json:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))
    elif isinstance(obj, str):
        print(obj)
    else:
        print(json.dumps(obj, ensure_ascii=False, indent=2, default=str))


def cmd_validate(a) -> int:
    path = Path(a.model) if a.model and a.model.endswith((".yaml", ".yml", ".json")) else P.resolve_app(a.model) / P.MODEL_FILE
    m, rep = M.load_and_validate(path)
    if a.json:
        _print({"ok": rep.ok, "errors": rep.errors, "warnings": rep.warnings}, True)
    else:
        print(rep.render())
    return 0 if rep.ok else 1


def cmd_new(a) -> int:
    target = Path(a.dir)
    written = P.scaffold(target, Path(a.model) if a.model else None, force=a.force)
    res = P.generate(target)
    P.register(target)
    if a.json:
        _print({"scaffolded": len(written), **res}, True)
        return 0
    print(f"Scaffolded {len(written)} files in {target.resolve()}")
    _print_generate(res)
    print("\nNext: cd into the app, `npm install`, `supabase start`, `supabase db reset`, `npm run db:types`, `npm run dev`.")
    return 0


def _print_generate(res) -> None:
    for op in res["ops"]:
        print(f"  • {op}")
    for mg in res["migrations"]:
        print(f"  + {mg}")
    for f in res["files"]:
        print(f"  ~ {f}")
    for w in res.get("warnings", []):
        print(f"  ! {w}")
    if res.get("manual"):
        print("\nMANUAL STEPS REQUIRED: complete the *_manual_evolve_* migration (TODO(appforge) sections):")
        for op in res["manual"]:
            print(f"  - {op['op']} {op['target']}: {op['why']}")


def cmd_generate(a) -> int:
    root = P.resolve_app(a.app)
    res = P.generate(root, dry_run=a.dry_run, rebuild_behavior=a.rebuild_behavior)
    if a.json:
        _print(res, True)
        return 0
    print(("Dry run for " if a.dry_run else "Generated ") + str(root))
    if a.dry_run:
        for op in res["ops"]:
            print(f"  • {op}")
        for mg in res["migrations"]:
            print(f"\n===== {mg['path']} =====\n{mg['text'][:4000]}{'…' if len(mg['text']) > 4000 else ''}")
        return 0
    _print_generate(res)
    return 0


def cmd_status(a) -> int:
    root = P.resolve_app(a.app)
    st = P.status(root)
    if a.json:
        _print(st, True)
    else:
        print(f"{st.get('name', '?')} ({st.get('slug', '?')}) — {st['path']}")
        if st.get("generated"):
            print(f"  evolution #{st['evolution']}, generator {st['generator_version']}, last generated {st['last_generated']}")
        for n in st["notes"]:
            print(f"  · {n}")
        for p in st["problems"]:
            print(f"  ✗ {p}")
        if not st["problems"] and not st["notes"]:
            print("  ✓ up to date")
    return 1 if st["problems"] else 0


def cmd_check(a) -> int:
    root = P.resolve_app(a.app)
    rc = cmd_status(argparse.Namespace(app=str(root), json=False))
    if a.db:
        ok, log = P.check_db(root)
        print("\nDatabase check (scratch PostgreSQL + Supabase stubs):")
        print("  " + log.replace("\n", "\n  "))
        rc = rc or (0 if ok else 1)
    return rc


def cmd_apps(a) -> int:
    reg = P.read_registry()
    if a.action == "add":
        root = P.find_project(a.target or ".")
        e = P.register(root)
        print(f"registered {e['slug']} → {e['path']}")
        return 0
    if a.action == "remove":
        ok = P.unregister(a.target)
        print("removed" if ok else f"unknown app {a.target}")
        return 0 if ok else 1
    if a.action == "show":
        root = P.resolve_app(a.target)
        st = P.status(root)
        _print({**reg["apps"].get(st.get("slug", ""), {}), **st}, True)
        return 0
    rows = []
    for slug, e in sorted(reg["apps"].items()):
        p = Path(e["path"])
        if not (p / P.MODEL_FILE).exists():
            rows.append({**e, "state": "missing"})
            continue
        st = P.status(p)
        state = "problems" if st["problems"] else ("model changed" if st.get("model_changed") else ("not generated" if not st.get("generated") else "up to date"))
        rows.append({**e, "state": state, "evolution": st.get("evolution"), "problems": st["problems"]})
    if a.json:
        _print(rows, True)
        return 0
    if not rows:
        print(f"No app registered yet ({P.registry_path()}). Create one with /appforge:new-app.")
        return 0
    for r in rows:
        print(f"{r['slug']:<28} {r['state']:<14} evo #{r.get('evolution', '-')!s:<3} {r['path']}")
    return 0


def cmd_describe(a) -> int:
    root = P.resolve_app(a.app)
    m = M.normalize(M.load(root / P.MODEL_FILE))
    loc = m["app"]["locales"][0]
    lines = [f"{m['app']['name']} ({m['app']['slug']}) — locales {', '.join(m['app']['locales'])}",
             "roles: " + ", ".join(f"{k}{'*' if r['scoped'] else ''}" for k, r in m["roles"].items()) + "   (* scoped)"]
    for name, e in m["entities"].items():
        fl = ", ".join(f"{k}:{f['type']}{('→' + f['to']) if f['to'] else ''}{'[]' if f['many'] else ''}{'!' if f['required'] else ''}"
                       for k, f in e["fields"].items())
        lines.append(f"{name} [{e['kind']}] table={e['table']}: {fl}")
        if e["workflow"]:
            st = " → ".join(e["workflow"]["states"])
            lines.append(f"   states: {st}")
            for k, t in e["workflow"]["transitions"].items():
                lines.append(f"   {k}: {','.join(t['from'])} → {t['to']} by {','.join(t['by']) or t['trigger']['kind']}")
    lines.append("events: " + ", ".join(sorted(M.all_events(m))))
    for r in m["reactions"]:
        lines.append(f"reaction {r['name']}: on {r.get('on')} do {r.get('do')}")
    print("\n".join(lines))
    return 0


def cmd_ui(a) -> int:
    from . import ui as U
    root = P.resolve_app(a.app)
    m, rep = M.load_and_validate(root / P.MODEL_FILE)
    if a.action == "show":
        print(U.describe(m))
        return 0
    sugg = U.suggest(m)
    if a.json:
        _print(sugg, True)
        return 0
    if not sugg:
        print("No suggestion: the mapping already fits the model.")
        return 0
    for i, s_ in enumerate(sugg, 1):
        print(f"{i}. {s_['entity']}: {s_['what']} — {s_['why']}")
        snippet = M.dumps({"entities": {s_["entity"]: {"ui": s_["ui"]}}}).rstrip()
        print("   " + snippet.replace("\n", "\n   "))
    print("\nApply a suggestion by merging its `ui` into app.yaml (or ask /appforge:ui), then /appforge:generate.")
    return 0


def cmd_studio(a) -> int:
    from . import studio
    return studio.serve(port=a.port, app=a.app, open_browser=not a.no_browser)


def cmd_guard(a) -> int:
    """Hook helper: exit 2 (block) if the path is a generated file of a project."""
    from . import guard
    return guard.main()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="appforge", description="Model-driven application generator")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("validate", help="validate a model (app.yaml, path or app slug)")
    s.add_argument("model", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("new", help="scaffold a new application and generate it")
    s.add_argument("dir")
    s.add_argument("--model", help="model file to copy into the app (default: <dir>/app.yaml)")
    s.add_argument("--force", action="store_true")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("generate", help="generate migrations and artefacts from the model")
    s.add_argument("app", nargs="?")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--rebuild-behavior", action="store_true", help="emit a behaviour-only migration even if the model is unchanged")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_generate)

    s = sub.add_parser("status", help="state of an app (model vs lock, edited generated files, i18n)")
    s.add_argument("app", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_status)

    s = sub.add_parser("check", help="status + apply every migration to a scratch database")
    s.add_argument("app", nargs="?")
    s.add_argument("--db", action="store_true")
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("apps", help="registry of generated apps")
    s.add_argument("action", nargs="?", default="list", choices=["list", "add", "remove", "show"])
    s.add_argument("target", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_apps)

    s = sub.add_parser("describe", help="compact summary of the model")
    s.add_argument("app", nargs="?")
    s.set_defaults(fn=cmd_describe)

    s = sub.add_parser("ui", help="UI mapping of the model: show the effective widgets/views, suggest alternatives")
    s.add_argument("action", choices=["show", "suggest"])
    s.add_argument("app", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_ui)

    s = sub.add_parser("studio", help="graphical model editor and app manager (local web UI)")
    s.add_argument("--port", type=int, default=4321)
    s.add_argument("--app")
    s.add_argument("--no-browser", action="store_true")
    s.set_defaults(fn=cmd_studio)

    from . import mmcli
    mmcli.add_parser(sub)

    s = sub.add_parser("guard", help="(hook) pre: block edits of generated files; post: validate app.yaml")
    s.add_argument("mode", choices=["pre", "post", "session"])
    s.set_defaults(fn=cmd_guard)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.fn(args)
    except (M.ModelError, P.ProjectError) as exc:
        print(f"appforge: {exc}", file=sys.stderr)
        return 2
    except DbError as exc:
        print(f"appforge: database: {exc}", file=sys.stderr)
        return 2
