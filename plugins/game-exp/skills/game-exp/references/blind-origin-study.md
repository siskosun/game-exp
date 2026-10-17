# AI-only vs human-AI blind comparison (optional local sidecar)

Inspired by Conlon and Schwardmann (2026), https://arxiv.org/abs/2610.18921. This is an **observational preference pilot**, not a replication of incentivized willingness-to-pay, a causal estimate, or evidence that AI is superior.

The helper `scripts/blind_origin_study.py` works without a paid API. It does not modify protected Ledger records, lifecycle, Review PASS/FAIL, or selection. Keep Review strictly human-controlled.

## Preconditions and roles

Both variants must come from the same frozen gameplay brief and baseline, share an immutable Evaluation Profile, have independent fixed Candidate artifacts and verified shareable HTTPS playable URLs. Their trusted evaluation screening must be ELIGIBLE. An operator must verify every Candidate SHA/digest/Profile against the protected Ledger; the sidecar **checks consistency of operator-entered values, not their authenticity**.

Define `AI_ONLY` as the model designing and implementing without human creative iteration; `HUMAN_AI` permits human direction and edits. Both arms use the same model/toolchain and declared production time/model-call ceilings; record real consumption including human time. Source files, playable game metadata, game title and URL can unblind participants: audit them before recruitment.

H5 Game Prototype Agent and Godot Prototype Studio produce builds and independently test gameplay/browser interactions; game-exp freezes Candidate evidence. game-opportunity may cite aggregate observations, but its preregistered player-behavior signals remain separate. This sidecar introduces no new protected comparison schema.

## Local use

Create a private `plan.json` with `schema_version=1`, unique `study_id`, `brief_digest`, `baseline_digest`, `evaluation_profile_digest` (all sha256 digests), `resource_budget` (`model`, `max_minutes`, `max_model_calls`), `playtest` (`minimum_seconds_per_version`, `planned_min_responses`, `population`, `recruitment`, `limitations`), and exactly two `variants`. Each variant has `origin`, `candidate_id`, `source_sha`, `artifact_digest`, `baseline_digest`, `design_trace_digest`, `delivery_url`, `usage` (`model`, `minutes`, `model_calls`), and `evaluation` (`profile_digest`, `result_digest`, `screening=ELIGIBLE`, `source=TRUSTED_OBSERVED`). Never fabricate these fields for real tests.

```bash
python plugins/game-exp/skills/game-exp/scripts/blind_origin_study.py prepare --plan local/plan.json --private-dir local/private --public-dir exports/pages --sessions 20
python plugins/game-exp/skills/game-exp/scripts/blind_origin_study.py record --private-dir local/private --response local/votes/vote-SESSION.json
python plugins/game-exp/skills/game-exp/scripts/blind_origin_study.py report --private-dir local/private --public-dir exports/pages
```

The two output directories must not exist before preparation and must be separate. The optional `report --public-dir` recomputes SHA-256 for every exported page; if any page is missing or modified, report fails. Without `--public-dir`, `public_pages_verified=false` and there is **no display-file integrity claim**. Share **only** the generated `play-SESSION.html` pages; never expose the private `trial.json` mapping. Each page presents A first, then unlocks B via an explicit next-step button. This guides the randomized first-exposure order, but cannot independently verify which playable was actually opened first or for how long. The page downloads a JSON vote with no identifying user details. Participants should be adults with informed consent and should only be allocated one session. **Assign the generated session pages to participants without choosing by participant characteristics or preferred game origin.** The script generates balanced presentation slots; it does not randomize recruitment, enforce one unique human per session, or prove independent observations. Report counts are **session reports, not verified unique players**. The browser cannot verify actual playtime, and iframe display may be blocked by the game's hosting policy.

The private result distinguishes all recorded responses, paired-play self-reports (`paired_play_reports`) and users who did not report playing both (`not_played_both_reports`). **Only paired-play reports enter origin preference counts and the predeclared minimum sample threshold.** A respondent who has not played both may mark `INCONCLUSIVE`, but this is not a paired preference or eligible sample. The result also reports randomized presentation order, plan/assignment/response digests and limitations. With no observations the result is `NO_OBSERVED_PLAYER_PREFERENCES` with zero counts. The digests detect ordinary local drift, **not malicious tampering or true pre-registration**. Source attribution, profile eligibility and responses are operator/participant claims until independently checked.

For a **synthetic-only smoke test**, run the prepare and report commands with [the checked-in fake plan](../../../../../examples/blind-origin-synthetic-plan.json). Its Candidate, trusted-evaluation and game URLs are explicitly invented fixtures and MUST NOT be used with real participants, cited as evidence or imported into the protected Ledger.

No automatic promotion, rejection, Review outcome, commercial willingness-to-pay conclusion, significance test or population inference is produced.
