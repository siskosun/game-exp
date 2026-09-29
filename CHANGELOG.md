# Changelog

## 1.0.0 maintenance fix - 2026-09-29

- Project iteration delivery cards into the default `game_exp_board.experiments[]` response so ordinary 1.0 MCP users do not need the optional advanced experiment-panel tool.
- Keep `experiment_panel.delivery_card` as the same secondary projection rather than a separate data path.

- Add iteration delivery card v1 without changing the game-exp lifecycle or version number.
- Allow COMPLETED/HANDED_OFF `work.release` to carry bounded participant-reported `delivery` evidence: player-visible changes, verified playable descriptor, focus points, producer/build id and optional prior Candidate.
- Project `experiment_panel.delivery_card` with one immediate playable/download action, previous-version context, focus points and fixed Chinese quick intents.
- Keep quick intents non-authoritative: `保留这版` is no-op retention, Review PASS requires an explicit statement about the exact current Candidate, and selection still requires fresh Rehearsal.
- Fall back to trusted immutable Candidate retention when no direct playable entry exists; otherwise show `试玩入口未生成` rather than inventing a URL.

- Add local `game_exp_project_create` / CLI `project-create` for a brand-new Godot or H5 prototype when no repository exists.
- Default new repositories to private; require explicit public visibility and never publish automatically to bypass Ruleset-plan limits.
- Seed from the latest semantic-version-tagged GPS/H5 starter, install game-exp/project policy, push `main`, then run the existing project-init/Doctor path.
- Refuse existing local directories or GitHub repositories instead of overwriting them.
- Preserve a repository created before a later setup/push blocker and return an explicit resume action rather than deleting/recreating it.
- Keep first-experiment creation separate: after `PROJECT_READY`, onboarding continues from the user's original prototype goal without asking them to repeat it.

- Keep the game-exp version at `1.0.0`.
- Make `--check` compare a deterministic managed-runtime digest plus required installed entrypoints/configuration, so older maintenance builds with the same version string no longer report `CURRENT`.
- Store the managed-runtime digest in install provenance and normalize line endings before hashing for Windows/macOS/Linux consistency.
- Wrap game-exp runtime, Skill, MCP config, GPS and H5 managed targets in an install rollback transaction so a later failure does not leave a partial managed upgrade.
- Replace the stale client E2E `experiment.create` request with a stable `experiment.bind` canary contract, explicit applied-domain assertions, exact replay checks, and an explicit human GitHub E2E credential requirement.
- Add regression tests for incomplete same-version installs, digest drift, partial companion failure rollback, late game-exp failure rollback, and E2E operation drift.

## 1.0.0 maintenance fix - 2026-09-28

- Keep the game-exp version at `1.0.0`.
- When installing or upgrading one Harness, also fetch the latest semantic-version tags of `godot-prototype-studio` and `h5-game-prototype-agent` from their canonical GitHub repositories and install their runtime Skill files into the same Harness only.
- Preserve Harness isolation: a Codex upgrade does not modify Cursor/Qoder; `--harness all` remains explicit.
- Reject unversioned companion sources and tag/VERSION mismatches.
- Filter companion installs to runtime Skill content so tests, CI, audit/dev files, `node_modules`, evidence folders, and temporary outputs do not leak into Skill directories.
- Extend prototype handoff guidance to route Godot work to GPS and H5/browser work to H5 Game Prototype Agent without changing game-exp lifecycle authority.


## 1.0.0 - 2026-09-28

### Trust boundary
- Move `GAME_EXP_WRITER_KEY` from repository secrets to the main-only `game-exp-trusted-writer` Environment.
- Split repository protection so deletion/non-fast-forward/immutable-ref rules cannot be bypassed by the writer key.
- Add explicit `single-principal` and `multi-principal` trust modes; multi-principal main requires independent approval.
- Make Doctor validate Ruleset semantics, writer-secret scope, Environment branch policy, and independently inferred trust mode.
- Reject unsupported domain operation names instead of committing request-only records.
- Require an explicit Candidate id for human Review.
- Split GitHub Bridge validation from privileged execution and prefilter Issue-comment authors before the writer key is available.
- Pin production GitHub Actions to immutable commit SHAs and maintain them with Dependabot.

### Performance and resilience
- Load each immutable Ledger snapshot with one tree read plus batched GraphQL blob reads.
- Cache snapshot indexes by Ledger commit SHA and content by blob SHA.
- Reuse one pinned snapshot across Board, focused panels, handoff, and notifications.
- Retry idempotent GitHub reads with bounded backoff; unresolved transport failures return retryable `UNKNOWN`.
- Shallow-clone only the current Ledger head in Trusted Writer.

### Agent and user experience
- Use `game_exp_status` as the compact repository/access/version/protocol handshake.
- Require explicit repository identity for global MCP use.
- Keep conformance and compatibility tools out of the default MCP registration unless explicitly enabled.
- Reduce the Skill entrypoint to a routing page; load detailed references only for the active task.
- Add non-authoritative `surface_hint`: normal progress stays compact; human-action/recovery states may surface the relevant local panel.
- Preserve the full Board as an explicit user navigation surface rather than opening it after every implementation pass.
- Keep Chinese Board copy semantic and context-specific.

### Evaluation and collaboration retained from 0.21
- Evaluation Profile v1 and trusted evaluation against frozen Candidate bytes.
- `ELIGIBLE / INELIGIBLE / INCONCLUSIVE` screening without automatic lifecycle mutation.
- Incumbent/challenger human blind A/B evidence without Elo.
- Work Claim/Release, continuation context, exact freshness/precondition checks, and stable operation recovery.
- Human Review, PROMISING, SELECTED, integration merge, and archive-choice gates remain human-owned.

### Release engineering
- Pin the MCP SDK to an exact version.
- Add a local pre-merge gate and strengthen distribution checks.
- Align repository/runtime version markers and expose mismatch guidance through status.
- Separate release history into this changelog.

### Deliberately deferred after 1.0
These are maintenance refactors, not release blockers:
- split the large client module into transport/snapshot/projection/presentation/recovery packages;
- consolidate duplicated GitHub HTTP helpers;
- raise Actions-side coverage incrementally;
- evaluate reusable workflows for consumer repositories;
- add larger-N ranking only if real usage outgrows incumbent/challenger comparison.
