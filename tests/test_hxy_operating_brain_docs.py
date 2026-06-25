import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HxyOperatingBrainDocsTest(unittest.TestCase):
    def test_design_contract_defines_premium_light_operating_brain(self):
        path = ROOT / "docs" / "ui" / "hxy-operating-brain-design-contract.md"
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")

        for phrase in [
            "低饱和浅色",
            "莫兰迪",
            "悬浮胶囊操作栏",
            "Apple 级克制",
            "经营结果交付台",
            "不使用纯白大底",
        ]:
            self.assertIn(phrase, text)

    def test_memory_and_skill_contract_keeps_hxy_boundary(self):
        path = ROOT / "docs" / "architecture" / "hxy-operating-memory-and-skills.md"
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")

        for phrase in [
            "Supermemory",
            "Memory Layer",
            "HXY Operating Skill",
            "矛盾处理",
            "用户画像",
            "PostgreSQL + pgvector",
            "/root/hxy",
            "不得接入 /root/htops",
        ]:
            self.assertIn(phrase, text)

    def test_operating_brain_foundation_defines_fusion_and_training_strategy(self):
        path = ROOT / "docs" / "architecture" / "hxy-operating-memory-and-skills.md"
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")

        for phrase in [
            "运营大脑不是项目资料问答页",
            "project_knowledge",
            "operating_data",
            "market_intelligence",
            "operating_methodology",
            "organizational_memory",
            "role_context",
                "不做预训练",
            ]:
                self.assertIn(phrase, text)

    def test_understanding_engine_uses_depth_x_application_contract(self):
        design_path = ROOT / "docs" / "plans" / "2026-06-18-hxy-understanding-engine-design.md"
        architecture_path = ROOT / "docs" / "architecture" / "hxy-operating-memory-and-skills.md"
        self.assertTrue(design_path.exists())
        self.assertTrue(architecture_path.exists())
        design = design_path.read_text(encoding="utf-8")
        architecture = architecture_path.read_text(encoding="utf-8")
        combined = design + "\n" + architecture

        for phrase in [
            "深度维度 × 应用维度",
            "Intent Recognition Layer",
            "Conflict Element",
            "Priority Matrix",
            "Executability Gate",
            "Knowledge Evolution Layer",
            "D1_perception",
            "D5_judgment",
            "A1_role_output",
            "A5_memory_evolution",
            "impact * urgency * controllability * strategic_relevance",
        ]:
            self.assertIn(phrase, combined)

        self.assertIn("不采用单线性的 0-6 层逻辑", architecture)

    def test_execution_loop_documents_turn_loop_engineering_into_hxy_contract(self):
        claude_path = ROOT / "CLAUDE.md"
        loop_path = ROOT / "docs" / "project-brain" / "agents" / "02-execution-loop.md"
        workflow_path = ROOT / "docs" / "project-brain" / "agents" / "03-claude-code-workflow.md"
        template_path = ROOT / "docs" / "project-brain" / "samples" / "task-loop-template.md"
        index_path = ROOT / "docs" / "project-brain" / "PROJECT-INDEX.md"
        agent_map_path = ROOT / "docs" / "project-brain" / "agents" / "01-agent-map.md"

        for path in [claude_path, loop_path, workflow_path, template_path, index_path, agent_map_path]:
            self.assertTrue(path.exists())

        claude = claude_path.read_text(encoding="utf-8")
        loop = loop_path.read_text(encoding="utf-8")
        workflow = workflow_path.read_text(encoding="utf-8")
        template = template_path.read_text(encoding="utf-8")
        index = index_path.read_text(encoding="utf-8")
        agent_map = agent_map_path.read_text(encoding="utf-8")
        combined = "\n".join([claude, loop, workflow, template, index, agent_map])

        for phrase in [
            "Loop Engineering",
            "goal",
            "context_budget",
            "tool_or_agent",
            "evaluation",
            "stop_condition",
            "hard iteration limit",
            "max iterations reached",
            "goal drift",
            "Execution Loop",
            "Claude Code Workflow",
            "Harness",
            "Handoff",
            "Task Loop Template",
            "HXY Execution Loop",
            "HXY is the loop owner",
            "goal drift",
            "context budget",
            "Context Overflow",
        ]:
            self.assertIn(phrase, combined)

        self.assertIn("HXY is the independent operating system for 荷小悦", claude)

    def test_current_stage_product_contract_prioritizes_startup_validation(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        ui_contract = (ROOT / "docs" / "ui" / "hxy-operating-brain-design-contract.md").read_text(encoding="utf-8")
        combined = "\n".join([readme, ui_contract])

        for phrase in [
            "当前阶段主入口",
            "apps/admin-web/index.html",
            "apps/admin-web/startup.html",
            "0-1 项目推进器",
            "核爆点定位",
            "清泡调补养口径",
            "品牌资料沉淀",
            "开店前不把招商、门店日报、客户消费数据作为主入口",
        ]:
            self.assertIn(phrase, combined)


if __name__ == "__main__":
    unittest.main()
