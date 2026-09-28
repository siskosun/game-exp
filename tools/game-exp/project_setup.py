from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from client import GameExpClient, GitHubTransport
from trust_policy import (
    LEGACY_RULESET_NAMES,
    RULESET_NAMES,
    TRUST_MODES,
    WRITER_ENVIRONMENT,
    WRITER_KEY_TITLE,
    WRITER_SECRET,
    ruleset_semantics,
    ruleset_satisfies,
    ruleset_templates,
    strengthen_ruleset,
)

API_VERSION = "2022-11-28"


class ProjectSetupError(RuntimeError):
    pass


def _run(
    args: list[str],
    *,
    check: bool = True,
    input_text: str | None = None,
    input_bytes: bytes | None = None,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    if input_text is not None and input_bytes is not None:
        raise ProjectSetupError("provide only one of input_text or input_bytes")
    try:
        if input_bytes is not None:
            raw = subprocess.run(
                args,
                input=input_bytes,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
            proc = subprocess.CompletedProcess(
                raw.args,
                raw.returncode,
                raw.stdout.decode("utf-8", errors="strict"),
                raw.stderr.decode("utf-8", errors="strict"),
            )
        else:
            proc = subprocess.run(
                args,
                input=input_text,
                text=True,
                encoding="utf-8",
                errors="strict",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
            )
    except FileNotFoundError as exc:
        raise ProjectSetupError(f"required command not found: {args[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise ProjectSetupError(f"command timed out: {' '.join(args[:3])}") from exc
    if check and proc.returncode != 0:
        raise ProjectSetupError(
            f"command failed ({proc.returncode}): {' '.join(args)}\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    return proc


def _json(proc: subprocess.CompletedProcess[str]) -> Any:
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise ProjectSetupError(f"invalid JSON from command: {proc.stdout!r}") from exc


def _gh_api(
    repo: str,
    suffix: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    check: bool = True,
    timeout: float = 60.0,
) -> subprocess.CompletedProcess[str]:
    endpoint = f"repos/{repo}"
    if suffix:
        endpoint += f"/{suffix.lstrip('/')}"
    command = [
        "gh",
        "api",
        endpoint,
        "-H",
        "Accept: application/vnd.github+json",
        "-H",
        f"X-GitHub-Api-Version: {API_VERSION}",
    ]
    if method != "GET":
        command[2:2] = ["-X", method]
    if body is None:
        return _run(command, check=check, timeout=timeout)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        delete=False,
        suffix=".json",
    ) as handle:
        json.dump(body, handle, ensure_ascii=False, separators=(",", ":"))
        temp_path = handle.name
    try:
        return _run(
            [*command, "--input", temp_path],
            check=check,
            timeout=timeout,
        )
    finally:
        Path(temp_path).unlink(missing_ok=True)


def _repo_metadata(repo: str) -> dict[str, Any]:
    proc = _gh_api(repo, "")
    value = _json(proc)
    if not isinstance(value, dict):
        raise ProjectSetupError("repository metadata must be an object")
    return value


def _ruleset_probe(repo: str) -> dict[str, Any]:
    proc = _gh_api(repo, "rulesets?per_page=100", check=False)
    if proc.returncode == 0:
        data = _json(proc)
        return {
            "status": "PASS",
            "available": True,
            "rulesets": data if isinstance(data, list) else [],
        }
    text = (proc.stdout + "\n" + proc.stderr).strip()
    lowered = text.lower()
    if "upgrade to github pro" in lowered or "make this repository public" in lowered:
        return {
            "status": "BLOCKED_PLAN",
            "available": False,
            "code": "RULESETS_PLAN_UNSUPPORTED",
            "detail": text[-1600:],
            "resolution_choices": [
                "make_repository_public",
                "upgrade_github_plan",
            ],
        }
    return {
        "status": "FAIL",
        "available": False,
        "code": "RULESETS_UNAVAILABLE",
        "detail": text[-1600:],
    }


def preflight(repo: str) -> dict[str, Any]:
    metadata = _repo_metadata(repo)
    permissions = metadata.get("permissions")
    can_admin = bool(isinstance(permissions, dict) and permissions.get("admin"))
    rulesets = _ruleset_probe(repo)

    workflow = _gh_api(
        repo,
        "contents/.github/workflows/game-exp-trusted-writer.yml?ref=main",
        check=False,
    )
    workflow_present = workflow.returncode == 0

    status = "PASS"
    blockers: list[dict[str, Any]] = []
    if not can_admin:
        status = "BLOCKED_PERMISSION"
        blockers.append(
            {
                "code": "ADMIN_REQUIRED",
                "detail": "project initialization requires repository admin permission",
            }
        )
    if rulesets["status"] != "PASS":
        status = rulesets["status"]
        blockers.append(rulesets)
    if not workflow_present:
        if status == "PASS":
            status = "BLOCKED_SOURCE"
        blockers.append(
            {
                "code": "GAME_EXP_WORKFLOWS_NOT_COMMITTED",
                "detail": (
                    "install/bootstrap game-exp files and commit them to main before "
                    "project-init"
                ),
            }
        )

    return {
        "status": status,
        "repo": repo,
        "repository": {
            "visibility": metadata.get("visibility"),
            "private": metadata.get("private"),
            "default_branch": metadata.get("default_branch"),
            "owner_type": ((metadata.get("owner") or {}).get("type")),
        },
        "admin": can_admin,
        "rulesets": rulesets,
        "workflow_present": workflow_present,
        "blockers": blockers,
        "ready_to_provision": not blockers,
    }


def _ledger_head(repo: str) -> str | None:
    proc = _gh_api(repo, "git/ref/heads/game-exp/ledger", check=False)
    if proc.returncode != 0:
        return None
    value = _json(proc)
    sha = ((value or {}).get("object") or {}).get("sha")
    return sha if isinstance(sha, str) and re.fullmatch(r"[0-9a-f]{40}", sha) else None


def _ensure_ledger(repo: str) -> dict[str, Any]:
    existing = _ledger_head(repo)
    if existing:
        return {"status": "PASS", "changed": False, "ledger_head": existing}

    seed = {
        "kind": "game_exp_ledger",
        "schema_version": 1,
        "initialized_by": "game-exp project-init",
    }
    blob = _json(
        _gh_api(
            repo,
            "git/blobs",
            method="POST",
            body={
                "content": json.dumps(
                    seed,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                + "\n",
                "encoding": "utf-8",
            },
        )
    )
    blob_sha = blob.get("sha")
    if not isinstance(blob_sha, str):
        raise ProjectSetupError("failed to create Ledger seed blob")

    tree = _json(
        _gh_api(
            repo,
            "git/trees",
            method="POST",
            body={
                "tree": [
                    {
                        "path": "ledger.json",
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_sha,
                    }
                ]
            },
        )
    )
    tree_sha = tree.get("sha")
    if not isinstance(tree_sha, str):
        raise ProjectSetupError("failed to create Ledger seed tree")

    commit = _json(
        _gh_api(
            repo,
            "git/commits",
            method="POST",
            body={
                "message": "Initialize game-exp Ledger",
                "tree": tree_sha,
                "parents": [],
            },
        )
    )
    commit_sha = commit.get("sha")
    if not isinstance(commit_sha, str):
        raise ProjectSetupError("failed to create Ledger seed commit")

    _gh_api(
        repo,
        "git/refs",
        method="POST",
        body={"ref": "refs/heads/game-exp/ledger", "sha": commit_sha},
    )
    head = _ledger_head(repo)
    if head != commit_sha:
        raise ProjectSetupError("Ledger ref was not created at the expected commit")
    return {"status": "PASS", "changed": True, "ledger_head": head}


def _deploy_keys(repo: str) -> list[dict[str, Any]]:
    data = _json(_gh_api(repo, "keys?per_page=100"))
    if not isinstance(data, list):
        raise ProjectSetupError("deploy key response must be a list")
    return [row for row in data if isinstance(row, dict)]


def _secret_names(repo: str) -> set[str]:
    proc = _run(
        ["gh", "secret", "list", "--repo", repo, "--json", "name"],
        timeout=60,
    )
    data = _json(proc)
    if not isinstance(data, list):
        raise ProjectSetupError("repository secret response must be a list")
    return {
        str(row["name"])
        for row in data
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }


def _environment_secret_names(repo: str) -> set[str]:
    proc = _run(
        [
            "gh",
            "secret",
            "list",
            "--env",
            WRITER_ENVIRONMENT,
            "--repo",
            repo,
            "--json",
            "name",
        ],
        check=False,
    )
    if proc.returncode != 0:
        return set()
    data = _json(proc)
    if not isinstance(data, list):
        raise ProjectSetupError("environment secret response must be a list")
    return {
        row["name"]
        for row in data
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }


def _ensure_writer_environment(repo: str) -> dict[str, Any]:
    desired = {
        "wait_timer": 0,
        "prevent_self_review": False,
        "deployment_branch_policy": {
            "protected_branches": False,
            "custom_branch_policies": True,
        },
    }
    _gh_api(
        repo,
        f"environments/{WRITER_ENVIRONMENT}",
        method="PUT",
        body=desired,
    )
    policies_proc = _gh_api(
        repo,
        f"environments/{WRITER_ENVIRONMENT}/deployment-branch-policies?per_page=100",
        check=False,
    )
    if policies_proc.returncode != 0:
        raise ProjectSetupError("cannot read Trusted Writer environment branch policies")
    payload = _json(policies_proc)
    policies = payload.get("branch_policies") if isinstance(payload, dict) else None
    if not isinstance(policies, list):
        raise ProjectSetupError("environment branch policy response is invalid")

    main_seen = False
    removed: list[str] = []
    for row in policies:
        if not isinstance(row, dict):
            continue
        policy_id = row.get("id")
        name = row.get("name")
        policy_type = row.get("type") or "branch"
        if name == "main" and policy_type == "branch":
            main_seen = True
            continue
        if isinstance(policy_id, int):
            _gh_api(
                repo,
                f"environments/{WRITER_ENVIRONMENT}/deployment-branch-policies/{policy_id}",
                method="DELETE",
            )
            removed.append(str(name))
    if not main_seen:
        _gh_api(
            repo,
            f"environments/{WRITER_ENVIRONMENT}/deployment-branch-policies",
            method="POST",
            body={"name": "main", "type": "branch"},
        )

    verify = _json(
        _gh_api(
            repo,
            f"environments/{WRITER_ENVIRONMENT}/deployment-branch-policies?per_page=100",
        )
    )
    verified = verify.get("branch_policies") if isinstance(verify, dict) else None
    active = [
        (row.get("name"), row.get("type") or "branch")
        for row in (verified or [])
        if isinstance(row, dict)
    ]
    if active != [("main", "branch")]:
        raise ProjectSetupError(
            "Trusted Writer environment must allow deployments from main only"
        )
    return {
        "status": "PASS",
        "environment": WRITER_ENVIRONMENT,
        "branch_policies": ["main"],
        "removed_policies": removed,
    }


def _write_principals(repo: str) -> list[str] | None:
    proc = _gh_api(
        repo,
        "collaborators?affiliation=all&per_page=100",
        check=False,
    )
    if proc.returncode != 0:
        return None
    rows = _json(proc)
    if not isinstance(rows, list):
        return None
    result: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        permissions = row.get("permissions")
        can_write = bool(
            isinstance(permissions, dict)
            and (
                permissions.get("push")
                or permissions.get("maintain")
                or permissions.get("admin")
            )
        )
        if can_write and isinstance(row.get("login"), str):
            result.append(row["login"])
    return sorted(set(result))


def _resolve_trust_mode(repo: str, requested: str) -> str:
    if requested in TRUST_MODES:
        return requested
    if requested != "auto":
        raise ProjectSetupError(
            "trust_mode must be auto, single-principal, or multi-principal"
        )
    metadata = _repo_metadata(repo)
    owner = metadata.get("owner") if isinstance(metadata, dict) else None
    if isinstance(owner, dict) and owner.get("type") == "Organization":
        return "multi-principal"
    principals = _write_principals(repo)
    if principals is None:
        raise ProjectSetupError(
            "cannot determine repository write principals; rerun with an explicit trust_mode"
        )
    return "multi-principal" if len(principals) > 1 else "single-principal"


def _delete_deploy_key(repo: str, key_id: int) -> None:
    _gh_api(repo, f"keys/{key_id}", method="DELETE")


def _ssh_keygen_candidates() -> list[str]:
    candidates: list[str] = []
    system = shutil.which("ssh-keygen")
    if system:
        candidates.append(system)

    if os.name == "nt":
        git = shutil.which("git")
        if git:
            git_ssh = Path(git).resolve().parents[1] / "usr" / "bin" / "ssh-keygen.exe"
            if git_ssh.is_file():
                candidates.append(str(git_ssh))

        program_files = os.environ.get("ProgramFiles")
        if program_files:
            git_ssh = Path(program_files) / "Git" / "usr" / "bin" / "ssh-keygen.exe"
            if git_ssh.is_file():
                candidates.append(str(git_ssh))

    return list(dict.fromkeys(candidates))


def _generate_writer_keypair() -> tuple[str, str]:
    candidates = _ssh_keygen_candidates()
    if not candidates:
        raise ProjectSetupError(
            "ssh-keygen was not found; install OpenSSH or Git for Windows before project-init"
        )

    failures: list[str] = []
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "writer"
        for executable in candidates:
            path.unlink(missing_ok=True)
            path.with_suffix(".pub").unlink(missing_ok=True)
            proc = _run(
                [
                    executable,
                    "-q",
                    "-t",
                    "ed25519",
                    "-N",
                    "",
                    "-C",
                    "game-exp-trusted-writer",
                    "-f",
                    str(path),
                ],
                check=False,
            )
            if proc.returncode != 0:
                failures.append(f"{executable}: exit {proc.returncode}")
                continue
            if not path.is_file() or not path.with_suffix(".pub").is_file():
                failures.append(f"{executable}: key files were not created")
                continue

            private = path.read_text(encoding="utf-8")
            public = path.with_suffix(".pub").read_text(encoding="utf-8").strip()
            if (
                "BEGIN OPENSSH PRIVATE KEY" in private
                and public.startswith("ssh-ed25519 ")
            ):
                return private, public
            failures.append(f"{executable}: generated key format was invalid")

    raise ProjectSetupError(
        "failed to generate Trusted Writer ed25519 keypair; "
        + "; ".join(failures)
    )


def _ensure_writer_credentials(repo: str) -> dict[str, Any]:
    keys = _deploy_keys(repo)
    write_keys = [row for row in keys if not row.get("read_only", True)]
    matching = [row for row in write_keys if row.get("title") == WRITER_KEY_TITLE]
    repo_secrets = _secret_names(repo)
    env_secrets = _environment_secret_names(repo)

    unrelated = [row for row in write_keys if row.get("title") != WRITER_KEY_TITLE]
    if unrelated:
        raise ProjectSetupError(
            "repository has other write-capable deploy keys; remove or review them before "
            "project-init so Trusted Writer remains the only write deploy key"
        )
    if len(matching) > 1:
        raise ProjectSetupError("multiple game-exp Trusted Writer deploy keys exist")

    if (
        len(write_keys) == 1
        and len(matching) == 1
        and WRITER_SECRET in env_secrets
    ):
        changed = False
        if WRITER_SECRET in repo_secrets:
            deleted = _run(
                ["gh", "secret", "delete", WRITER_SECRET, "--repo", repo],
                check=False,
            )
            if deleted.returncode != 0:
                raise ProjectSetupError(
                    "Trusted Writer environment secret is healthy but the legacy "
                    "repository secret could not be removed"
                )
            changed = True
        return {
            "status": "PASS",
            "changed": changed,
            "deploy_key_id": matching[0].get("id"),
            "secret": WRITER_SECRET,
            "secret_scope": "environment",
            "environment": WRITER_ENVIRONMENT,
        }

    private, public = _generate_writer_keypair()
    old_key_id = None
    if matching:
        old_key_id = matching[0].get("id")
        if not isinstance(old_key_id, int):
            raise ProjectSetupError("existing Trusted Writer deploy key id is invalid")
        _delete_deploy_key(repo, old_key_id)

    created = _json(
        _gh_api(
            repo,
            "keys",
            method="POST",
            body={
                "title": WRITER_KEY_TITLE,
                "key": public,
                "read_only": False,
            },
        )
    )
    created_id = created.get("id")
    if not isinstance(created_id, int):
        raise ProjectSetupError("Trusted Writer deploy key creation did not return an id")

    secret_proc = _run(
        [
            "gh",
            "secret",
            "set",
            WRITER_SECRET,
            "--env",
            WRITER_ENVIRONMENT,
            "--repo",
            repo,
        ],
        check=False,
        input_bytes=private.encode("utf-8"),
        timeout=60,
    )
    if secret_proc.returncode != 0:
        _delete_deploy_key(repo, created_id)
        raise ProjectSetupError(
            "failed setting Trusted Writer Environment secret; newly created deploy key "
            "was rolled back: " + secret_proc.stderr[-1200:]
        )

    if WRITER_SECRET in repo_secrets:
        deleted = _run(
            ["gh", "secret", "delete", WRITER_SECRET, "--repo", repo],
            check=False,
        )
        if deleted.returncode != 0:
            raise ProjectSetupError(
                "environment secret was created but legacy repository secret removal failed"
            )

    keys_after = _deploy_keys(repo)
    write_after = [row for row in keys_after if not row.get("read_only", True)]
    exact_after = [
        row for row in write_after if row.get("title") == WRITER_KEY_TITLE
    ]
    env_after = _environment_secret_names(repo)
    repo_after = _secret_names(repo)
    if (
        len(write_after) != 1
        or len(exact_after) != 1
        or WRITER_SECRET not in env_after
        or WRITER_SECRET in repo_after
    ):
        raise ProjectSetupError("Trusted Writer credential verification failed")
    return {
        "status": "PASS",
        "changed": True,
        "deploy_key_id": exact_after[0].get("id"),
        "secret": WRITER_SECRET,
        "secret_scope": "environment",
        "environment": WRITER_ENVIRONMENT,
    }


RULESET_TEMPLATES = ruleset_templates("single-principal")


def _ruleset_semantics(value: dict[str, Any]) -> dict[str, Any]:
    return ruleset_semantics(value)


def _ensure_rulesets(repo: str, trust_mode: str) -> dict[str, Any]:
    probe = _ruleset_probe(repo)
    if probe["status"] != "PASS":
        raise ProjectSetupError(
            f"rulesets are unavailable: {probe.get('code')}: {probe.get('detail')}"
        )
    current = {
        row.get("name"): row
        for row in probe.get("rulesets", [])
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    created: list[str] = []
    updated: list[str] = []
    ids: dict[str, int] = {}
    for template in ruleset_templates(trust_mode):
        name = template["name"]
        existing = current.get(name)
        if existing is not None:
            rule_id = existing.get("id")
            if not isinstance(rule_id, int):
                raise ProjectSetupError(f"existing ruleset {name!r} has no valid id")
            full = _json(_gh_api(repo, f"rulesets/{rule_id}"))
            if not ruleset_satisfies(full, template):
                repaired = strengthen_ruleset(full, template)
                changed = _json(
                    _gh_api(
                        repo,
                        f"rulesets/{rule_id}",
                        method="PUT",
                        body=repaired,
                    )
                )
                if not isinstance(changed, dict):
                    raise ProjectSetupError(f"ruleset {name!r} update failed")
                updated.append(name)
            ids[name] = rule_id
            continue

        created_row = _json(
            _gh_api(repo, "rulesets", method="POST", body=template)
        )
        rule_id = created_row.get("id")
        if not isinstance(rule_id, int):
            raise ProjectSetupError(f"ruleset {name!r} creation did not return an id")
        ids[name] = rule_id
        created.append(name)

    removed_legacy: list[str] = []
    for legacy_name in sorted(LEGACY_RULESET_NAMES):
        existing = current.get(legacy_name)
        if existing is None or legacy_name in RULESET_NAMES:
            continue
        rule_id = existing.get("id")
        if isinstance(rule_id, int):
            _gh_api(repo, f"rulesets/{rule_id}", method="DELETE")
            removed_legacy.append(legacy_name)

    verify_probe = _ruleset_probe(repo)
    verify_rows = {
        row.get("name"): row
        for row in verify_probe.get("rulesets", [])
        if isinstance(row, dict) and isinstance(row.get("name"), str)
    }
    for template in ruleset_templates(trust_mode):
        name = template["name"]
        summary = verify_rows.get(name)
        if not isinstance(summary, dict) or not isinstance(summary.get("id"), int):
            raise ProjectSetupError(f"ruleset {name!r} missing after provisioning")
        full = _json(_gh_api(repo, f"rulesets/{summary['id']}"))
        if ruleset_semantics(full) != ruleset_semantics(template):
            raise ProjectSetupError(f"ruleset {name!r} failed semantic verification")

    return {
        "status": "PASS",
        "changed": bool(created or updated or removed_legacy),
        "created": created,
        "updated": updated,
        "removed_legacy": removed_legacy,
        "ids": ids,
        "trust_mode": trust_mode,
    }


def _ensure_immutable_releases(repo: str) -> dict[str, Any]:
    before = _gh_api(repo, "immutable-releases", check=False)
    if before.returncode == 0:
        value = _json(before)
        if isinstance(value, dict) and value.get("enabled") is True:
            return {"status": "PASS", "changed": False, **value}
    _gh_api(repo, "immutable-releases", method="PUT")
    after = _json(_gh_api(repo, "immutable-releases"))
    if not isinstance(after, dict) or after.get("enabled") is not True:
        raise ProjectSetupError("immutable releases did not become enabled")
    return {"status": "PASS", "changed": True, **after}


def _ensure_repository_baseline(repo: str) -> dict[str, Any]:
    _gh_api(repo, "", method="PATCH", body={"has_issues": True})
    desired = {
        "default_workflow_permissions": "read",
        "can_approve_pull_request_reviews": False,
    }
    current_proc = _gh_api(repo, "actions/permissions/workflow", check=False)
    current = _json(current_proc) if current_proc.returncode == 0 else {}
    changed = (
        not isinstance(current, dict)
        or current.get("default_workflow_permissions") != "read"
        or current.get("can_approve_pull_request_reviews") is not False
    )
    if changed:
        _gh_api(
            repo,
            "actions/permissions/workflow",
            method="PUT",
            body=desired,
        )
    verified = _json(_gh_api(repo, "actions/permissions/workflow"))
    if (
        not isinstance(verified, dict)
        or verified.get("default_workflow_permissions") != "read"
        or verified.get("can_approve_pull_request_reviews") is not False
    ):
        raise ProjectSetupError("GitHub Actions default permissions were not hardened")
    return {"status": "PASS", "changed": changed, **verified}


def _latest_selftest_run(repo: str, not_before: float) -> dict[str, Any] | None:
    proc = _run(
        [
            "gh",
            "run",
            "list",
            "--repo",
            repo,
            "--workflow",
            "game-exp-trusted-writer-selftest.yml",
            "--event",
            "workflow_dispatch",
            "--limit",
            "20",
            "--json",
            "databaseId,createdAt,status,conclusion,url",
        ],
        check=False,
        timeout=30,
    )
    if proc.returncode != 0:
        return None
    rows = _json(proc)
    if not isinstance(rows, list):
        return None
    for row in rows:
        if not isinstance(row, dict):
            continue
        created = row.get("createdAt")
        if not isinstance(created, str):
            continue
        try:
            stamp = datetime.fromisoformat(created.replace("Z", "+00:00"))
            epoch = stamp.astimezone(timezone.utc).timestamp()
        except ValueError:
            continue
        if epoch >= not_before - 10:
            return row
    return None


def _run_selftest(repo: str) -> dict[str, Any]:
    started = time.time()
    dispatch = _run(
        [
            "gh",
            "workflow",
            "run",
            "game-exp-trusted-writer-selftest.yml",
            "--repo",
            repo,
            "--ref",
            "main",
        ],
        check=False,
        timeout=30,
    )
    if dispatch.returncode != 0:
        raise ProjectSetupError(
            "failed to dispatch Trusted Writer self-test: " + dispatch.stderr[-1200:]
        )

    run = None
    for _ in range(30):
        run = _latest_selftest_run(repo, started)
        if run is not None:
            break
        time.sleep(2)
    if run is None:
        raise ProjectSetupError("could not locate Trusted Writer self-test run")

    run_id = run.get("databaseId")
    if not isinstance(run_id, int):
        raise ProjectSetupError("Trusted Writer self-test run id is invalid")
    watch = _run(
        ["gh", "run", "watch", str(run_id), "--repo", repo, "--exit-status"],
        check=False,
        timeout=300,
    )
    final = _json(
        _run(
            [
                "gh",
                "run",
                "view",
                str(run_id),
                "--repo",
                repo,
                "--json",
                "status,conclusion,url",
            ],
            timeout=30,
        )
    )
    if watch.returncode != 0 or final.get("conclusion") != "success":
        raise ProjectSetupError(
            f"Trusted Writer self-test failed: {final.get('url') or run.get('url')}"
        )
    return {
        "status": "PASS",
        "run_id": run_id,
        "url": final.get("url") or run.get("url"),
    }


def provision(
    repo: str,
    *,
    run_selftest: bool = True,
    trust_mode: str = "auto",
) -> dict[str, Any]:
    gate = preflight(repo)
    if gate["status"] != "PASS":
        return {
            "status": gate["status"],
            "repo": repo,
            "complete": False,
            "preflight": gate,
        }

    resolved_trust_mode = _resolve_trust_mode(repo, trust_mode)
    steps: list[dict[str, Any]] = []

    def step(name: str, func):
        result = func()
        steps.append({"name": name, **result})
        return result

    step("ledger_ref", lambda: _ensure_ledger(repo))
    step("trusted_writer_environment", lambda: _ensure_writer_environment(repo))
    step("trusted_writer", lambda: _ensure_writer_credentials(repo))
    step("immutable_releases", lambda: _ensure_immutable_releases(repo))
    step("repository_baseline", lambda: _ensure_repository_baseline(repo))
    step("rulesets", lambda: _ensure_rulesets(repo, resolved_trust_mode))
    if run_selftest:
        step("trusted_writer_selftest", lambda: _run_selftest(repo))

    doctor = GameExpClient(GitHubTransport(repo)).doctor()
    complete = doctor.get("status") == "PASS"
    return {
        "status": "PASS" if complete else "FAIL",
        "repo": repo,
        "complete": complete,
        "trust_mode": resolved_trust_mode,
        "steps": steps,
        "doctor": doctor,
    }
