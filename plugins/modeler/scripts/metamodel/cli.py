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
from . import behavior as B
from . import core as M
from . import dbschema as D
from . import ecore as E
from . import engine as N
from . import expr as X
from . import sqlgen as G

SCRIPTS_DIR = Path(__file__).resolve().parents[1]            # modeler.py, metamodel/, vendor/
KIT_DIR = SCRIPTS_DIR.parent / "kit"                          # only in the plugin, not in the vendored copy
STATE_DIR = ".modeler"                                        # proposals and backups, in the app repository
METAMODEL_JSON = Path("src/lib/modeler/metamodel.json")       # what the admin page reads
BEHAVIOR_JSON = Path("src/lib/modeler/behavior.json")         # the behaviour as the app reads it (typed expressions, SQL)
DOMAIN_MD = Path("docs/DOMAIN.md")                            # the domain explained, generated; hand notes allowed
BEHAVIOR_MD = Path("docs/BEHAVIOR.md")                        # the behaviour explained, generated (no hand notes)
DOMAIN_COPY = Path(STATE_DIR) / "DOMAIN.generated.md"         # what sync wrote last: hand edits are measured against it
EDITOR_JS = Path("public/modeler/metamodel-editor.js")
TOOLS_DIR = Path("tools/modeler")
LOCAL_SUPABASE_PORT = 54322
VERSION_PLACEHOLDER = "__MODELER_VERSION__"                   # in kit/metamodel-editor.js

