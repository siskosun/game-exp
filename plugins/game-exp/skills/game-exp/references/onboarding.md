# game-exp first-use onboarding

## Goal

Help a new user reach a valid first experiment without requiring them to understand Ledger internals, Binding, Candidate, Review, Rehearsal, request ids, lifecycle enums, PROMISING/SELECTED, or protected refs. The visible mental model is: `原型 → 修改 → 试玩 → 继续修改 / 保留这版 / 就选这版 / 放弃`.

First-experiment onboarding assumes the repository is already `PROJECT_READY` under `references/project-setup.md`. If the user is starting a brand-new prototype with no repository, use project-create first and carry the original prototype goal forward into onboarding. If repository trust prerequisites are incomplete, return to project setup instead of continuing onboarding.

Onboarding is guidance only. It must not bypass repository trust checks, human gates, or trusted workflow tools.

## When to trigger

Show first-use onboarding when any of these is true:

- the protected Ledger contains zero experiments;
- the user explicitly asks how to start or says they are using game-exp for the first time;
- the user opens the Board and no valid experiment exists yet.

Prefer the `project` and `onboarding` blocks returned by `game_exp_board`. They are the cross-Harness current-state projection. Do not override them with old chat context, cached preflight output, or remembered repository visibility.

If `project.readiness=PROJECT_READY`, repository setup is complete. In an empty repository this means onboarding starts at step 2, `描述第一个实验`; do not rerun or recommend `project-init`.

Do not repeatedly force onboarding after the repository already has experiments. Provide a visible `新手引导` entry instead.

## Six-step flow

1. `连接检查`
   - start with `game_exp_status`; it is the compact 1.0 handshake for exact repository identity, Ledger head, access, runtime version, repository version, and protocol versions;
   - if `version_state` is not `MATCH`, align the current Harness/runtime before any mutation;
   - classify `status.access.status` as `NO_ACCESS`, `READ_ONLY`, `WRITE`, or `ADMIN`;
   - `NO_ACCESS`: explain that the repository cannot be read and stop;
   - `READ_ONLY`: allow Board viewing but disable creating or advancing experiments;
   - `WRITE`: allow normal experiment work but label admin-only Doctor coverage as partial;
   - `ADMIN`: allow normal use with full repository-level inspection coverage;
   - if the Board already returns `project.readiness=PROJECT_READY`, treat trust setup as complete and continue to step 2;
   - otherwise run repo-level `game_exp_doctor` without `experiment_id`; on FAIL route to `references/project-setup.md`;
   - explain UNKNOWN/partial coverage and do not continue past a hard trust failure.

2. `描述第一个实验`
   - ask for or infer: target prototype/subject, intended change, and desired player outcome;
   - do not ask the user to write a Manifest.

3. `生成实验定义`
   - call `game_exp_experiment_template` or CLI `experiment-template`; if neither exists but GitHub read access is available, read this repository's `.game-exp/project-policy.json` plus its checked-in `references/public-contract.md`;
   - use the current repository's project policy and recommended Manifest schema returned or documented there;
   - do not search toy2game, another repository, or historical Ledger experiments merely to discover runtime fields or copy a Manifest shape;
   - draft hypothesis, success criteria, kill criteria, scope and subject from the user's goal;
   - use the returned schema-v2 runtime default `{adapter, policy_path}` and review default unless the user has a real reason to choose another review protocol;
   - ask only when a missing user-owned choice would materially change the experiment;
   - otherwise present the drafted definition in plain Chinese.

4. `建立实验`
   - resolve/create the real GitHub Issue through the host's authorized GitHub capability;
   - Bind through `game_exp_experiment_bind`; the agent generates the stable Manifest operation id internally;
   - reconcile ACCEPTED/UNKNOWN with `game_exp_operation_get` / the same operation id until authoritative;
   - Initialize through `game_exp_initialize` with a new stable request id for that Initialize operation;
   - do not make the user invent or copy request ids manually.

5. `开发与试玩`
   - source work happens on the canonical `exp/<issue>` branch;
   - resolve the selected stack before implementation: prefer Godot Prototype Studio for Godot and H5 Game Prototype Agent for H5/browser work when those Skills are available;
   - the canonical Harness installer normally synchronizes both companion Skills, but host availability still must be checked at runtime;
   - H5 PROBE outcomes are implementation evidence only; `READY_FOR_PLAYTEST` never equals Review PASS or PROMISING;
   - when implementation is ready, internally move to REVIEW and build Candidate, but tell the user only that the试玩版本 is ready;
   - explain that automated checks mean “可以开始试玩”，not “已经通过.”

6. `试玩与选择`
   - user says whether the current试玩版本通过、未通过、还要继续改，或只想保留这一版;
   - a试玩通过 does not automatically select the version;
   - when the user says `就选这版`, perform the internal Rehearsal/selection prerequisites automatically and report only actionable blockers;
   - when finished, ask only the material archive choice: whether to keep the development branch.

## Inline UI

When Chat inline UI is supported, empty repositories should render an onboarding card instead of only `暂无实验`.

Use the Board response's `onboarding` fields directly when available.

Show:

- progress: `1/6` through `6/6`; a ready empty repository normally shows `2/6`;
- current step title;
- one-sentence explanation;
- one primary next action;
- a compact `为什么需要这一步` expandable explanation;
- `跳过新手引导` only as a presentation choice, never as a way to skip required trust or lifecycle gates.

For repositories that already contain experiments, expose `新手引导` as an optional help entry and do not interrupt the normal Board.

## Natural-language entry points

Accept simple user intents such as:

- `第一次用 game-exp`
- `帮我新建一个 H5 原型`（无现有仓库时先走 project-create）
- `新建一个 Godot 原型项目`
- `帮我创建第一个实验`
- `我要给 flip-match 做一个实验：失配后提示下一位玩家`
- `这个版本做好了，准备试玩`
- `我试玩过了，通过`
- `继续改这版`
- `保留这版`
- `就选这版`
- `放弃这个实验`

Translate these intents to the existing trusted workflow. Do not require users to name MCP tools, lifecycle enums, or request ids. The agent must still generate and preserve stable ids internally for every mutation.

## Completion

Onboarding is complete only when the first experiment is authoritatively bound and initialized. Later lifecycle stages remain part of normal game-exp operation.

Do not label an ACCEPTED dispatch as onboarding completion.

## Access-state copy

Use these Chinese messages consistently:

- `NO_ACCESS`: `无法访问该 GitHub 仓库。请检查登录、仓库授权，或切换到你有权限的仓库。`
- `READ_ONLY`: `当前只有读取权限：可以查看 game-exp 面板，但不能创建或推进实验。请获得仓库写入权限后继续。`
- `WRITE`: `当前具有读写权限，可以使用 game-exp；部分管理员级检查可能不可见。`
- `ADMIN`: `当前具有完整仓库管理权限。`
