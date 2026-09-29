---
name: game-exp
description: Create brand-new prototype projects/repositories, continue, inspect, review, compare, integrate, archive, recover, and diagnose trusted gameplay/prototype experiments across MCP, CLI, and the GitHub Bridge. Also bootstrap or upgrade game-exp repositories. Preserve protected Ledger authority, exact Candidate identity, human lifecycle gates, and recovery by stable operation id.
---

# game-exp

game-exp is the experiment control plane. Prefer native `game_exp_*` MCP tools, then the repository CLI when shell execution is available, then the authorized GitHub Bridge. Use the host's authorized source-editing capability for source changes; game-exp owns experiment identity, evidence, coordination, protected lifecycle transitions, and recovery.

Detailed rules live in the references below. Read only the reference needed for the current task.

## Non-negotiable rules

1. Treat the protected Ledger as authoritative. Local files, Issue labels, branch names, rendered Board output, chat history, Agent memory, and `actor_claim` are not authority.
2. Never write protected Ledger records or protected refs directly. Re-enter the Trusted Writer / trusted workflow boundary.
3. Never report `ACCEPTED` as completion. Resolve the same operation id with `game_exp_operation_get` / CLI / GitHub Bridge evidence.
4. After `ACCEPTED` or `UNKNOWN`, enter recovery mode. Never create a replacement request id to escape an uncertain result, claim-without-result, stale precondition, or request-id conflict.
5. An authorization failure is not a transport failure. Do not switch interfaces to retry under a different identity.
6. Never auto-approve a human gate. PASS Review does not automatically mean PROMISING. SELECTED is allowed only after the user explicitly chooses/selects the Candidate.
7. Do not fabricate a `FAIL` Review when the user simply stops work; use `game_exp_abandon`. Evaluation evidence and screening never change lifecycle automatically.
8. Do not weaken scope, Rulesets, retention, Candidate/Rehearsal freshness, trust setup, or Archive recovery semantics to make a workflow pass.
9. Keep game-exp orchestration self-contained. Do not create `.ai/HANDOFF.md` or `.ai/STATE.md`, add parallel approval systems, or spawn extra Agents merely because work overlaps.
10. For archived experiments, the immutable final tag is the official source snapshot. Do not recreate deleted experiment branches as recovery.

## Repository identity and version handshake

Global MCP registration must not hard-code one repository. Resolve an exact GitHub `owner/name` and Pass that `repo` explicitly, or intentionally bind `GAME_EXP_REPO` in a repository-local configuration. Never reuse a repository remembered from another chat.

Start unfamiliar sessions with `game_exp_status`. It is the compact 1.0 handshake for Ledger head, access, runtime version, repository version, and protocol versions. If runtime/repository versions differ, align versions before mutation.

Canonical source: https://github.com/siskosun/game-exp

For installation or upgrade, read root `INSTALL.json`. Update only the current Harness by default. The canonical installer also synchronizes the latest semantic-version-tagged `godot-prototype-studio` and `h5-game-prototype-agent` Skills into that same Harness. Do not synchronize application repositories, sandboxes, or other Harnesses as a release side effect. Use `--harness all` only when explicitly requested. Preserve legacy shared copies during a single-Harness upgrade; remove them only through explicit `--cleanup-legacy-shared`.

## Task routing

| Task | Primary tool / action | Read |
|---|---|---|
| Status / permissions / version | `game_exp_status` | `references/public-contract.md` |
| Brand-new prototype / repository | `game_exp_project_create` (local stdio/CLI) | `references/project-setup.md`, `references/onboarding.md` |
| Existing repository / trust repair | `game_exp_project_init` (optional advanced preflight), Doctor | `references/project-setup.md` |
| First experiment | `game_exp_experiment_template`, Bind, Initialize | `references/onboarding.md`, `references/workflow.md` |
| Board / one experiment / one prototype | `game_exp_board`; optional advanced panel tools when enabled | `references/board.md`, `references/chat-ui.md` |
| Continue implementation | collaboration preflight, source edit, Work Claim/Release | `references/collaboration.md`, `references/workflow.md` |
| Godot implementation / playable handoff | `game_exp_prototype_handoff` | `references/prototype-handoff.md` |
| Candidate / evaluation / human comparison | Candidate, Review | `references/evaluation.md`, `references/workflow.md` |
| Review / PROMISING / SELECTED / Integration | trusted lifecycle tools | `references/workflow.md`, `references/public-contract.md` |
| Archive / recovery | Archive tools | `references/workflow.md`, `references/public-contract.md` |
| Notifications | optional advanced `game_exp_notifications` | `references/notifications.md` |
| GitHub Issue commands | GitHub Bridge | `references/github-bridge.md` |
| Harness behavior screening | optional conformance tools | `references/conformance.md` |

