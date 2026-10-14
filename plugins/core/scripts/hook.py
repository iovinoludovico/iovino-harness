#!/usr/bin/env python3
"""Hook entry point of the core plugin (stdlib only).

Usage: hook.py <session|guard-file|guard-bash|format>   (hook JSON on stdin)

Exit codes follow the Claude Code hook contract:
  0  no objection (optionally with JSON on stdout)
  2  block the tool call; stderr is shown to Claude
Every unexpected error exits 0 so a bug here never blocks the user's work.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN_ROOT = Path(os.environ.get("CLAUDE_PLUGIN_ROOT") or Path(__file__).resolve().parents[1])


# --------------------------------------------------------------------- helpers

def read_input() -> dict:
    try:
        data = json.loads(sys.stdin.read() or "{}")
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def option(name: str, default: str = "") -> str:
    return os.environ.get(f"CLAUDE_PLUGIN_OPTION_{name.upper()}", default)


def is_true(value: str, default: bool = True) -> bool:
    if value == "":
        return default
    return value.strip().lower() not in {"false", "0", "no", "off"}


def deny(reason: str) -> int:
    print(f"[core guard] {reason}", file=sys.stderr)
    return 2


def ask(reason: str) -> int:
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": f"[core guard] {reason}",
    }}))
    return 0


def git(cwd: Path, *args: str) -> str:
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5)
        return out.stdout.strip() if out.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


# --------------------------------------------------------------------- session

STACK_MARKERS = [
    ("package.json", "Node"),
    ("next.config.js", "Next.js"), ("next.config.mjs", "Next.js"), ("next.config.ts", "Next.js"),
    ("supabase/config.toml", "Supabase"),
    ("pyproject.toml", "Python"), ("requirements.txt", "Python"),
    ("pom.xml", "Maven"), ("build.gradle", "Gradle"), ("build.gradle.kts", "Gradle"),
    ("Dockerfile", "Docker"), ("docker-compose.yml", "Compose"), ("compose.yaml", "Compose"),
    ("domain.ecore.yaml", "metamodello appforge"),
    ("app.yaml", "appforge?"),
]


def detect_stack(root: Path) -> list[str]:
    found: list[str] = []
    for marker, label in STACK_MARKERS:
        if (root / marker).exists() and label not in found:
            found.append(label)
    if any(root.glob("*.ecore")) or any(root.glob("**/model/*.ecore")) or (root / "META-INF/MANIFEST.MF").exists():
        found.append("EMF/Eclipse")
    if any(root.glob("**/*.etl")) or any(root.glob("**/*.evl")):
        found.append("Epsilon")
    return found


def cmd_session(data: dict) -> int:
    cwd = Path(data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    parts: list[str] = []
    conv = PLUGIN_ROOT / "context" / "conventions.md"
    if conv.exists():
        parts.append(conv.read_text(encoding="utf-8").strip())

    info: list[str] = [f"- Cartella: {cwd}"]
    top = git(cwd, "rev-parse", "--show-toplevel")
    root = Path(top) if top else cwd
    if top:
        branch = git(cwd, "branch", "--show-current") or "(detached HEAD)"
        dirty = [line for line in git(cwd, "status", "--porcelain").splitlines() if line.strip()]
        info.append(f"- Git: branch `{branch}`, {len(dirty)} file modificati non committati")
        if branch in {"main", "master"}:
            info.append("- Sei sul branch principale: per modifiche non banali crea prima un branch feat/… o fix/…")
    else:
        info.append("- Non è un repository git")
    stack = detect_stack(root)
    if stack:
        info.append("- Stack rilevato: " + ", ".join(stack))
    if not (root / "CLAUDE.md").exists() and not (root / ".claude" / "CLAUDE.md").exists():
        info.append("- Manca CLAUDE.md: proponi `/core:project-init` se il lavoro sul progetto non è occasionale")
    if (root / "HANDOFF.md").exists():
        info.append("- Esiste HANDOFF.md: leggilo prima di iniziare, contiene lo stato lasciato dalla sessione precedente")
    parts.append("## Progetto corrente\n" + "\n".join(info))

    print("\n\n".join(parts))
    return 0


# ------------------------------------------------------------------ guard-file

SECRET_NAME_RE = re.compile(
    r"^(\.env(\..+)?|.*\.(pem|key|p12|pfx|keystore|jks)|id_(rsa|ecdsa|ed25519|dsa)(\.pub)?|\.npmrc|\.pypirc|\.netrc|credentials(\.json)?|service-account.*\.json)$",
    re.IGNORECASE,
)
SAFE_SUFFIXES = (".example", ".sample", ".template", ".dist", ".pub")

SECRET_CONTENT = [
    (re.compile(r"-----BEGIN (RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----"), "una chiave privata"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "una access key AWS"),
    (re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b"), "un token GitHub"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{50,}\b"), "un token GitHub"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"), "una API key Anthropic"),
    (re.compile(r"\bsk-(proj-)?[A-Za-z0-9]{32,}\b"), "una API key OpenAI"),
    (re.compile(r"\bxox[abpr]-[A-Za-z0-9-]{10,}\b"), "un token Slack"),
]


def file_target(tool_input: dict) -> str:
    return str(tool_input.get("file_path") or tool_input.get("notebook_path") or "")


def written_text(tool_input: dict) -> str:
    chunks = [tool_input.get("content"), tool_input.get("new_string"), tool_input.get("new_source")]
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict):
            chunks.append(edit.get("new_string"))
    return "\n".join(c for c in chunks if isinstance(c, str))


def cmd_guard_file(data: dict) -> int:
    tool_input = data.get("tool_input") or {}
    path = file_target(tool_input)
    if path:
        p = Path(path)
        name = p.name
        if ".git" in p.parts:
            return deny(f"{path} è dentro .git/: usa i comandi git, non modificare gli interni del repository.")
        if SECRET_NAME_RE.match(name) and not name.lower().endswith(SAFE_SUFFIXES):
            return deny(
                f"{name} è un file di segreti: non lo modifico. Aggiorna invece il corrispondente "
                f".env.example (solo nomi delle variabili) e chiedi all'utente di inserire i valori."
            )
    text = written_text(tool_input)
    if text:
        for pattern, label in SECRET_CONTENT:
            if pattern.search(text):
                return deny(
                    f"il contenuto da scrivere in {path or 'questo file'} sembra contenere {label}. "
                    f"I segreti vanno nelle variabili d'ambiente, non nei file versionati. "
                    f"Usa un placeholder e un riferimento a process.env / os.environ."
                )
    return 0


# ------------------------------------------------------------------ guard-bash

QUOTED_RE = re.compile(r"'[^']*'|\"(?:\\.|[^\"\\])*\"")
SEGMENT_RE = re.compile(r"\|\||&&|;|\||\n")

DENY_RULES = [
    (re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR][a-zA-Z]*\s+(-[a-zA-Z]+\s+)*(/|~|\$HOME|\$\{HOME\})/?\*?(\s|$)"),
     "rm ricorsivo sulla root o sulla home"),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "formattazione di un filesystem"),
    (re.compile(r"\bdd\b.*\bof=/dev/(sd|nvme|disk|hd)"), "scrittura diretta su un disco"),
    (re.compile(r":\(\)\s*\{\s*:\|:&\s*\};:"), "fork bomb"),
    (re.compile(r"\bgit\s+push\b.*(--force\b|--force-with-lease\b|\s-f\b|\s\+\S).*\b(main|master)\b"),
     "force push sul branch principale"),
    (re.compile(r"\bgit\s+push\b.*\b(main|master)\b.*(--force\b|\s-f\b)"), "force push sul branch principale"),
]

ASK_RULES = [
    (re.compile(r"\bgit\s+push\b"), "git push: per convenzione si fa solo su richiesta esplicita"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard scarta le modifiche locali"),
    (re.compile(r"\bgit\s+clean\s+-[a-zA-Z]*f"), "git clean cancella file non tracciati"),
    (re.compile(r"\bgit\s+(checkout|restore)\s+(--\s+)?\.(\s|$)"), "scarta tutte le modifiche locali"),
    (re.compile(r"\bgit\s+branch\s+-D\b"), "cancellazione forzata di un branch"),
    (re.compile(r"\bgit\s+(tag|rebase)\b"), "tag e rebase si fanno solo su richiesta"),
    (re.compile(r"--no-verify\b"), "salta gli hook di verifica"),
    (re.compile(r"\bgh\s+(release|repo\s+delete|pr\s+merge)\b"), "operazione GitHub irreversibile o pubblica"),
    (re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-[a-zA-Z]*[rR]"), "cancellazione ricorsiva"),
    (re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z)?sh\b"), "esegue uno script scaricato dalla rete"),
    (re.compile(r"\bchmod\s+(-R\s+)?777\b"), "permessi 777"),
    (re.compile(r"\bsudo\b"), "comando con sudo"),
    (re.compile(r"\bsupabase\s+(db\s+reset|db\s+push|link)\b"), "operazione sul database Supabase"),
    (re.compile(r"\bdocker\s+(system|volume|image)\s+prune\b|\bdocker\s+compose\s+down\s+.*-v\b"),
     "cancella volumi o immagini Docker"),
    (re.compile(r"\b(cat|less|more|head|tail|bat|source|\.)\s+(\S*/)?\.env(\.(?!example\b)\w+)*(\s|$)"),
     "legge un file di segreti"),
    (re.compile(r"\b(npm|pnpm|yarn)\s+publish\b"), "pubblicazione di un pacchetto"),
]


# checked on the raw command: SQL usually travels inside quotes (psql -c "...")
RAW_ASK_RULES = [
    (re.compile(r"\b(DROP|TRUNCATE)\s+(TABLE|DATABASE|SCHEMA)\b", re.IGNORECASE), "DDL distruttivo sul database"),
    (re.compile(r"\bDELETE\s+FROM\s+\w+\s*(;|\"|'|$)", re.IGNORECASE), "DELETE senza WHERE"),
]


def cmd_guard_bash(data: dict) -> int:
    command = str((data.get("tool_input") or {}).get("command") or "")
    if not command.strip():
        return 0
    for pattern, label in DENY_RULES:
        if pattern.search(command):
            return deny(f"comando bloccato ({label}). Se è davvero necessario, l'utente lo esegue a mano.")
    unquoted = QUOTED_RE.sub("''", command)
    reasons: list[str] = []
    for segment in SEGMENT_RE.split(unquoted):
        for pattern, label in ASK_RULES:
            if pattern.search(segment) and label not in reasons:
                reasons.append(label)
    # pipes are split above, so check curl|sh on the whole command as well
    for pattern, label in ASK_RULES:
        if "|" in pattern.pattern and pattern.search(unquoted) and label not in reasons:
            reasons.append(label)
    for pattern, label in RAW_ASK_RULES:
        if pattern.search(command) and label not in reasons:
            reasons.append(label)
    if reasons:
        return ask("; ".join(reasons))
    return 0


# ---------------------------------------------------------------------- format

PRETTIER_EXT = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".json", ".css", ".scss", ".md", ".mdx",
                ".html", ".yaml", ".yml", ".vue", ".svelte"}
PRETTIER_CONFIGS = [".prettierrc", ".prettierrc.json", ".prettierrc.js", ".prettierrc.cjs", ".prettierrc.mjs",
                    ".prettierrc.yaml", ".prettierrc.yml", ".prettierrc.toml", "prettier.config.js",
                    "prettier.config.cjs", "prettier.config.mjs", "prettier.config.ts"]


def find_up(start: Path, stop: Path, predicate) -> Path | None:
    cur = start
    while True:
        if predicate(cur):
            return cur
        if cur == stop or cur.parent == cur:
            return None
        cur = cur.parent


def has_prettier_config(d: Path) -> bool:
    if any((d / c).exists() for c in PRETTIER_CONFIGS):
        return True
    pkg = d / "package.json"
    if pkg.exists():
        try:
            return "prettier" in json.loads(pkg.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return False
    return False


def python_formatter(d: Path) -> list[str] | None:
    text = ""
    if (d / "pyproject.toml").exists():
        text = (d / "pyproject.toml").read_text(encoding="utf-8", errors="ignore")
    if ((d / "ruff.toml").exists() or (d / ".ruff.toml").exists() or "[tool.ruff" in text) and shutil.which("ruff"):
        return ["ruff", "format", "--quiet"]
    if "[tool.black" in text and shutil.which("black"):
        return ["black", "--quiet"]
    return None


def formatter_for(path: Path, project: Path) -> tuple[list[str], Path] | None:
    ext = path.suffix.lower()
    if ext in PRETTIER_EXT:
        root = find_up(path.parent, project, has_prettier_config)
        if root:
            local = find_up(path.parent, project, lambda d: (d / "node_modules/.bin/prettier").exists())
            if local:
                return [str(local / "node_modules/.bin/prettier"), "--write", "--log-level", "warn"], root
    if ext in {".py", ".pyi"}:
        for d in [path.parent, *path.parent.parents]:
            cmd = python_formatter(d)
            if cmd:
                return cmd, d
            if d == project:
                break
    return None


def digest(path: Path) -> str:
    try:
        return hashlib.sha1(path.read_bytes()).hexdigest()
    except OSError:
        return ""


def cmd_format(data: dict) -> int:
    if not is_true(option("autoformat"), default=True):
        return 0
    path_str = file_target(data.get("tool_input") or {})
    if not path_str:
        return 0
    path = Path(path_str)
    if not path.is_file():
        return 0
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or path.parent).resolve()
    path = path.resolve()
    if project not in path.parents:
        return 0
    if "node_modules" in path.parts or ".git" in path.parts:
        return 0
    found = formatter_for(path, project)
    if not found:
        return 0
    cmd, root = found
    before = digest(path)
    try:
        subprocess.run([*cmd, str(path)], cwd=root, capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.SubprocessError):
        return 0
    if digest(path) != before:
        tool = Path(cmd[0]).name
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": f"{path.name} è stato riformattato da {tool}: rileggilo prima di modificarlo di nuovo.",
        }}))
    return 0


# ------------------------------------------------------------------------ main

COMMANDS = {
    "session": cmd_session,
    "guard-file": cmd_guard_file,
    "guard-bash": cmd_guard_bash,
    "format": cmd_format,
}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] not in COMMANDS:
        print(f"usage: hook.py <{'|'.join(COMMANDS)}>", file=sys.stderr)
        return 0
    try:
        return COMMANDS[argv[1]](read_input())
    except Exception as exc:  # never break the session because of a bug in a hook
        print(f"[core hook] errore interno ignorato: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
