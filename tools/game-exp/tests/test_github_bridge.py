from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import github_bridge  # noqa: E402


class GitHubBridgeTests(unittest.TestCase):
    def command(self, payload):
        return "/game-exp\n" + json.dumps(payload, ensure_ascii=False)

    def test_parse_status_command(self):
        result = github_bridge.parse_command(
            self.command(
                {
                    "schema_version": 1,
                    "request_id": "req_bridge_status_50",
                    "action": "status",
                    "experiment_id": "EXP-50",
                }
            )
        )
        self.assertEqual(result["action"], "status")

    def test_parse_rejects_extra_keys(self):
        with self.assertRaisesRegex(github_bridge.BridgeError, "keys mismatch"):
            github_bridge.parse_command(
                self.command(
                    {
                        "schema_version": 1,
                        "request_id": "req_bridge_bad",
                        "action": "rehearse",
                        "experiment_id": "EXP-50",
                        "unexpected": True,
                    }
                )
            )

    def test_bind_request_must_match_manifest_operation_id(self):
        command = {
            "schema_version": 1,
            "request_id": "req_bridge_bind_50",
            "action": "bind",
            "manifest": {
                "operation_id": "req_other",
                "experiment": {"issue_number": "50"},
            },
        }
        with self.assertRaisesRegex(github_bridge.BridgeError, "operation_id"):
            github_bridge.validate_issue_binding(command, "50")

    def test_experiment_must_match_comment_issue(self):
        command = {
            "schema_version": 1,
            "request_id": "req_bridge_rehearse_50",
            "action": "rehearse",
            "experiment_id": "EXP-50",
        }
        with self.assertRaisesRegex(github_bridge.BridgeError, "match"):
            github_bridge.validate_issue_binding(command, "51")

    @patch("github_bridge.github_json")
    def test_verify_actor_requires_write_permission(self, github_json):
        github_json.return_value = {
            "permission": "read",
            "user": {"login": "alice", "id": 1},
        }
        with self.assertRaisesRegex(github_bridge.BridgeError, "lacks write"):
            github_bridge.verify_actor("owner/repo", "alice")

    @patch("github_bridge.github_json")
    def test_verify_actor_accepts_admin(self, github_json):
        github_json.return_value = {
            "permission": "admin",
            "user": {"login": "alice", "id": 1},
        }
        self.assertEqual(
            github_bridge.verify_actor("owner/repo", "alice"),
            "admin",
        )

    def test_parse_work_claim_and_release_commands(self):
        claim = github_bridge.parse_command(
            self.command(
                {
                    "schema_version": 1,
                    "request_id": "req_work_50",
                    "action": "work_claim",
                    "experiment_id": "EXP-50",
                    "base_source_sha": "b" * 40,
                    "summary": "Tune movement",
                    "paths": ["games/player"],
                    "executor": {"harness": "codex", "agent": "gpt"},
                }
            )
        )
        self.assertEqual(claim["action"], "work_claim")

        release = github_bridge.parse_command(
            self.command(
                {
                    "schema_version": 1,
                    "request_id": "req_release_50",
                    "action": "work_release",
                    "experiment_id": "EXP-50",
                    "claim_id": "req_work_50",
                    "outcome": "ABANDONED",
                    "notes": "No longer needed.",
                    "result_source_sha": None,
                }
            )
        )
        self.assertEqual(release["action"], "work_release")

    @patch("github_bridge.submit_writer")
    def test_work_claim_and_release_use_trusted_writer(self, submit_writer):
        submit_writer.return_value = {"status": "COMMITTED"}
        claim = github_bridge.execute_action(
            {
                "schema_version": 1,
                "request_id": "req_work_50",
                "action": "work_claim",
                "experiment_id": "EXP-50",
                "base_source_sha": "b" * 40,
                "summary": "Tune movement",
                "paths": ["games/player"],
                "executor": {"harness": "codex", "agent": "gpt"},
            },
            repo="owner/repo",
            actor_login="alice",
            comment_id="123",
            ssh_key="/tmp/key",
            run_id="456",
            run_attempt="1",
            workflow_source_sha="a" * 40,
        )
        self.assertEqual(claim["status"], "COMMITTED")
        payload = submit_writer.call_args.args[2]
        self.assertEqual(payload["operation"], "work.claim")
        self.assertEqual(payload["input"]["base_source_sha"], "b" * 40)

        release = github_bridge.execute_action(
            {
                "schema_version": 1,
                "request_id": "req_release_50",
                "action": "work_release",
                "experiment_id": "EXP-50",
                "claim_id": "req_work_50",
                "outcome": "ABANDONED",
                "notes": "Superseded.",
                "result_source_sha": None,
            },
            repo="owner/repo",
            actor_login="alice",
            comment_id="124",
            ssh_key="/tmp/key",
            run_id="457",
            run_attempt="1",
            workflow_source_sha="a" * 40,
        )
        self.assertEqual(release["status"], "COMMITTED")
        payload = submit_writer.call_args.args[2]
        self.assertEqual(payload["operation"], "work.release")
        self.assertNotIn("result_source_sha", payload["input"])

    def test_parse_review_accepts_revision_comparison(self):
        revision = {
            "previous_candidate_id": "C-50-122-1",
            "previous_artifact_digest": "sha256:" + "0" * 64,
            "blind": True,
            "presentation_order": "CURRENT_PREVIOUS",
            "choice": "A_SLIGHTLY_BETTER",
            "notes": "A felt slightly better.",
        }
        command = github_bridge.parse_command(
            self.command(
                {
                    "schema_version": 1,
                    "request_id": "req_review_50",
                    "action": "review_record",
                    "experiment_id": "EXP-50",
                    "candidate_id": "C-50-123-1",
                    "outcome": "PASS",
                    "notes": "Human review.",
                    "revision_comparison": revision,
                }
            )
        )
        self.assertEqual(command["revision_comparison"], revision)

    @patch("github_bridge.submit_writer")
    def test_review_forwards_revision_comparison_to_trusted_writer(
        self,
        submit_writer,
    ):
        submit_writer.return_value = {"status": "COMMITTED"}
        revision = {
            "previous_candidate_id": "C-50-122-1",
            "previous_artifact_digest": "sha256:" + "0" * 64,
            "blind": True,
            "presentation_order": "PREVIOUS_CURRENT",
            "choice": "B_MUCH_BETTER",
            "notes": "B was clearly better.",
        }
        result = github_bridge.execute_action(
            {
                "schema_version": 1,
                "request_id": "req_review_50",
                "action": "review_record",
                "experiment_id": "EXP-50",
                "candidate_id": "C-50-123-1",
                "outcome": "PASS",
                "notes": "Human review.",
                "revision_comparison": revision,
            },
            repo="owner/repo",
            actor_login="alice",
            comment_id="125",
            ssh_key="/tmp/key",
            run_id="458",
            run_attempt="1",
            workflow_source_sha="a" * 40,
        )
        self.assertEqual(result["status"], "COMMITTED")
        payload = submit_writer.call_args.args[2]
        self.assertEqual(payload["operation"], "review.record")
        self.assertEqual(payload["input"]["revision_comparison"], revision)

    @patch("github_bridge._claim_async_execution")
    @patch("github_bridge._dispatch_workflow")
    def test_rehearse_routes_to_existing_trusted_workflow(self, dispatch, claim):
        claim.return_value = {"status": "COMMITTED"}
        dispatch.return_value = {"status": "ACCEPTED"}
        result = github_bridge.execute_action(
            {
                "schema_version": 1,
                "request_id": "req_bridge_rehearse_50",
                "action": "rehearse",
                "experiment_id": "EXP-50",
            },
            repo="owner/repo",
            actor_login="alice",
            comment_id="123",
            ssh_key="/tmp/key",
            run_id="456",
            run_attempt="1",
            workflow_source_sha="a" * 40,
        )
        self.assertEqual(result["status"], "ACCEPTED")
        claim.assert_called_once()
        self.assertEqual(claim.call_args.args[0]["request_id"], "req_bridge_rehearse_50")
        dispatch.assert_called_once_with(
            "owner/repo",
            "game-exp-rehearsal.yml",
            {"experiment_id": "EXP-50"},
            request_id="req_bridge_rehearse_50",
        )

    @patch("github_bridge._claim_async_execution")
    @patch("github_bridge._dispatch_workflow")
    def test_archive_uses_same_claim_and_worker_contract(self, dispatch, claim):
        claim.return_value = {"status": "COMMITTED"}
        dispatch.return_value = {"status": "ACCEPTED"}
        command = {
            "schema_version": 1,
            "request_id": "req_bridge_archive_50",
            "action": "archive",
            "experiment_id": "EXP-50",
            "mode": "ATOMIC_DELETE",
        }
        result = github_bridge.execute_action(
            command,
            repo="owner/repo",
            actor_login="alice",
            comment_id="123",
            ssh_key="/tmp/key",
            run_id="456",
            run_attempt="1",
            workflow_source_sha="a" * 40,
        )
        self.assertEqual(result["status"], "ACCEPTED")
        claim.assert_called_once()
        dispatch.assert_called_once_with(
            "owner/repo",
            "game-exp-archive.yml",
            {"experiment_id": "EXP-50", "mode": "ATOMIC_DELETE"},
            request_id="req_bridge_archive_50",
        )

    @patch("github_bridge._token", return_value="token")
    @patch("github_bridge.subprocess.run")
    def test_worker_dispatch_failure_is_unknown_not_rejected(self, run, _token):
        run.return_value.returncode = 1
        run.return_value.stdout = ""
        run.return_value.stderr = "network uncertain"
        with self.assertRaises(github_bridge.BridgeUncertainError):
            github_bridge._dispatch_workflow(
                "owner/repo",
                "game-exp-candidate.yml",
                {"experiment_id": "EXP-50"},
                request_id="req_bridge_candidate_50",
            )

    def test_bridge_marker_replay_binds_request_id_to_command_digest(self):
        row = {
            "id": 10,
            "html_url": "https://example.test/comment/10",
            "body": "\n".join(
                [
                    github_bridge._marker("req_bridge_50", "result"),
                    github_bridge._command_digest_line("sha256:" + "1" * 64),
                ]
            ),
        }
        same = github_bridge._marker_replay_status(
            row,
            request_id="req_bridge_50",
            command_digest="sha256:" + "1" * 64,
            phase="result",
        )
        self.assertIsNone(same)

        conflict = github_bridge._marker_replay_status(
            row,
            request_id="req_bridge_50",
            command_digest="sha256:" + "2" * 64,
            phase="result",
        )
        self.assertEqual(conflict["status"], "CONFLICT")
        self.assertEqual(conflict["conflict_type"], "REQUEST_ID_CONFLICT")

    def test_legacy_bridge_marker_without_digest_is_unknown(self):
        row = {
            "id": 11,
            "html_url": "https://example.test/comment/11",
            "body": github_bridge._marker("req_bridge_50", "claim"),
        }
        result = github_bridge._marker_replay_status(
            row,
            request_id="req_bridge_50",
            command_digest="sha256:" + "3" * 64,
            phase="claim",
        )
        self.assertEqual(result["status"], "UNKNOWN")
        self.assertEqual(
            result["reason"],
            "legacy_marker_without_command_digest",
        )

    @patch("github_bridge._claim_async_execution")
    @patch("github_bridge._dispatch_workflow")
    def test_non_committed_async_claim_never_dispatches_worker(self, dispatch, claim):
        claim.return_value = {
            "status": "CONFLICT",
            "conflict_type": "REQUEST_ID_CONFLICT",
        }
        command = {
            "schema_version": 1,
            "request_id": "req_bridge_candidate_50",
            "action": "candidate_build",
            "experiment_id": "EXP-50",
        }
        result = github_bridge.execute_action(
            command,
            repo="owner/repo",
            actor_login="alice",
            comment_id="123",
            ssh_key="/tmp/key",
            run_id="456",
            run_attempt="1",
            workflow_source_sha="a" * 40,
        )
        self.assertEqual(result["status"], "CONFLICT")
        dispatch.assert_not_called()

    def test_marker_is_request_scoped(self):
        self.assertEqual(
            github_bridge._marker("req_bridge_50", "claim"),
            "<!-- game-exp-bridge:req_bridge_50:claim -->",
        )


if __name__ == "__main__":
    unittest.main()