## Complete project setup

Before a first experiment, the repository must be `PROJECT_READY`. Installing files alone is not completion. Local CLI and stdio MCP flows require GitHub CLI (`gh`) to be installed and authenticated (`gh auth login`).

When the user asks for a **brand-new prototype** and has not selected an existing repository, prefer `game_exp_project_create` or CLI `project-create` instead of asking them to create GitHub/Git/configuration manually. Default visibility to **public**. Existing private repositories remain usable only when their GitHub plan exposes the required protection; do not silently change an existing repository's visibility.

The project-create path creates the local starter and GitHub repository, installs game-exp files/project policy, pushes `main`, runs project-init/Doctor, then returns either `PROJECT_READY` or one retained repository plus an actionable setup blocker. It must refuse existing local directories/repositories rather than overwrite them.

If project-create succeeds, continue directly into first-experiment onboarding using the user's original prototype goal; do not ask them to repeat it.

If the optional advanced `game_exp_project_preflight` tool is registered, use it first; otherwise `game_exp_project_init` performs the same fail-closed preflight before any mutation. Run project initialization only from local stdio MCP or CLI using repository-admin credentials. Shared/streamable HTTP MCP must never perform complete project initialization.

1.0 uses a main-only `game-exp-trusted-writer` Environment for the private writer key and semantic Ruleset verification. `single-principal` and `multi-principal` are explicit trust modes; multi-principal repositories require an independent main-branch approval. A final repo-level Doctor PASS plus Trusted Writer self-test is required for `PROJECT_READY`.

Do not silently change an existing repository's visibility. New game-exp prototype repositories use public visibility by default.

## Experiment Board

Use `game_exp_board` for the default Board. If advanced focused-panel tools are registered, they may be used for one experiment/subject; otherwise use Board focus plus `game_exp_experiment_get`. All are read-only projections from one pinned Ledger snapshot.

Chinese is the default presentation. Use the emitted `display` contract rather than retranslating raw fields. Normal views are `总览`, `待处理`, `原型`, `分支图`, `归档`. Keep system-generated panel entries in natural Chinese. `health=FAIL` blocks normal lifecycle work.

Keep stable `subject` identity and `relationships` separate from scope. Distinguish `发起人` from display-only `代码贡献者`. If inline UI is available, follow `references/chat-ui.md`; otherwise use the text fallback. ChatGPT Work, Codex, and other hosts share the same read-only Board semantics.

## Route an iteration: revision or new experiment

Default to a **revision of the current experiment** when hypothesis, success/kill criteria, core mechanic, and target player experience remain materially the same. Bug fixes, implementation repair, feel tuning, balancing, visuals, UI, and playtest-driven refinement normally stay on the same canonical experiment branch.

Do not ask the user to choose between internal labels on every iteration. Revision classification may be automatic; new-experiment creation must not be silent. If the boundary changes materially, explain the concrete change and ask for confirmation before Bind/Initialize.

After substantive revision, create a new Candidate. The prior current Review binding does not carry forward to that new Candidate.

For a public repository, `game_exp_prototype_handoff` may set `delivery_request.prefer_shareable_url=true`. That is a delivery preference, not lifecycle authority: the selected prototype executor stores immutable static bytes on `gh-pages`, dispatches the managed `.github/workflows/game-exp-pages.yml` Actions deployment, and must verify both that workflow deployment and the actual browser/player path before returning a verified `SHAREABLE_URL`. game-exp never hosts the playable itself.

## Collaboration preflight for source work

Before editing an existing experiment, read `game_exp_collaboration_context`, then declare `game_exp_work_claim` once implementation is already authorized; that bookkeeping does not require another user approval.

`STALE` source means synchronize safely before editing. Scope overlap is advisory, not a hard lock. Never spawn additional Agents merely because a claim overlaps. Prefer isolated workspaces for real concurrent work.

Release with `game_exp_work_release`: `COMPLETED`, `ABANDONED`, or `HANDED_OFF`. Handoff text is participant-reported context, not authority. Unpublished local edits are not recoverable through game-exp.

After each completed implementation iteration, include structured `delivery` evidence when the executor can provide it: player-visible changes, a verified playable entry or explicit `MISSING`, 1-3 focus points, producer/build identity, and an optional previous Candidate id. Prefer the current experiment's `game_exp_board.experiments[].delivery_card` from the default MCP surface; an advanced `experiment_panel.delivery_card` is the same projection when that tool is enabled. Present the card instead of dumping the full Board. The card is an intent surface only: `保留这版` never means SELECTED; `我试玩通过了` records PASS only when the exact current Candidate is already waiting for human Review; `就选这版` preserves Rehearsal/selection prerequisites.

