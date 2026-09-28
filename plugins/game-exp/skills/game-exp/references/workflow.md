# game-exp workflow reference

## Lifecycle

Canonical lifecycle:

`ACTIVE -> REVIEW -> PROMISING -> SELECTED -> INTEGRATED -> ARCHIVED`

Additional paths:

- `REVIEW -> ACTIVE`
- `REVIEW -> REJECTED`
- `PROMISING -> ACTIVE`
- `PROMISING -> REJECTED`
- `ACTIVE / REVIEW / PROMISING / SELECTED -> ABANDONED` for an explicit human stop that is not a Review result
- `REJECTED / ABANDONED -> ARCHIVED` through the dedicated Archive protocol
- supported non-terminal lifecycles may also be archived through the dedicated Archive protocol

`INTEGRATED` and `ARCHIVED` are reserved for dedicated trusted operations, not generic lifecycle decisions.

## Iteration routing

Classify a requested change to an existing experiment before creating another experiment.

The default route is **same-experiment revision** when these remain materially unchanged:

- hypothesis;
- success/kill criteria;
- core mechanic;
- intended player experience.

Bug fixes, polish, balancing, feel tuning, implementation repair, incomplete Agent output, and playtest-driven improvements to the same design belong to the existing experiment. In `ACTIVE` or `REVIEW`, continue on the existing canonical `exp/<issue>` branch. After substantive source changes, build a new Candidate. Candidate registration replaces the current Candidate and clears the previous current Review binding, so changed code requires fresh human evaluation.

A possible **new experiment** exists when at least one experiment boundary changes materially: hypothesis, success criteria, core mechanic, or intended player experience. The Agent may identify this automatically but must ask before creating the new Issue/Bind/Initialize operation. Do not interrupt every ordinary revision with a confirmation question.

When classification is ambiguous, ask one question about the actual design intent. Prefer "Are we improving the current combat approach, or trying a different core combat approach?" over "Revision or experiment?".

Explicit user classification wins. Existing lifecycle rules remain authoritative; routing policy does not bypass human gates or reopen terminal/selected work.

## Collaboration coordination

Before editing an existing experiment, read `game_exp_collaboration_context`. When the Harness knows its current source SHA, pass it as `observed_source_sha`.

- `CURRENT`: the Harness sees the canonical experiment branch head.
- `STALE`: synchronize before source edits.
- `UNKNOWN`: source identity was not supplied; do not claim that synchronization was verified.

Use `game_exp_work_claim` before source edits and `game_exp_work_release` after integrated completion or abandonment. Claims are protected Ledger coordination records, not lifecycle states.

Scope overlap is surfaced but not hard-locked. Prefer isolated workspaces plus merge/test when overlap is intentional. Do not silently assume another Agent's intent from chat history.

See `collaboration.md` for the full cross-Harness contract.

## Evaluation evidence

For project-policy schema v3 experiments, Manifest schema v3 binds a content-addressed Evaluation Profile. Candidate build executes the declared project evaluation command inside the trusted workflow, then a source-free observation job independently validates the result/evidence bundle.

Interpret Candidate screening conservatively:

- `ELIGIBLE`: required trusted observations passed;
- `INELIGIBLE`: at least one required condition has a trusted product-defect failure;
- `INCONCLUSIVE`: required trusted evidence is unavailable/unstable or failed for non-product reasons.

No screening result changes lifecycle.

For incumbent/challenger product judgment, keep the challenger linked with `supersedes`. If its declared review protocol is `incumbent-challenger-blind-ab-v1`, record optional structured human comparison through the normal Review mutation. The human still explicitly supplies Review PASS/FAIL.

See `evaluation.md`.

## Tool map