NPM_SCRIPTS = {
    "model:validate": "python3 tools/modeler/modeler.py validate",
    "model:show": "python3 tools/modeler/modeler.py show",
    "model:sync": "python3 tools/modeler/modeler.py sync",
    "model:docs": "python3 tools/modeler/modeler.py docs",
    "model:drift": "python3 tools/modeler/modeler.py drift",
    "model:proposals": "python3 tools/modeler/modeler.py proposals",
    "model:pull": "python3 tools/modeler/modeler.py pull",
    "model:done": "python3 tools/modeler/modeler.py done",
    "model:apply": "python3 tools/modeler/modeler.py apply",
    "model:migrate": "python3 tools/modeler/modeler.py migrate",
    "model:behavior": "python3 tools/modeler/modeler.py behavior",
    "model:engine": "python3 tools/modeler/modeler.py engine",
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


def remote_dsn(root: Path) -> str | None:
    """DSN of the production database: MODELER_PROD_DB, else the Supabase project linked with `supabase link`.

    The linked DSN has no password: psql takes it from PGPASSWORD (SUPABASE_DB_PASSWORD), ~/.pgpass or a prompt.
    """
    if os.environ.get("MODELER_PROD_DB"):
        return os.environ["MODELER_PROD_DB"]
    temp = root / "supabase" / ".temp"
    pooler = temp / "pooler-url"
    if pooler.exists() and pooler.read_text(encoding="utf-8").strip():
        return pooler.read_text(encoding="utf-8").strip()
    ref = temp / "project-ref"
    if ref.exists() and ref.read_text(encoding="utf-8").strip():
        return f"postgresql://postgres@db.{ref.read_text(encoding='utf-8').strip()}.supabase.co:5432/postgres"
    return None


def _dsn_target(dsn: str) -> str:
    """user@host:port/db of a DSN, without the password, to show where a command connects."""
    m = re.match(r"^postgres(?:ql)?://(?:([^:@/]+)(?::[^@/]*)?@)?([^/?]+)(/[^?]*)?", dsn)
    if not m:
        return "(DSN in key=value form)"
    return f"{m.group(1) + '@' if m.group(1) else ''}{m.group(2)}{m.group(3) or ''}"


def _has_password(dsn: str) -> bool:
    return bool(re.match(r"^postgres(?:ql)?://[^:@/]+:[^@/]+@", dsn)) or "password=" in dsn


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
def behavior_file(meta_path: Path, explicit: str | None = None) -> Path | None:
    """The behaviour model to check with a metamodel: the one given, else behavior.yaml next to the metamodel."""
    if explicit:
        return Path(explicit)
    p = B.behavior_path(meta_path)
    return p if p.exists() else None


def validate_behavior(meta_raw: dict[str, Any], bpath: Path) -> M.Report:
    try:
        return B.validate(B.load(bpath), meta_raw)
    except M.ModelError as exc:
        rep = M.Report()
        rep.error(str(bpath), str(exc))
        return rep


def cmd_validate(a) -> int:
    meta_path = find_metamodel(a.path)
    raw = E.load(meta_path)
    rep = E.validate(raw)
    bpath = behavior_file(meta_path, a.behavior)
    brep = validate_behavior(raw, bpath) if bpath and rep.ok else None
    if a.json:
        out: dict[str, Any] = {"ok": rep.ok and (brep is None or brep.ok), "errors": rep.errors, "warnings": rep.warnings}
        if brep is not None:
            out["behavior"] = {"file": str(bpath), "ok": brep.ok, "errors": brep.errors, "warnings": brep.warnings}
        print(json.dumps(out, indent=2))
    else:
        print(rep.render())
        if brep is not None:
            print(f"--- {bpath.name} against the metamodel")
            print(brep.render(ok_text="Behaviour OK"))
        elif bpath and not rep.ok:
            print(f"{bpath.name}: not checked (the metamodel must be valid first)")
    return 0 if rep.ok and (brep is None or brep.ok) else 1


def cmd_show(a) -> int:
    meta = E.load(find_metamodel(a.path))
    if a.format == "emfatic":
        print(E.to_emfatic(meta), end="")
    elif a.format == "mermaid":
        print(E.to_mermaid(meta), end="")
    elif a.format == "markdown":
        print(E.to_markdown(meta), end="")
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


def cmd_behavior(a) -> int:
    """The behaviour model in a given view (valid metamodel and behaviour assumed: run validate first)."""
    meta_path = find_metamodel(a.path)
    bpath = behavior_file(meta_path, a.behavior)
    if bpath is None:
        print(f"no {B.BEHAVIOR_FILE} next to {meta_path}", file=sys.stderr)
        return 1
    raw, meta = B.load(bpath), E.load(meta_path)
    rep = E.validate(meta)
    brep = B.validate(raw, meta) if rep.ok else None
    if not rep.ok or not brep.ok:
        print((rep if not rep.ok else brep).render(), file=sys.stderr)
        return 1
    if a.format == "markdown":
        print(B.to_markdown(raw, meta, a.lang), end="")
    elif a.format == "mermaid":
        b = B.expand(raw)
        lang = a.lang or E.expand(meta)["language"]
        for cname, w in b["workflows"].items():
            print(f"%% {cname}")
            print(B.mermaid_workflow(w, lang), end="")
    elif a.format == "json":
        print(json.dumps(B.runtime_json(raw, meta), ensure_ascii=False, indent=2))
    elif a.format == "sql":
        print(B.sql_view(raw, meta), end="")
    elif a.format == "engine":
        b = B.expand(raw)
        try:
            print(json.dumps({c: B.engine_version(raw, meta, c) for c in b["workflows"]}, ensure_ascii=False, indent=2))
        except X.ExprError as exc:
            print(f"a guard the engine cannot evaluate as clauses: {exc}", file=sys.stderr)
            return 1
    return 0


def _write_migration(meta_path: Path, name: str, sql: str) -> Path:
    name = re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_") or "model_change"
    mig = meta_path.parent / "supabase" / "migrations"
    mig.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    latest = max((f.name[:14] for f in mig.glob("*.sql") if f.name[:14].isdigit()), default="")
    if latest >= stamp:   # keep the order of the existing migrations
        stamp = str(int(latest) + 1)
    out = mig / f"{stamp}_{name}.sql"
    out.write_text(sql, encoding="utf-8")
    return out


def cmd_engine(a) -> int:
    """The SQL engine of the behaviour: one idempotent migration, printed or saved in supabase/migrations/."""
    meta_path = find_metamodel(a.path)
    bpath = behavior_file(meta_path, a.behavior)
    if bpath is None:
        print(f"no {B.BEHAVIOR_FILE} next to {meta_path}", file=sys.stderr)
        return 1
    raw, meta = B.load(bpath), E.load(meta_path)
    rep = E.validate(meta)
    brep = B.validate(raw, meta) if rep.ok else None
    if not rep.ok or not brep.ok:
        print((rep if not rep.ok else brep).render(), file=sys.stderr)
        return 1
    try:
        sql, notes = N.engine_sql(raw, meta, a.schema)
    except X.ExprError as exc:
        print(f"cannot generate the engine: {exc}", file=sys.stderr)
        return 1
    todos = sql.count(f"-- {N.TODO}")
    if not a.write:
        print(sql, end="")
        for n in notes:
            print(f"note: {n}", file=sys.stderr)
        print(f"(dry run: --write saves it in supabase/migrations/; {todos} TODO(modeler) to review)", file=sys.stderr)
        return 0
    out = _write_migration(meta_path, a.name or "behavior_engine", sql)
    print(f"wrote {out}")
    for n in notes:
        print(f"note: {n}")
    print(f"{todos} TODO(modeler) to review; then apply it locally (supabase db reset) and `npm run model:drift`. "
          "Regenerate it after every change of the behaviour (the file is replaced: keep one engine migration per release).")
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
              "in production `npm run model:pull` copies them from model_change_requests)")
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
    if meta_path.exists():
        # the box positions saved by the editor are not domain: the file keeps its own (or none)
        new.pop("diagram", None)
        if old.get("diagram"):
            new["diagram"] = old["diagram"]
    changes = E.diff(old, new)
    print(f"Proposal {src}:")
    print("\n".join(f"  {c}" for c in changes) if changes else "  no changes")
    rep = E.validate(new)
    print(rep.render())
    if not rep.ok:
        print("\nThe proposal is not a valid metamodel: nothing was written.")
        return 1
    bpath = behavior_file(meta_path)
    if bpath is not None:
        brep = validate_behavior(new, bpath)
        if not brep.ok:
            print(f"\nThe proposal breaks {bpath.name} (fix the behaviour in the same change):\n" + brep.render())
    included, others = _other_proposals(meta_path, src, old, new)
    if included:
        print("\nIncluded in this proposal (archived with it):")
        print("\n".join(f"  {f.name}" for f in included))
    if others:
        print("\nStill pending, with changes this proposal does not contain (review them one by one: "
              "`model:apply -- <file>`, or reject them from the modeler):")
        print("\n".join(f"  {f.name}" for f in others))
    if not a.write:
        print("\n(dry run: pass --write to update the metamodel)")
        return 0
    if meta_path.exists():
        text = meta_path.read_text(encoding="utf-8")
        new = E.align_order(new, old)   # the proposal's key order (editor, jsonb) must not reorder the file
        patched = E.patch_text(text, new)
        if patched is None and not a.rewrite:
            print(f"\nThis change cannot be written by editing only the changed lines of {E.METAMODEL_FILE} "
                  "(it touches the package header, or the file is not in the usual layout): nothing was written. "
                  "Apply it by hand, or pass --rewrite to rewrite the whole file (key order, quoting and comments "
                  "are not kept).", file=sys.stderr)
            return 1
        bak = meta_path.parent / STATE_DIR / "backups" / f"{E.METAMODEL_FILE}.{dt.datetime.now():%Y%m%d-%H%M%S}"
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(meta_path, bak)
        if patched is not None:         # only the lines of what changed: order, style and comments kept
            meta_path.write_text(patched, encoding="utf-8")
        else:
            lost = E.comment_lines(text)
            if lost:
                print(f"\nwarning: {len(lost)} comment line(s) of {E.METAMODEL_FILE} are not kept (copy in {bak}):")
                print("\n".join(f"  {line.strip()}" for line in lost[:10]))
            E.dump(new, meta_path)
    else:
        E.dump(new, meta_path)
    moved = []
    pending = src.resolve().parent == proposals_dir(meta_path).resolve()   # not a downloaded file elsewhere
    for f in ([src] if pending else []) + included:
        (f.parent / "applied").mkdir(exist_ok=True)
        dst = f.parent / "applied" / f.name
        while dst.exists():                                          # never overwrite an archived proposal
            dst = dst.with_name(f"{dst.stem}-1{dst.suffix}")
        moved.append(f.rename(dst))
    sync(meta_path.parent)
    if docs_status(meta_path.parent)["state"] in ("edited", "clash"):
        print(docs_report(docs_status(meta_path.parent), diff=False))
    print(f"\nwrote {meta_path}")
    print("next: `npm run model:migrate -- --write` drafts the migration; resolve its TODO(modeler) lines, "
          "apply it locally, then `npm run model:drift`")
    if any(_proposal_id(f) for f in moved):
        print("from production: after the deploy, `npm run model:done` marks them applied in model_change_requests")
    return 0


