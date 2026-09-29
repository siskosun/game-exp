# game-exp prototype executor handoff

## Boundary

game-exp owns experiment identity, scope, lifecycle, evidence references, human gates, Candidate identity, selection, integration and archive state.

Specialized prototype Skills own implementation and implementation evidence:

- **Godot** -> Godot Prototype Studio (`godot-prototype-studio`)
- **H5/browser** -> H5 Game Prototype Agent (`h5-game-prototype-agent`)

game-exp must not rebuild either executor's editing, runtime verification, browser/export, replay, or playtest-preparation workflow.

Automated executor evidence never authorizes Review PASS/FAIL, PROMISING, SELECTED, REJECTED, merge, or Archive choices. Candidate/Review authority remains in game-exp.

## Companion Skill availability

Canonical sources:

- GPS: `https://github.com/siskosun/godot-prototype-studio`
- H5: `https://github.com/siskosun/h5-game-prototype-agent`

The canonical game-exp Harness installer synchronizes the latest semantic-version-tagged releases of both Skills into the Harness being installed or upgraded.

This is a Harness convenience, not a lifecycle dependency:

- missing executor capability does not change repository health, `PROJECT_READY`, or Ledger state;
- a host may still have been installed manually or may be unable to reach GitHub;
- the host must confirm which Skills/tools are actually available before invoking them;
- if a specialized Skill is unavailable, report the capability gap rather than inventing its evidence.

## Executor routing

Use the technology already selected by the user/project.

### Godot subject

Prefer `godot-prototype-studio`.

Pass:

- player-experience goal;
- experiment id and current lifecycle;
- stable subject id/name/root path;
- canonical experiment branch;
- success/kill criteria;
- allowed/avoided scope;
- current Candidate id when one exists;
- requested delivery target;
- evidence already known.

GPS may resolve local implementation variants inside delegated authority. It must not choose between game-exp Candidates or cross-experiment branches.

### H5/browser subject

Prefer `h5-game-prototype-agent`.

Choose its task mode from the work being handed off:

- **PROBE** when the question is whether one mechanic/hypothesis deserves further investment;
- **SLICE** when the experiment already requires a more complete playable implementation or delivery.

For PROBE, pass the experiment goal and constraints, but keep the probe card local to H5 execution. Machine outcomes such as `READY_FOR_PLAYTEST`, `MACHINE_REJECT`, or `UNCERTAIN` remain implementation evidence only.

Do not translate `READY_FOR_PLAYTEST` into game-exp Review PASS or PROMISING. A human still decides whether the experiment advances.

## H5 repository-root build constraint

Current game-exp Candidate/Rehearsal project-policy commands run from the **repository root**. `subject.root_path` identifies the subject but does not automatically become the build working directory.

Therefore, when an H5 workspace contains several nested probes:

1. use H5 locally to explore/filter them;
2. when one probe is chosen for game-exp promotion, default to placing that selected probe in its own repository before Bind/Initialize;
3. alternatively, keep a multi-probe repository only if its repository-root install/test/build commands intentionally route to the selected subject.

Do not claim that setting `subject.root_path` alone gives per-subdirectory Candidate builds.

## Handoff schema v2

Handoff schema v2 remains the stable cross-interface contract. Use `game_exp_prototype_handoff(experiment_id)` when available.

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

Pass the same authoritative package to the selected executor. Executor-specific local briefs/cards refine implementation but must not override game-exp scope or lifecycle authority.

## Return evidence

Implementation return should identify:

- exact `source_sha`;
- `build_identity`: build id/digest, source SHA, producer, and originating handoff id when available;
- checks actually run;
- check environment;
- normal player-input reachability where relevant;
- playable/browser/export status;
- evidence scope;
- artifacts;
- delivery evidence only when delivery was requested.

For H5 PROBE evidence also preserve when available:

- frozen probe-card digest;
- browser/version/viewport;
- input-source provenance (`PLAYER`, `INJECTED`, `EMULATED_TOUCH`);
- degenerate-strategy checks;
- `agent_verdict`;
- human verdict separately, never synthesized.

Each artifact requires an id, kind, location, digest when available, and portability status.

A local filesystem path may be valid in one Harness but is not durable cross-Harness evidence. If an artifact exists only locally, mark it non-portable. Evidence intended to survive machine/Harness switching should use a durable accessible location plus digest.

Checks must state the source SHA/build identity they validate. Evidence for an older artifact does not automatically validate later code.

## Resume game-exp

After implementation evidence is returned:

1. refresh authoritative experiment state;
2. ensure evidence matches the current source/Candidate identity;
3. move to REVIEW/build Candidate only when the implementation is actually ready;
4. present machine evidence and playable artifact to the human;
5. record human Review only after an explicit human outcome;
6. preserve normal PROMISING -> Rehearsal -> SELECTED -> Integration gates.

Specialized executor automation stops at evidence. game-exp remains the authority for experiment advancement.

## Playtest delivery ownership

game-exp does not host or publish playable builds. The specialized executor owns the requested playable delivery. For external testers, prefer a verified `SHAREABLE_URL`; a localhost/LAN URL or retained `candidate.tgz` is not a substitute for a cross-device link. On public repositories the handoff sets `delivery_request.prefer_shareable_url=true` and recommends immutable GitHub Pages paths keyed by the exact `result_source_sha`. GPS/H5 may use their bundled publisher, but must verify both deployment identity and the real browser/player path before returning `verified=true`.

Each published build should remain at a stable path such as `play/<result_source_sha>/`. That lets the Board recover an older playable by matching `previous_candidate.source_sha` to historical `work.release.delivery.playable` records. If no verified historical shareable exists, the Board falls back to the retained Candidate artifact.

If a completed iteration returns `LOCAL_URL`, `ARTIFACT_ONLY`, or `MISSING` and external testing is needed, the next action is to ask the executor to publish a shareable build and persist that URL through `work.release.delivery.playable`.
