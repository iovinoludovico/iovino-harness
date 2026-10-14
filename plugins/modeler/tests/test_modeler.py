"""Metamodel notation, storage mapping, the modeler installed in an app, proposals, reverse and drift.

python3 -m unittest discover -s plugins/modeler/tests   (MODELER_PG=postgresql://… enables the database tests)
"""

import argparse
import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from metamodel import __version__  # noqa: E402
from metamodel import cli  # noqa: E402
from metamodel import dbschema as D  # noqa: E402
from metamodel import ecore as E  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "anagrafica.ecore.yaml"


class NotationTests(unittest.TestCase):
    def test_fixture_is_valid_and_round_trips(self):
        meta = E.load(FIXTURE)
        self.assertTrue(E.validate(meta).ok, E.validate(meta).render())
        self.assertEqual(E.expand(E.loads(E.dumps(meta))), E.expand(meta))
        back = E.expand(E.import_ecore(E.export_ecore(meta)))
        self.assertEqual(back["classes"], E.expand(meta)["classes"])
        self.assertEqual(back["enums"], E.expand(meta)["enums"])

    def test_storage_mapping(self):
        st = E.storage(E.load(FIXTURE))
        ents = st["entities"]
        self.assertNotIn("Soggetto", ents)                                  # abstract: no table
        self.assertEqual(ents["Persona"]["table"], "persone")                # language: it
        self.assertEqual(ents["Indirizzo"]["table"], "indirizzi")
        self.assertEqual(ents["Account"]["table"], "account")
        p = ents["Persona"]["fields"]
        self.assertIn("nome", p)                                            # inherited from Soggetto
        self.assertTrue(p["codice_fiscale"]["unique"])                      # id attribute
        self.assertEqual(ents["Persona"]["display"], "codice_fiscale")
        self.assertTrue(p["account"]["required"] and p["account"]["unique"])  # one-to-one on the mandatory side
        self.assertNotIn("persona", ents["Account"]["fields"])              # the other end has no column
        self.assertTrue(p["gruppi"]["many"])                                # many-to-many owned by Persona
        self.assertNotIn("membri", ents["Gruppo"]["fields"])
        ind = ents["Indirizzo"]["fields"]["persona"]                         # containment with opposite
        self.assertEqual((ind["required"], ind["on_delete"]), (True, "cascade"))
        alle = ents["Allegato"]["fields"]["gruppo"]                          # containment without opposite
        self.assertEqual((alle["to"], alle["on_delete"]), ("Gruppo", "cascade"))
        self.assertEqual(p["utente"]["on_delete"], "set_null")              # optional reference
        self.assertEqual(p["ruolo"]["default"], "staff")                    # literal STAFF → staff
        self.assertEqual(st["enums"]["Ruolo"], ["admin", "staff", "ospite"])

    def test_english_tables(self):
        st = E.storage({"package": "t", "classes": {"BookingItem": {"attributes": {"label": "EString"}}}})
        self.assertEqual(st["entities"]["BookingItem"]["table"], "booking_items")

    def test_errors_are_reported(self):
        cases = {
            "polymorphic": ({"classes": {"A": {"abstract": True}, "B": {"supertypes": ["A"]}, "C": {"supertypes": ["A"]},
                                         "D": {"references": {"a": "A"}}}}, "polymorphic"),
            "unknown type": ({"classes": {"A": {"attributes": {"x": "Strin"}}}}, "unknown data type"),
            "class as attribute": ({"classes": {"A": {}, "B": {"attributes": {"a": "A"}}}}, "declare it under references"),
            "opposite": ({"classes": {"A": {"references": {"b": {"type": "B", "opposite": "a"}}},
                                      "B": {"references": {"a": {"type": "A", "opposite": "x"}}}}}, "must declare opposite"),
            "behaviour in metamodel": ({"classes": {"A": {"workflow": {}}}}, "unknown keys: workflow"),
            "top-level behaviour": ({"classes": {"A": {}}, "roles": []}, "structure only"),
            "reserved": ({"classes": {"A": {"attributes": {"createdAt": "EDate"}}}}, "standard column"),
            "user declared": ({"classes": {"User": {}}}, "built in"),
            "cycle": ({"classes": {"A": {"supertypes": ["B"]}, "B": {"supertypes": ["A"]}}}, "cycle"),
            "column clash": ({"classes": {"A": {"attributes": {"b": "EString"}, "references": {"b": "B"}},
                                          "B": {}}}, "declared twice"),
        }
        for name, (raw, needle) in cases.items():
            self.assertIn(needle, E.validate({"package": "t", **raw}).render(), name)

    def test_common_column_names_are_allowed(self):
        raw = {"package": "t", "classes": {"Item": {"attributes": {"type": "EString", "state": "EString", "data": "JSON"}}}}
        self.assertTrue(E.validate(raw).ok, E.validate(raw).render())

    def test_diff(self):
        old = E.load(FIXTURE)
        new = copy.deepcopy(old)
        new["classes"]["Persona"]["attributes"]["telefono"] = "EString"
        new["classes"]["Persona"]["attributes"]["cf"] = {**new["classes"]["Persona"]["attributes"].pop("codiceFiscale"),
                                                        "renamed_from": "codiceFiscale"}
        del new["classes"]["Allegato"]
        changes = E.diff(old, new)
        self.assertIn("+ Persona.telefono: EString", changes)
        self.assertIn("~ Persona.codiceFiscale renamed to cf", changes)
        self.assertIn("- class Allegato", changes)

    def test_views(self):
        meta = E.load(FIXTURE)
        self.assertIn("val Indirizzo[*]#persona indirizzi;", E.to_emfatic(meta))
        self.assertIn("Soggetto <|-- Persona", E.to_mermaid(meta))

    def test_legacy_ecore_annotations_are_read(self):
        text = E.export_ecore(E.load(FIXTURE)).replace('source="modeler"', 'source="appforge"')
        self.assertEqual(E.expand(E.import_ecore(text))["enums"], E.expand(E.load(FIXTURE))["enums"])