_MISSING = object()


def _contained(old: Any, prop: Any, new: Any) -> bool:
    """True when every value in which `prop` differs from `old` has the same value in `new` (expanded models)."""
    if old == prop:
        return True
    if isinstance(old, dict) and isinstance(prop, dict):
        sub = new if isinstance(new, dict) else {}
        return all(_contained(old.get(k, _MISSING), prop.get(k, _MISSING), sub.get(k, _MISSING))
                   for k in old.keys() | prop.keys())
    return prop == new


def _other_proposals(meta_path: Path, src: Path, old: dict[str, Any],
                     new: dict[str, Any]) -> tuple[list[Path], list[Path]]:
    """The other pending proposals, split into those whose changes are all in the applied one and the rest.

    Every proposal is a whole metamodel, so the latest one usually contains the earlier ones. The comparison is
    on the expanded models (every feature property, not only what diff() prints); diagram positions are ignored."""
    def model(m: dict[str, Any]) -> dict[str, Any]:
        out = E.expand(m)
        out.pop("diagram", None)
        return out

    d = proposals_dir(meta_path)
    base, applied = model(old), model(new)
    included, others = [], []
    for f in sorted(d.glob("*.json")) if d.exists() else []:
        if f.resolve() == src.resolve():
            continue
        try:
            prop = model(_load_any(f))
        except (ValueError, KeyError, TypeError, AttributeError, OSError, M.ModelError):
            others.append(f)
            continue
        (included if _contained(base, prop, applied) else others).append(f)
    return included, others


PULL_SQL = """
with picked as (
  update public.model_change_requests set status = 'pulled'
   where status = 'open' returning id, metamodel, note, author_email, created_at)
select coalesce(json_agg(picked order by created_at), '[]') from picked
"""


class NoProductionDb(Exception):
    pass


def _can_prompt() -> bool:
    """psql can ask the password only with a terminal: not from Claude Code (its tools, nor a `! …` command)."""
    if not sys.stdin.isatty():
        return False
    try:
        os.close(os.open("/dev/tty", os.O_RDWR))
        return True
    except OSError:
        return False


def _pgpass_line(dsn: str) -> str:
    """The ~/.pgpass line for a DSN, with a placeholder for the password."""
    m = re.match(r"^postgres(?:ql)?://(?:([^:@/]+)(?::[^@/]*)?@)?([^/:?]+)(?::(\d+))?(?:/([^?]*))?", dsn)
    if not m:
        return "<host>:<port>:<database>:<user>:<password>"
    return f"{m.group(2)}:{m.group(3) or 5432}:{m.group(4) or 'postgres'}:{m.group(1) or 'postgres'}:<password>"


