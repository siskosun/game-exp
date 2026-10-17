"""Synthetic regressions for the advisory, not trusted Rehearsal evidence."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "plugins/game-exp/skills/game-exp/scripts/preflight_integration.py"
spec = importlib.util.spec_from_file_location("integration_viability", SCRIPT)
assert spec is not None and spec.loader is not None
preflight = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preflight)


def manifest(issue=7, avoid=None, allowed=None, parent=None):
    return {
        "experiment": {"issue_number": issue},
        "parent": parent or {"experiment": None, "commit": "a" * 40},
        "scope": {"allowed": ["src/**", "test/**"] if allowed is None else allowed,
                  "avoid": [".github/**"] if avoid is None else avoid},
    }


def facts(ancestry=True, actions=True, connector=None):
    return {
        "main_sha": "a" * 40 if ancestry else "b" * 40,
        "parent_is_ancestor_of_main": ancestry,
        "pr_capabilities": {"actions_can_create_pr": actions,
                            "authorized_connector_can_create_pr": connector},
    }


def codes(report):
    return {x["code"] for x in report["findings"]}


class IntegrationPreflightTests(unittest.TestCase):
    def test_scope_globs(self):
        match = preflight.git_glob_match
        self.assertTrue(match("experiments/EXP-7/manifest.yaml", "experiments/**"))
        self.assertTrue(match("experiments/EXP-7/manifest.yaml", "experiments/EXP-7/**"))
        self.assertFalse(match("experiments/EXP-7/manifest.yaml", "experiments/EXP-6/**"))
        self.assertFalse(match("src/nested/game.js", "src/*.js"))
        self.assertTrue(match("README.md", "**/README.md"))

    def test_exp5_parent_not_integrated(self):
        parent = {"experiment": "EXP-1", "commit": "a" * 40}
        x = preflight.assess(manifest(parent=parent), dict(facts(False),
                  parent_experiment_lifecycle="ACTIVE"))
        self.assertEqual(x["verdict"], "BLOCKED")
        self.assertTrue({"PARENT_NOT_IN_MAIN", "UNINTEGRATED_PARENT"} <= codes(x))

    def test_exp6_self_blocked(self):
        x = preflight.assess(manifest(avoid=["experiments/**"]), facts())
        self.assertEqual(x["verdict"], "BLOCKED")
        self.assertIn("SELF_BLOCKING_METADATA", codes(x))

    def test_exp7_metadata_safe(self):
        x = preflight.assess(manifest(avoid=["experiments/EXP-6/**"]), facts())
        self.assertEqual(x["verdict"], "READY")
        self.assertEqual(x["findings"], [])

    def test_pr_fallback_is_warning(self):
        x = preflight.assess(manifest(), facts(actions=False, connector=True))
        self.assertEqual(x["verdict"], "READY_WITH_WARNINGS")
        self.assertIn("PR_CREATION_FALLBACK", codes(x))

    def test_no_pr_creator_blocks(self):
        x = preflight.assess(manifest(), facts(actions=False, connector=False))
        self.assertEqual(x["verdict"], "BLOCKED")

    def test_missing_permission_not_assumed(self):
        x = preflight.assess(manifest(), facts(actions=None))
        self.assertEqual(x["verdict"], "UNVERIFIED")

    def test_missing_ancestry_not_assumed(self):
        x = preflight.assess(manifest(), {"pr_capabilities": {"actions_can_create_pr": True}})
        self.assertEqual(x["verdict"], "UNVERIFIED")
        self.assertIn("ANCESTRY_UNVERIFIED", codes(x))

    def test_conflicting_ancestry_blocks(self):
        x = preflight.assess(manifest(), dict(facts(), parent_is_ancestor_of_main=False))
        self.assertEqual(x["verdict"], "BLOCKED")
        self.assertIn("ANCESTRY_EVIDENCE_CONFLICT", codes(x))

    def test_invalid_input_rejected(self):
        with self.assertRaises(ValueError):
            preflight.assess(manifest(allowed="src/**"), facts())
        with self.assertRaises(ValueError):
            preflight.assess(manifest(), dict(facts(), pr_capabilities={"actions_can_create_pr": 1}))

    def test_real_git_ancestry(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            def git(*args):
                return subprocess.run(["git", "-C", str(repo), *args], check=True,
                                      text=True, stdout=subprocess.PIPE,
                                      stderr=subprocess.PIPE).stdout.strip()
            git("init", "-q")
            git("config", "user.name", "Fixture")
            git("config", "user.email", "fixture@example.test")
            (repo / "seed.txt").write_text("seed", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "seed")
            base = git("rev-parse", "HEAD")
            (repo / "next.txt").write_text("next", encoding="utf-8")
            git("add", ".")
            git("commit", "-qm", "next")
            head = git("rev-parse", "HEAD")
            m = manifest(parent={"commit": base, "experiment": None})
            caps = {"pr_capabilities": {"actions_can_create_pr": True}}
            self.assertEqual(preflight.assess(m, dict(caps, main_sha=head), repo)["verdict"], "READY")
            self.assertIn("PARENT_NOT_IN_MAIN", codes(preflight.assess(
                manifest(parent={"commit": head, "experiment": None}),
                dict(caps, main_sha=base), repo)))

    def test_strict_cli_exit(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = root / "manifest.json"
            s = root / "facts.json"
            m.write_text(json.dumps(manifest(avoid=["experiments/**"])), encoding="utf-8")
            s.write_text(json.dumps(facts()), encoding="utf-8")
            proc = subprocess.run(["python", str(SCRIPT), "--manifest", str(m),
                                   "--snapshot", str(s), "--strict"],
                                  capture_output=True, text=True, check=False)
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(json.loads(proc.stdout)["verdict"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
