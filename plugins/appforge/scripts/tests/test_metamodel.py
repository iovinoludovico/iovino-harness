"""Metamodel (domain.ecore.yaml), UI mapping, proposals, reverse engineering and drift.

python3 -m unittest discover -s scripts/tests   (APPFORGE_PG=postgresql://… enables the database tests)
"""

import argparse
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from appforge import dbschema as D  # noqa: E402
from appforge import ecore as E  # noqa: E402
from appforge import mmcli  # noqa: E402
from appforge import model as M  # noqa: E402
from appforge import project as P  # noqa: E402
from appforge import ui as U  # noqa: E402

FIXTURE = ROOT / "scripts" / "tests" / "fixtures" / "anagrafica.ecore.yaml"
GUEST = ROOT / "examples" / "guest-invitations"
ACS = ROOT / "examples" / "acs" / "app.yaml"


def _strip_order(m):
    m = copy.deepcopy(m)
    for e in m["entities"].values():
        for f in e["fields"].values():
            f.pop("order", None)
        e["fields"] = dict(sorted(e["fields"].items()))
        e.pop("ui", None)
    return m


def storage(meta, behaviour=None):
    rep = M.Report()
    m = M.normalize(E.compose(meta, behaviour or {"app": {"name": "t", "slug": "t-app"}}, rep))
    return m, rep


class NotationTests(unittest.TestCase):
    def test_fixture_is_valid_and_round_trips(self):
        meta = E.load(FIXTURE)
        self.assertTrue(E.validate(meta).ok, E.validate(meta).render())
        self.assertEqual(E.expand(E.loads(E.dumps(meta))), E.expand(meta))
        back = E.expand(E.import_ecore(E.export_ecore(meta)))
        self.assertEqual(back["classes"], E.expand(meta)["classes"])
        self.assertEqual(back["enums"], E.expand(meta)["enums"])

    def test_storage_mapping(self):
        m, rep = storage(E.load(FIXTURE))
        self.assertTrue(rep.ok, rep.render())
        ents = m["entities"]
        self.assertNotIn("Soggetto", ents)                                  # abstract: no table
        self.assertEqual(ents["Persona"]["table"], "persone")                # language: it
        self.assertEqual(ents["Indirizzo"]["table"], "indirizzi")
        self.assertEqual(ents["Account"]["table"], "account")
        p = ents["Persona"]["fields"]
        self.assertIn("nome", p)                                            # inherited from Soggetto
        self.assertEqual(p["codice_fiscale"]["unique"], True)               # id attribute
        self.assertEqual(ents["Persona"]["display"], "codice_fiscale")
        self.assertTrue(p["account"]["required"] and p["account"]["unique"])  # one-to-one on the mandatory side
        self.assertNotIn("persona", ents["Account"]["fields"])              # the other end has no column
        self.assertTrue(p["gruppi"]["many"])                                # many-to-many owned by Persona
        self.assertNotIn("membri", ents["Gruppo"]["fields"])
        ind = ents["Indirizzo"]["fields"]["persona"]                         # containment with opposite
        self.assertEqual((ind["required"], ind["on_delete"]), (True, "cascade"))
        alle = ents["Allegato"]["fields"]["gruppo"]                          # containment without opposite
        self.assertEqual((alle["to"], alle["on_delete"]), ("Gruppo", "cascade"))
        self.assertEqual(p["ruolo"]["default"], "staff")                    # literal STAFF → staff
        self.assertEqual(m["enums"]["Ruolo"]["values"][2]["label"]["it"], "Ospite esterno")

    def test_errors_are_reported(self):
        cases = {
            "polymorphic": ({"classes": {"A": {"abstract": True}, "B": {"supertypes": ["A"]}, "C": {"supertypes": ["A"]},
                                         "D": {"references": {"a": "A"}}}}, "polymorphic"),
            "unknown type": ({"classes": {"A": {"attributes": {"x": "Strin"}}}}, "unknown data type"),
            "class as attribute": ({"classes": {"A": {}, "B": {"attributes": {"a": "A"}}}}, "declare it under references"),
            "opposite": ({"classes": {"A": {"references": {"b": {"type": "B", "opposite": "a"}}},
                                      "B": {"references": {"a": {"type": "A", "opposite": "x"}}}}}, "must declare opposite"),
            "behaviour in metamodel": ({"classes": {"A": {"workflow": {}}}}, "behaviour"),
            "reserved": ({"classes": {"A": {"attributes": {"createdAt": "EDate"}}}}, "standard column"),
            "user declared": ({"classes": {"User": {}}}, "built in"),
            "cycle": ({"classes": {"A": {"supertypes": ["B"]}, "B": {"supertypes": ["A"]}}}, "cycle"),
        }
        for name, (raw, needle) in cases.items():
            raw = {"package": "t", **raw}
            self.assertIn(needle, E.validate(raw).render(), name)

    def test_fields_in_app_yaml_are_rejected(self):
        rep = M.Report()
        E.compose(E.load(FIXTURE), {"app": {"slug": "x"}, "entities": {"Persona": {"fields": {"x": "string"}},
                                                                         "Ghost": {}}}, rep)
        text = rep.render()
        self.assertIn("declared in the metamodel", text)
        self.assertIn("not a class of the metamodel", text)

    def test_legacy_split_preserves_the_model(self):
        raw = M.load_file(ACS)
        meta, beh = E.extract(raw)
        self.assertTrue(E.validate(meta).ok)
        self.assertEqual(_strip_order(M.normalize(E.compose(meta, beh))), _strip_order(M.normalize(raw)))

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


