# GitHub Bridge command reference

## Contents

- Envelope and placement
- Result markers and reconciliation
- Read action
- Lifecycle actions
- Archive actions

## Envelope and placement

Post the command as a top-level comment on the canonical experiment Issue. The Issue number must equal the numeric part of the experiment id.

Use exactly:

~~~text
/game-exp
{"schema_version":1,"request_id":"req_example","action":"status","experiment_id":"EXP-42"}
~~~

Rules:

- Use schema version 1.
- Use one stable request id per logical action.
- Do not include unknown keys.
- Do not put actor identity, tokens, secrets, or repository credentials in the JSON.
- For `bind`, `request_id` must equal `manifest.operation_id`.
- New manifests should include stable `subject`; old manifests without it remain valid for compatibility.
- New manifests may include `relationships` to existing valid bound experiments using only `depends_on`, `blocks`, or `supersedes`.
- Human-gated commands may be posted only after the user explicitly made that decision.

## Result markers and reconciliation

The bridge posts:

- `<!-- game-exp-bridge:<request_id>:claim -->` before execution.
- `<!-- game-exp-bridge:<request_id>:result -->` after execution.

If a result marker exists, use that result and refresh the protected Ledger.

If a claim exists without a result, treat the bridge request as `UNKNOWN`. Inspect the bridge Actions run linked in the claim and refresh the protected Ledger. Do not post another command or create a new request id until the original outcome is resolved.

For async actions (`initialize`, `candidate_build`, `rehearse`, `integrate`, `integrate_finalize`, `archive`), the Bridge first commits the same protected `execution.claim` used by MCP/CLI. The worker then receives the identical request id and refuses to run unless action, experiment, arguments and trusted actor match that claim.

If the execution claim committed but worker dispatch cannot be proven, the Bridge result is `UNKNOWN`, not `REJECTED`. Recover/query that same request id; never submit a replacement command.

## Read action

### status

~~~json
{"schema_version":1,"request_id":"req_status_42","action":"status","experiment_id":"EXP-42"}
~~~

## Lifecycle actions

### bind

~~~json
{"schema_version":1,"request_id":"req_bind_42","action":"bind","manifest":{"schema_version":1,"experiment":{"host":"github.com","repository_id":"...","issue_id":"...","issue_number":"42"},"title":"...","subject":{"type":"game-prototype","id":"example-game","name":"Example Game","root_path":"games/example-game"},"relationships":[{"type":"depends_on","experiment_id":"EXP-41"}],"operation_id":"req_bind_42","parent":{"experiment":null,"commit":"..."},"hypothesis":"...","success_criteria":["..."],"kill_criteria":["..."],"scope":{"allowed":["games/example/**"],"avoid":[".github/**","tools/game-exp/**","plugins/**",".game-exp/**"]},"runtime":{"godot":"...","export_templates":"...","addons_lock":"..."},"review":{"protocol":"blind-playtest-v1"},"created_at":"..."}}
~~~

### initialize

~~~json
{"schema_version":1,"request_id":"req_initialize_42","action":"initialize","experiment_id":"EXP-42"}
~~~

### candidate_build

~~~json
{"schema_version":1,"request_id":"req_candidate_42_1","action":"candidate_build","experiment_id":"EXP-42"}
~~~

### work_claim

Declare source-editing intent before changing the canonical experiment branch:

~~~json
{"schema_version":1,"request_id":"req_work_42_1","action":"work_claim","experiment_id":"EXP-42","base_source_sha":"<40-char-current-exp-branch-sha>","summary":"Tune movement feel","paths":["games/player"],"executor":{"harness":"codex","agent":"gpt","session_id":"optional-session"}}
~~~

The Trusted Writer verifies that `base_source_sha` is still the current canonical experiment branch head. Overlap with another current work claim is recorded as a coordination signal; it is not a hard lock.

### work_release

After the work is represented by the canonical experiment branch:

~~~json
{"schema_version":1,"request_id":"req_work_release_42_1","action":"work_release","experiment_id":"EXP-42","claim_id":"req_work_42_1","outcome":"COMPLETED","notes":"Merged and verified.","result_source_sha":"<40-char-current-exp-branch-sha>"}
~~~

