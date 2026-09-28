from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

from trust_policy import ruleset_templates, validate_rulesets  # noqa: E402


class TrustPolicyTests(unittest.TestCase):
    def test_immutable_rules_never_grant_deploy_key_bypass(self):
        rows = {row["name"]: row for row in ruleset_templates("single-principal")}
        for name in (
            "game-exp ledger immutable",
            "game-exp experiment immutable",
            "game-exp immutable refs immutable",
        ):
            self.assertEqual(rows[name]["bypass_actors"], [])

    def test_multi_principal_main_requires_review_and_last_push_approval(self):
        rows = {row["name"]: row for row in ruleset_templates("multi-principal")}
        pr = next(
            rule
            for rule in rows["game-exp protected main"]["rules"]
            if rule["type"] == "pull_request"
        )
        self.assertEqual(pr["parameters"]["required_approving_review_count"], 1)
        self.assertTrue(pr["parameters"]["require_last_push_approval"])

    def test_semantic_validator_rejects_weakened_ruleset(self):
        rows = {row["name"]: row for row in ruleset_templates("single-principal")}
        weakened = {name: dict(value) for name, value in rows.items()}
        weakened["game-exp ledger immutable"] = {
            **weakened["game-exp ledger immutable"],
            "bypass_actors": [
                {
                    "actor_id": None,
                    "actor_type": "DeployKey",
                    "bypass_mode": "always",
                }
            ],
        }
        result = validate_rulesets(weakened)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("game-exp ledger immutable", result["mismatched"])


if __name__ == "__main__":
    unittest.main()
