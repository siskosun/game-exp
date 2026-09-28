# Evaluation Evidence v1

## Purpose

Evaluation Evidence v1 lets game-exp bind reproducible machine evidence and human incumbent/challenger observations to concrete Candidates without turning automated evaluation into lifecycle authority.

game-exp owns:

- Evaluation Profile identity and digest;
- Candidate/evidence identity and provenance;
- trusted observation boundaries;
- screening projection;
- human Review identity and optional blind A/B annotations.

The prototype executor (for example Godot Prototype Studio) owns project-specific scenarios, input/replay hooks and local variant exploration. game-exp does not become a game-playing engine.

## Keep the exploration thread serial

This contract does not change `exploration-thread.md`.

- Default to one active experiment for one exploration thread.
- Do not fan out 3-5 experiments just to create a comparison set.
- 2-4 implementation variants may be explored inside the prototype tool/executor when that remains within one experiment and brief.
- At the game-exp level, v1 comparison is **incumbent vs challenger**. The challenger Manifest identifies the incumbent with a `supersedes` relationship.
- No authoritative Comparison Set object is introduced.

## Evaluation Profile v1

Manifest schema v3 references one immutable/content-addressed Evaluation Profile:

```json
{
  "evaluation_profile": {
    "path": ".game-exp/evaluation-profiles/squad-choice-v1.json",
    "digest": "sha256:<64 lowercase hex>",
    "version": 1
  }
}
```

The referenced profile lives in the exact experiment source commit. The Candidate workflow fetches it from that commit and recomputes the canonical digest before running evaluation.

Profile v1 separates:

- `standing_requirements`: reusable project-level requirements such as launch, normal input, retry/recovery and no soft lock;
- `hypothesis_requirements`: requirements specific to the experiment hypothesis;
- `interface`: scenario/player goal plus seed/replay/snapshot policies.

Requirements describe outcomes/goals, not a hard-coded control sequence. For example, prefer “form a three-person squad and enter battle” over “click A, drag B, press C”.

The profile defines what counts as comparable evidence. Therefore the human-approved Manifest binding freezes its digest. Changing the profile requires a new Candidate/evaluation under the changed contract; do not edit the evaluator merely to improve a score.

## Project policy v3

Project policy schema v3 adds one protected command:

```json
{
  "evaluation": {
    "argv": ["python", ".game-exp/evaluate.py"],
    "output_dir": ".game-exp/evaluation-output"
  }
}
```

The evaluation argv must execute a runner from `control/.game-exp/evaluation/`. That directory is checked out from the same protected workflow source commit as the project policy, not from the challenger experiment branch. The runner may invoke the Candidate build and project QA hooks, but the experiment cannot rewrite the evaluator itself.

The fixed output directory is deliberate.

Before invoking the evaluation command the trusted Candidate workflow removes that directory. The project command then creates fresh output for the exact Candidate source. This prevents a committed prewritten result file from being accepted merely because it exists.

The command runs on the trusted Ubuntu Candidate workflow. Non-Node adapters must provision everything they need through their declared install command; game-exp does not install Godot or learn project-specific controls.

Project policy v1/v2 remains supported. Those repositories continue using Manifest schema v1/v2 and have no Evaluation Evidence v1 requirement.

## Trusted evaluation bundle

When Evaluation Profile is enabled, the project evaluation command writes:

`.game-exp/evaluation-output/result.json`

plus any referenced logs/snapshots/traces/captures.

The build job packages this directory as `evaluation-output.tgz`.

A separate trusted observation job:

1. has no experiment source checkout;
2. downloads the evaluation bundle;
3. fetches the Profile from the exact Candidate source SHA;
4. recomputes the Profile digest;
5. safely extracts the bundle;
6. validates `result.json`;
7. recomputes every referenced evidence digest;
8. derives the tri-state screening result.

Only that observation produces `TRUSTED_OBSERVED` evaluation evidence.

The immutable Candidate release retains:

- `candidate.tgz`;
- `evaluation-output.tgz` when enabled;
- `evaluation-summary.json` when enabled.

Ledger stores the compact summary/digests, not video or large evidence bytes.

## Result contract

A trusted project result is bound to:

