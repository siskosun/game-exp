from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve()
sys.path.insert(0, str(HERE.parents[1]))

from trust_policy import (  # noqa: E402
    ruleset_templates,
    strengthen_ruleset,
    validate_rulesets,
)


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

    def test_semantic_validator_accepts_stronger_main_protection(self):
        rows = {row["name"]: row for row in ruleset_templates("multi-principal")}
        main = rows["game-exp protected main"]
        rules = [dict(rule) for rule in main["rules"]]
        pr = next(rule for rule in rules if rule["type"] == "pull_request")
        pr["parameters"] = {
            **pr["parameters"],
            "required_approving_review_count": 2,
            "require_code_owner_review": True,
            "required_review_thread_resolution": True,
            "allowed_merge_methods": ["squash"],
        }
        rows["game-exp protected main"] = {**main, "rules": rules}
        result = validate_rulesets(rows, expected_mode="multi-principal")
        self.assertEqual(result["status"], "PASS")

    def test_strengthen_ruleset_preserves_stricter_review_settings(self):
        minimum = {
            row["name"]: row
            for row in ruleset_templates("multi-principal")
        }["game-exp protected main"]
        actual = {
            **minimum,
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {
                        **next(
                            rule["parameters"]
                            for rule in minimum["rules"]
                            if rule["type"] == "pull_request"
                        ),
                        "required_approving_review_count": 3,
                        "require_code_owner_review": True,
                        "allowed_merge_methods": ["squash"],
                    },
                },
                {"type": "deletion"},
                {"type": "non_fast_forward"},
                {"type": "required_signatures"},
            ],
        }
        repaired = strengthen_ruleset(actual, minimum)
        pr = next(rule for rule in repaired["rules"] if rule["type"] == "pull_request")
        self.assertEqual(pr["parameters"]["required_approving_review_count"], 3)
        self.assertTrue(pr["parameters"]["require_code_owner_review"])
        self.assertEqual(pr["parameters"]["allowed_merge_methods"], ["squash"])
        self.assertIn(
            "required_signatures",
            {rule["type"] for rule in repaired["rules"]},
        )

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