## Prototype implementation handoff

Specialized prototype executors are recommended but not mandatory dependencies. Before implementation, check the current host's available Skill/tool catalog.

- Godot -> `godot-prototype-studio` · https://github.com/siskosun/godot-prototype-studio
- H5/browser -> `h5-game-prototype-agent` · https://github.com/siskosun/h5-game-prototype-agent

The canonical Harness installer normally synchronizes both latest semantic-version-tagged Skills into the selected Harness. Missing capability must not make experiment health fail. Continue with the current Harness if appropriate, and never claim specialized validation that was not run.

For H5 PROBE work, `READY_FOR_PLAYTEST` is implementation evidence only; it never means Review PASS or PROMISING.

## Evaluation Evidence v1

For project-policy schema v3, use a content-addressed Evaluation Profile and obtain explicit confirmation before Bind. Screening states are exactly `ELIGIBLE`, `INELIGIBLE`, and `INCONCLUSIVE`; they are evidence, not lifecycle transitions.

Trusted evaluation runs against frozen Candidate bytes in a clean trusted job. Keep `TRUSTED_OBSERVED`, `PARTICIPANT_REPORTED`, and `HUMAN_REPORTED` distinct.

At game-exp level, v1 compares a challenger only with its declared `supersedes` incumbent. Human blind A/B uses review protocol `incumbent-challenger-blind-ab-v1`, binds exact Candidate/artifact/Profile identities, and records per-dimension outcomes. Do not add Elo for the small 2-candidate decision.

## Review and lifecycle

Use the exact current Candidate id for human Review; do not infer it at submission time. Review follows the Manifest's declared protocol.

Canonical lifecycle and permitted returns are defined in `references/workflow.md`. Human product judgment remains authoritative for PASS/FAIL Review, PROMISING, SELECTED, and REJECTED. Machine build/evaluation results only provide evidence.

A PASS Review does not automatically mean PROMISING. If a later experiment is worth continuing because it beats an incumbent, that supports Review/PROMISING; it does not mean SELECTED. A comparison-based negative conclusion is normally human FAIL Review / REJECTED. Non-evaluative stopping uses ABANDONED.

## Archive

Archive is a destructive/recovery-sensitive workflow. Follow `references/workflow.md`.

`ATOMIC_DELETE` removes the canonical experiment branch only after the protected archive preparation/evidence sequence. `RETAIN_BRANCH` preserves it by explicit user choice. Never infer Archive completion from branch absence alone.

## Cross-interface recovery

MCP tools, CLI, and the GitHub Bridge share stable request-id semantics. Use `game_exp_operation_get` to resolve an operation and `game_exp_operation_resume` only when the protocol says effects can be safely resumed.

The default 1.0 MCP surface keeps day-to-day lifecycle and recovery tools only. Optional diagnostics and secondary projections (`project_preflight`, single-experiment/subject panels, notifications, generic request submit) require `GAME_EXP_ENABLE_ADVANCED_TOOLS=1`. Legacy aliases require `GAME_EXP_ENABLE_LEGACY_TOOLS=1`; conformance-only tools require their dedicated conformance mode/flag. Do not assume optional tools are registered.

For `UNKNOWN`, transport uncertainty, or claim-without-result, keep the same request id. For authorization failure, do not use fallback authority. Use the authorized GitHub connector when repository data/actions are needed and available.

The older `game_exp_request_get`, separate access/capabilities tools, and conformance simulator tools are compatibility/diagnostic surfaces and are not registered by default in the 1.0 MCP surface.

## Harness conformance screening

Conformance is screening only. When explicitly enabled, follow `references/conformance.md`: use the same `suite_digest`, require `eligible_for_real_repo_test=true` before real-repo testing, and never treat simulator PASS as trusted end-to-end validation.

## References

- `references/workflow.md` — lifecycle, Candidate/Review/Rehearsal/Integration/Archive
- `references/public-contract.md` — cross-interface protocol and compatibility
- `references/project-setup.md` — trust bootstrap, repair, Doctor
- `references/board.md`, `references/chat-ui.md` — Board/presentation
- `references/onboarding.md` — first-use flow
- `references/collaboration.md` — work intent, freshness, handoff
- `references/evaluation.md` — Evaluation Profile/evidence/human comparison
- `references/prototype-handoff.md` — Godot/H5 executor handoff boundary
- `references/exploration-thread.md` — serial exploration rule
- `references/notifications.md` — notification/cursor rules
- `references/github-bridge.md` — Issue command surface
- `references/conformance.md` — optional Harness screening