def _no_password_message(dsn: str) -> str:
    return ("no database password, and psql cannot ask for it here (no terminal: Claude Code tools and `! …` "
            "commands have none). Either:\n"
            "  - export SUPABASE_DB_PASSWORD in the shell before starting Claude Code;\n"
            f"  - add this line to ~/.pgpass, then `chmod 600 ~/.pgpass`:\n      {_pgpass_line(dsn)}\n"
            "  - or run the command in your own terminal, outside Claude Code.\n"
            "Never write the password in the command: it would stay in the shell history.")


def _prod_query(dsn: str | None, sql: str, verb: str) -> Any:
    """Runs one statement returning JSON on the production database (see remote_dsn for the DSN and password)."""
    import subprocess
    if not dsn:
        raise NoProductionDb()
    env = dict(os.environ)
    if not _has_password(dsn) and os.environ.get("SUPABASE_DB_PASSWORD") and not os.environ.get("PGPASSWORD"):
        env["PGPASSWORD"] = os.environ["SUPABASE_DB_PASSWORD"]
    pgpass = Path(env.get("PGPASSFILE") or Path.home() / ".pgpass")
    interactive = _can_prompt()
    if not (_has_password(dsn) or env.get("PGPASSWORD") or pgpass.exists() or interactive):
        raise D.DbError(_no_password_message(dsn))
    print(f"{verb} {_dsn_target(dsn)}", file=sys.stderr)
    try:
        # with a terminal psql asks a missing password there (not on the captured output); without one, -w makes it
        # fail at once instead of waiting
        out = subprocess.run(["psql", dsn, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", *([] if interactive else ["-w"]),
                              "-c", sql], capture_output=True, text=True, timeout=120, env=env)
    except FileNotFoundError as exc:
        raise D.DbError("psql not found: install the PostgreSQL client") from exc
    if out.returncode != 0:
        if "no password supplied" in out.stderr:                    # e.g. ~/.pgpass without a line for this host
            raise D.DbError(f"{out.stderr.strip()}\n{_no_password_message(dsn)}")
        raise D.DbError(out.stderr.strip())
    return json.loads(out.stdout.strip() or "null")


NO_PROD_DB = ("no production database: link the app with `supabase link --project-ref <ref>`, "
              "or set MODELER_PROD_DB, or pass --db <DSN>")


def cmd_pull(a) -> int:
    """Copies the open proposals stored by the production modeler into .modeler/proposals/."""
    meta_path = find_metamodel(a.path)
    try:
        rows = _prod_query(a.db or remote_dsn(meta_path.parent), PULL_SQL, "pulling from") or []
    except NoProductionDb:
        print(NO_PROD_DB, file=sys.stderr)
        return 2
    d = proposals_dir(meta_path)
    for r in rows:
        name = str(r["created_at"]).replace(":", "-").replace(" ", "T")[:19] + f"-{str(r['id'])[:8]}.json"
        _write_json(d / name, {"id": r["id"], "author": r.get("author_email"), "note": r.get("note"),
                               "created_at": r["created_at"], "metamodel": r["metamodel"]})
        print(f"  + {d / name}")
    print(f"{len(rows)} proposal(s) pulled" + ("; review them with `proposals`" if rows else ""))
    return 0


UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
PULLED_NAME_RE = re.compile(r"-([0-9a-f]{8})\.json$")


