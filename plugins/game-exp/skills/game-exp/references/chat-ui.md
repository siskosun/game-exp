# game-exp Chat inline UI contract

## Purpose

When the host supports a self-contained inline interactive app surface, render the game-exp Board as an interactive Chinese panel directly in the chat instead of expanding every Board field into prose.

This UI is a read-only projection. The protected Ledger and trusted workflow tools remain authoritative.

## Data sources

Use only one pinned protected Ledger snapshot per rendered panel.

Preferred read APIs:

1. Repository level: `game_exp_board`
2. Subject/prototype level: `game_exp_subject_panel`
3. Experiment level: `game_exp_experiment_panel`

Never combine data from separately moving snapshots inside one rendered panel.

## Navigation hierarchy

The inline panel must support:

`仓库总览 -> 原型/主体 -> 单实验`

The user must be able to return to the previous level without a new remote mutation.

## Repository access state

When onboarding or when repository capability is uncertain, render the result of `game_exp_access_check` before write-capable actions.

- `NO_ACCESS`: block Board loading if the repository itself cannot be read.
- `READ_ONLY`: allow Board viewing, disable create/advance actions, and show the Chinese read-only explanation.
- `WRITE`: enable normal workflows; mark admin-only inspection coverage as partial when applicable.
- `ADMIN`: enable normal workflows with full repository inspection coverage.

## Repository view

Use the ready-to-render repository-level `display` block before the five tabs:

1. `display.title_zh`
2. `display.rows_zh` in order
3. `display.trust_title_zh` + `display.trust_summary_zh`
4. optional expandable check rows from `display.trust_checks_zh`
5. `display.snapshot_note_zh` as secondary help text

If the host needs one plain-text representation, use `display.summary_text_zh` directly. For presentation v4, `display.render_contract.strict_primary_copy=true`; do not recompose visible copy from raw fields, and ordinary primary copy must not contain any token listed in `forbidden_primary_tokens`.

Do not reconstruct the visible status strip from `project.readiness`, `project.doctor_status`, `project.access`, or other machine fields. Do not translate raw key names such as `doctor`; in normal Chinese UI it is always `仓库检查`, never `医生检查`. `PROJECT_READY`, `ADMIN`, `PASS` and similar enums are diagnostics-only.

The raw `repository`, `project`, `statistics`, and `snapshot_head` fields remain available for interaction logic, filtering, and diagnostics.

Then provide five tabs:

- 总览
- 待处理
- 原型
- 分支图
- 归档

When the repository has zero experiments, render the `onboarding` block prominently. If `project.readiness=PROJECT_READY`, show `2/6 · 描述第一个实验` and `创建第一个实验`; do not show repository setup actions.

At minimum support local filtering by:

- keyword
- subject/prototype
- lifecycle
- attention only

Filtering changes presentation only. It must not change the Ledger snapshot, authority, counts in the complete repository projection, or lifecycle state.

## Subject view

Show:

- stable subject/prototype name and root path
- experiment count
- active / archived / attention counts
- lifecycle and health distribution
- recent activity
- child experiments
- relationship edges touching the subject

Selecting a child experiment opens the single-experiment view.

## Multi-user attribution

Experiment cards should show `发起人` when `initiator.login` is present and `代码贡献者` when contributor logins are available.

The UI must visually distinguish them. Contributor data is collaboration metadata only and must never imply Review, promotion, selection, merge, or archive authority.

For legacy experiments with no trusted initiator, show `发起人：历史记录未保存`. If `contributors_complete` is false, show `贡献者记录可能不完整`.

## Experiment view

Show in this order:

1. 实验概况
2. 假设与判定
3. 活动时间线
4. 关系
5. 代码与证据

The primary labels must be Chinese. Raw enums and ids may appear as secondary diagnostic detail.

## Iteration delivery card

After a completed implementation iteration, prefer the current experiment's `game_exp_board.experiments[].delivery_card` as the user-facing completion surface before opening the full Board. If the optional advanced single-experiment panel is enabled, `experiment_panel.delivery_card` carries the same projection.

Render, in order:

1. `本次改了什么` from `changes_zh`;
2. one primary playable action from `playable.action_zh`;
3. `与上一版相比` from `comparison`;
4. `这次重点感受` from `focus_points_zh`;
5. enabled natural-language actions from `quick_actions`.

Playable semantics are explicit:

- `SHAREABLE_URL`: `立即试玩`; verified clickable URL, intended to work across devices;
- `LOCAL_URL`: verified clickable URL only for the current device/network environment;
- `ARTIFACT_ONLY`: no direct playable link; offer the retained Candidate artifact;
- `MISSING`: say `试玩入口未生成`; never invent a URL.

The card is read-only and `authoritative=false`. Its quick actions are user-intent shortcuts, not a second state machine:

- `继续微调`: continue the same experiment; return to ACTIVE when the current lifecycle allows it, then claim source work;
- `保留这版`: no lifecycle mutation; retain the version only;
- `我试玩通过了`: an explicit human PASS statement only when the exact current Candidate is waiting for Review;
- `就选这版`: explicit selection intent, but run/refresh required Rehearsal before SELECTED;
- `回到上一版`: source-revision intent using the referenced prior Candidate; it does not rewrite Ledger history.

If an action is disabled, do not silently reinterpret it. Explain the missing prerequisite in normal language.

## Interaction boundary

The inline UI may perform only local presentation actions by itself:

- tab switching
- local filter/sort
- expand/collapse
- repository -> subject -> experiment navigation
- returning to parent view

It must not directly mutate lifecycle state or protected refs.

For actions such as Review, PROMISING, SELECTED, Integration, or Archive, the UI may show the currently valid next action, but execution must be handed back to the trusted MCP/workflow path and must preserve existing human gates.

## Empty and failure states

For a zero-experiment repository, prefer the Board response's `onboarding` block and the first-use rules from `onboarding.md` over a bare empty state. The card may show `暂无实验` as context. When `project.readiness=PROJECT_READY`, its primary action is `创建第一个实验` and repository bootstrap actions must not be offered.

- zero repository experiments: `暂无实验`
- zero filtered experiments: `没有符合当前筛选条件的实验`
- health FAIL: show as blocked; do not present normal lifecycle actions as available
- UNKNOWN: show unresolved and preserve the same authoritative request/snapshot identity

## Text fallback

If the host cannot render an interactive inline app, fall back to the text Board rules in `board.md` without changing data semantics.

The interactive UI is a presentation layer, not a new protocol or authority layer.


## Experiment card copy

Render each experiment card from `experiments[].card_zh`. This precomposed Chinese projection includes experiment, prototype, initiator, contributors, branch, progress, health, and next action.

## Rehearsal terminology

`Rehearsal` is the protocol name for validating the candidate's integration result against the latest main branch. Chinese primary UI copy should express that meaning as `主干集成验证`; keep raw `rehearsal_id` only as a protocol/diagnostic identifier.
