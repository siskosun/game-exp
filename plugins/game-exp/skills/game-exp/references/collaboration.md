# Collaboration coordination v1

## Purpose

game-exp coordinates source-editing intent across people, Harnesses and Agents without becoming a multi-agent execution framework.

The protected Ledger remains the coordination source of truth. Chat transcripts, local task lists and Agent memory may help a Harness reason, but they do not define current collaborative work state.

## Before source editing

For an existing experiment:

1. Read `game_exp_collaboration_context(experiment_id, observed_source_sha)`.
2. If `sync_status=STALE`, synchronize to the current canonical `exp/<issue>` branch before editing.
3. Declare the work through `game_exp_work_claim`.
4. If another current claim overlaps the declared paths, surface the overlap. Do not treat it as a hard lock.
5. Prefer an isolated workspace/worktree when overlapping or uncertain work must proceed concurrently. Merge into the canonical experiment branch and run the repository's normal verification before release.
6. Release the claim with `game_exp_work_release` after the result is integrated, or mark it `ABANDONED` when the work is intentionally dropped.

A clear work claim is coordination metadata, not a new experiment, branch, lifecycle state, or human approval gate. The Agent may create it automatically as part of executing an already-authorized implementation request.

## Work claim

A protected work claim binds:

- experiment id;
- exact current canonical experiment branch SHA;
- short work summary;
- declared repository paths;
- trusted GitHub actor;
- Harness / Agent / optional session identity.

The trusted writer re-reads the canonical experiment branch and rejects a stale `base_source_sha`. This prevents a Harness from silently beginning work against an old source state.

`paths=[]` means the editing scope is not yet precise. It is treated conservatively as potentially overlapping any other current claim.

## Overlap policy

Overlapping claims are first-class coordination signals, not a hard lock or mutex.

Why:

- optimistic parallelism is useful when work is separable;
- static pre-write locking can serialize nearly all work;
- undeclared or inaccurate scopes make dynamic locking unsafe;
- a conflict signal plus isolated workspace preserves human/Agent judgment without hiding risk.

The read projection returns `WORK_SCOPE_OVERLAP` with `blocking=false`. A Harness should coordinate scope or use an isolated workspace before proceeding. It must not imply that overlap is already resolved.

## Current vs stale claims

A claim whose `base_source_sha` still equals the current canonical experiment branch head is `current`.

If that branch advances, an unreleased older claim is surfaced as `stale`. Stale claims remain auditable but do not participate in current-head overlap calculations. Their owner should refresh context and either:

- release/abandon the stale claim; or
- start a new claim on current source for continuing work.

Do not rewrite an old claim to make it current.

## Release

`COMPLETED` release requires a `result_source_sha` equal to the current canonical experiment branch head. This means the claim is closed only after its result is represented by the shared experiment branch, not merely by a private local workspace.

`ABANDONED` closes the claim without a result SHA.

The claim owner may release their own claim. Repository admins/maintainers may clean up abandoned/stale claims when necessary. Ordinary writers may not close another user's claim.

## Cross-Harness continuation

When work moves from Codex to Qoder, Cursor, ChatGPT, or another Harness:

- do not transfer raw chat as authority;
- read the compact collaboration context from the protected Ledger;
- compare the receiving Harness's observed source SHA with the canonical branch SHA;
- retain actor and executor identities separately;
- continue only from current source.

This is an explicit execution-state handoff rather than a transcript handoff.

## Research rationale

This design deliberately combines evidence from several recent lines of work without copying any one architecture wholesale:

- CAID (arXiv:2603.21489): structured delegation, isolated workspaces, dependency-aware coordination, Git merge and executable verification.
- SyncMind (arXiv:2502.06994): out-of-sync recovery is a major collaborative software-engineering failure mode.
- MPAC (arXiv:2604.09744): intent and conflict should be first-class coordination objects across independent principals.
- Turning Interaction History into Execution State (arXiv:2608.00808): compact explicit execution state is more useful than replaying raw interaction history.
- CooperBench (arXiv:2601.13295): naïve Agent collaboration can underperform independent work because of vague communication and commitment drift.
- Claim Plane (arXiv:2608.00947): pre-write declarations improve coordination, while overly static conflict controls can collapse useful concurrency.

Accordingly game-exp does **not** add CRDT editing, automatic Agent swarms, generic shared memory, or mandatory file locks in v1.