def _proposal_id(f: Path) -> str | None:
    """Row id of a proposal pulled from production: the `id` field, or the 8-char prefix in the file name
    (files pulled before the id was stored). None for a proposal saved in development."""
    try:
        doc = json.loads(f.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if isinstance(doc, dict) and "closed" in doc:
        return None
    if isinstance(doc, dict) and isinstance(doc.get("id"), str) and UUID_RE.fullmatch(doc["id"]):
        return doc["id"]
    if isinstance(doc, dict) and "created_at" in doc and "metamodel" in doc:
        m = PULLED_NAME_RE.search(f.name)
        return m.group(1) if m else None
    return None


def _done_sql(applied: list[str], rejected: list[str]) -> str:
    """Marks the rows applied/rejected (only if still open or pulled); returns id and status of the rows found.
    The ids are validated hex (full uuid, or the 8-char prefix of older pulls), so they are safe to inline."""
    def match(ids: list[str]) -> str:
        full = [i for i in ids if UUID_RE.fullmatch(i)]
        short = [i for i in ids if not UUID_RE.fullmatch(i)]
        conds = [f"id = any(array[{','.join(repr(i) for i in full)}]::uuid[])"] if full else []
        conds += [f"id::text like any(array[{','.join(repr(i + '%') for i in short)}])"] if short else []
        return "(" + " or ".join(conds) + ")" if conds else "false"
    return f"""
with a as (update public.model_change_requests set status = 'applied'
            where {match(applied)} and status in ('open', 'pulled') returning id),
     r as (update public.model_change_requests set status = 'rejected'
            where {match(rejected)} and status in ('open', 'pulled') returning id)
select json_build_object(
  'applied', (select coalesce(json_agg(id), '[]') from a),
  'rejected', (select coalesce(json_agg(id), '[]') from r),
  'found', (select coalesce(json_object_agg(id, status), '{{}}') from public.model_change_requests
             where {match(applied + rejected)}))
"""


def cmd_done(a) -> int:
    """Closes in production (model_change_requests) the pulled proposals applied or rejected in the repository."""
    meta_path = find_metamodel(a.path)
    d = proposals_dir(meta_path)
    todo: dict[str, list[tuple[Path, str]]] = {"applied": [], "rejected": []}
    for status in todo:
        for f in sorted((d / status).glob("*.json")) if (d / status).exists() else []:
            pid = _proposal_id(f)
            if pid:
                todo[status].append((f, pid))
    if not any(todo.values()):
        print("nothing to close: no proposal pulled from production is applied or rejected and still open")
        return 0
    for status, items in todo.items():
        for f, _ in items:
            print(f"  {status}: {f.name}")
    if not a.write:
        print("\n(dry run: pass --write to mark them in production, after the deploy of the change)")
        return 0
    try:
        res = _prod_query(a.db or remote_dsn(meta_path.parent),
                          _done_sql([p for _, p in todo["applied"]], [p for _, p in todo["rejected"]]), "closing on")
    except NoProductionDb:
        print(NO_PROD_DB, file=sys.stderr)
        return 2
    updated = {str(i) for i in res.get("applied", []) + res.get("rejected", [])}
    found: dict[str, str] = {str(k): v for k, v in (res.get("found") or {}).items()}
    for status, items in todo.items():
        for f, pid in items:
            rows = [i for i in found if i.startswith(pid)]
            if len(rows) != 1:
                print(f"  {'not' if not rows else 'ambiguous'} in model_change_requests (left as is): {f.name}",
                      file=sys.stderr)
                continue
            # a row closed earlier (e.g. rejected from the production modeler) keeps its status: say so
            final = status if rows[0] in updated else found[rows[0]]
            if final != status:
                print(f"  {f.name}: already '{final}' in production, not '{status}'", file=sys.stderr)
            doc = json.loads(f.read_text(encoding="utf-8"))
            doc["closed"] = final
            _write_json(f, doc)
    print(f"marked {len(res.get('applied', []))} applied, {len(res.get('rejected', []))} rejected in production")
    return 0


# --------------------------------------------------------------------------- #
# Migration draft
# --------------------------------------------------------------------------- #
EMPTY = {"package": "domain", "classes": {}}


def _previous(meta_path: Path, ref: str) -> tuple[dict[str, Any], str]:
    """The metamodel to compare with: `empty`, a file, or `<git ref>` (the metamodel as committed there)."""
    import subprocess
    if ref == "empty":
        return EMPTY, "empty database"
    p = Path(ref)
    if p.exists():
        return _load_any(p), str(p)
    root = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=meta_path.parent, capture_output=True, text=True)
    if root.returncode != 0:
        raise M.ModelError("not a git repository: pass --from <file> or --from empty")
    rel = meta_path.resolve().relative_to(Path(root.stdout.strip()).resolve()).as_posix()
    out = subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=meta_path.parent, capture_output=True, text=True)
    if out.returncode != 0:
        if ref == "HEAD":   # never committed: the whole schema is new
            return EMPTY, "empty database (metamodel not committed yet)"
        raise M.ModelError(f"cannot read {rel} at {ref}: {out.stderr.strip()}")
    return E.loads(out.stdout), f"{ref}:{rel}"


def cmd_migrate(a) -> int:
    meta_path = find_metamodel(a.path)
    new = E.load(meta_path)
    rep = E.validate(new)
    if not rep.ok:
        print(rep.render(), file=sys.stderr)
        return 1
    old, origin = _previous(meta_path, a.from_)
    sql, notes = G.migration(old, new, origin)
    if not sql:
        print(f"no structural change between {origin} and {E.METAMODEL_FILE}"
              + (" (already committed? use --from HEAD~1)" if a.from_ == "HEAD" else ""))
        return 0
    todos = sql.count(f"-- {G.TODO}")
    if not a.write:
        print(sql, end="")
        for n in notes:
            print(f"note: {n}", file=sys.stderr)
        print(f"(dry run: --write saves it in supabase/migrations/; {todos} TODO(modeler) to resolve)", file=sys.stderr)
        return 0
    name = re.sub(r"[^a-z0-9_]+", "_", (a.name or "model_change").lower()).strip("_") or "model_change"
    mig = meta_path.parent / "supabase" / "migrations"
    mig.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
    latest = max((f.name[:14] for f in mig.glob("*.sql") if f.name[:14].isdigit()), default="")
    if latest >= stamp:   # keep the order of the existing migrations
        stamp = str(int(latest) + 1)
    out = mig / f"{stamp}_{name}.sql"
    out.write_text(sql, encoding="utf-8")
    print(f"wrote {out}")
    for n in notes:
        print(f"note: {n}")
    print(f"{todos} TODO(modeler) to resolve; then apply it locally (supabase db reset) and `npm run model:drift`")
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
    meta = E.load(meta_path)
    found = D.drift(meta, D.catalog(dsn, a.schema), exclude)
    print("\n".join(found) if found else "metamodel and database are aligned")
    bpath = behavior_file(meta_path)
    if bpath is not None and B.expand(B.load(bpath))["workflows"]:
        wcat = D.workflow_catalog(dsn, a.schema)
        if wcat is None:
            print(f"{bpath.name}: the database has no workflow tables (workflow_versions): the workflows are code, not compared")
        else:
            wfound = B.workflow_drift(B.load(bpath), meta, wcat)
            print("\n".join(wfound) if wfound else f"{bpath.name}: workflows aligned with the published versions")
            found += wfound
    return 1 if found else 0


