# game-exp public cross-interface contract

## Purpose

MCP, CLI and the GitHub Bridge are replaceable interfaces. They do not define experiment truth and they do not gain write authority merely by sharing code.

The stable contract is:

```text
Harness
  -> MCP / CLI / GitHub Bridge
  -> versioned command/query contract
  -> trusted execution boundary
  -> domain rules
  -> protected game-exp Ledger
```

## Contract version

Current public contract: `1.0`.

A client may tolerate new result fields within the same major version. Mutating requests remain strict and reject unknown request fields. An unsupported major version must fail closed rather than guessing.

Use `game_exp_capabilities` or `game-exp capabilities` to inspect business features and contract version. Repository access returned there is only a current snapshot for UX; every write is re-authorized at the trusted boundary.

## Self-describing Manifest contract

A new Harness must be able to create the first experiment without reading another repository or historical Ledger examples.

Use `game_exp_experiment_template` or CLI `experiment-template` to read:

- the current repository's `.game-exp/project-policy.json`;
- the recommended Manifest schema version;
- the runtime shape derived from that project policy;
- the default human review protocol;
- Evaluation Profile requirements when project policy v3 enables them;
- which fields are user-owned versus resolved by the Agent.

Manifest schema v2 remains the recommended generic runtime contract for project-policy schema v1/v2 repositories. Manifest schema v3 is recommended when project-policy schema v3 enables Evaluation Evidence v1.

Both v2 and v3 use the generic repository-policy runtime shape:

```json
{
  "runtime": {
    "adapter": "node-npm",
    "policy_path": ".game-exp/project-policy.json"
  }
}
```

Schema v3 additionally requires one content-addressed Evaluation Profile reference:

```json
{
  "evaluation_profile": {
    "path": ".game-exp/evaluation-profiles/profile-id.json",
    "digest": "sha256:<64 lowercase hex>",
    "version": 1
  }
}
```

The adapter value comes from the current repository project policy. Manifest schema v1 remains accepted for existing experiments and uses the legacy Godot-specific runtime object. New experiments should not emit Godot placeholder fields for non-Godot repositories.

The example Manifest returned by `experiment-template` contains unresolved placeholders and is explicitly non-bindable. The Agent must resolve the real Issue identity, parent SHA, stable operation id, scope, subject, timestamp and, for schema v3, the exact Profile digest before Bind.

## Project policy schema

Project validation policy is repository-local and independent from Manifest schema.

- Project policy schema v1 remains compatible and is limited to the legacy `node-npm` shape.
- Project policy schema v2 keeps install/test/build as argv arrays and makes the adapter generic.
- Project policy schema v3 adds one protected `evaluation` argv command plus the fixed `.game-exp/evaluation-output` directory. Use it only when the repository is ready to participate in Evaluation Evidence v1.
- The evaluation argv must execute a runner from `control/.game-exp/evaluation/`, checked out from the protected workflow source rather than the experiment branch.
- For `node-npm`, schema v2/v3 requires an exact `toolchain.node_version`. Trusted workflows use that value with `actions/setup-node`; they no longer require a repository `.node-version` file.
- For adapters other than `node-npm`, `toolchain` is currently empty and game-exp performs no implicit runtime installation. Declared argv commands must be self-contained on the trusted `ubuntu-latest` runner.

Bootstrap must not guess Node/npm for an unknown repository type. Existing v1/v2 repositories remain valid and are not automatically upgraded to evaluation-enabled v3.

## Evaluation Evidence v1

Evaluation Evidence v1 is opt-in through project-policy schema v3 and Manifest schema v3.

The Profile is content-addressed and frozen by the human-authorized Manifest Bind. The Candidate workflow:

1. fetches the Profile from the exact Candidate source commit;
2. recomputes its digest;
3. removes the fixed evaluation output directory;
4. runs the repository-declared evaluation argv command;
5. packages its fresh output;
6. independently validates the output in a trusted job without experiment source checkout;
7. recomputes referenced evidence digests;
8. stores only compact trusted summaries/digests in Ledger while retaining larger bytes in the immutable Candidate release.

