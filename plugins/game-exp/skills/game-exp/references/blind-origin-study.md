# AI-only vs human-AI blind comparison (optional local sidecar)

Inspired by Conlon and Schwardmann (2026), https://arxiv.org/abs/2610.18921. This is an **observational preference pilot**, not a replication of incentivized willingness-to-pay, a causal estimate, or evidence that AI is superior.

The helper `scripts/blind_origin_study.py` works without a paid API. It does not modify protected Ledger records, lifecycle, Review PASS/FAIL, or selection. Keep Review strictly human-controlled.

## Preconditions and roles

Both variants must come from the same frozen gameplay brief and baseline, share an immutable Evaluation Profile, have independent fixed Candidate artifacts and verified shareable HTTPS playable URLs. Their trusted evaluation screening must be ELIGIBLE. An operator must verify every Candidate SHA/digest/Profile against the protected Ledger; the sidecar **checks consistency of operator-entered values, not their authenticity**.

Define `AI_ONLY` as the model designing and implementing without human creative iteration; `HUMAN_AI` permits human direction and edits. Both arms use the same model/toolchain and declared production time/model-call ceilings; record real consumption including human time. Source files, playable game metadata, game title and URL can unblind participants: audit them before recruitment.

H5 Game Prototype Agent and Godot Prototype Studio produce builds and independently test gameplay/browser interactions; game-exp freezes Candidate evidence. game-opportunity may cite aggregate observations, but its preregistered player-behavior signals remain separate. This sidecar introduces no new protected comparison schema.

## Define the scientific question before generating a pair

This minimal tool assesses preference for **two fixed outputs made under declared workflows**. One AI-only game versus one human-AI game cannot establish an average human contribution across games, nor a causal effect of human creativity if the workflows also differ in coding, assets, test effort or implementation quality.

Choose and freeze the comparison unit **before** authoring:

- **Production workflow comparison (default):** supply an identical frozen brief, starter/template, asset access, technology, engine/model version, evaluator Profile, budget ceiling and allowed iteration window to both producers. Human creative interventions are permitted only in HUMAN_AI, while AI_ONLY may use the same declared budget for autonomous revision. Log prompts, actual model calls, elapsed production effort and substantive design changes separately. The output is a within-brief *workflow* comparison, not proof of a pure design effect.
- **Human design-edit increment (alternative):** begin from one frozen AI design and common implementation baseline. Permit a documented human creative change in HUMAN_AI, and a resource-matched autonomous change in AI_ONLY; build both with the same implementation pipeline. This narrows implementation differences but still estimates only this particular comparison.

The `usage.minutes` field is operator-declared production effort, **not** proof that human and AI costs are equal. Include active human design/edit time and separately retain generation/retry logs outside the protected Ledger. Record actual budget differences; do not conceal unequal resources by noting only identical ceilings.

Freeze the primary endpoint as one adult participant's overall **anonymous, paired playtest choice** (including `NO_CLEAR_DIFFERENCE` and `INCONCLUSIVE`). Randomly assign available session pages without selecting orders based on testers; keep each person to one session using a separately managed eligibility roster rather than claiming this script verifies uniqueness. Finish recruitment and playback before unblinding the private source mapping. Do not revise Candidate artifacts after responses begin. Independently inspect both playable pages for author names, model logos, URL/title clues, broken embeds and materially different playtest instructions. Report recruitment, exposure and attrition limitations even if every technical check passes.

## Local use

Create a private `plan.json` with `schema_version=1`, unique `study_id`, `brief_digest`, `baseline_digest`, `evaluation_profile_digest` (all sha256 digests), `resource_budget` (`model`, `max_minutes`, `max_model_calls`), `playtest` (`minimum_seconds_per_version`, `planned_min_responses`, `population`, `recruitment`, `limitations`), and exactly two `variants`. Each variant has `origin`, `candidate_id`, `source_sha`, `artifact_digest`, `baseline_digest`, `design_trace_digest`, `delivery_url`, `usage` (`model`, `minutes`, `model_calls`), and `evaluation` (`profile_digest`, `result_digest`, `screening=ELIGIBLE`, `source=TRUSTED_OBSERVED`). Never fabricate these fields for real tests.

```bash
python plugins/game-exp/skills/game-exp/scripts/blind_origin_study.py prepare --plan local/plan.json --private-dir local/private --public-dir exports/pages --sessions 20
python plugins/game-exp/skills/game-exp/scripts/blind_origin_study.py record --private-dir local/private --response local/votes/vote-SESSION.json
python plugins/game-exp/skills/game-exp/scripts/blind_origin_study.py report --private-dir local/private --public-dir exports/pages
```

