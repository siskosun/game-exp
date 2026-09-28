# game-exp -> Godot Prototype Studio handoff

## Boundary

game-exp owns experiment identity, scope, lifecycle, evidence references, human gates and selection.

Godot Prototype Studio owns prototype implementation, runtime verification, export, and requested playable delivery.

game-exp must not rebuild Godot editing/export/publishing capabilities.


## Optional executor capability

Godot Prototype Studio is the recommended specialized executor, not a game-exp dependency.

Canonical source:

`https://github.com/siskosun/godot-prototype-studio`

Before Godot implementation begins, the host should check its own available Skill/tool catalog for `godot-prototype-studio`.

- Installed/available: prefer it for implementation, runtime verification, export, and requested playable delivery.
- Missing: show one non-blocking installation suggestion with the canonical source URL, explicitly say installation is optional, and continue with ordinary host source-editing capability unless the user chooses to install first.
- Missing capability never changes experiment health, repository readiness, lifecycle, or trusted Ledger state.
- The host must not infer installation from repository files; only the host knows which Skills/tools it can invoke.
- Fallback implementation evidence is truthful-by-construction: report only checks, Godot runs, exports, and playable delivery that actually occurred.

The handoff exposes this policy in `recommended_executor` so different Harnesses can render the same guidance without hard-coding their own repository URL or dependency semantics.

## Handoff schema v2

Use `game_exp_prototype_handoff(experiment_id)`.

The package is bound to:

- protected Ledger snapshot;
- stable `handoff_id`;
- canonical experiment branch;
- observed branch-head SHA when available;
- parent SHA;
- subject/prototype root;
- title and hypothesis;
- success/kill criteria;
- allowed/avoided scope;
- runtime requirements;
- Review protocol.

Pass this package to Godot Prototype Studio when implementation or playable delivery is needed.

## Return evidence

The implementation return must identify:

- exact `source_sha`;
- `build_identity`: build id, source SHA, producer, and originating handoff id;
- checks actually run;
- check environment;
- playable status;
- evidence scope;
- artifacts;
- delivery evidence only when delivery was requested.

Each artifact requires an id, kind, location, digest and `portable` flag.

A local filesystem path may be valid in one Harness but is not durable cross-Harness evidence. If an artifact exists only locally, mark `portable=false`. Evidence intended to survive machine/Harness switching should use a durable accessible location plus digest.

Checks must state the source SHA and environment they validate. A check result for an older source SHA does not automatically validate later code.

These implementation/runtime facts never authorize Review PASS, PROMISING, SELECTED, merge or Archive. game-exp resumes the normal Candidate/Review lifecycle after evidence is available.

## Future A2A

If Godot Prototype Studio later becomes an independent Agent, this task/evidence package may be transported as an A2A task/artifact set. A2A transport must not redefine game-exp idempotency, human approval scope, or evidence validity.
