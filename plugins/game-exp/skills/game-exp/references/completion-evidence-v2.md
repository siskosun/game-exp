# Optional Completion Evidence v2 integration

This is an evidence adapter, not a new lifecycle gate or a replacement for Evaluation Profile v1.

## Ownership

- GPS/H5 own path declarations, executor-specific replay hooks, and participant-reported exploration.
- game-exp owns the frozen Candidate identity, protected evaluator boundary, trusted observation provenance, and human lifecycle decisions.
- A skill-produced report is participant-reported until the protected game-exp evaluator independently replays the declared traces against the frozen Candidate archive.

## Mapping into Evaluation Evidence v1

Do not change the Evaluation Profile v1 schema or reinterpret its existing requirements.

A project may add a hypothesis requirement for each materially distinct promised path or terminal outcome. The protected evaluator must:
1. Read the path declaration from the exact Candidate source SHA.
2. Validate the declared path/transition graph and source/artifact identities.
3. Independently execute each required trace against the frozen Candidate bytes in a clean workspace.
4. Record per-path PASS, FAIL_PRODUCT_DEFECT or INCONCLUSIVE using the existing Evaluation Evidence v1 result contract.
5. Preserve path coverage as descriptive evidence, including the denominator, missing paths and missing transitions.

Do not accept a self-reported path_results PASS as trusted evidence. A report's hashes prove byte identity only; they do not prove who executed it or whether the claimed gameplay occurred.

## Lifecycle boundary

Path coverage is a projection of trusted observations. It must not automatically record Review PASS/FAIL, PROMISING, REJECTED, SELECTED, Integration or Archive. The existing human Review and selection gates remain authoritative.

## Adoption

Keep v1 for ordinary probes and existing projects. Adopt path-level requirements only when the accepted brief includes materially different branches, endings or recovery paths. Do not add a universal minimum path count or coverage percentage. A small game with one meaningful route should not be forced to manufacture branches.
