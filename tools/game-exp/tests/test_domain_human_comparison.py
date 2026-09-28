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


def manifest(issue: int, *, review_protocol: str, supersedes: str | None = None):
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
        "hypothesis": "Comparison evidence stays bound to exact Candidates.",
        "success_criteria": ["Human comparison is traceable."],
        "kill_criteria": ["A stale or unrelated incumbent can be compared."],
        "scope": {"allowed": ["games/**"], "avoid": [".game-exp/**"]},
        "runtime": {
            "adapter": "command",
            "policy_path": ".game-exp/project-policy.json",
        },
        "evaluation_profile": {
            "path": ".game-exp/evaluation-profiles/shared-v1.json",
            "digest": PROFILE_DIGEST,
            "version": 1,
        },
        "review": {"protocol": review_protocol},
        "created_at": "2026-09-28T18:00:00+08:00",
    }
    if supersedes:
        value["relationships"] = [
            {"type": "supersedes", "experiment_id": supersedes}
        ]
    return value


def evaluation(profile_digest=PROFILE_DIGEST):
    return {
        "profile_id": "shared-v1",
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
            {"id": "launch", "status": "PASS", "classification": "NONE"},
        ],
    }


class HumanComparisonTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = pathlib.Path(self.tmp.name)
        self.actor = TrustedActorContext(
            login="reviewer",
            user_id="101",
            permission="write",
        )
        self._bind(76, review_protocol="manual-playtest-v1")
        self._bind(
            77,
            review_protocol="incumbent-challenger-blind-ab-v1",
            supersedes="EXP-76",
        )
        self._candidate(76, run_id="100")
        self._candidate(77, run_id="101")
        self._to_review(77)

    def _apply(self, plan):
        for path, value in plan.writes.items():
            target = self.root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps(value), encoding="utf-8")

    def _bind(self, issue: int, *, review_protocol: str, supersedes=None):
        mf = manifest(issue, review_protocol=review_protocol, supersedes=supersedes)
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
        operation = {
            "domain_experiment_id": f"EXP-{issue}",
            "domain_paths": plan.paths,
            "domain_status": "APPLIED",
            "payload": payload,
            "payload_digest": digest_object(payload),
            "request_id": mf["operation_id"],
        }
        op = self.root / "operations" / f"{mf['operation_id']}.json"
        op.parent.mkdir(parents=True, exist_ok=True)
        op.write_text(json.dumps(operation), encoding="utf-8")

    def _candidate(self, issue: int, *, run_id: str):
        binding = json.loads(
            (self.root / f"experiments/EXP-{issue}/binding.json").read_text(
                encoding="utf-8"
            )
        )
        artifact = "sha256:" + (("c" if issue == 76 else "d") * 64)
        context = TrustedCandidateContext(
            experiment_id=f"EXP-{issue}",
            candidate_id=f"C-{issue}-{run_id}-1",
            source_sha=("b" if issue == 76 else "e") * 40,
            manifest_digest=binding["initialization"]["manifest_digest"],
            artifact_digest=artifact,
            policy_digest="sha256:" + "f" * 64,
            workflow_source_sha="1" * 40,
            run_id=run_id,
            run_attempt="1",
            checks=(
                {
                    "name": "project_tests",
                    "status": "PASS",
                    "source": "TRUSTED_OBSERVED",
                },
            ),
            retention={
                "provider": "github-immutable-release",
                "release_tag": f"game-exp-candidate-{issue}-{run_id}-1",
                "release_url": "https://example.test/release",
                "immutable": True,
                "artifact_digest": artifact,
            },
            attestation={
                "provider": "github-artifact-attestations",
                "verified": True,
                "subject_digest": artifact,
                "source_sha": ("b" if issue == 76 else "e") * 40,
            },
            evaluation=evaluation(),
        )
        payload = build_operation_payload(
            "candidate.register",
            {"experiment_id": f"EXP-{issue}"},
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

    def _to_review(self, issue: int):
        payload = build_operation_payload(
            "experiment.decision",
            {
                "experiment_id": f"EXP-{issue}",
                "to_state": "REVIEW",
                "previous_decision_id": None,
                "reason": "ready for human comparison",
            },
        )
        plan = plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id=f"req_review_state_{issue}",
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_actor=self.actor,
        )
        self._apply(plan)

    def _comparison(self, **overrides):
        value = {
            "incumbent_experiment_id": "EXP-76",
            "incumbent_candidate_id": "C-76-100-1",
            "incumbent_artifact_digest": "sha256:" + "c" * 64,
            "profile_digest": PROFILE_DIGEST,
            "blind": True,
            "presentation_order": "CHALLENGER_INCUMBENT",
            "dimensions": [
                {
                    "id": "mechanic_clarity",
                    "choice": "CHALLENGER",
                    "notes": "The consequence was easier to understand.",
                }
            ],
            "overall": "NO_CLEAR_DIFFERENCE",
        }
        value.update(overrides)
        return value

    def _review(self, comparison):
        payload = build_operation_payload(
            "review.record",
            {
                "experiment_id": "EXP-77",
                "candidate_id": "C-77-101-1",
                "outcome": "PASS",
                "notes": "Human approved continuing evaluation.",
                "comparison": comparison,
            },
        )
        return plan_domain_mutation(
            repo_dir=self.root,
            payload=payload,
            request_id="req_human_ab",
            payload_digest=digest_object(payload),
            repository_full_name="owner/repo",
            trusted_actor=self.actor,
        )

    def test_human_ab_binds_current_incumbent_and_shared_profile(self):
        plan = self._review(self._comparison())
        review = plan.writes["experiments/EXP-77/reviews/req_human_ab.json"]
        comparison = review["comparison"]
        self.assertEqual(comparison["evidence_source"], "HUMAN_REPORTED")
        self.assertEqual(comparison["incumbent_experiment_id"], "EXP-76")
        self.assertEqual(comparison["challenger_experiment_id"], "EXP-77")
        self.assertEqual(comparison["profile_digest"], PROFILE_DIGEST)
        self.assertEqual(comparison["overall"], "NO_CLEAR_DIFFERENCE")

    def test_human_ab_rejects_mismatched_profile_digest(self):
        with self.assertRaises(DomainError) as ctx:
            self._review(
                self._comparison(profile_digest="sha256:" + "0" * 64)
            )
        self.assertEqual(ctx.exception.code, "DOMAIN_REVIEW_CONFLICT")


if __name__ == "__main__":
    unittest.main()
