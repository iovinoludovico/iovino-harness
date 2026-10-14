"""appforge Studio: local web UI to manage the generated applications and edit
their domain model graphically (entities, workflows, events, reactions).

The Studio is a thin layer over the same functions used by the CLI and the
plugin commands: the model file (app.yaml) stays the single source of truth.
It listens on 127.0.0.1 only and requires a per-session token on every API call.
"""

from __future__ import annotations

import json
import secrets
import shutil
import threading
import traceback
import webbrowser
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from . import model as M
from . import project as P

STATIC = Path(__file__).resolve().parents[2] / "studio"
LAYOUT = ".appforge/studio-layout.json"


def _app_root(slug: str | None) -> Path:
    if not slug:
        raise P.ProjectError("missing app")
    return P.resolve_app(slug)


def _layout(root: Path) -> dict[str, Any]:
    f = root / LAYOUT
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"entities": {}, "workflows": {}}


def _model_payload(root: Path) -> dict[str, Any]:
    """app.yaml (behaviour) composed with domain.ecore.yaml when the app is split."""
    from . import ecore as E
    text = (root / P.MODEL_FILE).read_text(encoding="utf-8")
    meta_file = root / E.METAMODEL_FILE
    split = meta_file.exists()
    raw = M.loads(text)
    meta = E.load(meta_file) if split else E.extract(raw)[0]
    if split:
        raw = E.compose(meta, raw)
    payload = {"root": str(root), "yaml": text, "raw": raw, "layout": _layout(root), "split": split, **_analyse(raw)}
    doc = E.runtime_json(meta)
    if payload.get("normalized"):
        doc["behaviour"] = E.behaviour_summary(payload["normalized"])
    payload["metamodel"] = doc
    return payload


def _behaviour_only(root: Path, raw: dict[str, Any]) -> dict[str, Any]:
    """Drops from a composed model what belongs to the metamodel (fields, enums, class labels)."""
    from . import ecore as E
    meta = E.expand(E.load(root / E.METAMODEL_FILE))
    out = {k: v for k, v in raw.items() if k not in ("entities", "enums")}
    ents = {}
    for name, spec in (raw.get("entities") or {}).items():
        cls = meta["classes"].get(name, {})
        rest = {k: v for k, v in (spec or {}).items() if k != "fields"}
        for k_ent, k_meta in (("label", "label"), ("plural", "plural"), ("table", "table"), ("description", "doc")):
            if k_ent in rest and rest[k_ent] == cls.get(k_meta):
                del rest[k_ent]
        if meta.get("language") == "it" and "table" in rest and rest["table"] == E.default_table(name, "it"):
            del rest["table"]
        if rest:
            ents[name] = rest
    if ents:
        out["entities"] = ents
    return out


