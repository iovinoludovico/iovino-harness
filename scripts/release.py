#!/usr/bin/env python3
"""Plugin versions of the harness: every release (push) of a changed plugin raises its version.

    python3 scripts/release.py            show which plugins changed since their last version and the next version
    python3 scripts/release.py --write    raise them (plugin.json + twin files) and commit `chore(release): …`
    python3 scripts/release.py --check    exit 1 if a changed plugin still has its old version (pre-push hook, CI)

A plugin needs a release when commits after the last change of its `"version"` line touch `plugins/<name>/`.
The level comes from those Conventional Commits: breaking (`!` or BREAKING CHANGE) -> major, `feat` -> minor,
anything else -> patch; in 0.x a major becomes a minor. `--level` forces it. No tags, no push.
Python standard library only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# files that repeat the plugin version and must follow plugin.json (path relative to the plugin, regex with one group)
TWIN_FILES = {
    "modeler": [("scripts/metamodel/__init__.py", r'^__version__ = "([^"]+)"$')],
}
LEVELS = ("patch", "minor", "major")
SUBJECT = re.compile(r"^(?P<type>\w+)(?:\([^)]*\))?(?P<bang>!)?:")


class ReleaseError(Exception):
    pass


def git(repo: Path, *args: str) -> str:
    out = subprocess.run(["git", *args], cwd=repo, capture_output=True, text=True)
    if out.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)}: {out.stderr.strip()}")
    return out.stdout


def plugins(repo: Path) -> list[str]:
    market = json.loads((repo / ".claude-plugin" / "marketplace.json").read_text(encoding="utf-8"))
    return [p["name"] for p in market.get("plugins", [])]


def manifest(repo: Path, name: str) -> Path:
    return repo / "plugins" / name / ".claude-plugin" / "plugin.json"


def version_of(repo: Path, name: str) -> str:
    return json.loads(manifest(repo, name).read_text(encoding="utf-8"))["version"]


def twin_versions(repo: Path, name: str) -> list[tuple[Path, str | None]]:
    out = []
    for rel, pattern in TWIN_FILES.get(name, []):
        path = repo / "plugins" / name / rel
        m = re.search(pattern, path.read_text(encoding="utf-8"), re.M) if path.exists() else None
        out.append((path, m.group(1) if m else None))
    return out


def bump(version: str, level: str) -> str:
    m = re.match(r"^(\d+)\.(\d+)\.(\d+)$", version)
    if not m:
        raise ReleaseError(f"not a semantic version: {version}")
    major, minor, patch = map(int, m.groups())
    if level == "major" and major == 0:
        level = "minor"                      # 0.x: breaking changes raise the minor
    if level == "major":
        return f"{major + 1}.0.0"
    if level == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def level_of(messages: list[str]) -> str:
    level = "patch"
    for msg in messages:
        m = SUBJECT.match(msg.strip())
        if (m and m.group("bang")) or "BREAKING CHANGE" in msg:
            return "major"
        if m and m.group("type") == "feat":
            level = "minor"
    return level


def status(repo: Path, name: str) -> dict:
    """What a release of `name` would do: changed commits since its last version change."""
    rel_manifest = str(manifest(repo, name).relative_to(repo))
    base = git(repo, "log", "-1", "--format=%H", "-G\"version\"", "--", rel_manifest).strip()
    if not base:
        raise ReleaseError(f"{name}: no commit sets a version in {rel_manifest}")
    log = git(repo, "log", "--format=%H%x1f%B%x1e", f"{base}..HEAD", "--", f"plugins/{name}/")
    messages = [chunk.split("\x1f", 1)[1] for chunk in log.split("\x1e") if "\x1f" in chunk]
    dirty = git(repo, "status", "--porcelain", "--", f"plugins/{name}/").strip()
    current = version_of(repo, name)
    problems = [f"{p.relative_to(repo)} has version {v}, plugin.json {current}"
                for p, v in twin_versions(repo, name) if v != current]
    return {"name": name, "version": current, "base": base[:7], "commits": len(messages),
            "level": level_of(messages), "dirty": bool(dirty), "problems": problems}


def write(repo: Path, name: str, new: str) -> list[Path]:
    path = manifest(repo, name)
    text = path.read_text(encoding="utf-8")
    text, n = re.subn(r'("version"\s*:\s*")[^"]+(")', rf"\g<1>{new}\g<2>", text, count=1)
    if n != 1:
        raise ReleaseError(f"{path}: no version field")
    path.write_text(text, encoding="utf-8")
    changed = [path]
    for rel, pattern in TWIN_FILES.get(name, []):
        twin = repo / "plugins" / name / rel
        body = twin.read_text(encoding="utf-8")
        m = re.search(pattern, body, re.M)
        if not m:
            raise ReleaseError(f"{twin}: version not found")
        twin.write_text(body[:m.start(1)] + new + body[m.end(1):], encoding="utf-8")
        changed.append(twin)
    return changed


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--write", action="store_true", help="raise the versions and commit")
    p.add_argument("--check", action="store_true", help="exit 1 if a changed plugin was not released")
    p.add_argument("--level", choices=LEVELS, help="force the level instead of deducing it from the commits")
    p.add_argument("--repo", default=str(Path(__file__).resolve().parents[1]))
    a = p.parse_args(argv)
    repo = Path(a.repo).resolve()
    try:
        states = [status(repo, n) for n in plugins(repo)]
        problems = [x for s in states for x in s["problems"]]
        if problems:
            print("Versions out of sync:\n" + "\n".join(f"  {x}" for x in problems), file=sys.stderr)
            return 1
        pending = [s for s in states if s["commits"]]
        if a.check:
            if pending:
                names = ", ".join(f"{s['name']} {s['version']}" for s in pending)
                print(f"release: {names} changed since the last version. Run `python3 scripts/release.py --write`"
                      " and push again.", file=sys.stderr)
                return 1
            return 0
        if not pending:
            print("Nothing to release: every plugin is at the version of its last change.")
            return 0
        plan = [(s, bump(s["version"], a.level or s["level"])) for s in pending]
        for s, new in plan:
            dirty = " (uncommitted changes in the plugin: commit them first)" if s["dirty"] else ""
            print(f"{s['name']}: {s['version']} -> {new}  ({s['commits']} commit(s) since {s['base']}, "
                  f"{a.level or s['level']}){dirty}")
        if not a.write:
            print("(dry run: --write raises the versions and commits)")
            return 0
        if any(s["dirty"] for s, _ in plan):
            print("Commit the changes of the plugins first.", file=sys.stderr)
            return 1
        files = [f for s, new in plan for f in write(repo, s["name"], new)]
        git(repo, "add", "--", *[str(f.relative_to(repo)) for f in files])
        summary = ", ".join(f"{s['name']} {new}" for s, new in plan)
        git(repo, "commit", "-q", "-m", f"chore(release): {summary}")
        print(f"committed chore(release): {summary}")
        return 0
    except ReleaseError as exc:
        print(f"release: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
