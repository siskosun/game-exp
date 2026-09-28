from __future__ import annotations

import argparse
import base64
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

from protocol_core import digest_object


class ExecutionGuardError(RuntimeError):
    pass


SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def _token() -> str:
    token = os.environ.get("GAME_EXP_GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if not token:
        raise ExecutionGuardError("GAME_EXP_GITHUB_TOKEN or GH_TOKEN is required")
    return token


def github_json(repo: str, suffix: str) -> Any:
    request = urllib.request.Request(
        f"https://api.github.com/repos/{repo}{suffix}",
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {_token()}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "game-exp-execution-guard",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[-1000:]
        raise ExecutionGuardError(
            f"GitHub API failed ({exc.code}) for {suffix}: {body}"
        ) from exc


def github_content_json(repo: str, path: str, ref: str) -> dict[str, Any]:
    suffix = (
        "/contents/"
        + "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
        + "?ref="
        + urllib.parse.quote(ref, safe="")
    )
    value = github_json(repo, suffix)
    if not isinstance(value, dict):
        raise ExecutionGuardError(f"GitHub content response is invalid for {path}@{ref}")
    encoded = value.get("content")
    if value.get("encoding") != "base64" or not isinstance(encoded, str):
        raise ExecutionGuardError(f"GitHub content is not base64 JSON: {path}@{ref}")
    try:
        decoded = base64.b64decode(encoded).decode("utf-8")
        obj = json.loads(decoded)
    except Exception as exc:
        raise ExecutionGuardError(f"invalid JSON for {path}@{ref}: {exc}") from exc
    if not isinstance(obj, dict):
        raise ExecutionGuardError(f"{path}@{ref} must be an object")
    return obj


def ref_sha(repo: str, ref_path: str) -> str:
    value = github_json(repo, "/git/ref/" + ref_path)
    obj = value.get("object") if isinstance(value, dict) else None
    sha = obj.get("sha") if isinstance(obj, dict) else None
    if not isinstance(sha, str) or not SHA_RE.fullmatch(sha):
        raise ExecutionGuardError(f"ref {ref_path!r} does not resolve to a commit SHA")
    return sha


def evaluate(
    *,
    repo: str,
    action: str,
    experiment_id: str,
    request_id: str,
) -> dict[str, Any]:
    operation = github_content_json(
        repo,
        f"operations/{request_id}.json",
        "game-exp/ledger",
    )
    payload = operation.get("payload")
    if (
        not isinstance(payload, dict)
        or payload.get("kind") != "operation_request"
        or payload.get("operation") != "execution.claim"
    ):
        raise ExecutionGuardError("request is not a protected execution.claim")
    if operation.get("domain_status") != "REQUEST_ONLY":
        raise ExecutionGuardError("execution claim was not committed as REQUEST_ONLY")

    value = payload.get("input")
    pre = payload.get("preconditions")
    if not isinstance(value, dict) or not isinstance(pre, dict):
        raise ExecutionGuardError("execution claim input/preconditions are invalid")
    if value.get("experiment_id") != experiment_id or value.get("action") != action:
        raise ExecutionGuardError("execution claim identity differs from worker request")
    if pre.get("protocol_version") != 2:
        raise ExecutionGuardError("execution claim requires collaboration protocol v2")

    state = github_content_json(
        repo,
        f"experiments/{experiment_id}/state.json",
        "game-exp/ledger",
    )
    actual_state_digest = digest_object(state)
    if pre.get("experiment_state_digest") != actual_state_digest:
        raise ExecutionGuardError(
            "execution claim is stale: experiment state changed after claim"
        )

    binding = github_content_json(
        repo,
        f"experiments/{experiment_id}/binding.json",
        "game-exp/ledger",
    )
    initialization = binding.get("initialization")
    if not isinstance(initialization, dict):
        raise ExecutionGuardError("binding initialization is unavailable")

    manifest_digest = pre.get("manifest_digest")
    if manifest_digest is not None and manifest_digest != initialization.get("manifest_digest"):
        raise ExecutionGuardError("execution claim is stale: manifest binding changed")

    source_sha = pre.get("source_sha")
    if source_sha is not None:
        branch_ref = initialization.get("branch_ref")
        if not isinstance(branch_ref, str) or not branch_ref.startswith("refs/heads/"):
            raise ExecutionGuardError("canonical experiment branch is unavailable")
        actual_source = ref_sha(repo, branch_ref.removeprefix("refs/"))
        if source_sha != actual_source:
            raise ExecutionGuardError(
                f"execution claim is stale: source advanced expected={source_sha} actual={actual_source}"
            )

    candidate_id = pre.get("candidate_id")
    candidate_source_sha = pre.get("candidate_source_sha")
    if candidate_id is not None:
        if candidate_id != state.get("current_candidate_id"):
            raise ExecutionGuardError("execution claim is stale: current Candidate changed")
        candidate = github_content_json(
            repo,
            f"experiments/{experiment_id}/candidates/{candidate_id}.json",
            "game-exp/ledger",
        )
        if candidate_source_sha is not None and candidate.get("source_sha") != candidate_source_sha:
            raise ExecutionGuardError("execution claim is stale: Candidate source changed")

    rehearsal_id = pre.get("rehearsal_id")
    if rehearsal_id is not None and rehearsal_id != state.get("current_rehearsal_id"):
        raise ExecutionGuardError("execution claim is stale: current Rehearsal changed")

    main_sha = pre.get("main_sha")
    if main_sha is not None:
        actual_main = ref_sha(repo, "heads/main")
        if main_sha != actual_main:
            raise ExecutionGuardError(
                f"execution claim is stale: main advanced expected={main_sha} actual={actual_main}"
            )

    return {
        "status": "PASS",
        "request_id": request_id,
        "experiment_id": experiment_id,
        "action": action,
        "as_of": {
            "ledger_commit": ref_sha(repo, "heads/game-exp/ledger"),
            "read": "LIVE",
        },
        "preconditions": pre,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--experiment-id", required=True)
    parser.add_argument("--request-id", required=True)
    parser.add_argument("--github-output")
    args = parser.parse_args()

    result = evaluate(
        repo=args.repo,
        action=args.action,
        experiment_id=args.experiment_id,
        request_id=args.request_id,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    if args.github_output:
        pre = result["preconditions"]
        with open(args.github_output, "a", encoding="utf-8") as out:
            for key in (
                "source_sha",
                "candidate_id",
                "candidate_source_sha",
                "rehearsal_id",
                "main_sha",
                "manifest_digest",
            ):
                value = pre.get(key)
                if value is not None:
                    out.write(f"{key}={value}\n")
            out.write(
                "experiment_state_digest="
                + str(pre.get("experiment_state_digest") or "")
                + "\n"
            )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(
            json.dumps(
                {"status": "EXECUTION_PRECONDITION_FAILED", "error": str(exc)},
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        raise SystemExit(41)
