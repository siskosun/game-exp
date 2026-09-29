# game-exp Board information architecture

## Default view

When the user opens the panel without naming a view, render `总览`.

Show five logical views:

- `总览`
- `待处理`
- `原型`
- `分支图`
- `归档`

Use one pinned protected experiment-record snapshot for every view in the same response.

In the 1.5 default MCP surface, `game_exp_board`, `game_exp_subject_panel`, and `game_exp_experiment_panel` are registered read-only tools. Registration is not a UI trigger. The full Board remains explicit by default; a focused panel may surface proactively only when `surface_hint.surface_when_relevant=true` or the user explicitly drills down.

## Shared header

Prefer the ready-to-render `display` block returned by `game_exp_board`. It is the cross-Harness Chinese presentation contract and must be rendered before a host invents its own summary.

For the normal Chinese Board:

- render `display.title_zh` as the title;
- render `display.rows_zh` in order as the summary rows;
- render `display.trust_title_zh` + `display.trust_summary_zh` for repository checks;
- when the host needs one text block instead of a rich table, render `display.summary_text_zh` directly;
- use `display.snapshot_note_zh` only as secondary help text;
- treat `display.render_contract` as normative: raw fields are logic/diagnostic inputs, not copy to translate;
- use `project`, `repository`, `statistics`, and raw enums for logic, not as primary UI copy.

The standard rows are:

- `仓库`
- `项目状态`
- `我的权限`
- `实验记录快照`
- `实验统计`
- `下一步`

Do not append machine codes to these values. In particular, normal rendering must not produce forms such as `readiness=PROJECT_READY`, `管理员 (ADMIN)`, `5/5 PASS`, or literal translations such as `医生检查`. The engineering field/tool name `doctor` is presented as `仓库检查`, never `医生检查`. Do not translate raw key names at all when a ready-to-render `display` value exists.

The experiment views are pinned to `snapshot_head`. Repository visibility, access and trust checks are current repository state at call time; do not present them as historical experiment-record state.

If `project.readiness=PROJECT_READY`, the repository bootstrap is complete. Never infer an older private-repository Ruleset blocker from chat history, cached preflight output, or a previous Board. Never recommend `project-init` in that state.

## 上浮策略

Board 是决策界面，不是每次 Agent 完成工作的固定结束页。1.0 的默认展示策略是：

- 普通实现/修订完成，且当前没有需要人处理的事项：返回紧凑结果，不自动打开完整 Board；
- 当前实验出现需要试玩、选择版本、完成归档、恢复、记录异常或依赖复核等需要处理事项：允许宿主主动上浮该实验的局部面板；
- 用户明确要求“打开面板 / 看所有实验 / 看分支”时：打开完整 Board。

实验行的 `surface_hint` 是只读展示提示：

- `COMPACT_RESULT`：正常完成反馈，不主动打断；
- `CONTEXTUAL_PANEL`：有当前人类动作或异常需要处理，宿主可以上浮对应局部面板；
- `surface_when_relevant=true` 只表示“现在值得主动呈现”，不是生命周期命令，也不授予任何操作权限；
- `surface_hint.authoritative=false` 必须保持为 false。

触发依据是“用户现在是否需要做什么”，不是“Agent 刚刚做完了什么”。完整 Board 始终由用户显式打开，除非宿主本身有独立的 UI 导航规则。

## 聚焦筛选

The Board may include a read-only `focus` projection. It never changes the protected Ledger snapshot or any lifecycle state.

Supported filters:

- `query`: case-insensitive substring search across experiment id, Issue number, title, subject/prototype name, and hypothesis.
- `subject_id`: exact stable subject id.
- `lifecycle`: lifecycle code, normalized to uppercase.
- `attention_only`: only experiments that currently require attention.

When any filter is active, render `focus.summary_zh` and use `focus.experiment_ids` to narrow the displayed rows. The focus projection also carries `attention_count`, `counts_by_lifecycle`, and `counts_by_health` for the narrowed result. Keep global counts and the underlying five views based on the complete pinned snapshot so filtering cannot hide repository health or change authority.

If the focus result is empty, show `没有符合当前筛选条件的实验`; do not report `暂无实验` unless the repository itself has zero experiments.

## 总览

Answer three questions first: what is broken, what needs a human decision, and what is currently active.

Order:

1. `需要处理`: use `views.overview.attention_ids`; order by Board attention priority.
2. `当前进行`: use `views.overview.active_ids`, excluding experiments already shown under `需要处理`.
3. One-line archived summary using `views.overview.archived_count`.