To drop work without a result:

~~~json
{"schema_version":1,"request_id":"req_work_release_42_2","action":"work_release","experiment_id":"EXP-42","claim_id":"req_work_42_1","outcome":"ABANDONED","notes":"Superseded by another implementation.","result_source_sha":null}
~~~

Work claims/releases are coordination records, not lifecycle decisions or human approvals.

### review_record

~~~json
{"schema_version":1,"request_id":"req_review_42_1","action":"review_record","experiment_id":"EXP-42","candidate_id":"C-42-...","outcome":"PASS","notes":"Human review notes."}
~~~

`outcome` is `PASS` or `FAIL`.

For Manifest review protocol `incumbent-challenger-blind-ab-v1`, the command may add one optional `comparison` object. It must bind the current incumbent Candidate of the challenger's `supersedes` relationship, both artifact identities, the shared Evaluation Profile digest, `blind=true`, presentation order, dimension choices, and optional overall choice.

~~~json
{"schema_version":1,"request_id":"req_review_42_2","action":"review_record","experiment_id":"EXP-42","candidate_id":"C-42-...","outcome":"PASS","notes":"Human explicitly approved continuing the challenger.","comparison":{"incumbent_experiment_id":"EXP-41","incumbent_candidate_id":"C-41-...","incumbent_artifact_digest":"sha256:<64hex>","profile_digest":"sha256:<64hex>","blind":true,"presentation_order":"CHALLENGER_INCUMBENT","dimensions":[{"id":"mechanic_clarity","choice":"CHALLENGER","notes":"The consequence was easier to understand."}],"overall":"NO_CLEAR_DIFFERENCE"}}
~~~

Comparison choices are `INCUMBENT`, `CHALLENGER`, `NO_CLEAR_DIFFERENCE`, or `INCONCLUSIVE`. The comparison is `HUMAN_REPORTED` evidence and does not replace the explicit Review outcome.

### decision_submit

~~~json
{"schema_version":1,"request_id":"req_decision_42_promising","action":"decision_submit","experiment_id":"EXP-42","to_state":"PROMISING","reason":"Human-approved promotion after Review PASS.","previous_decision_id":"req_previous_or_null"}
~~~

Use the current protected `last_decision_id`. JSON `null` is allowed when the authoritative state has no previous decision.

To explicitly stop an experiment without claiming a failed Review, submit `ABANDONED`:

~~~json
{"schema_version":1,"request_id":"req_abandon_42","action":"decision_submit","experiment_id":"EXP-42","to_state":"ABANDONED","reason":"Human chose to stop this experiment for product/resource reasons.","previous_decision_id":"req_previous_or_null"}
~~~

Do not create a synthetic `review_record FAIL` for abandonment. Closing the Issue alone is not a lifecycle mutation.

### rehearse

~~~json
{"schema_version":1,"request_id":"req_rehearse_42_1","action":"rehearse","experiment_id":"EXP-42"}
~~~

### integrate

~~~json
{"schema_version":1,"request_id":"req_integrate_42_1","action":"integrate","experiment_id":"EXP-42"}
~~~

### integrate_finalize

~~~json
{"schema_version":1,"request_id":"req_integrate_finalize_42_52","action":"integrate_finalize","experiment_id":"EXP-42","pr_number":"52"}
~~~

Run only after the Integration PR is actually merged.

## Archive actions

### archive

~~~json
{"schema_version":1,"request_id":"req_archive_42_1","action":"archive","experiment_id":"EXP-42","mode":"ATOMIC_DELETE"}
~~~

`mode` is `ATOMIC_DELETE` or `RETAIN_BRANCH`. Do not choose the mode on the user's behalf.

### archive_abort

~~~json
{"schema_version":1,"request_id":"req_archive_abort_42_1","action":"archive_abort","experiment_id":"EXP-42","archive_id":"A-42-1","reason":"Human requested abort before Claim."}
~~~

Abort is valid only while the Archive is still PREPARED.
