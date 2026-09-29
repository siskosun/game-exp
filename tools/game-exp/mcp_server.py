from __future__ import annotations

import os
from typing import Any

from mcp.server import MCPServer
from mcp.types import ToolAnnotations

from client import GameExpClient, GitHubTransport
from project_setup import preflight as project_preflight, provision as project_provision
from prototype_project import create_project as prototype_project_create
from conformance_core import (
    ConformanceClient,
    compare_reports as conformance_compare_reports,
    evaluate as conformance_evaluate,
    load_session as conformance_load_session,
    save_session as conformance_save_session,
    start_session as conformance_start_session,
    suite_descriptor as conformance_suite_descriptor,
)

mcp = MCPServer("game-exp")


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes"}


def _optional_tool(enabled: bool, *, annotations: ToolAnnotations):
    def decorate(func):
        if enabled:
            return mcp.tool(annotations=annotations)(func)
        return func
    return decorate


def _conformance_session_path() -> str | None:
    value = os.environ.get("GAME_EXP_CONFORMANCE_SESSION")
    return value.strip() if isinstance(value, str) and value.strip() else None


def _target_repo(repo: str | None = None) -> str:
    target = repo or os.environ.get("GAME_EXP_REPO")
    if not isinstance(target, str) or "/" not in target.strip():
        raise ValueError(
            "explicit repo is required for global MCP use; pass owner/name or set GAME_EXP_REPO"
        )
    return target.strip()


def _client(repo: str | None = None) -> GameExpClient | ConformanceClient:
    session_path = _conformance_session_path()
    if session_path is not None:
        return ConformanceClient(session_path, surface="mcp")
    return GameExpClient(GitHubTransport(_target_repo(repo)))


def _mcp_transport() -> str:
    return os.environ.get("GAME_EXP_MCP_TRANSPORT", "stdio").strip().lower() or "stdio"


CONFORMANCE_TOOLS_ENABLED = (
    _conformance_session_path() is not None
    or _env_flag("GAME_EXP_ENABLE_CONFORMANCE_TOOLS")
)
LEGACY_MCP_TOOLS_ENABLED = _env_flag("GAME_EXP_ENABLE_LEGACY_TOOLS")
ADVANCED_MCP_TOOLS_ENABLED = _env_flag("GAME_EXP_ENABLE_ADVANCED_TOOLS")


def _http_single_principal_write_enabled() -> bool:
    return os.environ.get(
        "GAME_EXP_MCP_TRUSTED_SINGLE_PRINCIPAL",
        "",
    ).strip().lower() in {"1", "true", "yes"}


def _write_identity_rejection(repo: str | None) -> dict[str, Any] | None:
    if _conformance_session_path() is not None:
        return None
    if _mcp_transport() != "streamable-http":
        return None
    if _http_single_principal_write_enabled():
        return None
    client = _client(repo)
    return {
        "status": "REJECTED",
        "code": "MCP_HTTP_WRITE_IDENTITY_UNBOUND",
        "repo": client.transport.repo,
        "error": (
            "Streamable HTTP write identity is not bound per caller. "
            "Use a per-user local stdio/CLI identity, GitHub Bridge, or explicitly "
            "configure a trusted single-principal HTTP endpoint."
        ),
        "fallback_policy": "AUTHORIZATION_FAILURE_DO_NOT_RETRY_AS_NEW_OPERATION",
    }


