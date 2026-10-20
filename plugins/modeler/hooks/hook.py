"""Claude Code hooks of the modeler plugin (Python standard library only; never break a session).

post    (PostToolUse on Edit|Write|MultiEdit): domain.ecore.yaml changed -> validate it, and behavior.yaml
        against it (exit 2 sends the errors back to Claude); behavior.yaml changed -> validate it against the
        metamodel; a migration changed in an app with a metamodel -> remind to keep them aligned.
session (SessionStart): inside an app with a metamodel, describe how it is kept aligned, report a vendored
        modeler older than the plugin and, with MODELER_DRIFT_DB set, the drift from the database.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
METAMODEL_FILE = "domain.ecore.yaml"
BEHAVIOR_FILE = "behavior.yaml"


def _input() -> dict:
    try:
        return json.load(sys.stdin)
    except Exception:
        return {}


def _path(fp: str, data: dict) -> Path:
    p = Path(fp)
    return (p if p.is_absolute() else Path(data.get("cwd") or ".") / p).resolve()


def _app_root(start: Path) -> Path | None:
    for d in [start, *start.parents]:
        if (d / METAMODEL_FILE).exists():
            return d
    return None


def _context(event: str, text: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"hookEventName": event, "additionalContext": text}}))


def post(data: dict) -> int:
    fp = (data.get("tool_input") or {}).get("file_path")
    if not fp:
        return 0
    path = _path(fp, data)
    norm = str(path).replace("\\", "/")
    if "/supabase/migrations/" in norm and norm.endswith(".sql") and not norm.endswith("_model_change_requests.sql"):
        root = _app_root(path.parent)
        if root:
            _context("PostToolUse", f"modeler: this migration changes the database of an app described by "
                                    f"{root / METAMODEL_FILE}. Update the metamodel in the same change, then "
                                    "`npm run model:sync` and, after applying the migration locally, `npm run model:drift`.")
        return 0
    if path.name == "BEHAVIOR.md" and path.parent.name == "docs" and _app_root(path.parent.parent):
        _context("PostToolUse", f"modeler: docs/BEHAVIOR.md is generated from {BEHAVIOR_FILE} (`npm run model:sync`) and "
                                f"rewritten every time: the change belongs in {BEHAVIOR_FILE}.")
        return 0
    if path.name == "DOMAIN.md" and path.parent.name == "docs" and _app_root(path.parent.parent):
        _context("PostToolUse", "modeler: docs/DOMAIN.md is generated from domain.ecore.yaml (`npm run model:sync`). "
                                "If this is the user's note to translate, leave it; otherwise the change belongs in "
                                "domain.ecore.yaml (structure, or `rules` for constraints), then "
                                "`npm run model:sync -- --force` regenerates the file.")
        return 0
    if path.name == BEHAVIOR_FILE and (path.parent / METAMODEL_FILE).exists():
        return _check_behavior(path.parent / METAMODEL_FILE, path, changed="behavior")
    if path.name != METAMODEL_FILE:
        return 0
    sys.path.insert(0, str(SCRIPTS))
    from metamodel import core as M, ecore as E  # noqa: E402

    try:
        rep = E.validate(E.load(path))
    except M.ModelError as exc:
        print(f"modeler: {exc}", file=sys.stderr)
        return 2
    if not rep.ok:
        print(f"modeler: {METAMODEL_FILE} is not valid — fix it:\n" + rep.render(), file=sys.stderr)
        return 2
    if (path.parent / BEHAVIOR_FILE).exists():
        code = _check_behavior(path, path.parent / BEHAVIOR_FILE, changed="metamodel")
        if code:
            return code
    _context("PostToolUse", "modeler: metamodel valid. Next, in the same change: the migration "
                            "(`npm run model:migrate -- --name <name> --write`, then resolve its TODO(modeler) lines), "
                            "`npm run model:sync` "
                            "(refreshes the admin modeler and docs/DOMAIN.md), the code that uses the new structure, "
                            "`npm run model:drift`.")
    return 0


def _check_behavior(meta: Path, behavior: Path, changed: str) -> int:
    """behavior.yaml against the metamodel: errors go back to Claude (exit 2)."""
    sys.path.insert(0, str(SCRIPTS))
    from metamodel import behavior as B, core as M, ecore as E  # noqa: E402

    try:
        meta_raw = E.load(meta)
        if not E.validate(meta_raw).ok:
            return 0                                     # the metamodel's own errors are reported by its edit
        rep = B.validate(B.load(behavior), meta_raw)
    except M.ModelError as exc:
        print(f"modeler: {BEHAVIOR_FILE}: {exc}", file=sys.stderr)
        return 2
    if not rep.ok:
        head = (f"modeler: this change of {METAMODEL_FILE} breaks {BEHAVIOR_FILE} — update the behaviour in the same change "
                "(or revert the domain change):" if changed == "metamodel"
                else f"modeler: {BEHAVIOR_FILE} is not valid against {METAMODEL_FILE} — fix it:")
        print(head + "\n" + rep.render(), file=sys.stderr)
        return 2
    if changed == "behavior":
        note = "modeler: behaviour valid against the metamodel."
        if rep.warnings:
            note += "\n" + "\n".join(f"WARNING {w}" for w in rep.warnings)
        _context("PostToolUse", note)
    return 0


def session(data: dict) -> int:
    root = _app_root(Path(data.get("cwd") or ".").resolve())
    if not root:
        return 0
    lines = [f"App with a domain metamodel: {root / METAMODEL_FILE} (source of truth of the domain structure). "
             "Every schema change starts from the metamodel (/modeler:metamodel) and goes with its migration in the "
             "same change; `npm run model:drift` must report 'aligned'. Proposals from the admin modeler: /modeler:apply."]
    try:
        sys.path.insert(0, str(SCRIPTS))
        from metamodel import __version__, cli  # noqa: E402

        lines.append(f"Modeler plugin loaded in this session: {__version__}.")
        installed = cli.installed_version(root)
        if installed is None:
            lines.append("The web modeler is not installed in this app yet: /modeler:install.")
        elif installed != __version__:
            lines.append(f"The app ships modeler {installed}, the plugin is {__version__}: upgrade it with "
                         "/modeler:install (the skill first checks that the plugin itself is current; if not: "
                         "`claude plugin marketplace update iovino-harness && claude plugin update modeler@iovino-harness`, "
                         "then /reload-plugins).")
        if (root / BEHAVIOR_FILE).exists():
            lines.append(f"Behaviour model: {root / BEHAVIOR_FILE} (roles, derivations, workflows, events, reactions), "
                         "written on the concepts of the metamodel and checked against it by `npm run model:validate`.")
        else:
            hint = cli.workflow_hint(root)                   # workflows in code, no behaviour model yet
            if hint:
                lines.append(hint)
        pending = sorted(cli.proposals_dir(root / METAMODEL_FILE).glob("*.json"))
        if pending:
            lines.append(f"{len(pending)} proposal(s) saved by the admin modeler and not applied yet "
                         f"(.modeler/proposals/: {', '.join(p.name for p in pending[:5])}): tell the user and "
                         "propose /modeler:apply. Production proposals: `pull`.")
        docs = cli.docs_status(root)
        if docs["state"] == "edited":
            lines.append("docs/DOMAIN.md has hand edits to translate into the metamodel (sections: "
                         f"{', '.join(s['name'] for s in docs['sections'][:6])}): tell the user and propose "
                         "/modeler:metamodel; `npm run model:docs` shows the diff.")
        elif docs["state"] == "stale":
            lines.append("docs/DOMAIN.md is out of date (the metamodel changed): `npm run model:sync`.")
        elif docs["state"] == "missing" and installed is not None:
            lines.append("docs/DOMAIN.md missing: `npm run model:sync` writes it.")
        elif docs["state"] == "clash":
            lines.append(f"{docs['other']} differs from docs/DOMAIN.md only by letter case: another document, not "
                         "hand notes. Nothing is written to docs/DOMAIN.md until it is renamed (e.g. docs/behavior.md, "
                         "updating its references) or deleted; tell the user.")
        dsn = os.environ.get("MODELER_DRIFT_DB")
        if dsn:
            from metamodel import dbschema as D, ecore as E  # noqa: E402
            found = D.drift(E.load(root / METAMODEL_FILE), D.catalog(dsn))
            lines.append("Metamodel and database aligned." if not found else
                         "DRIFT between metamodel and database:\n" + "\n".join(f"- {x}" for x in found[:30]))
    except Exception as exc:  # never break a session
        lines.append(f"(modeler check skipped: {exc})")
    print("\n".join(lines))
    return 0


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "post"
    return {"post": post, "session": session}[mode](_input())


if __name__ == "__main__":
    sys.exit(main())
