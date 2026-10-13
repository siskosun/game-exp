# Requirement clarification and intent alignment

This is a lightweight reasoning step before Bind/Initialize and before substantial source edits, inspired by [ReqClarifyBench](https://arxiv.org/abs/2610.13022). It is **not** a new lifecycle gate, Agent, database, mandatory Manifest field, or independent approval mechanism. Do not turn it into an exhaustive questionnaire.

## Triage from existing evidence

1. Read the user's actual request and available current repository context first. For an existing experiment, refresh the protected experiment projection and current Manifest; do not overwrite authoritative fields with old chat notes or an executor's guess.
2. Separate information by its actual source and purpose:
   - **Confirmed intent**: the user's explicit choice or a valid existing requirement that the user has not changed.
   - **Experiment question**: a game-design hypothesis to test through implementation and human playtest, such as which interaction feels better. Do not demand the answer up front.
   - **Reversible default**: a low-cost implementation/detail choice that the agent can make and later change. Label consequential assumptions as defaults, not user decisions.
   - **Blocking ambiguity**: two or more plausible interpretations that would materially alter the hypothesis, intended player experience, core mechanic, target multiplayer mode, success/kill criteria, authorized scope, or an irreversible action.
3. Check whether project policy, existing code, earlier explicit choices, or the current experiment already resolves the ambiguity. Do not ask the user to repeat known answers.

## Ask only when it changes the decision

- For a blocking ambiguity, ask one direct, concrete question about the **player/product decision**, with meaningful alternatives where helpful. Clarify before Bind/Initialize or an irreversible change. Do not replace that decision with a guessed Manifest.
- For independent, non-blocking uncertainties, proceed using the simplest reversible assumption. Don't stop to collect preferred colors, engine/library choices already established by the repository, or exhaustive feature lists.
- Avoid multi-round low-yield clarification: integrate each answer, stop asking once remaining gaps are reversible or are meant to be explored experimentally, and continue the task.
- An explicit user instruction to proceed autonomously does not authorize inventing a materially different core intent or bypassing human lifecycle gates.

Examples:

| User request | Treatment |
|---|---|
| “做一个多人捉迷藏原型” and no existing multiplayer choice | Ask whether players act simultaneously in real time or take asynchronous turns if that difference changes the core experiment/implementation. |
| “把现有原型的按钮做得更醒目” | Treat style and layout as reversible defaults; implement and validate without questioning. |
| “试试哪种合作机制更有趣” | Record the choice between mechanisms as the **question to test**, not a fact the user must decide before experimentation. |
| “把目前的单人对战改成实时多人竞技” | Check whether this crosses the current hypothesis/core-mechanic boundary; if so, explain the change and ask before creating a new Issue/experiment. |

## Preserve intent without changing the protocol

- Use the repository's existing Manifest schema and its hypothesis, success/kill criteria, scope, subject, runtime and review protocol. Do **not** add an unsupported `requirements`, `assumptions`, or `clarification_status` field or make a requirements document compulsory.
- Tie testable criteria to observable player behavior or declared test evidence. Keep subjective enjoyment/feel explicitly for human playtest; passing automated checks does not prove that players enjoyed the result.
- In the short plain-language pre-Bind summary and available executor brief, distinguish **user-confirmed requirements**, **experiment hypotheses**, and **agent defaults**. If the Manifest has no field for provenance, keep it in the conversation/brief rather than changing protected domain records or pretending an assumption was confirmed.
- Do not silently change experiment scope, criteria, or review protocol after Bind. Follow the existing revision/new-experiment routing and trusted workflow.

## Reconcile during implementation and Review

- When new input changes the goal, reassess against the exact current Manifest. Ordinary polish or tuning stays a revision; a materially different hypothesis, core mechanic, player experience, or success/kill criterion requires the existing new-experiment confirmation before Bind/Initialize.
- After a substantive revision, use the new exact Candidate and fresh human Review; a prior Review does not validate changed bytes.
- Before asking for human Review, compare the playable and implementation evidence with the **originally intended player outcome**. Surface verified behavior, unmet requirements, untested subjective claims, and significant remaining agent defaults separately. Do not report “intent aligned” merely because a build/test is green.
- The human still decides PASS/FAIL, PROMISING, and SELECTED. Clarification never records or bypasses those decisions.

Success is fewer costly misunderstandings **without** unnecessary questions, redundant paperwork, or weaker experiment protections.