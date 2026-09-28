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


def _rule_map(value: dict[str, Any]) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for raw in value.get("rules") or []:
        if isinstance(raw, dict) and isinstance(raw.get("type"), str):
            result[raw["type"]] = raw
    return result


def ruleset_satisfies(actual: dict[str, Any], minimum: dict[str, Any]) -> bool:
    actual_semantics = ruleset_semantics(actual)
    minimum_semantics = ruleset_semantics(minimum)
    for key in ("name", "target", "enforcement", "conditions"):
        if actual_semantics.get(key) != minimum_semantics.get(key):
            return False

    # Bypass authority must match exactly. Extra bypass actors weaken trust.
    if actual_semantics.get("bypass_actors") != minimum_semantics.get("bypass_actors"):
        return False

    actual_rules = _rule_map(actual_semantics)
    minimum_rules = _rule_map(minimum_semantics)
    for rule_type, expected in minimum_rules.items():
        current = actual_rules.get(rule_type)
        if not isinstance(current, dict):
            return False
        expected_parameters = expected.get("parameters")
        if rule_type == "update":
            current_parameters = current.get("parameters") or {}
            if current_parameters.get("update_allows_fetch_and_merge", False) is not False:
                return False
            continue
        if rule_type == "pull_request":
            current_parameters = current.get("parameters") or {}
            expected_parameters = expected_parameters or {}
            current_count = current_parameters.get("required_approving_review_count", 0)
            expected_count = expected_parameters.get("required_approving_review_count", 0)
            if not isinstance(current_count, int) or current_count < expected_count:
                return False
            for key, expected_value in expected_parameters.items():
                if key in {"required_approving_review_count", "required_reviewers", "allowed_merge_methods"}:
                    continue
                if expected_value is True and current_parameters.get(key) is not True:
                    return False
            expected_methods = set(expected_parameters.get("allowed_merge_methods") or [])
            current_methods = set(current_parameters.get("allowed_merge_methods") or [])
            if not current_methods or not current_methods.issubset(expected_methods):
                return False
            continue
        if expected_parameters is not None and current.get("parameters") != expected_parameters:
            return False
    return True


def strengthen_ruleset(actual: dict[str, Any], minimum: dict[str, Any]) -> dict[str, Any]:
    # Preserve additional restrictive rules and stronger review settings while
    # correcting any weak minimum required by game-exp.
    value = {
        key: minimum[key]
        for key in ("name", "target", "enforcement", "conditions", "bypass_actors")
    }

    current_rules = [
        dict(row)
        for row in (actual.get("rules") or [])
        if isinstance(row, dict) and isinstance(row.get("type"), str)
    ]
    by_type = {row["type"]: row for row in current_rules}
    for expected in minimum.get("rules") or []:
        if not isinstance(expected, dict) or not isinstance(expected.get("type"), str):
            continue
        rule_type = expected["type"]
        current = by_type.get(rule_type)
        if current is None:
            current_rules.append(dict(expected))
            by_type[rule_type] = current_rules[-1]
            continue
        if rule_type == "update":
            parameters = dict(current.get("parameters") or {})
            parameters["update_allows_fetch_and_merge"] = False
            current["parameters"] = parameters
        elif rule_type == "pull_request":
            current_parameters = dict(current.get("parameters") or {})
            expected_parameters = dict(expected.get("parameters") or {})
            current_parameters["required_approving_review_count"] = max(
                int(current_parameters.get("required_approving_review_count") or 0),
                int(expected_parameters.get("required_approving_review_count") or 0),
            )
            for key, expected_value in expected_parameters.items():
                if key in {"required_approving_review_count", "required_reviewers", "allowed_merge_methods"}:
                    continue
                if expected_value is True:
                    current_parameters[key] = True
                else:
                    current_parameters.setdefault(key, expected_value)
            expected_methods = list(expected_parameters.get("allowed_merge_methods") or [])
            current_methods = list(current_parameters.get("allowed_merge_methods") or [])
            if current_methods:
                allowed = [method for method in current_methods if method in expected_methods]
                current_parameters["allowed_merge_methods"] = allowed or expected_methods
            else:
                current_parameters["allowed_merge_methods"] = expected_methods
            current_parameters.setdefault(
                "required_reviewers",
                expected_parameters.get("required_reviewers", []),
            )
            current["parameters"] = current_parameters
    value["rules"] = current_rules
    return value


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
    *,
    expected_mode: str | None = None,
) -> dict[str, Any]:
    mode = expected_mode or infer_trust_mode_from_rulesets(full_rulesets)
    if mode not in TRUST_MODES:
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
        for name, minimum in expected.items()
        if name in full_rulesets
        and not ruleset_satisfies(full_rulesets[name], minimum)
    )
    return {
        "status": "PASS" if not missing and not mismatched else "FAIL",
        "code": "RULESETS_MATCH" if not missing and not mismatched else "RULESETS_MISMATCH",
        "trust_mode": mode,
        "expected_mode_source": "independent" if expected_mode is not None else "ruleset",
        "missing": missing,
        "mismatched": mismatched,
    }
