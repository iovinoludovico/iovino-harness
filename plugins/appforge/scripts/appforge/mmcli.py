"""`appforge metamodel ...`: commands on the domain metamodel (domain.ecore.yaml)."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from . import dbschema as D
from . import ecore as E
from . import model as M

PLUGIN_ROOT = Path(__file__).resolve().parents[2]
KIT_DIR = PLUGIN_ROOT / "modeler"


def find_metamodel(ref: str | None, must_exist: bool = True) -> Path:
    """A metamodel file from a path (file or directory), an app slug, or the nearest one upwards."""
    if ref:
        p = Path(ref)
        if p.is_file():
            return p.resolve()
        if p.is_dir():
            return (p / E.METAMODEL_FILE).resolve()
        from . import project as P
        try:
            return P.resolve_app(ref) / E.METAMODEL_FILE
        except P.ProjectError:
            pass
        if not must_exist:
            return p.resolve()
        raise M.ModelError(f"no metamodel at {ref}")
    cwd = Path.cwd().resolve()
    for d in [cwd, *cwd.parents]:
        if (d / E.METAMODEL_FILE).exists():
            return d / E.METAMODEL_FILE
    if not must_exist:
        return cwd / E.METAMODEL_FILE
    raise M.ModelError(f"no {E.METAMODEL_FILE} in {cwd} or its parents (create it with /appforge:metamodel)")


def _report(meta_path: Path, meta: dict[str, Any]) -> M.Report:
    rep = E.validate(meta)
    app = meta_path.parent / "app.yaml"
    if app.exists() and rep.ok:
        _, rep2 = M.load_and_validate(app)
        rep.errors += [x for x in rep2.errors if not x.startswith("domain.ecore.yaml")]
        rep.warnings += [x for x in rep2.warnings if not x.startswith("domain.ecore.yaml")]
    return rep


def cmd_validate(a) -> int:
    path = find_metamodel(a.path)
    meta = E.load(path)
    rep = _report(path, meta)
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
        raw = E.compose(meta, {}, rep)
        m = M.normalize(raw)
        for name, ent in m["entities"].items():
            cols = ", ".join(f"{k}{'[]' if f['many'] else ''}:{f['type']}{('→' + f['to']) if f['to'] else ''}{'!' if f['required'] else ''}"
                             for k, f in ent["fields"].items())
            print(f"{ent['table']} ({name}): {cols}")
        for x in rep.errors:
            print("ERROR", x)
    else:
        print(E.dumps(meta), end="")
    return 0


def cmd_extract(a) -> int:
    from . import project as P
    root = P.resolve_app(a.app)
    app = root / P.MODEL_FILE
    if (root / E.METAMODEL_FILE).exists():
        print(f"{root / E.METAMODEL_FILE} already exists: the app is already split", file=sys.stderr)
        return 1
    raw = M.load_file(app)
    meta, beh = E.extract(raw)
    before = M.normalize(raw)
    after = M.normalize(E.compose(meta, beh))
    for ent in list(before["entities"].values()) + list(after["entities"].values()):
        for f in ent["fields"].values():
            f.pop("order", None)
    if json.dumps(before, sort_keys=True, default=str) != json.dumps(after, sort_keys=True, default=str):
        print("extract would change the model: aborted (please report this case)", file=sys.stderr)
        return 1
    if a.dry_run:
        print(E.dumps(meta))
        print("# ---- app.yaml (behaviour) ----")
        print(M.dumps(beh))
        return 0
    (root / ".appforge").mkdir(exist_ok=True)
    shutil.copyfile(app, root / ".appforge" / "app.yaml.before-split")
    E.dump(meta, root / E.METAMODEL_FILE)
    M.dump(beh, app)
    lock = P.read_lock(root)
    if lock:   # same model, only the field order changed: do not report it as a model change
        lock["raw"] = M.load(app)
        lock["model"] = M.normalize(lock["raw"])
        lock["model_sha"] = P.sha(app.read_text(encoding="utf-8") + (root / E.METAMODEL_FILE).read_text(encoding="utf-8"))
        P.write_lock(root, lock)
    print(f"wrote {root / E.METAMODEL_FILE} (structure) and {app} (behaviour); backup in .appforge/app.yaml.before-split")
    return 0


def cmd_export(a) -> int:
    path = find_metamodel(a.path)
    text = E.export_ecore(E.load(path))
    out = Path(a.output) if a.output else path.with_name(E.expand(E.load(path))["package"] + ".ecore")
    out.write_text(text, encoding="utf-8")
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


def _load_any(path: Path) -> dict[str, Any]:
    if path.suffix == ".json":
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc = doc.get("metamodel", doc)  # a proposal file wraps the metamodel
        return E.from_editor(doc)
    return E.load(path)


def cmd_diff(a) -> int:
    changes = E.diff(_load_any(Path(a.old)), _load_any(Path(a.new)))
    print("\n".join(changes) if changes else "no changes")
    return 0


def proposals_dir(meta_path: Path) -> Path:
    return meta_path.parent / ".appforge" / "proposals"


def cmd_proposals(a) -> int:
    meta_path = find_metamodel(a.path)
    d = proposals_dir(meta_path)
    files = sorted(d.glob("*.json")) if d.exists() else []
    if not files:
        print("no pending proposals (the admin modeler saves them in .appforge/proposals/ in development,"
              " or offers them for download in production)")
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
    app = meta_path.parent / "app.yaml"
    if rep.ok and app.exists():   # the behaviour (workflow, reactions, UI) must still fit the new structure
        composed = E.compose(new, M.load_file(app), rep)
        rep2 = M.validate(M.normalize(composed))
        rep.errors += [f"app.yaml {x}" for x in rep2.errors]
    print(rep.render())
    if not rep.ok:
        print("\nThe proposal breaks the application: fix app.yaml (or the proposal) first; nothing was written.")
        return 1
    if not a.write:
        print("\n(dry run: pass --write to update the metamodel)")
        return 0
    if meta_path.exists():
        bak = meta_path.parent / ".appforge" / f"domain.ecore.yaml.{dt.datetime.now():%Y%m%d-%H%M%S}.bak"
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(meta_path, bak)
    E.dump(new, meta_path)
    if src.parent == proposals_dir(meta_path):
        done = src.parent / "applied"
        done.mkdir(exist_ok=True)
        src.rename(done / src.name)
    print(f"\nwrote {meta_path}")
    app = meta_path.parent / "app.yaml"
    if app.exists():
        _, rep2 = M.load_and_validate(app)
        print("composed with app.yaml: " + rep2.render().splitlines()[-1])
        print("next: /appforge:generate (or python3 scripts/appforge.py generate)")
    else:
        print("next (app not generated by appforge): run `metamodel drift --db ...` and implement the changes")
    return 0


def cmd_reverse(a) -> int:
    cat = D.catalog(a.db, a.schema)
    exclude = {t.strip() for t in (a.exclude or "").split(",") if t.strip()}
    include = {t.strip() for t in (a.include or "").split(",") if t.strip()}
    raw, notes = D.reverse(cat, package=a.package, exclude=exclude, include=include)
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
    meta = E.load(find_metamodel(a.path))
    exclude = {t.strip() for t in (a.exclude or "").split(",") if t.strip()}
    found = D.drift(meta, D.catalog(a.db, a.schema), exclude)
    print("\n".join(found) if found else "metamodel and database are aligned")
    return 1 if found else 0


def cmd_install_modeler(a) -> int:
    target = Path(a.app).resolve()
    if not (target / "package.json").exists():
        print(f"{target} is not a Node/Next.js project", file=sys.stderr)
        return 1
    written = install_kit(target, with_migration=not a.no_migration)
    for w in written:
        print(f"  + {w}")
    print("next: wire the admin page into the app's admin guard and navigation (see the adopt skill)")
    return 0


def install_kit(target: Path, with_migration: bool = True) -> list[str]:
    """Copies the framework-free modeler and its glue into an existing Next.js app."""
    written = []
    copies = {
        KIT_DIR / "metamodel-editor.js": target / "public" / "appforge" / "metamodel-editor.js",
        KIT_DIR / "next" / "metamodel-modeler.tsx": target / "src" / "components" / "appforge" / "metamodel-modeler.tsx",
        KIT_DIR / "next" / "metamodel-actions.ts": target / "src" / "lib" / "appforge" / "metamodel-actions.ts",
    }
    for src, dst in copies.items():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        written.append(str(dst.relative_to(target)))
    if with_migration:
        mig = target / "supabase" / "migrations"
        mig.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S")
        if not list(mig.glob("*_model_change_requests.sql")):
            dst = mig / f"{stamp}_model_change_requests.sql"
            shutil.copyfile(KIT_DIR / "model_change_requests.sql", dst)
            written.append(str(dst.relative_to(target)))
    meta = target / E.METAMODEL_FILE
    if meta.exists():
        out = target / "src" / "lib" / "appforge" / "metamodel.json"
        out.write_text(json.dumps(E.runtime_json(E.load(meta)), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        written.append(str(out.relative_to(target)))
    return written


def cmd_sync(a) -> int:
    """Refreshes the modeler files of an adopted app (metamodel.json and the editor) after a change."""
    meta_path = find_metamodel(a.path)
    root = meta_path.parent
    out = root / "src" / "lib" / "appforge" / "metamodel.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(E.runtime_json(E.load(meta_path)), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {out}")
    js = root / "public" / "appforge" / "metamodel-editor.js"
    if js.parent.exists():
        shutil.copyfile(KIT_DIR / "metamodel-editor.js", js)
        print(f"wrote {js}")
    return 0


PULL_SQL = """
with picked as (
  update public.model_change_requests set status = 'pulled'
   where status = 'open' returning id, metamodel, note, author_email, created_at)
