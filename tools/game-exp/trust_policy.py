from __future__ import annotations

from typing import Any

WRITER_KEY_TITLE = "game-exp trusted writer"
WRITER_SECRET = "GAME_EXP_WRITER_KEY"
WRITER_ENVIRONMENT = "game-exp-trusted-writer"
TRUST_MODES = {"single-principal", "multi-principal"}

LEGACY_RULESET_NAMES = {
    "game-exp ledger",
    "game-exp experiment branches",
    "game-exp immutable refs",
}

RULESET_NAMES = (
    "game-exp ledger immutable",
    "game-exp ledger writer",
    "game-exp experiment immutable",
    "game-exp experiment lifecycle",
    "game-exp immutable refs immutable",
    "game-exp immutable refs creation",
    "game-exp protected main",
)


def _deploy_key_bypass() -> list[dict[str, Any]]:
    return [
        {"actor_id": None, "actor_type": "DeployKey", "bypass_mode": "always"}
    ]


def ruleset_templates(trust_mode: str) -> tuple[dict[str, Any], ...]:
    if trust_mode not in TRUST_MODES:
        raise ValueError(f"unsupported trust mode: {trust_mode}")
    review_count = 1 if trust_mode == "multi-principal" else 0
    require_last_push_approval = trust_mode == "multi-principal"
    return (
        {
            "name": "game-exp ledger immutable",
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {
                "ref_name": {
                    "exclude": [],
                    "include": ["refs/heads/game-exp/ledger"],
                }
            },
            "rules": [
                {"type": "deletion"},
                {"type": "non_fast_forward"},
            ],
        },
        {
            "name": "game-exp ledger writer",
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": _deploy_key_bypass(),
            "conditions": {
                "ref_name": {
                    "exclude": [],
                    "include": ["refs/heads/game-exp/ledger"],
                }
            },
            "rules": [
                {"type": "update", "parameters": {"update_allows_fetch_and_merge": False}},
                {"type": "creation"},
            ],
        },
        {
            "name": "game-exp experiment immutable",
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {
                "ref_name": {
                    "exclude": [],
                    "include": ["refs/heads/exp/*"],
                }
            },
            "rules": [{"type": "non_fast_forward"}],
        },
        {
            "name": "game-exp experiment lifecycle",
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": _deploy_key_bypass(),
            "conditions": {
                "ref_name": {
                    "exclude": [],
                    "include": ["refs/heads/exp/*"],
                }
            },
            "rules": [
                {"type": "creation"},
                {"type": "deletion"},
            ],
        },
        {
            "name": "game-exp immutable refs immutable",
            "target": "tag",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {
                "ref_name": {
                    "exclude": [],
                    "include": [
                        "refs/tags/exp-base/*",
                        "refs/tags/exp-final/*",
                        "refs/tags/exp-candidate/**/*",
                        "refs/tags/exp-rehearsal/**/*",
                    ],
                }
            },
            "rules": [
                {"type": "update", "parameters": {"update_allows_fetch_and_merge": False}},
                {"type": "deletion"},
                {"type": "non_fast_forward"},
            ],
        },
        {
            "name": "game-exp immutable refs creation",
            "target": "tag",
            "enforcement": "active",
            "bypass_actors": _deploy_key_bypass(),
            "conditions": {
                "ref_name": {
                    "exclude": [],
                    "include": [
                        "refs/tags/exp-base/*",
                        "refs/tags/exp-final/*",
                        "refs/tags/exp-candidate/**/*",
                        "refs/tags/exp-rehearsal/**/*",
                    ],
                }
            },
            "rules": [{"type": "creation"}],
        },
        {
            "name": "game-exp protected main",
            "target": "branch",
            "enforcement": "active",
            "bypass_actors": [],
            "conditions": {
                "ref_name": {
                    "exclude": [],
                    "include": ["refs/heads/main"],
                }
            },
            "rules": [
                {
                    "type": "pull_request",
                    "parameters": {
                        "required_approving_review_count": review_count,
                        "dismiss_stale_reviews_on_push": False,
                        "required_reviewers": [],
                        "require_code_owner_review": False,
                        "require_last_push_approval": require_last_push_approval,
                        "required_review_thread_resolution": False,
                        "require_extra_approval_for_unattributed_changes": True,
                        "allowed_merge_methods": ["merge", "squash", "rebase"],
                    },
                },
                {"type": "deletion"},
                {"type": "non_fast_forward"},
            ],
        },
    )


def ruleset_semantics(value: dict[str, Any]) -> dict[str, Any]:
    rules: list[Any] = []
    for raw_rule in value.get("rules") or []:
        if not isinstance(raw_rule, dict):
            rules.append(raw_rule)
            continue
        rule = dict(raw_rule)
        if rule.get("type") == "update":
            parameters = dict(rule.get("parameters") or {})
            parameters.setdefault("update_allows_fetch_and_merge", False)
            rule["parameters"] = parameters
        if rule.get("type") == "pull_request":
            parameters = dict(rule.get("parameters") or {})
            parameters.setdefault("required_reviewers", [])
            parameters.setdefault("require_code_owner_review", False)
            parameters.setdefault("dismiss_stale_reviews_on_push", False)
            parameters.setdefault("require_last_push_approval", False)
            parameters.setdefault("required_review_thread_resolution", False)
            parameters.setdefault("require_extra_approval_for_unattributed_changes", True)
            parameters.setdefault("allowed_merge_methods", ["merge", "squash", "rebase"])
            rule["parameters"] = parameters
        rules.append(rule)

    return {
        "name": value.get("name"),
        "target": value.get("target"),
        "enforcement": value.get("enforcement"),
        "bypass_actors": value.get("bypass_actors") or [],
        "conditions": value.get("conditions"),
        "rules": rules,
    }


def infer_trust_mode_from_rulesets(full_rulesets: dict[str, dict[str, Any]]) -> str | None:
    row = full_rulesets.get("game-exp protected main")
    if not isinstance(row, dict):
        return None
    for rule in row.get("rules") or []:
        if isinstance(rule, dict) and rule.get("type") == "pull_request":
            parameters = rule.get("parameters") or {}
            count = parameters.get("required_approving_review_count")
            last_push = parameters.get("require_last_push_approval")
            if isinstance(count, int) and count >= 1 and last_push is True:
                return "multi-principal"
            if count == 0:
                return "single-principal"
    return None


def validate_rulesets(
    full_rulesets: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    mode = infer_trust_mode_from_rulesets(full_rulesets)
    if mode is None:
        return {
            "status": "FAIL",
            "code": "TRUST_MODE_UNRESOLVED",
            "trust_mode": None,
            "missing": [],
            "mismatched": ["game-exp protected main"],
        }
    expected = {row["name"]: row for row in ruleset_templates(mode)}
    missing = sorted(set(expected) - set(full_rulesets))
    mismatched = sorted(
        name
        for name, template in expected.items()
        if name in full_rulesets
        and ruleset_semantics(full_rulesets[name]) != ruleset_semantics(template)
    )
    return {
        "status": "PASS" if not missing and not mismatched else "FAIL",
        "code": "RULESETS_MATCH" if not missing and not mismatched else "RULESETS_MISMATCH",
        "trust_mode": mode,
        "missing": missing,
        "mismatched": mismatched,
    }