Screening is exactly `ELIGIBLE | INELIGIBLE | INCONCLUSIVE`. It never mutates lifecycle.

`PARTICIPANT_REPORTED` exploration cannot by itself create trusted PASS/FAIL. `HUMAN_REPORTED` A/B preference is recorded through the existing Review authority path and remains distinct from `TRUSTED_OBSERVED` machine evidence.

v1 introduces no persistent Comparison Set. One challenger compares with the current Candidate of its `supersedes` incumbent. Structured blind A/B comparison is optional Review evidence only when the Manifest review protocol is `incumbent-challenger-blind-ab-v1`.

See `evaluation.md`.

## Board presentation contract

`game_exp_board` returns both machine-facing state and ready-to-render Chinese presentation data.

For normal Chinese UI, `display` is authoritative presentation copy:

- `display.presentation_version >= 4` means the host must not rebuild visible labels by translating raw field names;
- render `display.rows_zh` and `display.trust_summary_zh`, or use `display.summary_text_zh` for a plain-text surface;
- `presentation.primary=display` and `display.render_contract` explicitly mark raw `project`, `repository`, `statistics`, and enum fields as logic/diagnostic inputs;
- presentation v4 adds `strict_primary_copy=true`, a canonical terminology map, and `forbidden_primary_tokens` so rich Harness UIs can mechanically prevent mixed Chinese/engineering copy;
- raw codes such as `PROJECT_READY`, `ADMIN`, `WRITE`, `PASS`, `FAIL`, and internal names such as `doctor` are not ordinary UI copy;
- `doctor` is presented as `仓库检查`, never a literal translation such as `医生检查`;
- repository identifiers, branch names, commit hashes, experiment ids, and product names may remain literal.

This contract exists specifically so Codex, Qoder, Cursor, ChatGPT, and future Harnesses render the same Chinese Board instead of independently translating engineering keys.

## Stable operation identity

Every logical mutation has one stable `request_id` / operation id.

- Same id + same request: replay or return the existing operation.
- Same id + different request: `CONFLICT`.
- Lost response, timeout, or `UNKNOWN`: query the same id with `game_exp_operation_get` / `game-exp get-operation`.
- Never create a new id to escape uncertainty.
- Authorization failure is terminal for that attempted authority context. Do not retry the same logical mutation through another interface to bypass it.

For asynchronous lifecycle workers (Initialize, Candidate, Rehearsal, Integration, Integration Finalize, Archive), the stable id first commits an `execution.claim` in the protected Ledger. A v2 claim binds:

- experiment id;
- action;
- exact action arguments;
- authoritative experiment-state digest;
- action-specific version identities such as source SHA, Candidate/Rehearsal ids, manifest digest and main SHA;
- Trusted Writer-verified GitHub actor.

The Trusted Writer validates these identities at claim commit, and the worker validates the committed claim again before effects. Only a workflow run whose action/arguments match that committed claim may perform effects. Duplicate runs with the same request id are remotely deduplicated.

## 1.0 session handshake and MCP surface

Start an unfamiliar session with `game_exp_status`. The status response is intentionally compact and includes:

- exact `owner/name` repository identity;
- current protected Ledger head;
- repository access snapshot;
- running game-exp version;
- repository game-exp version;
- `MATCH / RUNTIME_OLDER / REPOSITORY_OLDER / UNKNOWN` version state;
- supported Manifest/project-policy protocol versions.

A runtime/repository version mismatch is a pre-mutation warning: align versions before changing experiment state.

Global MCP use requires an explicit repository argument or an intentionally configured `GAME_EXP_REPO`; it must not infer a repository from an unrelated process working directory.

The 1.0 default MCP surface keeps daily workflow tools only. Compatibility/diagnostic surfaces remain implemented but are not registered unless explicitly enabled:

- `game_exp_access_check`, `game_exp_capabilities`, `game_exp_request_get` via `GAME_EXP_ENABLE_LEGACY_TOOLS=1`;
- the conformance simulator tools via `GAME_EXP_ENABLE_CONFORMANCE_TOOLS=1` or an active conformance session.