select coalesce(json_agg(picked order by created_at), '[]') from picked
"""


def cmd_pull(a) -> int:
    """Copies the open proposals stored by the production modeler into .appforge/proposals/."""
    import subprocess
    meta_path = find_metamodel(a.path)
    out = subprocess.run(["psql", a.db, "-X", "-A", "-t", "-v", "ON_ERROR_STOP=1", "-c", PULL_SQL],
                         capture_output=True, text=True, timeout=60)
    if out.returncode != 0:
        raise D.DbError(out.stderr.strip())
    rows = json.loads(out.stdout.strip() or "[]")
    d = proposals_dir(meta_path)
    d.mkdir(parents=True, exist_ok=True)
    for r in rows:
        name = str(r["created_at"]).replace(":", "-").replace(" ", "T")[:19] + f"-{str(r['id'])[:8]}.json"
        (d / name).write_text(json.dumps({"author": r.get("author_email"), "note": r.get("note"),
                                          "created_at": r["created_at"], "metamodel": r["metamodel"]},
                                         ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"  + {d / name}")
    print(f"{len(rows)} proposal(s) pulled" + ("; review them with `appforge metamodel proposals`" if rows else ""))
    return 0


def add_parser(sub) -> None:
    mm = sub.add_parser("metamodel", help="domain metamodel (domain.ecore.yaml): validate, show, reverse, drift, proposals")
    s2 = mm.add_subparsers(dest="mmcmd", required=True)

    s = s2.add_parser("validate", help="validate the metamodel (and app.yaml composed with it)")
    s.add_argument("path", nargs="?")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_validate)

    s = s2.add_parser("show", help="print the metamodel")
    s.add_argument("path", nargs="?")
    s.add_argument("--format", choices=["yaml", "emfatic", "mermaid", "json", "storage"], default="emfatic")
    s.set_defaults(fn=cmd_show)

    s = s2.add_parser("extract", help="split a legacy app.yaml into domain.ecore.yaml + app.yaml")
    s.add_argument("app", nargs="?")
    s.add_argument("--dry-run", action="store_true")
    s.set_defaults(fn=cmd_extract)

    s = s2.add_parser("export", help="write the metamodel as an Ecore XMI file (Eclipse EMF, Epsilon)")
    s.add_argument("path", nargs="?")
    s.add_argument("-o", "--output")
    s.set_defaults(fn=cmd_export)

    s = s2.add_parser("import", help="read an .ecore file into domain.ecore.yaml")
    s.add_argument("ecore")
    s.add_argument("-o", "--output")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_import)

    s = s2.add_parser("diff", help="changes between two metamodels (yaml, .ecore or proposal .json)")
    s.add_argument("old")
    s.add_argument("new")
    s.set_defaults(fn=cmd_diff)

    s = s2.add_parser("proposals", help="list the proposals saved by the admin modeler")
    s.add_argument("path", nargs="?")
    s.set_defaults(fn=cmd_proposals)

    s = s2.add_parser("apply", help="apply a proposal (default: the latest in .appforge/proposals)")
    s.add_argument("proposal", nargs="?")
    s.add_argument("--path", help="metamodel file or app directory")
    s.add_argument("--write", action="store_true", help="update the metamodel (otherwise dry run)")
    s.set_defaults(fn=cmd_apply)

    s = s2.add_parser("reverse", help="derive a metamodel from an existing PostgreSQL schema")
    s.add_argument("--db", required=True, help="DSN, e.g. postgresql://postgres:postgres@127.0.0.1:54322/postgres")
    s.add_argument("--schema", default="public")
    s.add_argument("--package", default="domain")
    s.add_argument("--exclude", help="comma separated tables to skip")
    s.add_argument("--include", help="comma separated tables to describe (default: all)")
    s.add_argument("-o", "--output")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_reverse)

    s = s2.add_parser("drift", help="compare the metamodel with a live database")
    s.add_argument("path", nargs="?")
    s.add_argument("--db", required=True)
    s.add_argument("--schema", default="public")
    s.add_argument("--exclude")
    s.set_defaults(fn=cmd_drift)

    s = s2.add_parser("install-modeler", help="add the web modeler to an existing Next.js app")
    s.add_argument("app")
    s.add_argument("--no-migration", action="store_true")
    s.set_defaults(fn=cmd_install_modeler)

    s = s2.add_parser("pull", help="copy the proposals saved in production (model_change_requests) into .appforge/proposals")
    s.add_argument("path", nargs="?")
    s.add_argument("--db", required=True)
    s.set_defaults(fn=cmd_pull)

    s = s2.add_parser("sync", help="refresh src/lib/appforge/metamodel.json of an adopted app")
    s.add_argument("path", nargs="?")
    s.set_defaults(fn=cmd_sync)


def run(a: argparse.Namespace) -> int:
    try:
        return a.fn(a)
    except D.DbError as exc:
        print(f"appforge: database: {exc}", file=sys.stderr)
        return 2
