"""`modeler <command>`: the domain metamodel (domain.ecore.yaml) and the web modeler of an application.

The same CLI runs from the plugin and, vendored by `install`, from the application itself
(`tools/modeler/modeler.py`, wired to the `model:*` npm scripts), so the app stays aligned without the plugin.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from pathlib import Path
from typing import Any

from . import __version__
from . import core as M
from . import dbschema as D
from . import ecore as E

SCRIPTS_DIR = Path(__file__).resolve().parents[1]            # modeler.py, metamodel/, vendor/
KIT_DIR = SCRIPTS_DIR.parent / "kit"                          # only in the plugin, not in the vendored copy
STATE_DIR = ".modeler"                                        # proposals and backups, in the app repository
METAMODEL_JSON = Path("src/lib/modeler/metamodel.json")       # what the admin page reads
EDITOR_JS = Path("public/modeler/metamodel-editor.js")
TOOLS_DIR = Path("tools/modeler")
LOCAL_SUPABASE_PORT = 54322

NPM_SCRIPTS = {
    "model:validate": "python3 tools/modeler/modeler.py validate",
    "model:show": "python3 tools/modeler/modeler.py show",
    "model:sync": "python3 tools/modeler/modeler.py sync",
    "model:drift": "python3 tools/modeler/modeler.py drift",
    "model:proposals": "python3 tools/modeler/modeler.py proposals",
    "model:apply": "python3 tools/modeler/modeler.py apply",
}


# --------------------------------------------------------------------------- #
# Locating things
# --------------------------------------------------------------------------- #
def find_metamodel(ref: str | None, must_exist: bool = True) -> Path:
    """A metamodel file from a path (file or directory), or the nearest one upwards from the current directory."""
    if ref:
        p = Path(ref)
        if p.is_dir():
            p = p / E.METAMODEL_FILE
        if p.exists() or not must_exist:
            return p.resolve()
        raise M.ModelError(f"no metamodel at {ref}")
    cwd = Path.cwd().resolve()
    for d in [cwd, *cwd.parents]:
        if (d / E.METAMODEL_FILE).exists():
            return d / E.METAMODEL_FILE
    if not must_exist:
        return cwd / E.METAMODEL_FILE
    raise M.ModelError(f"no {E.METAMODEL_FILE} in {cwd} or its parents (create it with /modeler:metamodel "
                       "or derive it from the database with `reverse`)")


def local_dsn(root: Path) -> str | None:
    """DSN of the database to compare with: MODELER_DB, else the local Supabase of the app (supabase/config.toml)."""
    if os.environ.get("MODELER_DB"):
        return os.environ["MODELER_DB"]
    cfg = root / "supabase" / "config.toml"
    if cfg.exists():
        section = None
        for line in cfg.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("["):
                section = line.strip("[]").strip()
            elif section == "db" and re.match(r"^port\s*=", line):
                port = re.sub(r"\D", "", line.split("=", 1)[1])
                return f"postgresql://postgres:postgres@127.0.0.1:{port or LOCAL_SUPABASE_PORT}/postgres"
        return f"postgresql://postgres:postgres@127.0.0.1:{LOCAL_SUPABASE_PORT}/postgres"
    return None


def proposals_dir(meta_path: Path) -> Path:
    return meta_path.parent / STATE_DIR / "proposals"


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_any(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        doc = json.loads(path.read_text(encoding="utf-8"))
        return E.from_editor(doc.get("metamodel", doc))   # a proposal file wraps the metamodel
    return E.load(path)


# --------------------------------------------------------------------------- #
# Commands on the metamodel
# --------------------------------------------------------------------------- #
def cmd_validate(a) -> int:
    rep = E.validate(E.load(find_metamodel(a.path)))
    if a.json:
        print(json.dumps({"ok": rep.ok, "errors": rep.errors, "warnings": rep.warnings}, indent=2))
    else:
        print(rep.render())
    return 0 if rep.ok else 1


def cmd_show(a) -> int:
    meta = E.load(find_metamodel(a.path))
    if a.format == "emfatic":
        print(E.to_emfatic(meta), end="")
    elif a.format == "mermaid":
        print(E.to_mermaid(meta), end="")
    elif a.format == "json":
        print(json.dumps(E.runtime_json(meta), ensure_ascii=False, indent=2))
    elif a.format == "storage":
        rep = M.Report()
        st = E.storage(meta, rep)
        for name, ent in st["entities"].items():
            cols = []
            for k, f in ent["fields"].items():
                if f["many"] and f["type"] == "ref":
                    cols.append(f"{k}[]→{f['to']} (join table {f.get('join_table') or ent['table'] + '_' + k})")
                    continue
                target = f"→{f['to']}" if f["to"] else ""
                cols.append(f"{k}:{f['enum'] or f['type']}{target}{'!' if f['required'] else ''}{' unique' if f['unique'] else ''}")
            print(f"{ent['table']} ({name}): {', '.join(cols)}")
        for x in rep.errors:
            print("ERROR", x)
    else:
        print(E.dumps(meta), end="")
    return 0


def cmd_export(a) -> int:
    path = find_metamodel(a.path)
    meta = E.load(path)
    out = Path(a.output) if a.output else path.with_name(E.expand(meta)["package"] + ".ecore")
    out.write_text(E.export_ecore(meta), encoding="utf-8")
    print(f"wrote {out}")
    return 0


def cmd_import(a) -> int:
    raw = E.import_ecore(Path(a.ecore).read_text(encoding="utf-8"))
    out = Path(a.output or E.METAMODEL_FILE)
    if out.exists() and not a.force:
        print(f"{out} exists: use --force to overwrite", file=sys.stderr)
        return 1
    E.dump(raw, out)
    print(f"wrote {out}")
    print(E.validate(raw).render())
    return 0


def cmd_diff(a) -> int:
    changes = E.diff(_load_any(Path(a.old)), _load_any(Path(a.new)))
    print("\n".join(changes) if changes else "no changes")
    return 0


# --------------------------------------------------------------------------- #
# Proposals saved by the web modeler
# --------------------------------------------------------------------------- #
def cmd_proposals(a) -> int:
    meta_path = find_metamodel(a.path)
    d = proposals_dir(meta_path)
    files = sorted(d.glob("*.json")) if d.exists() else []
    if not files:
        print(f"no pending proposals (the modeler saves them in {STATE_DIR}/proposals/ in development; "
              "in production `pull --db <DSN>` copies them from model_change_requests)")
        return 0
    current = E.load(meta_path)
    for f in files:
        doc = json.loads(f.read_text(encoding="utf-8"))
        changes = E.diff(current, E.from_editor(doc.get("metamodel", doc)))
        print(f"{f.name}  by {doc.get('author', '?')}  {doc.get('note', '')}")
        for c in changes[:20]:
            print(f"    {c}")
    return 0


def cmd_apply(a) -> int:
    meta_path = find_metamodel(a.path, must_exist=False)
    if a.proposal:
        src = Path(a.proposal)
    else:
        d = proposals_dir(meta_path)
        files = sorted(d.glob("*.json")) if d.exists() else []
        if not files:
            print("no proposal to apply", file=sys.stderr)
            return 1
        src = files[-1]
    new = _load_any(src)
    old = E.load(meta_path) if meta_path.exists() else {"package": new.get("package", "domain"), "classes": {}}
    changes = E.diff(old, new)
    print(f"Proposal {src}:")
    print("\n".join(f"  {c}" for c in changes) if changes else "  no changes")
    rep = E.validate(new)
    print(rep.render())
    if not rep.ok:
        print("\nThe proposal is not a valid metamodel: nothing was written.")
        return 1
    if not a.write:
        print("\n(dry run: pass --write to update the metamodel)")
        return 0
    if meta_path.exists():
        bak = meta_path.parent / STATE_DIR / "backups" / f"{E.METAMODEL_FILE}.{dt.datetime.now():%Y%m%d-%H%M%S}"
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(meta_path, bak)
    E.dump(new, meta_path)
    if src.parent == proposals_dir(meta_path):
        done = src.parent / "applied"
        done.mkdir(exist_ok=True)
        src.rename(done / src.name)
    sync(meta_path.parent)
    print(f"\nwrote {meta_path}")
    print("next: write the migration for these changes, apply it locally, then `npm run model:drift`")
    return 0


PULL_SQL = """
with picked as (
  update public.model_change_requests set status = 'pulled'
   where status = 'open' returning id, metamodel, note, author_email, created_at)