This is an Agent-context optimization only. It does not remove the underlying CLI/protocol compatibility contract.

## Contextual surface contract v1

`features.contextual_surface_v1=true` adds a read-only presentation hint to experiment projections.

- `COMPACT_RESULT`: normal progress stays compact; the full Board is not the default end screen.
- `CONTEXTUAL_PANEL`: current evidence says a human action, recovery item, health issue, archive choice, or dependency review deserves attention.
- `surface_when_relevant` is presentation guidance for the host.
- `authoritative=false` is required; the hint never changes experiment authority or the valid next action.
- an explicit user request for the Board still opens the full Board.

The trigger is whether the user needs to act now, not merely whether an Agent finished work.
## Routing and recovery

Before any mutation has been submitted, prefer interfaces in this order:

1. native game-exp MCP;
2. game-exp CLI when shell execution is available;
3. GitHub Bridge when an authorized GitHub Issue-comment path is available.

Interface availability is not permission.

### MCP identity modes

Local stdio MCP and the CLI normally execute under the local GitHub credential and therefore have one concrete local principal.

Streamable HTTP is different: a shared server credential is not automatically the caller's identity. game-exp therefore treats HTTP MCP as read-only by default unless the deployment explicitly sets `GAME_EXP_MCP_TRUSTED_SINGLE_PRINCIPAL=1` for a genuinely single-principal endpoint. Multi-user HTTP deployments require a future per-request identity binding; until then use per-user local MCP/CLI or GitHub Bridge for writes.

Supporting MCP transport does not imply equivalent authorization semantics.

After a mutation returns `ACCEPTED` or `UNKNOWN`, enter recovery mode. You may use another interface to query or resume the same operation id, but you must not create a replacement logical operation.

Example:

```text
MCP candidate_build req-123
  -> reply lost

CLI:
game-exp get-operation req-123
game-exp resume-operation req-123
```

This is valid because the operation identity is unchanged.

## Result semantics

- `PASS`: a read/projection/check succeeded, or an asynchronous worker completed successfully.
- `WARN`: result exists but has an explicit non-fatal condition.
- `ACCEPTED`: accepted/claimed/dispatched/running; not completion.
- `COMMITTED`: protected Ledger contains the matching request record.
- `CONFLICT`: identity, state precondition, request digest, or concurrency fact differs.
- `REJECTED`: validated failure; do not retry unchanged.
- `UNKNOWN`: outcome cannot yet be proved; recover by the same operation id.

## Abandonment vs Review failure

`ABANDONED` is a first-class terminal lifecycle decision for explicitly stopping an experiment without claiming that the Candidate failed its declared human Review protocol.

- Valid decision transitions: `ACTIVE / REVIEW / PROMISING / SELECTED -> ABANDONED`.
- Use MCP `game_exp_abandon`, CLI `abandon`, or Bridge `decision_submit` with `to_state=ABANDONED`.
- The decision requires a trusted write-capable GitHub actor and a human-supplied reason.
- No Candidate or Review is required.
- `ABANDONED` does not close the canonical Issue, archive/delete the experiment branch, delete source, or delete immutable Candidate Releases.
- A later Archive is a separate operation and retains the normal `ATOMIC_DELETE` / `RETAIN_BRANCH` human choice.
- Closing the canonical Issue alone does not change Ledger lifecycle.
- A `FAIL` Review must describe an actual human Review outcome. It must never be fabricated as a mechanical path to stop an experiment.

When a user refers to a prototype/subject rather than one experiment, resolve the subject first. If multiple non-terminal experiments exist, the affected experiment set is a material scope choice and must be confirmed before applying multiple terminal decisions.

## Cancellation

There is no generic `cancel-operation` in public contract v1.0. A claimed/running async operation is recovered or allowed to complete; arbitrary cancellation could leave external effects ambiguous.

Archive keeps its existing dedicated `archive_abort`, valid only while the Archive is PREPARED and has not been claimed. Once claimed, recover the same Archive instead of cancelling it.