class AppTests(unittest.TestCase):
    """The modeler as part of an application."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.app = Path(self.tmp.name) / "app"
        (self.app / "supabase").mkdir(parents=True)
        (self.app / "package.json").write_text(json.dumps({"name": "app", "scripts": {"dev": "next dev"}}))
        (self.app / "supabase" / "config.toml").write_text('[api]\nport = 55121\n\n[db]\nport = 55122\n')
        (self.app / "domain.ecore.yaml").write_text(FIXTURE.read_text())

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_makes_the_modeler_part_of_the_app(self):
        written = cli.install(self.app)
        for rel in ("public/modeler/metamodel-editor.js", "src/components/modeler/metamodel-modeler.tsx",
                    "src/lib/modeler/metamodel-actions.ts", "src/lib/modeler/access.ts",
                    "src/lib/modeler/metamodel.json", "tools/modeler/modeler.py",
                    "tools/modeler/metamodel/ecore.py", "tools/modeler/vendor/yaml/__init__.py"):
            self.assertTrue((self.app / rel).exists(), rel)
        self.assertTrue(any(w.endswith("_model_change_requests.sql") for w in written))
        self.assertEqual(cli.installed_version(self.app), __version__)
        scripts = json.loads((self.app / "package.json").read_text())["scripts"]
        self.assertEqual(scripts["dev"], "next dev")
        self.assertEqual(scripts["model:drift"], cli.NPM_SCRIPTS["model:drift"])
        doc = json.loads((self.app / "src/lib/modeler/metamodel.json").read_text())
        self.assertIn("Persona", doc["classes"])
        self.assertNotIn("appforge", (self.app / "src/lib/modeler/metamodel-actions.ts").read_text())

    def test_reinstall_upgrades_owned_files_and_keeps_adapted_ones(self):
        cli.install(self.app)
        (self.app / "src/lib/modeler/access.ts").write_text("// adapted to the app\n")
        (self.app / "public/modeler/metamodel-editor.js").write_text("// old\n")
        (self.app / "tools/modeler/VERSION").write_text("0.0.1\n")
        written = cli.install(self.app)
        self.assertEqual((self.app / "src/lib/modeler/access.ts").read_text(), "// adapted to the app\n")
        self.assertIn("customElements", (self.app / "public/modeler/metamodel-editor.js").read_text())
        self.assertEqual(cli.installed_version(self.app), __version__)
        self.assertFalse(any(w.endswith("_model_change_requests.sql") for w in written))   # migration once

    def test_vendored_cli_runs_without_the_plugin(self):
        cli.install(self.app)
        run = lambda *args: subprocess.run([sys.executable, "tools/modeler/modeler.py", *args],  # noqa: E731
                                           cwd=self.app, capture_output=True, text=True)
        out = run("validate")
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("Metamodel OK", out.stdout)
        self.assertIn("persone (Persona)", run("show", "--format", "storage").stdout)
        out = run("install")
        self.assertNotEqual(out.returncode, 0)                               # the kit lives only in the plugin

    def test_local_dsn_from_supabase_config(self):
        self.assertEqual(cli.local_dsn(self.app), "postgresql://postgres:postgres@127.0.0.1:55122/postgres")

    def test_proposal_apply(self):
        cli.install(self.app)
        doc = json.loads((self.app / "src/lib/modeler/metamodel.json").read_text())
        doc["classes"]["Persona"]["attributes"]["telefono"] = {"type": "EString", "lower": 0, "upper": 1}
        prop_dir = self.app / ".modeler" / "proposals"
        prop_dir.mkdir(parents=True)
        (prop_dir / "p1.json").write_text(json.dumps({"note": "telefono", "metamodel": doc}))
        ns = argparse.Namespace(path=str(self.app), proposal=None, write=True)
        self.assertEqual(cli.cmd_apply(ns), 0)
        self.assertIn("telefono", (self.app / "domain.ecore.yaml").read_text())
        self.assertTrue((prop_dir / "applied" / "p1.json").exists())
        self.assertIn("telefono", (self.app / "src/lib/modeler/metamodel.json").read_text())   # synced
        self.assertTrue(list((self.app / ".modeler" / "backups").iterdir()))
        bad = copy.deepcopy(doc)
        bad["classes"]["Persona"]["references"]["account"]["type"] = "Ghost"
        (self.app / "bad.json").write_text(json.dumps({"metamodel": bad}))
        ns = argparse.Namespace(path=str(self.app), proposal=str(self.app / "bad.json"), write=True)
        self.assertEqual(cli.cmd_apply(ns), 1)
        self.assertNotIn("Ghost", (self.app / "domain.ecore.yaml").read_text())


class HookTests(unittest.TestCase):
    HOOK = ROOT / "hooks" / "hook.py"

    def run_hook(self, mode, payload):
        return subprocess.run([sys.executable, str(self.HOOK), mode], input=json.dumps(payload),
                              capture_output=True, text=True)

    def test_invalid_metamodel_is_sent_back(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "domain.ecore.yaml"
            f.write_text("package: t\nclasses:\n  A:\n    attributes: {x: Strin}\n")
            out = self.run_hook("post", {"tool_input": {"file_path": str(f)}})
            self.assertEqual(out.returncode, 2)
            self.assertIn("unknown data type", out.stderr)
            f.write_text(FIXTURE.read_text())
            self.assertEqual(self.run_hook("post", {"tool_input": {"file_path": str(f)}}).returncode, 0)

    def test_migration_reminder_and_session(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "domain.ecore.yaml").write_text(FIXTURE.read_text())
            mig = Path(d) / "supabase" / "migrations" / "20260101000000_x.sql"
            out = self.run_hook("post", {"tool_input": {"file_path": str(mig)}})
            self.assertIn("Update the metamodel", out.stdout)
            out = self.run_hook("session", {"cwd": d})
            self.assertIn("not installed", out.stdout)
            self.assertEqual(self.run_hook("session", {"cwd": tempfile.gettempdir()}).stdout, "")


@unittest.skipUnless(os.environ.get("MODELER_PG"), "MODELER_PG not set")
class DatabaseTests(unittest.TestCase):
    SCHEMA = """
    create type booking_status as enum ('draft', 'confirmed');
    create table profiles (id uuid primary key);
    create table rooms (id uuid primary key default gen_random_uuid(), name varchar(80) not null unique, seats int,
      type text);
    create table bookings (id uuid primary key default gen_random_uuid(),
      room_id uuid not null references rooms(id) on delete restrict,
      owner_id uuid references profiles(id), status booking_status not null default 'draft',
      starts_on date not null, kind text check (kind in ('lesson', 'meeting')), notes text,
      created_at timestamptz not null default now());
    create table booking_items (id uuid primary key default gen_random_uuid(),
      booking_id uuid not null references bookings(id) on delete cascade, label text not null);
    create table tags (id uuid primary key default gen_random_uuid(), name text not null);
    create table bookings_tags (booking_id uuid references bookings(id) on delete cascade,
      tag_id uuid references tags(id) on delete cascade, primary key (booking_id, tag_id));
    """

    def setUp(self):
        self.base = os.environ["MODELER_PG"]
        self.db = f"modeler_{uuid.uuid4().hex[:8]}"
        subprocess.run(["psql", self.base, "-qc", f"create database {self.db}"], check=True, capture_output=True)
        self.dsn = self.base.rsplit("/", 1)[0] + "/" + self.db
        subprocess.run(["psql", self.dsn, "-q", "-v", "ON_ERROR_STOP=1", "-c", self.SCHEMA], check=True, capture_output=True)

    def tearDown(self):
        subprocess.run(["psql", self.base, "-qc", f"drop database {self.db} with (force)"], capture_output=True)

    def test_reverse_and_drift(self):
        cat = D.catalog(self.dsn)
        meta, notes = D.reverse(cat, package="aule")
        self.assertTrue(E.validate(meta).ok, E.validate(meta).render())
        e = E.expand(meta)
        b = e["classes"]["Booking"]
        self.assertEqual(b["attributes"]["status"]["type"], "BookingStatus")
        self.assertEqual(b["attributes"]["kind"]["type"], "Kind")
        self.assertIn("type", e["classes"]["Room"]["attributes"])            # an ordinary column name
        self.assertEqual(b["references"]["room"]["column"], "room_id")
        self.assertEqual(b["references"]["owner"]["type"], "User")
        self.assertTrue(b["references"]["bookingItems"]["containment"])
        self.assertEqual(b["references"]["tags"]["join_table"], "bookings_tags")
        self.assertEqual(D.drift(meta, cat), [])
        e["classes"]["Room"]["attributes"]["floor"] = {"type": "EInt", "lower": 0, "upper": 1}
        e["classes"]["Room"]["attributes"]["seats"]["lower"] = 1
        found = D.drift(E.compact(e), cat)
        self.assertIn("MISSING COLUMN rooms.floor (Room.floor)", found)
        self.assertTrue(any(x.startswith("NULLABLE rooms.seats") for x in found), found)


if __name__ == "__main__":
    unittest.main()