# --------------------------------------------------------------------------- #
# The modeler inside the application
# --------------------------------------------------------------------------- #
def sync(root: Path, force: bool = False) -> list[str]:
    """Refreshes what is generated from domain.ecore.yaml: metamodel.json (the admin page) and docs/DOMAIN.md.
    A DOMAIN.md with hand edits is kept (notes for /modeler:metamodel) unless `force`, which backs it up first."""
    meta = root / E.METAMODEL_FILE
    if not meta.exists():
        return []
    raw = E.load(meta)
    _write_json(root / METAMODEL_JSON, E.runtime_json(raw))
    written = [str(METAMODEL_JSON)]
    written += sync_behavior(root, raw)
    st = docs_status(root, raw)
    if st["state"] == "clash":                       # another document would be read or overwritten as DOMAIN.md
        return written
    if st["state"] != "edited" or force:
        if st["state"] == "edited":
            bak = root / STATE_DIR / "backups" / f"DOMAIN.md.{dt.datetime.now():%Y%m%d-%H%M%S}"
            bak.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(root / DOMAIN_MD, bak)
        write_docs(root, raw)
        written.append(str(DOMAIN_MD))
    return written


def sync_behavior(root: Path, raw: dict[str, Any]) -> list[str]:
    """What is generated from behavior.yaml, when the app has one and it is valid against the metamodel:
    behavior.json (typed expressions and SQL for the app) and docs/BEHAVIOR.md (the behaviour explained, no hand
    notes: always rewritten). A docs/behavior.md with other letter case is another document: BEHAVIOR.md is not
    written until it is renamed or removed."""
    bpath = root / B.BEHAVIOR_FILE
    if not bpath.exists():
        return []
    braw = B.load(bpath)
    if not E.validate(raw).ok or not B.validate(braw, raw).ok:
        return []
    _write_json(root / BEHAVIOR_JSON, B.runtime_json(braw, raw))
    written = [str(BEHAVIOR_JSON)]
    if docs_clash(root, BEHAVIOR_MD):
        return written
    path = root / BEHAVIOR_MD
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(B.markdown_document(braw, raw), encoding="utf-8")
    return written + [str(BEHAVIOR_MD)]


def docs_clash(root: Path, doc: Path = DOMAIN_MD) -> str | None:
    """A file in docs/ named like DOMAIN.md with other letter case (appforge wrote docs/domain.md): another
    document. On macOS it would be read as DOMAIN.md, on Linux sync would write a twin next to it."""
    docs = root / doc.parent
    if not docs.is_dir():
        return None
    for name in sorted(os.listdir(docs)):                # listdir, not exists(): the latter lies on macOS
        if name.lower() == doc.name.lower() and name != doc.name:
            return str(doc.parent / name)
    return None


def docs_status(root: Path, raw: dict[str, Any] | None = None) -> dict[str, Any]:
    """docs/DOMAIN.md against the metamodel: `missing`, `aligned`, `stale` (the metamodel changed: regenerate),
    `edited` (hand notes to translate into the metamodel, listed by section with a short diff) or `clash`
    (a docs/domain.md with other letter case: nothing is written until it is renamed or removed)."""
    other = docs_clash(root)
    if other:
        return {"state": "clash", "sections": [], "other": other}
    path = root / DOMAIN_MD
    if not path.exists():
        return {"state": "missing", "sections": []}
    raw = raw if raw is not None else E.load(root / E.METAMODEL_FILE)
    generated = E.markdown_document(raw)
    actual = path.read_text(encoding="utf-8-sig")
    norm = E.markdown_normalize
    if norm(actual) == norm(generated):
        return {"state": "aligned", "sections": []}
    copy_path = root / DOMAIN_COPY
    previous = copy_path.read_text(encoding="utf-8") if copy_path.exists() else None
    if previous is not None:
        untouched = norm(actual) == norm(previous)
    else:                                            # no copy (older install): the marker's checksum decides
        checksum, body = E.markdown_split(actual)
        untouched = checksum is not None and checksum == E.markdown_checksum(body)
    if untouched:
        return {"state": "stale", "sections": []}
    # hand notes are what differs from the file sync wrote, not from the metamodel of today
    return {"state": "edited", "sections": E.markdown_changes(previous if previous is not None else generated, actual),
            "metamodel_changed": previous is not None and norm(previous) != norm(generated)}


def write_docs(root: Path, raw: dict[str, Any]) -> Path:
    path = root / DOMAIN_MD
    text = E.markdown_document(raw)
    for p in (path, root / DOMAIN_COPY):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return path


