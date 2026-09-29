from __future__ import annotations

import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
PLUGIN = ROOT / "plugins" / "game-exp"
SKILL = PLUGIN / "skills" / "game-exp" / "SKILL.md"


class GameExpSkillContractTests(unittest.TestCase):
    def test_portable_plugin_manifest(self):
        manifest = json.loads((PLUGIN / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "game-exp")
        self.assertEqual(manifest["version"], "1.0.0")
        self.assertEqual(
            manifest["$schema"],
            "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json",
        )
        self.assertTrue(SKILL.exists())

    def test_skill_icon_is_packaged_and_referenced(self):
        icon = PLUGIN / "skills" / "game-exp" / "assets" / "icon.svg"
        metadata = (PLUGIN / "skills" / "game-exp" / "agents" / "openai.yaml").read_text(
            encoding="utf-8"
        )
        bootstrap = (ROOT / "tools" / "game-exp" / "bootstrap.py").read_text(
            encoding="utf-8"
        )
        self.assertTrue(icon.exists())
        self.assertIn("icon_small: assets/icon.svg", metadata)
        self.assertIn("icon_large: assets/icon.svg", metadata)
        self.assertIn(
            '"plugins/game-exp/skills/game-exp/assets/icon.svg"',
            bootstrap,
        )
        self.assertIn('"install_harnesses.py"', bootstrap)
        self.assertTrue((ROOT / "tools" / "game-exp" / "install_harnesses.py").is_file())

    def test_repo_marketplace_points_to_plugin(self):
        market = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(market["name"], "game-exp")
        entry = next(row for row in market["plugins"] if row["name"] == "game-exp")
        self.assertEqual(entry["source"]["source"], "local")
        self.assertEqual(entry["source"]["path"], "./plugins/game-exp")
        self.assertIn(
            entry["policy"]["installation"],
            {"AVAILABLE", "INSTALLED_BY_DEFAULT"},
        )

    def test_standalone_distribution_has_machine_readable_install_contract(self):
        self.assertFalse((ROOT / ".codex" / "config.toml").exists())
        install = json.loads((ROOT / "INSTALL.json").read_text(encoding="utf-8"))
        self.assertEqual(
            install["source_of_truth"],
            "https://github.com/siskosun/game-exp",
        )
        self.assertEqual(
            install["policy"]["default_update_scope"],
            "current_harness_only",
        )
        self.assertFalse(install["policy"]["updates_other_harnesses"])
        self.assertFalse(install["policy"]["updates_consumer_repositories"])
        self.assertEqual(
            install["distribution_check"],
            ["python", "tools/game-exp/distribution_check.py", "--json"],
        )
        self.assertTrue((ROOT / "tools" / "game-exp" / "distribution_check.py").is_file())
        for harness in ("codex", "qoder", "cursor"):
            command = install["harnesses"][harness]["install_or_upgrade"]
            self.assertIn("--harness", command)
            self.assertIn(harness, command)

    def test_skill_frontmatter_and_domain_tools(self):
        content = SKILL.read_text(encoding="utf-8")
        server = (ROOT / "tools" / "game-exp" / "mcp_server.py").read_text(
            encoding="utf-8"
        )
        conformance = (
            PLUGIN / "skills" / "game-exp" / "references" / "conformance.md"
        ).read_text(encoding="utf-8")
        workflow = (
            PLUGIN / "skills" / "game-exp" / "references" / "workflow.md"
        ).read_text(encoding="utf-8")

        self.assertRegex(content, r"(?s)^---\nname: game-exp\ndescription: .+?\n---")
        for phrase in (
            "Detailed rules live in the references below",
            "## Task routing",
            "game_exp_status",
            "game_exp_project_preflight",
            "game_exp_project_init",
            "game_exp_board",
            "advanced focused-panel tools",
            "GAME_EXP_ENABLE_ADVANCED_TOOLS=1",
            "game_exp_notifications",
            "game_exp_collaboration_context",
            "game_exp_work_claim",
            "game_exp_work_release",
            "game_exp_prototype_handoff",
            "game_exp_operation_get",
            "game_exp_operation_resume",
        ):
            self.assertIn(phrase, content)

        # 1.0 keeps diagnostic/compatibility tools implemented but out of
        # the default MCP registration and fixed Skill context.
        for name in (
            "game_exp_conformance_suite",
            "game_exp_conformance_start",
            "game_exp_conformance_result",
            "game_exp_conformance_compare",
            "game_exp_access_check",
            "game_exp_capabilities",
            "game_exp_request_get",
        ):
            self.assertIn(name, server)
        self.assertIn("game_exp_conformance_suite", conformance)
        self.assertIn("game_exp_archive_abort", workflow)
        self.assertIn("game_exp_review_record", workflow)

    def test_skill_preserves_human_gates_and_async_semantics(self):
        content = SKILL.read_text(encoding="utf-8")
        workflow = (
            PLUGIN / "skills" / "game-exp" / "references" / "workflow.md"
        ).read_text(encoding="utf-8")
        setup = (
            PLUGIN / "skills" / "game-exp" / "references" / "project-setup.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "Never auto-approve a human gate",
            "Never report `ACCEPTED` as completion",
            "PASS Review does not automatically mean PROMISING",
            "only after the user explicitly chooses/selects the Candidate",
            "ATOMIC_DELETE",
            "RETAIN_BRANCH",
            "Archive is a destructive/recovery-sensitive workflow",
            "UNKNOWN",
            "Keep game-exp orchestration self-contained",
            ".ai/HANDOFF.md",
            "Global MCP registration must not hard-code one repository",
            "Pass that `repo` explicitly",
            "Do not fabricate a `FAIL` Review",
            "game_exp_abandon",
            "GitHub Bridge",
            "claim-without-result",
            "authorized GitHub connector",
        ):
            self.assertIn(phrase, content)
        public_contract = (
            PLUGIN / "skills" / "game-exp" / "references" / "public-contract.md"
        ).read_text(encoding="utf-8")
        for phrase in ("CONFLICT", "REJECTED"):
            self.assertIn(phrase, public_contract)
        for phrase in ("game_exp_archive_abort", "game_exp_review_record"):
            self.assertIn(phrase, workflow)
        self.assertIn("repo-level", setup)

    def test_skill_has_cross_host_board_entrypoint(self):
        content = SKILL.read_text(encoding="utf-8")
        for phrase in (
            "## Experiment Board",
            "game_exp_board",
            "read-only projection",
            "health=FAIL",
            "ChatGPT Work",
            "Codex",
            "host's authorized source-editing capability",
            "总览",
            "待处理",
            "原型",
            "分支图",
            "归档",
            "stable `subject`",
            "system-generated panel entries in natural Chinese",
            "`relationships`",
            "references/chat-ui.md",
        ):
            self.assertIn(phrase, content)

        board = (
            PLUGIN / "skills" / "game-exp" / "references" / "board.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "Repository -> Subject/Prototype -> Experiment",
            "需要处理",
            "当前进行",
            "仓库级/未指定原型",
            "禁止继续；重建实验",
            "DO_NOT_USE_RECREATE_EXPERIMENT",
            "views.overview.attention_ids",
            "views.prototypes.groups",
            "views.branches.lanes",
            "views.archive.experiment_ids",
            "views.attention.sections",
            "活动时间线",
            "需要你评审",
            "需要你决策",
            "依赖",
            "阻塞",
            "替代",
            "中文展示约束",
            "聚焦筛选",
            "focus.experiment_ids",
            "attention_only",
            "counts_by_lifecycle",
            "counts_by_health",
            "advanced focused-panel tools",
            "judgement.success_criteria",
            "GAME_EXP_ENABLE_ADVANCED_TOOLS=1",
            "relationship_edges",
            "发起人",
            "代码贡献者",
            "contributors_complete",
            "display.rows_zh",
            "display.summary_text_zh",
            "display.presentation_version >= 4",
            "仓库检查",
            "never `医生检查`",
            "实验记录快照",
            "Do not append machine codes",
            "strict_primary_copy",
            "forbidden_primary_tokens",
        ):
            self.assertIn(phrase, board)


    def test_workflow_reference_maps_board_tool(self):
        content = (PLUGIN / "skills" / "game-exp" / "references" / "workflow.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("Open experiment Board / panel", content)
        self.assertIn("game_exp_board", content)
        self.assertTrue((PLUGIN / "skills" / "game-exp" / "references" / "github-bridge.md").exists())
        self.assertTrue((PLUGIN / "skills" / "game-exp" / "references" / "board.md").exists())
        self.assertTrue((PLUGIN / "skills" / "game-exp" / "references" / "chat-ui.md").exists())
        self.assertTrue((PLUGIN / "skills" / "game-exp" / "references" / "onboarding.md").exists())
        self.assertTrue((PLUGIN / "skills" / "game-exp" / "references" / "prototype-handoff.md").exists())
        self.assertTrue((PLUGIN / "skills" / "game-exp" / "references" / "exploration-thread.md").exists())
        self.assertTrue((PLUGIN / "skills" / "game-exp" / "references" / "notifications.md").exists())
        self.assertTrue((PLUGIN / "skills" / "game-exp" / "references" / "public-contract.md").exists())
        self.assertTrue((PLUGIN / "skills" / "game-exp" / "references" / "conformance.md").exists())
        self.assertTrue((PLUGIN / "skills" / "game-exp" / "references" / "project-setup.md").exists())

    def test_complete_project_setup_contract_is_fail_closed(self):
        skill = SKILL.read_text(encoding="utf-8")
        setup = (
            PLUGIN / "skills" / "game-exp" / "references" / "project-setup.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "## Complete project setup",
            "game_exp_project_preflight",
            "game_exp_project_init",
            "PROJECT_READY",
            "Shared/streamable HTTP MCP must never perform",
        ):
            self.assertIn(phrase, skill)
        for phrase in (
            "PROJECT_READY",
            "RULESETS_PLAN_UNSUPPORTED",
            "Trusted Writer self-test",
            "repo-level `game_exp_doctor` returns `PASS`",
            "never change repository visibility without explicit user approval",
            "There is no \"weak private Free\" compatibility mode",
        ):
            self.assertIn(phrase, setup)

    def test_project_create_contract_is_private_by_default_and_non_overwriting(self):
        skill = SKILL.read_text(encoding="utf-8")
        setup = (
            PLUGIN / "skills" / "game-exp" / "references" / "project-setup.md"
        ).read_text(encoding="utf-8")
        contract = (
            PLUGIN / "skills" / "game-exp" / "references" / "public-contract.md"
        ).read_text(encoding="utf-8")
        onboarding = (
            PLUGIN / "skills" / "game-exp" / "references" / "onboarding.md"
        ).read_text(encoding="utf-8")

        for phrase in (
            "game_exp_project_create",
            "Default visibility to **private**",
            "first-experiment onboarding",
        ):
            self.assertIn(phrase, skill)
        for phrase in (
            "latest tagged companion starter",
            "default visibility is private",
            "Never overwrite an existing local directory or GitHub repository",
            "Never automatically change a private repository to public",
        ):
            self.assertIn(phrase, setup)
        for phrase in (
            "game_exp_project_create",
            "default repository visibility is `private`",
            "never overwritten",
            "shared/streamable HTTP MCP must reject project creation",
        ):
            self.assertIn(phrase, contract)
        self.assertIn("project-create", onboarding)

    def test_conformance_contract_is_screening_only(self):
        skill = SKILL.read_text(encoding="utf-8")
        reference = (
            PLUGIN / "skills" / "game-exp" / "references" / "conformance.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "## Harness conformance screening",
            "eligible_for_real_repo_test=true",
            "same `suite_digest`",
            "optional conformance tools",
        ):
            self.assertIn(phrase, skill)
        for phrase in (
            "game_exp_conformance_suite",
            "game_exp_conformance_start",
            "game_exp_conformance_result",
            "game_exp_conformance_compare",
            "game-exp-standing-v1",
            "lost-response-recovery",
            "authorization-no-fallback",
            "review-bound-to-candidate",
            "stale-rehearsal-refresh",
            "dependency-review-required",
            "human-gate-preserved",
            "abandon-without-review",
            "not a substitute for trusted end-to-end validation",
        ):
            self.assertIn(phrase, reference)

    def test_chat_inline_ui_contract_is_read_only_and_has_fallback(self):
        content = (
            PLUGIN / "skills" / "game-exp" / "references" / "chat-ui.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "仓库总览 -> 原型/主体 -> 单实验",
            "总览",
            "待处理",
            "原型",
            "分支图",
            "归档",
            "local filtering",
            "It must not directly mutate lifecycle state or protected refs",
            "trusted MCP/workflow path",
            "READ_ONLY",
            "发起人",
            "代码贡献者",
            "display.rows_zh",
            "display.summary_text_zh",
            "never `医生检查`",
            "diagnostics-only",
            "Text fallback",
        ):
            self.assertIn(phrase, content)

    def test_first_use_onboarding_contract_preserves_trust_and_human_gates(self):
        content = (
            PLUGIN / "skills" / "game-exp" / "references" / "onboarding.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "连接检查",
            "描述第一个实验",
            "生成实验定义",
            "建立实验",
            "开发与试玩",
            "人工决定",
            "game_exp_status",
            "version_state",
            "READ_ONLY",
            "WRITE",
            "ADMIN",
            "game_exp_doctor",
            "game_exp_experiment_bind",
            "game_exp_initialize",
            "PASS does not auto-promote",
            "ACCEPTED dispatch",
            "创建第一个实验",
            "跳过新手引导",
        ):
            self.assertIn(phrase, content)

    def test_collaboration_and_prototype_handoff_contracts(self):
        notifications = (
            PLUGIN / "skills" / "game-exp" / "references" / "notifications.md"
        ).read_text(encoding="utf-8")
        exploration = (
            PLUGIN / "skills" / "game-exp" / "references" / "exploration-thread.md"
        ).read_text(encoding="utf-8")
        handoff = (
            PLUGIN / "skills" / "game-exp" / "references" / "prototype-handoff.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "event_id",
            "external adapter",
            "new experiment",
            "发起人",
        ):
            self.assertIn(phrase, notifications)
        for phrase in (
            "NOT a command to generate multiple variants in parallel",
            "one active experiment",
            "manifest.relationships",
        ):
            self.assertIn(phrase, exploration)
        for phrase in (
            "game_exp_prototype_handoff",
            "Godot Prototype Studio",
            "source SHA",
            "Candidate/Review",
        ):
            self.assertIn(phrase, handoff)

    def test_cross_interface_contract_is_recovery_safe(self):
        skill = SKILL.read_text(encoding="utf-8")
        contract = (
            PLUGIN / "skills" / "game-exp" / "references" / "public-contract.md"
        ).read_text(encoding="utf-8")
        notifications = (
            PLUGIN / "skills" / "game-exp" / "references" / "notifications.md"
        ).read_text(encoding="utf-8")
        handoff = (
            PLUGIN / "skills" / "game-exp" / "references" / "prototype-handoff.md"
        ).read_text(encoding="utf-8")
        board = (
            PLUGIN / "skills" / "game-exp" / "references" / "board.md"
        ).read_text(encoding="utf-8")

        for phrase in (
            "MCP tools",
            "CLI",
            "GitHub Bridge",
            "game_exp_operation_get",
            "game_exp_operation_resume",
            "authorization failure",
            "recovery mode",
        ):
            self.assertIn(phrase, skill)
        self.assertIn("game_exp_capabilities", contract)

        for phrase in (
            "Current public contract: `1.0`",
            "## Board presentation contract",
            "display.presentation_version >= 4",
            "presentation.primary=display",
            "strict_primary_copy=true",
            "forbidden_primary_tokens",
            "医生检查",
            "Same id + same request",
            "Same id + different request",
            "Authorization failure",
            "execution.claim",
            "Trusted Writer",
            "Interface availability is not permission",
            "CURSOR_EXPIRED",
            "Handoff schema v2",
            "A2A",
        ):
            self.assertIn(phrase, contract)

        for phrase in (
            "checkpoint_cursor",
            "next_cursor",
            "CURSOR_EXPIRED",
            "event_version",
            "viewer_login",
        ):
            self.assertIn(phrase, notifications)

        for phrase in (
            "Handoff schema v2",
            "build_identity",
            "portable",
            "source SHA",
        ):
            self.assertIn(phrase, handoff)

        for phrase in (
            "DEPENDENCY_REVIEW_REQUIRED",
            "blocks_progress=false",
            "Lifecycle alone is insufficient",
        ):
            self.assertIn(phrase, board)

    def test_collaboration_coordination_is_explicit_state_not_agent_chat(self):
        skill = SKILL.read_text(encoding="utf-8")
        workflow = (
            PLUGIN / "skills" / "game-exp" / "references" / "workflow.md"
        ).read_text(encoding="utf-8")
        contract = (
            PLUGIN / "skills" / "game-exp" / "references" / "public-contract.md"
        ).read_text(encoding="utf-8")
        collaboration = (
            PLUGIN / "skills" / "game-exp" / "references" / "collaboration.md"
        ).read_text(encoding="utf-8")

        for phrase in (
            "## Collaboration preflight for source work",
            "game_exp_collaboration_context",
            "game_exp_work_claim",
            "game_exp_work_release",
            "does not require another user approval",
            "Never spawn additional Agents merely because a claim overlaps",
            "Unpublished local edits are not recoverable through game-exp",
            "HANDED_OFF",
        ):
            self.assertIn(phrase, skill)

        for phrase in (
            "## Collaboration coordination",
            "`STALE`: synchronize before source edits",
            "Scope overlap is surfaced but not hard-locked",
        ):
            self.assertIn(phrase, workflow)

        for phrase in (
            "Collaboration coordination contract v2",
            "features.collaboration_coordination_v2=true",
            "DOMAIN_CLIENT_UPGRADE_REQUIRED",
            "WORK_SCOPE_OVERLAP",
            "blocking=false",
            "participant_reported",
        ):
            self.assertIn(phrase, contract)

        for phrase in (
            "out-of-sync",
            "not a hard lock",
            "explicit execution-state handoff",
            "persistent Conflict objects",
            "Protected execution preconditions",
            "CAID",
            "SyncMind",
            "CooperBench",
            "Claim Plane",
            "does **not** add CRDT editing",
        ):
            self.assertIn(phrase, collaboration)

    def test_iteration_routing_defaults_to_revision_without_silent_new_experiment(self):
        skill = SKILL.read_text(encoding="utf-8")
        workflow = (
            PLUGIN / "skills" / "game-exp" / "references" / "workflow.md"
        ).read_text(encoding="utf-8")
        contract = (
            PLUGIN / "skills" / "game-exp" / "references" / "public-contract.md"
        ).read_text(encoding="utf-8")

        for phrase in (
            "Default to a **revision of the current experiment**",
            "Do not ask the user to choose between internal labels",
            "ask for confirmation before Bind/Initialize",
            "Revision classification may be automatic; new-experiment creation must not be silent",
            "prior current Review binding",
        ):
            self.assertIn(phrase, skill)

        for phrase in (
            "same-experiment revision",
            "new Candidate",
            "ask before creating the new Issue/Bind/Initialize operation",
            "one question about the actual design intent",
        ):
            self.assertIn(phrase, workflow)

        for phrase in (
            "Iteration routing policy v1",
            "features.iteration_routing_v1=true",
            "A Harness may infer that a request crosses an experiment boundary",
        ):
            self.assertIn(phrase, contract)

    def test_prototype_executors_are_optional_and_non_blocking(self):
        skill = SKILL.read_text(encoding="utf-8")
        handoff = (
            PLUGIN / "skills" / "game-exp" / "references" / "prototype-handoff.md"
        ).read_text(encoding="utf-8")
        contract = (
            PLUGIN / "skills" / "game-exp" / "references" / "public-contract.md"
        ).read_text(encoding="utf-8")

        for phrase in (
            "check the current host's available Skill/tool catalog",
            "https://github.com/siskosun/godot-prototype-studio",
            "https://github.com/siskosun/h5-game-prototype-agent",
            "Missing capability must not make experiment health fail",
            "not mandatory dependencies",
            "never claim specialized validation that was not run",
            "READY_FOR_PLAYTEST",
        ):
            self.assertIn(phrase, skill)

        for phrase in (
            "Godot Prototype Studio (`godot-prototype-studio`)",
            "H5 Game Prototype Agent (`h5-game-prototype-agent`)",
            "missing executor capability does not change repository health",
            "READY_FOR_PLAYTEST",
            "repository root",
        ):
            self.assertIn(phrase, handoff)

        for phrase in (
            "Optional implementation capability contract v1",
            "features.optional_implementation_capabilities_v1=true",
            "recommended_capabilities.godot_prototype_studio",
            "recommended_capabilities.h5_game_prototype_agent",
            "Handoff schema v2 remains compatible",
        ):
            self.assertIn(phrase, contract)

    def test_plugin_contains_exactly_one_skill_entrypoint(self):
        entrypoints = list(PLUGIN.glob("skills/**/SKILL.md"))
        self.assertEqual(entrypoints, [SKILL])


    def test_evaluation_evidence_contract_preserves_human_authority(self):
        skill = SKILL.read_text(encoding="utf-8")
        evaluation = (
            PLUGIN / "skills" / "game-exp" / "references" / "evaluation.md"
        ).read_text(encoding="utf-8")
        for phrase in (
            "## Evaluation Evidence v1",
            "project-policy schema v3",
            "explicit confirmation before Bind",
            "ELIGIBLE",
            "INELIGIBLE",
            "INCONCLUSIVE",
            "incumbent-challenger-blind-ab-v1",
            "Do not add Elo",
        ):
            self.assertIn(phrase, skill)
        for phrase in (
            "content-addressed Evaluation Profile",
            "clean evaluation boundary",
            "TRUSTED_OBSERVED",
            "PARTICIPANT_REPORTED",
            "HUMAN_REPORTED",
            "No authoritative Comparison Set object",
            "Screening is evidence only",
            "human FAIL Review / REJECTED",
        ):
            self.assertIn(phrase, evaluation)


if __name__ == "__main__":
    unittest.main()
