"""Generated projects: scaffold, generate, status and the registry of applications.

Every generated application is an independent repository. It holds its model
(`app.yaml`), the lock of the last generation (`.appforge/lock.json`) and the
generated artefacts; it does not depend on the plugin at run time. The registry
(`~/.appforge/registry.json`) only indexes the applications so that the plugin
and the Studio can list them, show their state and operate on any of them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import shutil
from pathlib import Path
from typing import Any

from . import diff as D
from . import model as M
from . import sqlgen as S
from . import tsgen as T

GENERATOR_VERSION = "0.2.0"
PLUGIN_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE_DIR = PLUGIN_ROOT / "templates" / "app"
LOCK = ".appforge/lock.json"
MODEL_FILE = "app.yaml"
GENERATED_FILES = ("src/lib/model.ts", "src/lib/events/catalog.ts", "docs/domain.md", "src/lib/appforge/metamodel.json",
                   "public/appforge/metamodel-editor.js")
MODELER_DIR = PLUGIN_ROOT / "modeler"
# web modeler glue copied once into a new app (then it is app code, like the template)
MODELER_KIT = {
    "next/metamodel-modeler.tsx": "src/components/appforge/metamodel-modeler.tsx",
    "next/metamodel-actions.ts": "src/lib/appforge/metamodel-actions.ts",
}
METAMODEL_FILE = "domain.ecore.yaml"
TEXT_SUFFIXES = {".ts", ".tsx", ".js", ".mjs", ".json", ".md", ".yml", ".yaml", ".toml", ".sql", ".css", ".example", ""}


class ProjectError(Exception):
    pass


# --------------------------------------------------------------------------- #
# Small utilities
# --------------------------------------------------------------------------- #
def sha(text: str | bytes) -> str:
    if isinstance(text, str):
        text = text.encode("utf-8")
    return hashlib.sha256(text).hexdigest()


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0)


def find_project(start: str | Path | None = None) -> Path:
    """The nearest directory (upwards) containing app.yaml."""
    p = Path(start or os.getcwd()).resolve()
    if p.is_file():
        p = p.parent
    for d in [p, *p.parents]:
        if (d / MODEL_FILE).exists():
            return d
    raise ProjectError(f"no {MODEL_FILE} found in {p} or its parents (run /appforge:new-app first)")


def read_lock(root: Path) -> dict[str, Any] | None:
    f = root / LOCK
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else None


def write_lock(root: Path, lock: dict[str, Any]) -> None:
    f = root / LOCK
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(lock, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")  # key order matters (field order)


def migration_stamps(root: Path) -> list[str]:
    mdir = root / "supabase" / "migrations"
    if not mdir.exists():
        return []
    return sorted(f.name.split("_", 1)[0] for f in mdir.glob("*.sql") if re.match(r"^\d{14}_", f.name))


def next_stamp(root: Path, used: list[str]) -> str:
    """A migration timestamp later than every existing or already allocated one."""
    stamp = now_utc().strftime("%Y%m%d%H%M%S")
    existing = migration_stamps(root) + used
    if existing and stamp <= max(existing):
        stamp = (dt.datetime.strptime(max(existing), "%Y%m%d%H%M%S") + dt.timedelta(seconds=1)).strftime("%Y%m%d%H%M%S")
    return stamp


# --------------------------------------------------------------------------- #
# Registry
# --------------------------------------------------------------------------- #
def registry_path() -> Path:
    return Path(os.environ.get("APPFORGE_HOME", Path.home() / ".appforge")) / "registry.json"


def read_registry() -> dict[str, Any]:
    p = registry_path()
    if not p.exists():
        return {"apps": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"apps": {}}


def write_registry(reg: dict[str, Any]) -> None:
    p = registry_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(reg, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def register(root: Path, m: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
    root = root.resolve()
    if m is None:
        m = M.normalize(M.load(root / MODEL_FILE))
    reg = read_registry()
    entry = reg["apps"].get(m["app"]["slug"], {})
    if entry.get("path") and Path(entry["path"]) != root and Path(entry["path"]).exists():
        raise ProjectError(f"an app with slug '{m['app']['slug']}' is already registered at {entry['path']}")
    entry.update({
        "slug": m["app"]["slug"], "name": m["app"]["name"], "path": str(root),
        "description": m["app"]["description"], "deploy_url": m["app"]["deploy"]["base_url"],
        "image": m["app"]["deploy"]["image"],
    })
    entry.setdefault("registered_at", now_utc().isoformat())
    entry.update({k: v for k, v in extra.items() if v is not None})
    reg["apps"][m["app"]["slug"]] = entry
    write_registry(reg)
    return entry


def unregister(slug: str) -> bool:
    reg = read_registry()
    if slug in reg["apps"]:
        del reg["apps"][slug]
        write_registry(reg)
        return True
    return False


def resolve_app(ref: str | None) -> Path:
    """An app given by slug (registry), path, or the current directory."""
    if ref:
        reg = read_registry()
        if ref in reg["apps"]:
            return Path(reg["apps"][ref]["path"])
        p = Path(ref).expanduser()
        if p.exists():
            return find_project(p)
        raise ProjectError(f"unknown app '{ref}': not a registered slug nor a path")
    return find_project()


# --------------------------------------------------------------------------- #
# Scaffold
# --------------------------------------------------------------------------- #
def placeholders(m: dict[str, Any]) -> dict[str, str]:
    app = m["app"]
    return {
        "{{APP_NAME}}": app["name"],
        "{{APP_SLUG}}": app["slug"],
        "{{APP_DESCRIPTION}}": app["description"],
        "{{IMAGE}}": app["deploy"]["image"],
        "{{BASE_URL}}": app["deploy"]["base_url"],
        "{{ALLOWED_DOMAINS}}": ",".join(app["auth"]["allowed_domains"]),
        "{{DEFAULT_LOCALE}}": app["locales"][0],
        "{{LOCALES_TS}}": json.dumps(app["locales"]),
        "{{TIMEZONE}}": app["timezone"],
        "{{GOOGLE_ENABLED}}": "true" if "google" in app["auth"]["providers"] else "false",
        "{{EMAIL_ENABLED}}": "true" if "email" in app["auth"]["providers"] else "false",
        "{{GENERATOR_VERSION}}": GENERATOR_VERSION,
        "{{PLATFORMS}}": ",".join(app["deploy"]["platforms"]),
    }


def scaffold(target: Path, model_path: Path | None, force: bool = False) -> list[str]:
    """Copies the application template into `target` and puts the model in it."""
    target = target.resolve()
    if target.exists() and any(target.iterdir()) and not force:
        if not (target / MODEL_FILE).exists() or (target / "package.json").exists():
            raise ProjectError(f"{target} is not empty (use --force to scaffold into it)")
    target.mkdir(parents=True, exist_ok=True)
    if model_path and model_path.resolve() != (target / MODEL_FILE).resolve():
        shutil.copyfile(model_path, target / MODEL_FILE)
        meta = model_path.resolve().parent / METAMODEL_FILE
        if meta.exists() and not (target / METAMODEL_FILE).exists():
            shutil.copyfile(meta, target / METAMODEL_FILE)
    if not (target / MODEL_FILE).exists():
        raise ProjectError("no model: pass --model or create app.yaml first (/appforge:spec)")
    if not (target / METAMODEL_FILE).exists():
        # every app is model-based: the structure goes to the metamodel, app.yaml keeps the behaviour
        from . import ecore as E
        meta, beh = E.extract(M.load_file(target / MODEL_FILE))
        E.dump(meta, target / METAMODEL_FILE)
        M.dump(beh, target / MODEL_FILE)
    m, rep = M.load_and_validate(target / MODEL_FILE)
    if not rep.ok:
        raise ProjectError("the model is not valid:\n" + rep.render())
    subst = placeholders(m)
    written = []
    for src in TEMPLATE_DIR.rglob("*"):
        if src.is_dir():
            continue
        rel = src.relative_to(TEMPLATE_DIR)
        rel_str = str(rel).replace("_dot_", ".")  # template keeps dotfiles as _dot_name
        dst = target / rel_str
        if dst.exists() and not force:
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        if src.suffix in TEXT_SUFFIXES or src.name.startswith("_dot_"):
            try:
                text = src.read_text(encoding="utf-8")
                for k, v in subst.items():
                    text = text.replace(k, v)
                dst.write_text(text, encoding="utf-8")
            except UnicodeDecodeError:
                shutil.copyfile(src, dst)
        else:
            shutil.copyfile(src, dst)
        written.append(rel_str)
    for src_rel, dst_rel in MODELER_KIT.items():
        dst = target / dst_rel
        if not dst.exists() or force:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(MODELER_DIR / src_rel, dst)
            written.append(dst_rel)
    for loc in m["app"]["locales"]:
        mf = target / "messages" / f"{loc}.json"
        if not mf.exists():
            base = target / "messages" / "en.json"
            mf.write_text(base.read_text(encoding="utf-8") if base.exists() else "{}\n", encoding="utf-8")
            written.append(f"messages/{loc}.json")
    return written


# --------------------------------------------------------------------------- #
# Generate
# --------------------------------------------------------------------------- #
def without_ui(m: dict[str, Any]) -> dict[str, Any]:
    """The model without the UI mapping (which never needs a migration)."""
    out = dict(m)
    out["entities"] = {n: {k: v for k, v in e.items() if k not in ("ui", "ui_spec")} for n, e in m.get("entities", {}).items()}
    return out


def metamodel_json(root: Path, m: dict[str, Any] | None = None) -> str:
    """Runtime copy of the metamodel read by the admin modeler (derived from app.yaml if not split yet),
    with the behaviour attached to each class (workflow, events, webhooks, UI)."""
    from . import ecore as E
    meta_file = root / METAMODEL_FILE
    meta = E.load(meta_file) if meta_file.exists() else E.extract(M.load_file(root / MODEL_FILE))[0]
    doc = E.runtime_json(meta)
    if m is not None:
        doc["behaviour"] = E.behaviour_summary(m)
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"

def _write(root: Path, rel: str, text: str) -> str:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return sha(text)


def manual_migration_text(ops: list[dict[str, str]], n: int, phase: str) -> str:
    when = ("BEFORE the generated evolve migration that follows it (drops, renames, data moves)." if phase == "pre"
            else "AFTER the generated evolve migration that precedes it (backfills of new columns).")
    out = [f"-- TODO(appforge): hand-written migration for evolution #{n} ({phase}).",
           "-- The model changed in ways that cannot be generated safely. Complete every",
           "-- section, remove the TODO lines, then run /appforge:check. This file runs",
           f"-- {when}", ""]
    for op in ops:
        out.append(f"-- TODO(appforge) {op['op']} {op['target']}: {op['why']}")
        out.extend(op["sql"].splitlines() if op["sql"] else [])
        out.append("")
    return "\n".join(out) + "\n"


def generate(root: Path, dry_run: bool = False, rebuild_behavior: bool = False) -> dict[str, Any]:
    root = root.resolve()
    m, rep = M.load_and_validate(root / MODEL_FILE)
    if not rep.ok:
        raise ProjectError("the model is not valid:\n" + rep.render())
    lock = read_lock(root)
    result: dict[str, Any] = {"migrations": [], "files": [], "ops": [], "manual": [], "warnings": rep.warnings}
    used: list[str] = []
    migrations: list[tuple[str, str]] = []

    if lock is None:
        core = S.core_sql(m) + "\n" + (MODELER_DIR / "model_change_requests.sql").read_text(encoding="utf-8")
        for name, text in (("appforge_core", core), ("appforge_structure", S.structure_sql(m)),
                           ("appforge_behavior", S.behavior_sql(m))):
            stamp = next_stamp(root, used)
            used.append(stamp)
            migrations.append((f"supabase/migrations/{stamp}_{name}.sql", text))
        result["ops"].append("INITIAL generation")
        evolution = 0
    else:
        # Re-normalise the stored raw model with the current normaliser, so that a newer
        # generator never mistakes its own normalisation changes for model changes.
        old = M.normalize(lock["raw"]) if "raw" in lock else lock["model"]
        upgraded = lock.get("generator_version") != GENERATOR_VERSION
        if without_ui(old) == without_ui(m) and not (rebuild_behavior or upgraded):
            result["ops"].append("model unchanged: no migration" if old == m else "UI mapping changed: artefacts only, no migration")
            evolution = lock.get("evolution", 0)
        else:
            evolution = lock.get("evolution", 0) + 1
            delta = D.compute(old, m)
            result["ops"] += delta.ops or [("behaviour rebuilt with generator " + GENERATOR_VERSION) if old == m else "behaviour-only change"]
            pre_ops = [o for o in delta.manual if o.get("phase", "pre") == "pre"]
            post_ops = [o for o in delta.manual if o.get("phase") == "post"]
            result["manual"] = delta.manual
            if pre_ops:
                stamp = next_stamp(root, used)
                used.append(stamp)
                migrations.append((f"supabase/migrations/{stamp}_manual_evolve_{evolution}.sql", manual_migration_text(pre_ops, evolution, "pre")))
            if delta.pre:
                stamp = next_stamp(root, used)
                used.append(stamp)
                migrations.append((f"supabase/migrations/{stamp}_appforge_evolve_{evolution}_types.sql",
                                   S.HEADER + "-- Enum values first: they must be committed before use.\n" + "\n".join(delta.pre) + "\n"))
            stamp = next_stamp(root, used)
            used.append(stamp)
            body = S.HEADER + f"-- Evolution #{evolution}\n-- " + "\n-- ".join(delta.ops or ["behaviour only"]) + "\n\n"
            if delta.auto:
                body += "-- ---------------- structure (additive) ----------------\n" + "\n".join(delta.auto) + "\n\n"
            body += "-- ---------------- behaviour (full regeneration) ----------------\n" + S.behavior_sql(m).replace(S.HEADER, "")
            migrations.append((f"supabase/migrations/{stamp}_appforge_evolve_{evolution}.sql", body))
            if post_ops:
                stamp = next_stamp(root, used)
                used.append(stamp)
                migrations.append((f"supabase/migrations/{stamp}_manual_evolve_{evolution}_post.sql", manual_migration_text(post_ops, evolution, "post")))

    artefacts = {
        "src/lib/model.ts": T.model_ts(m),
        "src/lib/events/catalog.ts": T.catalog_ts(m),
        "docs/domain.md": T.domain_md(m),
        "src/lib/appforge/metamodel.json": metamodel_json(root, m),
        "public/appforge/metamodel-editor.js": (MODELER_DIR / "metamodel-editor.js").read_text(encoding="utf-8"),
    }
    if dry_run:
        result["migrations"] = [{"path": p, "text": t} for p, t in migrations]
        result["files"] = list(artefacts)
        return result

    hashes = dict((lock or {}).get("generated", {}))
    mig_hashes = dict((lock or {}).get("migrations", {}))
    for path, text in migrations:
        h = _write(root, path, text)
        if "_manual_" in path:
            result["migrations"].append(path)
            continue
        mig_hashes[path] = h
        result["migrations"].append(path)
    for path, text in artefacts.items():
        hashes[path] = _write(root, path, text)
        result["files"].append(path)
    msgs = T.messages(m)
    for loc, ns in msgs.items():
        mf = root / "messages" / f"{loc}.json"
        existing = json.loads(mf.read_text(encoding="utf-8")) if mf.exists() else {}
        mf.parent.mkdir(parents=True, exist_ok=True)
        mf.write_text(json.dumps(T.merge_messages(existing, ns), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["files"].append(f"messages/{loc}.json (model namespace)")

    schema = PLUGIN_ROOT / "schema" / "app.schema.json"
    if schema.exists():
        (root / ".appforge").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(schema, root / ".appforge" / "app.schema.json")
    stubs = sorted({r["handler"] for r in m["reactions"] if r.get("do") == "custom"})
    new_lock = {
        "generator_version": GENERATOR_VERSION,
        "generated_at": now_utc().isoformat(),
        "evolution": evolution,
        "model": m,
        "raw": M.load(root / MODEL_FILE),
        "model_sha": sha((root / MODEL_FILE).read_text(encoding="utf-8")
                         + ((root / METAMODEL_FILE).read_text(encoding="utf-8") if (root / METAMODEL_FILE).exists() else "")),
        "migrations": mig_hashes,
        "generated": hashes,
        "custom_handlers": stubs,
    }
    write_lock(root, new_lock)
    try:
        register(root, m, last_generated=new_lock["generated_at"], generator_version=GENERATOR_VERSION,
                 evolution=evolution)
    except ProjectError as exc:
        result["warnings"].append(str(exc))
    return result


# --------------------------------------------------------------------------- #
# Status / check
# --------------------------------------------------------------------------- #
def status(root: Path) -> dict[str, Any]:
    root = root.resolve()
    out: dict[str, Any] = {"path": str(root), "problems": [], "notes": []}
    try:
        m, rep = M.load_and_validate(root / MODEL_FILE)
        out["slug"] = m["app"]["slug"]
        out["name"] = m["app"]["name"]
        out["model_valid"] = rep.ok
        if not rep.ok:
            out["problems"].append(f"model has {len(rep.errors)} error(s): run /appforge:validate")
    except M.ModelError as exc:
        out["problems"].append(str(exc))
        return out
    lock = read_lock(root)
    if not lock:
        out["generated"] = False
        out["notes"].append("never generated: run /appforge:generate")
        return out
    out["generated"] = True
    out["evolution"] = lock.get("evolution", 0)
    out["generator_version"] = lock.get("generator_version")
    out["last_generated"] = lock.get("generated_at")
    old = M.normalize(lock["raw"]) if "raw" in lock else lock["model"]
    out["model_changed"] = rep.ok and old != m
    if out["model_changed"]:
        out["notes"].append("the model changed since the last generation: run /appforge:generate")
    if lock.get("generator_version") != GENERATOR_VERSION:
        out["notes"].append(f"generated with appforge {lock.get('generator_version')}, plugin is {GENERATOR_VERSION}: /appforge:upgrade")
    for path, h in {**lock.get("generated", {}), **lock.get("migrations", {})}.items():
        p = root / path
        if not p.exists():
            out["problems"].append(f"generated file missing: {path}")
        elif sha(p.read_text(encoding="utf-8")) != h:
            out["problems"].append(f"generated file edited by hand: {path} (change the model instead)")
    for f in sorted((root / "supabase" / "migrations").glob("*_manual_evolve_*.sql")) if (root / "supabase" / "migrations").exists() else []:
        if "TODO(appforge)" in f.read_text(encoding="utf-8"):
            out["problems"].append(f"manual migration to complete: {f.relative_to(root)}")
    # i18n parity
    locales = m["app"]["locales"]
    keysets = {}
    for loc in locales:
        mf = root / "messages" / f"{loc}.json"
        if mf.exists():
            keysets[loc] = set(_flatten(json.loads(mf.read_text(encoding="utf-8"))))
        else:
            out["problems"].append(f"missing messages/{loc}.json")
    if len(keysets) > 1:
        base = keysets[locales[0]]
        for loc, ks in keysets.items():
            missing = sorted(base - ks)[:10]
            extra = sorted(ks - base)[:10]
            if missing:
                out["problems"].append(f"messages/{loc}.json lacks keys: {', '.join(missing)}")
            if extra:
                out["problems"].append(f"messages/{loc}.json has keys missing in {locales[0]}: {', '.join(extra)}")
    return out


def _flatten(d: Any, prefix: str = "") -> list[str]:
    if not isinstance(d, dict):
        return [prefix]
    out = []
    for k, v in d.items():
        out += _flatten(v, f"{prefix}.{k}" if prefix else k)
    return out


def check_db(root: Path, dsn_admin: str | None = None) -> tuple[bool, str]:
    """Applies every migration to a scratch PostgreSQL database (with Supabase stubs)."""
    import subprocess
    import tempfile
    import uuid

    psql = shutil.which("psql")
    if not psql:
        return False, "psql not found: install the PostgreSQL client, or run `supabase db reset` instead"
    name = "appforge_check_" + uuid.uuid4().hex[:8]
    env = dict(os.environ)
    base = dsn_admin or os.environ.get("APPFORGE_PG", "")
    conn = (lambda db: [psql, base.rsplit("/", 1)[0] + "/" + db] if base else [psql, "-d", db])
    def run(args: list[str], db: str = "postgres") -> subprocess.CompletedProcess:
        return subprocess.run(conn(db) + ["-v", "ON_ERROR_STOP=1", "-q"] + args, capture_output=True, text=True,
                              env={**env, "PGOPTIONS": "-c client_min_messages=warning"})
    r = run(["-c", f"create database {name}"])
    if r.returncode != 0:
        return False, "cannot create a scratch database: " + r.stderr.strip() + "\nSet APPFORGE_PG=postgresql://user:pass@host:5432/postgres"
    log = []
    ok = True
    try:
        files = [Path(__file__).parent / "testing" / "supabase_stub.sql"]
        files += sorted((root / "supabase" / "migrations").glob("*.sql"))
        tmp = Path(tempfile.mkdtemp())
        for f in files:
            copy = tmp / f.name
            shutil.copyfile(f, copy)
            os.chmod(copy, 0o644)
            os.chmod(tmp, 0o755)
            r = run(["-1", "-f", str(copy)], name)
            if r.returncode != 0:
                ok = False
                log.append(f"FAILED {f.name}\n{r.stderr.strip()}")
                break
            log.append(f"ok {f.name}")
        seed = root / "supabase" / "seed.sql"
        if ok and seed.exists():
            copy = tmp / "seed.sql"
            shutil.copyfile(seed, copy)
            os.chmod(copy, 0o644)
            r = run(["-1", "-f", str(copy)], name)
            log.append("ok seed.sql" if r.returncode == 0 else f"FAILED seed.sql\n{r.stderr.strip()}")
            ok = ok and r.returncode == 0
    finally:
        run(["-c", f"drop database if exists {name}"])
    return ok, "\n".join(log)
