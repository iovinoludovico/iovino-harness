"""Regression tests of the generator: python3 -m unittest discover -s scripts/tests

Set APPFORGE_PG=postgresql://user:pass@host:5432/postgres to also apply the
generated migrations to a scratch database.
"""

import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

from appforge import diff as D  # noqa: E402
from appforge import ecore as E  # noqa: E402
from appforge import model as M  # noqa: E402
from appforge import project as P  # noqa: E402

EXAMPLES = sorted((ROOT / "examples").glob("*/app.yaml"))
WORKFLOW_EXAMPLE = ROOT / "examples" / "guest-invitations" / "app.yaml"


class ModelTests(unittest.TestCase):
    def test_examples_are_valid(self):
        self.assertTrue(EXAMPLES)
        for ex in EXAMPLES:
            _, rep = M.load_and_validate(ex)
            self.assertTrue(rep.ok, f"{ex}: {rep.render()}")

    def test_semantic_errors_are_reported(self):
        raw = M.load(WORKFLOW_EXAMPLE)
        bad = copy.deepcopy(raw)
        inv = next(e for e in bad["entities"].values() if e.get("workflow"))
        inv["workflow"]["transitions"]["ghost"] = {"from": "nowhere", "to": "missing", "by": ["nobody"]}
        bad["reactions"].append({"name": "x", "on": "nope.created", "do": "notify"})
        rep = M.validate(M.normalize(bad))
        text = rep.render()
        for needle in ("unknown target state", "unknown source state", "unknown principal", "unknown event"):
            self.assertIn(needle, text)

    def test_reaction_cycle_is_detected(self):
        raw = {"app": {"name": "Cyc", "slug": "cyc"}, "entities": {"Ticket": {"fields": {"n": {"type": "int"}}}},
               "reactions": [{"name": "loop", "on": "ticket.updated", "do": "set", "set": {"n": 1}}]}
        rep = M.validate(M.normalize(raw))
        self.assertTrue(any("cycle" in e for e in rep.errors), rep.render())

    def test_yaml_on_key(self):
        raw = M.loads("app: {name: X}\nentities: {A: {fields: {n: string}}}\nreactions:\n  - on: a.created\n    do: broadcast\n    channel: c\n")
        self.assertEqual(raw["reactions"][0]["on"], "a.created")


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ["APPFORGE_HOME"] = str(Path(self.tmp.name) / "home")

    def tearDown(self):
        self.tmp.cleanup()

    def _new(self, example: Path) -> Path:
        target = Path(self.tmp.name) / example.parent.name
        P.scaffold(target, example)
        P.generate(target)
        return target

    def test_new_app_and_status(self):
        for ex in EXAMPLES:
            app = self._new(ex)
            st = P.status(app)
            self.assertEqual(st["problems"], [], st)
            self.assertFalse(st["model_changed"], f"{ex}: lock does not round-trip the model")
            again = P.generate(app)
            self.assertEqual(again["migrations"], [], again["ops"])
            self.assertTrue((app / "src/lib/model.ts").exists())
            msgs = json.loads((app / "messages/it.json").read_text())
            self.assertIn("model", msgs)
            self.assertEqual(len(list((app / "supabase/migrations").glob("*.sql"))), 3)

    def test_evolution_additive_and_manual(self):
        app = self._new(EXAMPLES[0])
        meta = E.load(app / "domain.ecore.yaml")      # every new app is split: structure in the metamodel
        cls = next(c for c in meta["classes"].values() if c.get("attributes"))
        first = next(iter(cls["attributes"]))
        cls["attributes"]["extraNote"] = "Text"
        cls["attributes"]["mustHave"] = {"type": "EString", "lower": 1}
        del cls["attributes"][first]
        E.dump(meta, app / "domain.ecore.yaml")
        res = P.generate(app)
        names = [Path(p).name for p in res["migrations"]]
        self.assertTrue(any("_manual_evolve_1.sql" in n for n in names), names)
        self.assertTrue(any("_manual_evolve_1_post.sql" in n for n in names), names)
        self.assertTrue(any("_appforge_evolve_1.sql" in n for n in names), names)
        st = P.status(app)
        self.assertTrue(any("manual migration to complete" in p for p in st["problems"]))

    def test_rename_is_automatic(self):
        old = M.normalize(M.load(EXAMPLES[0]))
        raw = M.load(EXAMPLES[0])
        ent_name, ent = next((n, e) for n, e in raw["entities"].items() if e.get("fields"))
        k0 = next(iter(ent["fields"]))
        spec = ent["fields"].pop(k0)
        spec = {"type": spec} if isinstance(spec, str) else dict(spec)
        spec["renamed_from"] = k0
        ent["fields"]["renamed_" + k0] = spec
        delta = D.compute(old, M.normalize(raw))
        self.assertFalse(delta.manual, delta.manual)
        self.assertTrue(any(op.startswith("RENAME field") for op in delta.ops), delta.ops)

    def test_guard_blocks_generated_files(self):
        app = self._new(EXAMPLES[0])
        cli = [sys.executable, str(ROOT / "scripts/appforge.py"), "guard", "pre"]
        blocked = subprocess.run(cli, input=json.dumps({"tool_input": {"file_path": str(app / "src/lib/model.ts")}}),
                                 text=True, capture_output=True)
        self.assertEqual(blocked.returncode, 2)
        free = subprocess.run(cli, input=json.dumps({"tool_input": {"file_path": str(app / "src/app/layout.tsx")}}),
                              text=True, capture_output=True)
        self.assertEqual(free.returncode, 0)

    @unittest.skipUnless(os.environ.get("APPFORGE_PG"), "APPFORGE_PG not set")
    def test_migrations_apply(self):
        for ex in EXAMPLES:
            app = self._new(ex)
            ok, log = P.check_db(app)
            self.assertTrue(ok, log)


if __name__ == "__main__":
    unittest.main()
