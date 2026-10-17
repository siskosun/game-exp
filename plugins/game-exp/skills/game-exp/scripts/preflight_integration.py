#!/usr/bin/env python3
"""Read-only advisory before Bind: ancestry, Manifest scope and PR permissions.

This is not a Trusted Writer, Doctor or Rehearsal. Missing evidence remains
UNVERIFIED. Example:

python scripts/preflight_integration.py --manifest m.json --snapshot facts.json --strict
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

SHA_RE = re.compile(r"^[0-9a-fA-F]{40}$")


def git_glob_match(path: str, pattern: str) -> bool:
    """Scope glob: ** crosses components; * and ? do not."""
    path, pattern = path.strip("/"), pattern.strip("/")
    if not path or not pattern:
        return False
    parts = ["^"]
    i = 0
    while i < len(pattern):
        c = pattern[i]
        if c == "*":
            if i + 1 < len(pattern) and pattern[i + 1] == "*":
                i += 2
                if i < len(pattern) and pattern[i] == "/":
                    parts.append("(?:.*/)?")
                    i += 1
                else:
                    parts.append(".*")
                continue
            parts.append("[^/]*")
        elif c == "?":
            parts.append("[^/]")
        else:
            parts.append(re.escape(c))
        i += 1
    return re.fullmatch("".join(parts)[1:-1], path) is not None


def git_is_ancestor(repo: Path, base: str, head: str) -> bool | None:
    if not SHA_RE.fullmatch(base) or not SHA_RE.fullmatch(head):
        return None
    for sha in (base, head):
        p = subprocess.run(["git", "-C", str(repo), "cat-file", "-e",
                            f"{sha}^{{commit}}"], capture_output=True, check=False)
        if p.returncode:
            return None
    p = subprocess.run(["git", "-C", str(repo), "merge-base", "--is-ancestor",
                        base, head], capture_output=True, check=False)
    return {0: True, 1: False}.get(p.returncode)


def assess(manifest: dict[str, Any], snapshot: dict[str, Any] | None = None,
           repo: Path | None = None) -> dict[str, Any]:
    """Check only pinned supplied facts. Never fetch or mutate protected data."""
    snapshot = snapshot or {}
    if not isinstance(manifest, dict) or not isinstance(snapshot, dict):
        raise ValueError("manifest and snapshot must be objects")
    parent, scope, experiment = (manifest.get(x) for x in ("parent", "scope", "experiment"))
    if not isinstance(parent, dict) or not isinstance(scope, dict) or not isinstance(experiment, dict):
        raise ValueError("manifest requires parent, scope, experiment objects")
    allowed, avoid = scope.get("allowed"), scope.get("avoid")
    if not isinstance(allowed, list) or not isinstance(avoid, list) or any(
        not isinstance(x, str) or not x for x in allowed + avoid
    ):
        raise ValueError("scope.allowed/avoid must be nonempty string arrays")
    issue = experiment.get("issue_number")
    if isinstance(issue, bool) or not str(issue).isdigit():
        raise ValueError("numeric experiment.issue_number required")
    experiment_id = f"EXP-{int(issue)}"
    meta = snapshot.get("metadata_path", f"experiments/{experiment_id}/manifest.yaml")
    if not isinstance(meta, str) or not meta:
        raise ValueError("metadata_path must be a string")
    base, main = parent.get("commit"), snapshot.get("main_sha")
    if base is not None and not isinstance(base, str):
        raise ValueError("parent.commit must be a Git SHA")
    if main is not None and not isinstance(main, str):
        raise ValueError("snapshot.main_sha must be a Git SHA")
    findings: list[dict[str, Any]] = []

    def add(code: str, severity: str, detail: Any) -> None:
        findings.append({"code": code, "severity": severity, "evidence": detail})

    for patterns, code, severity in (
        (avoid, "SELF_BLOCKING_METADATA", "BLOCKER"),
        (allowed, "METADATA_IN_SOURCE_ALLOWLIST", "WARNING"),
    ):
        matches = [x for x in patterns if git_glob_match(meta, x)]
        if matches:
            add(code, severity, {"metadata_path": meta, "patterns": matches})
    if not base or not SHA_RE.fullmatch(base):
        add("INVALID_BASE_SHA", "BLOCKER", base)
    if main is not None and not SHA_RE.fullmatch(main):
        add("INVALID_MAIN_SHA", "BLOCKER", main)

    claimed = snapshot.get("parent_is_ancestor_of_main")
    if claimed is not None and type(claimed) is not bool:
        raise ValueError("parent_is_ancestor_of_main must be boolean/null")
    observed = (True if base and main and base == main and SHA_RE.fullmatch(base)
                else git_is_ancestor(repo, base, main)
                if repo is not None and base and main else None)
    if claimed is not None and observed is not None and claimed != observed:
        add("ANCESTRY_EVIDENCE_CONFLICT", "BLOCKER", {"claimed": claimed, "verified": observed})
    ancestry = observed if observed is not None else claimed
    if ancestry is False:
        add("PARENT_NOT_IN_MAIN", "BLOCKER",
            {"base": base, "main": main, "parent_experiment": parent.get("experiment")})
    elif ancestry is None:
        add("ANCESTRY_UNVERIFIED", "UNVERIFIED", {"base": base, "main": main})

    if parent.get("experiment"):
        lifecycle = snapshot.get("parent_experiment_lifecycle")
        if lifecycle is None:
            add("PARENT_LIFECYCLE_UNKNOWN", "UNVERIFIED", parent["experiment"])
        elif lifecycle not in ("INTEGRATED", "ARCHIVED"):
            add("UNINTEGRATED_PARENT", "WARNING",
                {"id": parent["experiment"], "lifecycle": lifecycle})

    caps = snapshot.get("pr_capabilities", {})
    if not isinstance(caps, dict):
        raise ValueError("pr_capabilities must be an object")
    actions, connector = (caps.get(k) for k in
                          ("actions_can_create_pr", "authorized_connector_can_create_pr"))
    if type(actions) not in (bool, type(None)) or type(connector) not in (bool, type(None)):
        raise ValueError("PR capabilities must be booleans or null")
    if actions is False and connector is True:
        add("PR_CREATION_FALLBACK", "WARNING",
            "Use an authorized connector for the exact trusted proposal branch, "
            "then rerun failed job for the SAME workflow run and verify it.")
    elif actions is False:
        add("PR_CREATION_BLOCKED", "BLOCKER" if connector is False else "UNVERIFIED", caps)
    elif actions is None:
        add("PR_PERMISSION_UNVERIFIED", "UNVERIFIED", caps)

    verdict = ("BLOCKED" if any(x["severity"] == "BLOCKER" for x in findings)
               else "UNVERIFIED" if any(x["severity"] == "UNVERIFIED" for x in findings)
               else "READY_WITH_WARNINGS" if findings else "READY")
    return {"schema_version": 1, "kind": "game_exp_prebind_advisory",
            "experiment_id": experiment_id, "base_sha": base, "main_sha": main,
            "metadata_path": meta, "ancestry_proved": ancestry, "verdict": verdict,
            "findings": findings, "advisory_only": True,
            "authority": "Protected Ledger and trusted workflows remain authoritative"}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--manifest", required=True, type=Path)
    p.add_argument("--snapshot", type=Path)
    p.add_argument("--repo", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--strict", action="store_true")
    args = p.parse_args()
    try:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
        facts = json.loads(args.snapshot.read_text(encoding="utf-8")) if args.snapshot else {}
        report = assess(manifest, facts, args.repo)
    except (ValueError, OSError) as exc:
        print(f"Invalid input: {exc}", file=sys.stderr)
        return 4
    result = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result, encoding="utf-8")
    else:
        print(result, end="")
    return (2 if args.strict and report["verdict"] == "BLOCKED"
            else 3 if args.strict and report["verdict"] == "UNVERIFIED" else 0)


if __name__ == "__main__":
    raise SystemExit(main())