Transport wrappers may differ between MCP, CLI and Bridge. The business statuses and recovery semantics must not.

## Trusted execution boundary

Local MCP/CLI validation is advisory. Authoritative mutations are checked again by trusted GitHub workflows / Trusted Writer.

The trusted side verifies as applicable:

- current GitHub identity and repository permission;
- request id and payload digest;
- protected Ledger head/state;
- lifecycle and previous decision id;
- Candidate/source/rehearsal/integration evidence;
- archive lock/ref evidence;
- exact asynchronous execution claim.

A local CLI executable being modifiable does not grant Ledger write authority.

## Human decisions

Human Review and lifecycle decisions remain tied to concrete evidence.

A Review must identify the Candidate and its artifact digest. Promotion and selection re-check the current Candidate, Review, retention and/or Rehearsal. A human approval for an earlier Candidate does not silently apply to a later Candidate.

Abandonment is different evidence: it records an explicit human decision to stop work for a stated reason and intentionally requires no PASS/FAIL Review evidence.

Never convert a generic `approved=true` flag into authoritative human evidence.

## Capability probing

Route by available interface, not Harness brand. Do not maintain a Codex/Cursor/Claude/Qoder business-logic fork.

Typical probing:

```text
game_exp_* MCP available?
  -> MCP
else game-exp CLI available?
  -> CLI
else authorized GitHub Bridge available?
  -> Bridge
else
  -> report missing execution capability
```

A newly supported Harness should normally require no Domain Core changes. Installation, credentials, UI integration and compatibility verification may still require small host-specific setup.

## Notifications

Notification events are deterministic projections of committed Ledger snapshots.

Adapters must:

1. page with `cursor` until `next_cursor` is empty;
2. persist the returned `checkpoint_cursor` only after all pages are processed;
3. use that checkpoint as `after` on the next poll;
4. deduplicate by `event_id`;
5. respect viewer access;
6. handle `CURSOR_EXPIRED` explicitly.

Delivery retries and delivered/read state stay outside game-exp.

## Dependency review

`depends_on` is currently a coarse experiment relationship. Lifecycle alone does not prove whether a dependency is still satisfied.

If an active experiment depends on an experiment that becomes REJECTED or ARCHIVED, game-exp emits `DEPENDENCY_REVIEW_REQUIRED` with supporting evidence. It does not automatically reject the downstream experiment.

A later contract version may introduce explicit dependency predicates such as “integrated capability”, “immutable source snapshot”, or “continued upstream delivery” if real usage requires them.

## New prototype project creation

`game_exp_project_create` is the local-stdio/CLI convenience surface for a brand-new prototype when no repository exists yet.

It may create a local Git working tree and a GitHub repository, install the current game-exp managed files, seed a tagged GPS/H5 starter, push `main`, and invoke the same project-init trust provisioning used by existing repositories.

Contract:

- stack is explicit: `godot` or `h5`;
- default repository visibility is `private`;
- existing local directories and existing GitHub repositories are never overwritten;
- H5 defaults to the PROBE starter unless the caller explicitly asks for SLICE;
- public visibility is explicit and is never selected automatically to bypass a GitHub plan limitation;
- repository creation is durable: if later trust provisioning fails, the retained repository is returned with an actionable resume step instead of being deleted/recreated;
- `PROJECT_READY` requires normal project-init completion, Trusted Writer self-test, and Doctor PASS;
- shared/streamable HTTP MCP must reject project creation because the workflow requires local filesystem/GitHub-admin operations.

Project creation does not itself create or approve an experiment. After `PROJECT_READY`, continue first-experiment onboarding with the user's original prototype goal.

## Prototype handoff

`game_exp_prototype_handoff` emits Handoff schema v2 for a specialized prototype executor. It preserves the schema version and adds executor metadata without changing lifecycle authority.

The return evidence must bind:

- experiment id;
- handoff id;
- exact source SHA;
- build id / producer;
- checks and their environment;
- artifact locations and digests;
- whether each artifact location is portable across Harnesses.