| User intent | Preferred MCP tool | Notes |
|---|---|---|
| Inspect repo/Ledger | `game_exp_status` | Read-only |
| Inspect public contract/features | `game_exp_capabilities` | Read-only; access snapshot is not execution authority |
| Build repository-local Manifest blueprint | `game_exp_experiment_template` | Read-only; use before first Bind instead of copying another repository's Manifest |
| Open experiment Board / panel | `game_exp_board` | Read-only consistent Ledger snapshot |
| Collaboration notification feed | `game_exp_notifications` | Read-only, replayable, external delivery adapters dedupe by event_id |
| Build implementation brief | `game_exp_prototype_handoff` | Read-only implementation handoff; no lifecycle mutation |\n| Inspect collaboration state | `game_exp_collaboration_context` | Read-only current branch / active work intents / overlap projection |\n| Declare source work | `game_exp_work_claim` | Protected intent bound to current canonical experiment branch SHA |\n| Release source work | `game_exp_work_release` | Close completed or abandoned work intent |
| Inspect experiment | `game_exp_experiment_get` | Read-only authoritative projection |
| Diagnose trust/archive health | `game_exp_doctor` | Read-only |
| Bind Manifest | `game_exp_experiment_bind` | Manifest operation id is idempotency key |
| Initialize source refs | `game_exp_initialize` | Idempotent trusted workflow |
| Build Candidate | `game_exp_candidate_build` | Build/observe/attest/retain/register |
| Record human review | `game_exp_review_record` | Human outcome only; trusted GitHub actor rechecked |
| Change lifecycle | `game_exp_decision_submit` | Human gate for PROMISING/SELECTED/REJECTED/ABANDONED |
| Stop/abandon experiment | `game_exp_abandon` | Direct human stop; never fabricate FAIL Review |
| Latest-main rehearsal | `game_exp_rehearse` | Scope-filtered, trusted tree recompute |
| Create Integration PR | `game_exp_integrate` | Does not itself mean INTEGRATED |
| Finalize merged Integration PR | `game_exp_integrate_finalize` | Verifies merged tree/ancestry |
| Recoverable Archive | `game_exp_archive` | `ATOMIC_DELETE` or `RETAIN_BRANCH` |
| Abort PREPARED Archive | `game_exp_archive_abort` | Forbidden after Claim |
| Resolve operation | `game_exp_operation_get` | Use same id for ACCEPTED/UNKNOWN/lost response across MCP/CLI/Bridge |
| Resume claimed async operation | `game_exp_operation_resume` | Same id only; refuses state drift |
| Reconcile request | `game_exp_request_get` | Backward-compatible alias for operation_get |
| Low-level request | `game_exp_request_submit` | Recovery/unsupported cases only; prefer domain tools |


## Backend routing

Before submitting a mutation:

1. Native game-exp MCP.
2. game-exp CLI when shell execution is available.
3. GitHub Bridge through the canonical Issue.
4. Otherwise stop at the missing capability.

This is interface probing, not Harness-name routing.

After a mutation is `ACCEPTED` or `UNKNOWN`, do not route a replacement mutation through another interface. Query or resume the exact same operation id. Authorization rejection is not a reason to try another interface.

Async worker actions first commit a trusted `execution.claim` containing action, exact arguments and experiment-state digest. The worker validates that protected claim and its Trusted Writer-verified actor before effects. GitHub Actions deduplicates duplicate runs by the same request id.

See `public-contract.md` for versioning, status, recovery, evidence and compatibility semantics.

## GitHub Bridge

The Bridge is a transport fallback, not a separate authority system. Mutating Bridge actions use the same stable request id. Async actions commit the same `execution.claim` before dispatching the same worker workflow. Claim-without-result remains `UNKNOWN`; reconcile the same id.

## Human-owned gates

The agent must not decide these from automated evidence:

1. Review PASS/FAIL.
2. Promotion to PROMISING.
3. Selection to SELECTED.
4. Rejection when the user has not explicitly made that decision.
5. Abandonment when the user has not explicitly chosen to stop that experiment/prototype scope.
6. Archive branch-retention choice when the user has not made the destructive intent clear.

## Trust boundaries

- Protected Ledger is authoritative.
- Trusted Writer independently resolves GitHub identity/permissions for human-gated operations.
- Candidate required checks must be trusted-observed.
- PROMISING rechecks current immutable Candidate retention.
- SELECTED rechecks current successful Rehearsal and Candidate retention.
- Integration finalization verifies merged PR tree against trusted Rehearsal tree.
- Archive finalization requires the recoverable Archive state machine and verified refs.
- The Experiment Board, Issue labels, and future UI are projections only.

## Board views

The Board projection contains `overview`, `attention`, `prototypes`, `branches`, and `archive` views. Follow `board.md` for presentation. `attention.sections` is the action Inbox, experiment `activity` is the Ledger-derived timeline, and prototype groups carry recent activity plus relationship counts. New experiments should carry stable `manifest.subject`; legacy experiments may use scope-derived fallback identity. Optional `manifest.relationships` may declare `depends_on`, `blocks`, or `supersedes` links to existing valid experiments in the same repository.

## Collaboration and implementation boundaries

- Notification events are derived from the protected Ledger and must not become a second lifecycle state machine.
- game-exp exposes targets and stable event ids; external systems perform message delivery.
- Creative exploration defaults to sequential experiments rather than automatic parallel variant generation.
- Godot Prototype Studio owns prototype implementation, runtime verification, export, and requested playtest delivery.
- game-exp resumes at Candidate/Review after implementation evidence is returned.