The two output directories must not exist before preparation and must be separate. The optional `report --public-dir` recomputes SHA-256 for every exported page; if any page is missing or modified, report fails. Without `--public-dir`, `public_pages_verified=false` and there is **no display-file integrity claim**. Share **only** the generated `play-SESSION.html` pages; never expose the private `trial.json` mapping. Each page presents A first, then unlocks B via an explicit next-step button. This guides the randomized first-exposure order, but cannot independently verify which playable was actually opened first or for how long. The page downloads a JSON vote with no identifying user details. Participants should be adults with informed consent and should only be allocated one session. **Assign the generated session pages to participants without choosing by participant characteristics or preferred game origin.** The script generates balanced presentation slots; it does not randomize recruitment, enforce one unique human per session, or prove independent observations. Report counts are **session reports, not verified unique players**. Output field `measurement_unit=session_reports_not_verified_unique_players` makes this explicit. Do **not** feed these counts directly into game-opportunity's `unique_players` validation metrics without separate eligible-player deduplication and evidence verification. The browser cannot verify actual playtime, and iframe display may be blocked by the game's hosting policy.

## Client-side assignment commitments

New exported pages include opaque `plan_commitment` and `session_commitment` values in their downloaded votes. They commit to the frozen plan and exact A/B artifact order without disclosing design origin or Candidate IDs. The `record` command compares both against the private plan/assignment map and rejects a changed plan, wrong session, or only one supplied commitment. These hashes detect accidental cross-plan/cross-session imports; **they do not authenticate a player or protect against an operator changing all local files together**.

Older five-field votes remain accepted for compatibility but are explicitly marked `LEGACY_NO_CLIENT_COMMITMENT`, while newly bound votes are marked `MATCHED_UNTRUSTED`. The report includes separate `client_commitment_matched_reports` and `legacy_without_client_commitment_reports` counts. Do not present legacy votes as though their downloaded page had been cryptographically bound to the private assignment.

The private result distinguishes all recorded responses, paired-play self-reports (`paired_play_reports`) and users who did not report playing both (`not_played_both_reports`). **Only paired-play reports enter origin preference counts and the predeclared minimum sample threshold.** A respondent who has not played both may mark `INCONCLUSIVE`, but this is not a paired preference or eligible sample. The result also reports randomized presentation order, plan/assignment/response digests and limitations. With no observations the result is `NO_OBSERVED_PLAYER_PREFERENCES` with zero counts. The digests detect ordinary local drift, **not malicious tampering or true pre-registration**. Source attribution, profile eligibility and responses are operator/participant claims until independently checked.

For a **synthetic-only smoke test**, run the prepare and report commands with [the checked-in fake plan](../../../../../examples/blind-origin-synthetic-plan.json). Its Candidate, trusted-evaluation and game URLs are explicitly invented fixtures and MUST NOT be used with real participants, cited as evidence or imported into the protected Ledger.


## Repeatable browser smoke test (no real players)

The PR adds `tools/game-exp/tests/test_blind_origin_browser.py`, run in GitHub Actions by `.github/workflows/game-exp-blind-origin-browser.yml`. It hosts two neutral fake games and the A/B pages on temporary **different-port HTTPS servers with a self-signed test certificate**, then uses Chromium to exercise both desktop and mobile flows, iframe gameplay, JSON download, CLI import, reverse mapping and tamper refusal. The browser test creates only **synthetic** participant responses and keeps them in a temporary directory; they are not real player results or Ledger evidence.

For optional local execution on a machine with Python, OpenSSL and compatible Chromium (from the game-exp repository root):

```bash
python -m pip install playwright==1.55.0
python -m playwright install chromium
GAME_EXP_BROWSER_E2E=1 python -m unittest tools/game-exp/tests/test_blind_origin_browser.py -v
```

This shell syntax is for Bash; on PowerShell, first set `$env:GAME_EXP_BROWSER_E2E='1'` and then run the Python unittest command. The test explicitly ignores its **own local self-signed certificate errors only**. Success does not verify production HTTPS certificates, external game URLs, participant independence or actual creative origin.

No automatic promotion, rejection, Review outcome, commercial willingness-to-pay conclusion, significance test or population inference is produced.
