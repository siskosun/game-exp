from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

from domain_core import (  # noqa: E402
    DomainError,
    TrustedActorContext,
    TrustedBindingContext,
    TrustedExecutionContext,
    plan_domain_mutation,
)
from protocol_core import build_operation_payload, digest_object  # noqa: E402


def manifest(request_id="req_bind_88"):
    return {
        "schema_version": 1,
        "experiment": {
            "host": "github.com",
            "repository_id": "1384446218",
            "issue_id": "5000000088",
            "issue_number": "88",
        },
        "title": "Execution precondition test",
        "operation_id": request_id,
        "parent": {"experiment": None, "commit": "a" * 40},
        "hypothesis": "Protected async work must remain bound to exact state.",
        "success_criteria": ["Stale source is rejected."],
        "kill_criteria": ["Worker silently changes source."],
        "scope": {"allowed": ["games/**"], "avoid": [".github/**"]},
        "runtime": {
            "godot": "n/a",
            "export_templates": "n/a",
            "addons_lock": "sha256:none",
        },
        "review": {"protocol": "manual-playtest-v1"},
        "created_at": "2026-09-28T12:00:00+08:00",
    }


class ExecutionPreconditionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.actor = TrustedActorContext(
            login="alice",
            user_id="101",
            permission="write",
        )
        bind_request = "req_bind_88"
        mf = manifest(bind_request)
        payload = build_operation_payload("experiment.bind", {"manifest": mf})
        plan = plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id=bind_request,
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_binding=TrustedBindingContext(
                host="github.com",
                repository_id="1384446218",
                issue_id="5000000088",
                issue_number="88",
                parent_sha="a" * 40,
            ),
            trusted_actor=self.actor,
        )
        for path, value in plan.writes.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value), encoding="utf-8")
        operation = {
            "domain_experiment_id": "EXP-88",
            "domain_paths": plan.paths,
            "domain_status": "APPLIED",
            "payload": payload,
            "payload_digest": digest_object(payload),
            "request_id": bind_request,
        }
        target = self.root / f"operations/{bind_request}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(operation), encoding="utf-8")

    def state(self):
        return json.loads(
            (self.root / "experiments/EXP-88/state.json").read_text(encoding="utf-8")
        )

    def execution(self, *, source_sha="b" * 40, protocol_version=2):
        state = self.state()
        preconditions = {
            "protocol_version": protocol_version,
            "experiment_state_digest": digest_object(state),
            "manifest_digest": json.loads(
                (self.root / "experiments/EXP-88/binding.json").read_text(encoding="utf-8")
            )["initialization"]["manifest_digest"],
            "source_sha": source_sha,
        }
        payload = build_operation_payload(
            "execution.claim",
            {
                "experiment_id": "EXP-88",
                "action": "candidate_build",
                "arguments": {},
                "state_digest": digest_object(state),
            },
            preconditions=preconditions,
        )
        return payload

    def test_candidate_build_claim_accepts_exact_source(self):
        payload = self.execution()
        plan = plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id="req_exec_88",
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_actor=self.actor,
            trusted_execution=TrustedExecutionContext(
                experiment_id="EXP-88",
                branch_ref="refs/heads/exp/88",
                branch_head_sha="b" * 40,
                main_sha=None,
            ),
        )
        self.assertEqual(plan.status, "REQUEST_ONLY")

    def test_candidate_build_claim_rejects_source_advanced(self):
        payload = self.execution(source_sha="b" * 40)
        with self.assertRaises(DomainError) as ctx:
            plan_domain_mutation(
                repo_dir=self.root,
                payload=payload,
                request_id="req_exec_stale",
                payload_digest=digest_object(payload),
                repository_full_name="owner/repo",
                trusted_actor=self.actor,
                trusted_execution=TrustedExecutionContext(
                    experiment_id="EXP-88",
                    branch_ref="refs/heads/exp/88",
                    branch_head_sha="c" * 40,
                    main_sha=None,
                ),
            )
        self.assertEqual(ctx.exception.code, "DOMAIN_EXECUTION_CONFLICT")

    def test_legacy_async_claim_requires_client_upgrade(self):
        state = self.state()
        payload = build_operation_payload(
            "execution.claim",
            {
                "experiment_id": "EXP-88",
                "action": "candidate_build",
                "arguments": {},
                "state_digest": digest_object(state),
            },
        )
        with self.assertRaises(DomainError) as ctx:
            plan_domain_mutation(
                repo_dir=self.root,
                payload=payload,
                request_id="req_exec_legacy",
                payload_digest=digest_object(payload),
                repository_full_name="owner/repo",
                trusted_actor=self.actor,
                trusted_execution=TrustedExecutionContext(
                    experiment_id="EXP-88",
                    branch_ref="refs/heads/exp/88",
                    branch_head_sha="b" * 40,
                    main_sha=None,
                ),
            )
        self.assertEqual(ctx.exception.code, "DOMAIN_CLIENT_UPGRADE_REQUIRED")


if __name__ == "__main__":
    unittest.main()