def _analyse(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalised model + validation report + event list for the UI."""
    try:
        norm = M.normalize(raw)
        rep = M.validate(norm)
        events = sorted(M.all_events(norm).keys())
        return {"normalized": norm, "errors": rep.errors, "warnings": rep.warnings, "events": events}
    except Exception as exc:  # malformed shapes while editing
        return {"normalized": None, "errors": [f"model: {exc}"], "warnings": [], "events": []}


def _apps() -> list[dict[str, Any]]:
    reg = P.read_registry()
    rows = []
    for slug, e in sorted(reg["apps"].items()):
        p = Path(e["path"])
        if not (p / P.MODEL_FILE).exists():
            rows.append({**e, "state": "missing", "problems": [f"{p} not found"]})
            continue
        st = P.status(p)
        state = ("problems" if st["problems"] else "changed" if st.get("model_changed")
                 else "new" if not st.get("generated") else "ok")
        rows.append({**e, "state": state, "evolution": st.get("evolution"), "problems": st["problems"], "notes": st["notes"]})
    return rows


class Handler(BaseHTTPRequestHandler):
    token = ""
    server_version = "appforge-studio/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # quiet
        pass

    # ------------------------------------------------------------------ io
    def _send(self, status: int, body: bytes, ctype: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj: Any, status: int = 200) -> None:
        self._send(status, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"), "application/json; charset=utf-8")

    def _body(self) -> dict[str, Any]:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}") if n else {}

    def _authorised(self) -> bool:
        return secrets.compare_digest(self.headers.get("X-Studio-Token", ""), self.token)

    # ------------------------------------------------------------- routing
    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path in ("/", "/index.html"):
            html = (STATIC / "index.html").read_text(encoding="utf-8")
            self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            return
        if url.path == "/static/metamodel-editor.js":
            f = STATIC.parent / "modeler" / "metamodel-editor.js"
            self._send(200, f.read_bytes(), "text/javascript; charset=utf-8")
            return
        if url.path.startswith("/static/"):
            f = (STATIC / url.path[len("/static/"):]).resolve()
            if STATIC in f.parents and f.exists():
                ctype = {".js": "text/javascript", ".css": "text/css", ".json": "application/json"}.get(f.suffix, "application/octet-stream")
                self._send(200, f.read_bytes(), ctype + "; charset=utf-8")
                return
            self._send(404, b"not found", "text/plain")
            return
        self._api("GET", url)

    def do_POST(self) -> None:  # noqa: N802
        self._api("POST", urlparse(self.path))

    def do_PUT(self) -> None:  # noqa: N802
        self._api("PUT", urlparse(self.path))

    def _api(self, method: str, url) -> None:
        if not url.path.startswith("/api/"):
            self._send(404, b"not found", "text/plain")
            return
        if not self._authorised():
            self._json({"error": "invalid studio token: reopen the URL printed by /appforge:studio"}, 403)
            return
        qs = {k: v[0] for k, v in parse_qs(url.query).items()}
        route = f"{method} {url.path}"
        try:
            if route == "GET /api/apps":
                self._json({"apps": _apps(), "registry": str(P.registry_path())})
            elif route == "GET /api/model":
                self._json(_model_payload(_app_root(qs.get("app"))))
            elif route == "POST /api/validate":
                b = self._body()
                raw = b["raw"] if "raw" in b else M.loads(b.get("yaml", ""))
                self._json({"raw": raw, **_analyse(raw)})
            elif route == "POST /api/yaml":
                self._json({"yaml": M.dumps(self._body().get("raw") or {})})
            elif route == "PUT /api/metamodel":
                self._json(self._save_metamodel(_app_root(qs.get("app")), self._body()))
            elif route == "POST /api/extract":
                root = _app_root(qs.get("app"))
                from . import mmcli
                import argparse as _ap
                rc = mmcli.cmd_extract(_ap.Namespace(app=str(root), dry_run=False))
                if rc:
                    raise P.ProjectError("extract failed")
                self._json(_model_payload(root))
            elif route == "PUT /api/model":
                self._json(self._save(_app_root(qs.get("app")), self._body()))
            elif route == "GET /api/status":
                self._json(P.status(_app_root(qs.get("app"))))
            elif route == "POST /api/generate":
                root = _app_root(qs.get("app"))
                b = self._body()
                res = P.generate(root, dry_run=bool(b.get("dry_run")))
                self._json(res)
            elif route == "POST /api/check-db":
                ok, log = P.check_db(_app_root(qs.get("app")))
                self._json({"ok": ok, "log": log})
            elif route == "POST /api/register":
                e = P.register(P.find_project(self._body().get("path", "")))
                self._json({"app": e})
            elif route == "POST /api/unregister":
                self._json({"removed": P.unregister(self._body().get("slug", ""))})
            elif route == "POST /api/new":
                self._json(self._new(self._body()))
            else:
                self._json({"error": f"unknown route {route}"}, 404)
        except (P.ProjectError, M.ModelError) as exc:
            self._json({"error": str(exc)}, 400)
        except Exception as exc:  # pragma: no cover
            self._json({"error": f"{exc.__class__.__name__}: {exc}", "trace": traceback.format_exc()}, 500)

    # ------------------------------------------------------------ actions
    def _save(self, root: Path, b: dict[str, Any]) -> dict[str, Any]:
        mf = root / P.MODEL_FILE
        bak = root / ".appforge" / "app.yaml.bak"
        bak.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(mf, bak)
        if "yaml" in b and b.get("mode") == "yaml":
            raw = M.loads(b["yaml"])          # keeps the author's text (and comments) as typed
            mf.write_text(b["yaml"] if b["yaml"].endswith("\n") else b["yaml"] + "\n", encoding="utf-8")
        else:
            raw = b["raw"]
            from . import ecore as E
            M.dump(_behaviour_only(root, raw) if (root / E.METAMODEL_FILE).exists() else raw, mf)
        if "layout" in b:
            (root / LAYOUT).write_text(json.dumps(b["layout"], ensure_ascii=False, indent=2), encoding="utf-8")
        payload = _model_payload(root)
        payload["saved"] = True
        return payload

    def _save_metamodel(self, root: Path, b: dict[str, Any]) -> dict[str, Any]:
        """Writes domain.ecore.yaml from the web modeler, refusing changes that break app.yaml."""
        from . import ecore as E
        new = E.from_editor(b.get("metamodel") or {})
        rep = E.validate(new)
        if rep.ok and (root / P.MODEL_FILE).exists():
            rep2 = M.validate(M.normalize(E.compose(new, M.load_file(root / P.MODEL_FILE), rep)))
            rep.errors += [f"app.yaml {x}" for x in rep2.errors]
        if not rep.ok:
            raise P.ProjectError("the metamodel cannot be saved:\n" + "\n".join(rep.errors))
        mf = root / E.METAMODEL_FILE
        if mf.exists():
            (root / ".appforge").mkdir(exist_ok=True)
            shutil.copyfile(mf, root / ".appforge" / "domain.ecore.yaml.bak")
        E.dump(new, mf)
        payload = _model_payload(root)
        payload["saved"] = True
        payload["changes"] = b.get("changes", [])
        return payload

    def _new(self, b: dict[str, Any]) -> dict[str, Any]:
        directory = Path(b.get("dir", "")).expanduser()
        if not b.get("dir"):
            raise P.ProjectError("choose a directory for the new app")
        slug = b.get("slug") or directory.name
        raw = {
            "version": 1,
            "app": {"name": b.get("name") or slug, "slug": slug, "description": b.get("description", ""),
                    "locales": ["it", "en"],
                    "auth": {"providers": ["google"], "allowed_domains": [d for d in [b.get("domain")] if d],
                             "approval": "manual", "admins": [a for a in [b.get("admin")] if a]}},
            "roles": {},
            "entities": {"Item": {"label": {"it": "Elemento", "en": "Item"},
                                  "fields": {"name": {"type": "string", "required": True, "label": {"it": "Nome", "en": "Name"}}}}},
        }
        directory.mkdir(parents=True, exist_ok=True)
        if (directory / P.MODEL_FILE).exists():
            raise P.ProjectError(f"{directory} already contains an app.yaml")
        M.dump(raw, directory / P.MODEL_FILE)
        P.scaffold(directory, None)
        res = P.generate(directory)
        P.register(directory)
        return {"slug": slug, "path": str(directory.resolve()), "generate": res}


def serve(port: int = 4321, app: str | None = None, open_browser: bool = True) -> int:
    Handler.token = secrets.token_urlsafe(18)
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{server.server_port}/#token={Handler.token}" + (f"&app={app}" if app else "")
    print(f"appforge Studio on {url}\n(Ctrl+C to stop)", flush=True)
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
