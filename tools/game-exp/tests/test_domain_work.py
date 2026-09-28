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
    TrustedWorkContext,
    plan_domain_mutation,
)
from protocol_core import build_operation_payload, digest_object  # noqa: E402


def manifest(request_id="req_bind_77"):
    return {
        "schema_version": 1,
        "experiment": {
            "host": "github.com",
            "repository_id": "1384446218",
            "issue_id": "5000000077",
            "issue_number": "77",
        },
        "title": "Collaboration coordination",
        "operation_id": request_id,
        "parent": {"experiment": None, "commit": "a" * 40},
        "hypothesis": "Explicit work intent reduces stale collaborative edits.",
        "success_criteria": ["Harnesses detect stale source before editing."],
        "kill_criteria": ["Coordination requires serializing all source work."],
        "scope": {"allowed": ["games/**"], "avoid": [".github/**"]},
        "runtime": {
            "godot": "n/a",
            "export_templates": "n/a",
            "addons_lock": "sha256:none",
        },
        "review": {"protocol": "manual-playtest-v1"},
        "created_at": "2026-09-28T12:00:00+08:00",
    }


class WorkCoordinationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.owner = TrustedActorContext(
            login="alice",
            user_id="101",
            permission="write",
        )
        self.other = TrustedActorContext(
            login="bob",
            user_id="202",
            permission="write",
        )
        self.admin = TrustedActorContext(
            login="admin",
            user_id="303",
            permission="admin",
        )
        self.work = TrustedWorkContext(
            experiment_id="EXP-77",
            branch_ref="refs/heads/exp/77",
            branch_head_sha="b" * 40,
        )

        bind_request = "req_bind_77"
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
                issue_id="5000000077",
                issue_number="77",
                parent_sha="a" * 40,
            ),
            trusted_actor=self.owner,
        )
        self.apply(plan)
        operation = {
            "domain_experiment_id": "EXP-77",
            "domain_paths": plan.paths,
            "domain_status": "APPLIED",
            "payload": payload,
            "payload_digest": digest_object(payload),
            "request_id": bind_request,
        }
        target = self.root / f"operations/{bind_request}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(operation), encoding="utf-8")

    def apply(self, plan):
        for path, value in plan.writes.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value), encoding="utf-8")

    def claim(
        self,
        request_id,
        *,
        actor=None,
        base_source_sha=None,
        paths=None,
        summary="Tune movement feel",
        harness="codex",
        agent="gpt",
    ):
        payload = build_operation_payload(
            "work.claim",
            {
                "experiment_id": "EXP-77",
                "base_source_sha": base_source_sha or "b" * 40,
                "summary": summary,
                "paths": ["games/player"] if paths is None else paths,
                "executor": {
                    "harness": harness,
                    "agent": agent,
                    "session_id": f"session-{request_id}",
                },
            },
        )
        return plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id=request_id,
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_actor=actor or self.owner,
            trusted_work=self.work,
        )

    def release(
        self,
        request_id,
        claim_id,
        *,
        actor=None,
        outcome="COMPLETED",
        result_source_sha=None,
    ):
        value = {
            "experiment_id": "EXP-77",
            "claim_id": claim_id,
            "outcome": outcome,
            "notes": "Work finished and reconciled.",
        }
        if result_source_sha is not None:
            value["result_source_sha"] = result_source_sha
        elif outcome == "COMPLETED":
            value["result_source_sha"] = "b" * 40
        payload = build_operation_payload("work.release", value)
        return plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id=request_id,
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_actor=actor or self.owner,
            trusted_work=self.work,
        )

    def test_work_claim_binds_current_branch_actor_and_executor(self):
        plan = self.claim("req_work_1")
        claim = plan.writes["experiments/EXP-77/work-claims/req_work_1.json"]
        state = plan.writes["experiments/EXP-77/state.json"]
        self.assertEqual(claim["base_source_sha"], "b" * 40)
        self.assertEqual(claim["branch_ref"], "refs/heads/exp/77")
        self.assertEqual(claim["actor"]["login"], "alice")
        self.assertEqual(claim["executor"]["harness"], "codex")
        self.assertEqual(claim["paths"], ["games/player"])
        self.assertFalse(claim["coordination_required"])
        self.assertEqual(state["active_work_claim_ids"], ["req_work_1"])

    def test_stale_work_claim_is_rejected_before_editing(self):
        with self.assertRaises(DomainError) as ctx:
            self.claim("req_work_stale", base_source_sha="c" * 40)
        self.assertEqual(ctx.exception.code, "DOMAIN_WORK_STALE")

    def test_overlapping_claim_is_recorded_not_blocked(self):
        first = self.claim("req_work_1")
        self.apply(first)
        second = self.claim(
            "req_work_2",
            actor=self.other,
            paths=["games/player/movement"],
            harness="qoder",
            agent="qoder-agent",
        )
        claim = second.writes["experiments/EXP-77/work-claims/req_work_2.json"]
        self.assertTrue(claim["coordination_required"])
        self.assertEqual(claim["overlap_with"], ["req_work_1"])

    def test_unknown_scope_overlaps_conservatively(self):
        first = self.claim("req_work_1", paths=[])
        self.apply(first)
        second = self.claim("req_work_2", actor=self.other, paths=["games/ui"])
        claim = second.writes["experiments/EXP-77/work-claims/req_work_2.json"]
        self.assertTrue(claim["coordination_required"])

    def test_completed_release_requires_current_canonical_head(self):
        first = self.claim("req_work_1")
        self.apply(first)
        plan = self.release("req_release_1", "req_work_1")
        release = plan.writes["experiments/EXP-77/work-releases/req_release_1.json"]
        state = plan.writes["experiments/EXP-77/state.json"]
        self.assertEqual(release["result_source_sha"], "b" * 40)
        self.assertEqual(state["active_work_claim_ids"], [])

        first = self.claim("req_work_2")
        self.apply(first)
        with self.assertRaises(DomainError) as ctx:
            self.release(
                "req_release_stale",
                "req_work_2",
                result_source_sha="c" * 40,
            )
        self.assertEqual(ctx.exception.code, "DOMAIN_WORK_STALE")

    def test_other_writer_cannot_release_claim_but_admin_can(self):
        first = self.claim("req_work_1")
        self.apply(first)
        with self.assertRaises(DomainError) as ctx:
            self.release("req_release_other", "req_work_1", actor=self.other)
        self.assertEqual(ctx.exception.code, "DOMAIN_AUTHORIZATION_FAILED")

        plan = self.release("req_release_admin", "req_work_1", actor=self.admin)
        self.assertIn(
            "experiments/EXP-77/work-releases/req_release_admin.json",
            plan.writes,
        )

    def test_abandoned_release_has_no_result_source(self):
        first = self.claim("req_work_1")
        self.apply(first)
        plan = self.release(
            "req_release_abandoned",
            "req_work_1",
            outcome="ABANDONED",
        )
        release = plan.writes[
            "experiments/EXP-77/work-releases/req_release_abandoned.json"
        ]
        self.assertIsNone(release["result_source_sha"])

    def test_work_claim_requires_active_or_review_lifecycle(self):
        state_path = self.root / "experiments/EXP-77/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["lifecycle"] = "PROMISING"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        with self.assertRaises(DomainError) as ctx:
            self.claim("req_work_promising")
        self.assertEqual(ctx.exception.code, "DOMAIN_WORK_CONFLICT")


if __name__ == "__main__":
    unittest.main()
