from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from domain_core import (  # noqa: E402
    DomainError,
    TrustedBindingContext,
    TrustedCandidateContext,
    plan_domain_mutation,
    validate_manifest,
)
from protocol_core import build_operation_payload, digest_object  # noqa: E402


PROFILE_DIGEST = "sha256:" + "9" * 64


def manifest(request_id="req_bind_77"):
    return {
        "schema_version": 3,
        "experiment": {
            "host": "github.com",
            "repository_id": "1384446218",
            "issue_id": "5000000077",
            "issue_number": "77",
        },
        "title": "Evaluation evidence",
        "operation_id": request_id,
        "parent": {"experiment": None, "commit": "a" * 40},
        "hypothesis": "A shared evaluation profile makes the challenger comparable to the incumbent.",
        "success_criteria": ["Trusted replay evidence is bound to the Candidate."],
        "kill_criteria": ["Screening can be forged by project-reported evidence."],
        "scope": {"allowed": ["games/**"], "avoid": [".game-exp/**"]},
        "runtime": {
            "adapter": "command",
            "policy_path": ".game-exp/project-policy.json",
        },
        "evaluation_profile": {
            "path": ".game-exp/evaluation-profiles/squad-choice-v1.json",
            "digest": PROFILE_DIGEST,
            "version": 1,
        },
        "review": {"protocol": "incumbent-challenger-blind-ab-v1"},
        "created_at": "2026-09-28T18:00:00+08:00",
    }


def evaluation(screening="ELIGIBLE", source="TRUSTED_OBSERVED"):
    return {
        "profile_id": "squad-choice-v1",
        "profile_digest": PROFILE_DIGEST,
        "result_digest": "sha256:" + "1" * 64,
        "bundle_digest": "sha256:" + "2" * 64,
        "bundle_asset_name": "evaluation-output.tgz",
        "screening": screening,
        "source": source,
        "run_mode": "TRUSTED_REPLAY",
        "trace_digest": "sha256:" + "3" * 64,
        "step_mode": "SCENE_CONTROLLED",
        "requirements": [
            {"id": "launch", "status": "PASS", "classification": "NONE"},
            {
                "id": "choice_changes_battle",
                "status": (
                    "FAIL_PRODUCT_DEFECT"
                    if screening == "INELIGIBLE"
                    else "INCONCLUSIVE"
                    if screening == "INCONCLUSIVE"
                    else "PASS"
                ),
                "classification": (
                    "PRODUCT_DEFECT"
                    if screening == "INELIGIBLE"
                    else "TEST_HARNESS"
                    if screening == "INCONCLUSIVE"
                    else "NONE"
                ),
            },
        ],
    }


class EvaluationDomainTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        mf = manifest()
        payload = build_operation_payload("experiment.bind", {"manifest": mf})
        plan = plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id=mf["operation_id"],
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_binding=TrustedBindingContext(
                host="github.com",
                repository_id="1384446218",
                issue_id="5000000077",
                issue_number="77",
                parent_sha="a" * 40,
            ),
        )
        for path, value in plan.writes.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value), encoding="utf-8")
        op_path = self.root / "operations" / f"{mf['operation_id']}.json"
        op_path.parent.mkdir(parents=True, exist_ok=True)
        op_path.write_text(
            json.dumps(
                {
                    "domain_experiment_id": "EXP-77",
                    "domain_paths": plan.paths,
                    "domain_status": "APPLIED",
                    "payload": payload,
                    "payload_digest": digest_object(payload),
                    "request_id": mf["operation_id"],
                }
            ),
            encoding="utf-8",
        )
        self.manifest_digest = plan.writes[
            "experiments/EXP-77/binding.json"
        ]["initialization"]["manifest_digest"]

    def candidate_context(self, **overrides):
        value = {
            "experiment_id": "EXP-77",
            "candidate_id": "C-77-123-1",
            "source_sha": "b" * 40,
            "manifest_digest": self.manifest_digest,
            "artifact_digest": "sha256:" + "c" * 64,
            "policy_digest": "sha256:" + "d" * 64,
            "workflow_source_sha": "e" * 40,
            "run_id": "123",
            "run_attempt": "1",
            "checks": (
                {"name": "project_tests", "status": "PASS", "source": "TRUSTED_OBSERVED"},
                {"name": "build", "status": "PASS", "source": "TRUSTED_OBSERVED"},
            ),
            "retention": {
                "provider": "github-immutable-release",
                "release_tag": "game-exp-candidate-77-123-1",
                "release_url": "https://example.test/release",
                "immutable": True,
                "artifact_digest": "sha256:" + "c" * 64,
            },
            "attestation": {
                "provider": "github-artifact-attestations",
                "verified": True,
                "subject_digest": "sha256:" + "c" * 64,
                "source_sha": "b" * 40,
            },
            "evaluation": evaluation(),
        }
        value.update(overrides)
        return TrustedCandidateContext(**value)

    def plan_candidate(self, context):
        payload = build_operation_payload(
            "candidate.register",
            {"experiment_id": "EXP-77"},
        )
        return plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id="req_candidate_eval",
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_candidate=context,
        )

    def test_schema_v3_requires_profile_reference(self):
        value = manifest()
        value.pop("evaluation_profile")
        with self.assertRaises(DomainError):
            validate_manifest(value)

    def test_schema_v2_rejects_evaluation_profile(self):
        value = manifest()
        value["schema_version"] = 2
        with self.assertRaises(DomainError):
            validate_manifest(value)

    def test_candidate_stores_trusted_screening_without_lifecycle_change(self):
        plan = self.plan_candidate(self.candidate_context())
        candidate = plan.writes[
            "experiments/EXP-77/candidates/C-77-123-1.json"
        ]
        state = plan.writes["experiments/EXP-77/state.json"]
        self.assertEqual(candidate["evaluation"]["screening"], "ELIGIBLE")
        self.assertEqual(candidate["evaluation"]["source"], "TRUSTED_OBSERVED")
        self.assertEqual(state["lifecycle"], "ACTIVE")

    def test_ineligible_screening_does_not_auto_reject(self):
        plan = self.plan_candidate(
            self.candidate_context(evaluation=evaluation("INELIGIBLE"))
        )
        candidate = plan.writes[
            "experiments/EXP-77/candidates/C-77-123-1.json"
        ]
        state = plan.writes["experiments/EXP-77/state.json"]
        self.assertEqual(candidate["evaluation"]["screening"], "INELIGIBLE")
        self.assertEqual(state["lifecycle"], "ACTIVE")

    def test_untrusted_evaluation_is_rejected(self):
        with self.assertRaises(DomainError) as ctx:
            self.plan_candidate(
                self.candidate_context(
                    evaluation=evaluation(source="PARTICIPANT_REPORTED")
                )
            )
        self.assertEqual(ctx.exception.code, "DOMAIN_PREREQUISITE_MISSING")

    def test_profile_digest_mismatch_is_rejected(self):
        bad = evaluation()
        bad["profile_digest"] = "sha256:" + "0" * 64
        with self.assertRaises(DomainError) as ctx:
            self.plan_candidate(self.candidate_context(evaluation=bad))
        self.assertEqual(ctx.exception.code, "DOMAIN_CANDIDATE_CONFLICT")


if __name__ == "__main__":
    unittest.main()