Do not dump Candidate/Rehearsal/Integration IDs in the default overview. Treat them as diagnostic identifiers; only show them when the user explicitly asks for protocol/debug detail.

## 待处理

Use `views.attention.sections` as the primary structure instead of one flat list.

Render sections in this order when non-empty:

1. `异常`
2. `需要恢复`
3. `需要你试玩`
4. `需要你选择`
5. `需要你完成归档`

Each experiment entry should show:

- 实验编号
- 原型/主体
- 实验标题
- 发起人（来自可信实验登记；历史记录可能缺失）
- 代码贡献者（来自 GitHub commit contributor 信息，仅协作展示，不作为权限依据）
- 当前进展
- 为什么需要处理
- 下一步动作

Use the Chinese values already emitted in `display` and `attention`. Do not expose raw enums such as `HUMAN_REVIEW` as the primary UI text.

## 协作状态

实验条目可携带 `unreleased_work_claims`、`unreleased_work_claim_count` 和 `work_awareness_zh`，用于回答“现在谁正在改什么”。

这些字段来自同一个固定 Ledger 快照，只表示**尚未结束的工作意图**。它们不能证明执行者仍基于当前实验分支，也不能替代实时冲突判断。

当用户准备继续开发、切换 Harness、或需要判断是否和别人撞车时，使用 `game_exp_collaboration_context`。该查询会额外读取当前 canonical experiment branch SHA，并区分：

- 当前工作意图；
- 已因分支推进而过期的工作意图；
- 当前范围重叠冲突；
- 当前 Harness 是否落后于实验分支。

范围重叠是协调提示，不是锁，也不改变实验 health/lifecycle。

## 原型

Use `views.prototypes.groups`.

Render one compact group per subject:

- subject name and root path;
- total / active / archived / attention counts;
- for concurrent experiments, show each experiment's trusted initiator and GitHub contributors so the user can see who is trying what;
- lifecycle distribution;
- latest experiment;
- child experiment ids only when useful.

Hierarchy is `Repository -> Subject/Prototype -> Experiment`.

Authoritative `manifest.subject` wins. `scope.allowed` inference is legacy fallback only.
If a legacy manifest has only broad `games/**` scope or no resolvable prototype, display `仓库级/未指定原型` rather than inventing a prototype identity.

For each prototype group, show `recent_activity` as `最近活动` and `relationship_count` when non-zero. Activity labels must remain Chinese.

When the user opens a prototype group, use `game_exp_subject_panel` when available. Render `summary` first, then `experiments`, `recent_activity`, and `relationship_edges`. This is a read-only drill-down between repository overview and single-experiment detail.

## 可信筛查与现任 / 挑战者比较

When Evaluation Evidence v1 is present, an experiment row may expose:

- `candidate_evaluation`;
- `evaluation_profile_digest`;
- `eligible_for_human_comparison`;
- `evaluation_summary_zh`;
- `incumbent_experiment_id`;
- `incumbent_comparison`;
- `review_comparison`.

`eligible_for_human_comparison` is a screening projection, not a lifecycle state:

- `ELIGIBLE` -> `可信筛查通过，可进入人工比较`
- `INELIGIBLE` -> `可信筛查发现必要条件缺陷，不建议进入人工比较`
- `INCONCLUSIVE` -> `筛查证据不足，暂不能判断是否适合人工比较`
- `UNKNOWN` -> `尚无可用的可信筛查结果`

Do not render `INELIGIBLE` as `已拒绝`; only human lifecycle state may say that.

For a challenger with a `supersedes` relationship, Board may derive a compact incumbent/challenger panel from the two experiment rows and the challenger's Review. This remains a projection, not an authoritative Comparison Set.

When a human blind A/B comparison exists, display the per-dimension choices, presentation order and `无明显差异` / `证据不足` outcomes without converting them to a numeric score or Elo.

In experiment detail, show `可信筛查` before the human Review row. If the challenger is `ELIGIBLE` and the review protocol calls for comparison, `待人工比较` is useful secondary evidence text; lifecycle next-gate remains governed by the existing Review rules.

### 同实验版本修订 A/B

Iteration delivery card may expose `comparison.revision_ab_session` when the exact current Candidate and its authoritative immediate previous Candidate both have verified shareable URLs.

Primary presentation rules:

- show only `版本 A` and `版本 B` plus the focus points and rating options;
- do not expose `machine_binding.slot_candidates`, Candidate ids, or which slot is current before the human choice;
- the session is read-only until the human also supplies an explicit Review PASS/FAIL;
- participant-reported previous-Candidate hints are diagnostic only; the Board pair comes from protected Candidate history;
- a recorded Review may expose `review_revision_comparison` afterward, including the normalized current-relative verdict;
- do not turn the comparison into Elo, a numeric score, PROMISING, REJECTED, or SELECTED.

This revision comparison is independent of the cross-experiment `incumbent_comparison` projection and does not create a persistent Comparison Set.

## 分支图

Use `views.branches.lanes`.

Render a lightweight text topology rather than a wide table. Example:

```text
main
├─ exp/51  原型A  REVIEW  Candidate C-51-...
├─ exp/52  原型B  PROMISING  主干集成验证 R-52-...
└─ exp/53  原型C  ARCHIVED  final tag exp-final/53
```

Show parent SHA only when diagnosing freshness or ancestry. Show final tag for archived experiments. Do not imply a branch still exists after `ATOMIC_DELETE` merely because the canonical branch ref is recorded in binding metadata.

## 实验详情

When the user opens one experiment, use `game_exp_experiment_panel` when available and organize the returned detail panel in this order:

1. `实验概况`: 标题、原型、发起人、代码贡献者、当前进展、记录状态、下一步。
2. `假设与判定`: use `judgement.hypothesis`, `judgement.success_criteria`, and `judgement.kill_criteria`.
3. `活动时间线`: use the experiment `activity` array. Render `label_zh` and `detail_zh`; show `occurred_at` only when the Ledger-derived record contains a trustworthy timestamp.
4. `关系`: show outgoing and incoming experiment relations with Chinese relation labels.
5. `代码与证据`: branch / Candidate / Rehearsal / PR / Archive records only on demand. In the default view, label Candidate as `试玩版本`, Review as `试玩结果`, and Rehearsal as `合入前检查`.

Relationship labels:

- `depends_on` -> `依赖`
- incoming `depends_on` -> `被依赖`
- `blocks` -> `阻塞`
- incoming `blocks` -> `被阻塞`
- `supersedes` -> `替代`
- incoming `supersedes` -> `被替代`

Do not fabricate timestamps for timeline events. Events without an authoritative time may still appear in semantic lifecycle order.

## 中文展示约束

All system-generated panel entries must use natural Chinese as the primary text: view names, section names, lifecycle labels, health labels, next actions, relationship labels, activity labels, repository trust checks, and permission/status summaries.

For ordinary Board rendering, do not expose or parenthesize raw machine enums. `PROJECT_READY`, `ADMIN`, `WRITE`, `PASS`, `FAIL`, `WARN`, and similar codes are machine-facing values and may be shown only when the user explicitly asks for diagnostics. A host must not reconstruct the normal summary from raw fields when `display.presentation_version >= 4`; use `display.rows_zh`, `display.trust_summary_zh`, or `display.summary_text_zh` instead. Treat `display.render_contract.strict_primary_copy=true` and `forbidden_primary_tokens` as normative: those tokens must not appear in ordinary Chinese panel copy.

Do not mechanically translate internal English identifiers. Required presentation mappings include:

- `doctor` / Doctor -> `仓库检查` (never `医生检查`)
- Ledger -> `实验记录`
- Rulesets -> `分支与引用保护`
- Deploy Key -> `部署密钥`
- Secret -> `私钥` or the more specific Chinese label already emitted by `display`
- Immutable Releases -> `发布保护`
- Candidate -> `试玩版本`
- Review -> `试玩结果`
- PASS / FAIL Review -> `试玩通过 / 试玩未通过`
- Rehearsal -> `合入前检查`
- Binding -> `实验登记`
- PROMISING -> `待选择`
- SELECTED -> `已选定`

Literal identifiers that are part of the repository itself, such as `owner/repo`, branch names such as `main`, commit hashes, experiment ids, and product names such as `game-exp` / GitHub, may remain unchanged.

User-authored or authoritative stored titles are not silently translated or rewritten.

## 归档

Use `views.archive.experiment_ids`.

Show experiment, subject/prototype, title, Archive id, Integration id, and final-tag ref when available. Keep this view separate from active work by default.

## Chinese labels

Lifecycle:

- `ACTIVE` -> `修改中`
- `REVIEW` -> `待试玩`
- `PROMISING` -> `待选择`
- `SELECTED` -> `已选定`
- `INTEGRATED` -> `已合入主版本`
- `REJECTED` -> `未采用`
- `ABANDONED` -> `已放弃`
- `ARCHIVED` -> `已归档`

