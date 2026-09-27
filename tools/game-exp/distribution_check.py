from __future__ import annotations

import argparse
import json
import pathlib
import sys
from dataclasses import dataclass
from typing import Any

HERE = pathlib.Path(__file__).resolve()
TOOLS_DIR = HERE.parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(TOOLS_DIR))

from bootstrap import _managed_paths  # noqa: E402
from install_harnesses import CANONICAL_SOURCE, SUPPORTED_HARNESSES  # noqa: E402


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: Any = None

    def as_dict(self) -> dict[str, Any]:
        row = {"name": self.name, "status": self.status}
        if self.detail not in (None, "", [], {}):
            row["detail"] = self.detail
        return row


def _read_json(path: pathlib.Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def _command_matches(command: Any, harness: str, *, check: bool) -> bool:
    if not isinstance(command, list) or not all(isinstance(x, str) for x in command):
        return False
    expected = [
        "python",
        "tools/game-exp/install_harnesses.py",
        "--harness",
        harness,
    ]
    if check:
        expected.append("--check")
    expected.append("--json")
    return command == expected


def run_checks(root: pathlib.Path = ROOT) -> dict[str, Any]:
    root = root.resolve()
    checks: list[Check] = []

    def add(name: str, ok: bool, detail: Any = None) -> None:
        checks.append(Check(name, "PASS" if ok else "FAIL", detail))

    try:
        version = (root / "VERSION.txt").read_text(encoding="utf-8").strip()
    except Exception as exc:
        version = ""
        add("version_marker", False, str(exc))
    else:
        add("version_marker", bool(version), version)

    try:
        plugin = _read_json(root / "plugins/game-exp/plugin.json")
    except Exception as exc:
        plugin = {}
        add("plugin_manifest", False, str(exc))
    else:
        add("plugin_manifest", True)

    try:
        install = _read_json(root / "INSTALL.json")
    except Exception as exc:
        install = {}
        add("install_contract", False, str(exc))
    else:
        add("install_contract", True)

    versions = {
        "VERSION.txt": version,
        "plugin.json": plugin.get("version"),
        "INSTALL.json": install.get("version"),
    }
    add(
        "version_alignment",
        bool(version) and len(set(versions.values())) == 1,
        versions,
    )

    source_values = {
        "installer": CANONICAL_SOURCE,
        "plugin": plugin.get("repository"),
        "install": install.get("source_of_truth"),
    }
    add(
        "canonical_source_alignment",
        len(set(source_values.values())) == 1
        and CANONICAL_SOURCE == "https://github.com/siskosun/game-exp",
        source_values,
    )

    policy = install.get("policy") if isinstance(install.get("policy"), dict) else {}
    add(
        "isolated_update_policy",
        policy.get("default_update_scope") == "current_harness_only"
        and policy.get("updates_other_harnesses") is False
        and policy.get("updates_consumer_repositories") is False
        and policy.get("use_all_only_with_explicit_user_request") is True
        and policy.get("repository_binding") == "dynamic",
        policy,
    )

    harnesses = install.get("harnesses")
    harnesses = harnesses if isinstance(harnesses, dict) else {}
    add(
        "harness_set_alignment",
        set(harnesses) == set(SUPPORTED_HARNESSES),
        {
            "installer": list(SUPPORTED_HARNESSES),
            "install_contract": sorted(harnesses),
        },
    )

    command_errors = []
    for harness in SUPPORTED_HARNESSES:
        row = harnesses.get(harness)
        if not isinstance(row, dict):
            command_errors.append(f"{harness}: missing config")
            continue
        if not _command_matches(row.get("install_or_upgrade"), harness, check=False):
            command_errors.append(f"{harness}: invalid install_or_upgrade")
        if not _command_matches(row.get("check"), harness, check=True):
            command_errors.append(f"{harness}: invalid check")
        expected_runtime = f"~/.game-exp/runtimes/{harness}"
        if row.get("runtime") != expected_runtime:
            command_errors.append(f"{harness}: runtime is not isolated")
    add("harness_commands", not command_errors, command_errors)

    all_cmd = install.get("explicit_all")
    all_check = install.get("explicit_all_check")
    add(
        "explicit_all_only",
        _command_matches(all_cmd, "all", check=False)
        and _command_matches(all_check, "all", check=True),
        {"install": all_cmd, "check": all_check},
    )

    add(
        "distribution_check_command",
        install.get("distribution_check")
        == ["python", "tools/game-exp/distribution_check.py", "--json"],
        install.get("distribution_check"),
    )

    legacy = install.get("legacy_shared_install")
    legacy = legacy if isinstance(legacy, dict) else {}
    add(
        "legacy_migration_policy",
        legacy.get("single_harness_behavior") == "detect_and_preserve"
        and legacy.get("cleanup_requires_explicit_all") is True,
        legacy,
    )

    missing_managed = [
        rel for rel in _managed_paths() if not (root / rel).is_file()
    ]
    add("managed_source_complete", not missing_managed, missing_managed)

    forbidden_repo_config = root / ".codex" / "config.toml"
    add(
        "no_distribution_repo_binding",
        not forbidden_repo_config.exists(),
        str(forbidden_repo_config) if forbidden_repo_config.exists() else None,
    )

    skill = root / "plugins/game-exp/skills/game-exp/SKILL.md"
    skill_text = skill.read_text(encoding="utf-8") if skill.is_file() else ""
    add(
        "skill_distribution_contract",
        CANONICAL_SOURCE in skill_text
        and "INSTALL.json" in skill_text
        and "Do not synchronize application repositories" in skill_text
        and "--cleanup-legacy-shared" in skill_text,
    )

    status = "PASS" if all(row.status == "PASS" for row in checks) else "FAIL"
    return {
        "status": status,
        "source": CANONICAL_SOURCE,
        "version": version or None,
        "check_count": len(checks),
        "checks": [row.as_dict() for row in checks],
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify standalone game-exp distribution invariants"
    )
    parser.add_argument("--root", default=str(ROOT))
    parser.add_argument("--json", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    try:
        result = run_checks(pathlib.Path(args.root))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = {"status": "FAIL", "error": str(exc)}

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"{result.get('status')}\tgame-exp distribution")
        for check in result.get("checks", []):
            detail = check.get("detail")
            suffix = "" if detail in (None, "", [], {}) else f" — {detail}"
            print(f"{check['status']:4}\t{check['name']}{suffix}")
    return 0 if result.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