A local filesystem path alone is not sufficient cross-Harness evidence unless it is explicitly marked `portable=false`.

A2A may later transport the same task/artifact semantics if a specialized prototype Skill becomes an independent Agent. A2A transport must not redefine game-exp human approvals, idempotency or evidence validity.


### Board presentation v5

`experiments[].card_zh` is the normative primary-copy surface for experiment cards. It is ready to render in Chinese and carries experiment, prototype, initiator, contributor, branch, progress, health, and next-action rows. Raw enum fields remain available for logic and diagnostics but are not primary UI copy.

### Board presentation v6

Chinese primary UI copy uses `主干集成验证` for protocol `Rehearsal`, because the operation validates the candidate's integration result against the latest main branch. Experiment detail surfaces expose `evidence_zh.rows_zh` with fixed Chinese labels for 候选版本、人工评审、主干集成验证、集成、归档. Raw `rehearsal_id` remains a protocol and diagnostics field.

## Iteration routing policy v1

Iteration routing is a cross-Harness semantic policy, not a new lifecycle state or authority source.

`game_exp_capabilities` exposes `features.iteration_routing_v1=true` and an `iteration_routing` descriptor. Clients should default an existing-experiment change to `REVISION` when hypothesis, success criteria, core mechanic, and target player experience remain materially unchanged. A revision reuses the existing experiment and canonical branch; after substantive changes it produces a new Candidate, and an earlier Review does not carry forward to the changed Candidate.

A Harness may infer that a request crosses an experiment boundary, but it must get user confirmation before creating a new experiment. Clear revisions proceed without a taxonomy confirmation. Ambiguous cases should ask one design-intent question rather than requiring the user to understand game-exp's internal classification.

This policy does not mutate lifecycle state, loosen human gates, or authorize reopening `SELECTED`, `INTEGRATED`, or `ARCHIVED` work.

## Optional implementation capability contract v1

`game_exp_capabilities` exposes `features.optional_implementation_capabilities_v1=true`, `recommended_capabilities.godot_prototype_studio`, and `recommended_capabilities.h5_game_prototype_agent`.

Godot Prototype Studio and H5 Game Prototype Agent are recommended but optional. Canonical sources are `https://github.com/siskosun/godot-prototype-studio` and `https://github.com/siskosun/h5-game-prototype-agent`. The host, not game-exp Ledger state, resolves whether each Skill/tool is currently available. Absence is non-blocking and must not affect project readiness, experiment health, or lifecycle.

The canonical Harness installer synchronizes the latest semantic-version-tagged releases of both companion Skills into the selected Harness. This is install convenience, not protocol authority.

`game_exp_prototype_handoff` includes both `recommended_executors` and one `recommended_executor`. For `runtime.adapter=node-npm`, H5 Game Prototype Agent is preferred; other game runtimes keep Godot Prototype Studio as the default specialized executor. The host may override that suggestion when the user/project has already selected another stack.

A host may continue with ordinary source-editing capability when the specialized Skill is unavailable, but may report only implementation/runtime/browser/export/playable evidence it actually produced. H5 PROBE machine verdicts remain evidence and never authorize lifecycle transitions.

This adds optional result fields only; Handoff schema v2 remains compatible.

## Collaboration coordination contract v1

`game_exp_capabilities` exposes `features.collaboration_coordination_v1=true`, the `collaboration_coordination` descriptor, read query `collaboration_context`, and protected operations `work.claim` / `work.release`.

A work claim is a coordination record, not lifecycle authority. It binds source-editing intent to the exact current canonical experiment branch SHA, trusted GitHub actor, executor identity, summary, and declared path scope.

Before editing, a Harness should call `game_exp_collaboration_context` with its observed source SHA when available. A stale SHA must be synchronized before a trusted work claim can commit. This prevents silent continuation from stale source across Harness changes.

Overlapping current work claims are returned as explicit `WORK_SCOPE_OVERLAP` conflicts with `blocking=false`. The protocol intentionally surfaces risk without implementing a static file lock. Hosts should coordinate or use isolated workspaces and merge/test. They must not report the overlap as resolved unless coordination actually occurred.

