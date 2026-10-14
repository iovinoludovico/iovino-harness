#!/usr/bin/env python3
"""Merge recommended permissions into a Claude Code settings.json (idempotent).

Usage: merge_settings.py <recommended.json> <target settings.json> [--allow RULE]... [--dry-run]

Only permissions.allow / permissions.deny / permissions.ask lists are merged
(union, existing order kept). Everything else in the target is left untouched.
A timestamped backup is written next to the target before any change.
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from pathlib import Path

LISTS = ("allow", "ask", "deny")


def merge(current: dict, recommended: dict) -> tuple[dict, list[str]]:
    result = json.loads(json.dumps(current))
    perms = result.setdefault("permissions", {})
    added: list[str] = []
    for key in LISTS:
        new = (recommended.get("permissions") or {}).get(key) or []
        if not new:
            continue
        existing = perms.setdefault(key, [])
        for rule in new:
            if rule not in existing:
                existing.append(rule)
                added.append(f"{key}: {rule}")
    return result, added


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__, file=sys.stderr)
        return 1
    recommended = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    target = Path(argv[2]).expanduser()
    dry = "--dry-run" in argv
    extra = [argv[i + 1] for i, a in enumerate(argv[:-1]) if a == "--allow"]
    if extra:
        recommended.setdefault("permissions", {}).setdefault("allow", []).extend(extra)
    current: dict = {}
    if target.exists():
        text = target.read_text(encoding="utf-8").strip()
        if text:
            try:
                current = json.loads(text)
            except json.JSONDecodeError as exc:
                print(f"{target} non è JSON valido ({exc}): lo lascio invariato.", file=sys.stderr)
                return 1
    merged, added = merge(current, recommended)
    if not added:
        print("Permessi già allineati: nessuna modifica.")
        return 0
    print("Regole aggiunte:\n  " + "\n  ".join(added))
    if dry:
        return 0
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        backup = target.with_name(f"{target.name}.bak-{time.strftime('%Y%m%d-%H%M%S')}")
        shutil.copy2(target, backup)
        print(f"Backup: {backup}")
    target.write_text(json.dumps(merged, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Aggiornato: {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
