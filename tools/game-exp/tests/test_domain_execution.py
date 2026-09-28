from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

from domain_core import DomainError, TrustedActorContext, TrustedExecutionContext, plan_domain_mutation  # noqa: E402
from protocol_core import build_operation_payload, digest_object  # noqa: E402


class AsyncExecutionClaimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.experiment_id = "EXP-9"
        self.state = {
            "kind": "experiment_state",
            "experiment_id": self.experiment_id,
            "lifecycle": "REVIEW",
            "sequence": 2,
            "last_decision_id": "req-review-state",
            "archive_lock": None,
            "created_by_request_id": "req_bind_9",
            "current_candidate_id": None,
        }
        manifest = {
            "schema_version": 1,
            "experiment": {
                "host": "github.com",
                "repository_id": "1",
                "issue_id": "9",
                "issue_number": "9",
            },
            "title": "Test",
            "operation_id": "req_bind_9",
            "parent": {"experiment": None, "commit": "a" * 40},
            "hypothesis": "test",
            "success_criteria": ["works"],
            "kill_criteria": ["fails"],
            "scope": {"allowed": ["games/test/**"], "avoid": []},
            "runtime": {
                "godot": "4.5",
                "export_templates": "4.5",
                "addons_lock": "none",
            },
            "review": {"protocol": "blind-playtest-v1"},
            "created_at": "2026-09-27T00:00:00Z",
            "subject": {
                "type": "game-prototype",
                "id": "test-game",
                "name": "Test Game",
                "root_path": "games/test",
            },
        }
        bind_payload = build_operation_payload(
            "experiment.bind",
            {"manifest": manifest},
        )
        bind_digest = digest_object(bind_payload)
        root = self.root / "experiments" / self.experiment_id
        root.mkdir(parents=True)
        (root / "manifest.json").write_text(
            json.dumps(manifest, ensure_ascii=False),
            encoding="utf-8",
        )
        binding = {
            "kind": "experiment_identity",
            "experiment_id": self.experiment_id,
            "request_id": "req_bind_9",
            "inputs_digest": bind_digest,
            "parent_sha": "a" * 40,
            "canonical": {
                "host": "github.com",
                "repository_id": "1",
                "issue_id": "9",
                "issue_number": "9",
            },
            "initialization": {
                "manifest_digest": digest_object(manifest),
                "branch_ref": "refs/heads/exp/9",
            },
        }
        (root / "binding.json").write_text(json.dumps(binding), encoding="utf-8")
        (root / "state.json").write_text(json.dumps(self.state), encoding="utf-8")
        operations = self.root / "operations"
        operations.mkdir()
        operation = {
            "request_id": "req_bind_9",
            "payload": bind_payload,
            "payload_digest": bind_digest,
            "domain_status": "APPLIED",
            "domain_experiment_id": self.experiment_id,
            "domain_paths": [
                f"experiments/{self.experiment_id}/binding.json",
                f"experiments/{self.experiment_id}/manifest.json",
                f"experiments/{self.experiment_id}/state.json",
            ],
        }
        (operations / "req_bind_9.json").write_text(
            json.dumps(operation),
            encoding="utf-8",
        )
        self.actor = TrustedActorContext(
            login="alice",
            user_id="1001",
            permission="write",
        )

    def _candidate_fixture(self):
        candidate_id = "C-9-100-1"
        source_sha = "b" * 40
        root = self.root / "experiments" / self.experiment_id
        candidate = {
            "kind": "candidate",
            "candidate_id": candidate_id,
            "experiment_id": self.experiment_id,
            "source_sha": source_sha,
            "manifest_digest": json.loads((root / "binding.json").read_text(encoding="utf-8"))["initialization"]["manifest_digest"],
            "artifact_digest": "sha256:" + "c" * 64,
            "policy_digest": "sha256:" + "d" * 64,
            "workflow_source_sha": "e" * 40,
            "github_run_id": "100",
            "github_run_attempt": "1",
            "checks": [
                {"name": "build", "status": "PASS", "source": "TRUSTED_OBSERVED"},
            ],
            "retention": {
                "provider": "github-immutable-release",
                "immutable": True,
                "artifact_digest": "sha256:" + "c" * 64,
                "release_tag": "game-exp-candidate-9-100-1",
                "release_url": "https://example.test/release",
            },
            "attestation": {
                "provider": "github-artifact-attestations",
                "verified": True,
                "subject_digest": "sha256:" + "c" * 64,
                "source_sha": source_sha,
            },
        }
        path = root / "candidates" / f"{candidate_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(candidate), encoding="utf-8")
        self.state["current_candidate_id"] = candidate_id
        (root / "state.json").write_text(json.dumps(self.state), encoding="utf-8")
        return candidate_id, source_sha

    def plan(self, *, action="candidate_build", arguments=None, state_digest=None, actor=None):
        root = self.root / "experiments" / self.experiment_id
        binding = json.loads((root / "binding.json").read_text(encoding="utf-8"))
        actual_state = json.loads((root / "state.json").read_text(encoding="utf-8"))
        supplied_state_digest = state_digest or digest_object(actual_state)
        preconditions = {
            "protocol_version": 2,
            "experiment_state_digest": supplied_state_digest,
        }
        trusted = TrustedExecutionContext(
            experiment_id=self.experiment_id,
            branch_ref="refs/heads/exp/9",
            branch_head_sha=None,
            main_sha=None,
        )
        if action == "candidate_build":
            preconditions.update(
                {
                    "manifest_digest": binding["initialization"]["manifest_digest"],
                    "source_sha": "b" * 40,
                }
            )
            trusted = TrustedExecutionContext(
                experiment_id=self.experiment_id,
                branch_ref="refs/heads/exp/9",
                branch_head_sha="b" * 40,
                main_sha=None,
            )
        elif action == "initialize":
            preconditions["manifest_digest"] = binding["initialization"]["manifest_digest"]
        elif action == "rehearse":
            candidate_id = actual_state.get("current_candidate_id")
            candidate = json.loads(
                (root / "candidates" / f"{candidate_id}.json").read_text(encoding="utf-8")
            )
            preconditions.update(
                {
                    "candidate_id": candidate_id,
                    "candidate_source_sha": candidate["source_sha"],
                    "main_sha": "f" * 40,
                }
            )
            trusted = TrustedExecutionContext(
                experiment_id=self.experiment_id,
                branch_ref="refs/heads/exp/9",
                branch_head_sha=None,
                main_sha="f" * 40,
            )
        elif action == "archive":
            preconditions["source_sha"] = "b" * 40
            trusted = TrustedExecutionContext(
                experiment_id=self.experiment_id,
                branch_ref="refs/heads/exp/9",
                branch_head_sha="b" * 40,
                main_sha=None,
            )

        payload = build_operation_payload(
            "execution.claim",
            {
                "experiment_id": self.experiment_id,
                "action": action,
                "arguments": arguments or {},
                "state_digest": supplied_state_digest,
            },
            preconditions=preconditions,
        )
        return plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id="req_exec_9",
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_actor=self.actor if actor is None else actor,
            trusted_execution=trusted,
        )

    def test_claim_is_request_only_and_bound_to_experiment(self):
        plan = self.plan()
        self.assertEqual(plan.status, "REQUEST_ONLY")
        self.assertEqual(plan.experiment_id, self.experiment_id)
        self.assertEqual(plan.writes, {})

    def test_claim_rejects_stale_state(self):
        with self.assertRaises(DomainError) as ctx:
            self.plan(state_digest="sha256:" + "0" * 64)
        self.assertEqual(ctx.exception.code, "DOMAIN_EXECUTION_CONFLICT")

    def test_claim_rejects_read_only_actor(self):
        with self.assertRaises(DomainError) as ctx:
            self.plan(
                actor=TrustedActorContext(
                    login="reader",
                    user_id="1002",
                    permission="read",
                )
            )
        self.assertEqual(ctx.exception.code, "DOMAIN_AUTHORIZATION_FAILED")

    def test_claim_rejects_wrong_lifecycle(self):
        with self.assertRaises(DomainError) as ctx:
            self.plan(action="initialize")
        self.assertEqual(ctx.exception.code, "DOMAIN_EXECUTION_CONFLICT")

    def test_selected_experiment_can_claim_rehearsal_refresh(self):
        selected = dict(self.state)
        selected["lifecycle"] = "SELECTED"
        root = self.root / "experiments" / self.experiment_id
        (root / "state.json").write_text(json.dumps(selected), encoding="utf-8")
        self.state = selected
        self._candidate_fixture()
        plan = self.plan(action="rehearse")
        self.assertEqual(plan.status, "REQUEST_ONLY")
        self.assertEqual(plan.experiment_id, self.experiment_id)

    def test_rejected_and_abandoned_experiments_can_claim_archive(self):
        root = self.root / "experiments" / self.experiment_id
        for lifecycle in ("REJECTED", "ABANDONED"):
            with self.subTest(lifecycle=lifecycle):
                state = dict(self.state)
                state["lifecycle"] = lifecycle
                (root / "state.json").write_text(json.dumps(state), encoding="utf-8")
                self.state = state
                plan = self.plan(
                    action="archive",
                    arguments={"mode": "RETAIN_BRANCH"},
                )
                self.assertEqual(plan.status, "REQUEST_ONLY")
                self.assertEqual(plan.experiment_id, self.experiment_id)

    def test_claim_validates_action_arguments(self):
        with self.assertRaises(DomainError) as ctx:
            self.plan(action="archive", arguments={"mode": "DELETE"})
        self.assertEqual(ctx.exception.code, "DOMAIN_EXECUTION_INVALID")


if __name__ == "__main__":
    unittest.main()