`COMPLETED` work release binds to the current canonical experiment branch head. `ABANDONED` releases without a result SHA. Work claims and releases do not approve Review, lifecycle promotion, selection, integration merge, or archive.

The protected collaboration projection is current execution state. Chat transcripts, local Harness memory, and Agent plans are non-authoritative context.

## Collaboration coordination contract v2

v2 is an additive coordination contract over the existing Ledger/Git authority model. It intentionally removes persistent Conflict objects from the proposed design.

`game_exp_capabilities` exposes `features.collaboration_coordination_v2=true` and `collaboration_coordination.protocol_version=2`.

### Freshness

`game_exp_collaboration_context` returns `as_of` plus action-relevant freshness dimensions.

Allowed freshness states are exactly:

- `CURRENT`
- `STALE`
- `UNKNOWN`
- `NOT_APPLICABLE`

Non-current results carry a reason code. `UNKNOWN` must never be collapsed into `CURRENT`. Lease/liveness is separate from freshness.

Legacy Work Claims without v2 lease/session metadata remain readable and use `UNKNOWN / LEGACY_RECORD` where applicability cannot be proved.

### Precise async execution preconditions

New async `execution.claim` operations require `preconditions.protocol_version=2`. Preconditions are action-specific and bind the exact identities the action depends on, including the experiment-state digest and, where relevant, source SHA, manifest digest, Candidate identity/source, Rehearsal identity, and main SHA.

The Trusted Writer re-resolves the live facts before committing the claim. Each asynchronous worker then reads the protected claim and rechecks the same facts before performing effects.

A global Ledger-head mismatch is treated as an observation mismatch, not by itself as a domain conflict. The Writer plans against the current Ledger; domain-specific preconditions decide whether the logical operation is stale. The protected Ledger ref still relies on normal non-fast-forward Git protection.

Candidate registration separately rejects a Candidate whose source SHA is no longer the canonical experiment branch head.

A legacy client that omits the required v2 async preconditions must receive a client-upgrade-required domain failure for these protected async operations rather than bypass the new checks.

### Work Claim v2 and leases

A Work Claim with a `session_id` is recorded as schema v2 and receives a Writer-observed timestamp plus a 24-hour lease. The lease exists only to suppress abandoned coordination noise; it grants no authority and says nothing about source freshness.

Expired claims remain historical records and are excluded from live overlap projection. v1 claims without lease/session remain readable with unknown lease state.

### Handoff

`game_exp_work_release` supports `HANDED_OFF`.

A handoff must be bound to the current pushed canonical experiment branch SHA and contains bounded lists for `done`, `remaining`, `known_failures`, `user_constraints`, and `open_questions`.

Handoff content is tagged `participant_reported`. It is not trusted evidence, may contain untrusted free text, and must never directly determine authority, validation PASS, lifecycle promotion, or protocol `next_actions`.

Unpushed local work is outside game-exp's recoverability guarantee.

### Derived overlap

`WORK_SCOPE_OVERLAP` remains a read projection with `blocking=false`. v2 exposes no `conflict.create` or `conflict.resolve` operation.

Hosts may enrich overlap/risk with Git-native facts such as actual changed paths, `git merge-tree`, hotspot files, and Git LFS locks for non-mergeable assets, but those remain derived coordination evidence rather than lifecycle authority.

### Mixed-version behavior

- New reader + old Ledger: missing v2 facts are returned as `UNKNOWN` / legacy reason codes.
- Old reader + new Ledger: append-only new records/fields must not change the meaning of existing lifecycle records. Compatibility must be verified by tests.
- Old client + new Writer: reads remain compatible; protected async mutations requiring v2 preconditions may fail with `DOMAIN_CLIENT_UPGRADE_REQUIRED`.
- New and old interfaces may query the same stable operation id, but no interface may weaken the v2 preconditions when resuming or retrying.

This contract does not add a lifecycle state, shared-memory service, CRDT layer, Agent swarm, second database, or general file lock.

