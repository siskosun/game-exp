# game-exp

[English](README.md) | **简体中文**

`game-exp` 是可信游戏实验管理系统（实验控制平面）的独立源码仓库，也是其唯一的正式开发与分发来源。

仓库地址：https://github.com/siskosun/game-exp

本仓库是唯一的开发事实来源。`main` 是开发分支，**不是**默认安装来源。稳定版安装和升级会选择 GitHub 上最新发布的、非预发布的语义化版本 Release。`toy2game`、`game-exp-sandbox`、各个目标项目仓库和本地安装到不同 Harness 的副本，都只是使用方或特定时点的快照，不是镜像仓库，也不会在 game-exp 更新时自动同步。

## 安装与升级

先阅读 [INSTALL.json](INSTALL.json)，确认当前使用的 Harness，然后只执行该 Harness 对应的安装命令。首次安装和后续升级使用同一个命令。

以 Codex 为例：

```powershell
git clone https://github.com/siskosun/game-exp.git
cd game-exp
python tools/game-exp/install_harnesses.py --harness codex --json
```

上面的代码仓库副本只是安装器的启动入口。默认的 `--channel stable` **不会安装当前检出的 `main`**：安装器会查询 GitHub Releases，选出最新已发布、非预发布的语义化版本，下载该 Release Tag 对应的源码归档，核对版本元数据，再从这份固定源码安装。

如需安装某个指定的已发布版本，包括主动回退到旧版本：

```powershell
python tools/game-exp/install_harnesses.py --harness codex --release v1.3.0 --allow-downgrade --json
```

如需测试当前检出的代码或 `main`，必须明确选择开发通道：

```powershell
python tools/game-exp/install_harnesses.py --harness codex --channel development --json
```

`--release` 与 `--channel development` 不能同时使用。稳定版安装会在 `INSTALL_SOURCE.json` 中记录实际使用的 Release Tag 和 Release URL；开发版安装会记录 `source_channel=development`、`source_ref=working-tree`。

支持的 Harness 为 `codex`、`qoder` 和 `cursor`，要求 Python 3.11 或更高版本。本地 CLI 和项目初始化还需要安装 GitHub CLI（`gh`），并通过 `gh auth login` 登录。只有明确需要同时更新三个 Harness 时，才使用 `--harness all`。

### 安装前检查

可以先只读检查当前 Harness 的安装状态：

```powershell
python tools/game-exp/install_harnesses.py --harness codex --check --json
```

检查可能返回 `NOT_INSTALLED`、`CURRENT`、`UPGRADE_AVAILABLE` 或版本比较警告，不会修改任何文件。

`CURRENT` 不仅要求版本号相同，还会核对受管运行时摘要、必需的运行时入口、已安装的 game-exp Skill 元数据和所选 Harness 的 MCP 配置。因此，即使版本号没有变化，也能发现不完整或发生漂移的安装。默认禁止降级；只有明确指定 `--allow-downgrade` 才允许主动回退。

### 旧版共享安装迁移

升级单个 Harness 时，会检测 `~/.agents/tools/game-exp` 和 `~/.agents/skills/game-exp` 下的旧版（0.17.x）共享安装，但**不会自动删除它们**。

只有已明确迁移全部三个 Harness，并且希望清理旧版共享目录时，才运行：

```powershell
python tools/game-exp/install_harnesses.py --harness all --cleanup-legacy-shared --json
```

`--cleanup-legacy-shared` 不能用于仅安装单个 Harness 的命令。

### Harness 隔离与伴随技能

每个 Harness 都有独立的运行时目录 `~/.game-exp/runtimes/<harness>`、单独的 game-exp Skill 副本和自己的 MCP 配置。升级其中一个 Harness，不会重写其他 Harness 的安装。

安装或升级 game-exp 时，安装器还会在**同一个 Harness** 中同步以下两个伴随技能的最新语义化版本 Tag：

