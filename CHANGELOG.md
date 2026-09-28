# Changelog

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