Health:

- `PASS` -> `正常`
- `FAIL` -> `异常`
- `UNKNOWN` -> `未知`

Next gate:

- `IMPLEMENT_OR_REVIEW` -> `继续修改 / 准备试玩`
- `CANDIDATE_BUILD` -> `准备试玩版本`
- `HUMAN_REVIEW` -> `试玩后选择通过或未通过`
- `HUMAN_PROMOTION` -> `保留为待选版本 / 继续修改`
- `HUMAN_DECISION` -> `继续修改 / 放弃这版`
- `TRUSTED_REHEARSAL` -> `自动检查是否可以合入主版本`
- `HUMAN_SELECTION_OR_REFRESH_REHEARSAL` -> `选定这版 / 主版本变化后重新检查`
- `TRUSTED_INTEGRATION_OR_REFRESH_REHEARSAL` -> `合入主版本 / 主版本变化后重新检查`
- `ARCHIVE_OR_RETAIN` -> `完成；选择是否保留开发分支`
- `ARCHIVE_RECOVERY` -> `继续完成归档`
- `ARCHIVE` -> `归档这个实验`
- `TERMINAL_NEW_EXPERIMENT_FOR_NEW_WORK` -> `已结束；新想法请新建实验`
- `VERIFY_EXPERIMENT_HEALTH` -> `检查实验记录`
- `DO_NOT_USE_RECREATE_EXPERIMENT` -> `记录异常；先修复再继续`

Keep raw non-PASS health codes visible for diagnosis.

## Empty repository

If the protected Ledger contains zero experiments, render `onboarding` from the Board response.

When `project.readiness=PROJECT_READY` and `project.can_create_experiment=true`:

- show `暂无实验`;
- show onboarding progress `2/6 · 描述第一个实验`;
- make `创建第一个实验` the primary action;
- do not suggest `project-init`, Ruleset setup, Deploy Key setup, Secret setup, Immutable Releases setup, or changing repository visibility.

When the project is not ready, use `project.next_action_zh` and the failed/unknown `project.trust_checks` instead of guessing the blocker.

Do not fabricate a placeholder experiment row.

## 作者与贡献者

Use two distinct concepts:

- `发起人`: the trusted GitHub actor recorded when the experiment is established. This identity may be used for attribution, but authority still comes from current trusted permission checks. Keep Bind/binding details out of primary UI copy.
- `代码贡献者`: GitHub-linked contributors observed from commits on the canonical experiment branch (or final tag for archived experiments). This is collaboration metadata only and must never grant authority.

For legacy experiments without `binding.initiator`, display `发起人：历史记录未保存` rather than inferring an authoritative initiator from commit authors.

When contributor history is incomplete (for example more than the inspected commit window or GitHub lookup failed), `contributors_complete=false` and the UI must label it as `贡献者记录可能不完整`.

## 协作通知

The panel may show a compact `协作动态` entry backed by `game_exp_notifications`. The notification tool is registered by default, but registration is not permission to poll or surface events continuously; call it only for explicit activity/collaboration requests or a workflow that actually needs incremental event deltas.

Show only meaningful experiment events. Display subject/prototype, experiment id, trusted actor when known, event label, and title. Do not show delivery state as lifecycle state.

For a new experiment under a subject where another collaborator has prior participation, surface the event prominently to that collaborator.


## 依赖复核

`depends_on` currently identifies a coarse experiment dependency; it does not state whether the downstream requires an integrated capability, an immutable source snapshot, or continued upstream development.

When an active experiment depends on a REJECTED, ABANDONED, or ARCHIVED experiment:

- add `DEPENDENCY_REVIEW_REQUIRED` to the downstream projection;
- show the upstream lifecycle plus Integration id/final tag when available;
- place it in `依赖需复核` only when no higher-priority blocker/human gate already owns the attention slot;
- never auto-reject or auto-archive the downstream experiment;
- keep `blocks_progress=false` until a more specific dependency predicate exists.

An ABANDONED upstream means work stopped without asserting a failed Review; the downstream must be rechecked rather than auto-rejected. An ARCHIVED upstream may be perfectly valid if its integrated capability or immutable final snapshot satisfies the downstream dependency. Lifecycle alone is insufficient to decide.


## Experiment card rendering

Each experiment exposes `card_zh` as ready-to-render Chinese copy for the card surface. Render `card_zh.rows_zh` or `card_zh.summary_text_zh` directly for repository, prototype, and attention views. Raw machine fields remain available for logic and diagnostics.
