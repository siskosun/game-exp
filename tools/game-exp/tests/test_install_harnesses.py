from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import tomllib
import unittest
from unittest import mock

TOOLS_DIR = pathlib.Path(__file__).resolve().parents[1]
ROOT = TOOLS_DIR.parents[1]
sys.path.insert(0, str(TOOLS_DIR))

from install_harnesses import (  # noqa: E402
    SUPPORTED_HARNESSES,
    HarnessInstallError,
    HarnessInstaller,
    install_many,
)


class HarnessInstallerTests(unittest.TestCase):
    def _codex_config(self, home: pathlib.Path) -> pathlib.Path:
        path = home / ".codex" / "config.toml"
        path.parent.mkdir(parents=True)
        path.write_text(
            'model = "gpt-test"\n\n'
            '[mcp_servers.other]\n'
            'command = "other"\n',
            encoding="utf-8",
        )
        return path

    def _json_config(self, path: pathlib.Path, *, extra=None) -> pathlib.Path:
        path.parent.mkdir(parents=True)
        value = {
            "mcpServers": {"other": {"type": "stdio", "command": "other"}},
            **(extra or {}),
        }
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_codex_install_is_isolated_from_other_harnesses(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            codex = self._codex_config(home)
            qoder = self._json_config(
                home / ".qoder" / "settings.json",
                extra={"theme": "dark"},
            )
            cursor = self._json_config(home / ".cursor" / "mcp.json")
            qoder_before = qoder.read_bytes()
            cursor_before = cursor.read_bytes()

            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                result = HarnessInstaller(
                    ROOT,
                    home,
                    harness="codex",
                ).install()

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["version"], "0.18.1")
            self.assertEqual(result["updated_harnesses"], ["codex"])
            self.assertFalse(result["shared_runtime"])
            runtime = home / ".game-exp" / "runtimes" / "codex"
            self.assertEqual(pathlib.Path(result["runtime_dir"]).resolve(), runtime.resolve())
            self.assertEqual(
                (runtime / "VERSION.txt").read_text(encoding="utf-8").strip(),
                "0.18.1",
            )
            provenance = json.loads(
                (runtime / "INSTALL_SOURCE.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                provenance,
                {
                    "schema_version": 1,
                    "source": "https://github.com/siskosun/game-exp",
                    "version": "0.18.1",
                    "harness": "codex",
                },
            )
            codex_data = tomllib.loads(codex.read_text(encoding="utf-8"))
            game_exp = codex_data["mcp_servers"]["game-exp"]
            self.assertEqual(game_exp["command"], "uv")
            self.assertEqual(
                pathlib.Path(game_exp["args"][-1]).resolve(),
                (runtime / "tools" / "game-exp" / "mcp_server.py").resolve(),
            )
            self.assertTrue((home / ".codex" / "skills" / "game-exp" / "SKILL.md").is_file())
            self.assertEqual(qoder.read_bytes(), qoder_before)
            self.assertEqual(cursor.read_bytes(), cursor_before)
            self.assertFalse((home / ".qoder" / "skills" / "game-exp").exists())
            self.assertFalse((home / ".cursor" / "skills" / "game-exp").exists())

    def test_check_plan_is_read_only_and_reports_upgrade_state(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            installer = HarnessInstaller(ROOT, home, harness="codex")
            before = installer.plan()
            self.assertEqual(before["install_state"], "NOT_INSTALLED")
            self.assertFalse(installer.runtime_dir.exists())

            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                installer.install()

            current = HarnessInstaller(ROOT, home, harness="codex").plan()
            self.assertEqual(current["install_state"], "CURRENT")
            self.assertEqual(current["installed_version"], "0.18.1")
            self.assertFalse(current["would_update_other_harnesses"])

    def test_downgrade_requires_explicit_override(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            installer = HarnessInstaller(ROOT, home, harness="codex")
            installer.runtime_dir.mkdir(parents=True)
            (installer.runtime_dir / "VERSION.txt").write_text(
                "9.0.0\n",
                encoding="utf-8",
            )

            plan = installer.plan()
            self.assertEqual(plan["install_state"], "SOURCE_OLDER_THAN_INSTALLED")
            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                with self.assertRaisesRegex(HarnessInstallError, "older than the installed"):
                    installer.install()

            rollback = HarnessInstaller(
                ROOT,
                home,
                harness="codex",
                allow_downgrade=True,
            )
            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                result = rollback.install()
            self.assertEqual(result["version"], "0.18.1")

    def test_single_harness_detects_but_preserves_legacy_shared_install(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            legacy_runtime = home / ".agents" / "tools" / "game-exp"
            legacy_skill = home / ".agents" / "skills" / "game-exp"
            legacy_runtime.mkdir(parents=True)
            legacy_skill.mkdir(parents=True)
            (legacy_runtime / "VERSION.txt").write_text("0.17.0\n", encoding="utf-8")
            (legacy_skill / "SKILL.md").write_text("legacy\n", encoding="utf-8")

            installer = HarnessInstaller(ROOT, home, harness="codex")
            plan = installer.plan()
            self.assertTrue(plan["legacy_shared"]["detected"])
            self.assertEqual(plan["legacy_shared"]["runtime_version"], "0.17.0")

            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                result = installer.install()

            self.assertEqual(result["updated_harnesses"], ["codex"])
            self.assertTrue(legacy_runtime.exists())
            self.assertTrue(legacy_skill.exists())

    def test_explicit_all_can_cleanup_legacy_shared_install(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            legacy_runtime = home / ".agents" / "tools" / "game-exp"
            legacy_skill = home / ".agents" / "skills" / "game-exp"
            legacy_runtime.mkdir(parents=True)
            legacy_skill.mkdir(parents=True)
            (legacy_runtime / "VERSION.txt").write_text("0.17.0\n", encoding="utf-8")
            (legacy_skill / "SKILL.md").write_text("legacy\n", encoding="utf-8")

            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                result = install_many(
                    ROOT,
                    home,
                    SUPPORTED_HARNESSES,
                    cleanup_legacy_shared=True,
                )

            self.assertTrue(result["legacy_cleanup"]["performed"])
            self.assertEqual(len(result["legacy_cleanup"]["removed"]), 2)
            self.assertFalse(legacy_runtime.exists())
            self.assertFalse(legacy_skill.exists())
            for harness in SUPPORTED_HARNESSES:
                self.assertTrue(
                    pathlib.Path(result["results"][harness]["runtime_dir"]).exists()
                )

    def test_explicit_all_uses_separate_runtimes(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                result = install_many(ROOT, home, SUPPORTED_HARNESSES)

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(result["version"], "0.18.1")
            self.assertEqual(result["updated_harnesses"], list(SUPPORTED_HARNESSES))
            runtime_paths = {
                pathlib.Path(row["runtime_dir"]).resolve()
                for row in result["results"].values()
            }
            self.assertEqual(len(runtime_paths), 3)
            for harness in SUPPORTED_HARNESSES:
                row = result["results"][harness]
                self.assertEqual(row["harness"], harness)
                self.assertTrue(pathlib.Path(row["runtime_dir"], "VERSION.txt").is_file())
                self.assertTrue(pathlib.Path(row["skill"], "SKILL.md").is_file())
                self.assertTrue(pathlib.Path(row["config"]).is_file())

    def test_runtime_install_falls_back_when_directory_swap_is_locked(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            installer = HarnessInstaller(ROOT, home, harness="codex")
            original_replace = __import__("install_harnesses")._atomic_replace_dir
            calls = {"count": 0}

            def locked_once(source, target):
                calls["count"] += 1
                if target == installer.runtime_dir:
                    raise PermissionError("simulated live Windows directory lock")
                return original_replace(source, target)

            with (
                mock.patch("install_harnesses.shutil.which", return_value="uv"),
                mock.patch("install_harnesses._atomic_replace_dir", side_effect=locked_once),
            ):
                result = installer.install()

            self.assertEqual(result["runtime_update_mode"], "filewise-fallback")
            self.assertEqual(
                (installer.runtime_dir / "VERSION.txt").read_text(encoding="utf-8").strip(),
                "0.18.1",
            )

    def test_runtime_install_handles_file_locked_against_replace(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            installer = HarnessInstaller(ROOT, home, harness="codex")
            module = __import__("install_harnesses")
            original_replace = module._atomic_replace_dir
            original_atomic_write = module._atomic_write
            locked_path = installer.runtime_dir / "tools" / "game-exp" / "project_setup.py"
            state = {"raised": False}

            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                installer.install()

            def locked_directory(source, target):
                if target == installer.runtime_dir:
                    raise PermissionError("simulated live runtime directory lock")
                return original_replace(source, target)

            def locked_file(path, content):
                if path == locked_path and path.exists() and not state["raised"]:
                    state["raised"] = True
                    raise PermissionError("simulated reader denying delete-sharing")
                return original_atomic_write(path, content)

            with (
                mock.patch("install_harnesses.shutil.which", return_value="uv"),
                mock.patch("install_harnesses._atomic_replace_dir", side_effect=locked_directory),
                mock.patch("install_harnesses._atomic_write", side_effect=locked_file),
            ):
                result = installer.install()

            self.assertTrue(state["raised"])
            self.assertEqual(result["runtime_update_mode"], "filewise-live-fallback")
            self.assertEqual(
                locked_path.read_bytes(),
                (ROOT / "tools" / "game-exp" / "project_setup.py").read_bytes(),
            )
            self.assertEqual(list(locked_path.parent.glob("project_setup.py.live-backup-*")), [])

    def test_reinstall_is_idempotent_for_selected_harness(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                first = HarnessInstaller(ROOT, home, harness="codex").install()
                second = HarnessInstaller(ROOT, home, harness="codex").install()

            self.assertEqual(first["version"], second["version"])
            codex = tomllib.loads(
                (home / ".codex" / "config.toml").read_text(encoding="utf-8")
            )
            self.assertEqual(list(codex["mcp_servers"]).count("game-exp"), 1)

    def test_invalid_unselected_config_does_not_block_selected_harness(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            qoder = home / ".qoder" / "settings.json"
            qoder.parent.mkdir(parents=True)
            qoder.write_text("{not-json", encoding="utf-8")

            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                result = HarnessInstaller(ROOT, home, harness="codex").install()

            self.assertEqual(result["status"], "PASS")
            self.assertEqual(qoder.read_text(encoding="utf-8"), "{not-json")

    def test_invalid_selected_config_fails_before_runtime_write(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            qoder = home / ".qoder" / "settings.json"
            qoder.parent.mkdir(parents=True)
            qoder.write_text("{not-json", encoding="utf-8")
            installer = HarnessInstaller(ROOT, home, harness="qoder")

            with mock.patch("install_harnesses.shutil.which", return_value="uv"):
                with self.assertRaises(HarnessInstallError):
                    installer.install()

            self.assertFalse(installer.runtime_dir.exists())

    def test_missing_uv_fails_before_install(self):
        with tempfile.TemporaryDirectory() as td:
            home = pathlib.Path(td)
            installer = HarnessInstaller(ROOT, home, harness="cursor")
            with mock.patch("install_harnesses.shutil.which", return_value=None):
                with self.assertRaisesRegex(HarnessInstallError, "uv is required"):
                    installer.install()
            self.assertFalse(installer.runtime_dir.exists())

    def test_invalid_harness_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaisesRegex(HarnessInstallError, "unsupported harness"):
                HarnessInstaller(ROOT, pathlib.Path(td), harness="unknown")


if __name__ == "__main__":
    unittest.main()
