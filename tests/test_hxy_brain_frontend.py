import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class HxyBrainFrontendTest(unittest.TestCase):
    def test_frontdesk_is_minimal_execution_surface_without_governance_workflow(self):
        page = ROOT / "apps" / "admin-web" / "frontdesk.html"
        self.assertTrue(page.exists(), "frontdesk execution surface should exist")
        html = page.read_text(encoding="utf-8")

        for label in [
            "<title>HXYOS 前台</title>",
            "HXYOS 前台",
            "前台速查",
            "不用打字",
            "顾客现在问什么？",
            "第一次来应该选什么？",
            "你们和普通按摩有什么不一样？",
            "为什么有点贵？",
            "做一次有没有效果？",
            "草本泡脚有什么用？",
            "直接说",
            "下一句",
            "别这样说",
            "用标准说法",
            "练一遍",
            "我不会答，提交",
            "现场问答框",
            "自己输入顾客原话",
            "按原话判断",
            "id=\"frontdeskInput\"",
            "id=\"frontdeskAskButton\"",
            "askFrontdeskQuestion",
            "loadApprovedAnswerCards",
            "matchApprovedAnswerCard",
            "/api/knowledge/answer-cards?status=approved",
            "approvedAnswerCards",
            "apiBaseCandidates",
            "http://127.0.0.1:18081",
            'data-question="first"',
            'data-question="difference"',
            'data-question="price"',
            'data-question="effect"',
            'data-question="herbal"',
            'aria-pressed="true"',
            'aria-pressed="false"',
            'id="currentQuestion"',
            'id="frontdeskOutput"',
            "renderQuestion",
            "activeQuestion",
            "questionButtons",
            "focus-visible",
        ]:
            self.assertIn(label, html)

        for forbidden in [
            "待审核",
            "审核",
            "发布",
            "候选",
            "证据链",
            "知识图谱",
            "版本流转",
            "claim",
            "reference",
            "needs_review",
            "approved answer card",
            "复核队列",
            "资料入库",
            "风险评分",
            "今天只做三件事",
            "现场工作流",
            "第 1 步",
            "第 2 步",
            "第 3 步",
            "第 4 步",
            "data-step",
            'data-mode=',
            "renderMode",
        ]:
            self.assertNotIn(forbidden, html)

    def test_admin_default_entry_is_hxyos_task_gateway_with_qa_box(self):
        page = ROOT / "apps" / "admin-web" / "index.html"
        self.assertTrue(page.exists(), "admin default entry should exist")
        html = page.read_text(encoding="utf-8")

        for label in [
            "<title>HXYOS 工作台</title>",
            "HXYOS 工作台",
            "今天要做什么？",
            "前台怎么说",
            "开业还差什么",
            "这句话能不能发",
            "资料变成知识",
            "问答框",
            "先问一句",
            "id=\"homeQuestionInput\"",
            "id=\"homeAskButton\"",
            "id=\"homeAnswer\"",
            "askHomeQuestion",
            "frontdesk.html",
            "startup.html",
            "brand-check.html",
            "knowledge.html",
        ]:
            self.assertIn(label, html)

        for label in [
            "招商",
            "加盟",
            "门店日报",
            "客户消费",
            "POS",
            "多店看板",
            "http-equiv=\"refresh\"",
        ]:
            self.assertNotIn(label, html)

    def test_admin_entry_is_dataagent_style_three_layer_console(self):
        page = ROOT / "apps" / "admin-web" / "index.html"
        self.assertTrue(page.exists(), "admin default entry should exist")
        html = page.read_text(encoding="utf-8")

        for marker in [
            'data-layer="frontstage"',
            'data-layer="middle-platform"',
            'data-layer="backstage"',
            "前台",
            "一个问答框 + 场景工作流",
            "场景工作流",
            "前台接待",
            "对外发布",
            "首店开业",
            "资料入库",
            "员工训练",
            "经营复盘",
            "中台",
            "知识引擎",
            "检索应用",
            "Skill",
            "Agent",
            "记忆",
            "后台",
            "审核",
            "权限",
            "版本",
            "运行记录",
            "评测",
            "监控",
        ]:
            self.assertIn(marker, html)

        self.assertEqual(html.count('id="homeQuestionInput"'), 1)
        self.assertIn("frontdesk.html", html)
        self.assertIn("brand-check.html", html)
        self.assertIn("startup.html", html)
        self.assertIn("knowledge.html", html)
        self.assertIn("../employee-web/training.html", html)
        self.assertIn("brain.html", html)

    def test_home_frontstage_does_not_leak_backstage_governance_terms(self):
        html = (ROOT / "apps" / "admin-web" / "index.html").read_text(encoding="utf-8")
        front_start = html.index('data-layer="frontstage"')
        front_end = html.index('data-layer="middle-platform"', front_start)
        front_html = html[front_start:front_end]

        for label in [
            "一个问答框 + 场景工作流",
            "前台接待",
            "对外发布",
            "首店开业",
            "资料入库",
            "员工训练",
            "经营复盘",
        ]:
            self.assertIn(label, front_html)

        for forbidden in [
            "审核",
            "权限",
            "版本",
            "运行记录",
            "评测",
            "监控",
            "claim",
            "chunk_id",
            "review queue",
            "needs_review",
            "P0 合规",
            "合规审核包",
        ]:
            self.assertNotIn(forbidden, front_html)

    def test_brand_check_is_front_stage_expression_checker_not_review_console(self):
        page = ROOT / "apps" / "admin-web" / "brand-check.html"
        self.assertTrue(page.exists(), "brand expression checker should exist")
        html = page.read_text(encoding="utf-8")

        for label in [
            "<title>HXYOS 说法检查</title>",
            "HXYOS 说法检查",
            "动作前预检",
            "这句话能不能发？",
            "先预检，不直接发布",
            "把准备使用的话贴进来",
            "用途",
            "发出去",
            "给员工说",
            "放进项目菜单",
            "立即预检",
            "可以继续",
            "先改再继续",
            "不要继续",
            "能不能继续",
            "为什么",
            "怎么改",
            "下一步",
            "医疗",
            "保证",
            "夸大",
            "id=\"brandTextInput\"",
            "id=\"brandPurposeSelect\"",
            "id=\"brandApiToken\"",
            "id=\"brandCheckResult\"",
            "系统口令",
            "连接企业预检",
            "hxyActionApiToken",
            "hxyBrainApiToken",
            "hxyKnowledgeApiToken",
            "runBrandPreflight",
            "renderBrandPreflightResult",
            "buildBrandPreflightPayload",
            "apiBaseCandidates",
            'headers.set("Authorization", `Bearer ${token}`)',
            'localStorage.setItem("hxyActionApiToken"',
            "http://127.0.0.1:18081",
            "defaultRiskRules",
            "riskRules",
            "loadBrandRiskRules",
            "/api/operating-brain/brand-risk-rules",
            "/api/operating-brain/workflow-gates/compliance/run",
            "index.html",
        ]:
            self.assertIn(label, html)

        for forbidden in [
            "待审核",
            "审核队列",
            "发布队列",
            "批准",
            "claim",
            "reference",
            "needs_review",
            "资料入库",
            "知识图谱",
            "审核人",
            "合规审核包",
            "P0 合规",
            "review queue",
            "招商",
            "加盟",
        ]:
            self.assertNotIn(forbidden, html)

    def test_brand_check_allows_boundary_language_for_forbidden_terms(self):
        page = ROOT / "apps" / "admin-web" / "brand-check.html"
        html = page.read_text(encoding="utf-8")
        script = html.split("<script>", 1)[1].split("</script>", 1)[0]
        runner = textwrap.dedent(
            f"""
            const vm = require("node:vm");
            const elements = {{
              brandTextInput: {{
                value: "我们不做祛湿排毒承诺，也不能替代医疗治疗。可以说草本现煮，泡着舒服。",
                focus() {{}}
              }},
              brandPurposeSelect: {{ value: "content_publish" }},
              brandApiToken: {{ value: "" }},
              brandCheckResult: {{ innerHTML: "" }}
            }};
            const context = {{
              console,
              window: {{ location: {{ origin: "null" }} }},
              localStorage: {{
                getItem() {{ return ""; }},
                setItem() {{}}
              }},
              fetch: async () => {{ throw new Error("offline"); }},
              document: {{
                getElementById(id) {{ return elements[id]; }}
              }}
            }};
            vm.createContext(context);
            vm.runInContext({script!r}, context);
            (async () => {{
              await vm.runInContext("runBrandPreflight()", context);
              process.stdout.write(elements.brandCheckResult.innerHTML);
            }})().catch((error) => {{
              console.error(error);
              process.exit(1);
            }});
            """
        )
        result = subprocess.run(
            ["node", "-e", runner],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        self.assertIn("可以继续", result.stdout)
        self.assertNotIn("不要继续", result.stdout)

    def test_brand_check_renders_workflow_gate_result_from_api(self):
        page = ROOT / "apps" / "admin-web" / "brand-check.html"
        html = page.read_text(encoding="utf-8")
        script = html.split("<script>", 1)[1].split("</script>", 1)[0]
        runner = textwrap.dedent(
            f"""
            const vm = require("node:vm");
            const calls = [];
            const elements = {{
              brandTextInput: {{
                value: "泡一次就能治疗失眠，保证一周见效。",
                focus() {{}}
              }},
              brandPurposeSelect: {{ value: "staff_script" }},
              brandApiToken: {{ value: "front-token" }},
              brandCheckResult: {{ innerHTML: "" }}
            }};
            const context = {{
              console,
              Headers,
              window: {{ location: {{ origin: "http://127.0.0.1:18084" }} }},
              localStorage: {{
                getItem(key) {{ return key === "hxyActionApiToken" ? "front-token" : ""; }},
                setItem() {{}}
              }},
              fetch: async (url, options = {{}}) => {{
                calls.push([url, options]);
                if (String(url).includes("/brand-risk-rules")) {{
                  return {{ ok: true, json: async () => ({{ rules: [] }}) }};
                }}
                return {{
                  ok: true,
                  json: async () => ({{
                    decision: "block",
                    workflow_status: "blocked",
                    risk_level: "high",
                    risk_reason: "涉及治疗和保证效果表达。",
                    rewrite_suggestion: "可以说泡着舒服，适合下班后来放松一下。",
                    next_step: "先改掉风险表达，再交给运营负责人确认。",
                    human_owner: "运营负责人",
                    hit_gates: ["medical_claim", "guaranteed_effect"],
                    can_publish: false,
                    official_use_allowed: false
                  }})
                }};
              }},
              document: {{
                getElementById(id) {{ return elements[id]; }}
              }}
            }};
            vm.createContext(context);
            vm.runInContext({script!r}, context);
            (async () => {{
              await vm.runInContext("runBrandPreflight()", context);
              process.stdout.write(JSON.stringify({{
                html: elements.brandCheckResult.innerHTML,
                workflowCall: calls.find(([url]) => String(url).includes("/workflow-gates/compliance/run")),
                authorization: calls.find(([url]) => String(url).includes("/workflow-gates/compliance/run"))?.[1]?.headers?.get("Authorization"),
              }}));
            }})().catch((error) => {{
              console.error(error);
              process.exit(1);
            }});
            """
        )
        result = subprocess.run(
            ["node", "-e", runner],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = __import__("json").loads(result.stdout)
        self.assertIn("/api/operating-brain/workflow-gates/compliance/run", payload["workflowCall"][0])
        self.assertIn('"workflow_type":"staff_script"', payload["workflowCall"][1]["body"])
        self.assertEqual(payload["authorization"], "Bearer front-token")
        self.assertIn("不要继续", payload["html"])
        self.assertIn("涉及治疗和保证效果表达", payload["html"])
        self.assertIn("可以说泡着舒服", payload["html"])
        self.assertIn("先改掉风险表达", payload["html"])

    def test_brand_check_reuses_existing_admin_tokens_for_workflow_gate(self):
        page = ROOT / "apps" / "admin-web" / "brand-check.html"
        html = page.read_text(encoding="utf-8")
        script = html.split("<script>", 1)[1].split("</script>", 1)[0]
        runner = textwrap.dedent(
            f"""
            const vm = require("node:vm");
            const calls = [];
            const saved = [];
            const elements = {{
              brandTextInput: {{
                value: "草本现煮，泡着舒服，适合下班后来放松一下。",
                focus() {{}}
              }},
              brandPurposeSelect: {{ value: "content_publish" }},
              brandApiToken: {{ value: "" }},
              brandCheckResult: {{ innerHTML: "" }}
            }};
            const stored = {{
              hxyBrainApiToken: "brain-token",
              hxyKnowledgeApiToken: "knowledge-token"
            }};
            const context = {{
              console,
              Headers,
              window: {{ location: {{ origin: "http://127.0.0.1:18084" }} }},
              localStorage: {{
                getItem(key) {{ return stored[key] || ""; }},
                setItem(key, value) {{ saved.push([key, value]); }}
              }},
              fetch: async (url, options = {{}}) => {{
                calls.push([url, options]);
                if (String(url).includes("/brand-risk-rules")) {{
                  return {{ ok: true, json: async () => ({{ rules: [] }}) }};
                }}
                return {{
                  ok: true,
                  json: async () => ({{
                    decision: "allow",
                    workflow_status: "can_continue",
                    risk_reason: "没有命中高风险规则。",
                    rewrite_suggestion: "草本现煮，泡着舒服，适合下班后来放松一下。",
                    next_step: "交给负责人确认后再使用。"
                  }})
                }};
              }},
              document: {{
                getElementById(id) {{ return elements[id]; }}
              }}
            }};
            vm.createContext(context);
            vm.runInContext({script!r}, context);
            (async () => {{
              await vm.runInContext("runBrandPreflight()", context);
              process.stdout.write(JSON.stringify({{
                tokenValue: elements.brandApiToken.value,
                saved,
                workflowCall: calls.find(([url]) => String(url).includes("/workflow-gates/compliance/run")),
                authorization: calls.find(([url]) => String(url).includes("/workflow-gates/compliance/run"))?.[1]?.headers?.get("Authorization"),
              }}));
            }})().catch((error) => {{
              console.error(error);
              process.exit(1);
            }});
            """
        )
        result = subprocess.run(
            ["node", "-e", runner],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )
        payload = __import__("json").loads(result.stdout)
        self.assertEqual(payload["tokenValue"], "brain-token")
        self.assertEqual(payload["authorization"], "Bearer brain-token")
        self.assertIn(["hxyActionApiToken", "brain-token"], payload["saved"])

    def test_knowledge_page_starts_with_front_stage_intake_not_governance_console(self):
        page = ROOT / "apps" / "admin-web" / "knowledge.html"
        self.assertTrue(page.exists(), "knowledge intake page should exist")
        html = page.read_text(encoding="utf-8")

        for label in [
            "HXYOS 资料台",
            "资料变成知识",
            "先把资料放进入口",
            "系统先整理，不直接定稿",
            "能用时再进入工作台",
            "原始资料不是正式答案",
            "进入高级工具",
            "id=\"advancedKnowledgeTools\"",
            "openAdvancedKnowledgeTools",
            "/root/hxy/knowledge/raw/inbox",
        ]:
            self.assertIn(label, html)

        front_index = html.index("资料变成知识")
        governance_index = html.index("P0 合规闸门")
        self.assertLess(front_index, governance_index)

    def test_knowledge_page_exposes_review_topics_instead_of_raw_claim_queue(self):
        page = ROOT / "apps" / "admin-web" / "knowledge.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "核心经营议题",
            "品牌战略、定位、产品、话术、首店验证优先",
            "机器摘录不直接展示",
            "品牌战略",
            "定位验证",
            "产品体系",
            "员工话术",
            "合规边界",
            "首店动作",
            "先判断",
            "为什么重要",
            "下一步",
            "id=\"reviewTopics\"",
            "id=\"reviewTopicsMeta\"",
            "renderReviewTopics",
            "refreshReviewTopics",
            "/api/operating-brain/knowledge-compiler/review-topics?limit=12",
            "reviewTopicState",
            "不是正式知识",
            "requires_human_review",
        ]:
            self.assertIn(label, html)

        governance_index = html.index("P0 合规闸门")
        topics_index = html.index("核心经营议题")
        self.assertLess(governance_index, topics_index)

        for forbidden in [
            "候选 Claim 复核",
            "Claim 去噪工作台",
            "原始 claim 不直接展示",
            "让系统把原始 claim 整理成议题",
            "cluster_member_count",
            "duplicate_count",
            "overclaim_risk",
            "转草稿",
            "需修改",
            "驳回",
        ]:
            self.assertNotIn(forbidden, html)

    def test_knowledge_workbench_renders_core_topic_draft_asset_workflow(self):
        page = ROOT / "apps" / "admin-web" / "knowledge.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "议题转资产",
            "建议资产",
            "定位卡",
            "话术卡",
            "SOP卡",
            "风险边界卡",
            "补证据任务",
            "待人工复核",
            "id=\"topicDraftAssetsList\"",
            "id=\"refreshTopicDraftAssetsButton\"",
            "renderTopicDraftAssets",
            "loadTopicDraftAssets",
            "/api/operating-brain/knowledge-compiler/topic-draft-assets?limit=12",
        ]:
            self.assertIn(label, html)

        draft_start = html.index("议题转资产")
        draft_end = html.index("合规审核包", draft_start)
        draft_html = html[draft_start:draft_end]
        for forbidden in ["raw claim", "chunk_id", "cluster_id", "review queue", "needs_review"]:
            self.assertNotIn(forbidden, draft_html)

    def test_knowledge_workbench_renders_topic_review_packets_without_approval_buttons(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for label in [
            "复核任务包",
            "谁看",
            "看什么",
            "允许的判断",
            "不能做什么",
            "needs_more_evidence",
            "revise_draft",
            "ready_for_manual_approval",
            "reject",
            "id=\"topicReviewPacketsList\"",
            "id=\"refreshTopicReviewPacketsButton\"",
            "renderTopicReviewPackets",
            "loadTopicReviewPackets",
            "/api/operating-brain/knowledge-compiler/topic-review-packets?limit=12",
        ]:
            self.assertIn(label, html)

        panel_start = html.index("复核任务包")
        panel_end = html.index("合规审核包", panel_start)
        panel_html = html[panel_start:panel_end]
        for forbidden in ["批准发布", "一键批准", "写入 approved", "chunk_id", "cluster_id", "raw claim"]:
            self.assertNotIn(forbidden, panel_html)

    def test_knowledge_workbench_renders_topic_review_decision_file_workflow(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for label in [
            "人工决策文件",
            "本地 JSON",
            "topic-review-decisions.json",
            "待填写",
            "只做预览校验",
            "ready_for_manual_approval 不是批准",
            "id=\"topicReviewDecisionWorkflow\"",
            "id=\"refreshTopicReviewDecisionsButton\"",
            "renderTopicReviewDecisions",
            "loadTopicReviewDecisions",
            "/api/operating-brain/knowledge-compiler/topic-review-decisions",
            "/api/operating-brain/knowledge-compiler/topic-review-decision-preview",
        ]:
            self.assertIn(label, html)

        panel_start = html.index("人工决策文件")
        panel_end = html.index("合规审核包", panel_start)
        panel_html = html[panel_start:panel_end]
        for forbidden in ["一键批准", "批准发布", "自动发布", "写入 approved", "发布正式知识"]:
            self.assertNotIn(forbidden, panel_html)

    def test_knowledge_page_exposes_compliance_language_check_execution_panel(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for label in [
            "对外话语检查",
            "这句话能不能发",
            "id=\"complianceTextInput\"",
            "id=\"complianceWorkflowTypeSelect\"",
            "id=\"complianceChannelSelect\"",
            "id=\"complianceLanguageCheckResult\"",
            "id=\"runComplianceLanguageCheck\"",
            "runComplianceLanguageCheck",
            "renderComplianceLanguageCheckResult",
            "/api/operating-brain/workflow-gates/compliance/run",
            "内容发布",
            "员工话术",
            "项目菜单",
            "可以发",
            "建议改",
            "不要发",
            "能不能继续",
            "风险等级",
            "命中规则",
            "原因",
            "建议改法",
            "下一步",
            "负责人",
            "不可发布为正式知识",
        ]:
            self.assertIn(label, html)

        for forbidden in [
            "批准为正式知识",
            "发布 approved",
            "cluster_member_count",
            "sample_claims",
            "chunk_id",
            "risk_level：",
            "hit_gates：",
            "risk_reason：",
            "rewrite_suggestion：",
            "can_publish：",
            "official_use_allowed：",
        ]:
            self.assertNotIn(forbidden, html)

    def test_knowledge_page_shows_product_objects_not_raw_artifacts(self):
        page = ROOT / "apps" / "admin-web" / "knowledge.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "知识引擎",
            "检索应用",
            "意图规划",
            "Skill 中心",
            "自动化任务",
            "id=\"productContracts\"",
            "id=\"retrievalApps\"",
            "id=\"intentDefinitions\"",
            "id=\"skillRegistry\"",
            "id=\"automationTasks\"",
            "renderProductContracts",
            "renderRetrievalApps",
            "renderIntentDefinitions",
            "renderSkills",
            "renderAutomationTasks",
            "/api/operating-brain/product-contracts",
            "/api/operating-brain/retrieval-apps",
            "/api/operating-brain/intent-definitions",
            "/api/operating-brain/skills",
            "/api/operating-brain/automation-tasks",
        ]:
            self.assertIn(label, html)

        for forbidden in [
            "cluster_member_count",
            "sample_claims",
            "chunk_id",
            "/root/hxy\"",
        ]:
            self.assertNotIn(forbidden, html)

    def test_startup_stage_product_focuses_on_today_action_not_full_os(self):
        page = ROOT / "apps" / "admin-web" / "startup.html"
        self.assertTrue(page.exists(), "startup stage product page should exist")
        html = page.read_text(encoding="utf-8")

        for label in [
            "<title>HXYOS 首店</title>",
            "HXYOS 首店",
            "首店今日动作台",
            "今天只推进一件事",
            "验证核爆点定位是否成立",
            "今日唯一动作",
            "完成 5 个用户访谈，并录入原话",
            "为什么先做这个",
            "待验证",
            "当前结论",
            "证据缺口",
            "证据状态",
            "用户原话",
            "复述测试",
            "付费理由",
            "替代方案",
            "今日拿到什么证据？",
            "AI 推进草稿",
            "记录证据",
            "更新结论",
            "生成下一步",
            "沉淀为定位卡",
            "id=\"startupEvidenceInput\"",
            "id=\"startupAdvanceStatus\"",
            "id=\"startupAdvanceResult\"",
            "data-progress-action=\"record\"",
            "data-progress-action=\"revise\"",
            "data-progress-action=\"next\"",
            "data-progress-action=\"card\"",
        ]:
            self.assertIn(label, html)

        for item in [
            "/api/operating-brain/brand-assets",
            "/api/operating-brain/brand-answer-cards",
            "/api/operating-brain/evals/golden",
            "/api/operating-brain/startup-advance",
            "loadStartupAssets",
            "renderBrandAnswerCards",
            "currentStartupContext",
            "startupAdvance",
            "renderStartupAdvance",
            "startupAdvanceStatus",
            "startupEvidenceInput",
            "startupAdvanceResult",
            "today-action-board",
            "evidence-panel",
            "startup-loop-actions",
            "data-progress-action",
        ]:
            self.assertIn(item, html)

        for forbidden in [
            "stage-pills",
            "/api/knowledge/chat",
            "startupQuestionInput",
            "runStartupQuestion",
            "data-startup-question",
            "生成判断卡",
            "继续追问",
            "今天要定哪件事？",
            "decision-box",
            "decision-card",
            'class="workspace"',
            'class="rail"',
            'class="inspector"',
            "今日营业额",
            "技师产能",
            "客户消费记录",
            "招商表达风险",
            "招商话术",
            "招商看",
            "回本周期",
            "合伙人",
            "待审核",
            "审核队列",
            "发布",
            "claim",
            "reference",
            "needs_review",
            "知识图谱",
        ]:
            self.assertNotIn(forbidden, html)

    def test_startup_stage_actions_call_ai_progress_loop_not_static_drawer(self):
        html = (ROOT / "apps" / "admin-web" / "startup.html").read_text(encoding="utf-8")

        for label in [
            "AI 推进草稿",
            "把今天拿到的证据、访谈原话或新判断写在这里。",
            "证据门槛",
            "下一步动作",
            "记忆动作",
        ]:
            self.assertIn(label, html)

        for item in [
            'id="startupEvidenceInput"',
            'id="startupAdvanceStatus"',
            'id="startupAdvanceResult"',
            'data-current-action',
            "function currentStartupContext",
            "async function startupAdvance",
            "function renderStartupAdvance",
            "/api/operating-brain/startup-advance",
            "startupAdvance(button.dataset.progressAction)",
            "button.disabled = true",
            "button.disabled = false",
        ]:
            self.assertIn(item, html)

        listener_start = html.index('document.querySelectorAll("[data-progress-action]")')
        listener_end = html.index("loadStartupAssets();", listener_start)
        listener_block = html[listener_start:listener_end]
        self.assertIn("startupAdvance(button.dataset.progressAction)", listener_block)
        self.assertNotIn("toggleEvidenceDrawer(true);\n      });", listener_block)

    def test_startup_evidence_drawer_has_local_action_buttons_after_evidence_input(self):
        html = (ROOT / "apps" / "admin-web" / "startup.html").read_text(encoding="utf-8")
        panel_start = html.index('<section class="evidence-panel"')
        panel_end = html.index("</section>", panel_start)
        drawer_html = html[panel_start:panel_end]

        input_index = drawer_html.index('id="startupEvidenceInput"')
        local_actions_index = drawer_html.index('class="startup-loop-actions"')
        self.assertGreater(local_actions_index, input_index)

        for action, label in [
            ("record", "记录证据"),
            ("revise", "更新结论"),
            ("next", "生成下一步"),
            ("card", "沉淀为定位卡"),
        ]:
            self.assertIn(f'data-progress-action="{action}"', drawer_html)
            self.assertIn(label, drawer_html)

    def test_startup_stage_mobile_keeps_result_area_primary(self):
        html = (ROOT / "apps" / "admin-web" / "startup.html").read_text(encoding="utf-8")
        mobile_start = html.index("@media (max-width: 900px)")
        mobile_css = html[mobile_start:]

        self.assertIn(".startup-shell", mobile_css)
        self.assertIn(".today-action-board", mobile_css)
        self.assertIn(".evidence-panel", mobile_css)
        self.assertIn("grid-template-columns: 1fr;", mobile_css)
        self.assertIn(".startup-loop-actions", mobile_css)
        self.assertIn("grid-template-columns: 1fr;", mobile_css)
        self.assertIn(".top-meta", mobile_css)
        self.assertIn("display: none;", mobile_css)

    def test_startup_primary_action_focuses_evidence_input_before_ai_loop(self):
        html = (ROOT / "apps" / "admin-web" / "startup.html").read_text(encoding="utf-8")
        action_start = html.index('<div class="action-strip">')
        action_end = html.index('      <div class="focus-grid">', action_start)
        action_html = html[action_start:action_end]

        self.assertIn("开始录入", action_html)
        self.assertIn("data-focus-evidence", action_html)
        self.assertNotIn("data-progress-action", action_html)
        self.assertIn("function focusEvidenceInput", html)
        self.assertIn('document.querySelector("[data-focus-evidence]")', html)

    def test_startup_supporting_assets_are_collapsed_below_main_workflow(self):
        html = (ROOT / "apps" / "admin-web" / "startup.html").read_text(encoding="utf-8")

        self.assertIn('<details class="support-panel" aria-label="首店支撑资料">', html)
        self.assertIn("<summary>支撑资料</summary>", html)
        self.assertNotIn('<aside class="support-panel"', html)
        self.assertNotIn('<details class="support-panel" aria-label="首店支撑资料" open>', html)

    def test_startup_mobile_hides_long_summary_copy(self):
        html = (ROOT / "apps" / "admin-web" / "startup.html").read_text(encoding="utf-8")
        mobile_start = html.index("@media (max-width: 900px)")
        mobile_css = html[mobile_start:]

        self.assertIn(".summary", mobile_css)
        summary_mobile_start = mobile_css.index(".summary")
        summary_mobile_end = mobile_css.index("}", summary_mobile_start)
        summary_mobile_css = mobile_css[summary_mobile_start:summary_mobile_end]

        self.assertIn("display: none;", summary_mobile_css)
        self.assertIn("h1", mobile_css)
        self.assertIn("font-size: clamp(30px, 9vw, 44px);", mobile_css)

    def test_brain_page_exposes_answer_evolution_controls(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        self.assertIn("/api/knowledge/review-tasks", html)
        self.assertIn('/resolve', html)
        self.assertIn("/api/knowledge/answer-cards", html)
        self.assertIn("/api/knowledge/import", html)
        self.assertIn('id="reviewTasks"', html)
        self.assertIn('data-resolve-task', html)
        self.assertIn('data-create-card', html)
        self.assertIn('data-create-draft-card', html)
        self.assertIn("correction_package", html)
        self.assertIn("answer_card_draft", html)
        self.assertIn("source_answer_id", html)
        self.assertIn("defaultApiBase", html)
        self.assertIn("window.location.origin", html)

    def test_brain_page_exposes_public_ai_workspace_event_stream(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        for label in [
            "公共 AI 工作间",
            "最新 AI 工作",
            "组织可见",
            "风险标签",
            "复核动作",
            "记忆动作",
            "不是正式知识",
        ]:
            self.assertTrue(label in html, f"missing workspace label: {label}")

        for marker in [
            'id="workspaceEvents"',
            'id="refreshWorkspaceEvents"',
            "/api/operating-brain/workspace/events",
            "refreshWorkspaceEvents",
            "renderWorkspaceEvents",
            "createWorkspaceEvent",
            "data-workspace-review",
            "data-workspace-memory",
        ]:
            self.assertTrue(marker in html, f"missing workspace marker: {marker}")

    def test_brain_page_api_token_is_available_for_workspace_write_actions(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        for marker in [
            'id="apiToken"',
            "hxyBrainApiToken",
            "apiTokenInput",
            'headers.set("Authorization", `Bearer ${token}`)',
            'localStorage.setItem("hxyBrainApiToken"',
            "不影响本次回答",
        ]:
            self.assertTrue(marker in html, f"missing brain api token marker: {marker}")

    def test_brain_page_workspace_copy_does_not_claim_authority(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        workspace_start = html.find("公共 AI 工作间")
        self.assertNotEqual(workspace_start, -1, "brain page should expose public AI workspace section")
        workspace_end = html.find("</section>", workspace_start)
        self.assertNotEqual(workspace_end, -1, "public AI workspace section should be a section")
        workspace_html = html[workspace_start:workspace_end]

        self.assertIn("不是正式知识", workspace_html)
        self.assertNotIn("权威知识发布", workspace_html)
        self.assertNotIn("已批准口径", workspace_html)

    def test_brain_page_is_answer_first_operating_brain(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        self.assertIn("<title>荷小悦经营大脑</title>", html)
        self.assertIn("<h1>荷小悦经营大脑</h1>", html)
        self.assertIn("<h2>0-1 阶段先做三件事</h2>", html)
        self.assertIn("直接输入问题、资料、员工话术或纠偏意见", html)
        self.assertIn("系统会自动判断任务类型", html)
        self.assertIn("当前最重要的经营议题", html)
        self.assertIn("先看结论", html)
        self.assertIn("可执行动作", html)
        self.assertIn("internal-review", html)
        self.assertIn("<summary>查看依据和纠偏", html)
        self.assertNotIn("<h3>判断依据</h3>", html)
        self.assertNotIn("<h3>证据来源</h3>", html)
        self.assertNotIn("<h3>纠偏建议</h3>", html)
        self.assertNotIn("<h3>下一步动作</h3>", html)

    def test_brain_page_matches_operating_brain_product_shape(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        self.assertIn('class="workspace chat-first"', html)
        self.assertIn('class="brain-nav outcome-launcher"', html)
        self.assertIn('class="decision-panel"', html)
        self.assertIn('class="answer-detail inspector-panel is-hidden"', html)
        self.assertIn('class="mobile-actions"', html)
        self.assertIn("data-toggle-status", html)
        self.assertIn("data-toggle-inspector", html)
        self.assertIn("data-close-status", html)
        self.assertIn("data-close-inspector", html)
        self.assertIn("openInspector", html)
        self.assertIn("closeInspector", html)
        self.assertIn("closeStatusPanel", html)
        self.assertIn('workspace.classList.toggle("inspector-open"', html)
        for label in ["问经营", "练员工", "传资料", "统一口径", "招商话术", "门店复盘", "产品体系", "SOP", "用户宣传", "权威答案", "资料记忆", "复核任务"]:
            self.assertIn(label, html)
        for role in ["创始人内部决策", "招商话术", "门店员工培训", "用户端宣传"]:
            self.assertIn(role, html)
        for answer_field in ["经营结果", "可直接使用版本", "风险边界", "质量闸口"]:
            self.assertIn(answer_field, html)
        self.assertIn("默认简洁回答", html)
        self.assertIn("查看依据", html)
        self.assertIn("knowledge_quality", html)
        self.assertIn("data-scenario", html)
        self.assertIn("data-quick-question", html)
        self.assertIn("currentDetail", html)
        self.assertIn("scenario: selectedScenario", html)
        self.assertIn("result.applicable_scenarios", html)
        self.assertIn("result.answer_status", html)
        self.assertIn("result.result_card", html)

    def test_brain_page_exposes_outcome_workflow_launcher_not_generic_chat(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        self.assertIn('class="brain-nav outcome-launcher"', html)
        nav_start = html.index('<nav class="brain-nav outcome-launcher"')
        nav_end = html.index("</nav>", nav_start)
        nav_block = html[nav_start:nav_end]
        for workflow in ["ask", "train", "memory"]:
            self.assertIn(f'data-workflow="{workflow}"', html)
        for workflow in ["standardize", "franchise", "review"]:
            self.assertNotIn(f'data-workflow="{workflow}"', nav_block)
        for label in ["问经营", "练员工", "传资料"]:
            self.assertIn(label, html)
        self.assertIn("判断、口径、复盘", html)
        self.assertIn("打分、纠错、复训任务", html)
        self.assertIn("上传、识别、分类、记忆", html)
        for scene in ["统一口径", "招商话术", "门店复盘", "产品体系", "SOP", "用户宣传"]:
            self.assertIn(f'data-scenario="{scene}"', html)

    def test_brain_page_primary_surface_respects_pre_open_boundary(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        prompt_start = html.index('<section class="task-prompt"')
        prompt_end = html.index("</section>", prompt_start)
        prompt_block = html[prompt_start:prompt_end]

        composer_start = html.index('<div class="composer-tools"')
        composer_end = html.index("</div>", composer_start)
        composer_block = html[composer_start:composer_end]

        self.assertIn("0-1 阶段先做三件事", html)
        for label in [
            "验证核爆点定位",
            "固化清泡调补养口径",
            "整理品牌资料",
        ]:
            self.assertIn(label, prompt_block)

        for forbidden in [
            "招商",
            "加盟",
            "门店日报",
            "今日经营数据",
            "客户消费数据",
        ]:
            self.assertNotIn(forbidden, prompt_block)
            self.assertNotIn(forbidden, composer_block)

        self.assertIn("AI 自动判断", composer_block)
        self.assertNotIn('data-mode="task"', composer_block)

    def test_mobile_outcome_launcher_keeps_three_primary_tasks_visible(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        mobile_start = html.index("@media (max-width: 820px)")
        reduce_motion_start = html.index("@media (prefers-reduced-motion", mobile_start)
        mobile_css = html[mobile_start:reduce_motion_start]

        self.assertIn(".outcome-launcher", mobile_css)
        self.assertIn("grid-template-columns: repeat(3, minmax(0, 1fr));", mobile_css)
        self.assertIn("overflow-x: visible;", mobile_css)
        self.assertIn("min-width: 0;", mobile_css)
        self.assertNotIn(".brain-nav {\n        grid-template-columns: 1fr;", mobile_css)

    def test_mobile_chat_keeps_primary_space_after_launchers(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        mobile_start = html.index("@media (max-width: 820px)")
        reduce_motion_start = html.index("@media (prefers-reduced-motion", mobile_start)
        mobile_css = html[mobile_start:reduce_motion_start]

        self.assertIn("grid-template-rows: auto auto minmax(170px, 1fr) auto;", mobile_css)
        self.assertIn(".segmented", mobile_css)
        self.assertIn("display: none;", mobile_css)
        self.assertIn(".composer-help", mobile_css)
        self.assertIn("display: none;", mobile_css)
        self.assertIn(".messages", mobile_css)
        self.assertIn("min-height: 170px;", mobile_css)

    def test_mobile_operating_issue_queue_stacks_header_and_compresses_rows(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        mobile_start = html.index("@media (max-width: 820px)")
        reduce_motion_start = html.index("@media (prefers-reduced-motion", mobile_start)
        mobile_css = html[mobile_start:reduce_motion_start]

        self.assertIn(".operating-issue-board", mobile_css)
        self.assertIn(".issue-board-head", mobile_css)
        self.assertIn("grid-template-columns: 1fr;", mobile_css)
        self.assertIn(".issue-board-head .hint", mobile_css)
        self.assertIn("display: none;", mobile_css)
        self.assertIn(".issue-item", mobile_css)
        self.assertIn("padding: 10px;", mobile_css)

    def test_operating_issue_queue_maps_internal_fields_to_business_labels(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        render_start = html.index("function renderOperatingIssues")
        refresh_start = html.index("async function refreshOperatingIssues", render_start)
        render_block = html[render_start:refresh_start]

        self.assertIn("function formatIssuePriority", html)
        self.assertIn("function formatIssueDomain", html)
        self.assertIn("function formatMemoryTarget", html)
        self.assertIn("formatIssuePriority(issue.priority)", render_block)
        self.assertIn("formatIssueDomain(issue.domain)", render_block)
        self.assertIn("formatMemoryTarget(issue.memory_target)", render_block)
        self.assertIn("沉淀方向", render_block)
        self.assertNotIn('记忆目标：${escapeHtml(issue.memory_target', render_block)
        self.assertNotIn('${escapeHtml(issue.priority || "medium")}', render_block)
        self.assertNotIn('${escapeHtml(issue.domain || "general")}', render_block)

    def test_mobile_inspector_open_does_not_create_extra_grid_columns(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        mobile_start = html.index("@media (max-width: 820px)")
        reduce_motion_start = html.index("@media (prefers-reduced-motion", mobile_start)
        mobile_css = html[mobile_start:reduce_motion_start]

        self.assertIn(".workspace.inspector-open", mobile_css)
        self.assertIn("grid-template-columns: 1fr;", mobile_css)

    def test_mobile_header_hides_supporting_copy_instead_of_clipping_it(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        mobile_start = html.index("@media (max-width: 820px)")
        reduce_motion_start = html.index("@media (prefers-reduced-motion", mobile_start)
        mobile_css = html[mobile_start:reduce_motion_start]
        hint_start = mobile_css.index(".decision-title .hint")
        hint_end = mobile_css.index("}", hint_start)
        hint_block = mobile_css[hint_start:hint_end]

        self.assertIn("display: none;", hint_block)
        self.assertNotIn("max-height", hint_block)
        self.assertNotIn("overflow: hidden", hint_block)

    def test_brain_page_is_team_operating_brain_workbench_not_strategy_only_gate(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        for label in [
            "0-1 阶段先做三件事",
            "系统会自动判断任务类型",
            "当前优先服务定位验证、清泡调补养口径和品牌资料沉淀",
            "问经营",
            "练员工",
            "传资料",
            "统一口径",
            "招商话术",
            "门店复盘",
            "产品体系",
            "SOP",
            "用户宣传",
            "权威答案",
            "资料记忆",
            "复核任务",
        ]:
            self.assertIn(label, html)
        for inspector_label in [
            "当前理解",
            "自动分类结果",
            "主要矛盾",
            "缺失资料",
            "风险边界",
            "纠偏任务",
            "记忆动作",
        ]:
            self.assertIn(inspector_label, html)
        self.assertIn("/api/operating-brain/workbench-intake", html)
        self.assertIn("workbenchIntake", html)
        self.assertIn("input_type", html)
        self.assertIn("primary_workflow", html)
        self.assertNotIn("定位关 → 战略关 → 商业模式关", html)

    def test_brain_v2_centers_operating_issue_queue_and_okf_lifecycle(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        for label in [
            "动态经营记忆",
            "OKF 生命周期",
            "口径冲突",
            "证据不足",
            "待决策",
            "知识过期",
            "当前最重要的经营议题",
            "聊天只是输入方式",
        ]:
            self.assertIn(label, html)
        for item in [
            'id="issueQueue"',
            'id="okfLifecycleStatus"',
            "refreshOperatingIssues",
            "renderOperatingIssues",
            "/api/operating-brain/issues",
            "/api/operating-brain/okf/summary",
            "/api/operating-brain/issues/intake",
        ]:
            self.assertIn(item, html)

    def test_training_mode_uses_training_evaluation_endpoint(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        self.assertIn("/api/operating-brain/training/evaluate", html)
        self.assertIn("function evaluateTraining", html)
        self.assertIn('if (selectedMode === "training")', html)
        self.assertIn('data-set-mode="training"', html)
        self.assertIn('data-set-scenario="门店员工培训"', html)

    def test_training_mode_renders_dedicated_coach_card_not_generic_answer(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        add_answer_start = html.index("function addAnswer")
        source_brief_start = html.index("function renderSourceBriefDetail", add_answer_start)
        add_answer_block = html[add_answer_start:source_brief_start]

        self.assertIn("function renderTrainingCoachCard", html)
        self.assertIn("training-coach-card", html)
        self.assertIn("training-score", html)
        self.assertIn("关键错误", html)
        self.assertIn("改成这样说", html)
        self.assertIn("下一轮练习", html)
        self.assertIn('if (result.version === "hxy-training-evaluation.v1")', add_answer_block)
        self.assertIn("renderTrainingCoachCard(result)", add_answer_block)

    def test_training_result_scrolls_to_score_first(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        add_answer_start = html.index("function addAnswer")
        source_brief_start = html.index("function renderSourceBriefDetail", add_answer_start)
        add_answer_block = html[add_answer_start:source_brief_start]

        self.assertIn("function scrollTrainingResultIntoView", html)
        self.assertIn("scrollTrainingResultIntoView(item)", add_answer_block)
        self.assertIn("messages.scrollTop = messages.scrollHeight", add_answer_block)
        self.assertIn('result.version === "hxy-training-evaluation.v1"', add_answer_block)

    def test_employee_training_h5_is_mobile_first_ai_training_entry(self):
        page = ROOT / "apps" / "employee-web" / "training.html"
        self.assertTrue(page.exists(), "employee training H5 page should exist")
        html = page.read_text(encoding="utf-8")

        for label in [
            "荷小悦员工训练",
            "今日训练",
            "AI评分",
            "错误纠偏",
            "标准话术",
            "再练一次",
            "店长复训",
        ]:
            self.assertIn(label, html)
        for item in [
            "/api/operating-brain/training/evaluate",
            "employeeId",
            "employeeName",
            "storeId",
            "trainingResult",
            "submitTraining",
            "localStorage",
            "saveIdentity",
            "submitButton.disabled",
            "AI评分中",
            "fetch(",
            "viewport",
        ]:
            self.assertIn(item, html)

    def test_employee_training_h5_uses_question_bank_and_adaptive_retrain(self):
        page = ROOT / "apps" / "employee-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "能力等级",
            "训练题库",
            "自适应复训",
            "经营影响",
            "能力短板",
        ]:
            self.assertIn(label, html)
        for item in [
            "/api/operating-brain/training/question-bank",
            "loadQuestionBank",
            "renderQuestionBank",
            "capabilityProfile",
            "adaptiveRetrainPlan",
            "operatingMetricLinks",
            "data-question-id",
        ]:
            self.assertIn(item, html)

    def test_employee_training_h5_defaults_to_recommended_plan(self):
        page = ROOT / "apps" / "employee-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "系统推荐训练",
            "按你的能力档案安排下一轮训练",
        ]:
            self.assertIn(label, html)
        for item in [
            "/api/operating-brain/training/recommended-plan",
            "loadRecommendedPlan",
            "renderRecommendedPlan",
            "recommendedLevel",
            "recommendedPlan",
            "adaptive_retrain",
            "复训优先",
            "default_new_employee",
            "loadRecommendedPlan();",
        ]:
            self.assertIn(item, html)
        self.assertNotIn('loadQuestionBank("newbie");', html)

    def test_employee_training_h5_turns_adaptive_retrain_into_next_practice(self):
        page = ROOT / "apps" / "employee-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "继续练下一题",
            "下一题已经切换，请直接作答。",
        ]:
            self.assertIn(label, html)
        for item in [
            "lastAdaptiveRetrainPlan",
            "useAdaptiveNextQuestion",
            "next_questions",
            "customerQuestion.value = nextQuestion.customer_question",
            "employeeAnswer.value = \"\"",
        ]:
            self.assertIn(item, html)

    def test_employee_training_h5_updates_recommended_plan_after_failed_training(self):
        page = ROOT / "apps" / "employee-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for item in [
            "updateRecommendedPlanFromTrainingResult",
            "result.needs_retrain",
            "result.adaptive_retrain_plan",
            'source: "adaptive_retrain"',
            "renderRecommendedPlan({",
            "训练未达标，已切换到复训题。",
        ]:
            self.assertIn(item, html)

    def test_manager_training_h5_focuses_retrain_priorities_and_actions(self):
        page = ROOT / "apps" / "manager-web" / "training.html"
        self.assertTrue(page.exists(), "manager training H5 page should exist")
        html = page.read_text(encoding="utf-8")

        for label in [
            "荷小悦店长训练看板",
            "复训优先级",
            "常见错误",
            "今日动作",
            "班前会复训清单",
            "经营议题",
            "刷新",
        ]:
            self.assertIn(label, html)
        for item in [
            "/api/operating-brain/training/manager-summary",
            "/api/operating-brain/training/sessions",
            "managerStoreId",
            "renderSummary",
            "renderBriefingTasks",
            "briefing_tasks",
            "briefingTaskList",
            "renderSessions",
            "localStorage",
            "viewport",
        ]:
            self.assertIn(item, html)

    def test_manager_training_h5_is_compact_task_queue_not_module_tabs(self):
        page = ROOT / "apps" / "manager-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for item in [
            "overflow: hidden;",
            "height: 100dvh;",
            "width: 100%;",
            "max-width: 560px;",
            "grid-template-rows: auto auto minmax(0, 1fr);",
            "task-workbench",
            "task-list",
            "managerTaskQueue",
            "renderManagerTaskQueue",
            "buildManagerTasks",
            "data-task-filter",
            "currentTaskFilter",
        ]:
            self.assertIn(item, html)
        for label in ["今日任务单", "全部", "复训", "经营", "验收"]:
            self.assertIn(label, html)
        self.assertNotIn("manager-tabs", html)
        self.assertNotIn("data-manager-view", html)
        self.assertNotIn("data-manager-panel", html)

    def test_manager_training_h5_supports_acceptance_and_metric_links(self):
        page = ROOT / "apps" / "manager-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "店长验收",
            "通过验收",
            "打回复训",
            "经营结果关联",
            "客单价",
            "调补养占比",
        ]:
            self.assertIn(label, html)
        for item in [
            "/api/operating-brain/training/manager-acceptance",
            "submitManagerAcceptance",
            "renderAcceptanceActions",
            "operatingMetricLinks",
            "data-accept-session",
            "data-reject-session",
        ]:
            self.assertIn(item, html)

    def test_manager_training_h5_surfaces_capability_next_question_and_operating_impact(self):
        page = ROOT / "apps" / "manager-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "能力短板",
            "下一题",
            "经营影响",
        ]:
            self.assertIn(label, html)
        for item in [
            "capability_profile_json",
            "adaptive_retrain_plan_json",
            "operating_metric_links_json",
            "renderSessionTrainingContext",
            "renderSessionOperatingImpact",
        ]:
            self.assertIn(item, html)

    def test_manager_training_h5_renders_training_operating_impact_signals(self):
        page = ROOT / "apps" / "manager-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "经营结果关联",
            "训练影响",
        ]:
            self.assertIn(label, html)
        for item in [
            "operatingImpactList",
            "renderOperatingImpactSignals",
            "operating_impact_signals",
            "risk_level",
            "next_action",
        ]:
            self.assertIn(item, html)

    def test_manager_training_h5_requires_onsite_verification_for_acceptance(self):
        page = ROOT / "apps" / "manager-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "现场复述通过",
            "连续 2 次达标",
            "系统会校验验收资格",
        ]:
            self.assertIn(label, html)
        for item in [
            "onsiteVerified",
            "onsite_verified",
            "acceptance_rule",
            "data-onsite-verified",
        ]:
            self.assertIn(item, html)

    def test_manager_training_h5_uses_api_acceptance_result_for_status(self):
        page = ROOT / "apps" / "manager-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "验收未通过",
            "能力档案已更新",
        ]:
            self.assertIn(label, html)
        for item in [
            "renderAcceptanceStatus",
            "result.accepted",
            "result.requires_retrain",
            "result.capability_upgrade",
            "result.next_actions",
            "refreshDashboard({ preserveStatus: true })",
            "preserveStatus",
            "submitManagerAcceptance",
        ]:
            self.assertIn(item, html)

    def test_manager_training_h5_renders_employee_capability_levels(self):
        page = ROOT / "apps" / "manager-web" / "training.html"
        html = page.read_text(encoding="utf-8")

        for label in [
            "员工能力档案",
            "当前等级",
            "已达标次数",
        ]:
            self.assertIn(label, html)
        for item in [
            "/api/operating-brain/training/capability-levels",
            "capabilityList",
            "renderCapabilityLevels",
            "current_level",
            "accepted_count",
        ]:
            self.assertIn(item, html)

    def test_hxy_pages_expose_status_and_error_messages(self):
        pages = {
            "employee": (ROOT / "apps" / "employee-web" / "training.html").read_text(encoding="utf-8"),
            "manager": (ROOT / "apps" / "manager-web" / "training.html").read_text(encoding="utf-8"),
            "knowledge": (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8"),
            "staff": (ROOT / "apps" / "menu-h5" / "staff.html").read_text(encoding="utf-8"),
            "technician": (ROOT / "apps" / "menu-h5" / "technician.html").read_text(encoding="utf-8"),
            "admin": (ROOT / "apps" / "menu-h5" / "admin.html").read_text(encoding="utf-8"),
        }

        self.assertIn('id="status" class="status" role="status" aria-live="polite"', pages["employee"])
        self.assertIn('id="status" class="status" role="status" aria-live="polite"', pages["manager"])
        self.assertIn('id="actionResult" class="result" role="status" aria-live="polite"', pages["knowledge"])
        self.assertIn('id="authErr" role="alert"', pages["staff"])
        self.assertIn('id="authMsg" role="alert"', pages["technician"])
        self.assertIn('id="authMsg" role="alert"', pages["admin"])
        self.assertIn('id="status" role="status" aria-live="polite"', pages["admin"])

    def test_menu_h5_pages_use_accessible_controls(self):
        staff_html = (ROOT / "apps" / "menu-h5" / "staff.html").read_text(encoding="utf-8")
        technician_html = (ROOT / "apps" / "menu-h5" / "technician.html").read_text(encoding="utf-8")
        order_html = (ROOT / "apps" / "menu-h5" / "order.html").read_text(encoding="utf-8")

        self.assertIn('<button class="filter-btn', staff_html)
        self.assertNotIn('<div class="filter-btn', staff_html)
        for html in [staff_html, technician_html]:
            self.assertIn("min-height:44px", html)

        self.assertNotIn("立即购买 ⚡", order_html)
        self.assertIn('id="backBtn" type="button" aria-label="返回"', order_html)
        self.assertIn('id="closeSheet" type="button" aria-label="关闭"', order_html)
        self.assertIn('id="historyBack" type="button" aria-label="返回"', order_html)

    def test_all_hxy_html_buttons_declare_button_type(self):
        for page in (ROOT / "apps").glob("**/*.html"):
            html = page.read_text(encoding="utf-8")
            for line_number, line in enumerate(html.splitlines(), start=1):
                if "<button" in line and "type=" not in line:
                    self.fail(f"{page.relative_to(ROOT)}:{line_number} button should declare type=\"button\"")

    def test_brain_page_supports_store_daily_metrics_as_operating_diagnosis(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        add_answer_start = html.index("function addAnswer")
        detail_start = html.index("function updateCurrentDetail")
        add_answer_block = html[add_answer_start:detail_start]
        detail_end = html.index("async function sendFeedback")
        detail_block = html[detail_start:detail_end]

        for label in [
            "<summary>门店日报</summary>",
            "今日经营数据",
            "提交诊断",
            "营业额",
            "目标营业额",
            "客单价",
            "复购率",
            "清泡占比",
            "复训次数",
            "投诉数",
        ]:
            self.assertIn(label, html)
        for item in [
            "/api/operating-brain/store-daily-metrics",
            "function storeDailyMetricsPayload",
            "async function diagnoseStoreDailyMetrics",
            "renderStoreDailyDiagnosisCard",
            'if (result.version === "hxy-store-daily-diagnosis.v1")',
            "主要矛盾",
            "今日动作",
        ]:
            self.assertIn(item, html)
        self.assertIn("renderStoreDailyDiagnosisCard(result)", add_answer_block)
        self.assertIn("result.anomalies", detail_block)
        self.assertIn("经营异常", detail_block)
        self.assertIn("result.today_actions", detail_block)

    def test_super_composer_supports_multimodal_upload_drag_and_paste(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        self.assertIn('class="super-composer"', html)
        self.assertIn('id="chatFileInput"', html)
        self.assertIn("handleComposerFiles", html)
        self.assertIn("dragover", html)
        self.assertIn("drop", html)
        self.assertIn("paste", html)
        self.assertIn("attachedFiles", html)
        self.assertIn("uploadAttachedFiles", html)
        self.assertIn("/api/knowledge/upload", html)
        self.assertIn("/api/operating-brain/workbench-submit", html)
        self.assertIn("submitWorkbench", html)
        self.assertIn("memory_result", html)
        self.assertIn("uploaded_attachments", html)
        self.assertIn("image_understandings", html)
        self.assertIn("image_understanding_tasks", html)
        self.assertIn("data-mode=\"correction\"", html)
        self.assertIn("data-mode=\"training\"", html)
        self.assertIn("AI 自动判断", html)
        composer_start = html.index('<div class="composer-tools"')
        composer_end = html.index("</div>", composer_start)
        composer_block = html[composer_start:composer_end]
        self.assertNotIn("data-mode=\"task\"", composer_block)

    def test_inspector_renders_image_understanding_status_for_uploads(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        ask_start = html.index("async function ask")
        listener_start = html.index('document.querySelector("#saveApi").addEventListener', ask_start)
        ask_block = html[ask_start:listener_start]
        detail_start = html.index("function updateCurrentDetail")
        feedback_start = html.index("async function sendFeedback")
        detail_block = html[detail_start:feedback_start]

        self.assertIn("function renderImageUnderstandingStatus", html)
        self.assertIn("submitResult.image_understandings", ask_block)
        self.assertIn("submitResult.image_understanding_tasks", ask_block)
        self.assertIn("图片理解", detail_block)
        self.assertIn("待多模态复核", html)
        self.assertIn("image_understanding_count", detail_block)

    def test_memory_mode_uses_source_brief_notebook_style_workflow(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        ask_start = html.index("async function ask")
        listener_start = html.index('document.querySelector("#saveApi").addEventListener', ask_start)
        ask_block = html[ask_start:listener_start]
        detail_start = html.index("function updateCurrentDetail")
        feedback_start = html.index("async function sendFeedback")
        detail_block = html[detail_start:feedback_start]

        self.assertIn("/api/operating-brain/source-brief", html)
        self.assertIn("function buildSourceBriefResult", html)
        self.assertIn("async function sourceBrief", html)
        self.assertIn("contextLevelLabel", html)
        self.assertIn("domainLabel", html)
        self.assertIn('if (selectedMode === "upload" && !hasAttachments)', ask_block)
        self.assertIn("sourceBrief(finalQuestion)", ask_block)
        self.assertIn("result.source_brief", detail_block)
        self.assertIn("上下文策略", detail_block)
        self.assertIn("转换模板", detail_block)
        self.assertIn("资料研读能力", html)
        self.assertIn("已完成资料研读", detail_block)
        self.assertNotIn("Open Notebook", detail_block)

    def test_source_brief_quality_gate_copy_uses_business_labels(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        build_start = html.index("function buildSourceBriefResult")
        training_start = html.index("async function evaluateTraining", build_start)
        build_block = html[build_start:training_start]

        self.assertIn("引用、背景、排除策略", build_block)
        self.assertNotIn("full / summary / exclude", build_block)

    def test_super_composer_allows_attachment_only_memory_submit(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        submit_start = html.index('document.querySelector("#composer").addEventListener("submit"')
        submit_end = html.index('document.querySelector(".brain-nav").addEventListener', submit_start)
        submit_block = html[submit_start:submit_end]

        self.assertIn("const hasAttachments = attachedFiles.length > 0", submit_block)
        self.assertIn('const fallbackQuestion = "资料上传：请自动识别分类并进入组织记忆。"', submit_block)
        self.assertIn("if (!question && !hasAttachments) return;", submit_block)
        self.assertIn("ask(question || fallbackQuestion);", submit_block)
        self.assertNotIn("if (!question) return;", submit_block)

    def test_left_side_uses_lightweight_status_disclosures(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        self.assertIn('class="control-panel compact-status"', html)
        self.assertIn('class="panel-block knowledge-status status-rail"', html)
        self.assertIn("panel-disclosure", html)
        self.assertIn(".compact-status .panel-disclosure", html)
        self.assertIn("display: none;", html)
        for summary in ["团队入口", "连接", "资料上传", "黄金评测", "答案卡", "复核任务", "资料位置"]:
            self.assertIn(f"<summary>{summary}</summary>", html)
        self.assertIn("知识流入", html)
        self.assertIn("记忆演进", html)
        self.assertIn("待复核", html)
        self.assertIn("后台状态不抢主工作区", html)

    def test_left_side_workbench_sections_are_collapsed_by_default(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        for summary in ["团队入口", "连接", "资料上传", "黄金评测", "答案卡", "复核任务", "资料位置"]:
            marker = f"<summary>{summary}</summary>"
            start = html.index(marker)
            details_start = html.rfind("<details", 0, start)
            details_opening = html[details_start:start]
            self.assertNotIn("open", details_opening, summary)

    def test_team_work_entry_is_collapsed_by_default(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        nav_marker = 'class="team-nav"'
        nav_start = html.index(nav_marker)
        details_start = html.rfind("<details", 0, nav_start)
        summary_start = html.find("<summary>团队入口</summary>", details_start, nav_start)
        details_opening = html[details_start:summary_start]
        self.assertGreater(details_start, -1)
        self.assertGreater(summary_start, -1)
        self.assertNotIn("open", details_opening)

    def test_left_side_is_visually_subordinate_to_chat(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        self.assertIn("grid-template-columns: 216px minmax(0, 1fr);", html)
        self.assertIn("grid-template-columns: 216px minmax(0, 1fr) 340px;", html)
        self.assertIn("box-shadow: 0 10px 26px rgba(81, 91, 73, 0.06);", html)
        self.assertIn("一个输入框处理问答、资料、训练和纠偏。", html)
        self.assertIn("后台状态不抢主工作区。", html)

    def test_brain_page_uses_single_task_prompt_and_recommended_actions(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        for item in [
            'class="task-prompt"',
            "0-1 阶段先做三件事",
            "直接输入问题、资料、员工话术或纠偏意见",
            "系统会自动判断任务类型",
            "推荐先处理",
            "验证核爆点定位",
            "固化清泡调补养口径",
            "整理品牌资料",
        ]:
            self.assertIn(item, html)
        self.assertNotIn("先选任务，再选场景；", html)

    def test_left_side_renders_golden_eval_and_answer_card_workbench(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        for item in [
            'id="goldenEvalStatus"',
            'id="goldenEvalCases"',
            'id="answerCardStatus"',
            'id="answerCards"',
            'id="refreshGoldenEval"',
            'id="refreshAnswerCards"',
            "/api/operating-brain/evals/golden",
            "/api/knowledge/answer-cards?status=approved",
            "refreshGoldenEval",
            "renderGoldenEval",
            "refreshAnswerCards",
            "renderAnswerCards",
            "黄金问题",
            "权威答案卡",
        ]:
            self.assertIn(item, html)

    def test_left_side_renders_brand_asset_center_for_pre_open_stage(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        for item in [
            "<summary>品牌资产</summary>",
            'id="brandAssetStatus"',
            'id="brandAssetModules"',
            'id="brandAssetQuestions"',
            'id="brandAnswerCardStatus"',
            'id="brandAnswerCards"',
            'id="brandAssetBuildOrder"',
            "refreshBrandAssets",
            "refreshBrandAnswerCards",
            "renderBrandAnswerCards",
            "renderBrandAssets",
            "/api/operating-brain/brand-assets",
            "/api/operating-brain/brand-answer-cards",
            "开店前先做品牌资产",
            "客户消费数据开店后再接入",
            "品牌答案卡",
        ]:
            self.assertIn(item, html)

    def test_brain_page_renders_operating_result_card_fields(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        for label in ["经营结果", "可直接使用版本", "风险边界", "质量闸口"]:
            self.assertIn(label, html)
        self.assertIn("result.result_card", html)
        self.assertIn("qualityGateListHtml", html)

    def test_main_answer_card_is_concise_by_default(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        add_answer_start = html.index("function addAnswer")
        source_brief_start = html.index("function renderSourceBriefDetail", add_answer_start)
        add_answer_block = html[add_answer_start:source_brief_start]

        self.assertIn("answer-main", add_answer_block)
        self.assertIn("answer-foot", add_answer_block)
        self.assertIn("详情", add_answer_block)
        self.assertIn("纠偏", add_answer_block)
        self.assertNotIn("<h3>经营结果</h3>", add_answer_block)
        self.assertNotIn("<h3>可直接使用版本</h3>", add_answer_block)
        self.assertNotIn("<h3>风险边界</h3>", add_answer_block)
        self.assertNotIn("<h3>质量闸口</h3>", add_answer_block)
        self.assertNotIn("<h3>可执行动作</h3>", add_answer_block)
        self.assertNotIn("answer-meta", add_answer_block)
        self.assertNotIn("qualityGateListHtml", add_answer_block)
        self.assertNotIn("renderEvidence", add_answer_block)
        self.assertNotIn("data-rating=\"useful\"", add_answer_block)
        self.assertNotIn("data-create-card", add_answer_block)
        self.assertNotIn("source_path", add_answer_block)
        self.assertNotIn("chunk_id", add_answer_block)
        self.assertNotIn("normalized_path", add_answer_block)

    def test_inspector_feedback_has_visible_improvement_workflow(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        detail_start = html.index("function updateCurrentDetail")
        feedback_start = html.index("async function sendFeedback")
        detail_block = html[detail_start:feedback_start]
        send_feedback_end = html.index("async function createAnswerCard")
        feedback_block = html[feedback_start:send_feedback_end]

        self.assertIn("improvementNote", detail_block)
        self.assertIn("哪里需要完善", detail_block)
        self.assertIn("提交完善任务", detail_block)
        self.assertIn("feedbackStatus", detail_block)
        self.assertIn("feedbackStatusHtml", html)
        self.assertIn("setFeedbackStatus", html)
        self.assertIn("button.dataset.feedbackSubmitting", feedback_block)
        self.assertIn("result.correction_package", feedback_block)
        self.assertIn("补充缺失信息并更新答案卡草稿", html)
        self.assertIn("已生成完善任务", html)

    def test_inspector_maps_internal_workflow_keys_to_business_labels(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        detail_start = html.index("function updateCurrentDetail")
        feedback_start = html.index("async function sendFeedback")
        detail_block = html[detail_start:feedback_start]
        pills_start = html.index("function detailPillsHtml")
        pills_end = html.index("function updateCurrentDetail", pills_start)
        pills_block = html[pills_start:pills_end]

        self.assertIn("workflowLabel", html)
        self.assertIn("inputTypeLabel", html)
        self.assertIn("detailPillsHtml", html)
        self.assertIn("资料研读", detail_block)
        self.assertIn("secondaryLabel !== primaryLabel", pills_block)
        self.assertNotIn('intake.primary_workflow || "ask"', detail_block)
        self.assertNotIn('intake.input_type || "question"', detail_block)

    def test_inspector_renders_answer_pipeline_without_polluting_main_answer(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        add_answer_start = html.index("function addAnswer")
        detail_start = html.index("function updateCurrentDetail")
        add_answer_block = html[add_answer_start:detail_start]
        detail_end = html.index("async function sendFeedback")
        detail_block = html[detail_start:detail_end]

        for item in [
            "renderAnswerPipeline",
            "result.answer_pipeline",
            "Policy Gate",
            "Evidence Plan",
            "Guardrail",
            "Evolution",
            "pipeline.policy_decision",
            "pipeline.evidence_plan",
            "pipeline.guardrail_result",
            "pipeline.evolution_actions",
        ]:
            self.assertIn(item, detail_block)
        self.assertNotIn("answer_pipeline", add_answer_block)
        self.assertNotIn("Policy Gate", add_answer_block)
        self.assertNotIn("Evidence Plan", add_answer_block)
        self.assertNotIn("Guardrail", add_answer_block)
        self.assertNotIn("Evolution", add_answer_block)

    def test_inspector_renders_loop_contract_as_primary_runtime_constraint(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        detail_start = html.index("function updateCurrentDetail")
        feedback_start = html.index("async function sendFeedback")
        detail_block = html[detail_start:feedback_start]

        self.assertIn("Loop Contract", detail_block)
        self.assertIn("loop_contract", detail_block)
        self.assertIn("上下文预算", detail_block)
        self.assertIn("停止条件", detail_block)
        self.assertIn("hard limit", detail_block)

    def test_knowledge_workbench_renders_benchmark_correction_tasks(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for item in [
            "Benchmark 修正任务",
            'id="benchmarkCorrections"',
            'id="benchmarkCorrectionsMeta"',
            'id="refreshBenchmarkCorrections"',
            "renderBenchmarkCorrections",
            "/api/operating-brain/benchmark/corrections?limit=20",
            "failed_checks",
            "recommended_reviewer",
            "候选修正不等于批准",
        ]:
            self.assertIn(item, html)

    def test_knowledge_workbench_api_base_defaults_to_current_origin(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for marker in [
            "function defaultApiBase",
            "window.location.origin",
            'localStorage.getItem("hxyKnowledgeApiBase") || defaultApiBase()',
        ]:
            self.assertIn(marker, html)

        script_start = html.index("function defaultApiBase")
        script_end = html.index("function apiBase", script_start)
        default_block = html[script_start:script_end]
        self.assertNotIn("18081", default_block)
        self.assertNotIn('value="http://127.0.0.1:18081"', html)

    def test_knowledge_workbench_prioritizes_governance_cockpit_over_upload_tools(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for marker in [
            'class="knowledge-workbench"',
            'class="system-strip"',
            'class="gate-board"',
            'class="gate-panel p0-gate"',
            "P0 合规闸门",
            "知识底座健康度",
            "资料入库工具",
            "治理闸门优先",
            "blocked_at_empty_manual_decisions",
            "4 条 pending",
        ]:
            self.assertIn(marker, html)

        p0_index = html.index("P0 合规闸门")
        upload_index = html.index("资料入库工具")
        search_index = html.index("知识搜索")
        asset_index = html.index("资料清单")
        self.assertLess(p0_index, upload_index)
        self.assertLess(upload_index, search_index)
        self.assertLess(search_index, asset_index)

        p0_panel_end = html.index("资料入库工具", p0_index)
        p0_panel = html[p0_index:p0_panel_end]
        self.assertNotIn('data-action="approve"', p0_panel)
        self.assertNotIn('data-action="publish"', p0_panel)

    def test_knowledge_workbench_renders_p0_governance_review_queue(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for item in [
            "P0 合规答案卡闸门",
            "人工审核前不能发布",
            'id="p0GovernanceStatus"',
            'id="p0ReviewerTodo"',
            'id="refreshP0Governance"',
            "renderP0GovernanceStatus",
            "renderP0ReviewerTodo",
            "refreshP0Governance",
            "/api/v1/hxy/p0/governance-status",
            "/api/v1/hxy/p0/reviewer-todo",
            "blocked_at_empty_manual_decisions",
            "write_to_database: false",
            "publish_allowed: false",
            "requires_human_review",
        ]:
            self.assertIn(item, html)

        for item in [
            'id="p0RunId"',
            'id="copyP0Notification"',
            'id="p0DecisionPreviewInput"',
            'id="previewP0Decision"',
            'id="p0DecisionPreviewResult"',
            "copyP0Notification",
            "previewP0Decision",
            "refreshP0Governance",
            "/api/v1/hxy/p0/notification",
            "/api/v1/hxy/p0/decision-preview",
            "p0RunQuery",
            "renderP0GovernanceError",
            "navigator.clipboard.writeText",
            "复制 P0 通知",
            "预检人工决策",
            "preview_only",
            "不会写入 p0-review-decisions.json",
        ]:
            self.assertIn(item, html)

        p0_panel_start = html.index("P0 合规答案卡闸门")
        p0_panel_end = html.index("知识搜索", p0_panel_start)
        p0_panel = html[p0_panel_start:p0_panel_end]
        self.assertNotIn('data-action="approve"', p0_panel)
        self.assertNotIn('data-action="publish"', p0_panel)
        self.assertNotIn("POST /api/v1/hxy/p0/publish", p0_panel)

    def test_knowledge_workbench_renders_ingest_loop_panel(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for marker in [
            "资料入库 Loop",
            "候选资料不等于正式知识",
            'id="ingestLoopStatus"',
            'id="runIngestLoop"',
            'id="refreshIngestLoop"',
            "renderIngestLoopStatus",
            "/api/operating-brain/ingest-loop/status",
            "/api/operating-brain/ingest-loop/run",
        ]:
            self.assertIn(marker, html)

    def test_knowledge_workbench_renders_compliance_review_pack_without_approval_actions(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for marker in [
            "合规审核包",
            "只读审核包",
            'id="complianceReviewPack"',
            'id="complianceReviewPackMeta"',
            'id="refreshComplianceReviewPack"',
            "renderComplianceReviewPack",
            "refreshComplianceReviewPack",
            "/api/operating-brain/knowledge-compiler/compliance-review-pack",
            "approve_as_rule",
            "不能自动发布",
        ]:
            self.assertIn(marker, html)

        panel_start = html.index("合规审核包")
        panel_end = html.index("Benchmark 修正任务", panel_start)
        panel_html = html[panel_start:panel_end]
        self.assertNotIn('data-action="approve"', panel_html)
        self.assertNotIn('data-action="publish"', panel_html)

    def test_knowledge_workbench_renders_brand_decision_loop_panel(self):
        html = (ROOT / "apps" / "admin-web" / "knowledge.html").read_text(encoding="utf-8")

        for marker in [
            "首店品牌决策 Loop",
            "不替代 VI/SI 设计",
            'id="brandDecisionText"',
            'id="runBrandDecision"',
            'id="brandDecisionResult"',
            "renderBrandDecisionReview",
            "/api/operating-brain/brand-decision/review",
        ]:
            self.assertIn(marker, html)

    def test_inspector_evidence_hides_raw_file_paths_and_chunk_ids(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        render_start = html.index("function renderEvidence")
        render_end = html.index("async function workbenchIntake", render_start)
        render_block = html[render_start:render_end]

        self.assertIn("资料标题", render_block)
        self.assertIn("source.title", render_block)
        self.assertNotIn("source.source_path", render_block)
        self.assertNotIn("source.chunk_id", render_block)
        self.assertNotIn("<code>", render_block)

    def test_upload_flow_reports_actionable_network_errors(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        self.assertIn("function formatRequestError", html)
        self.assertIn("网络请求失败", html)
        self.assertIn("API 地址", html)
        self.assertIn("await requestJson(\"/health\")", html)
        self.assertIn("正在连接知识库服务", html)
        self.assertNotIn("setStatus(uploadStatus, error.message, \"error\");", html)

    def test_brain_page_defaults_to_same_origin_api(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
        default_start = html.index("function defaultApiBase")
        default_end = html.index("apiInput.value", default_start)
        default_block = html[default_start:default_end]

        self.assertIn("window.location.origin", default_block)
        self.assertNotIn(":18081", default_block)

    def test_brain_page_uses_premium_light_design_tokens(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        for token in [
            "--bg: #f7f4ee",
            "--bg-rose: #f7eef1",
            "--surface-glow",
            "--shadow-float",
            "radial-gradient(circle at 8% 6%",
            "backdrop-filter: blur(18px)",
            "border-radius: 999px",
            "知识流入",
            "记忆演进",
        ]:
            self.assertIn(token, html)

    def test_brain_page_locks_page_scroll_to_chat_history(self):
        html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

        self.assertIn("html,", html)
        self.assertIn("height: 100%;", html)
        self.assertIn("overflow: hidden;", html)
        self.assertIn("height: calc(100dvh - 32px);", html)
        self.assertIn("max-height: calc(100dvh - 32px);", html)
        self.assertIn(".messages", html)
        self.assertIn("overflow-y: auto;", html)


if __name__ == "__main__":
    unittest.main()