@_optional_tool(CONFORMANCE_TOOLS_ENABLED, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def game_exp_conformance_suite() -> dict[str, Any]:
    """Return the fixed synthetic behavior screening suite. Never touches GitHub."""
    result = conformance_suite_descriptor()
    return {"status": "PASS", "conformance_simulation": True, **result}


@_optional_tool(CONFORMANCE_TOOLS_ENABLED, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=False))
def game_exp_conformance_start(
    scenario_id: str,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Reset the configured synthetic session file to one conformance scenario."""
    path = _conformance_session_path()
    if path is None:
        return {
            "status": "REJECTED",
            "code": "CONFORMANCE_SESSION_PATH_REQUIRED",
            "error": "set GAME_EXP_CONFORMANCE_SESSION before starting simulator mode",
        }
    session = conformance_start_session(scenario_id, session_id=session_id)
    conformance_save_session(path, session)
    return {
        "status": "PASS",
        "conformance_simulation": True,
        "session_id": session["session_id"],
        "scenario_id": session["scenario_id"],
        "suite_digest": session["suite_digest"],
        "task_zh": session["task_zh"],
    }


@_optional_tool(CONFORMANCE_TOOLS_ENABLED, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def game_exp_conformance_compare(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, Any]:
    """Compare two screening reports only when their suite digest is identical."""
    return conformance_compare_reports(baseline, candidate)


@_optional_tool(CONFORMANCE_TOOLS_ENABLED, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=False))
def game_exp_conformance_result() -> dict[str, Any]:
    """Evaluate the configured synthetic session against the standing suite."""
    path = _conformance_session_path()
    if path is None:
        return {
            "status": "REJECTED",
            "code": "CONFORMANCE_SESSION_PATH_REQUIRED",
            "error": "set GAME_EXP_CONFORMANCE_SESSION before evaluating simulator mode",
        }
    session = conformance_load_session(path)
    if session.get("status") == "EVALUATED" and isinstance(
        session.get("evaluation"), dict
    ):
        return session["evaluation"]
    result = conformance_evaluate(session)
    conformance_save_session(path, session)
    return result


@_optional_tool(ADVANCED_MCP_TOOLS_ENABLED, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_project_preflight(repo: str | None = None) -> dict[str, Any]:
    """Check whether a repository can support a complete trusted game-exp setup."""
    if _conformance_session_path() is not None:
        return {
            "status": "REJECTED",
            "complete": False,
            "code": "PROJECT_SETUP_NOT_AVAILABLE_IN_CONFORMANCE",
        }
    target = GitHubTransport(_target_repo(repo)).repo
    return project_preflight(target)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
def game_exp_project_create(
    name: str,
    stack: str,
    visibility: str = "public",
    owner: str | None = None,
    directory: str | None = None,
    h5_mode: str = "probe",
    description: str | None = None,
    run_selftest: bool = True,
    trust_mode: str = "auto",
) -> dict[str, Any]:
    """Create a new prototype GitHub repository and provision game-exp. Local stdio only."""
    if _conformance_session_path() is not None:
        return {
            "status": "REJECTED",
            "complete": False,
            "code": "PROJECT_CREATE_NOT_AVAILABLE_IN_CONFORMANCE",
        }
    if _mcp_transport() != "stdio":
        return {
            "status": "REJECTED",
            "complete": False,
            "code": "PROJECT_CREATE_LOCAL_STDIO_REQUIRED",
            "error": (
                "project-create creates a local working tree, GitHub repository, and "
                "repository trust controls; run it through local CLI/stdio MCP."
            ),
        }
    return prototype_project_create(
        name=name,
        stack=stack,
        visibility=visibility,
        owner=owner,
        directory=directory,
        h5_mode=h5_mode,
        description=description,
        trust_mode=trust_mode,
        run_selftest=run_selftest,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_project_init(
    repo: str | None = None,
    run_selftest: bool = True,
    trust_mode: str = "auto",
) -> dict[str, Any]:
    """Provision all repository trust controls. Only local stdio MCP may run this."""
    if _conformance_session_path() is not None:
        return {
            "status": "REJECTED",
            "complete": False,
            "code": "PROJECT_SETUP_NOT_AVAILABLE_IN_CONFORMANCE",
        }
    if _mcp_transport() != "stdio":
        target = GitHubTransport(_target_repo(repo)).repo
        return {
            "status": "REJECTED",
            "complete": False,
            "repo": target,
            "code": "PROJECT_SETUP_LOCAL_STDIO_REQUIRED",
            "error": (
                "project-init generates a repository Deploy Key and writes a main-only "
                "Environment secret; run it through local CLI/stdio MCP with the repository admin "
                "GitHub principal, never through shared HTTP MCP"
            ),
        }
    target = GitHubTransport(_target_repo(repo)).repo
    result = project_provision(
        target,
        run_selftest=run_selftest,
        trust_mode=trust_mode,
    )
    if not run_selftest and result.get("status") == "PASS":
        result["status"] = "INCOMPLETE"
        result["complete"] = False
        result["reason"] = "Trusted Writer self-test was skipped"
    return result


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_status(repo: str | None = None) -> dict[str, Any]:
    """Return the target repository and authoritative game-exp Ledger head."""
    return _client(repo).status()

@_optional_tool(LEGACY_MCP_TOOLS_ENABLED, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_access_check(repo: str | None = None) -> dict[str, Any]:
    """Return the current GitHub repository access level for onboarding and gating."""
    return _client(repo).access_check()


@_optional_tool(LEGACY_MCP_TOOLS_ENABLED, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_capabilities(repo: str | None = None) -> dict[str, Any]:
    """Return versioned business capabilities and the active MCP identity boundary."""
    result = _client(repo).capabilities()
    transport = _mcp_transport()
    result["interface"] = {
        "type": "mcp",
        "transport": transport,
        "write_identity": (
            "synthetic-conformance"
            if _conformance_session_path() is not None
            else "local-gh-principal"
            if transport == "stdio"
            else "trusted-single-principal"
            if _http_single_principal_write_enabled()
            else "unbound-read-only"
        ),
        "shared_http_writes_allowed": (
            transport != "streamable-http"
            or _http_single_principal_write_enabled()
        ),
    }
    return result



@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_doctor(
    repo: str | None = None,
    experiment_id: str | None = None,
) -> dict[str, Any]:
    """Inspect trust prerequisites and optionally one archived experiment's refs."""
    return _client(repo).doctor(experiment_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_experiment_get(
    experiment_id: str,
    repo: str | None = None,
) -> dict[str, Any]:
    """Return the authoritative experiment projection from the protected Ledger."""
    return _client(repo).experiment_get(experiment_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_experiment_template(repo: str | None = None) -> dict[str, Any]:
    """Return the current repository project policy and self-describing Manifest v2 blueprint.

    Use this before creating the first experiment instead of searching another
    repository or historical Ledger records for an example.
    """
    if _conformance_session_path() is not None:
        return {
            "status": "REJECTED",
            "code": "EXPERIMENT_TEMPLATE_NOT_AVAILABLE_IN_CONFORMANCE",
            "error": "experiment-template requires a real repository project policy",
        }
    return _client(repo).experiment_template()


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_board(
    repo: str | None = None,
    query: str | None = None,
    subject_id: str | None = None,
    lifecycle: str | None = None,
    attention_only: bool = False,
) -> dict[str, Any]:
    """Return a Chinese-ready Board from one pinned Ledger snapshot.\n\n    For normal Chinese UI, render the returned `display` block as the primary\n    presentation contract. Presentation v4 sets `strict_primary_copy=true`\n    and publishes `forbidden_primary_tokens`; do not reconstruct copy from\n    raw fields, append enums such as PROJECT_READY/ADMIN/PASS, or translate\n    `doctor` as `医生检查`. Raw `project`/`repository`/`statistics` fields are\n    logic/diagnostics only. Use `display.rows_zh`,\n    `display.trust_summary_zh`, or `display.summary_text_zh`.\n    """
    return _client(repo).board(
        query=query,
        subject_id=subject_id,
        lifecycle=lifecycle,
        attention_only=attention_only,
    )

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_experiment_panel(
    experiment_id: str,
    repo: str | None = None,
) -> dict[str, Any]:
    """Return one Chinese-ready single-experiment drill-down from one pinned Ledger snapshot.

    This read-only tool is available by default. Registration is not a request
    to surface the panel proactively; open it only for explicit drill-down or
    when the Board surface hint says a contextual panel is relevant.
    """
    return _client(repo).experiment_panel(experiment_id)

@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_subject_panel(
    subject_id: str,
    repo: str | None = None,
) -> dict[str, Any]:
    """Return one Chinese-ready prototype drill-down from one pinned Ledger snapshot.

    This read-only tool is available by default. Registration alone must not
    trigger proactive UI; use it when the user opens a prototype or a Board
    interaction explicitly drills into that subject.
    """
    return _client(repo).subject_panel(subject_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_collaboration_context(
    experiment_id: str,
    repo: str | None = None,
    observed_source_sha: str | None = None,
) -> dict[str, Any]:
    """Return current branch, active work intents, sync state and overlap conflicts."""
    return _client(repo).collaboration_context(
        experiment_id,
        observed_source_sha=observed_source_sha,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_prototype_handoff(
    experiment_id: str,
    repo: str | None = None,
) -> dict[str, Any]:
    """Return the exact implementation brief and recommended specialized prototype executor."""
    return _client(repo).prototype_handoff(experiment_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_notifications(
    repo: str | None = None,
    viewer_login: str | None = None,
    subject_id: str | None = None,
    limit: int = 50,
    after: str | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    """Return cursor-resumable collaboration events from committed Ledger snapshots.

    This read-only feed is available by default but is not a polling mandate.
    Call it for explicit collaboration/activity requests or a user workflow
    that actually needs event deltas; do not surface it merely because the tool
    is registered.
    """
    return _client(repo).notification_feed(
        viewer_login=viewer_login,
        subject_id=subject_id,
        limit=limit,
        after=after,
        cursor=cursor,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_work_claim(
    experiment_id: str,
    base_source_sha: str,
    summary: str,
    paths: list[str],
    harness: str,
    agent: str,
    request_id: str,
    session_id: str | None = None,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Declare one protected source-editing intent before modifying an experiment."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).work_claim(
        experiment_id,
        base_source_sha=base_source_sha,
        summary=summary,
        paths=paths,
        harness=harness,
        agent=agent,
        session_id=session_id,
        actor_claim=actor_claim,
        request_id=request_id,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_work_release(
    experiment_id: str,
    claim_id: str,
    outcome: str,
    notes: str,
    request_id: str,
    result_source_sha: str | None = None,
    handoff: dict[str, Any] | None = None,
    delivery: dict[str, Any] | None = None,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Release one protected work intent after integration or abandonment."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).work_release(
        experiment_id,
        claim_id=claim_id,
        outcome=outcome,
        notes=notes,
        result_source_sha=result_source_sha,
        handoff=handoff,
        delivery=delivery,
        actor_claim=actor_claim,
        request_id=request_id,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
def game_exp_experiment_bind(
    manifest: dict[str, Any],
    request_id: str | None = None,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Submit a canonical experiment Manifest for trusted GitHub identity binding.

    The protocol binds Manifest operation_id to the request id. If request_id is
    omitted, manifest.operation_id is used as the idempotency key.
    """
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    client = _client(repo)
    manifest_request_id = manifest.get("operation_id")
    if not isinstance(manifest_request_id, str) or not manifest_request_id:
        return {
            "status": "REJECTED",
            "repo": client.transport.repo,
            "error": "manifest.operation_id is required",
        }
    if request_id is not None and request_id != manifest_request_id:
        return {
            "status": "REJECTED",
            "repo": client.transport.repo,
            "request_id": request_id,
            "manifest_operation_id": manifest_request_id,
            "error": "request_id must equal manifest.operation_id",
        }
    return client.submit(
        operation="experiment.bind",
        input_value={"manifest": manifest},
        actor_claim=actor_claim,
        request_id=manifest_request_id,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_initialize(
    experiment_id: str,
    request_id: str,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Initialize canonical source refs under a stable cross-interface operation id."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).initialize(
        experiment_id,
        request_id=request_id,
        actor_claim=actor_claim,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_candidate_build(
    experiment_id: str,
    request_id: str,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Build/register a trusted Candidate under a stable cross-interface operation id."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).candidate(
        experiment_id,
        request_id=request_id,
        actor_claim=actor_claim,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_review_record(
    experiment_id: str,
    outcome: str,
    notes: str,
    request_id: str,
    candidate_id: str,
    comparison: dict[str, Any] | None = None,
    revision_comparison: dict[str, Any] | None = None,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Record human PASS/FAIL for one concrete Candidate using a stable request id."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    client = _client(repo)
    return client.review_record(
        experiment_id,
        candidate_id=candidate_id,
        outcome=outcome,
        notes=notes,
        comparison=comparison,
        revision_comparison=revision_comparison,
        actor_claim=actor_claim,
        request_id=request_id,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_decision_submit(
    experiment_id: str,
    to_state: str,
    reason: str,
    request_id: str,
    previous_decision_id: str | None = None,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Submit one lifecycle Decision bound to protected state and a stable request id."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    client = _client(repo)
    if previous_decision_id is None:
        projection = client.experiment_get(experiment_id)
        if projection.get("status") != "PASS":
            return projection
        previous_decision_id = projection.get("state", {}).get("last_decision_id")
    return client.submit(
        operation="experiment.decision",
        input_value={
            "experiment_id": experiment_id,
            "to_state": to_state,
            "previous_decision_id": previous_decision_id,
            "reason": reason,
        },
        actor_claim=actor_claim,
        request_id=request_id,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True))
def game_exp_abandon(
    experiment_id: str,
    reason: str,
    request_id: str,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Explicitly stop an experiment without fabricating a FAIL Review.

    ABANDONED is a terminal human decision for strategic/resource/product stops.
    It does not close the GitHub Issue, archive/delete the branch, delete source,
    or imply the Candidate failed its review protocol.
    """
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).abandon(
        experiment_id,
        reason,
        request_id=request_id,
        actor_claim=actor_claim,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_rehearse(
    experiment_id: str,
    request_id: str,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Run latest-main trusted Rehearsal under a stable cross-interface operation id."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).rehearse(
        experiment_id,
        request_id=request_id,
        actor_claim=actor_claim,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_integrate(
    experiment_id: str,
    request_id: str,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Create/reuse the Integration PR under a stable cross-interface operation id."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).integrate(
        experiment_id,
        request_id=request_id,
        actor_claim=actor_claim,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_integrate_finalize(
    experiment_id: str,
    pr_number: str,
    request_id: str,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Finalize an actually merged Integration PR under the same operation contract."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).integrate_finalize(
        experiment_id,
        pr_number,
        request_id=request_id,
        actor_claim=actor_claim,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=True, openWorldHint=True))
def game_exp_archive(
    experiment_id: str,
    request_id: str,
    mode: str = "ATOMIC_DELETE",
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Run recoverable Archive under a stable cross-interface operation id."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).archive(
        experiment_id,
        mode,
        request_id=request_id,
        actor_claim=actor_claim,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False, openWorldHint=True))
def game_exp_archive_abort(
    experiment_id: str,
    archive_id: str,
    reason: str,
    request_id: str,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Abort an Archive only while it is PREPARED and has not been claimed."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).archive_abort(
        experiment_id,
        archive_id,
        reason,
        actor_claim=actor_claim,
        request_id=request_id,
    )


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_operation_get(
    request_id: str,
    repo: str | None = None,
) -> dict[str, Any]:
    """Resolve a trusted request or async execution using the exact same operation id."""
    return _client(repo).operation_get(request_id)


@_optional_tool(LEGACY_MCP_TOOLS_ENABLED, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_request_get(
    request_id: str,
    repo: str | None = None,
) -> dict[str, Any]:
    """Backward-compatible alias for game_exp_operation_get."""
    return _client(repo).operation_get(request_id)


@mcp.tool(annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_operation_resume(
    request_id: str,
    repo: str | None = None,
) -> dict[str, Any]:
    """Resume only the already-claimed async operation with this exact operation id."""
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).resume_execution(request_id)


@_optional_tool(ADVANCED_MCP_TOOLS_ENABLED, annotations=ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=True, openWorldHint=True))
def game_exp_request_submit(
    operation: str,
    input: dict[str, Any],
    request_id: str,
    preconditions: dict[str, Any] | None = None,
    actor_claim: str | None = None,
    repo: str | None = None,
) -> dict[str, Any]:
    """Submit one controlled operation request through the Trusted Writer.

    This tool submits an operation envelope only. It does not claim that the
    requested domain operation has been executed. Use game_exp_request_get to
    resolve ACCEPTED/UNKNOWN requests against the authoritative Ledger. A stable
    request_id is mandatory; authorization failures are not a signal to retry
    through another interface.
    """
    blocked = _write_identity_rejection(repo)
    if blocked is not None:
        return blocked
    return _client(repo).submit(
        operation=operation,
        input_value=input,
        preconditions=preconditions,
        actor_claim=actor_claim,
        request_id=request_id,
    )


def _http_port() -> int:
    raw = os.environ.get("GAME_EXP_MCP_PORT", "8765").strip()
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError("GAME_EXP_MCP_PORT must be an integer") from exc
    if not 1 <= port <= 65535:
        raise RuntimeError("GAME_EXP_MCP_PORT must be between 1 and 65535")
    return port


def _run_server() -> None:
    transport = os.environ.get("GAME_EXP_MCP_TRANSPORT", "stdio").strip().lower()
    if transport == "stdio":
        mcp.run()
        return
    if transport != "streamable-http":
        raise RuntimeError(
            "GAME_EXP_MCP_TRANSPORT must be stdio or streamable-http"
        )

    path = os.environ.get("GAME_EXP_MCP_PATH", "/mcp").strip() or "/mcp"
    if not path.startswith("/"):
        raise RuntimeError("GAME_EXP_MCP_PATH must start with /")

    mcp.run(
        transport="streamable-http",
        host=os.environ.get("GAME_EXP_MCP_HOST", "127.0.0.1").strip()
        or "127.0.0.1",
        port=_http_port(),
        streamable_http_path=path,
        stateless_http=True,
        json_response=True,
    )


if __name__ == "__main__":
    _run_server()
