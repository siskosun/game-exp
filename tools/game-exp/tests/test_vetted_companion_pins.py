"""Vetted release selection prevents accidental unreviewed companion installs."""
from __future__ import annotations
import hashlib
import io
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import companion_skills as m

def source_bytes(name, version):
    data = io.BytesIO()
    entry = f"---\nname: {name}\ndescription: fixture\n---\n"
    with zipfile.ZipFile(data, "w", zipfile.ZIP_DEFLATED) as z:
        p = f"{name}-{version}/"
        z.writestr(p + "SKILL.md", entry)
        z.writestr(p + "VERSION", version + "\n")
        z.writestr(p + "agents/openai.yaml", "interface:\n  display_name: Fixture\n")
    return data.getvalue(), hashlib.sha1((f"blob {len(entry.encode())}\0").encode() + entry.encode()).hexdigest()

class VettedCompanionPinsTest(unittest.TestCase):
    def setUp(self):
        self.entries = {}
        self.archives = {}
        for i, spec in enumerate(m.COMPANION_SKILLS):
            version = "0.2.6" if spec.name.startswith("h5-") else "1.0.7"
            commit_sha = ("a" if i == 0 else "b") * 40
            archive, blob = source_bytes(spec.name, version)
            self.archives[commit_sha] = archive
            self.entries[spec.name] = {
                "repository": spec.repository,
                "version": version,
                "tag": "v" + version,
                "commit_sha": commit_sha,
                "skill_git_blob_sha1": blob,
            }

    def snapshot(self):
        return {"schema_version":1, "policy":"released-pins-only",
                "game_exp_version":"1.5.4", "components":self.entries}

    def transport(self, url, *, timeout=30):
        for spec in m.COMPANION_SKILLS:
            entry = self.entries[spec.name]
            base = f"{m.GITHUB_API}/repos/{spec.repository}"
            if url == base + "/releases/tags/" + entry["tag"]:
                return json.dumps({"tag_name":entry["tag"],"draft":False,"prerelease":False}).encode()
            if url == base + "/git/ref/tags/" + entry["tag"]:
                return json.dumps({"object":{"type":"commit","sha":entry["commit_sha"]}}).encode()
            if url == f"{m.GITHUB_CODELOAD}/{spec.repository}/zip/{entry['commit_sha']}":
                return self.archives[entry["commit_sha"]]
        raise AssertionError("unexpected GitHub endpoint " + url)

    def test_self_version_not_in_snapshot_fails_before_writes(self):
        snapshot = self.snapshot()
        snapshot["game_exp_version"] = "1.5.3"
        with tempfile.TemporaryDirectory() as td, mock.patch.object(m, "_load_vetted_snapshot", return_value=snapshot):
            with self.assertRaisesRegex(m.CompanionSkillSyncError, "does not match shipped"):
                m.CompanionSkillSynchronizer(pathlib.Path(td), harness="codex").sync()
            self.assertFalse((pathlib.Path(td) / ".codex/skills").exists())

    def test_shipped_snapshot_versions_and_digests(self):
        actual = m._load_vetted_snapshot()
        self.assertEqual(actual["game_exp_version"], "1.5.4")
        expected = {
            "godot-prototype-studio": ("1.0.7", "8c3356ee42c0d8a07fd550eb9caf95bf9a95f61c"),
            "h5-game-prototype-agent": ("0.2.6", "fffe6579867e0f4f71c221ed0da836dbe418b835"),
        }
        self.assertEqual(set(actual["components"]), set(expected))
        for name, (version, commit) in expected.items():
            self.assertEqual(actual["components"][name]["version"], version)
            self.assertEqual(actual["components"][name]["commit_sha"], commit)

    def test_pins_and_exact_commit_archive_are_installed(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(m, "_load_vetted_snapshot", side_effect=self.snapshot), mock.patch.object(m, "_request_bytes", side_effect=self.transport):
            result = m.CompanionSkillSynchronizer(pathlib.Path(td), harness="codex").sync()
            self.assertEqual(len(result), 2)
            self.assertTrue(all(row["compatibility_basis"] == "shipped_release_snapshot" for row in result))
            for row in result:
                self.assertTrue((pathlib.Path(row["target"]) / "SKILL.md").exists())

    def test_moved_tag_blocks_before_local_writes(self):
        def moved(url, *, timeout=30):
            if "/git/ref/tags/" in url:
                return json.dumps({"object":{"type":"commit","sha":"f"*40}}).encode()
            return self.transport(url, timeout=timeout)
        with tempfile.TemporaryDirectory() as td, mock.patch.object(m, "_load_vetted_snapshot", side_effect=self.snapshot), mock.patch.object(m, "_request_bytes", side_effect=moved):
            with self.assertRaisesRegex(m.CompanionSkillSyncError, "tag moved"):
                m.CompanionSkillSynchronizer(pathlib.Path(td), harness="codex").sync()
            self.assertFalse((pathlib.Path(td) / ".codex/skills").exists())

    def test_unreviewed_companion_tag_is_never_used(self):
        def malicious(url, *, timeout=30):
            if url.endswith("/releases/tags/v0.2.6"):
                return json.dumps({"tag_name":"v0.2.6","prerelease":True,"draft":False}).encode()
            return self.transport(url, timeout=timeout)
        with tempfile.TemporaryDirectory() as td, mock.patch.object(m, "_load_vetted_snapshot", side_effect=self.snapshot), mock.patch.object(m, "_request_bytes", side_effect=malicious):
            with self.assertRaisesRegex(m.CompanionSkillSyncError, "stable published Release"):
                m.CompanionSkillSynchronizer(pathlib.Path(td), harness="codex").sync()

    def test_modified_entrypoint_archive_fails_deterministically(self):
        first = next(spec for spec in m.COMPANION_SKILLS if spec.name.startswith("godot"))
        self.entries[first.name]["skill_git_blob_sha1"] = "f"*40
        with tempfile.TemporaryDirectory() as td, mock.patch.object(m, "_load_vetted_snapshot", side_effect=self.snapshot), mock.patch.object(m, "_request_bytes", side_effect=self.transport):
            with self.assertRaisesRegex(m.CompanionSkillSyncError, "entrypoint digest mismatch"):
                m.CompanionSkillSynchronizer(pathlib.Path(td), harness="codex").sync()

if __name__ == "__main__":
    unittest.main()
