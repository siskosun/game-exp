from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import MagicMock, patch

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import cli  # noqa: E402


class CLIRoutingTests(unittest.TestCase):
    def run_cli(self, argv):
        transport = MagicMock()
        client = MagicMock()
        client.status.return_value = {"status": "PASS"}
        client.capabilities.return_value = {"status": "PASS", "contract": {"version": "1.0"}}
        client.board.return_value = {"status": "PASS", "experiments": []}
        client.experiment_template.return_value = {
            "status": "PASS",
            "manifest_contract": {"current_schema_version": 2},
        }
        client.experiment_get.return_value = {"status": "PASS", "state": {"current_candidate_id": "C-21-1-1", "last_decision_id": "req_prev"}}
        client.notification_feed.return_value = {"status": "PASS", "notifications": []}
        client.prototype_handoff.return_value = {"status": "PASS"}
        client.bind.return_value = {"status": "ACCEPTED"}
        client.review_record.return_value = {"status": "ACCEPTED"}
        client.operation_get.return_value = {"status": "COMMITTED"}
        client.resume_execution.return_value = {"status": "ACCEPTED"}
        client.integrate.return_value = {"status": "ACCEPTED"}
        client.integrate_finalize.return_value = {"status": "ACCEPTED"}
        client.archive.return_value = {"status": "ACCEPTED"}
        client.abandon.return_value = {"status": "ACCEPTED"}
        client.archive_abort.return_value = {"status": "ACCEPTED"}
        with (
            patch("cli.GitHubTransport", return_value=transport),
            patch("cli.GameExpClient", return_value=client),
            patch("cli._print_result"),
        ):
            code = cli.main(argv)
        return code, client

    def test_project_create_routes_before_repository_client_construction(self):
        result = {
            "status": "PASS",
            "complete": True,
            "project_readiness": "PROJECT_READY",
            "repo": "alice/demo",
        }
        with (
            patch("cli.prototype_project_create", return_value=result) as create,
            patch("cli.GitHubTransport") as transport,
            patch("cli._print_result"),
        ):
            code = cli.main(
                [
                    "project-create",
                    "demo",
                    "--stack",
                    "h5",
                    "--visibility",
                    "public",
                ]
            )
        self.assertEqual(code, 0)
        transport.assert_not_called()
        create.assert_called_once_with(
            name="demo",
            stack="h5",
            visibility="public",
            owner=None,
            directory=None,
            h5_mode="probe",
            description=None,
            trust_mode="auto",
            run_selftest=True,
        )

    def test_project_create_defaults_to_public(self):
        result = {
            "status": "PASS",
            "complete": True,
            "project_readiness": "PROJECT_READY",
            "repo": "alice/demo",
        }
        with (
            patch("cli.prototype_project_create", return_value=result) as create,
            patch("cli.GitHubTransport"),
            patch("cli._print_result"),
        ):
            code = cli.main(["project-create", "demo", "--stack", "h5"])
        self.assertEqual(code, 0)
        self.assertEqual(create.call_args.kwargs["visibility"], "public")

    def test_text_result_prints_error_and_hint(self):
        output = io.StringIO()
        with redirect_stdout(output):
            cli._print_result(
                {
                    "status": "REJECTED",
                    "code": "GITHUB_CLI_REQUIRED",
                    "error": "required command not found: gh",
                    "hint": "Install GitHub CLI (gh).",
                },
                as_json=False,
            )
        rendered = output.getvalue()
        self.assertIn("status: REJECTED", rendered)
        self.assertIn("code: GITHUB_CLI_REQUIRED", rendered)
        self.assertIn("error: required command not found: gh", rendered)
        self.assertIn("hint: Install GitHub CLI (gh).", rendered)

    def test_bind_routes_manifest_to_client(self):
        manifest = {
            "operation_id": "req_bind_21",
            "schema_version": 2,
        }
        code, client = self.run_cli(
            ["bind", "--manifest", json.dumps(manifest)]
        )
        self.assertEqual(code, 0)
        client.bind.assert_called_once_with(manifest, request_id=None)

    def test_project_create_incomplete_returns_nonzero(self):
        with (
            patch(
                "cli.prototype_project_create",
                return_value={
                    "status": "BLOCKED_PLAN",
                    "complete": False,
                    "repo_created": True,
                },
            ),
            patch("cli._print_result"),
        ):
            code = cli.main(["project-create", "demo", "--stack", "godot"])
        self.assertEqual(code, 1)

    def test_project_preflight_routes_before_client_construction(self):
        transport = MagicMock()
        transport.repo = "owner/repo"
        with (
            patch("cli.GitHubTransport", return_value=transport),
            patch(
                "cli.project_preflight",
                return_value={"status": "PASS", "ready_to_provision": True},
            ) as preflight,
            patch("cli._print_result"),
        ):
            code = cli.main(["--repo", "owner/repo", "project-preflight"])
        self.assertEqual(code, 0)
        preflight.assert_called_once_with("owner/repo")

    def test_project_init_requires_complete_pass(self):
        transport = MagicMock()
        transport.repo = "owner/repo"
        with (
            patch("cli.GitHubTransport", return_value=transport),
            patch(
                "cli.project_provision",
                return_value={"status": "PASS", "complete": True},
            ) as provision,
            patch("cli._print_result"),
        ):
            code = cli.main(["--repo", "owner/repo", "project-init"])
        self.assertEqual(code, 0)
        provision.assert_called_once_with(
            "owner/repo", run_selftest=True, trust_mode="auto"
        )

    def test_project_init_forwards_explicit_trust_mode(self):
        transport = MagicMock()
        transport.repo = "owner/repo"
        with (
            patch("cli.GitHubTransport", return_value=transport),
            patch(
                "cli.project_provision",
                return_value={"status": "PASS", "complete": True},
            ) as provision,
            patch("cli._print_result"),
        ):
            code = cli.main([
                "--repo",
                "owner/repo",
                "project-init",
                "--trust-mode",
                "multi-principal",
            ])
        self.assertEqual(code, 0)
        provision.assert_called_once_with(
            "owner/repo", run_selftest=True, trust_mode="multi-principal"
        )
    def test_project_init_skip_selftest_is_incomplete(self):
        transport = MagicMock()
        transport.repo = "owner/repo"
        with (
            patch("cli.GitHubTransport", return_value=transport),
            patch(
                "cli.project_provision",
                return_value={"status": "PASS", "complete": True},
            ),
            patch("cli._print_result") as printer,
        ):
            code = cli.main(
                ["--repo", "owner/repo", "project-init", "--skip-selftest"]
            )
        self.assertEqual(code, 1)
        result = printer.call_args.args[0]
        self.assertEqual(result["status"], "INCOMPLETE")
        self.assertFalse(result["complete"])

    def test_experiment_template_routes_to_client(self):
        code, client = self.run_cli(["experiment-template"])
        self.assertEqual(code, 0)
        client.experiment_template.assert_called_once_with()

    def test_board_routes_to_client(self):
        code, client = self.run_cli(["board"])
        self.assertEqual(code, 0)
        client.board.assert_called_once_with(
            query=None,
            subject_id=None,
            lifecycle=None,
            attention_only=False,
        )

    def test_abandon_routes_to_client(self):
        code, client = self.run_cli(
            [
                "abandon",
                "EXP-21",
                "--reason",
                "stop this experiment",
                "--request-id",
                "req_abandon_21",
            ]
        )
        self.assertEqual(code, 0)
        client.abandon.assert_called_once_with(
            "EXP-21",
            "stop this experiment",
            request_id="req_abandon_21",
            actor_claim=None,
        )

    def test_review_routes_revision_comparison_to_client(self):
        revision = {
            "previous_candidate_id": "C-21-122-1",
            "previous_artifact_digest": "sha256:" + "0" * 64,
            "blind": True,
            "presentation_order": "CURRENT_PREVIOUS",
            "choice": "A_SLIGHTLY_BETTER",
            "notes": "A felt slightly better.",
        }
        code, client = self.run_cli(
            [
                "review",
                "EXP-21",
                "--outcome",
                "PASS",
                "--notes",
                "Human review.",
                "--candidate-id",
                "C-21-123-1",
                "--revision-comparison-json",
                json.dumps(revision),
                "--request-id",
                "req_review_revision_21",
            ]
        )
        self.assertEqual(code, 0)
        client.review_record.assert_called_once_with(
            "EXP-21",
            candidate_id="C-21-123-1",
            outcome="PASS",
            notes="Human review.",
            comparison=None,
            revision_comparison=revision,
            actor_claim=None,
            request_id="req_review_revision_21",
        )

    def test_review_rejects_two_comparison_json_modes(self):
        code, client = self.run_cli(
            [
                "review",
                "EXP-21",
                "--outcome",
                "PASS",
                "--notes",
                "Human review.",
                "--candidate-id",
                "C-21-123-1",
                "--comparison-json",
                "{}",
                "--revision-comparison-json",
                "{}",
                "--request-id",
                "req_review_conflict_21",
            ]
        )
        self.assertEqual(code, 1)
        client.review_record.assert_not_called()

    def test_integrate_routes_to_client(self):
        code, client = self.run_cli(["integrate", "EXP-21", "--request-id", "req_integrate_21"])
        self.assertEqual(code, 0)
        client.integrate.assert_called_once_with(
            "EXP-21", request_id="req_integrate_21", actor_claim=None
        )

    def test_integrate_finalize_routes_to_client(self):
        code, client = self.run_cli(
            ["integrate-finalize", "EXP-21", "--pr-number", "35", "--request-id", "req_finalize_21"]
        )
        self.assertEqual(code, 0)
        client.integrate_finalize.assert_called_once_with(
            "EXP-21", "35", request_id="req_finalize_21", actor_claim=None
        )

    def test_archive_routes_mode_to_client(self):
        code, client = self.run_cli(
            [
                "archive",
                "EXP-21",
                "--mode",
                "RETAIN_BRANCH",
                "--request-id",
                "req_archive_21",
            ]
        )
        self.assertEqual(code, 0)
        client.archive.assert_called_once_with(
            "EXP-21",
            "RETAIN_BRANCH",
            request_id="req_archive_21",
            actor_claim=None,
        )

    def test_capabilities_routes_to_client(self):
        code, client = self.run_cli(["capabilities"])
        self.assertEqual(code, 0)
        client.capabilities.assert_called_once_with()
        self.assertEqual(
            client.capabilities.return_value["interface"]["write_identity"],
            "local-gh-principal",
        )

    def test_get_and_resume_operation_route_without_resubmit(self):
        code, client = self.run_cli(["get-operation", "req_shared_1"])
        self.assertEqual(code, 0)
        client.operation_get.assert_called_once_with("req_shared_1")

        code, client = self.run_cli(["resume-operation", "req_shared_1"])
        self.assertEqual(code, 0)
        client.resume_execution.assert_called_once_with("req_shared_1")

    def test_notifications_passes_resume_cursors(self):
        code, client = self.run_cli(
            [
                "notifications",
                "--viewer",
                "bob",
                "--subject-id",
                "arena-duel",
                "--after",
                "n1.checkpoint",
            ]
        )
        self.assertEqual(code, 0)
        client.notification_feed.assert_called_once_with(
            viewer_login="bob",
            subject_id="arena-duel",
            limit=50,
            after="n1.checkpoint",
            cursor=None,
        )

    def test_mutating_async_commands_require_request_id(self):
        with self.assertRaises(SystemExit):
            cli.build_parser().parse_args(["integrate", "EXP-21"])

    def test_conformance_session_uses_normal_cli_surface_without_github(self):
        with tempfile.TemporaryDirectory() as td:
            session = Path(td) / "session.json"
            with patch("cli._print_result"):
                code = cli.main(
                    [
                        "--json",
                        "conformance-start",
                        "lost-response-recovery",
                        "--session-file",
                        str(session),
                        "--session-id",
                        "cli-cross-surface",
                    ]
                )
            self.assertEqual(code, 0)
            self.assertTrue(session.exists())

            with (
                patch("cli.GitHubTransport") as github_transport,
                patch("cli._print_result"),
            ):
                code = cli.main(
                    [
                        "--conformance-session",
                        str(session),
                        "--json",
                        "get-operation",
                        "req-archive-42",
                    ]
                )
            self.assertEqual(code, 0)
            github_transport.assert_not_called()

            data = json.loads(session.read_text(encoding="utf-8"))
            self.assertEqual(data["trace"][-1]["surface"], "cli")
            self.assertEqual(data["trace"][-1]["tool"], "game_exp_operation_get")

    def test_conformance_result_and_report_are_local_only(self):
        with tempfile.TemporaryDirectory() as td:
            files = []
            scenarios = [
                ("lost-response-recovery", ["get-operation", "req-archive-42"], 0),
                (
                    "authorization-no-fallback",
                    ["get-operation", "req-promote-42"],
                    1,
                ),
                ("review-bound-to-candidate", ["experiment", "EXP-42"], 0),
                ("dependency-review-required", ["experiment", "EXP-86"], 0),
                ("human-gate-preserved", ["experiment", "EXP-42"], 0),
                (
                    "abandon-without-review",
                    [
                        "abandon",
                        "EXP-42",
                        "--reason",
                        "resource priority changed",
                        "--request-id",
                        "req-abandon-cli",
                    ],
                    0,
                ),
            ]
            for scenario_id, command, expected_code in scenarios:
                path = Path(td) / f"{scenario_id}.json"
                files.append(path)
                with patch("cli._print_result"):
                    self.assertEqual(
                        cli.main(
                            [
                                "conformance-start",
                                scenario_id,
                                "--session-file",
                                str(path),
                            ]
                        ),
                        0,
                    )
                    self.assertEqual(
                        cli.main(
                            [
                                "--conformance-session",
                                str(path),
                                *command,
                            ]
                        ),
                        expected_code,
                    )

            stale = Path(td) / "stale.json"
            files.append(stale)
            with patch("cli._print_result"):
                self.assertEqual(
                    cli.main(
                        [
                            "conformance-start",
                            "stale-rehearsal-refresh",
                            "--session-file",
                            str(stale),
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    cli.main(
                        [
                            "--conformance-session",
                            str(stale),
                            "rehearse",
                            "EXP-42",
                            "--request-id",
                            "req-rh-cli",
                        ]
                    ),
                    0,
                )
                self.assertEqual(
                    cli.main(
                        [
                            "--conformance-session",
                            str(stale),
                            "get-operation",
                            "req-rh-cli",
                        ]
                    ),
                    0,
                )

                argv = ["conformance-report"]
                for path in files:
                    argv.extend(["--session-file", str(path)])
                self.assertEqual(cli.main(argv), 0)

    def test_archive_abort_routes_human_request(self):
        code, client = self.run_cli(
            [
                "archive-abort",
                "EXP-21",
                "--archive-id",
                "A-21-1",
                "--reason",
                "cancel before claim",
                "--request-id",
                "req_abort_1",
                "--actor-claim",
                "reviewer",
            ]
        )
        self.assertEqual(code, 0)
        client.archive_abort.assert_called_once_with(
            "EXP-21",
            "A-21-1",
            "cancel before claim",
            actor_claim="reviewer",
            request_id="req_abort_1",
        )


if __name__ == "__main__":
    unittest.main()