- [godot-prototype-studio](https://github.com/siskosun/godot-prototype-studio)
- [h5-game-prototype-agent](https://github.com/siskosun/h5-game-prototype-agent)

伴随技能只同步运行所需的 Skill 文件，不复制其测试、CI、审计与开发历史，也不会修改游戏项目仓库。即使需要更新全部三个 Harness，也必须明确使用 `--harness all`。

如果伴随技能仓库没有语义化版本 Tag，或无法获取源码，安装器会明确报错，不会悄悄安装未发布的快照。安装采用事务机制：对 game-exp 运行时、Skill、MCP 配置及两个伴随技能进行整体更新；任一步失败，都会尝试恢复安装前的受管状态。

## 验证分发完整性

安装、发布或将本仓库交给其他 Harness 使用前，运行：

```powershell
python tools/game-exp/distribution_check.py --json
```

检查会识别版本标记不一致、正式 GitHub 源地址变化、安装过程破坏 Harness 隔离、必要受管文件缺失，或在独立分发包中混入固定绑定某个仓库的 Codex 配置等问题。

## 源码目录

- `tools/game-exp/`：运行时、CLI、MCP 服务、领域核心逻辑和测试。
- `plugins/game-exp/`：可移植的 Skill / Plugin 包。
- `.github/workflows/game-exp-*.yml`：由 Bootstrap 安装到目标项目仓库的可信工作流。
- `.agents/plugins/marketplace.json`：本地插件市场描述文件。
- `INSTALL.json`：可供程序读取的安装及升级约定。

## 开发与版本规则

**仅在本仓库进行 game-exp 的开发与发布。** 不要因为本仓库有了新提交，就自动把变更同步回应用仓库或已安装的 Harness 运行时。使用方只在明确请求升级时才更新。

合并正式发布所需的改动之前，应运行核心测试、MCP 测试和持续维护的 Conformance 一致性测试。人工审批关口、受保护 Ledger 的权威性，以及 Trusted Writer 的信任边界都必须保持不变。

v0.21 引入了 **Evaluation Evidence v1（评估证据机制）**：通过内容寻址的 Evaluation Profile，对固定 Candidate 产物进行可信重放与检查，提供三态的人类比较资格判断，并支持可选的现有方案与挑战方案的人类 A/B 比较注释。自动筛选只产生证据，**不会自动改变实验的生命周期状态**。

当前源码版本：**`1.5.3`**。

### 试玩版本交付

每次实现迭代完成后，game-exp 会基于 `work.release.delivery` 生成一张统一的中文交付卡，内容包括：本次改动、经过验证的可立即或本地试玩入口（没有入口时回退到保留的产物）、上一版的相关信息、1～3 项试玩重点，以及可用自然语言表达的下一步操作。

自 1.2.1 起，对于公开仓库，原型执行器可将不可变的试玩版本保存到 `gh-pages`，再通过受管的 GitHub Actions Pages 工作流按源码 SHA 部署。面板也能找回上一 Candidate 对应的、已经验证的历史分享地址。

交付卡**只读**；“保留这版”绝不等于 `SELECTED`，Review 和选择版本仍须经过既有人工审批关口。

自 1.3.0 起，如果当前 Candidate 和受保护记录中紧邻的上一 Candidate 都有已经验证、可分享的试玩版本，交付卡还可以提供匿名的“版本 A / 版本 B”修订对比。用户偏好属于 `HUMAN_REPORTED` 证据，只能与针对**当前 Candidate** 明确提交的 Review `PASS` / `FAIL` 一同保存；不会自动排序、晋级、拒绝或选中任何 Candidate。

### AI 独立设计与人机协作盲测（可选）

新增一个不依赖付费 API 的[本地匿名试玩辅助流程](plugins/game-exp/skills/game-exp/references/blind-origin-study.md)：登记两组作品的来源和固定证据，生成顺序平衡的 A/B 试玩页，记录并汇总玩家的主观选择。它不自动认证所填 Candidate 身份、不证明真实试玩顺序，也不修改 Ledger 或代替人工 Review。仓库的[纯合成示例](examples/blind-origin-synthetic-plan.json)只用于机制测试，没有真实玩家或真实作品。

### 从零创建原型项目

如果要制作全新原型而尚无项目仓库，本地 CLI / stdio MCP 可以使用 `project-create`，自动创建 GitHub 仓库、以最新已标记版本的 Godot 或 H5 起始模板初始化项目、安装 game-exp、推送 `main`，并完成项目初始化。

新仓库默认设为**公开**，以便在预期的 GitHub 免费套餐下使用 Rulesets。已有私有仓库不会被自动改为公开；只要其套餐支持所需的保护机制，仍可继续使用。

版本发布记录请参阅 [CHANGELOG.md](CHANGELOG.md)。

## 合并前检查

合并正式发布的改动前，运行：

```bash
python tools/game-exp/premerge.py --json
```

该命令会运行完整的单元测试（使用固定版本的 MCP SDK）、分发完整性检查及 Python 编译检查。