def docs_report(st: dict[str, Any], diff: bool = True) -> str:
    state = st["state"]
    if state == "clash":
        return (f"{st['other']} differs from {DOMAIN_MD} only by letter case: another document, read as {DOMAIN_MD} "
                "on macOS and doubled on Linux. Rename it (e.g. docs/behavior.md) and update its references, or "
                f"delete it if {DOMAIN_MD} replaces it; then `npm run model:sync`")
    if state == "missing":
        return f"{DOMAIN_MD} missing: `npm run model:sync` writes it"
    if state == "stale":
        return f"{DOMAIN_MD} out of date (the metamodel changed): `npm run model:sync`"
    if state == "aligned":
        return f"{DOMAIN_MD} aligned with the metamodel"
    lines = [f"{DOMAIN_MD} has edits not in the metamodel: {', '.join(x['name'] for x in st['sections'])}"]
    if diff:
        for x in st["sections"]:
            lines += [f"  [{x['name']}]"] + [f"    {line}" for line in x["diff"]]
    if st.get("metamodel_changed"):
        lines.append(f"(the metamodel changed too since {DOMAIN_MD} was written: the sections above are only the hand edits)")
    lines.append("translate them with /modeler:metamodel (structure, or `rules` for what the notation cannot express), "
                 "then `npm run model:sync -- --force` regenerates the file (a copy goes to .modeler/backups/)")
    return "\n".join(lines)


def cmd_sync(a) -> int:
    root = find_metamodel(a.path).parent
    for w in sync(root, force=getattr(a, "force", False)):
        print(f"wrote {w}")
    st = docs_status(root)
    if st["state"] in ("edited", "clash"):
        print(docs_report(st), file=sys.stderr)
        return 1
    return 0


def cmd_docs(a) -> int:
    root = find_metamodel(a.path).parent
    st = docs_status(root)
    print(docs_report(st))
    return 0 if st["state"] == "aligned" else 1


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
    editor = target / EDITOR_JS                                  # the toolbar shows the installed version
    editor.write_text(editor.read_text(encoding="utf-8").replace(VERSION_PLACEHOLDER, __version__), encoding="utf-8")
    copy(KIT_DIR / "next" / "metamodel-modeler.tsx", "src/components/modeler/metamodel-modeler.tsx")
    copy(KIT_DIR / "next" / "behavior-view.tsx", "src/components/modeler/behavior-view.tsx")
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
    if ensure_gitignore(target):
        written.append(".gitignore (__pycache__/)")
    written += sync(target)
    return written


def ensure_gitignore(target: Path) -> bool:
    """The vendored CLI leaves Python bytecode in the app when it runs: keep it out of git."""
    gi = target / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.exists() else ""
    entries = {line.strip() for line in text.splitlines()}
    if entries & {"__pycache__/", "__pycache__", "**/__pycache__/", "**/__pycache__"}:
        return False
    gi.write_text(text + ("" if not text or text.endswith("\n") else "\n")
                  + "\n# Python bytecode of the vendored modeler CLI (tools/modeler)\n__pycache__/\n", encoding="utf-8")
    return True


def installed_version(root: Path) -> str | None:
    f = root / TOOLS_DIR / "VERSION"
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def modeler_pages(root: Path) -> list[Path]:
    """The app's pages that render the modeler (the admin page adapted from kit/next/page.tsx)."""
    src = root / "src"
    if not src.exists():
        return []
    out = []
    for f in sorted(src.rglob("*.tsx")):
        if "components/modeler" in f.as_posix() or "node_modules" in f.parts:
            continue
        try:
            if "<MetamodelModeler" in f.read_text(encoding="utf-8"):
                out.append(f)
        except (OSError, UnicodeDecodeError):
            continue
    return out


def behavior_page_hint(root: Path) -> str | None:
    """The app has a behavior.yaml but its modeler page does not pass behavior.json: what to add by hand (the page
    belongs to the app, install never rewrites it). None when there is nothing to do."""
    if not (root / B.BEHAVIOR_FILE).exists():
        return None
    pages = modeler_pages(root)
    passes = re.compile(r"<MetamodelModeler\b[^>]*\bbehavior=", re.S)      # the prop in the JSX, not in a comment
    missing = [p for p in pages if not passes.search(p.read_text(encoding="utf-8"))]
    if pages and not missing:
        return None
    where = ", ".join(p.relative_to(root).as_posix() for p in missing) or "the modeler page (see the install skill)"
    return (f"{B.BEHAVIOR_FILE} found: pass the behaviour to the modeler in {where} "
            f"(import behavior from \"@/lib/modeler/behavior.json\"; <MetamodelModeler ... behavior={{behavior}} />) "
            "so /admin/model shows derived attributes, workflows and reactions")