class UiTests(unittest.TestCase):
    def test_defaults_and_overrides(self):
        m, rep = M.load_and_validate(GUEST / "app.yaml")
        self.assertTrue(rep.ok, rep.render())
        inv = m["entities"]["Invitation"]["ui"]
        self.assertEqual(inv["view"], "kanban")
        self.assertEqual(inv["calendar"], {"start": "start_date", "end": "end_date"})
        self.assertEqual(inv["widgets"]["accommodation"], "radio")          # 3 literals
        self.assertEqual(inv["widgets"]["hourly_rate"], "currency")
        self.assertEqual(inv["widgets"]["funds"], "ref-checklist")
        self.assertEqual(m["entities"]["Guest"]["ui"]["related"], [{"entity": "invitation", "field": "guest"}])

    def test_containment_shows_parts_and_suggestions(self):
        m, _ = storage(E.load(FIXTURE))
        self.assertEqual(m["entities"]["Persona"]["ui"]["related"], [{"entity": "indirizzo", "field": "persona"}])
        legacy = M.normalize(M.load_file(ACS))
        whats = {(s["entity"], s["what"]) for s in U.suggest(legacy)}
        self.assertIn(("Office", "kanban by status"), whats)
        self.assertIn(("Occupant", "cards view"), whats)

    def test_invalid_ui(self):
        raw = M.load(GUEST / "app.yaml")
        raw["entities"]["Guest"]["ui"] = {"widgets": {"email": "slider", "nope": "text"}, "views": ["calendar"],
                                          "calendar": {"start": "email"}}
        text = M.validate(M.normalize(raw)).render()
        self.assertIn("cannot render a email field", text)
        self.assertIn("unknown field 'nope'", text)
        self.assertIn("is not a date/datetime field", text)


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["APPFORGE_HOME"] = str(Path(self.tmp.name) / "home")

    def tearDown(self):
        self.tmp.cleanup()

    def _app(self, example: Path) -> Path:
        target = Path(self.tmp.name) / f"app-{uuid.uuid4().hex[:6]}"
        P.scaffold(target, example)
        P.generate(target)
        return target

    def test_new_app_is_split_and_ships_the_modeler(self):
        app = self._app(ACS)                                               # single-file model → split on scaffold
        self.assertTrue((app / "domain.ecore.yaml").exists())
        self.assertNotIn("fields", json.dumps(M.load_file(app / "app.yaml")))
        doc = json.loads((app / "src/lib/appforge/metamodel.json").read_text())
        self.assertIn("behaviour", doc)
        self.assertTrue((app / "public/appforge/metamodel-editor.js").exists())
        self.assertTrue((app / "src/components/appforge/metamodel-modeler.tsx").exists())
        core = next((app / "supabase/migrations").glob("*_appforge_core.sql")).read_text()
        self.assertIn("model_change_requests", core)
        self.assertEqual(P.status(app)["problems"], [])

    def test_ui_only_change_needs_no_migration(self):
        app = self._app(GUEST / "app.yaml")
        raw = M.load_file(app / "app.yaml")
        raw["entities"]["Invitation"]["ui"]["view"] = "table"
        M.dump(raw, app / "app.yaml")
        res = P.generate(app)
        self.assertEqual(res["migrations"], [])
        self.assertIn("UI mapping changed", res["ops"][0])

    def test_proposal_apply_and_guard(self):
        app = self._app(GUEST / "app.yaml")
        doc = json.loads((app / "src/lib/appforge/metamodel.json").read_text())
        doc["classes"]["Guest"]["attributes"]["phone"] = {"type": "EString", "lower": 0, "upper": 1}
        prop_dir = app / ".appforge" / "proposals"
        prop_dir.mkdir(parents=True)
        (prop_dir / "p1.json").write_text(json.dumps({"note": "phone", "metamodel": doc}))
        ns = argparse.Namespace(path=str(app), proposal=None, write=True)
        self.assertEqual(mmcli.cmd_apply(ns), 0)
        self.assertIn("phone", (app / "domain.ecore.yaml").read_text())
        self.assertTrue((prop_dir / "applied" / "p1.json").exists())
        # removing a field used by a workflow guard is refused
        bad = json.loads((app / "src/lib/appforge/metamodel.json").read_text())
        del bad["classes"]["Invitation"]["attributes"]["endDate"]
        (app / "bad.json").write_text(json.dumps({"metamodel": bad}))
        self.assertEqual(mmcli.cmd_apply(argparse.Namespace(path=str(app), proposal=str(app / "bad.json"), write=True)), 1)
        self.assertIn("endDate", (app / "domain.ecore.yaml").read_text())

    @unittest.skipUnless(shutil.which("node"), "node not installed")
    def test_check_model_script(self):
        app = self._app(GUEST / "app.yaml")
        run = lambda: subprocess.run(["node", "scripts/check-model.mjs"], cwd=app, capture_output=True, text=True)  # noqa: E731
        self.assertEqual(run().returncode, 0, run().stderr)
        meta = E.load(app / "domain.ecore.yaml")
        meta["classes"]["Guest"]["attributes"]["phone"] = "EString"
        E.dump(meta, app / "domain.ecore.yaml")
        out = run()
        self.assertEqual(out.returncode, 1)
        self.assertIn("changed after the last generation", out.stderr)
        P.generate(app)
        self.assertEqual(run().returncode, 0)

    def test_install_kit_in_existing_app(self):
        app = Path(self.tmp.name) / "existing"
        app.mkdir()
        (app / "package.json").write_text("{}")
        shutil.copyfile(FIXTURE, app / "domain.ecore.yaml")
        written = mmcli.install_kit(app)
        self.assertIn("public/appforge/metamodel-editor.js", written)
        self.assertTrue(any(w.endswith("_model_change_requests.sql") for w in written))
        self.assertTrue((app / "src/lib/appforge/metamodel.json").exists())


@unittest.skipUnless(os.environ.get("APPFORGE_PG"), "APPFORGE_PG not set")
class DatabaseTests(unittest.TestCase):
    SCHEMA = """
    create type booking_status as enum ('draft', 'confirmed');
    create table profiles (id uuid primary key);
    create table rooms (id uuid primary key default gen_random_uuid(), name varchar(80) not null unique, seats int);
    create table bookings (id uuid primary key default gen_random_uuid(),
      room_id uuid not null references rooms(id) on delete restrict,
      owner_id uuid references profiles(id), status booking_status not null default 'draft',
      starts_on date not null, kind text check (kind in ('lesson', 'meeting')), notes text);
    create table booking_items (id uuid primary key default gen_random_uuid(),
      booking_id uuid not null references bookings(id) on delete cascade, label text not null);
    create table tags (id uuid primary key default gen_random_uuid(), name text not null);
    create table bookings_tags (booking_id uuid references bookings(id) on delete cascade,
      tag_id uuid references tags(id) on delete cascade, primary key (booking_id, tag_id));
    """

    def setUp(self):
        self.base = os.environ["APPFORGE_PG"]
        self.db = f"af_{uuid.uuid4().hex[:8]}"
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
