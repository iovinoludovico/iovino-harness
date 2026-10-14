"""Claude Code hooks.

pre  (PreToolUse on Edit|Write|MultiEdit|NotebookEdit): blocks edits of files
     owned by the generator (artefacts and generated migrations listed in
     .appforge/lock.json, and the lock itself). Exit 2 = block, stderr goes to Claude.
post (PostToolUse on Edit|Write|MultiEdit): when app.yaml changes, validates it
     and reports errors back to Claude (exit 2) so they are fixed at once.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _input() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def _project_of(path: Path) -> Path | None:
    for d in [path.parent, *path.parent.parents]:
        if (d / "app.yaml").exists() and (d / ".appforge").exists():
            return d
    return None


def pre(data: dict) -> int:
    fp = (data.get("tool_input") or {}).get("file_path") or (data.get("tool_input") or {}).get("notebook_path")
    if not fp:
        return 0
    path = Path(fp)
    if not path.is_absolute():
        path = Path(data.get("cwd") or ".") / path
    path = path.resolve()
    root = _project_of(path)
    if not root:
        return 0
    rel = str(path.relative_to(root))
    if rel == ".appforge/lock.json":
        print("appforge: .appforge/lock.json is written only by the generator. Run /appforge:generate.", file=sys.stderr)
        return 2
    lock_file = root / ".appforge" / "lock.json"
    if not lock_file.exists():
        return 0
    lock = json.loads(lock_file.read_text(encoding="utf-8"))
    owned = set(lock.get("generated", {})) | set(lock.get("migrations", {}))
    if rel in owned:
        what = "a generated migration (migrations are immutable)" if rel.startswith("supabase/migrations/") else "a generated file"
        print(f"appforge: {rel} is {what}. Change app.yaml and run /appforge:generate, "
              "or put hand-written logic in a new migration / in a non-generated file "
              "(see the appforge-architecture skill, 'Where code goes').", file=sys.stderr)
        return 2
    return 0


def _adopted_schema_change(fp: str, data: dict) -> int:
    """Adopted (hand-written) app: a schema change must be reflected in the metamodel."""
    path = Path(fp)
    if not path.is_absolute():
        path = Path(data.get("cwd") or ".") / path
    for d in path.resolve().parents:
        if (d / "domain.ecore.yaml").exists():
            if (d / ".appforge" / "lock.json").exists():
                return 0     # generated app: migrations come from the model
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": ("appforge: this migration changes the database of an app described by "
                                      f"{d / 'domain.ecore.yaml'}. Keep them aligned: update the metamodel in the same "
                                      "change and check with `appforge metamodel drift --db <local DSN>`."),
            }}))
            return 0
    return 0


def post(data: dict) -> int:
    fp = (data.get("tool_input") or {}).get("file_path")
    if fp and "supabase/migrations/" in fp.replace("\\", "/") and fp.endswith(".sql"):
        return _adopted_schema_change(fp, data)
    if not fp or not fp.endswith(("app.yaml", "app.yml", "domain.ecore.yaml")):
        return 0
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from appforge import ecore as E  # noqa: WPS433
    from appforge import model as M  # noqa: WPS433

    path = Path(fp)
    if not path.is_absolute():
        path = Path(data.get("cwd") or ".") / path
    try:
        if path.name == "domain.ecore.yaml":
            app = path.parent / "app.yaml"
            if app.exists():
                _, rep = M.load_and_validate(app)
            else:
                rep = E.validate(E.load(path))
            if not rep.ok:
                print("appforge: domain.ecore.yaml is not valid — fix it:\n" + rep.render(), file=sys.stderr)
                return 2
            print("appforge: metamodel valid. Review it with `appforge metamodel show --format emfatic`; "
                  "then /appforge:generate (generated apps) or implement the changes (adopted apps).", file=sys.stderr)
            return 0
        _, rep = M.load_and_validate(path)
    except M.ModelError as exc:
        print(f"appforge: {exc}", file=sys.stderr)
        return 2
    if not rep.ok:
        print("appforge: app.yaml is not valid — fix it before generating:\n" + rep.render(), file=sys.stderr)
        return 2
    if rep.warnings:
        print("appforge: app.yaml valid, with warnings:\n" + "\n".join(rep.warnings), file=sys.stderr)
    return 0


def session(data: dict) -> int:
    """SessionStart: when the session opens inside an appforge app, print its state as context."""
    cwd = Path(data.get("cwd") or ".").resolve()
    root = None
    for d in [cwd, *cwd.parents]:
        if (d / "app.yaml").exists() and (d / ".appforge").exists():
            root = d
            break
    if not root:
        meta = next((d / "domain.ecore.yaml" for d in [cwd, *cwd.parents] if (d / "domain.ecore.yaml").exists()), None)
        if meta:
            print(f"Adopted app with an appforge metamodel: {meta}. The app is hand-written: change the metamodel with "
                  "/appforge:metamodel, then implement migrations and code by hand and check with "
                  "`appforge metamodel drift --db <local DSN>`.")
            dsn = os.environ.get("APPFORGE_DRIFT_DB")
            if dsn:   # e.g. the local Supabase: postgresql://postgres:postgres@127.0.0.1:54322/postgres
                sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
                try:
                    from appforge import dbschema as D, ecore as E  # noqa: WPS433
                    found = D.drift(E.load(meta), D.catalog(dsn))
                    print("Metamodel and database aligned." if not found else
                          "DRIFT between metamodel and database:\n" + "\n".join(f"- {x}" for x in found[:30]))
                except Exception as exc:  # never break a session
                    print(f"(drift check skipped: {exc})")
        return 0
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from appforge import project as P  # noqa: WPS433

    try:
        st = P.status(root)
    except Exception as exc:  # never break a session
        print(f"appforge app at {root} (status unavailable: {exc})")
        return 0
    lines = [f"appforge app: {st.get('name')} ({st.get('slug')}) at {root}; evolution #{st.get('evolution', '-')}.",
             ("The domain structure is domain.ecore.yaml (Ecore metamodel: /appforge:metamodel); behaviour is app.yaml. "
              if (root / "domain.ecore.yaml").exists() else
              "The domain model is app.yaml (single file: `appforge metamodel extract` splits it into domain.ecore.yaml + app.yaml). ")
             + "Run /appforge:generate after model changes; generated files are protected."]
    lines += [f"note: {n}" for n in st["notes"]] + [f"problem: {p}" for p in st["problems"]]
    print("\n".join(lines))
    return 0


def main() -> int:
    mode = sys.argv[2] if len(sys.argv) > 2 else "pre"
    data = _input()
    return {"pre": pre, "post": post, "session": session}[mode](data)
