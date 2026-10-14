"""scripts/release.py: which plugins need a release, at which level, and the release commit."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import release  # noqa: E402


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self.tmp.name)
        self.git("init", "-q", "-b", "main")
        self.git("config", "user.email", "t@example.org")
        self.git("config", "user.name", "Test")
        self.git("config", "commit.gpgsign", "false")
        self.write(".claude-plugin/marketplace.json", json.dumps(
            {"name": "m", "plugins": [{"name": "core", "source": "./plugins/core"},
                                      {"name": "modeler", "source": "./plugins/modeler"}]}))
        for name in ("core", "modeler"):
            self.write(f"plugins/{name}/.claude-plugin/plugin.json",
                       json.dumps({"name": name, "version": "0.1.0", "description": "x"}, indent=2) + "\n")
            self.write(f"plugins/{name}/README.md", "first\n")
        self.write("plugins/modeler/scripts/metamodel/__init__.py", '"""pkg"""\n\n__version__ = "0.1.0"\n')
        self.commit("feat: first version")

    def tearDown(self):
        self.tmp.cleanup()

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.repo, check=True, capture_output=True, text=True).stdout

    def write(self, rel, text):
        p = self.repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def commit(self, msg):
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)

    def run_release(self, *args):
        return release.main(["--repo", str(self.repo), *args])

    def states(self):
        return {s["name"]: s for s in (release.status(self.repo, n) for n in release.plugins(self.repo))}

    def test_nothing_to_release(self):
        self.assertEqual(self.run_release("--check"), 0)
        self.assertEqual(self.states()["core"]["commits"], 0)

    def test_levels_from_conventional_commits(self):
        self.write("plugins/core/README.md", "fix\n")
        self.commit("fix(core): typo")
        self.assertEqual(self.states()["core"]["level"], "patch")
        self.write("plugins/core/README.md", "feature\n")
        self.commit("feat(core): new skill")
        self.assertEqual(self.states()["core"]["level"], "minor")
        self.write("plugins/core/README.md", "breaking\n")
        self.commit("refactor(core)!: rename the skill")
        self.assertEqual(self.states()["core"]["level"], "major")
        self.assertEqual(release.bump("0.1.3", "major"), "0.2.0")     # 0.x: breaking raises the minor
        self.assertEqual(release.bump("1.4.2", "major"), "2.0.0")
        self.assertEqual(release.bump("1.4.2", "minor"), "1.5.0")
        self.assertEqual(release.bump("1.4.2", "patch"), "1.4.3")
        self.assertEqual(self.states()["modeler"]["commits"], 0)       # untouched plugin

    def test_write_raises_versions_and_twins_then_check_passes(self):
        self.write("plugins/modeler/README.md", "changed\n")
        self.commit("feat(modeler): editor warnings")
        self.assertEqual(self.run_release("--check"), 1)
        self.assertEqual(self.run_release("--write"), 0)
        manifest = json.loads((self.repo / "plugins/modeler/.claude-plugin/plugin.json").read_text())
        self.assertEqual(manifest["version"], "0.2.0")
        self.assertIn('__version__ = "0.2.0"', (self.repo / "plugins/modeler/scripts/metamodel/__init__.py").read_text())
        self.assertEqual(json.loads((self.repo / "plugins/core/.claude-plugin/plugin.json").read_text())["version"], "0.1.0")
        self.assertIn("chore(release): modeler 0.2.0", self.git("log", "-1", "--format=%s"))
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.run_release("--check"), 0)

    def test_forced_level(self):
        self.write("plugins/core/README.md", "x\n")
        self.commit("feat(core): x")
        self.assertEqual(self.run_release("--write", "--level", "patch"), 0)
        self.assertEqual(json.loads((self.repo / "plugins/core/.claude-plugin/plugin.json").read_text())["version"], "0.1.1")

    def test_uncommitted_changes_block_the_write(self):
        self.write("plugins/core/README.md", "x\n")
        self.commit("fix(core): x")
        self.write("plugins/core/README.md", "work in progress\n")
        self.assertEqual(self.run_release("--write"), 1)
        self.assertEqual(json.loads((self.repo / "plugins/core/.claude-plugin/plugin.json").read_text())["version"], "0.1.0")

    def test_versions_out_of_sync_are_an_error(self):
        self.write("plugins/modeler/scripts/metamodel/__init__.py", '__version__ = "9.9.9"\n')
        self.commit("chore: drift")
        self.assertEqual(self.run_release("--check"), 1)

    def test_pre_push_hook_blocks_an_unreleased_plugin(self):
        hook = ROOT / ".githooks" / "pre-push"
        self.write("scripts/release.py", (ROOT / "scripts" / "release.py").read_text())
        self.write("plugins/core/README.md", "x\n")
        self.commit("fix(core): x")
        out = subprocess.run(["sh", str(hook)], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(out.returncode, 1)
        self.assertIn("release.py --write", out.stderr)
        self.assertEqual(self.run_release("--write"), 0)
        self.assertEqual(subprocess.run(["sh", str(hook)], cwd=self.repo).returncode, 0)


if __name__ == "__main__":
    unittest.main()
