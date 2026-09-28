from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import tempfile
import unittest

TOOLS = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))

from evaluation_evidence import (  # noqa: E402
    EvaluationEvidenceError,
    evaluation_profile_digest,
    package_output,
    observe_bundle,
    validate_profile,
    validate_result,
)


def profile():
    return {
        "schema_version": 1,
        "profile_id": "squad-choice-v1",
        "standing_requirements": [
            {
                "id": "launch",
                "goal": "The prototype launches and accepts normal input.",
                "required": True,
            },
            {
                "id": "retry",
                "goal": "The player can recover after failure.",
                "required": True,
            },
        ],
        "hypothesis_requirements": [
            {
                "id": "choice_changes_battle",
                "goal": "A player can form a three-person squad and the choice changes battle behavior.",
                "required": True,
            }
        ],
        "interface": {
            "scenario_id": "cold-start-squad",
            "player_goal": "Form a three-person squad and enter the first battle within 60 seconds.",
            "seed_policy": "DECLARED",
            "replay_policy": "REQUIRED",
            "snapshot_policy": "REQUIRED",
        },
    }


def digest_file(path: pathlib.Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def result(profile_digest: str, source_sha: str, status="PASS", classification="NONE"):
    return {
        "schema_version": 1,
        "profile_digest": profile_digest,
        "source_sha": source_sha,
        "run_mode": "TRUSTED_REPLAY",
        "trace_digest": "sha256:" + "7" * 64,
        "step_mode": "SCENE_CONTROLLED",
        "requirements": [
            {
                "id": "launch",
                "status": "PASS",
                "classification": "NONE",
                "evidence": [],
            },
            {
                "id": "retry",
                "status": "PASS",
                "classification": "NONE",
                "evidence": [],
            },
            {
                "id": "choice_changes_battle",
                "status": status,
                "classification": classification,
                "evidence": [],
            },
        ],
    }


class EvaluationEvidenceTests(unittest.TestCase):
    def test_profile_digest_is_stable_and_goal_based(self):
        value = validate_profile(profile())
        first = evaluation_profile_digest(value)
        second = evaluation_profile_digest(json.loads(json.dumps(value)))
        self.assertEqual(first, second)
        self.assertRegex(first, r"^sha256:[0-9a-f]{64}$")
        self.assertIn("player_goal", value["interface"])
        self.assertNotIn("controls", value["interface"])

    def test_required_product_defect_makes_screening_ineligible(self):
        value = profile()
        digest = evaluation_profile_digest(value)
        with tempfile.TemporaryDirectory() as td:
            summary = validate_result(
                value,
                result(
                    digest,
                    "a" * 40,
                    status="FAIL_PRODUCT_DEFECT",
                    classification="PRODUCT_DEFECT",
                ),
                source_sha="a" * 40,
                evidence_root=pathlib.Path(td),
            )
        self.assertEqual(summary["screening"], "INELIGIBLE")
        self.assertEqual(summary["source"], "TRUSTED_OBSERVED")

    def test_inconclusive_required_evidence_stays_inconclusive(self):
        value = profile()
        digest = evaluation_profile_digest(value)
        with tempfile.TemporaryDirectory() as td:
            summary = validate_result(
                value,
                result(
                    digest,
                    "a" * 40,
                    status="INCONCLUSIVE",
                    classification="TEST_HARNESS",
                ),
                source_sha="a" * 40,
                evidence_root=pathlib.Path(td),
            )
        self.assertEqual(summary["screening"], "INCONCLUSIVE")

    def test_evidence_digest_is_recomputed(self):
        value = profile()
        digest = evaluation_profile_digest(value)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            evidence = root / "run.log"
            evidence.write_text("observed", encoding="utf-8")
            payload = result(digest, "a" * 40)
            payload["requirements"][0]["evidence"] = [
                {"path": "run.log", "digest": digest_file(evidence)}
            ]
            summary = validate_result(
                value,
                payload,
                source_sha="a" * 40,
                evidence_root=root,
            )
            self.assertEqual(summary["screening"], "ELIGIBLE")

            payload["requirements"][0]["evidence"][0]["digest"] = "sha256:" + "0" * 64
            with self.assertRaises(EvaluationEvidenceError):
                validate_result(
                    value,
                    payload,
                    source_sha="a" * 40,
                    evidence_root=root,
                )

    def test_bundle_observation_revalidates_profile_and_result(self):
        value = profile()
        digest = evaluation_profile_digest(value)
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            profile_path = root / "profile.json"
            profile_path.write_text(json.dumps(value), encoding="utf-8")
            output = root / "output"
            output.mkdir()
            (output / "result.json").write_text(
                json.dumps(result(digest, "a" * 40)),
                encoding="utf-8",
            )
            bundle = root / "evaluation-output.tgz"
            package_output(output, bundle)
            summary = observe_bundle(
                profile_path=profile_path,
                bundle_path=bundle,
                source_sha="a" * 40,
                expected_profile_digest=digest,
                work_dir=root / "observe",
            )
            self.assertEqual(summary["screening"], "ELIGIBLE")
            self.assertEqual(summary["bundle_asset_name"], "evaluation-output.tgz")
            self.assertRegex(summary["bundle_digest"], r"^sha256:[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
