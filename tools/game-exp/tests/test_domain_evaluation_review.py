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
    TrustedActorContext,
    TrustedBindingContext,
    TrustedCandidateContext,
    plan_domain_mutation,
)
from protocol_core import build_operation_payload, digest_object  # noqa: E402


PROFILE_DIGEST = "sha256:" + "9" * 64


def manifest(issue: int, *, supersedes: str | None = None):
    value = {
        "schema_version": 3,
        "experiment": {
            "host": "github.com",
            "repository_id": "1384446218",
            "issue_id": str(5000000000 + issue),
            "issue_number": str(issue),
        },
        "title": f"Experiment {issue}",
        "operation_id": f"req_bind_{issue}",
        "parent": {"experiment": None, "commit": "a" * 40},
        "hypothesis": "The challenger may improve the tested interaction.",
        "success_criteria": ["Human comparison can inform the Review."],
        "kill_criteria": ["The challenger is worse under the tested conditions."],
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
    if supersedes is not None:
        value["relationships"] = [
            {"type": "supersedes", "experiment_id": supersedes}
        ]
    return value


def evaluation(profile_digest=PROFILE_DIGEST):
    return {
        "profile_id": "squad-choice-v1",
        "profile_digest": profile_digest,
        "result_digest": "sha256:" + "1" * 64,
        "bundle_digest": "sha256:" + "2" * 64,
        "bundle_asset_name": "evaluation-output.tgz",
        "screening": "ELIGIBLE",
        "source": "TRUSTED_OBSERVED",
        "run_mode": "TRUSTED_REPLAY",
        "trace_digest": "sha256:" + "3" * 64,
        "step_mode": "SCENE_CONTROLLED",
        "requirements": [
            {"id": "launch", "status": "PASS", "classification": "NONE"}
        ],
    }


class EvaluationReviewTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.actor = TrustedActorContext(
            login="alice",
            user_id="101",
            permission="write",
        )
        self._bind(76)
        self._bind(77, supersedes="EXP-76")
        self._candidate(76, "101", "sha256:" + "6" * 64)
        self._candidate(77, "102", "sha256:" + "7" * 64)
        state_path = self.root / "experiments/EXP-77/state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["lifecycle"] = "REVIEW"
        state_path.write_text(json.dumps(state), encoding="utf-8")

    def _apply(self, plan):
        for path, value in plan.writes.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value), encoding="utf-8")

    def _bind(self, issue: int, *, supersedes: str | None = None):
        mf = manifest(issue, supersedes=supersedes)
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
                issue_id=str(5000000000 + issue),
                issue_number=str(issue),
                parent_sha="a" * 40,
            ),
            trusted_actor=self.actor,
        )
        self._apply(plan)
        op_path = self.root / "operations" / f"{mf['operation_id']}.json"
        op_path.parent.mkdir(parents=True, exist_ok=True)
        op_path.write_text(
            json.dumps(
                {
                    "domain_experiment_id": f"EXP-{issue}",
                    "domain_paths": plan.paths,
                    "domain_status": "APPLIED",
                    "payload": payload,
                    "payload_digest": digest_object(payload),
                    "request_id": mf["operation_id"],
                }
            ),
            encoding="utf-8",
        )

    def _candidate(self, issue: int, run_id: str, artifact_digest: str):
        experiment_id = f"EXP-{issue}"
        binding = json.loads(
            (self.root / f"experiments/{experiment_id}/binding.json").read_text(
                encoding="utf-8"
            )
        )
        context = TrustedCandidateContext(
            experiment_id=experiment_id,
            candidate_id=f"C-{issue}-{run_id}-1",
            source_sha="b" * 40,
            manifest_digest=binding["initialization"]["manifest_digest"],
            artifact_digest=artifact_digest,
            policy_digest="sha256:" + "d" * 64,
            workflow_source_sha="e" * 40,
            run_id=run_id,
            run_attempt="1",
            checks=(
                {"name": "project_tests", "status": "PASS", "source": "TRUSTED_OBSERVED"},
            ),
            retention={
                "provider": "github-immutable-release",
                "release_tag": f"game-exp-candidate-{issue}-{run_id}-1",
                "release_url": "https://example.test/release",
                "immutable": True,
                "artifact_digest": artifact_digest,
            },
            attestation={
                "provider": "github-artifact-attestations",
                "verified": True,
                "subject_digest": artifact_digest,
                "source_sha": "b" * 40,
            },
            evaluation=evaluation(),
        )
        payload = build_operation_payload(
            "candidate.register",
            {"experiment_id": experiment_id},
        )
        plan = plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id=f"req_candidate_{issue}",
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_candidate=context,
        )
        self._apply(plan)

    def comparison(self):
        return {
            "incumbent_experiment_id": "EXP-76",
            "incumbent_candidate_id": "C-76-101-1",
            "incumbent_artifact_digest": "sha256:" + "6" * 64,
            "profile_digest": PROFILE_DIGEST,
            "blind": True,
            "presentation_order": "CHALLENGER_INCUMBENT",
            "dimensions": [
                {
                    "id": "mechanic_clarity",
                    "choice": "CHALLENGER",
                    "notes": "I understood the consequence of squad choice sooner.",
                },
                {
                    "id": "control_feel",
                    "choice": "NO_CLEAR_DIFFERENCE",
                    "notes": "No meaningful difference in this session.",
                },
            ],
            "overall": "NO_CLEAR_DIFFERENCE",
        }

    def _review(self, comparison):
        payload = build_operation_payload(
            "review.record",
            {
                "experiment_id": "EXP-77",
                "candidate_id": "C-77-102-1",
                "outcome": "PASS",
                "notes": "Human explicitly approved continuing the challenger.",
                "comparison": comparison,
            },
        )
        return plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id="req_review_77",
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_actor=self.actor,
        )

    def test_blind_ab_is_human_reported_review_evidence(self):
        plan = self._review(self.comparison())
        review = plan.writes["experiments/EXP-77/reviews/req_review_77.json"]
        comparison = review["comparison"]
        self.assertEqual(comparison["evidence_source"], "HUMAN_REPORTED")
        self.assertEqual(comparison["incumbent_candidate_id"], "C-76-101-1")
        self.assertEqual(comparison["challenger_candidate_id"], "C-77-102-1")
        self.assertEqual(comparison["overall"], "NO_CLEAR_DIFFERENCE")
        self.assertEqual(review["outcome"], "PASS")
        self.assertEqual(
            plan.writes["experiments/EXP-77/state.json"]["lifecycle"],
            "REVIEW",
        )

    def test_comparison_requires_supersedes_incumbent(self):
        comparison = self.comparison()
        comparison["incumbent_experiment_id"] = "EXP-75"
        with self.assertRaises(DomainError) as ctx:
            self._review(comparison)
        self.assertEqual(ctx.exception.code, "DOMAIN_REVIEW_CONFLICT")

    def test_comparison_requires_same_profile_digest_on_both_candidates(self):
        incumbent_path = (
            self.root / "experiments/EXP-76/candidates/C-76-101-1.json"
        )
        incumbent = json.loads(incumbent_path.read_text(encoding="utf-8"))
        incumbent["evaluation"]["profile_digest"] = "sha256:" + "0" * 64
        incumbent_path.write_text(json.dumps(incumbent), encoding="utf-8")
        with self.assertRaises(DomainError) as ctx:
            self._review(self.comparison())
        self.assertEqual(ctx.exception.code, "DOMAIN_REVIEW_CONFLICT")

    def test_comparison_requires_blind_true(self):
        comparison = self.comparison()
        comparison["blind"] = False
        with self.assertRaises(DomainError) as ctx:
            self._review(comparison)
        self.assertEqual(ctx.exception.code, "DOMAIN_REVIEW_CONFLICT")


if __name__ == "__main__":
    unittest.main()