select coalesce(json_agg(picked order by created_at), '[]') from picked
"""


def cmd_pull(a) -> int:
    """Copies the open proposals stored by the production modeler into .modeler/proposals/."""
    import subprocess
    meta_path = find_metamodel(a.path)
    try:
        out = subprocess.run(["psql", a.db, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", PULL_SQL],
                             capture_output=True, text=True, timeout=60)
    except FileNotFoundError as exc:
        raise D.DbError("psql not found: install the PostgreSQL client") from exc
    if out.returncode != 0:
        raise D.DbError(out.stderr.strip())
    rows = json.loads(out.stdout.strip() or "[]")
    d = proposals_dir(meta_path)
    for r in rows:
        name = str(r["created_at"]).replace(":", "-").replace(" ", "T")[:19] + f"-{str(r['id'])[:8]}.json"
        _write_json(d / name, {"author": r.get("author_email"), "note": r.get("note"),
                               "created_at": r["created_at"], "metamodel": r["metamodel"]})
        print(f"  + {d / name}")
    print(f"{len(rows)} proposal(s) pulled" + ("; review them with `proposals`" if rows else ""))
    return 0


# --------------------------------------------------------------------------- #
# Database
# --------------------------------------------------------------------------- #
def cmd_reverse(a) -> int:
    root = Path(a.output).resolve().parent if a.output else Path.cwd()
    dsn = a.db or local_dsn(root)
    if not dsn:
        print("no database: pass --db <DSN> (or set MODELER_DB)", file=sys.stderr)
        return 2
    exclude = {t.strip() for t in (a.exclude or "").split(",") if t.strip()}
    include = {t.strip() for t in (a.include or "").split(",") if t.strip()}
    raw, notes = D.reverse(D.catalog(dsn, a.schema), package=a.package, exclude=exclude, include=include)
    rep = E.validate(raw)
    text = E.dumps(raw)
    if a.output:
        out = Path(a.output)
        if out.exists() and not a.force:
            print(f"{out} exists: use --force to overwrite", file=sys.stderr)
            return 1
        out.write_text(text, encoding="utf-8")
        print(f"wrote {out}")
    else:
        print(text)
    for n in notes:
        print(f"note: {n}", file=sys.stderr)
    print(rep.render(), file=sys.stderr)
    return 0 if rep.ok else 1


def cmd_drift(a) -> int:
    meta_path = find_metamodel(a.path)
    dsn = a.db or local_dsn(meta_path.parent)
    if not dsn:
        print("no database: pass --db <DSN> (or set MODELER_DB)", file=sys.stderr)
        return 2
    exclude = {t.strip() for t in (a.exclude or os.environ.get("MODELER_EXCLUDE", "")).split(",") if t.strip()}
    found = D.drift(E.load(meta_path), D.catalog(dsn, a.schema), exclude)
    print("\n".join(found) if found else "metamodel and database are aligned")
    return 1 if found else 0


# --------------------------------------------------------------------------- #
# The modeler inside the application
# --------------------------------------------------------------------------- #
def sync(root: Path) -> list[str]:
    """Refreshes what the admin page reads (metamodel.json) from domain.ecore.yaml."""
    meta = root / E.METAMODEL_FILE
    if not meta.exists():
        return []
    _write_json(root / METAMODEL_JSON, E.runtime_json(E.load(meta)))
    return [str(METAMODEL_JSON)]


def cmd_sync(a) -> int:
    root = find_metamodel(a.path).parent
    for w in sync(root):
        print(f"wrote {w}")
    return 0


def install(target: Path, with_migration: bool = True) -> list[str]:
    """Makes the modeler part of the application. Files owned by the modeler (editor, wrapper, server action,
    vendored CLI) are replaced on every run, so running it again upgrades the modeler; files meant to be
    adapted to the app (access.ts, the admin page) are written only when missing."""
    if not KIT_DIR.exists():
        raise M.ModelError("install runs from the plugin (the vendored copy in an app has no kit)")
    written: list[str] = []

    def copy(src: Path, rel: str, overwrite: bool = True) -> None:
        dst = target / rel
        if dst.exists() and not overwrite:
            return
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(rel)

    copy(KIT_DIR / "metamodel-editor.js", str(EDITOR_JS))
    copy(KIT_DIR / "next" / "metamodel-modeler.tsx", "src/components/modeler/metamodel-modeler.tsx")
    copy(KIT_DIR / "next" / "metamodel-actions.ts", "src/lib/modeler/metamodel-actions.ts")
    copy(KIT_DIR / "next" / "access.ts", "src/lib/modeler/access.ts", overwrite=False)
    # the CLI travels with the app: model:* scripts work without the plugin
    tools = target / TOOLS_DIR
    if tools.exists():
        shutil.rmtree(tools)
    shutil.copytree(SCRIPTS_DIR, tools, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    (tools / "VERSION").write_text(__version__ + "\n", encoding="utf-8")
    written.append(f"{TOOLS_DIR}/ (CLI {__version__})")
    if with_migration:
        mig = target / "supabase" / "migrations"
        if not list(mig.glob("*_model_change_requests.sql")):
            stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
            copy(KIT_DIR / "model_change_requests.sql", f"supabase/migrations/{stamp}_model_change_requests.sql")
    pkg = target / "package.json"
    data = json.loads(pkg.read_text(encoding="utf-8"))
    scripts = data.setdefault("scripts", {})
    if any(scripts.get(k) != v for k, v in NPM_SCRIPTS.items()):
        scripts.update(NPM_SCRIPTS)
        pkg.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append("package.json (model:* scripts)")
    written += sync(target)
    return written


def installed_version(root: Path) -> str | None:
    f = root / TOOLS_DIR / "VERSION"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def cmd_install(a) -> int:
    target = Path(a.app).resolve()
    if not (target / "package.json").exists():
        print(f"{target} is not a Node/Next.js project (no package.json)", file=sys.stderr)
        return 1
    for w in install(target, with_migration=not a.no_migration):
        print(f"  + {w}")
    if not (target / E.METAMODEL_FILE).exists():
        print(f"no {E.METAMODEL_FILE} yet: derive it with `reverse --db <DSN> -o {E.METAMODEL_FILE}`, then `sync`")
    print("next: adapt src/lib/modeler/access.ts to the app's admin check, add the admin page and the link "
          "in the admin navigation (see the install skill)")
    return 0


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="modeler", description="Domain metamodel (domain.ecore.yaml) and the web modeler of an app")
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("validate", help="validate the metamodel")
    s.add_argument("path", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("show", help="print the metamodel")
    s.add_argument("path", nargs="?")
    s.add_argument("--format", choices=["yaml", "emfatic", "mermaid", "json", "storage"], default="emfatic")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("export", help="write the metamodel as an Ecore XMI file (Eclipse EMF, Epsilon)")
    s.add_argument("path", nargs="?")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_export)

    s = sub.add_parser("import", help="read an .ecore file into domain.ecore.yaml")
    s.add_argument("ecore")
    s.add_argument("-o", "--output")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_import)

    s = sub.add_parser("diff", help="changes between two metamodels (yaml, .ecore or proposal .json)")
    s.add_argument("old")
    s.add_argument("new")
    s.set_defaults(fn=cmd_diff)

    s = sub.add_parser("proposals", help=f"list the proposals saved by the modeler ({STATE_DIR}/proposals)")
    s.add_argument("path", nargs="?")
    s.set_defaults(fn=cmd_proposals)

    s = sub.add_parser("apply", help="apply a proposal (default: the latest pending one)")
    s.add_argument("proposal", nargs="?")
    s.add_argument("--path", help="metamodel file or app directory")
    s.add_argument("--write", action="store_true", help="update the metamodel (otherwise dry run)")
    s.set_defaults(fn=cmd_apply)

    s = sub.add_parser("pull", help="copy the proposals saved in production (model_change_requests)")
    s.add_argument("path", nargs="?")
    s.add_argument("--db", required=True)
    s.set_defaults(fn=cmd_pull)

    s = sub.add_parser("reverse", help="derive a metamodel from an existing PostgreSQL schema")
    s.add_argument("--db", help="DSN (default: MODELER_DB or the local Supabase of the app)")
    s.add_argument("--schema", default="public")
    s.add_argument("--package", default="domain")
    s.add_argument("--exclude", help="comma separated tables (or table.column) to skip")
    s.add_argument("--include", help="comma separated tables to describe (default: all)")
    s.add_argument("-o", "--output")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_reverse)

    s = sub.add_parser("drift", help="compare the metamodel with a live database")
    s.add_argument("path", nargs="?")
    s.add_argument("--db", help="DSN (default: MODELER_DB or the local Supabase of the app)")
    s.add_argument("--schema", default="public")
    s.add_argument("--exclude", help="comma separated tables (or table.column) to ignore (default: MODELER_EXCLUDE)")
    s.set_defaults(fn=cmd_drift)

    s = sub.add_parser("sync", help=f"refresh {METAMODEL_JSON} from the metamodel")
    s.add_argument("path", nargs="?")
    s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("install", help="make the web modeler part of a Next.js + Supabase app (or upgrade it)")
    s.add_argument("app", nargs="?", default=".")
    s.add_argument("--no-migration", action="store_true")
    s.set_defaults(fn=cmd_install)
    return p


def main(argv: list[str] | None = None) -> int:
    a = build_parser().parse_args(argv)
    try:
        return a.fn(a)
    except D.DbError as exc:
        print(f"modeler: database: {exc}", file=sys.stderr)
        return 2
    except M.ModelError as exc:
        print(f"modeler: {exc}", file=sys.stderr)
        return 2
