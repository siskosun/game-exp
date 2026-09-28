from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

import execution_guard  # noqa: E402
from protocol_core import digest_object  # noqa: E402


class ExecutionGuardTests(unittest.TestCase):
    def fixture(self, *, source_sha="b" * 40, main_sha="m" * 40):
        state = {
            "kind": "experiment_state",
            "experiment_id": "EXP-7",
            "lifecycle": "REVIEW",
            "current_candidate_id": "C-7-10-1",
            "current_rehearsal_id": "R-7-11-1",
        }
        binding = {
            "kind": "experiment_identity",
            "experiment_id": "EXP-7",
            "initialization": {
                "branch_ref": "refs/heads/exp/7",
                "manifest_digest": "sha256:" + "1" * 64,
            },
        }
        candidate = {
            "kind": "candidate",
            "experiment_id": "EXP-7",
            "candidate_id": "C-7-10-1",
            "source_sha": source_sha,
        }
        return state, binding, candidate

    def operation(self, state, *, action="candidate_build", source_sha="b" * 40):
        pre = {
            "protocol_version": 2,
            "experiment_state_digest": digest_object(state),
        }
        if action == "candidate_build":
            pre.update(
                {
                    "manifest_digest": "sha256:" + "1" * 64,
                    "source_sha": source_sha,
                }
            )
        elif action == "rehearse":
            pre.update(
                {
                    "candidate_id": "C-7-10-1",
                    "candidate_source_sha": source_sha,
                    "main_sha": "d" * 40,
                }
            )
        return {
            "domain_status": "REQUEST_ONLY",
            "payload": {
                "kind": "operation_request",
                "operation": "execution.claim",
                "input": {
                    "experiment_id": "EXP-7",
                    "action": action,
                    "arguments": {},
                    "state_digest": digest_object(state),
                },
                "preconditions": pre,
            },
        }

    def test_candidate_build_guard_accepts_exact_claim(self):
        state, binding, candidate = self.fixture()
        operation = self.operation(state)
        def content(_repo, path, _ref):
            if path.startswith("operations/"):
                return operation
            if path.endswith("/state.json"):
                return state
            if path.endswith("/binding.json"):
                return binding
            if "/candidates/" in path:
                return candidate
            raise AssertionError(path)
        def refs(_repo, ref_path):
            return {
                "heads/exp/7": "b" * 40,
                "heads/game-exp/ledger": "e" * 40,
            }[ref_path]
        with patch.object(execution_guard, "github_content_json", side_effect=content), patch.object(
            execution_guard, "ref_sha", side_effect=refs
        ):
            result = execution_guard.evaluate(
                repo="owner/repo",
                action="candidate_build",
                experiment_id="EXP-7",
                request_id="req_exec_7",
            )
        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["preconditions"]["source_sha"], "b" * 40)

    def test_guard_rejects_source_advance_after_claim(self):
        state, binding, _candidate = self.fixture()
        operation = self.operation(state)
        def content(_repo, path, _ref):
            if path.startswith("operations/"):
                return operation
            if path.endswith("/state.json"):
                return state
            if path.endswith("/binding.json"):
                return binding
            raise AssertionError(path)
        def refs(_repo, ref_path):
            if ref_path == "heads/exp/7":
                return "c" * 40
            return "e" * 40
        with patch.object(execution_guard, "github_content_json", side_effect=content), patch.object(
            execution_guard, "ref_sha", side_effect=refs
        ):
            with self.assertRaises(execution_guard.ExecutionGuardError):
                execution_guard.evaluate(
                    repo="owner/repo",
                    action="candidate_build",
                    experiment_id="EXP-7",
                    request_id="req_exec_7",
                )

    def test_rehearsal_guard_rejects_main_advance(self):
        state, binding, candidate = self.fixture()
        operation = self.operation(state, action="rehearse")
        def content(_repo, path, _ref):
            if path.startswith("operations/"):
                return operation
            if path.endswith("/state.json"):
                return state
            if path.endswith("/binding.json"):
                return binding
            if "/candidates/" in path:
                return candidate
            raise AssertionError(path)
        def refs(_repo, ref_path):
            if ref_path == "heads/main":
                return "f" * 40
            if ref_path == "heads/game-exp/ledger":
                return "e" * 40
            raise AssertionError(ref_path)
        with patch.object(execution_guard, "github_content_json", side_effect=content), patch.object(
            execution_guard, "ref_sha", side_effect=refs
        ):
            with self.assertRaises(execution_guard.ExecutionGuardError):
                execution_guard.evaluate(
                    repo="owner/repo",
                    action="rehearse",
                    experiment_id="EXP-7",
                    request_id="req_rehearse_7",
                )


if __name__ == "__main__":
    unittest.main()
