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

    def test_huashu_design_article_is_mapped_to_execution_surface_only(self):
        path = ROOT / "docs" / "project-brain" / "architecture" / "04-hxyos-execution-surface-design-skill.md"
        index_path = ROOT / "docs" / "project-brain" / "PROJECT-INDEX.md"

        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        index = index_path.read_text(encoding="utf-8")
        combined = "\n".join([text, index])

        for phrase in [
            "Huashu Design",
            "Execution Surface",
            "外部参考资料",
            "不能作为 HXY 权威知识",
            "不改变 Week 1 对外话术风险优先级",
            "品牌资产协议",
            "反 AI Slop",
            "Playwright 验证",
            "五维设计评审",
            "HXY UI Prototype Skill",
            "knowledge/raw/external-references",
        ]:
            self.assertIn(phrase, combined)

    def test_ai_native_dev_article_is_mapped_to_dev_harness_only(self):
        path = ROOT / "docs" / "project-brain" / "agents" / "04-ai-native-dev-harness.md"
        index_path = ROOT / "docs" / "project-brain" / "PROJECT-INDEX.md"

        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")
        index = index_path.read_text(encoding="utf-8")
        combined = "\n".join([text, index])

        for phrase in [
            "Code is cheap",
            "AI Native Dev Harness",
            "外部参考资料",
            "不能作为",
            "HXY 权威业务知识",
            "No Spec, No Code",
            "Minimum Chaos Unit",
            "Codemap",
            "Checkpoint",
            "New Chat / Handoff",
            "多层 Safety Net",
            "scripts/run-hxy-loop.py",
            "frontend_regression",
            "startup.html",
            "首店今日动作台",
        ]:
            self.assertIn(phrase, combined)

    def test_agent_memory_contract_defines_cognitive_layers_retrieval_and_forgetting(self):
        path = ROOT / "docs" / "architecture" / "hxy-operating-memory-and-skills.md"
        self.assertTrue(path.exists())
        text = path.read_text(encoding="utf-8")

        for phrase in [
            "Agent Memory Cognitive Contract",
            "不是数据库三级缓存",
            "Working Memory",
            "Short-Term Memory",
            "Long-Term Memory",
            "上下文预算",
            "semantic relevance",
            "recency",
            "importance",
            "authority status",
            "遗忘不是删除",
            "decay_score",
            "hot / warm / cold",
            "过程记忆不能作为权威依据",
            "正确的信息在正确时间出现在正确位置",
        ]:
            self.assertIn(phrase, text)

    def test_p0_answer_card_governance_runbook_documents_manual_gates(self):
        path = ROOT / "docs" / "operations" / "hxy-p0-answer-card-governance-runbook.md"
        index_path = ROOT / "docs" / "project-brain" / "PROJECT-INDEX.md"
        self.assertTrue(path.exists())
        self.assertTrue(index_path.exists())

        text = path.read_text(encoding="utf-8")
        index = index_path.read_text(encoding="utf-8")
        combined = "\n".join([text, index])

        for phrase in [
            "HXY P0 Answer Card Governance Runbook",
            "p0-review-decisions.stub.json",
            "p0-review-decisions.sample.json",
            "p0-review-decisions.json",
            "validate-hxy-p0-review-decisions.py sample",
            "validate-hxy-p0-review-decisions.py review-packet",
            "p0-manual-review-packet.md",
            "validate-hxy-p0-review-decisions.py init-decisions",
            "validate-hxy-p0-review-decisions.py edit-guide",
            "p0-decision-edit-guide.md",
            "validate-hxy-p0-review-decisions.py decision-audit",
            "p0-review-decisions.audit.json",
            "p0-review-decisions.audit.md",
            "needs_decision_audit",
            "stale_decision_audit",
            "audit_fingerprint_digest",
            "sample_fingerprint_digest",
            "validate-hxy-p0-review-decisions.py reviewer-worksheet",
            "p0-reviewer-worksheet.md",
            "validate-hxy-p0-review-decisions.py reviewer-todo",
            "p0-reviewer-todo.json",
            "GET /api/v1/hxy/p0/reviewer-todo",
            "GET /api/v1/hxy/p0/governance-status",
            "POST /api/v1/hxy/p0/decision-preview",
            "decision_preview_validates_payload_without_writing_manual_decisions",
            "run-hxy-p0-governance-safe-next.py",
            "report-hxy-p0-governance-dry-run.py",
            "p0-governance-dry-run-report.json",
            "dry_run_report_does_not_execute_safe_next",
            "human_decision_required",
            "validate-hxy-p0-review-decisions.py decision-report",
            "p0-review-decisions.report.md",
            "needs_decision_report",
            "stale_decision_report",
            "decision_fingerprint_digest",
            "validate-hxy-p0-review-decisions.py validate",
            "p0-publication-preflight.json",
            "p0-approved-card-publication-package.json",
            "publish-hxy-p0-answer-cards.py dry-run",
            "p0-approved-card-publication-dry-run.json",
            "publish-hxy-p0-answer-cards.py publish",
            "--confirm-manual-publication",
            "published-answer-cards.reviewed.json",
            "import-hxy-p0-reviewed-answer-cards.py gate",
            "reviewed-answer-cards.import-gate.json",
            "write_to_database: false",
            "would_import_count: 0",
            "fingerprint",
            "blocked_at_empty_manual_decisions",
            "不得跳过 import gate",
            "不得把 dry-run payload 当 approved answer card",
            "不得自动批准 candidate / draft / process memory",
            "flowchart TD",
            "manual_decisions",
            "reviewed_file",
            "import_gate",
            "HXY P0 Answer Card Governance Runbook",
        ]:
            self.assertIn(phrase, combined)

    def test_p0_manual_review_template_documents_human_decision_inputs(self):
        path = ROOT / "docs" / "operations" / "hxy-p0-manual-review-template.md"
        index_path = ROOT / "docs" / "project-brain" / "PROJECT-INDEX.md"
        self.assertTrue(path.exists())
        self.assertTrue(index_path.exists())

        text = path.read_text(encoding="utf-8")
        index = index_path.read_text(encoding="utf-8")
        combined = "\n".join([text, index])

        for phrase in [
            "HXY P0 Manual Review Template",
            "p0-review-decisions.json",
            "compliance-medical-001",
            "compliance-effect-001",
            "compliance-marketing-001",
            "risk-002",
            "approve",
            "reject",
            "needs_revision",
            "pending",
            "source_references",
            "knowledge_version",
            "responsible_owner",
            "effective_scope",
            "risk_review_status",
            "不得自动批准 candidate / draft / process memory",
            "write_to_database: false",
            "publish_allowed: false",
        ]:
            self.assertIn(phrase, combined)


if __name__ == "__main__":
    unittest.main()
