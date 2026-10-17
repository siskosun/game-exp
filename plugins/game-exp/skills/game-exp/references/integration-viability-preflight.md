# Integration viability preflight (advisory, before Bind)

Use this optional read-only diagnostic when a proposed experiment might later be
integrated into main. It identifies recurring integration failure modes; it is
**not** a new game-exp lifecycle gate, Trusted Writer, protected Ledger record,
Doctor PASS, or merge authorization.

## Inputs and evidence provenance

Save the proposed unbound Manifest as JSON; use one pinned snapshot of verified
facts from the current repository and protected Ledger:

- main_sha: full 40-character HEAD SHA of main.
- parent_is_ancestor_of_main: boolean **only after** checking exact pinned Git
  ancestry or trusted GitHub compare evidence; otherwise null.
- parent_experiment_lifecycle: authoritative state from the same pinned Ledger
  when the Manifest names a parent experiment.
- metadata_path: optional override if project initialization differs from the
  standard path experiments/EXP-N/manifest.yaml.
- pr_capabilities.actions_can_create_pr: verified true/false only; an Actions
  YAML permission line does not prove repository settings permit PR creation.
- pr_capabilities.authorized_connector_can_create_pr: independently verified;
  null if unverified. Never conflate the connector with the Actions identity.

Example facts JSON:

    {"main_sha":"<40-hex>","parent_is_ancestor_of_main":null,
     "pr_capabilities":{"actions_can_create_pr":null,
                        "authorized_connector_can_create_pr":null}}

Run from the installed Skill root:

    python scripts/preflight_integration.py --manifest proposed.json \
      --snapshot pinned_facts.json --repo /path/to/clone \
      --output preflight.json --strict

The --repo option verifies ancestry from local Git objects. Without a checkout,
pass only externally verified pinned ancestry evidence. The script uses Python
standard library, makes no network calls, and writes no Git refs or Ledger
records. A preflight output report is advisory evidence only.

## Verdicts

- BLOCKED / strict exit 2: proven parent/base gap, self-conflicting trusted
  metadata path, conflicting ancestry evidence or a known PR creation block.
- UNVERIFIED / strict exit 3: missing ancestry, parent lifecycle or permission
  evidence; do not infer success.
- READY_WITH_WARNINGS: known fallback is necessary or allowed scope includes
  trusted metadata; check the warning.
- READY: these **narrow** checks are supported. It is not a gameplay, build,
  Rehearsal, future-main freshness or human Review result.
- Invalid inputs exit 4. With no --strict, valid advisory JSON exits 0 even if
  the verdict is BLOCKED. Consumers must inspect verdict, not exit 0 alone.

## Lessons from Echo Tide

- EXP-5 was based on an unintegrated active EXP-1. Parent base was not present
  in main. Fix the *planned* dependency or build an independent main-based
  variant; do not force the unreviewed parent through human gates.
- EXP-6 listed experiments/** in scope.avoid. This also banned its trusted
  initializer's own Manifest; the Rehearsal failed. Avoid banning the
  proposed experiment's metadata before Bind. Keep source scope.allowed tight.
- EXP-7 used a valid metadata exception and passed pinned-main Rehearsal, but
  Actions lacked permission to create a PR. The explicit alternative connector
  was permitted to create PRs without disabling any policy.

## Authenticated fallback after a trusted proposal

If a trusted Integration job already generated the exact proposal branch but
failed *only* on GitHub Actions PR permission:

1. Verify the failed job was PR permission, not a failing trusted scope/tree,
   freshness, Candidate, source, or policy check.
2. Pin the current protected state, main, candidate, Rehearsal and exact
   proposal branch. Verify its commit has one parent equal to pinned main and
   its tree equals the trusted Rehearsal integration_tree_sha.
3. If the current host has an independently authorized PR creator, create the
   PR from that **same branch** to main. Never rebuild the branch, rewrite SHA,
   switch actor identity to escape a denied operation, or weaken Rulesets.
4. Rerun the failed job of **the original workflow run**, not a replacement
   integrate request. Require the trusted job to recognize the exact PR head
   and base, and to finish SUCCESS.
5. Merge only on explicit user authorization; finalize only after real merge
   and trusted tree/ancestry verification.

Do not mutate Ledger or protected refs from this advisory. A positive diagnostic
does not approve any human decision.
