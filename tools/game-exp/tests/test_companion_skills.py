from __future__ import annotations

import io
import json
import pathlib
import sys
import tempfile
import unittest
import zipfile
from unittest import mock

TOOLS_DIR = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS_DIR))

import companion_skills as module  # noqa: E402
from companion_skills import (  # noqa: E402
    CompanionSkillSpec,
    CompanionSkillSyncError,
    CompanionSkillSynchronizer,
)


def _archive_bytes(root_name: str, *, skill_name: str, version: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        prefix = root_name.rstrip("/") + "/"
        archive.writestr(
            prefix + "SKILL.md",
            f"---\nname: {skill_name}\ndescription: test\n---\n\n# Test\n",
        )
        archive.writestr(prefix + "VERSION", version + "\n")
        archive.writestr(prefix + "agents/openai.yaml", "interface:\n  display_name: Test\n")
        archive.writestr(prefix + "references/runtime.md", "runtime\n")
        archive.writestr(prefix + "scripts/helper.py", "print('ok')\n")
        archive.writestr(prefix + "tests/test_dev.py", "raise SystemExit(1)\n")
        archive.writestr(prefix + "dev/build.py", "raise SystemExit(1)\n")
        archive.writestr(prefix + ".github/workflows/check.yml", "name: check\n")
        archive.writestr(prefix + "README.md", "development readme\n")
        archive.writestr(prefix + "ut-out.txt", "temporary\n")
    return buffer.getvalue()


class CompanionSkillTests(unittest.TestCase):
    def test_latest_semver_tag_uses_numeric_order(self):
        payload = json.dumps(
            [
                {"name": "v1.9.9"},
                {"name": "v1.10.0"},
                {"name": "preview"},
                {"name": "0.8.0"},
            ]
        ).encode("utf-8")
        with mock.patch("companion_skills._request_bytes", return_value=payload):
            self.assertEqual(module._latest_semver_tag("owner/repo"), "v1.10.0")

    def test_latest_semver_tag_rejects_unversioned_repository(self):
        payload = json.dumps([{"name": "main-snapshot"}]).encode("utf-8")
        with mock.patch("companion_skills._request_bytes", return_value=payload):
            with self.assertRaisesRegex(
                CompanionSkillSyncError, "no semantic version tag"
            ):
                module._latest_semver_tag("owner/repo")

    def test_sync_installs_only_runtime_files_into_selected_harness(self):
        spec = CompanionSkillSpec("demo-skill", "owner/demo-skill")
        tags = json.dumps([{"name": "v2.3.4"}]).encode("utf-8")
        archive = _archive_bytes(
            "demo-skill-2.3.4",
            skill_name="demo-skill",
            version="2.3.4",
        )

        def fake_request(url: str, *, timeout: int = 30) -> bytes:
            if "/tags?" in url:
                return tags
            if "codeload.github.com" in url:
                return archive
            raise AssertionError(url)

        with tempfile.TemporaryDirectory() as td, mock.patch(
            "companion_skills._request_bytes",
            side_effect=fake_request,
        ):
            home = pathlib.Path(td)
            result = CompanionSkillSynchronizer(
                home,
                harness="codex",
                specs=(spec,),
            ).sync()
            target = home / ".codex" / "skills" / "demo-skill"
            self.assertEqual(result[0]["tag"], "v2.3.4")
            self.assertEqual(result[0]["version"], "2.3.4")
            self.assertTrue((target / "SKILL.md").is_file())
            self.assertTrue((target / "references" / "runtime.md").is_file())
            self.assertFalse((target / "tests").exists())
            self.assertFalse((target / "dev").exists())
            self.assertFalse((target / ".github").exists())
            self.assertFalse((target / "README.md").exists())
            self.assertFalse((target / "ut-out.txt").exists())
            self.assertFalse((home / ".cursor" / "skills" / "demo-skill").exists())

    def test_safe_extract_rejects_too_many_members(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("root/a.txt", "a")
            archive.writestr("root/b.txt", "b")
            archive.writestr("root/c.txt", "c")
        with tempfile.TemporaryDirectory() as td:
            archive_path = pathlib.Path(td) / "source.zip"
            archive_path.write_bytes(buffer.getvalue())
            target = pathlib.Path(td) / "extract"
            target.mkdir()
            with mock.patch.object(module, "_MAX_ARCHIVE_MEMBERS", 2):
                with self.assertRaisesRegex(
                    CompanionSkillSyncError,
                    "too many members",
                ):
                    module._safe_extract(archive_path, target)

    def test_safe_extract_rejects_oversized_member(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("root/a.txt", "0123456789")
        with tempfile.TemporaryDirectory() as td:
            archive_path = pathlib.Path(td) / "source.zip"
            archive_path.write_bytes(buffer.getvalue())
            target = pathlib.Path(td) / "extract"
            target.mkdir()
            with mock.patch.object(module, "_MAX_ARCHIVE_MEMBER_BYTES", 8):
                with self.assertRaisesRegex(
                    CompanionSkillSyncError,
                    "member is too large",
                ):
                    module._safe_extract(archive_path, target)

    def test_safe_extract_rejects_symbolic_link_member(self):
        buffer = io.BytesIO()
        link = zipfile.ZipInfo("root/link")
        link.create_system = 3
        link.external_attr = (0o120777 << 16)
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr(link, "../outside")
        with tempfile.TemporaryDirectory() as td:
            archive_path = pathlib.Path(td) / "source.zip"
            archive_path.write_bytes(buffer.getvalue())
            target = pathlib.Path(td) / "extract"
            target.mkdir()
            with self.assertRaisesRegex(
                CompanionSkillSyncError,
                "symbolic-link",
            ):
                module._safe_extract(archive_path, target)

    def test_safe_extract_rejects_path_escape(self):
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("root/../../outside.txt", "escape")
        with tempfile.TemporaryDirectory() as td:
            archive_path = pathlib.Path(td) / "source.zip"
            archive_path.write_bytes(buffer.getvalue())
            target = pathlib.Path(td) / "extract"
            target.mkdir()
            with self.assertRaisesRegex(
                CompanionSkillSyncError,
                "unsafe archive path",
            ):
                module._safe_extract(archive_path, target)

    def test_sync_rejects_tag_version_mismatch_before_install(self):
        spec = CompanionSkillSpec("demo-skill", "owner/demo-skill")
        tags = json.dumps([{"name": "v2.3.4"}]).encode("utf-8")
        archive = _archive_bytes(
            "demo-skill-2.3.4",
            skill_name="demo-skill",
            version="2.3.3",
        )

        def fake_request(url: str, *, timeout: int = 30) -> bytes:
            return tags if "/tags?" in url else archive

        with tempfile.TemporaryDirectory() as td, mock.patch(
            "companion_skills._request_bytes",
            side_effect=fake_request,
        ):
            home = pathlib.Path(td)
            with self.assertRaisesRegex(CompanionSkillSyncError, "does not match tag"):
                CompanionSkillSynchronizer(
                    home,
                    harness="cursor",
                    specs=(spec,),
                ).sync()
            self.assertFalse(
                (home / ".cursor" / "skills" / "demo-skill").exists()
            )


if __name__ == "__main__":
    unittest.main()
