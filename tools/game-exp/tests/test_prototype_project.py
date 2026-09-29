from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = pathlib.Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import prototype_project as module  # noqa: E402


def completed(args=None, returncode=0, stdout="", stderr=""):
    return subprocess.CompletedProcess(args or ["cmd"], returncode, stdout, stderr)


class PrototypeProjectTests(unittest.TestCase):
    def _template(self, *, stack: str):
        def materialize(*, stack: str, h5_mode: str, destination: pathlib.Path):
            destination.mkdir(parents=True)
            if stack == "h5":
                (destination / "package.json").write_text(
                    json.dumps({"name": "demo"}),
                    encoding="utf-8",
                )
                (destination / "package-lock.json").write_text(
                    json.dumps({"lockfileVersion": 3}),
                    encoding="utf-8",
                )
            else:
                (destination / "project.godot").write_text(
                    '[application]\nrun/main_scene="res://scenes/main.tscn"\n',
                    encoding="utf-8",
                )
                for rel in (
                    "scenes/main.tscn",
                    "scripts/main.gd",
                    "scripts/game_model.gd",
                    "qa/qa_bridge.gd",
                ):
                    path = destination / rel
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("x\n", encoding="utf-8")
            return {
                "skill": (
                    "h5-game-prototype-agent"
                    if stack == "h5"
                    else "godot-prototype-studio"
                ),
                "repository": "https://github.com/example/source",
                "tag": "v1.2.3",
                "version": "1.2.3",
                "template": "template",
            }

        return materialize

    def test_new_h5_project_defaults_to_public_and_project_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "demo"
            bootstrap = mock.MagicMock()
            with (
                mock.patch("prototype_project.shutil.which", return_value="tool"),
                mock.patch(
                    "prototype_project._authenticated_user",
                    return_value={"login": "alice", "id": 42},
                ),
                mock.patch("prototype_project._repo_exists", return_value=False),
                mock.patch(
                    "prototype_project._materialize_template",
                    side_effect=self._template(stack="h5"),
                ),
                mock.patch("prototype_project._run", return_value=completed()) as run,
                mock.patch("prototype_project.Bootstrapper", return_value=bootstrap),
                mock.patch(
                    "prototype_project.project_provision",
                    return_value={"status": "PASS", "complete": True},
                ) as provision,
            ):
                result = module.create_project(
                    name="demo",
                    stack="h5",
                    directory=str(root),
                )

            self.assertEqual(result["status"], "PASS")
            self.assertTrue(result["complete"])
            self.assertEqual(result["project_readiness"], "PROJECT_READY")
            self.assertEqual(result["repo"], "alice/demo")
            self.assertEqual(result["visibility"], "public")
            self.assertEqual(result["h5_mode"], "probe")
            self.assertEqual(result["next_step"], "DESCRIBE_FIRST_EXPERIMENT")
            bootstrap.install.assert_called_once_with()
            provision.assert_called_once_with(
                "alice/demo", run_selftest=True, trust_mode="auto"
            )
            commands = [call.args[0] for call in run.call_args_list]
            repo_create = next(argv for argv in commands if argv[:3] == ["gh", "repo", "create"])
            self.assertIn("--public", repo_create)
            self.assertNotIn("--private", repo_create)

    def test_private_visibility_remains_explicit_compatibility_option(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "demo"
            with (
                mock.patch("prototype_project.shutil.which", return_value="tool"),
                mock.patch(
                    "prototype_project._authenticated_user",
                    return_value={"login": "alice", "id": 42},
                ),
                mock.patch("prototype_project._repo_exists", return_value=False),
                mock.patch(
                    "prototype_project._materialize_template",
                    side_effect=self._template(stack="h5"),
                ),
                mock.patch("prototype_project._run", return_value=completed()) as run,
                mock.patch("prototype_project.Bootstrapper"),
                mock.patch(
                    "prototype_project.project_provision",
                    return_value={"status": "PASS", "complete": True},
                ),
            ):
                module.create_project(
                    name="demo",
                    stack="h5",
                    visibility="private",
                    directory=str(root),
                )
            commands = [call.args[0] for call in run.call_args_list]
            repo_create = next(argv for argv in commands if argv[:3] == ["gh", "repo", "create"])
            self.assertIn("--private", repo_create)
            self.assertNotIn("--public", repo_create)

    def test_existing_remote_repository_is_never_overwritten(self):
        with (
            mock.patch("prototype_project.shutil.which", return_value="tool"),
            mock.patch(
                "prototype_project._authenticated_user",
                return_value={"login": "alice", "id": 42},
            ),
            mock.patch("prototype_project._repo_exists", return_value=True),
            mock.patch("prototype_project._materialize_template") as materialize,
        ):
            with self.assertRaisesRegex(module.PrototypeProjectError, "already exists"):
                module.create_project(name="demo", stack="h5")
        materialize.assert_not_called()

    def test_existing_local_directory_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "demo"
            root.mkdir()
            with (
                mock.patch("prototype_project.shutil.which", return_value="tool"),
                mock.patch(
                    "prototype_project._authenticated_user",
                    return_value={"login": "alice", "id": 42},
                ),
                mock.patch("prototype_project._repo_exists", return_value=False),
            ):
                with self.assertRaisesRegex(
                    module.PrototypeProjectError,
                    "local project directory already exists",
                ):
                    module.create_project(
                        name="demo",
                        stack="godot",
                        directory=str(root),
                    )

    def test_plan_block_preserves_created_repository_for_repair(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "demo"
            with (
                mock.patch("prototype_project.shutil.which", return_value="tool"),
                mock.patch(
                    "prototype_project._authenticated_user",
                    return_value={"login": "alice", "id": 42},
                ),
                mock.patch("prototype_project._repo_exists", return_value=False),
                mock.patch(
                    "prototype_project._materialize_template",
                    side_effect=self._template(stack="h5"),
                ),
                mock.patch("prototype_project._run", return_value=completed()),
                mock.patch("prototype_project.Bootstrapper"),
                mock.patch(
                    "prototype_project.project_provision",
                    return_value={
                        "status": "BLOCKED_PLAN",
                        "complete": False,
                        "preflight": {
                            "blockers": [
                                {"code": "RULESETS_PLAN_UNSUPPORTED"}
                            ]
                        },
                    },
                ),
            ):
                result = module.create_project(
                    name="demo",
                    stack="h5",
                    directory=str(root),
                )
            self.assertEqual(result["status"], "BLOCKED_PLAN")
            self.assertFalse(result["complete"])
            self.assertTrue(result["repo_created"])
            self.assertEqual(result["next_step"], "RESOLVE_PROJECT_SETUP_BLOCKER")
            self.assertTrue(root.exists())

    def test_partial_gh_repo_create_failure_preserves_remote_and_local(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "demo"
            calls = {"exists": 0}

            def exists(_repo):
                calls["exists"] += 1
                return calls["exists"] > 1

            def run(argv, **kwargs):
                if argv[:3] == ["gh", "repo", "create"]:
                    raise module.PrototypeProjectError("push failed")
                return completed(argv)

            with (
                mock.patch("prototype_project.shutil.which", return_value="tool"),
                mock.patch(
                    "prototype_project._authenticated_user",
                    return_value={"login": "alice", "id": 42},
                ),
                mock.patch("prototype_project._repo_exists", side_effect=exists),
                mock.patch(
                    "prototype_project._materialize_template",
                    side_effect=self._template(stack="h5"),
                ),
                mock.patch("prototype_project._run", side_effect=run),
                mock.patch("prototype_project.Bootstrapper"),
            ):
                result = module.create_project(
                    name="demo",
                    stack="h5",
                    directory=str(root),
                )
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertEqual(result["code"], "REPOSITORY_PUSH_INCOMPLETE")
            self.assertTrue(result["repo_created"])
            self.assertTrue(root.exists())

    def test_skip_selftest_cannot_report_project_ready(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td) / "demo"
            with (
                mock.patch("prototype_project.shutil.which", return_value="tool"),
                mock.patch(
                    "prototype_project._authenticated_user",
                    return_value={"login": "alice", "id": 42},
                ),
                mock.patch("prototype_project._repo_exists", return_value=False),
                mock.patch(
                    "prototype_project._materialize_template",
                    side_effect=self._template(stack="h5"),
                ),
                mock.patch("prototype_project._run", return_value=completed()),
                mock.patch("prototype_project.Bootstrapper"),
                mock.patch(
                    "prototype_project.project_provision",
                    return_value={"status": "PASS", "complete": True},
                ),
            ):
                result = module.create_project(
                    name="demo",
                    stack="h5",
                    directory=str(root),
                    run_selftest=False,
                )
            self.assertEqual(result["status"], "INCOMPLETE")
            self.assertFalse(result["complete"])
            self.assertEqual(result["project_readiness"], "INCOMPLETE")

    def test_godot_policy_builds_source_bundle_from_repo_root(self):
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            module._write_godot_policy(root)
            policy = json.loads(
                (root / ".game-exp" / "project-policy.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(policy["adapter"], "godot-source")
            self.assertEqual(
                policy["candidate"]["required_paths"],
                [
                    "dist-godot/project.godot",
                    "dist-godot/scenes/main.tscn",
                ],
            )
            checker = (root / "tools" / "prototype_ci.py").read_text(
                encoding="utf-8"
            )
            self.assertIn("dist-godot", checker)
            self.assertIn("run/main_scene", checker)


if __name__ == "__main__":
    unittest.main()