- Profile digest;
- Candidate source SHA;
- run mode (`TRUSTED_REPLAY` or `TRUSTED_CHECK`);
- optional replay-trace digest;
- actual stepping mode;
- per-requirement outcomes and evidence digests.

Per-requirement outcome:

- `PASS`;
- `FAIL_PRODUCT_DEFECT`;
- `INCONCLUSIVE`.

Classification distinguishes product, test harness, environment, design risk and uncertainty.

Agent/player exploration is not accepted through this trusted result path. An exploratory Agent may discover a candidate failing trace, but the trace must be independently replayed/observed by the trusted Candidate workflow before the runtime fact becomes `TRUSTED_OBSERVED`.

## Three-state screening

The Candidate projection derives:

- `ELIGIBLE`: every required Profile requirement is trusted PASS;
- `INELIGIBLE`: at least one required requirement is trusted `FAIL_PRODUCT_DEFECT`;
- `INCONCLUSIVE`: a required requirement lacks conclusive trusted product evidence.

Screening is evidence only.

It must never automatically emit Review FAIL, REJECTED, PROMISING, SELECTED or any lifecycle mutation.

An Agent failing to discover a path does not prove a product defect. When a trusted replay proves the path is reachable, such a finding may remain a discoverability/design-risk observation rather than a failed product requirement.

## Incumbent vs challenger

v1 avoids an authoritative N-way comparison object.

A challenger Manifest uses:

```json
{"type":"supersedes","experiment_id":"EXP-<incumbent>"}
```

When the declared Review protocol is `incumbent-challenger-blind-ab-v1`, the human Review may carry a structured `comparison`.

The comparison binds:

- incumbent current Candidate and artifact digest;
- challenger current Candidate and artifact digest;
- one shared Evaluation Profile digest already present on both Candidates;
- `blind=true`;
- presentation order;
- per-dimension human choice;
- optional overall human choice.

Choices are:

- `INCUMBENT`;
- `CHALLENGER`;
- `NO_CLEAR_DIFFERENCE`;
- `INCONCLUSIVE`.

The record source is `HUMAN_REPORTED`. It is stored inside the Review record and therefore uses the same Trusted Writer-verified human identity.

Human comparison does not itself choose the Review outcome. The user still explicitly supplies Review PASS/FAIL.

A comparison-driven negative conclusion should normally be represented by an explicit human FAIL Review / REJECTED decision as appropriate. `ABANDONED` remains for stopping work without asserting an evaluative failure.

## Small candidate comparison

For 2-4 variants, do not add Elo/Bradley-Terry solely for ranking convenience.

Prefer:

- per-dimension pairwise choice;
- A/B presentation order;
- whether reversed order changes the conclusion;
- agreement/disagreement across evaluators;
- trusted finite metric dominance where a project-specific tool already supports it.

Do not present a tiny dependent sample as a score such as “6:4”. `NO_CLEAR_DIFFERENCE` is a first-class result.

## Evidence provenance

Keep these sources distinct:

- `TRUSTED_OBSERVED`: trusted workflow observed and bound the result;
- `PARTICIPANT_REPORTED`: Agent/player/VLM report or exploratory evidence;
- `HUMAN_REPORTED`: real human observation/preference tied to exact artifacts.

Neither `PARTICIPANT_REPORTED` nor `HUMAN_REPORTED` is converted into a trusted machine PASS merely by being written through Trusted Writer. Trusted Writer proves identity/authorized recording; it does not prove the content of a subjective report.

## Board and panel projection

Board may derive, from Candidate + Review + `supersedes`:

- Candidate evaluation Profile digest;
- `eligible_for_human_comparison`: `ELIGIBLE | INELIGIBLE | INCONCLUSIVE | UNKNOWN`;
- Chinese screening summary;
- incumbent/challenger identities;
- current human blind A/B comparison when recorded.

This is a read-only projection. It is not a Comparison Set domain object.

## Human gate preservation

Evaluation Evidence v1 never changes these rules:

- Candidate trusted checks do not authorize Review PASS/FAIL;
- `ELIGIBLE` does not authorize PROMISING;
- machine dominance does not authorize REJECTED;
- human pairwise preference does not authorize SELECTED;
- SELECTED remains the explicit human choice for integration after PROMISING and fresh Rehearsal requirements.