def cmd_install(a) -> int:
    target = Path(a.app).resolve()
    if not (target / "package.json").exists():
        print(f"{target} is not a Node/Next.js project (no package.json)", file=sys.stderr)
        return 1
    for w in install(target, with_migration=not a.no_migration):
        print(f"  + {w}")
    if not (target / E.METAMODEL_FILE).exists():
        print(f"no {E.METAMODEL_FILE} yet: derive it with `reverse --db <DSN> -o {E.METAMODEL_FILE}`, then `sync`")
    elif docs_status(target)["state"] in ("edited", "clash"):
        print(docs_report(docs_status(target), diff=False))
    hint = behavior_page_hint(target)
    if hint:
        print(hint)
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

    s = sub.add_parser("validate", help=f"validate the metamodel (and {B.BEHAVIOR_FILE} next to it, if any)")
    s.add_argument("path", nargs="?")
    s.add_argument("--behavior", help=f"the behaviour model to check against the metamodel (default: {B.BEHAVIOR_FILE} next to it)")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_validate)

    s = sub.add_parser("show", help="print the metamodel")
    s.add_argument("path", nargs="?")
    s.add_argument("--format", choices=["yaml", "emfatic", "mermaid", "markdown", "json", "storage"], default="emfatic")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("behavior", help=f"print the behaviour model ({B.BEHAVIOR_FILE}) in a view")
    s.add_argument("path", nargs="?")
    s.add_argument("--behavior", help=f"the behaviour model (default: {B.BEHAVIOR_FILE} next to the metamodel)")
    s.add_argument("--format", choices=["markdown", "mermaid", "json", "sql", "engine"], default="markdown",
                   help="markdown: docs/BEHAVIOR.md; mermaid: the state diagrams; json: behavior.json (typed expressions, SQL); "
                        "sql: derivations and guards as PostgreSQL; engine: the workflow versions as the runtime engine stores them")
    s.add_argument("--lang", choices=sorted(E.LANGUAGES))
    s.set_defaults(fn=cmd_behavior)

    s = sub.add_parser("engine", help=f"the SQL engine of the behaviour ({B.BEHAVIOR_FILE}): functions and triggers, one idempotent migration")
    s.add_argument("path", nargs="?")
    s.add_argument("--behavior", help=f"the behaviour model (default: {B.BEHAVIOR_FILE} next to the metamodel)")
    s.add_argument("--schema", default="public")
    s.add_argument("--name", help="name of the migration file (default: behavior_engine)")
    s.add_argument("--write", action="store_true", help="save it in supabase/migrations/ (otherwise print it)")
    s.set_defaults(fn=cmd_engine)

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
    s.add_argument("--rewrite", action="store_true",
                   help="with --write, rewrite the whole file when only the changed lines cannot be edited")
    s.set_defaults(fn=cmd_apply)

    s = sub.add_parser("migrate", help="draft the migration from the previous metamodel to the current one")
    s.add_argument("path", nargs="?")
    s.add_argument("--from", dest="from_", default="HEAD",
                   help="previous metamodel: git ref (default HEAD), file, or `empty` for the whole schema")
    s.add_argument("--name", help="migration name (default model_change)")
    s.add_argument("--write", action="store_true", help="save it in supabase/migrations/ (otherwise print it)")
    s.set_defaults(fn=cmd_migrate)

    s = sub.add_parser("pull", help="copy the proposals saved in production (model_change_requests)")
    s.add_argument("path", nargs="?")
    s.add_argument("--db", help="DSN (default: MODELER_PROD_DB or the Supabase project linked with `supabase link`)")
    s.set_defaults(fn=cmd_pull)

    s = sub.add_parser("done", help="mark in production the pulled proposals applied or rejected in the repository")
    s.add_argument("path", nargs="?")
    s.add_argument("--db", help="DSN (default: MODELER_PROD_DB or the Supabase project linked with `supabase link`)")
    s.add_argument("--write", action="store_true", help="update model_change_requests (otherwise dry run)")
    s.set_defaults(fn=cmd_done)

    s = sub.add_parser("reverse", help="derive a metamodel from an existing PostgreSQL schema")
    s.add_argument("--db", help="DSN (default: MODELER_DB or the local Supabase of the app)")
    s.add_argument("--schema", default="public")
    s.add_argument("--package", default="domain")
    s.add_argument("--exclude", help="comma separated tables (or table.column) to skip")
    s.add_argument("--include", help="comma separated tables to describe (default: all)")
    s.add_argument("-o", "--output")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_reverse)

    s = sub.add_parser("drift", help=f"compare the metamodel with a live database (and the workflows of {B.BEHAVIOR_FILE} with the published versions)")
    s.add_argument("path", nargs="?")
    s.add_argument("--db", help="DSN (default: MODELER_DB or the local Supabase of the app)")
    s.add_argument("--schema", default="public")
    s.add_argument("--exclude", help="comma separated tables (or table.column) to ignore (default: MODELER_EXCLUDE)")
    s.set_defaults(fn=cmd_drift)

    s = sub.add_parser("sync", help=f"refresh {METAMODEL_JSON} and {DOMAIN_MD} from the metamodel "
                                    f"(and {BEHAVIOR_JSON}, {BEHAVIOR_MD} from {B.BEHAVIOR_FILE})")
    s.add_argument("path", nargs="?")
    s.add_argument("--force", action="store_true",
                   help=f"rewrite {DOMAIN_MD} even if it has hand edits (a copy goes to {STATE_DIR}/backups/)")
    s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("docs", help=f"state of {DOMAIN_MD}: aligned, out of date, or hand edits to translate into the metamodel")
    s.add_argument("path", nargs="?")
    s.set_defaults(fn=cmd_docs)

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
