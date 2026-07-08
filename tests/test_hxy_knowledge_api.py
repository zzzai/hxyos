import importlib
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))


class TestClient:
    def __init__(self, app):
        self.app = app
        self.default_headers = {"Authorization": "Bearer test-token"}

    def request(self, method: str, url: str, **kwargs):
        async def run():
            headers = dict(self.default_headers)
            headers.update(kwargs.pop("headers", {}) or {})
            transport = httpx.ASGITransport(app=self.app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, headers=headers, **kwargs)

        return asyncio.run(run())

    def get(self, url: str, **kwargs):
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs):
        return self.request("POST", url, **kwargs)


class FakeRepository:
    def __init__(self):
        self.imported = False
        self.last_search = None
        self.search_calls = []
        self.saved_answer = None
        self.saved_feedback = None
        self.saved_review_task = None
        self.saved_review_tasks = []
        self.saved_training_sessions = []
        self.last_training_summary_request = None
        self.last_training_sessions_request = None
        self.last_training_acceptance_evidence_request = None
        self.training_acceptance_evidence_result = None
        self.saved_training_acceptance = None
        self.saved_training_capability_level = None
        self.last_training_capability_levels_request = None
        self.saved_answer_card = None
        self.resolved_review_task = None
        self.answer_cards = []
        self.search_items = None
        self.search_items_by_query = {}
        self.upserted_runs = []
        self.upserted_assets = []
        self.upserted_chunks = []
        self.upserted_image_understandings = []
        self.saved_store_daily_metrics = None

    def summary(self):
        return {
            "asset_count": 2,
            "chunk_count": 3,
            "domains": [{"domain": "product", "count": 2}],
            "review_count": 1,
        }

    def assets(self, limit=100):
        return [
            {
                "asset_id": "hxy-inbox:a",
                "title": "泡脚方",
                "file_name": "a.md",
                "source_path": "knowledge/raw/inbox/a.md",
                "domain": "product",
                "stage": "preparation",
                "status": "extracted",
                "normalized_path": "knowledge/normalized/product/preparation/a.md",
            }
        ][:limit]

    def search(self, query, domain=None, stage=None, limit=20):
        self.last_search = {"query": query, "domain": domain, "stage": stage, "limit": limit}
        self.search_calls.append(self.last_search)
        if query in self.search_items_by_query:
            return self.search_items_by_query[query][:limit]
        if self.search_items is not None:
            return self.search_items[:limit]
        return [
            {
                "chunk_id": "hxy-inbox:a:chunk:0",
                "asset_id": "hxy-inbox:a",
                "title": "泡脚方",
                "source_path": "knowledge/raw/inbox/a.md",
                "normalized_path": "knowledge/normalized/product/preparation/a.md",
                "domain": domain or "product",
                "stage": stage or "preparation",
                "content": f"{query} 内容：荷小悦以功效泡脚为特色，强调一人一方、草本养生、对症推拿。",
                "score": 10,
            }
        ][:limit]

    def save_answer_run(self, payload):
        self.saved_answer = payload
        return "answer-test-id"

    def save_feedback(self, payload):
        self.saved_feedback = payload
        return "feedback-test-id"

    def create_review_task(self, payload):
        self.saved_review_task = payload
        self.saved_review_tasks.append(payload)
        return "review-task-test-id"

    def save_training_session(self, payload):
        self.saved_training_sessions.append(payload)
        return "training-session-test-id"

    def training_sessions(self, store_id=None, employee_id=None, limit=100):
        self.last_training_sessions_request = {"store_id": store_id, "employee_id": employee_id, "limit": limit}
        return [
            {
                "session_id": "training-session-test-id",
                "employee_id": employee_id or "emp-001",
                "employee_name": "小悦",
                "store_id": store_id or "store-001",
                "store_name": "荷小悦试点店",
                "training_item": "清泡调补养门店推荐话术",
                "customer_question": "顾客问：清泡调补养有什么区别？",
                "score": 62,
                "level": "retrain",
                "needs_retrain": True,
                "correction_points_json": ["不能承诺治疗、治愈、保证或肯定有效，只能表达放松、改善体验和状态建议。"],
                "capability_profile_json": {
                    "level": "newbie",
                    "weak_modules": ["customer_discovery", "compliance_risk"],
                    "summary": "顾客状态探询 · 合规与风险",
                },
                "adaptive_retrain_plan_json": {
                    "target_level": "newbie",
                    "next_questions": [{"question_id": "newbie-discovery-status"}],
                },
                "operating_metric_links_json": [
                    {"metric": "调补养占比", "direction": "negative", "reason": "讲不清升级价值"},
                ],
            }
        ][:limit]

    def training_manager_summary(self, store_id=None, days=7):
        self.last_training_summary_request = {"store_id": store_id, "days": days}
        return {
            "version": "hxy-training-manager-summary.v1",
            "store_id": store_id or "all",
            "days": days,
            "total_sessions": len(self.saved_training_sessions) or 3,
            "average_score": 72,
            "retrain_count": 2,
            "active_employee_count": 2,
            "low_score_employees": [
                {"employee_id": "emp-001", "employee_name": "小悦", "average_score": 62, "retrain_count": 2}
            ],
            "top_mistakes": [
                {"mistake": "不能承诺治疗、治愈、保证或肯定有效，只能表达放松、改善体验和状态建议。", "count": 2}
            ],
            "suggested_actions": ["今天班前会先练清泡调补养区别和禁用表达。"],
            "briefing_tasks": [
                {
                    "employee_id": "emp-001",
                    "employee_name": "小悦",
                    "training_focus": "清泡调补养门店推荐话术",
                    "practice_question": "顾客问：清泡调补养有什么区别？",
                    "correction_focus": "不能承诺治疗、治愈、保证或肯定有效，只能表达放松、改善体验和状态建议。",
                    "acceptance_standard": "现场复述通过，并连续 2 次达到 75 分以上。",
                    "operating_metric": "调补养占比",
                }
            ],
            "operating_impact_signals": [
                {
                    "metric": "调补养占比",
                    "risk_level": "high",
                    "training_signal": "近 7 天有 2 次复训，员工升级推荐不稳定。",
                    "reason": "员工讲不清清泡调补养区别时，顾客容易停留在清泡。",
                    "next_action": "班前会先练顾客状态追问和升级推荐。",
                }
            ],
            "operating_issue_signal": {
                "should_create_issue": True,
                "title": "门店话术复训风险",
                "priority": "high",
                "reason": "近 7 天有 2 次话术需要复训。",
                "recommended_action": "今天班前会先处理复训员工和高频错误。",
            },
        }

    def save_training_manager_acceptance(self, payload):
        self.saved_training_acceptance = payload
        return "training-acceptance-test-id"

    def training_acceptance_evidence(self, session_id, pass_score=75, required_pass_count=2):
        self.last_training_acceptance_evidence_request = {
            "session_id": session_id,
            "pass_score": pass_score,
            "required_pass_count": required_pass_count,
        }
        if self.training_acceptance_evidence_result is not None:
            return self.training_acceptance_evidence_result
        return {
            "version": "hxy-training-acceptance-evidence.v1",
            "session_id": session_id,
            "employee_id": "emp-001",
            "store_id": "store-001",
            "training_item": "清泡调补养门店推荐话术",
            "pass_score": pass_score,
            "required_pass_count": required_pass_count,
            "consecutive_pass_count": required_pass_count,
            "eligible": True,
            "reason": "同一训练项目已连续达标。",
        }

    def upsert_training_capability_level(self, payload):
        self.saved_training_capability_level = payload
        return {
            "capability_id": "capability-test-id",
            "employee_id": payload["employee_id"],
            "store_id": payload["store_id"],
            "training_item": payload["training_item"],
            "current_level": payload["current_level"],
            "accepted_count": payload["accepted_count"],
        }

    def training_capability_levels(self, store_id=None, employee_id=None, limit=100):
        self.last_training_capability_levels_request = {"store_id": store_id, "employee_id": employee_id, "limit": limit}
        return [
            {
                "capability_id": "capability-test-id",
                "employee_id": employee_id or "emp-001",
                "store_id": store_id or "store-001",
                "training_item": "清泡调补养门店推荐话术",
                "current_level": "standard",
                "accepted_count": 2,
                "last_acceptance_id": "acceptance-test-id",
            }
        ][:limit]

    def find_answer_card(self, question, intent):
        for card in self.answer_cards:
            if card.get("intent") == intent and card.get("status") == "approved":
                return card
        return None

    def create_answer_card(self, payload):
        self.saved_answer_card = payload
        card = dict(payload)
        card["card_id"] = "answer-card-test-id"
        self.answer_cards.append(card)
        return "answer-card-test-id"

    def list_answer_cards(self, status=None, limit=100):
        items = self.answer_cards
        if status:
            items = [card for card in items if card.get("status") == status]
        return items[:limit]

    def upsert_run(self, run_name, manifest_path, index_path, asset_count, chunk_count, status="completed"):
        self.upserted_runs.append(
            {
                "run_name": run_name,
                "manifest_path": manifest_path,
                "index_path": index_path,
                "asset_count": asset_count,
                "chunk_count": chunk_count,
                "status": status,
            }
        )

    def upsert_assets(self, assets):
        self.upserted_assets.extend(assets)

    def upsert_chunks(self, chunks):
        self.upserted_chunks.extend(chunks)

    def upsert_image_understandings(self, records):
        self.upserted_image_understandings.extend(records)

    def review_tasks(self, status="open", limit=50):
        if not self.saved_review_tasks:
            return []
        return [
            {
                **task,
                "task_id": f"review-task-test-id-{index}",
                "status": status,
                "payload_json": task,
            }
            for index, task in enumerate(self.saved_review_tasks, start=1)
        ][:limit]

    def resolve_review_task(self, task_id, status="resolved"):
        self.resolved_review_task = {"task_id": task_id, "status": status}
        return True

    def save_store_daily_metrics(self, payload):
        self.saved_store_daily_metrics = payload
        return "store-daily-metrics-test-id"


class FakeModelRouter:
    def __init__(self, output="模型生成的可用答案。", used_model=True):
        self.output = output
        self.used_model = used_model
        self.generate_calls = []

    def status(self):
        return {"version": "fake-router", "execution_mode": "enabled", "routes": []}

    def route(self, task_type):
        return {
            "version": "hxy-model-router.v1",
            "task_type": task_type,
            "purpose": "fake",
            "provider": "custom",
            "selected_model": "gpt-5.5",
            "wire_api": "responses",
            "endpoint_host": "models.example.test",
            "reasoning_effort": "high",
            "execution_mode": "enabled",
            "should_call_model": task_type != "authority_answer",
            "config_loaded": True,
            "config_source": "/tmp/fake-config.toml",
        }

    def generate(self, task_type, *, messages=None, prompt=None, metadata=None):
        self.generate_calls.append({"task_type": task_type, "messages": messages or [], "prompt": prompt, "metadata": metadata or {}})
        return {
            "version": "hxy-model-generation.v1",
            "used_model": self.used_model,
            "reason": "ok" if self.used_model else "disabled",
            "route": self.route(task_type),
            "request_shape": {
                "message_count": len(messages or []),
                "has_prompt": bool(prompt),
                "metadata_keys": sorted((metadata or {}).keys()),
            },
            "provider_response_id": "resp_fake" if self.used_model else None,
            "usage": {"input_tokens": 10, "output_tokens": 20} if self.used_model else {},
            "output": self.output if self.used_model else None,
        }


class HxyKnowledgeApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "knowledge" / "raw" / "inbox").mkdir(parents=True)
        (self.root / "knowledge" / "structured").mkdir(parents=True)
        self.previous_api_token = os.environ.get("HXY_API_TOKEN")
        self.previous_max_upload_bytes = os.environ.get("HXY_MAX_UPLOAD_BYTES")
        self.previous_allowed_upload_extensions = os.environ.get("HXY_ALLOWED_UPLOAD_EXTENSIONS")
        self.previous_cors_origins = os.environ.get("HXY_CORS_ORIGINS")
        os.environ["HXY_API_TOKEN"] = "test-token"
        os.environ.pop("HXY_MAX_UPLOAD_BYTES", None)
        os.environ.pop("HXY_ALLOWED_UPLOAD_EXTENSIONS", None)
        os.environ["HXY_CORS_ORIGINS"] = "http://testserver"
        module = importlib.import_module("apps.api.hxy_knowledge_api")
        self.repo = FakeRepository()
        self.app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo)
        self.client = TestClient(self.app)

    def tearDown(self):
        if self.previous_api_token is None:
            os.environ.pop("HXY_API_TOKEN", None)
        else:
            os.environ["HXY_API_TOKEN"] = self.previous_api_token
        if self.previous_max_upload_bytes is None:
            os.environ.pop("HXY_MAX_UPLOAD_BYTES", None)
        else:
            os.environ["HXY_MAX_UPLOAD_BYTES"] = self.previous_max_upload_bytes
        if self.previous_allowed_upload_extensions is None:
            os.environ.pop("HXY_ALLOWED_UPLOAD_EXTENSIONS", None)
        else:
            os.environ["HXY_ALLOWED_UPLOAD_EXTENSIONS"] = self.previous_allowed_upload_extensions
        if self.previous_cors_origins is None:
            os.environ.pop("HXY_CORS_ORIGINS", None)
        else:
            os.environ["HXY_CORS_ORIGINS"] = self.previous_cors_origins
        self.tmp.cleanup()

    def test_health_reports_hxy_service_and_inbox_path(self):
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["service"], "hxy-knowledge-api")
        self.assertEqual(body["status"], "ok")
        self.assertTrue(body["inbox_path"].endswith("knowledge/raw/inbox"))

    def test_operating_brain_capabilities_endpoint_returns_foundation_contract(self):
        response = self.client.get("/api/operating-brain/capabilities")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        knowledge_keys = {item["key"] for item in body["knowledge_fusion"]}
        self.assertIn("project_knowledge", knowledge_keys)
        self.assertIn("operating_data", knowledge_keys)
        self.assertIn("market_intelligence", knowledge_keys)
        route_keys = {item["key"] for item in body["model_routes"]}
        self.assertIn("reasoning", route_keys)
        self.assertFalse(body["training_strategy"]["pretraining_required"])

    def test_operating_brain_model_router_endpoint_returns_safe_route_status(self):
        response = self.client.get("/api/operating-brain/model-router")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-model-router.v1")
        self.assertEqual(body["config_source"], "/root/.codex/config.toml")
        self.assertIn("routes", body)
        route_keys = {item["task_type"] for item in body["routes"]}
        self.assertIn("reasoning", route_keys)
        self.assertIn("classification", route_keys)
        self.assertIn("vision", route_keys)
        self.assertIn("embedding", route_keys)
        self.assertIn("speech", route_keys)
        self.assertIn("training_evaluation", route_keys)
        self.assertIn(body["execution_mode"], {"metadata_only", "enabled"})
        serialized = str(body).lower()
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("secret", serialized)
        self.assertNotIn("password", serialized)
        self.assertNotIn("bearer", serialized)

    def test_operating_brain_product_contracts_include_enterprise_objects(self):
        response = self.client.get("/api/operating-brain/product-contracts")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("knowledge_engine", payload)
        self.assertIn("retrieval_apps", payload)
        self.assertIn("intent_planning", payload)
        self.assertIn("skill_registry", payload)
        self.assertIn("memory_policies", payload)
        self.assertIn("automation_tasks", payload)
        self.assertIn("authority_rules", payload)
        self.assertFalse(payload["authority_rules"]["chat_can_publish_approved"])
        self.assertFalse(payload["authority_rules"]["agent_can_publish_approved"])
        self.assertFalse(payload["authority_rules"]["loop_can_publish_approved"])
        self.assertFalse(payload["authority_rules"]["memory_can_publish_approved"])
        self.assertFalse(payload["authority_rules"]["skill_output_is_official"])

    def test_retrieval_apps_are_business_specific_and_do_not_expose_raw_chunks(self):
        response = self.client.get("/api/operating-brain/retrieval-apps")

        self.assertEqual(response.status_code, 200)
        serialized = json.dumps(response.json(), ensure_ascii=False)
        self.assertIn("employee_standard_answer_search", serialized)
        self.assertIn("brand_language_risk_check", serialized)
        self.assertIn("founder_decision_evidence_search", serialized)
        self.assertNotIn("chunk_id", serialized)
        self.assertNotIn("/root/hxy", serialized)
        self.assertNotIn("cluster_member_count", serialized)

    def test_intent_definitions_have_scope_exclusions_and_risk_gates(self):
        response = self.client.get("/api/operating-brain/intent-definitions")

        self.assertEqual(response.status_code, 200)
        items = response.json()["items"]
        compliance = next(item for item in items if item["intent_id"] == "intent-compliance-language-check")
        self.assertIn("positive_scope", compliance)
        self.assertIn("excluded_scope", compliance)
        self.assertIn("risk_gates", compliance)
        self.assertIn("medical_claim", compliance["risk_gates"])

    def test_skill_registry_keeps_skill_output_non_official(self):
        response = self.client.get("/api/operating-brain/skills")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("items", payload)
        self.assertFalse(payload["authority_rules"]["skill_output_is_official"])
        for item in payload["items"]:
            self.assertIn("version", item)
            self.assertIn("status", item)
            self.assertIn("owner", item)
            self.assertFalse(item["can_publish_approved"])

    def test_compliance_language_check_blocks_medical_claims(self):
        response = self.client.post(
            "/api/operating-brain/skills/hxy-compliance-language-check/run",
            json={
                "text": "泡脚能治疗失眠，睡不好来做一次就能好。",
                "channel": "朋友圈",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-compliance-language-check-result.v1")
        self.assertEqual(body["skill_id"], "hxy-compliance-language-check")
        self.assertEqual(body["decision"], "block")
        self.assertIn("medical_claim", body["hit_gates"])
        self.assertFalse(body["can_publish"])
        self.assertFalse(body["official_use_allowed"])
        self.assertTrue(body["review_required"])
        self.assertIn("rewrite_suggestion", body)
        self.assertIn("risk_reason", body)
        self.assertNotIn("/root/hxy", json.dumps(body, ensure_ascii=False))

    def test_compliance_language_check_suggests_source_replacement(self):
        response = self.client.post(
            "/api/operating-brain/skills/hxy-compliance-language-check/run",
            json={
                "text": "荷小悦可以治疗颈椎病。",
                "channel": "团购页",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision"], "block")
        self.assertIn("久坐肩颈紧，按一按松一点", body["rewrite_suggestion"])
        self.assertFalse(body["can_publish"])
        self.assertFalse(body["official_use_allowed"])

    def test_compliance_language_check_requires_api_token(self):
        response = self.client.post(
            "/api/operating-brain/skills/hxy-compliance-language-check/run",
            headers={"Authorization": ""},
            json={"text": "草本现煮，泡着舒服。"},
        )

        self.assertEqual(response.status_code, 401)

    def test_compliance_language_check_fails_closed_when_api_token_missing(self):
        os.environ.pop("HXY_API_TOKEN", None)
        module = importlib.import_module("apps.api.hxy_knowledge_api")
        app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo)
        client = TestClient(app)

        response = client.post(
            "/api/operating-brain/skills/hxy-compliance-language-check/run",
            headers={"Authorization": ""},
            json={"text": "草本现煮，泡着舒服。"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("HXY_API_TOKEN", response.json()["detail"])

    def test_compliance_language_check_blocks_guaranteed_effect(self):
        response = self.client.post(
            "/api/operating-brain/skills/hxy-compliance-language-check/run",
            json={
                "text": "这个项目一周保证见效，调理一次就有疗效。",
                "channel": "团购页",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision"], "block")
        self.assertIn("guaranteed_effect", body["hit_gates"])
        self.assertFalse(body["can_publish"])
        self.assertFalse(body["official_use_allowed"])

    def test_compliance_language_check_allows_low_risk_copy(self):
        response = self.client.post(
            "/api/operating-brain/skills/hxy-compliance-language-check/run",
            json={
                "text": "草本现煮，泡着舒服，适合下班后来放松一下。",
                "channel": "海报",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["decision"], "allow")
        self.assertEqual(body["risk_level"], "none")
        self.assertEqual(body["risk_reason"], "未命中禁用表达。")
        self.assertEqual(body["hit_gates"], [])
        self.assertFalse(body["can_publish"])
        self.assertFalse(body["official_use_allowed"])
        self.assertFalse(body["review_required"])

    def test_compliance_workflow_gate_blocks_content_publish_medical_claim(self):
        response = self.client.post(
            "/api/operating-brain/workflow-gates/compliance/run",
            json={
                "workflow_type": "content_publish",
                "text": "泡脚能治疗失眠，睡不好来做一次就能好。",
                "channel": "朋友圈",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-compliance-workflow-gate-result.v1")
        self.assertEqual(body["workflow_type"], "content_publish")
        self.assertEqual(body["workflow_status"], "blocked")
        self.assertFalse(body["can_continue"])
        self.assertFalse(body["can_publish"])
        self.assertFalse(body["official_use_allowed"])
        self.assertIn("停止发布", body["next_step"])
        self.assertEqual(body["human_owner"], "内容/运营负责人")

    def test_compliance_workflow_gate_blocks_staff_script_training_risk(self):
        response = self.client.post(
            "/api/operating-brain/workflow-gates/compliance/run",
            json={
                "workflow_type": "staff_script",
                "text": "你这是湿气重，要调理几个疗程。",
                "channel": "员工话术",
                "audience": "staff",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["workflow_status"], "blocked")
        self.assertFalse(body["can_continue"])
        self.assertIn("禁止进入员工培训", body["next_step"])
        self.assertEqual(body["human_owner"], "店长/运营培训负责人")

    def test_compliance_workflow_gate_blocks_project_menu_medicalized_copy(self):
        response = self.client.post(
            "/api/operating-brain/workflow-gates/compliance/run",
            json={
                "workflow_type": "project_menu",
                "text": "艾灸调理体质，改善慢病。",
                "channel": "项目菜单",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["workflow_status"], "blocked")
        self.assertFalse(body["can_continue"])
        self.assertIn("停止上架", body["next_step"])
        self.assertEqual(body["human_owner"], "产品/菜单负责人")

    def test_compliance_workflow_gate_allows_safe_copy_to_continue_without_publishing(self):
        response = self.client.post(
            "/api/operating-brain/workflow-gates/compliance/run",
            json={
                "workflow_type": "content_publish",
                "text": "草本现煮，泡着舒服，适合下班后来放松一下。",
                "channel": "海报",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["workflow_status"], "can_continue")
        self.assertTrue(body["can_continue"])
        self.assertFalse(body["can_publish"])
        self.assertFalse(body["official_use_allowed"])
        self.assertIn("人工确认", body["next_step"])

    def test_compliance_workflow_gate_rejects_unknown_workflow_type(self):
        response = self.client.post(
            "/api/operating-brain/workflow-gates/compliance/run",
            json={
                "workflow_type": "unknown",
                "text": "草本现煮，泡着舒服。",
                "channel": "海报",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("workflow_type", response.json()["detail"])

    def test_automation_tasks_are_allowlisted_and_cannot_publish_approved(self):
        response = self.client.get("/api/operating-brain/automation-tasks")

        self.assertEqual(response.status_code, 200)
        for item in response.json()["items"]:
            self.assertIn("task_type", item)
            self.assertIn("stop_condition", item)
            self.assertFalse(item["can_publish_approved"])
            self.assertTrue(item["allowed_script"].startswith("scripts/") or item["allowed_script"] == "")

    def test_operating_brain_store_daily_metrics_endpoint_returns_actionable_diagnosis(self):
        response = self.client.post(
            "/api/operating-brain/store-daily-metrics",
            json={
                "store_id": "pilot-store",
                "store_name": "荷小悦试点店",
                "business_date": "2026-06-22",
                "revenue": 3800,
                "target_revenue": 6000,
                "orders": 48,
                "average_ticket": 79,
                "target_average_ticket": 118,
                "repeat_rate": 0.24,
                "target_repeat_rate": 0.42,
                "product_mix": {"清泡": 0.68, "调泡": 0.18, "补泡": 0.09, "养泡": 0.05},
                "training_retrain_count": 3,
                "customer_complaints": 2,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-store-daily-diagnosis.v1")
        self.assertEqual(body["metrics_id"], "store-daily-metrics-test-id")
        self.assertEqual(body["priority"], "high")
        self.assertIn("客单价", body["main_conflict"])
        self.assertTrue(body["should_create_issue"])
        self.assertIsNotNone(self.repo.saved_store_daily_metrics)
        self.assertEqual(self.repo.saved_store_daily_metrics["store_id"], "pilot-store")
        self.assertEqual(self.repo.saved_store_daily_metrics["diagnosis"]["priority"], "high")

    def test_operating_brain_golden_eval_endpoint_returns_quality_gate_summary(self):
        response = self.client.get("/api/operating-brain/evals/golden")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-eval-runner.v1")
        self.assertEqual(body["suite"], "golden_questions")
        self.assertEqual(body["total"], 6)
        self.assertEqual(body["pass_count"], 6)
        self.assertEqual(body["fail_count"], 0)
        self.assertGreaterEqual(body["score"], 0.95)
        self.assertEqual(body["model_route"]["task_type"], "offline_eval")
        self.assertFalse(body["model_route"]["should_call_model"])
        self.assertEqual(
            {item["question"] for item in body["cases"]},
            {
                "荷小悦是什么？",
                "核爆点定位是什么？",
                "清泡调补养怎么讲？",
                "门店员工怎么推荐泡脚方？",
                "招商怎么讲单店模型？",
                "哪些话不能说？",
            },
        )

    def test_operating_brain_brand_assets_endpoint_returns_brand_first_scope(self):
        response = self.client.get("/api/operating-brain/brand-assets")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-brand-assets.v1")
        self.assertEqual(body["stage"], "pre_open_brand_first")
        self.assertGreaterEqual(len(body["modules"]), 8)
        self.assertGreaterEqual(len(body["golden_questions"]), 30)
        self.assertEqual(body["next_build_order"][0], "先固化品牌定位和核爆点口径")
        visible = response.text
        self.assertIn("品牌战略库", visible)
        self.assertIn("产品服务库", visible)
        self.assertIn("招商融资库", visible)
        self.assertIn("客户消费数据开店后再接入", visible)

    def test_operating_brain_brand_risk_rules_endpoint_uses_compliance_materials(self):
        response = self.client.get("/api/operating-brain/brand-risk-rules")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-brand-risk-rules.v1")
        self.assertFalse(body["official_use_allowed"])
        self.assertTrue(body["requires_human_review"])
        serialized_rules = json.dumps(body["rules"], ensure_ascii=False)
        for term in ["祛湿排毒", "改善睡眠", "治疗脚气", "年轻十岁", "医美级"]:
            self.assertIn(term, serialized_rules)
        self.assertIn("09_风险与合规/荷小悦禁用表达库.md", " ".join(body["source_paths"]))

    def test_brand_risk_rules_compile_employee_scripts_and_project_red_lines(self):
        from hxy_knowledge.compliance_rules import check_brand_risk_text, load_brand_risk_rules

        rules = load_brand_risk_rules(root_dir=self.root)

        self.assertEqual(rules["status"], "candidate_rules")
        self.assertFalse(rules["official_use_allowed"])
        self.assertTrue(rules["requires_human_review"])
        serialized_rules = json.dumps(rules["rules"], ensure_ascii=False)
        self.assertIn("你这是湿气重", serialized_rules)
        self.assertIn("调理体质", serialized_rules)
        self.assertIn("改善慢病", serialized_rules)
        self.assertIn("safe_replacements", rules)
        self.assertIn(
            {"unsafe": "治疗颈椎病", "safe": "久坐肩颈紧，按一按松一点"},
            rules["safe_replacements"],
        )

        risky = check_brand_risk_text("艾灸调理体质，改善慢病。", root_dir=self.root)
        self.assertEqual(risky["status"], "bad")
        self.assertTrue(any(hit["level"] == "bad" for hit in risky["hits"]))

        boundary = check_brand_risk_text("我们不做治疗，也不能替代医院检查。", root_dir=self.root)
        self.assertEqual(boundary["status"], "ok")
        self.assertEqual(boundary["hits"], [])

    def test_operating_brain_brand_answer_cards_endpoint_returns_approved_brand_cards(self):
        response = self.client.get("/api/operating-brain/brand-answer-cards")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-brand-answer-cards.v1")
        self.assertEqual(body["stage"], "pre_open_brand_first")
        self.assertGreaterEqual(body["count"], 30)
        questions = {item["question_pattern"] for item in body["items"]}
        self.assertIn("荷小悦是什么？", questions)
        self.assertIn("招商怎么讲单店模型？", questions)
        self.assertIn("哪些话不能说？", questions)
        sample = next(item for item in body["items"] if item["question_pattern"] == "荷小悦是什么？")
        self.assertEqual(sample["status"], "approved")
        self.assertEqual(sample["review_status"], "approved_v1")
        self.assertEqual(sample["source"], "brand_assets")
        self.assertIn("founder", sample["role_versions"])
        self.assertIn("store_staff", sample["role_versions"])
        self.assertIn("franchisee", sample["role_versions"])
        self.assertIn("customer", sample["role_versions"])
        visible = response.text
        self.assertNotIn("客户消费记录", visible)
        self.assertNotIn("POS", visible)

    def test_operating_brain_startup_advance_endpoint_turns_action_into_progress_draft(self):
        response = self.client.post(
            "/api/operating-brain/startup-advance",
            json={
                "action": "record",
                "evidence_input": "访谈 3 个社区白领，都说下班后想要肩颈放松和睡前恢复，不会主动说养生。",
                "current_conclusion": "荷小悦是面向社区高疲劳人群的轻恢复项目。",
                "main_question": "核爆点定位是否成立？",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-startup-advance.v1")
        self.assertEqual(body["stage"], "pre_open_zero_to_one")
        self.assertEqual(body["action"], "record")
        self.assertEqual(body["main_question"], "核爆点定位是否成立？")
        self.assertIn("访谈 3 个社区白领", body["input_summary"])
        self.assertGreaterEqual(body["confidence"], 0.5)
        self.assertIn("核爆点定位", body["focus"])
        self.assertIn("evidence_capture", body["workflow"])
        self.assertIn("证据", body["draft"]["title"])
        self.assertGreaterEqual(len(body["draft"]["bullets"]), 3)
        self.assertGreaterEqual(len(body["evidence_requirements"]), 3)
        self.assertGreaterEqual(len(body["next_actions"]), 3)
        self.assertGreaterEqual(len(body["quality_gates"]), 3)
        self.assertEqual(body["memory_action"]["target"], "knowledge/okf")
        self.assertIn("定位", body["memory_action"]["artifact"])
        self.assertIn("开店前", body["boundary"])
        visible = response.text
        self.assertNotIn("POS", visible)
        self.assertNotIn("客户消费记录", visible)

    def test_operating_brain_startup_advance_rejects_unknown_action(self):
        response = self.client.post(
            "/api/operating-brain/startup-advance",
            json={
                "action": "store_dashboard",
                "evidence_input": "今天想看门店日报。",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_operating_brain_okf_summary_reads_lifecycle_files(self):
        okf_dir = self.root / "knowledge" / "okf" / "core"
        okf_dir.mkdir(parents=True)
        (okf_dir / "qingpao.md").write_text(
            """---
type: operating_claim
title: 清泡调补养员工话术
domain: product_system
status: disputed
confidence: 0.58
last_confirmed: 2026-05-01
owner: 运营负责人
contradicts:
  - old-script-v1
used_by:
  - employee_training
---

门店员工需要统一清泡调补养话术。
""",
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/okf/summary")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-okf-lifecycle-summary.v1")
        self.assertEqual(body["root"], "knowledge/okf")
        self.assertEqual(body["total"], 1)
        self.assertEqual(body["status_counts"]["disputed"], 1)
        self.assertEqual(body["conflict_count"], 1)

    def test_operating_brain_knowledge_governance_endpoint_returns_enterprise_gate(self):
        (self.root / "quarantine" / "knowledge-assets" / "structured").mkdir(parents=True)
        (self.root / "quarantine" / "knowledge-assets" / "structured" / "claims.json").write_text(
            json.dumps(
                [
                    {
                        "claim_id": "claim-no-evidence",
                        "claim_type": "brand_positioning",
                        "claim": "荷小悦是社区轻恢复品牌",
                        "status": "current_candidate",
                        "confidence": 0.62,
                        "evidence_ids": [],
                    },
                    {
                        "claim_id": "claim-overclaim",
                        "claim_type": "product_service",
                        "claim": "清泡可以治疗失眠，保证有效",
                        "status": "current_candidate",
                        "confidence": 0.78,
                        "evidence_ids": ["e1"],
                    },
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (self.root / "quarantine" / "knowledge-assets" / "structured" / "evidence.json").write_text(
            json.dumps([{"evidence_id": "e1", "source_id": "asset-reference", "snippet": "外部方法论"}], ensure_ascii=False),
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/knowledge-governance")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-enterprise-knowledge-governance.v1")
        self.assertIn("summary", body)
        self.assertIn("quality_score", body)
        self.assertIn("memory_layers", body)
        self.assertIn("release_gate", body)
        self.assertIn("evolution_actions", body)
        self.assertIn("review_task_drafts", body)
        self.assertFalse(body["release_gate"]["can_publish"])
        issue_codes = {item["code"] for item in body["lint_issues"]}
        self.assertIn("claim_missing_evidence", issue_codes)
        self.assertIn("claim_overclaim_risk", issue_codes)
        self.assertEqual(
            body["memory_layers"]["policy"]["direct_answer_allowed"],
            ["L3_approved_knowledge", "L4_action_asset"],
        )

    def test_operating_brain_incremental_compile_endpoint_accepts_manifests(self):
        response = self.client.post(
            "/api/operating-brain/incremental-compile-plan",
            json={
                "previous_manifest": {
                    "assets": [
                        {"asset_id": "asset-a", "relative_path": "a.md", "sha256": "old"},
                        {"asset_id": "asset-b", "relative_path": "b.md", "sha256": "same"},
                    ]
                },
                "current_manifest": {
                    "assets": [
                        {"asset_id": "asset-a", "relative_path": "a.md", "sha256": "new"},
                        {"asset_id": "asset-c", "relative_path": "c.md", "sha256": "new-c"},
                    ]
                },
                "relations": [{"from_id": "asset-a", "to_id": "claim-a", "relation_type": "supports"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-incremental-compile-plan.v1")
        self.assertEqual(body["summary"]["added"], 1)
        self.assertEqual(body["summary"]["changed"], 1)
        self.assertEqual(body["summary"]["deleted"], 1)
        self.assertIn("lint", {task["stage"] for task in body["tasks"]})
        self.assertIn("claim-a", {item["id"] for item in body["affected_nodes"]})

    def test_operating_brain_file_manifest_endpoint_hashes_hxy_raw_inbox(self):
        inbox = self.root / "knowledge" / "raw" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "brand.md").write_text("荷小悦品牌资料", encoding="utf-8")
        (inbox / "ignore.tmp").write_text("ignore", encoding="utf-8")

        response = self.client.get("/api/operating-brain/file-manifest")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-file-manifest.v1")
        self.assertEqual(body["summary"]["asset_count"], 1)
        self.assertEqual(body["summary"]["ignored_count"], 1)
        self.assertEqual(body["assets"][0]["relative_path"], "knowledge/raw/inbox/brand.md")
        self.assertTrue(body["assets"][0]["asset_id"].startswith("hxy-file:"))

    def test_operating_brain_benchmark_endpoint_reads_latest_report(self):
        report_dir = self.root / "knowledge" / "reports"
        report_dir.mkdir(parents=True)
        (report_dir / "benchmark-latest.json").write_text(
            json.dumps(
                {
                    "version": "hxy-brain-benchmark-report.v1",
                    "case_count": 30,
                    "passed_count": 24,
                    "failed_count": 6,
                    "pass_rate": 0.8,
                    "failure_thresholds": {"min_pass_rate": 0.85},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/benchmark")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-brain-benchmark-status.v1")
        self.assertEqual(body["summary"]["case_count"], 30)
        self.assertEqual(body["summary"]["pass_rate"], 0.8)
        self.assertIn("next_actions", body)

    def test_operating_brain_compiler_status_endpoint_reads_latest_report(self):
        report_dir = self.root / "knowledge" / "reports"
        report_dir.mkdir(parents=True)
        (report_dir / "compiler-latest.json").write_text(
            json.dumps(
                {
                    "version": "hxy-knowledge-compiler-report.v1",
                    "extract_count": 2,
                    "claim_count": 7,
                    "approved_count": 0,
                    "graph_node_count": 12,
                    "graph_edge_count": 14,
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/knowledge-compiler/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-knowledge-compiler-status.v1")
        self.assertEqual(body["summary"]["extract_count"], 2)
        self.assertEqual(body["summary"]["claim_count"], 7)
        self.assertEqual(body["summary"]["approved_count"], 0)
        self.assertIn("next_actions", body)

    def test_operating_brain_compiler_review_queue_endpoint_reads_generated_queue(self):
        wiki_dir = self.root / "knowledge" / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "review-queue.json").write_text(
            json.dumps(
                {
                    "version": "hxy-review-queue.v1",
                    "items": [
                        {
                            "claim_id": "claim-001",
                            "claim": "荷小悦社区小店要复核门店模型参数。",
                            "review_group": "store_model",
                            "priority": "high",
                            "sources": ["source.pdf"],
                        }
                    ],
                    "reviewable_claim_count": 1,
                    "noise_claim_count": 0,
                    "group_counts": {"store_model": 1},
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/knowledge-compiler/review-queue")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-review-queue.v1")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["claim_id"], "claim-001")
        self.assertFalse(body["items"][0]["official_use_allowed"])

    def test_operating_brain_compiler_claim_triage_endpoint_limits_and_marks_candidates(self):
        wiki_dir = self.root / "knowledge" / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "claim-triage.json").write_text(
            json.dumps(
                {
                    "version": "hxy-claim-triage.v1",
                    "total_claim_count": 218895,
                    "noise_claim_count": 1123,
                    "duplicate_claim_count": 11930,
                    "unique_reviewable_claim_count": 205842,
                    "cluster_count": 15657,
                    "selected_count": 2,
                    "items": [
                        {
                            "claim_id": "triage-001",
                            "claim": "员工不能承诺治疗脚气或保证有效。",
                            "review_group": "risk_boundary",
                            "priority": "high",
                            "source_class": "risk_compliance",
                            "cluster_member_count": 42,
                            "duplicate_count": 3,
                            "sources": ["risk.md"],
                        },
                        {
                            "claim_id": "triage-002",
                            "claim": "门店话术需要保持口语化。",
                            "review_group": "brand_expression",
                            "priority": "medium",
                            "source_class": "brand",
                            "cluster_member_count": 9,
                            "duplicate_count": 1,
                            "sources": ["brand.md"],
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/knowledge-compiler/claim-triage?limit=1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-claim-triage.v1")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["total_claim_count"], 218895)
        self.assertEqual(body["noise_claim_count"], 1123)
        self.assertEqual(body["duplicate_claim_count"], 11930)
        self.assertEqual(body["unique_reviewable_claim_count"], 205842)
        self.assertEqual(body["cluster_count"], 15657)
        self.assertEqual(body["selected_count"], 2)
        self.assertFalse(body["official_use_allowed"])
        self.assertTrue(body["requires_human_review"])
        self.assertEqual(body["items"][0]["claim_id"], "triage-001")
        self.assertFalse(body["items"][0]["official_use_allowed"])
        self.assertTrue(body["items"][0]["requires_human_review"])

    def test_operating_brain_compiler_review_topics_endpoint_turns_raw_claims_into_business_topics(self):
        wiki_dir = self.root / "knowledge" / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "claim-triage.json").write_text(
            json.dumps(
                {
                    "version": "hxy-claim-triage.v1",
                    "total_claim_count": 218895,
                    "cluster_count": 15657,
                    "items": [
                        {
                            "claim_id": "triage-001",
                            "claim": "高 | 容易被理解成治疗、诊疗、医美或高风险技术 | 不做主门头，必须人工复核",
                            "review_group": "risk_boundary",
                            "priority": "high",
                            "source_class": "risk_compliance",
                            "cluster_member_count": 42,
                            "sources": ["/root/hxy/knowledge/raw/inbox/风险与合规/荷小悦项目红线卡.md"],
                        },
                        {
                            "claim_id": "triage-002",
                            "claim": "员工提醒 | 必须标注外用、禁忌、过敏提醒；不能替代药品",
                            "review_group": "employee_script",
                            "priority": "high",
                            "source_class": "risk_compliance",
                            "cluster_member_count": 8,
                            "sources": ["/root/hxy/knowledge/raw/inbox/风险与合规/荷小悦员工功效问题标准话术.md"],
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/knowledge-compiler/review-topics?limit=10")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-review-topics.v1")
        self.assertEqual(body["count"], 2)
        self.assertFalse(body["official_use_allowed"])
        self.assertTrue(body["requires_human_review"])
        serialized = json.dumps(body, ensure_ascii=False)
        self.assertIn("医疗与功效表达边界", serialized)
        self.assertIn("员工对外话术边界", serialized)
        self.assertIn("先判断", serialized)
        self.assertIn("荷小悦项目红线卡.md", serialized)
        self.assertNotIn("/root/hxy", serialized)
        self.assertNotIn("cluster_member_count", serialized)
        self.assertNotIn("sample_claims", serialized)
        self.assertNotIn("不做主门头", serialized)
        for item in body["items"]:
            self.assertEqual(item["version"], "hxy-review-topic.v1")
            self.assertIn("decision_question", item)
            self.assertIn("why_it_matters", item)
            self.assertIn("next_action", item)
            self.assertFalse(item["official_use_allowed"])
            self.assertTrue(item["requires_human_review"])

    def test_operating_brain_compiler_review_topics_prefers_core_decision_topics(self):
        wiki_dir = self.root / "knowledge" / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "claim-triage.json").write_text(
            json.dumps(
                {
                    "version": "hxy-claim-triage.v1",
                    "total_claim_count": 218895,
                    "cluster_count": 15657,
                    "items": [
                        {
                            "claim_id": "raw-claim",
                            "claim": "某一条机器候选 claim 不应该成为前台审核对象。",
                            "review_group": "general",
                            "priority": "high",
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        (wiki_dir / "core-decision-topics.json").write_text(
            json.dumps(
                {
                    "version": "hxy-core-decision-topics.v1",
                    "status": "ready",
                    "core_topic_count": 1,
                    "raw_claims_hidden": True,
                    "items": [
                        {
                            "version": "hxy-core-decision-topic.v1",
                            "topic_id": "hxy-core-topic:brand-positioning",
                            "topic_key": "brand_positioning",
                            "title": "品牌战略与核爆点定位",
                            "decision_question": "这个判断现在能不能作为首店开业和对外口径的依据？",
                            "why_it_matters": "定位没定清楚，前台话术、门头、内容和员工训练都会漂。",
                            "next_action": "补齐用户原话、复述测试、付费理由和替代方案。",
                            "priority": "P0",
                            "evidence_count": 3,
                            "source_samples": ["00_项目总览.md"],
                            "official_use_allowed": False,
                            "requires_human_review": True,
                        }
                    ],
                    "official_use_allowed": False,
                    "requires_human_review": True,
                    "authority_rule": "core_decision_topics_are_review_objects_claim_triage_is_machine_intermediate",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/knowledge-compiler/review-topics?limit=10")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-review-topics.v1")
        self.assertEqual(body["source"], "core_decision_topics")
        self.assertEqual(body["count"], 1)
        self.assertTrue(body["raw_claims_hidden"])
        serialized = json.dumps(body, ensure_ascii=False)
        self.assertIn("品牌战略与核爆点定位", serialized)
        self.assertIn("首店开业", serialized)
        self.assertNotIn("某一条机器候选 claim", serialized)
        self.assertNotIn("claim_id", serialized)

    def test_operating_brain_compiler_compliance_review_pack_endpoint_is_read_only(self):
        wiki_dir = self.root / "knowledge" / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "compliance-review-pack.json").write_text(
            json.dumps(
                {
                    "version": "hxy-compliance-review-pack.v1",
                    "status": "needs_human_review",
                    "count": 1,
                    "items": [
                        {
                            "claim_id": "risk-001",
                            "claim": "员工不能承诺治疗、保证有效或一次见效。",
                            "risk_level": "P0",
                            "required_decision": "approve_as_rule, needs_revision, or reject",
                            "official_use_allowed": False,
                            "publish_allowed": False,
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/knowledge-compiler/compliance-review-pack")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-compliance-review-pack.v1")
        self.assertEqual(body["status"], "needs_human_review")
        self.assertEqual(body["count"], 1)
        self.assertFalse(body["official_use_allowed"])
        self.assertFalse(body["publish_allowed"])
        self.assertTrue(body["requires_human_review"])
        self.assertEqual(body["items"][0]["claim_id"], "risk-001")
        self.assertFalse(body["items"][0]["official_use_allowed"])
        self.assertFalse(body["items"][0]["publish_allowed"])

    def test_operating_brain_compiler_review_decision_records_decision_and_creates_draft_card(self):
        wiki_dir = self.root / "knowledge" / "wiki"
        wiki_dir.mkdir(parents=True)
        (wiki_dir / "review-queue.json").write_text(
            json.dumps(
                {
                    "version": "hxy-review-queue.v1",
                    "items": [
                        {
                            "claim_id": "claim-001",
                            "claim": "荷小悦不是传统足疗店，而是社区轻养生门店。",
                            "domain": "brand_positioning",
                            "review_group": "brand_positioning",
                            "priority": "high",
                            "risk_flags": [],
                            "sources": ["source.pdf"],
                        }
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.post(
            "/api/operating-brain/knowledge-compiler/review-queue/claim-001/decision",
            json={"action": "pass_to_draft", "reviewer": "founder", "note": "先做草稿，不批准。"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-compiler-review-decision.v1")
        self.assertEqual(body["decision"]["action"], "pass_to_draft")
        self.assertEqual(body["answer_card_draft"]["status"], "draft")
        self.assertFalse(body["answer_card_draft"]["official_use_allowed"])
        self.assertTrue((wiki_dir / "review-decisions.json").is_file())
        decisions = json.loads((wiki_dir / "review-decisions.json").read_text(encoding="utf-8"))
        self.assertEqual(decisions["items"][0]["claim_id"], "claim-001")

    def test_operating_brain_benchmark_corrections_endpoint_reads_latest_corrections(self):
        runs_dir = self.root / "knowledge" / "runs" / "benchmark-loop-latest"
        runs_dir.mkdir(parents=True)
        (runs_dir / "benchmark-corrections.json").write_text(
            json.dumps(
                {
                    "version": "hxy-benchmark-correction-package.v1",
                    "benchmark_version": "hxy-brain-benchmark.v1",
                    "task_count": 2,
                    "tasks": [
                        {
                            "task_id": "benchmark-fix-brand-001",
                            "case_id": "brand-001",
                            "domain": "brand_positioning",
                            "question": "荷小悦是什么？",
                            "failed_checks": ["missing_citation"],
                            "warnings": ["lifecycle_not_explicit"],
                            "recommended_reviewer": "品牌/产品负责人",
                            "required_action": "补充已批准答案卡引用。",
                            "status": "open",
                        },
                        {
                            "task_id": "benchmark-fix-product-001",
                            "case_id": "product-001",
                            "domain": "product_system",
                            "question": "清泡调补养怎么讲？",
                            "failed_checks": ["missing_citation"],
                            "warnings": [],
                            "recommended_reviewer": "品牌/产品负责人",
                            "required_action": "补充已批准答案卡引用。",
                            "status": "open",
                        },
                    ],
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/benchmark/corrections?limit=1")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-benchmark-corrections.v1")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["total"], 2)
        self.assertEqual(body["items"][0]["case_id"], "brand-001")
        self.assertFalse(body["items"][0]["official_use_allowed"])
        self.assertIn("correction_package", body["items"][0])

    def test_hxy_p0_reviewer_todo_endpoint_is_read_only_and_hxy_owned(self):
        runs_dir = self.root / "knowledge" / "runs" / "benchmark-loop-latest"
        runs_dir.mkdir(parents=True)
        decisions_path = runs_dir / "p0-review-decisions.json"
        decisions_payload = {
            "version": "hxy-p0-review-decisions.v1",
            "decision_count": 4,
            "publish_allowed": False,
            "write_to_database": False,
            "manual_decisions": [
                {"source_case_id": "compliance-medical-001", "action": "pending"},
                {"source_case_id": "compliance-effect-001", "action": "pending"},
                {"source_case_id": "compliance-marketing-001", "action": "pending"},
                {"source_case_id": "risk-002", "action": "pending"},
            ],
        }
        decisions_path.write_text(json.dumps(decisions_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        before_decisions = decisions_path.read_text(encoding="utf-8")
        (runs_dir / "p0-reviewer-todo.json").write_text(
            json.dumps(
                {
                    "version": "hxy-p0-reviewer-todo.v1",
                    "item_count": 4,
                    "pending_count": 4,
                    "actioned_count": 0,
                    "items": [
                        {
                            "source_case_id": "compliance-medical-001",
                            "question_pattern": "泡脚能治失眠吗？",
                            "current_action": "pending",
                            "edit_target": "p0-review-decisions.json items[source_case_id=compliance-medical-001]",
                            "official_use_allowed": False,
                            "publish_allowed": False,
                            "write_to_database": False,
                        }
                    ],
                    "official_use_allowed": False,
                    "publish_allowed": False,
                    "write_to_database": False,
                    "requires_human_review": True,
                    "authority_rule": "p0_reviewer_todo_does_not_publish_approved_cards",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/v1/hxy/p0/reviewer-todo")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-p0-reviewer-todo.v1")
        self.assertEqual(body["status"], "ready")
        self.assertEqual(body["run_id"], "benchmark-loop-latest")
        self.assertEqual(body["pending_count"], 4)
        self.assertEqual(body["actioned_count"], 0)
        self.assertFalse(body["write_to_database"])
        self.assertFalse(body["publish_allowed"])
        self.assertFalse(body["official_use_allowed"])
        self.assertTrue(body["requires_human_review"])
        self.assertEqual(body["items"][0]["source_case_id"], "compliance-medical-001")
        self.assertFalse(body["items"][0]["write_to_database"])
        self.assertEqual(decisions_path.read_text(encoding="utf-8"), before_decisions)
        self.assertEqual(len(self.repo.saved_review_tasks), 0)
        self.assertNotIn("htops", json.dumps(body, ensure_ascii=False).lower())

    def test_hxy_p0_reviewer_todo_endpoint_returns_safe_missing_state(self):
        response = self.client.get("/api/v1/hxy/p0/reviewer-todo")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-p0-reviewer-todo.v1")
        self.assertEqual(body["status"], "missing")
        self.assertEqual(body["run_id"], "benchmark-loop-latest")
        self.assertEqual(body["pending_count"], 0)
        self.assertFalse(body["write_to_database"])
        self.assertFalse(body["publish_allowed"])
        self.assertFalse(body["official_use_allowed"])
        self.assertTrue(body["requires_human_review"])
        self.assertIn("next_actions", body)

    def test_hxy_p0_reviewer_todo_endpoint_rejects_unsafe_run_id(self):
        response = self.client.get("/api/v1/hxy/p0/reviewer-todo?run_id=../../htops")

        self.assertEqual(response.status_code, 400)

    def test_hxy_p0_governance_status_endpoint_is_read_only(self):
        response = self.client.get("/api/v1/hxy/p0/governance-status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-p0-governance-status.v1")
        self.assertEqual(body["run_id"], "benchmark-loop-latest")
        self.assertEqual(body["current_step"], "missing_stub")
        self.assertTrue(body["blocked"])
        self.assertFalse(body["write_to_database"])
        self.assertEqual(body["authority_rule"], "status_check_is_read_only")
        self.assertIn("p0_reviewer_todo_url", body)
        self.assertEqual(len(self.repo.saved_review_tasks), 0)
        self.assertNotIn("htops", json.dumps(body, ensure_ascii=False).lower())

    def test_hxy_p0_governance_status_endpoint_rejects_unsafe_run_id(self):
        response = self.client.get("/api/v1/hxy/p0/governance-status?run_id=../htops")

        self.assertEqual(response.status_code, 400)

    def test_hxy_p0_notification_endpoint_builds_read_only_hermes_payload(self):
        response = self.client.get("/api/v1/hxy/p0/notification")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-p0-governance-notification.v1")
        self.assertEqual(body["run_id"], "benchmark-loop-latest")
        self.assertEqual(body["channel"], "hermes_feishu")
        self.assertFalse(body["send_allowed"])
        self.assertFalse(body["write_to_database"])
        self.assertFalse(body["publish_allowed"])
        self.assertFalse(body["official_use_allowed"])
        self.assertIn("HXY P0 Governance Status", body["text"])
        self.assertIn("Current step: missing_stub", body["text"])
        self.assertIn("/api/v1/hxy/p0/governance-status?run_id=benchmark-loop-latest", body["links"]["status_api"])
        self.assertIn("/api/v1/hxy/p0/reviewer-todo?run_id=benchmark-loop-latest", body["links"]["reviewer_todo_api"])
        self.assertEqual(len(self.repo.saved_review_tasks), 0)
        self.assertNotIn("htops", json.dumps(body, ensure_ascii=False).lower())

    def test_hxy_p0_decision_preview_validates_without_writing_decisions(self):
        runs_dir = self.root / "knowledge" / "runs" / "benchmark-loop-latest"
        runs_dir.mkdir(parents=True)
        (runs_dir / "p0-review-decisions.stub.json").write_text(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions.v1",
                    "decision_count": 1,
                    "items": [
                        {
                            "source_case_id": "compliance-effect-001",
                            "source_task_id": "authority-gap-compliance-effect-001",
                            "question_pattern": "泡脚多久能见效？",
                            "reviewer": "运营/合规负责人",
                            "action": "pending",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        decisions_path = runs_dir / "p0-review-decisions.json"
        decisions_path.write_text(
            json.dumps(
                {
                    "version": "hxy-p0-review-decisions.v1",
                    "items": [
                        {
                            "source_case_id": "compliance-effect-001",
                            "source_task_id": "authority-gap-compliance-effect-001",
                            "action": "pending",
                        }
                    ],
                    "write_to_database": False,
                    "publish_allowed": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        before_decisions = decisions_path.read_text(encoding="utf-8")

        response = self.client.post(
            "/api/v1/hxy/p0/decision-preview",
            json={
                "decisions": {
                    "version": "hxy-p0-review-decisions.v1",
                    "items": [
                        {
                            "source_case_id": "compliance-effect-001",
                            "source_task_id": "authority-gap-compliance-effect-001",
                            "action": "approve",
                            "reviewer": "运营/合规负责人",
                            "publication_metadata": {},
                        }
                    ],
                }
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-p0-decision-preview.v1")
        self.assertFalse(body["valid"])
        self.assertFalse(body["write_to_database"])
        self.assertFalse(body["publish_allowed"])
        self.assertFalse(body["official_use_allowed"])
        self.assertTrue(body["requires_human_review"])
        self.assertEqual(body["validation"]["error_count"], 1)
        self.assertEqual(body["validation"]["errors"][0]["code"], "missing_publication_metadata")
        self.assertEqual(decisions_path.read_text(encoding="utf-8"), before_decisions)
        self.assertEqual(len(self.repo.saved_review_tasks), 0)

    def test_operating_brain_governance_run_package_endpoint_returns_auditable_package(self):
        inbox = self.root / "knowledge" / "raw" / "inbox"
        inbox.mkdir(parents=True, exist_ok=True)
        (inbox / "brand.md").write_text("荷小悦品牌资料", encoding="utf-8")
        (self.root / "quarantine" / "knowledge-assets" / "structured").mkdir(parents=True)
        (self.root / "quarantine" / "knowledge-assets" / "structured" / "claims.json").write_text(
            json.dumps(
                [
                    {
                        "claim_id": "claim-no-evidence",
                        "claim_type": "brand_positioning",
                        "claim": "荷小悦是社区轻恢复品牌",
                        "status": "current_candidate",
                        "confidence": 0.62,
                        "evidence_ids": [],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/governance-run-package?run_id=test-run")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-governance-run-package.v1")
        self.assertEqual(body["run_id"], "test-run")
        self.assertIn("incremental_compile_plan", body)
        self.assertIn("governance_report", body)
        self.assertIn("recommended_persistence", body)
        self.assertIn("review_task_drafts", body)
        self.assertGreaterEqual(body["summary"]["blocking_issues"], 1)

    def test_operating_brain_governance_run_package_can_create_review_tasks_when_requested(self):
        (self.root / "quarantine" / "knowledge-assets" / "structured").mkdir(parents=True)
        (self.root / "quarantine" / "knowledge-assets" / "structured" / "claims.json").write_text(
            json.dumps(
                [
                    {
                        "claim_id": "claim-no-evidence",
                        "claim_type": "brand_positioning",
                        "claim": "荷小悦是社区轻恢复品牌",
                        "status": "current_candidate",
                        "confidence": 0.62,
                        "evidence_ids": [],
                    }
                ],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        preview = self.client.get("/api/operating-brain/governance-run-package?run_id=test-run&create_tasks=true")
        self.assertEqual(preview.status_code, 200)
        self.assertNotIn("created_review_tasks", preview.json())
        self.assertEqual(len(self.repo.saved_review_tasks), 0)

        response = self.client.post("/api/operating-brain/governance-run-package/review-tasks?run_id=test-run")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("created_review_tasks", body)
        self.assertGreaterEqual(len(body["created_review_tasks"]), 1)
        self.assertGreaterEqual(len(self.repo.saved_review_tasks), 1)
        task = self.repo.saved_review_tasks[0]
        self.assertEqual(task["intent"], "knowledge_governance")
        self.assertEqual(task["reason"], "claim_missing_evidence")
        self.assertEqual(task["priority"], "high")
        self.assertIn("correction_package", task)

    def test_operating_brain_governance_review_task_creation_requires_auth(self):
        response = self.client.post(
            "/api/operating-brain/governance-run-package/review-tasks?run_id=test-run",
            headers={"Authorization": ""},
        )

        self.assertEqual(response.status_code, 401)

    def test_operating_brain_governance_review_task_creation_requires_configured_token(self):
        os.environ.pop("HXY_API_TOKEN", None)
        module = importlib.import_module("apps.api.hxy_knowledge_api")
        app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo)
        client = TestClient(app)

        response = client.post("/api/operating-brain/governance-run-package/review-tasks?run_id=test-run")

        self.assertEqual(response.status_code, 503)
        self.assertIn("HXY_API_TOKEN", response.json()["detail"])

    def test_operating_brain_process_memory_preview_does_not_create_review_task(self):
        response = self.client.post(
            "/api/operating-brain/process-memory/preview",
            json={
                "text": "不要再用满电回家这个表达，太抽象。以后品牌表达要口语化。",
                "source": "chat",
                "actor": "founder",
                "target_domain": "brand_strategy",
                "confidence": 0.82,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-process-memory-preview.v1")
        self.assertEqual(body["record"]["memory_type"], "rejection")
        self.assertEqual(body["promotion_draft"]["target_status"], "current_candidate")
        self.assertFalse(body["promotion_draft"]["official_use_allowed"])
        self.assertEqual(len(self.repo.saved_review_tasks), 0)

    def test_operating_brain_ingest_loop_status_returns_missing_when_not_run(self):
        response = self.client.get("/api/operating-brain/ingest-loop/status")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-ingest-loop-status.v1")
        self.assertEqual(body["status"], "missing")
        self.assertFalse(body["official_use_allowed"])

    def test_operating_brain_ingest_loop_run_requires_auth_and_stops_at_review(self):
        (self.root / "knowledge" / "raw" / "inbox" / "brand.md").write_text(
            "荷小悦是社区轻养生品牌。不能说治疗失眠。",
            encoding="utf-8",
        )

        response = self.client.post("/api/operating-brain/ingest-loop/run")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-ingest-loop-state.v1")
        self.assertEqual(body["status"], "review_required")
        self.assertFalse(body["official_use_allowed"])

    def test_operating_brain_brand_decision_review_requires_auth_and_does_not_approve(self):
        response = self.client.post(
            "/api/operating-brain/brand-decision/review",
            json={
                "artifact_type": "storefront",
                "stage": "first_store_opening",
                "text": "荷小悦 草本泡脚按摩\n草本真现煮，按出真功夫",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-brand-decision-review.v1")
        self.assertEqual(body["artifact_type"], "storefront")
        self.assertFalse(body["official_use_allowed"])
        self.assertTrue(body["requires_human_review"])
        self.assertTrue((self.root / "knowledge" / "brand" / "reviews").exists())

    def test_compliance_preflight_attaches_to_brand_decision_review(self):
        response = self.client.post(
            "/api/operating-brain/brand-decision/review",
            json={
                "artifact_type": "opening_content",
                "stage": "first_store_opening",
                "text": "泡脚能治疗失眠，一次见效。",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        preflight = body["compliance_preflight"]
        self.assertEqual(preflight["workflow_type"], "content_publish")
        self.assertEqual(preflight["workflow_status"], "blocked")
        self.assertFalse(preflight["can_continue"])
        self.assertFalse(body["can_continue"])
        self.assertFalse(body["can_publish"])

    def test_operating_brain_workspace_event_creates_and_lists_latest_topic(self):
        response = self.client.post(
            "/api/operating-brain/workspace/events",
            json={
                "topic": "清泡调补养公域素材讨论",
                "actor": "founder",
                "role": "operator",
                "visibility": "public_org",
                "input": "整理一次 AI 工作区讨论，先作为过程记忆。",
                "ai_output": {"summary": "需要沉淀素材方向，但不能直接进入正式知识。"},
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-workspace-event-created.v1")
        self.assertFalse(body["event"]["official_use_allowed"])

        list_response = self.client.get("/api/operating-brain/workspace/events?limit=10")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["items"][0]["topic"], "清泡调补养公域素材讨论")

    def test_operating_brain_workspace_event_list_redacts_restricted_payload(self):
        create_response = self.client.post(
            "/api/operating-brain/workspace/events",
            json={
                "topic": "敏感配置排查",
                "actor": "ops",
                "role": "operator",
                "visibility": "public_org",
                "input": "本次排查发现 HXY_API_TOKEN=secret-value，不能公开展示。",
                "ai_output": {"summary": "需要红线处理。"},
            },
        )
        self.assertEqual(create_response.status_code, 200)

        response = self.client.get("/api/operating-brain/workspace/events?limit=10")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("secret-value", response.text)
        self.assertEqual(body["items"][0]["visibility"], "redacted_public")

    def test_operating_brain_workspace_event_review_task_does_not_approve_knowledge(self):
        create_response = self.client.post(
            "/api/operating-brain/workspace/events",
            json={
                "topic": "员工话术候选",
                "actor": "founder",
                "role": "operator",
                "visibility": "public_org",
                "input": "候选话术需要运营负责人复核后才可外用。",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        event_id = create_response.json()["event"]["event_id"]

        response = self.client.post(f"/api/operating-brain/workspace/events/{event_id}/review-task")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "review_task_created")
        self.assertFalse(body["official_use_allowed"])
        self.assertEqual(self.repo.saved_review_task["reason"], "workspace_event_review")
        self.assertEqual(self.repo.saved_review_task["intent"], "workspace_event_review")

    def test_operating_brain_workspace_event_review_task_rejects_private_draft(self):
        create_response = self.client.post(
            "/api/operating-brain/workspace/events",
            json={
                "topic": "创始人私密草稿",
                "visibility": "private_draft",
                "input": "这只是私人推演，不允许进入复核流。",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        event_id = create_response.json()["event"]["event_id"]

        response = self.client.post(f"/api/operating-brain/workspace/events/{event_id}/review-task")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(len(self.repo.saved_review_tasks), 0)

    def test_operating_brain_workspace_event_process_memory_rejects_private_draft(self):
        create_response = self.client.post(
            "/api/operating-brain/workspace/events",
            json={
                "topic": "创始人私密草稿",
                "actor": "founder",
                "role": "founder",
                "visibility": "private_draft",
                "input": "这只是私人推演，不允许进入过程记忆处理。",
            },
        )
        self.assertEqual(create_response.status_code, 200)
        event_id = create_response.json()["event"]["event_id"]

        response = self.client.post(f"/api/operating-brain/workspace/events/{event_id}/process-memory")

        self.assertEqual(response.status_code, 400)

    def test_operating_brain_workspace_event_detail_hides_private_draft(self):
        create_response = self.client.post(
            "/api/operating-brain/workspace/events",
            json={
                "topic": "创始人私密草稿",
                "visibility": "private_draft",
                "input": "HXY_API_TOKEN=private-secret",
                "ai_output": {"summary": "内部草稿内容"},
            },
        )
        self.assertEqual(create_response.status_code, 200)
        event_id = create_response.json()["event"]["event_id"]

        response = self.client.get(f"/api/operating-brain/workspace/events/{event_id}")

        self.assertEqual(response.status_code, 404)
        self.assertNotIn("private-secret", response.text)

    def test_operating_brain_workspace_event_process_memory_preview_for_public_event(self):
        create_response = self.client.post(
            "/api/operating-brain/workspace/events",
            json={
                "topic": "品牌表达过程记录",
                "actor": "founder",
                "role": "operator",
                "visibility": "public_org",
                "input": "以后品牌表达要更口语化，但仍需复核后才能成为正式知识。",
                "ai_output": {"summary": "形成一条过程记忆预览。"},
            },
        )
        self.assertEqual(create_response.status_code, 200)
        event_id = create_response.json()["event"]["event_id"]

        response = self.client.post(f"/api/operating-brain/workspace/events/{event_id}/process-memory")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-process-memory-preview.v1")
        self.assertEqual(body["status"], "process_memory_preview_created")
        self.assertIn("process memory cannot be formal knowledge", json.dumps(body["boundary"], ensure_ascii=False))

    def test_operating_brain_process_memory_promotion_creates_review_task_with_auth(self):
        response = self.client.post(
            "/api/operating-brain/process-memory/promote",
            json={
                "text": "待验证假设：清泡调补养是荷小悦核爆点，需要复述测试。",
                "source": "strategy_discussion",
                "actor": "founder",
                "target_domain": "brand_strategy",
                "confidence": 0.76,
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-process-memory-promotion-result.v1")
        self.assertEqual(body["review_task_id"], "review-task-test-id")
        self.assertEqual(self.repo.saved_review_task["intent"], "process_memory_promotion")
        self.assertEqual(self.repo.saved_review_task["reason"], "promote_process_memory")
        self.assertIn("correction_package", self.repo.saved_review_task)
        self.assertEqual(
            self.repo.saved_review_task["correction_package"]["source_memory_id"],
            body["record"]["memory_id"],
        )

    def test_operating_brain_process_memory_promotion_requires_configured_token(self):
        os.environ.pop("HXY_API_TOKEN", None)
        module = importlib.import_module("apps.api.hxy_knowledge_api")
        app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo)
        client = TestClient(app)

        response = client.post(
            "/api/operating-brain/process-memory/promote",
            json={"text": "以后表达要口语化。"},
        )

        self.assertEqual(response.status_code, 503)
        self.assertIn("HXY_API_TOKEN", response.json()["detail"])

    def test_operating_brain_issues_endpoint_returns_lifecycle_issue_queue(self):
        okf_dir = self.root / "knowledge" / "okf" / "core"
        okf_dir.mkdir(parents=True)
        (okf_dir / "franchise.md").write_text(
            """---
type: decision
title: 招商单店模型
domain: franchise
status: draft
confidence: 0.52
last_confirmed: 2026-01-01
owner: 创始人
used_by:
  - franchise_pitch
---

招商单店模型需要补齐数据后再外讲。
""",
            encoding="utf-8",
        )

        response = self.client.get("/api/operating-brain/issues")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-operating-issue-queue.v1")
        self.assertEqual(body["source"], "okf_lifecycle")
        self.assertEqual(body["count"], 1)
        issue = body["items"][0]
        self.assertEqual(issue["version"], "hxy-operating-issue.v1")
        self.assertEqual(issue["issue_type"], "证据不足")
        self.assertEqual(issue["domain"], "franchise")
        self.assertIn("招商单店模型", issue["title"])
        self.assertIn("补齐", " ".join(issue["next_actions"]))
        visible_issue_text = " ".join(
            [issue["evidence_gap"], issue["risk_boundary"], *issue["next_actions"]]
        )
        self.assertNotIn("last_confirmed", visible_issue_text)
        self.assertNotIn("confidence", visible_issue_text)

    def test_operating_brain_issue_intake_endpoint_creates_actionable_issue(self):
        response = self.client.post(
            "/api/operating-brain/issues/intake",
            json={
                "input": "员工说清泡可以治疗失眠，需要纠偏并复训",
                "scenario": "门店员工培训",
                "role": "运营",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-operating-issue.v1")
        self.assertEqual(body["issue_type"], "员工训练纠偏")
        self.assertEqual(body["priority"], "high")
        self.assertEqual(body["memory_target"], "training_card")
        self.assertIn("治疗", body["risk_boundary"])

    def test_answer_cards_endpoint_returns_repository_and_builtin_approved_cards(self):
        self.repo.answer_cards.append(
            {
                "card_id": "repo-card-1",
                "question_pattern": "门店例会怎么开？",
                "intent": "operations",
                "audience": "store_manager",
                "answer": "先看本周顾客反馈，再看员工话术执行，最后定下一个复盘动作。",
                "status": "approved",
                "review_status": "approved_v1",
                "version": "v1.0",
                "role_versions": {"store_manager": "按反馈、执行、动作三段开。"},
                "forbidden_terms": [],
                "applicable_scenarios": ["门店经营"],
                "aliases": [],
            }
        )

        response = self.client.get("/api/knowledge/answer-cards?status=approved&limit=20")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertGreater(body["count"], 1)
        questions = {item["question_pattern"] for item in body["items"]}
        self.assertIn("门店例会怎么开？", questions)
        self.assertIn("荷小悦是什么？", questions)
        repo_card = next(item for item in body["items"] if item["question_pattern"] == "门店例会怎么开？")
        self.assertFalse(repo_card["builtin"])
        self.assertEqual(repo_card["source"], "repository")
        builtin_card = next(item for item in body["items"] if item["question_pattern"] == "荷小悦是什么？")
        self.assertTrue(builtin_card["builtin"])
        self.assertEqual(builtin_card["source"], "builtin")
        self.assertEqual(builtin_card["status"], "approved")

    def test_operating_brain_understand_endpoint_returns_depth_and_application_contract(self):
        response = self.client.post(
            "/api/operating-brain/understand",
            json={
                "input": "清泡调补养怎么给门店员工培训？",
                "scenario": "门店员工培训",
                "role": "store_staff",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("intent", body)
        self.assertIn("depth", body)
        self.assertIn("applications", body)
        self.assertIn("executability_gate", body)
        self.assertEqual(body["intent"]["mode"], "deep_understanding")
        self.assertIn("main_conflict", body["depth"]["D5_judgment"])
        self.assertIn("store_staff", body["applications"]["A1_role_output"])
        self.assertIn("thinking_lenses", body)

    def test_operating_brain_thinking_lenses_endpoint_returns_guiding_questions(self):
        response = self.client.post(
            "/api/operating-brain/thinking-lenses",
            json={
                "input": "泡脚方定价太难，药材成本降不下来，加盟商觉得回本慢",
                "scenario": "创始人内部决策",
                "stage": "zero_to_one",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        lens_keys = [item["key"] for item in body["lenses"]]
        self.assertEqual(body["stage"], "zero_to_one")
        self.assertEqual(body["sequence"], ["jtbd_positioning", "niche_focus", "unit_economics"])
        self.assertIn("jtbd_positioning", lens_keys)
        self.assertIn("unit_economics", lens_keys)
        self.assertIn("guiding_questions", body)
        self.assertIn("药材成本", " ".join(body["guiding_questions"]))
        self.assertIn("LTV", " ".join(body["guiding_questions"]))
        self.assertNotIn("Stay hungry", str(body))

    def test_operating_brain_workbench_intake_routes_multimodal_team_workflows(self):
        response = self.client.post(
            "/api/operating-brain/workbench-intake",
            json={
                "input": "上传这张菜单图，自动识别分类并沉淀为资料记忆",
                "scenario": "资料记忆",
                "role": "运营",
                "attachments": [{"name": "menu.png", "type": "image/png"}],
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["input_type"], "knowledge_intake")
        self.assertEqual(body["primary_workflow"], "ingest")
        self.assertIn("资料变记忆", body["team_value"])
        self.assertIn("分类结果", body["inspector_shape"])
        self.assertIn("复核", body["memory_action"])

    def test_operating_brain_workbench_intake_uses_ai_judgment_for_ambiguous_workflows(self):
        router = FakeModelRouter(
            output='{"input_type":"correction","primary_workflow":"correct","team_value":["纠偏进化","统一口径"],"answer_shape":["错误点","正确口径","影响范围","下一步复核"],"inspector_shape":["当前理解","自动分类结果","纠偏任务","记忆动作"],"memory_action":"生成纠偏任务；复核后更新答案卡或训练卡。","next_actions":["定位错误口径","补充权威资料","提交运营负责人复核"],"confidence":0.91,"reason":"用户在要求重做上一条答案，不是普通问答。"}'
        )
        app = importlib.import_module("apps.api.hxy_knowledge_api").create_app(
            root_dir=self.root,
            repository_factory=lambda: self.repo,
            model_router=router,
        )
        client = TestClient(app)

        response = client.post(
            "/api/operating-brain/workbench-intake",
            json={
                "input": "刚才那个不行，按总部最新口径重做",
                "scenario": "统一口径",
                "role": "运营",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["input_type"], "correction")
        self.assertEqual(body["primary_workflow"], "correct")
        self.assertEqual(body["intake_judgment"]["mode"], "ai")
        self.assertEqual(body["intake_judgment"]["task_type"], "workbench_intake")
        self.assertIn("纠偏进化", body["team_value"])
        self.assertEqual(router.generate_calls[0]["task_type"], "workbench_intake")

    def test_operating_brain_source_brief_returns_notebook_style_business_brief(self):
        self.repo.search_items = [
            {
                "chunk_id": "chunk-product-1",
                "asset_id": "asset-product",
                "title": "清泡调补养产品手册",
                "source_path": "/root/hxy/knowledge/raw/inbox/product.md",
                "normalized_path": "/root/hxy/knowledge/normalized/product.md",
                "domain": "product",
                "stage": "approved",
                "content": "清泡是基础放松，调泡按近期状态做调理表达，补泡强调疲劳后的恢复感，养泡适合长期保养。门店员工不得承诺治疗失眠。",
                "score": 80,
            }
        ]

        response = self.client.post(
            "/api/operating-brain/source-brief",
            json={"question": "清泡调补养资料怎么用于门店培训？", "scenario": "门店员工培训", "limit": 5},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-source-brief.v1")
        self.assertEqual(body["workflow"], "source_brief")
        self.assertEqual(body["query"], "清泡调补养资料怎么用于门店培训？")
        self.assertIn("ask", {item["key"] for item in body["open_notebook_patterns"]})
        self.assertIn("transformations", {item["key"] for item in body["open_notebook_patterns"]})
        self.assertEqual(body["context_plan"][0]["context_level"], "full")
        self.assertIn("训练素材生成", {item["name"] for item in body["transformations"]})
        self.assertIn("答案卡", body["deliverables"])
        serialized = response.text
        self.assertNotIn("source_path", serialized)
        self.assertNotIn("chunk-product-1", serialized)

    def test_operating_brain_source_brief_falls_back_when_initial_hits_are_metadata_noise(self):
        noisy_content = (
            "file: 荷小悦资料/荷小悦研究资料/荷小悦O2O系统_完整优化方案_V2.0.docx "
            "(44194 bytes) - file: 微信图片_20260528141933.png (281476 bytes)"
        )
        self.repo.search_items_by_query = {
            "资料识别：清泡调补养资料怎么用于门店培训？": [
                {
                    "chunk_id": "chunk-noisy",
                    "asset_id": "asset-noisy",
                    "title": "Desktop",
                    "source_path": "knowledge/raw/inbox/list.md",
                    "normalized_path": "knowledge/normalized/external/preparation/list.md",
                    "domain": "external",
                    "stage": "preparation",
                    "content": noisy_content,
                    "score": 100,
                }
            ],
            "清泡调补养": [
                {
                    "chunk_id": "chunk-product-1",
                    "asset_id": "asset-product",
                    "title": "清泡调补养产品手册",
                    "source_path": "knowledge/raw/inbox/product.md",
                    "normalized_path": "knowledge/normalized/product/preparation/product.md",
                    "domain": "product",
                    "stage": "approved",
                    "content": "清泡是基础放松，调泡按近期状态做调理表达，补泡强调疲劳后的恢复感，养泡适合长期保养。",
                    "score": 80,
                }
            ],
        }

        response = self.client.post(
            "/api/operating-brain/source-brief",
            json={"question": "资料识别：清泡调补养资料怎么用于门店培训？", "scenario": "门店员工培训", "limit": 5},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("清泡是基础放松", " ".join(body["key_findings"]))
        self.assertEqual(body["context_plan"][0]["context_level"], "full")
        self.assertEqual(body["retrieval"]["used_query"], "清泡调补养")
        self.assertIn("清泡调补养", [call["query"] for call in self.repo.search_calls])
        serialized = response.text
        self.assertNotIn("44194 bytes", serialized)
        self.assertNotIn("chunk-noisy", serialized)

    def test_operating_brain_source_brief_chooses_higher_quality_fallback_when_initial_hits_are_mixed_noise(self):
        noisy_content = (
            "file: Desktop.zip (44194 bytes) source_path: knowledge/raw/inbox/Desktop.zip "
            "chunk_id: external:file-listing"
        )
        self.repo.search_items_by_query = {
            "资料识别：清泡调补养资料怎么用于门店培训？": [
                {
                    "chunk_id": "external-noise-1",
                    "asset_id": "asset-external",
                    "title": "Desktop",
                    "source_path": "knowledge/raw/inbox/Desktop.zip",
                    "normalized_path": "knowledge/normalized/external/preparation/list.md",
                    "domain": "external",
                    "stage": "preparation",
                    "content": noisy_content,
                    "score": 95,
                },
                {
                    "chunk_id": "finance-1",
                    "asset_id": "asset-finance",
                    "title": "分账介绍",
                    "source_path": "knowledge/raw/inbox/payment.pdf",
                    "normalized_path": "knowledge/normalized/finance/preparation/payment.md",
                    "domain": "finance",
                    "stage": "preparation",
                    "content": "联合收单、分账和支付结算案例，不涉及清泡调补养门店话术。",
                    "score": 70,
                },
                {
                    "chunk_id": "product-weak",
                    "asset_id": "asset-product-weak",
                    "title": "图片识别片段",
                    "source_path": "knowledge/raw/inbox/menu.png",
                    "normalized_path": "knowledge/normalized/product/preparation/menu.md",
                    "domain": "product",
                    "stage": "pilot",
                    "content": "file: menu.png (281476 bytes) chunk_id: product-weak",
                    "score": 100,
                },
            ],
            "清泡调补养": [
                {
                    "chunk_id": "product-strong-1",
                    "asset_id": "asset-product-strong",
                    "title": "清泡调补养产品手册",
                    "source_path": "knowledge/raw/inbox/product.md",
                    "normalized_path": "knowledge/normalized/product/preparation/product.md",
                    "domain": "product",
                    "stage": "approved",
                    "content": "清泡调补养是荷小悦的泡脚产品分层：清泡是基础放松，调泡看近期状态，补泡讲疲劳恢复感，养泡讲长期保养。门店员工培训要先问状态再推荐泡脚方。",
                    "score": 90,
                },
                {
                    "chunk_id": "product-strong-2",
                    "asset_id": "asset-product-training",
                    "title": "门店员工训练卡",
                    "source_path": "knowledge/raw/inbox/training.md",
                    "normalized_path": "knowledge/normalized/product/approved/training.md",
                    "domain": "product",
                    "stage": "approved",
                    "content": "员工推荐泡脚方时，重点问睡眠、疲劳、手脚凉、压力和久坐情况。",
                    "score": 75,
                },
            ],
        }

        response = self.client.post(
            "/api/operating-brain/source-brief",
            json={"question": "资料识别：清泡调补养资料怎么用于门店培训？", "scenario": "门店员工培训", "limit": 8},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["retrieval"]["used_query"], "清泡调补养")
        self.assertEqual(body["context_plan"][0]["source"], "清泡调补养产品手册")
        self.assertEqual(body["context_plan"][0]["context_level"], "full")
        self.assertIn("员工培训要先问顾客状态", " ".join(body["key_findings"]))
        self.assertIn("清泡调补养", [call["query"] for call in self.repo.search_calls])
        serialized = response.text
        self.assertNotIn("external-noise-1", serialized)
        self.assertNotIn("finance-1", serialized)

    def test_operating_brain_source_brief_orders_product_system_sources_by_business_domain_priority(self):
        self.repo.search_items_by_query = {
            "泡脚方": [
                {
                    "chunk_id": "store-model-1",
                    "asset_id": "asset-store-model",
                    "title": "单店模型研讨",
                    "source_path": "knowledge/raw/inbox/store-model.md",
                    "normalized_path": "knowledge/normalized/store_model/pilot/store-model.md",
                    "domain": "store_model",
                    "stage": "pilot",
                    "content": "荷小悦门店模型资料提到泡脚方、草本泡脚和单店经营策略。",
                    "score": 120,
                },
                {
                    "chunk_id": "product-1",
                    "asset_id": "asset-product",
                    "title": "清泡调补养产品手册",
                    "source_path": "knowledge/raw/inbox/product.md",
                    "normalized_path": "knowledge/normalized/product/approved/product.md",
                    "domain": "product",
                    "stage": "pilot",
                    "content": "清泡调补养是产品体系，门店员工推荐泡脚方时先问状态，再讲清泡、调泡、补泡、养泡。",
                    "score": 120,
                },
            ]
        }

        response = self.client.post(
            "/api/operating-brain/source-brief",
            json={"question": "泡脚方资料怎么用于门店培训？", "scenario": "门店员工培训", "limit": 8},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["retrieval"]["used_query"], "泡脚方")
        self.assertEqual(body["context_plan"][0]["source"], "清泡调补养产品手册")
        self.assertEqual(body["context_plan"][0]["domain"], "product")

    def test_operating_brain_source_brief_prefers_product_source_over_higher_scored_store_model_for_product_system(self):
        self.repo.search_items_by_query = {
            "泡脚方": [
                {
                    "chunk_id": "store-model-strong",
                    "asset_id": "asset-store-model",
                    "title": "单店模型研讨",
                    "source_path": "knowledge/raw/inbox/store-model.md",
                    "normalized_path": "knowledge/normalized/store_model/pilot/store-model.md",
                    "domain": "store_model",
                    "stage": "pilot",
                    "content": "荷小悦门店模型资料提到清泡调补养、泡脚方、产品体系、草本泡脚、一人一方、门店员工、培训、话术和单店经营策略。",
                    "score": 130,
                },
                {
                    "chunk_id": "product-lower-score",
                    "asset_id": "asset-product",
                    "title": "清泡调补养产品手册",
                    "source_path": "knowledge/raw/inbox/product.md",
                    "normalized_path": "knowledge/normalized/product/preparation/product.md",
                    "domain": "product",
                    "stage": "preparation",
                    "content": "清泡调补养是产品体系，门店员工推荐泡脚方时先问状态，再讲清泡、调泡、补泡、养泡。",
                    "score": 100,
                },
            ]
        }

        response = self.client.post(
            "/api/operating-brain/source-brief",
            json={"question": "泡脚方资料怎么用于门店培训？", "scenario": "门店员工培训", "limit": 8},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["context_plan"][0]["source"], "清泡调补养产品手册")
        self.assertEqual(body["context_plan"][0]["domain"], "product")

    def test_training_evaluate_scores_employee_script_and_creates_retrain_task(self):
        response = self.client.post(
            "/api/operating-brain/training/evaluate",
            json={
                "training_item": "清泡调补养门店推荐话术",
                "customer_question": "顾客问：清泡调补养有什么区别？",
                "employee_answer": "清泡便宜，其他就是更贵一点。这个能治疗失眠，泡了肯定有效。",
                "scenario": "门店员工培训",
                "role": "门店员工",
                "employee_id": "emp-001",
                "employee_name": "小悦",
                "store_id": "store-001",
                "store_name": "荷小悦试点店",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-training-evaluation.v1")
        self.assertEqual(body["status"], "evaluated")
        self.assertEqual(body["level"], "retrain")
        self.assertLess(body["score"], 75)
        self.assertIn("需复训", body["result_card"]["business_result"])
        self.assertNotIn("retrain", body["result_card"]["business_result"])
        dimension_keys = {item["key"] for item in body["dimensions"]}
        self.assertEqual(dimension_keys, {"accuracy", "discovery", "compliance", "conversion", "clarity"})
        self.assertTrue(body["needs_retrain"])
        self.assertTrue(body["review_task_id"])
        self.assertIn("复训", body["retraining_task"]["title"])
        self.assertIn("不能承诺治疗", " ".join(body["correction_points"]))
        self.assertIn("顾客问", body["follow_up_questions"][0])
        self.assertEqual(body["training_session_id"], "training-session-test-id")
        self.assertEqual(self.repo.saved_training_sessions[-1]["employee_id"], "emp-001")
        self.assertEqual(self.repo.saved_training_sessions[-1]["store_id"], "store-001")
        self.assertEqual(self.repo.saved_training_sessions[-1]["score"], body["score"])
        self.assertEqual(self.repo.saved_training_sessions[-1]["review_task_id"], "review-task-test-id")
        self.assertEqual(self.repo.saved_review_task["intent"], "training")
        self.assertEqual(self.repo.saved_review_task["reason"], "training_retrain")
        package = self.repo.saved_review_task["correction_package"]
        self.assertEqual(package["failure_type"], "training_gap")
        self.assertIn("复训", package["target"])
        self.assertEqual(package["answer_card_draft"]["status"], "draft")
        self.assertIn("standard_script", body)
        self.assertIn("您好", body["standard_script"])
        self.assertIn("最近", body["standard_script"])
        self.assertIn("清泡", body["standard_script"])
        self.assertNotIn("先问顾客", body["standard_script"])
        self.assertNotIn("建议控制", body["standard_script"])
        self.assertEqual(package["answer_card_draft"]["answer"], body["standard_script"])
        self.assertIn("capability_profile", body)
        self.assertIn("adaptive_retrain_plan", body)
        self.assertIn("weak_modules", body["capability_profile"])
        self.assertGreaterEqual(len(body["adaptive_retrain_plan"]["next_questions"]), 3)
        self.assertIn("operating_metric_links", body["adaptive_retrain_plan"])
        self.assertEqual(self.repo.saved_training_sessions[-1]["capability_profile"]["level"], body["capability_profile"]["level"])

    def test_training_evaluate_high_score_returns_answer_card_draft(self):
        response = self.client.post(
            "/api/operating-brain/training/evaluate",
            json={
                "training_item": "清泡调补养门店推荐话术",
                "customer_question": "顾客问：清泡调补养有什么区别？",
                "employee_answer": "我会先问您最近睡眠、疲劳、手脚凉和压力情况。清泡适合基础放松，调泡根据近期状态做针对性调理表达，补泡强调疲劳后的恢复感，养泡适合长期保养。我们只讲放松和状态建议，不承诺治疗效果。",
                "scenario": "门店员工培训",
                "role": "门店员工",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["level"], "excellent")
        self.assertGreaterEqual(body["score"], 90)
        self.assertFalse(body["needs_retrain"])
        self.assertTrue(body["answer_card_draft"])
        self.assertEqual(body["answer_card_draft"]["status"], "draft")
        self.assertEqual(body["answer_card_draft"]["audience"], "store_staff")
        self.assertIn("清泡", body["answer_card_draft"]["answer"])
        self.assertEqual(self.repo.saved_review_task["reason"], "training_answer_card_candidate")
        self.assertEqual(self.repo.saved_review_task["priority"], "low")

    def test_training_question_bank_endpoint_returns_scientific_curriculum(self):
        response = self.client.get("/api/operating-brain/training/question-bank?level=newbie")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-training-question-bank.v1")
        self.assertGreaterEqual(body["count"], 4)
        modules = {item["module"] for item in body["items"]}
        self.assertIn("basic_knowledge", modules)
        self.assertIn("compliance_risk", modules)
        self.assertTrue(all(item["level"] == "newbie" for item in body["items"]))
        self.assertTrue(all(item["capability_targets"] for item in body["items"]))

    def test_training_manager_acceptance_endpoint_links_result_to_operating_metrics(self):
        response = self.client.post(
            "/api/operating-brain/training/manager-acceptance",
            json={
                "session_id": "training-session-test-id",
                "manager_id": "manager-001",
                "manager_name": "店长",
                "accepted": False,
                "score": 68,
                "note": "仍然没有先问顾客状态。",
                "operating_metric_links": [
                    {"metric": "客单价", "direction": "negative", "reason": "不会升级推荐"},
                    {"metric": "调补养占比", "direction": "negative", "reason": "只推清泡"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-training-manager-acceptance.v1")
        self.assertEqual(body["acceptance_id"], "training-acceptance-test-id")
        self.assertFalse(body["accepted"])
        self.assertTrue(body["requires_retrain"])
        self.assertIn("客单价", body["operating_summary"])
        self.assertEqual(self.repo.saved_training_acceptance["manager_id"], "manager-001")

    def test_training_manager_acceptance_accepts_training_session_id_from_evaluate_response(self):
        response = self.client.post(
            "/api/operating-brain/training/manager-acceptance",
            json={
                "training_session_id": "training-session-test-id",
                "manager_id": "manager-001",
                "manager_name": "店长",
                "accepted": True,
                "onsite_verified": True,
                "score": 82,
                "note": "现场复述通过。",
                "operating_metric_links": [
                    {"metric": "调补养占比", "direction": "positive", "reason": "能讲清升级价值"},
                ],
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["session_id"], "training-session-test-id")
        self.assertFalse(body["requires_retrain"])
        self.assertEqual(self.repo.saved_training_acceptance["session_id"], "training-session-test-id")

    def test_training_manager_acceptance_blocks_pass_without_two_consecutive_passes_and_onsite_check(self):
        self.repo.training_acceptance_evidence_result = {
            "version": "hxy-training-acceptance-evidence.v1",
            "session_id": "training-session-test-id",
            "pass_score": 75,
            "required_pass_count": 2,
            "consecutive_pass_count": 1,
            "eligible": False,
            "reason": "同一训练项目最近只连续达标 1 次，还需要 2 次。",
        }

        response = self.client.post(
            "/api/operating-brain/training/manager-acceptance",
            json={
                "session_id": "training-session-test-id",
                "manager_id": "manager-001",
                "manager_name": "店长",
                "accepted": True,
                "score": 88,
                "onsite_verified": False,
                "note": "店长误点通过。",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["accepted"])
        self.assertTrue(body["requires_retrain"])
        self.assertEqual(body["acceptance_rule"]["consecutive_pass_count"], 1)
        self.assertFalse(body["acceptance_rule"]["onsite_verified"])
        self.assertIn("现场复述", body["next_actions"][0])
        self.assertFalse(self.repo.saved_training_acceptance["accepted"])

    def test_training_manager_acceptance_passes_only_with_rule_evidence_and_onsite_check(self):
        response = self.client.post(
            "/api/operating-brain/training/manager-acceptance",
            json={
                "session_id": "training-session-test-id",
                "manager_id": "manager-001",
                "manager_name": "店长",
                "accepted": True,
                "score": 88,
                "onsite_verified": True,
                "note": "连续达标并现场复述通过。",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["accepted"])
        self.assertFalse(body["requires_retrain"])
        self.assertEqual(body["acceptance_rule"]["required_pass_count"], 2)
        self.assertEqual(body["acceptance_rule"]["pass_score"], 75)
        self.assertEqual(body["capability_upgrade"]["current_level"], "standard")
        self.assertEqual(body["capability_upgrade"]["accepted_count"], 2)
        self.assertTrue(self.repo.saved_training_acceptance["onsite_verified"])
        self.assertFalse(self.repo.saved_training_acceptance["requires_retrain"])
        self.assertEqual(self.repo.saved_training_capability_level["employee_id"], "emp-001")
        self.assertEqual(self.repo.saved_training_capability_level["current_level"], "standard")

    def test_training_manager_acceptance_does_not_upgrade_capability_when_retrain_required(self):
        self.repo.training_acceptance_evidence_result = {
            "version": "hxy-training-acceptance-evidence.v1",
            "session_id": "training-session-test-id",
            "employee_id": "emp-001",
            "store_id": "store-001",
            "training_item": "清泡调补养门店推荐话术",
            "pass_score": 75,
            "required_pass_count": 2,
            "consecutive_pass_count": 0,
            "eligible": False,
            "reason": "同一训练项目最近只连续达标 0 次，还需要 2 次。",
        }

        response = self.client.post(
            "/api/operating-brain/training/manager-acceptance",
            json={
                "session_id": "training-session-test-id",
                "manager_id": "manager-001",
                "manager_name": "店长",
                "accepted": True,
                "onsite_verified": True,
                "score": 90,
                "note": "强行通过。",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["accepted"])
        self.assertTrue(body["requires_retrain"])
        self.assertIsNone(body["capability_upgrade"])
        self.assertIsNone(self.repo.saved_training_capability_level)

    def test_training_evaluate_uses_ai_judgment_before_keyword_scoring(self):
        module = importlib.import_module("apps.api.hxy_knowledge_api")
        ai_output = """
        {
          "score": 86,
          "level": "pass",
          "dimensions": [
            {"key": "accuracy", "name": "产品准确性", "score": 84, "detail": "能说明不同方案对应不同状态，不是价格差。"},
            {"key": "discovery", "name": "需求探询", "score": 90, "detail": "能先了解顾客近期状态。"},
            {"key": "compliance", "name": "合规边界", "score": 88, "detail": "没有承诺治疗或保证效果。"},
            {"key": "conversion", "name": "推荐转化", "score": 84, "detail": "能根据顾客状态推荐。"},
            {"key": "clarity", "name": "表达清晰度", "score": 84, "detail": "表达清楚，可直接复述。"}
          ],
          "correction_points": [],
          "standard_script": "您好，我先了解一下您最近睡得怎么样、累不累、手脚冷不冷。您如果只是想放松，可以做基础放松；如果最近疲劳明显，我会给您选更适合恢复感的方案；如果想长期保养，我们就按您的状态做持续养护。我们主要做放松和状态调理建议，不替代医疗治疗。",
          "usable_answer": "训练结果：通过。员工能先了解状态，再给出合规推荐。"
        }
        """
        router = FakeModelRouter(output=ai_output)
        app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo, model_router=router)
        client = TestClient(app)

        response = client.post(
            "/api/operating-brain/training/evaluate",
            json={
                "training_item": "清泡调补养门店推荐话术",
                "customer_question": "顾客问：清泡调补养有什么区别？",
                "employee_answer": "我会先了解您最近休息、疲劳、怕冷和压力情况，再按您的状态给您选适合的放松方案。我们只做放松和状态建议，不讲治疗。",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["score"], 86)
        self.assertEqual(body["level"], "pass")
        self.assertEqual(body["level_label"], "通过")
        self.assertFalse(body["needs_retrain"])
        self.assertEqual(body["training_judgment"]["mode"], "ai")
        self.assertEqual(body["training_judgment"]["model_reason"], "ok")
        self.assertIn("您好，我先了解", body["standard_script"])
        self.assertEqual(self.repo.saved_review_task["reason"], "training_answer_card_candidate")
        self.assertEqual(router.generate_calls[-1]["task_type"], "training_evaluation")
        self.assertIn("不要只按关键词命中打分", router.generate_calls[-1]["messages"][0]["content"])

    def test_training_safety_gate_forces_retrain_when_ai_passes_unsafe_employee_claim(self):
        module = importlib.import_module("apps.api.hxy_knowledge_api")
        ai_output = """
        {
          "score": 94,
          "level": "excellent",
          "dimensions": [
            {"key": "accuracy", "name": "产品准确性", "score": 95, "detail": "产品解释完整。"},
            {"key": "discovery", "name": "需求探询", "score": 92, "detail": "有需求探询。"},
            {"key": "compliance", "name": "合规边界", "score": 96, "detail": "模型误判为合规。"},
            {"key": "conversion", "name": "推荐转化", "score": 94, "detail": "推荐清楚。"},
            {"key": "clarity", "name": "表达清晰度", "score": 93, "detail": "表达清楚。"}
          ],
          "correction_points": [],
          "standard_script": "您好，我先了解您的状态，再按清泡、调泡、补泡、养泡做合适推荐。我们主要做放松和状态建议，不替代医疗治疗。",
          "usable_answer": "训练结果：优秀。"
        }
        """
        router = FakeModelRouter(output=ai_output)
        app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo, model_router=router)
        client = TestClient(app)

        response = client.post(
            "/api/operating-brain/training/evaluate",
            json={
                "training_item": "清泡调补养门店推荐话术",
                "customer_question": "顾客问：清泡调补养有什么区别？",
                "employee_answer": "我先问您睡眠和疲劳情况。这个方子可以治疗失眠，泡完保证有效。",
                "scenario": "门店员工培训",
                "role": "门店员工",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["training_judgment"]["mode"], "ai")
        self.assertFalse(body["training_judgment"]["safety_gate"]["passed"])
        self.assertEqual(body["level"], "retrain")
        self.assertEqual(body["level_label"], "需复训")
        self.assertLess(body["score"], 75)
        self.assertTrue(body["needs_retrain"])
        self.assertIsNone(body["answer_card_draft"])
        self.assertEqual(self.repo.saved_review_task["reason"], "training_retrain")
        self.assertEqual(self.repo.saved_review_task["priority"], "high")
        self.assertIn("不能承诺治疗", " ".join(body["correction_points"]))
        dimensions = {item["key"]: item for item in body["dimensions"]}
        self.assertFalse(dimensions["compliance"]["passed"])
        self.assertLess(dimensions["compliance"]["score"], 75)

    def test_compliance_preflight_prevents_risky_training_from_promotion(self):
        response = self.client.post(
            "/api/operating-brain/training/evaluate",
            json={
                "training_item": "清泡调补养门店推荐话术",
                "customer_question": "顾客问：能不能治失眠？",
                "employee_answer": "可以治疗失眠，一次见效，建议办疗程。",
                "scenario": "门店员工培训",
                "role": "门店员工",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["needs_retrain"])
        self.assertEqual(body["compliance_preflight"]["workflow_type"], "staff_script")
        self.assertEqual(body["compliance_preflight"]["workflow_status"], "blocked")
        self.assertFalse(body["training_artifact_gate"]["can_promote_to_answer_card"])
        self.assertFalse(body["training_artifact_gate"]["official_use_allowed"])

    def test_training_manager_summary_endpoint_returns_actionable_training_metrics(self):
        response = self.client.get("/api/operating-brain/training/manager-summary?store_id=store-001&days=7")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-training-manager-summary.v1")
        self.assertEqual(body["store_id"], "store-001")
        self.assertEqual(body["days"], 7)
        self.assertGreaterEqual(body["total_sessions"], 1)
        self.assertGreaterEqual(body["retrain_count"], 1)
        self.assertIn("low_score_employees", body)
        self.assertIn("top_mistakes", body)
        self.assertIn("suggested_actions", body)
        self.assertIn("briefing_tasks", body)
        self.assertGreaterEqual(len(body["briefing_tasks"]), 1)
        task = body["briefing_tasks"][0]
        self.assertIn("employee_name", task)
        self.assertIn("training_focus", task)
        self.assertIn("practice_question", task)
        self.assertIn("correction_focus", task)
        self.assertIn("acceptance_standard", task)
        self.assertIn("operating_metric", task)
        self.assertIn("operating_impact_signals", body)
        self.assertGreaterEqual(len(body["operating_impact_signals"]), 1)
        signal = body["operating_impact_signals"][0]
        self.assertIn("metric", signal)
        self.assertIn("risk_level", signal)
        self.assertIn("training_signal", signal)
        self.assertIn("next_action", signal)
        self.assertTrue(body["operating_issue_signal"]["should_create_issue"])
        self.assertIn("话术复训", body["operating_issue_signal"]["title"])
        self.assertEqual(self.repo.last_training_summary_request, {"store_id": "store-001", "days": 7})

    def test_training_sessions_endpoint_returns_filtered_history(self):
        response = self.client.get("/api/operating-brain/training/sessions?store_id=store-001&employee_id=emp-001&limit=20")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-training-sessions.v1")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["employee_id"], "emp-001")
        self.assertEqual(body["items"][0]["store_id"], "store-001")
        self.assertTrue(body["items"][0]["needs_retrain"])
        self.assertEqual(body["items"][0]["capability_profile_json"]["level"], "newbie")
        self.assertEqual(body["items"][0]["adaptive_retrain_plan_json"]["target_level"], "newbie")
        self.assertEqual(body["items"][0]["operating_metric_links_json"][0]["metric"], "调补养占比")
        self.assertEqual(
            self.repo.last_training_sessions_request,
            {"store_id": "store-001", "employee_id": "emp-001", "limit": 20},
        )

    def test_training_capability_levels_endpoint_returns_employee_capability_assets(self):
        response = self.client.get("/api/operating-brain/training/capability-levels?store_id=store-001&employee_id=emp-001&limit=20")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-training-capability-levels.v1")
        self.assertEqual(body["store_id"], "store-001")
        self.assertEqual(body["employee_id"], "emp-001")
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["current_level"], "standard")
        self.assertEqual(body["items"][0]["accepted_count"], 2)
        self.assertEqual(
            self.repo.last_training_capability_levels_request,
            {"store_id": "store-001", "employee_id": "emp-001", "limit": 20},
        )

    def test_training_recommended_plan_uses_employee_capability_level(self):
        class CapabilityOnlyRepository(FakeRepository):
            def training_sessions(self, store_id=None, employee_id=None, limit=100):
                self.last_training_sessions_request = {"store_id": store_id, "employee_id": employee_id, "limit": limit}
                return []

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = CapabilityOnlyRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.get("/api/operating-brain/training/recommended-plan?store_id=store-001&employee_id=emp-001")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-training-recommended-plan.v1")
        self.assertEqual(body["store_id"], "store-001")
        self.assertEqual(body["employee_id"], "emp-001")
        self.assertEqual(body["recommended_level"], "standard")
        self.assertEqual(body["source"], "capability_level")
        self.assertGreaterEqual(body["count"], 1)
        self.assertTrue(all(item["level"] == "standard" for item in body["items"]))
        self.assertIn("员工能力档案", body["reason"])
        self.assertEqual(
            repo.last_training_capability_levels_request,
            {"store_id": "store-001", "employee_id": "emp-001", "limit": 1},
        )

    def test_training_recommended_plan_prioritizes_adaptive_retrain_when_latest_session_failed(self):
        response = self.client.get("/api/operating-brain/training/recommended-plan?store_id=store-001&employee_id=emp-001")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["recommended_level"], "newbie")
        self.assertEqual(body["source"], "adaptive_retrain")
        self.assertGreaterEqual(body["count"], 1)
        self.assertEqual(body["items"][0]["question_id"], "newbie-discovery-status")
        self.assertIn("上次训练未达标", body["reason"])
        self.assertNotIn("latest_session", body)
        self.assertNotIn("employee_answer", str(body))
        self.assertEqual(
            self.repo.last_training_sessions_request,
            {"store_id": "store-001", "employee_id": "emp-001", "limit": 1},
        )

    def test_training_recommended_plan_defaults_to_newbie_without_capability_profile(self):
        class NewEmployeeRepository(FakeRepository):
            def training_sessions(self, store_id=None, employee_id=None, limit=100):
                self.last_training_sessions_request = {"store_id": store_id, "employee_id": employee_id, "limit": limit}
                return []

            def training_capability_levels(self, store_id=None, employee_id=None, limit=100):
                self.last_training_capability_levels_request = {"store_id": store_id, "employee_id": employee_id, "limit": limit}
                return []

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = NewEmployeeRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.get("/api/operating-brain/training/recommended-plan?store_id=store-001&employee_id=new-001")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["recommended_level"], "newbie")
        self.assertEqual(body["source"], "default_new_employee")
        self.assertTrue(all(item["level"] == "newbie" for item in body["items"]))
        self.assertIn("先打基础", body["reason"])

    def test_api_serves_employee_training_h5(self):
        page = self.root / "apps" / "employee-web" / "training.html"
        page.parent.mkdir(parents=True)
        page.write_text("<html><title>员工训练</title><body>今日训练</body></html>", encoding="utf-8")

        response = self.client.get("/employee/training")

        self.assertEqual(response.status_code, 200)
        self.assertIn("员工训练", response.text)

    def test_api_serves_manager_training_h5(self):
        page = self.root / "apps" / "manager-web" / "training.html"
        page.parent.mkdir(parents=True)
        page.write_text("<html><title>店长训练看板</title><body>复训优先级</body></html>", encoding="utf-8")

        response = self.client.get("/manager/training")

        self.assertEqual(response.status_code, 200)
        self.assertIn("店长训练看板", response.text)

    def test_operating_brain_workbench_submit_uploads_and_indexes_text_file_as_memory(self):
        response = self.client.post(
            "/api/operating-brain/workbench-submit",
            data={"input": "上传这份门店 SOP，自动识别分类并记忆", "scenario": "资料记忆", "role": "运营"},
            files={"files": ("store-sop.md", "# 门店 SOP\n清泡调补养话术训练".encode("utf-8"), "text/markdown")},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["intake"]["input_type"], "knowledge_intake")
        self.assertEqual(body["memory_result"]["status"], "indexed")
        self.assertEqual(body["memory_result"]["asset_count"], 1)
        self.assertEqual(body["memory_result"]["chunk_count"], 1)
        self.assertIn("store-sop.md", body["uploaded_files"][0]["file_name"])
        self.assertEqual(self.repo.upserted_runs[-1]["status"], "completed")
        self.assertEqual(self.repo.upserted_assets[-1]["status"], "indexed")
        self.assertEqual(self.repo.upserted_chunks[-1]["content"], "# 门店 SOP\n清泡调补养话术训练")
        self.assertIn("组织记忆", body["next_message"])

    def test_operating_brain_workbench_submit_understands_uploaded_image_with_vision_model(self):
        module = importlib.import_module("apps.api.hxy_knowledge_api")

        class VisionRouter(FakeModelRouter):
            def route(self, task_type):
                route = super().route(task_type)
                route["should_call_model"] = task_type == "vision_understanding"
                return route

            def generate(self, task_type, *, messages=None, prompt=None, metadata=None):
                self.generate_calls.append(
                    {"task_type": task_type, "messages": messages or [], "prompt": prompt, "metadata": metadata or {}}
                )
                return {
                    "version": "hxy-model-generation.v1",
                    "used_model": True,
                    "reason": "ok",
                    "route": self.route(task_type),
                    "request_shape": {
                        "message_count": len(messages or []),
                        "has_prompt": bool(prompt),
                        "metadata_keys": sorted((metadata or {}).keys()),
                    },
                    "provider_response_id": "resp_vision",
                    "usage": {},
                    "output": """
                    {
                      "image_type": "menu",
                      "visual_summary": "这是一张荷小悦清泡调补养菜单图，包含草本泡脚、项目分层和价格信息。",
                      "business_summary": "应作为产品体系资料，用于门店员工讲清清泡、调泡、补泡、养泡区别。",
                      "ocr_text": "荷小悦 清泡 调泡 补泡 养泡 ¥68",
                      "detected_entities": ["荷小悦", "清泡调补养", "草本泡脚"],
                      "prices": ["¥68"],
                      "related_domains": ["product", "operations"],
                      "confidence": 0.88,
                      "qa_ready": true,
                      "needs_review": false
                    }
                    """,
                }

        router = VisionRouter()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo, model_router=router)
        client = TestClient(app)

        response = client.post(
            "/api/operating-brain/workbench-submit",
            data={"input": "上传这张菜单图，自动识别分类并记忆", "scenario": "资料记忆", "role": "运营"},
            files={"files": ("menu.png", b"fake-image-bytes", "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["memory_result"]["status"], "indexed")
        self.assertEqual(body["memory_result"]["image_understanding_count"], 1)
        self.assertEqual(body["image_understandings"][0]["image_type"], "menu")
        self.assertTrue(body["image_understandings"][0]["qa_ready"])
        image_understanding_text = (
            body["image_understandings"][0]["visual_summary"]
            + body["image_understandings"][0]["business_summary"]
            + "、".join(body["image_understandings"][0]["detected_entities"])
        )
        self.assertIn("产品体系", body["image_understandings"][0]["business_summary"])
        self.assertIn("清泡调补养", image_understanding_text)
        self.assertEqual(router.generate_calls[0]["task_type"], "vision_understanding")
        self.assertEqual(self.repo.upserted_image_understandings[0]["image_type"], "menu")
        image_chunks = [chunk for chunk in self.repo.upserted_chunks if chunk["metadata"].get("chunk_type") == "image_understanding"]
        self.assertEqual(len(image_chunks), 1)
        self.assertEqual(image_chunks[0]["domain"], "product")
        self.assertIn("业务摘要", image_chunks[0]["content"])
        self.assertIn("清泡调补养", image_chunks[0]["content"])

    def test_operating_brain_workbench_submit_creates_review_task_when_image_model_unavailable(self):
        response = self.client.post(
            "/api/operating-brain/workbench-submit",
            data={"input": "上传这张菜单图，自动识别分类并记忆", "scenario": "资料记忆", "role": "运营"},
            files={"files": ("menu.png", b"fake-image-bytes", "image/png")},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["memory_result"]["status"], "needs_review")
        self.assertEqual(body["memory_result"]["image_understanding_count"], 0)
        self.assertEqual(body["image_understanding_tasks"][0]["status"], "needs_review")
        self.assertEqual(self.repo.saved_review_task["reason"], "image_understanding_needed")
        self.assertEqual(self.repo.saved_review_task["priority"], "medium")
        self.assertIn("menu.png", self.repo.saved_review_task["question"])
        self.assertIn("多模态理解", body["next_message"])

    def test_api_serves_brain_page_for_same_origin_uploads(self):
        response = self.client.get("/brain.html")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("荷小悦经营大脑", response.text)
        self.assertIn("/api/knowledge/upload", response.text)

    def test_api_serves_startup_stage_product_page(self):
        response = self.client.get("/startup.html")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertIn("HXYOS 首店", response.text)
        self.assertIn("首店今日动作台", response.text)
        self.assertIn("开始录入", response.text)
        self.assertIn("/api/operating-brain/brand-answer-cards", response.text)
        self.assertIn("/api/operating-brain/startup-advance", response.text)

    def test_summary_assets_and_search_use_repository(self):
        summary = self.client.get("/api/knowledge/summary")
        assets = self.client.get("/api/knowledge/assets?limit=1")
        search = self.client.get("/api/knowledge/search?q=泡脚&domain=product&stage=preparation")

        self.assertEqual(summary.status_code, 200)
        self.assertEqual(summary.json()["asset_count"], 2)
        self.assertEqual(assets.status_code, 200)
        self.assertEqual(assets.json()["items"][0]["title"], "泡脚方")
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json()["items"][0]["domain"], "product")
        self.assertEqual(search.json()["items"][0]["stage"], "preparation")

    def test_upload_keeps_files_inside_hxy_inbox(self):
        response = self.client.post(
            "/api/knowledge/upload",
            files={"file": ("泡脚方.md", b"# test", "text/markdown")},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        saved_path = self.root / body["relative_path"]
        self.assertEqual(saved_path.read_bytes(), b"# test")
        self.assertTrue(saved_path.resolve().is_relative_to((self.root / "knowledge" / "raw" / "inbox").resolve()))

    def test_upload_rejects_path_traversal_names(self):
        response = self.client.post(
            "/api/knowledge/upload",
            files={"file": ("../escape.md", b"bad", "text/markdown")},
        )

        self.assertEqual(response.status_code, 400)

    def test_write_endpoints_require_bearer_token_when_configured(self):
        response = self.client.post(
            "/api/knowledge/upload",
            headers={"Authorization": ""},
            files={"file": ("泡脚方.md", b"# test", "text/markdown")},
        )

        self.assertEqual(response.status_code, 401)

    def test_upload_rejects_unsupported_file_extension(self):
        response = self.client.post(
            "/api/knowledge/upload",
            files={"file": ("payload.exe", b"bad", "application/octet-stream")},
        )

        self.assertEqual(response.status_code, 415)

    def test_upload_rejects_files_over_configured_size_limit(self):
        os.environ["HXY_MAX_UPLOAD_BYTES"] = "4"
        module = importlib.import_module("apps.api.hxy_knowledge_api")
        app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/upload",
            files={"file": ("too-large.md", b"12345", "text/markdown")},
        )

        self.assertEqual(response.status_code, 413)
        self.assertFalse((self.root / "knowledge" / "raw" / "inbox" / "too-large.md").exists())

    def test_chat_returns_answer_and_sources_from_repository(self):
        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "泡脚方是什么？", "domain": "product", "stage": "preparation"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["question"], "泡脚方是什么？")
        self.assertIn("泡脚方", body["answer"])
        self.assertEqual(body["sources"][0]["title"], "泡脚方")
        self.assertEqual(self.repo.last_search["query"], "泡脚方是什么？")
        self.assertEqual(self.repo.last_search["domain"], "product")
        self.assertEqual(self.repo.last_search["stage"], "preparation")

    def test_chat_returns_enterprise_answer_contract_and_persists_run(self):
        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦的品牌定位是什么？"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in [
            "answer_id",
            "intent",
            "audience",
            "answer",
            "reasoning",
            "evidence",
            "conflicts",
            "corrections",
            "confidence",
            "next_actions",
            "needs_review",
        ]:
            self.assertIn(key, body)
        self.assertEqual(body["intent"], "brand_positioning")
        self.assertIsInstance(body["reasoning"], list)
        self.assertIsInstance(body["evidence"], list)
        self.assertTrue(body["evidence"])
        self.assertIn(body["confidence"], {"high", "medium", "low"})
        self.assertEqual(body["answer_id"], "answer-test-id")
        self.assertEqual(self.repo.saved_answer["intent"], "brand_positioning")

    def test_chat_does_not_treat_builtin_golden_question_as_approved_authority(self):
        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "清泡调补养怎么讲？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["from_answer_card"])
        self.assertTrue(body["needs_review"])
        self.assertNotEqual(body["answer_status"], "已批准")
        self.assertGreaterEqual(len(self.repo.search_calls), 1)
        self.assertIn("model_route", body)
        self.assertEqual(body["model_route"]["task_type"], "rag_answer")
        self.assertFalse(body["model_route"]["should_call_model"])
        self.assertIn("answer_pipeline", body)
        pipeline = body["answer_pipeline"]
        self.assertEqual(pipeline["policy_decision"]["action"], "needs_review")
        self.assertEqual(pipeline["answer_builder"]["answer_type"], "reference_draft")
        self.assertIn("参考资料", pipeline["evidence_plan"]["sources"])
        self.assertNotIn("policy_decision", body["answer"])
        self.assertNotIn("evidence_plan", body["answer"])

    def test_chat_does_not_match_builtin_authority_card_even_when_intent_is_generic(self):
        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦是什么？", "scenario": "用户端宣传"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["from_answer_card"])
        self.assertTrue(body["needs_review"])
        self.assertNotEqual(body["answer_status"], "已批准")
        self.assertGreaterEqual(len(self.repo.search_calls), 1)

    def test_chat_does_not_use_brand_asset_cards_as_approved_authority(self):
        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "为什么选择社区小店？", "scenario": "创始人内部决策"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["from_answer_card"])
        self.assertTrue(body["needs_review"])
        self.assertNotEqual(body["answer_status"], "已批准")
        self.assertGreaterEqual(len(self.repo.search_calls), 1)

    def test_chat_marks_weak_rag_answer_insufficient_instead_of_hard_answering(self):
        self.repo.search_items = [
            {
                "chunk_id": "hxy-inbox:weak:chunk:0",
                "asset_id": "hxy-inbox:weak",
                "title": "无关资料",
                "source_path": "knowledge/raw/inbox/weak.md",
                "normalized_path": "knowledge/normalized/external/preparation/weak.md",
                "domain": "external",
                "stage": "preparation",
                "content": "这里只是泛泛而谈，没有荷小悦单店模型、招商和回本资料。",
                "score": 1,
            }
        ]

        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "陌生城市加盟回本模型怎么承诺？", "scenario": "招商话术", "limit": 1},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["from_answer_card"])
        self.assertTrue(body["needs_review"])
        self.assertEqual(body["answer_status"], "资料不足")
        self.assertIn("不能可靠回答", body["answer"])
        self.assertIn("请补充", body["answer"])
        self.assertLess(body["quality_score"]["score"], 0.7)
        self.assertTrue(body["quality_score"]["needs_review"])
        self.assertIn("model_route", body)
        self.assertEqual(body["model_route"]["task_type"], "rag_answer")
        self.assertFalse(body["model_route"]["should_call_model"])
        self.assertIn("answer_pipeline", body)
        pipeline = body["answer_pipeline"]
        self.assertEqual(pipeline["policy_decision"]["action"], "needs_review")
        self.assertFalse(pipeline["guardrail_result"]["passed"])
        self.assertIn("create_review_task", pipeline["evolution_actions"])

    def test_chat_treats_reference_material_as_unapproved_draft_even_when_relevant(self):
        self.repo.search_items = [
            {
                "chunk_id": "hxy-inbox:positioning:chunk:0",
                "asset_id": "hxy-inbox:positioning",
                "title": "荷小悦定位讨论稿",
                "source_path": "knowledge/raw/inbox/positioning.md",
                "normalized_path": "knowledge/normalized/brand/preparation/positioning.md",
                "domain": "brand",
                "stage": "preparation",
                "status": "reference",
                "source_type": "reference_material",
                "content": "荷小悦是面向社区高疲劳人群的轻养生服务空间，核心围绕泡脚和轻恢复体验。",
                "score": 90,
            }
        ]

        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦是什么？", "scenario": "品牌定位", "limit": 1},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["from_answer_card"])
        self.assertTrue(body["needs_review"])
        self.assertIn(body["answer_status"], {"待复核", "资料不足"})
        pipeline = body["answer_pipeline"]
        self.assertEqual(pipeline["policy_decision"]["action"], "needs_review")
        self.assertEqual(pipeline["answer_builder"]["answer_type"], "reference_draft")
        self.assertIn("参考资料", pipeline["evidence_plan"]["sources"])
        self.assertIn("create_answer_card_draft", pipeline["evolution_actions"])
        self.assertEqual(body["evidence"][0]["status"], "reference")

    def test_chat_uses_model_only_after_retrieval_and_quality_gate(self):
        module = importlib.import_module("apps.api.hxy_knowledge_api")

        class PassingPolicyRouter(FakeModelRouter):
            def generate(self, task_type, *, messages=None, prompt=None, metadata=None):
                self.generate_calls.append({"task_type": task_type, "messages": messages or [], "prompt": prompt, "metadata": metadata or {}})
                output = (
                    "门店培训版：先问顾客最近状态，再推荐清泡、调泡、补泡或养泡；只讲体验和放松，不承诺治疗。"
                    if task_type == "answer_synthesis"
                    else '{"passed":true,"action":"pass","risk_flags":[],"reason":"候选答案克制且未发现技术噪声。","confidence":0.9}'
                )
                return {
                    "version": "hxy-model-generation.v1",
                    "used_model": True,
                    "reason": "ok",
                    "route": self.route(task_type),
                    "request_shape": {
                        "message_count": len(messages or []),
                        "has_prompt": bool(prompt),
                        "metadata_keys": sorted((metadata or {}).keys()),
                    },
                    "provider_response_id": f"resp_{task_type}",
                    "usage": {},
                    "output": output,
                }

        router = PassingPolicyRouter()
        self.repo.search_items = [
            {
                "chunk_id": "hxy-inbox:p1:chunk:0",
                "asset_id": "hxy-inbox:p1",
                "title": "清泡调补养产品体系",
                "source_path": "knowledge/raw/inbox/product-system.md",
                "normalized_path": "knowledge/normalized/product/preparation/product-system.md",
                "domain": "product",
                "stage": "preparation",
                "content": "产品体系：清泡是基础放松，调泡按近期状态做针对性表达，补泡强调疲劳恢复，养泡适合长期保养。",
                "score": 30,
            },
            {
                "chunk_id": "hxy-inbox:p2:chunk:0",
                "asset_id": "hxy-inbox:p2",
                "title": "门店泡脚方话术",
                "source_path": "knowledge/raw/inbox/store-training.md",
                "normalized_path": "knowledge/normalized/operations/preparation/store-training.md",
                "domain": "operations",
                "stage": "preparation",
                "content": "门店员工推荐泡脚方时，先问顾客睡眠、疲劳、手脚凉、压力，再推荐清泡调泡补泡养泡。",
                "score": 28,
            },
            {
                "chunk_id": "hxy-inbox:p3:chunk:0",
                "asset_id": "hxy-inbox:p3",
                "title": "草本泡脚风险边界",
                "source_path": "knowledge/raw/inbox/risk-boundary.md",
                "normalized_path": "knowledge/normalized/product/preparation/risk-boundary.md",
                "domain": "product",
                "stage": "preparation",
                "content": "草本泡脚对外只能讲体验、放松和状态建议，不能承诺治疗、治愈或绝对效果。",
                "score": 26,
            },
        ]
        app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo, model_router=router)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "泡脚方怎么给门店员工讲？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["from_answer_card"])
        self.assertEqual(body["model_generation"]["used_model"], True)
        self.assertIn("门店培训版", body["answer"])
        self.assertEqual(body["model_route"]["task_type"], "rag_answer")
        self.assertEqual(router.generate_calls[0]["task_type"], "answer_synthesis")
        self.assertEqual(router.generate_calls[1]["task_type"], "policy_review")
        self.assertIn("证据", router.generate_calls[0]["messages"][0]["content"])
        self.assertIn("泡脚方", router.generate_calls[0]["messages"][1]["content"])
        self.assertEqual(router.generate_calls[0]["metadata"]["intent"], body["intent"])
        self.assertEqual(body["policy_review"]["action"], "pass")
        self.assertNotIn("chunk_id", body["answer"])
        self.assertEqual(body["answer_pipeline"]["answer_builder"]["answer_type"], "reference_draft")
        self.assertEqual(body["answer_pipeline"]["policy_decision"]["action"], "needs_review")

    def test_chat_policy_review_can_reject_model_answer_without_relaxing_local_rules(self):
        module = importlib.import_module("apps.api.hxy_knowledge_api")

        class PolicyRouter(FakeModelRouter):
            def generate(self, task_type, *, messages=None, prompt=None, metadata=None):
                self.generate_calls.append({"task_type": task_type, "messages": messages or [], "prompt": prompt, "metadata": metadata or {}})
                output = (
                    "门店培训版：先问顾客最近状态，再推荐清泡、调泡、补泡或养泡。"
                    if task_type == "answer_synthesis"
                    else '{"passed":false,"action":"needs_review","risk_flags":["证据不足"],"reason":"答案没有明确绑定证据中的风险边界。","confidence":0.88}'
                )
                return {
                    "version": "hxy-model-generation.v1",
                    "used_model": True,
                    "reason": "ok",
                    "route": self.route(task_type),
                    "request_shape": {
                        "message_count": len(messages or []),
                        "has_prompt": bool(prompt),
                        "metadata_keys": sorted((metadata or {}).keys()),
                    },
                    "provider_response_id": f"resp_{task_type}",
                    "usage": {},
                    "output": output,
                }

        router = PolicyRouter()
        self.repo.search_items = [
            {
                "chunk_id": "hxy-inbox:p1:chunk:0",
                "asset_id": "hxy-inbox:p1",
                "title": "清泡调补养产品体系",
                "source_path": "knowledge/raw/inbox/product-system.md",
                "normalized_path": "knowledge/normalized/product/preparation/product-system.md",
                "domain": "product",
                "stage": "preparation",
                "content": "清泡是基础放松，调泡按近期状态表达，补泡强调疲劳恢复，养泡适合长期保养。不得承诺治疗。",
                "score": 35,
            },
            {
                "chunk_id": "hxy-inbox:p2:chunk:0",
                "asset_id": "hxy-inbox:p2",
                "title": "泡脚方门店训练",
                "source_path": "knowledge/raw/inbox/training.md",
                "normalized_path": "knowledge/normalized/operations/preparation/training.md",
                "domain": "operations",
                "stage": "preparation",
                "content": "门店员工推荐泡脚方时，先问顾客疲劳、睡眠和手脚凉，再解释调泡看状态、补泡强调恢复感。",
                "score": 32,
            },
            {
                "chunk_id": "hxy-inbox:p3:chunk:0",
                "asset_id": "hxy-inbox:p3",
                "title": "草本泡脚边界",
                "source_path": "knowledge/raw/inbox/risk.md",
                "normalized_path": "knowledge/normalized/product/preparation/risk.md",
                "domain": "product",
                "stage": "preparation",
                "content": "草本泡脚对外只能讲体验、放松和状态建议，不得承诺治疗、治愈或绝对效果。",
                "score": 30,
            }
        ]
        app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo, model_router=router)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "泡脚方遇到顾客说最近很累但不想加项目，员工应该怎么解释调泡和补泡？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual([call["task_type"] for call in router.generate_calls], ["answer_synthesis", "policy_review"])
        self.assertEqual(body["model_generation"]["used_model"], False)
        self.assertEqual(body["model_generation"]["reason"], "policy_review_rejected")
        self.assertTrue(body["needs_review"])
        self.assertEqual(body["policy_review"]["mode"], "ai")
        self.assertIn("证据不足", body["policy_review"]["risk_flags"])

    def test_chat_uses_ai_frontdoor_classification_for_ambiguous_business_questions(self):
        module = importlib.import_module("apps.api.hxy_knowledge_api")

        class DomainHintRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20, domain_hint=None):
                self.last_search = {
                    "query": query,
                    "domain": domain,
                    "stage": stage,
                    "limit": limit,
                    "domain_hint": domain_hint,
                }
                self.search_calls.append(self.last_search)
                if domain_hint == "product_system":
                    return [
                        {
                            "chunk_id": "product-ai-frontdoor:1",
                            "asset_id": "asset-product-ai-frontdoor",
                            "title": "清泡调补养顾客表达",
                            "source_path": "knowledge/raw/inbox/product-script.md",
                            "normalized_path": "knowledge/normalized/product/approved/product-script.md",
                            "domain": "product",
                            "stage": "approved",
                            "content": "清泡调补养对顾客讲时，先问睡眠、疲劳、手脚凉和压力，再按状态说明清泡基础放松、调泡状态调理、补泡恢复感、养泡长期保养。",
                            "score": 90,
                        }
                    ][:limit]
                return [
                    {
                        "chunk_id": "external-ai-frontdoor:1",
                        "asset_id": "asset-external-ai-frontdoor",
                        "title": "泛泛资料",
                        "source_path": "knowledge/raw/inbox/noise.md",
                        "normalized_path": "knowledge/normalized/external/preparation/noise.md",
                        "domain": "external",
                        "stage": "preparation",
                        "content": "这是一段无法支持门店话术的泛泛材料。",
                        "score": 1,
                    }
                ][:limit]

        class FrontdoorRouter(FakeModelRouter):
            def route(self, task_type):
                route = super().route(task_type)
                route["should_call_model"] = task_type == "frontdoor_classification"
                return route

            def generate(self, task_type, *, messages=None, prompt=None, metadata=None):
                self.generate_calls.append(
                    {"task_type": task_type, "messages": messages or [], "prompt": prompt, "metadata": metadata or {}}
                )
                return {
                    "version": "hxy-model-generation.v1",
                    "used_model": True,
                    "reason": "ok",
                    "route": self.route(task_type),
                    "request_shape": {
                        "message_count": len(messages or []),
                        "has_prompt": bool(prompt),
                        "metadata_keys": sorted((metadata or {}).keys()),
                    },
                    "provider_response_id": "resp_frontdoor",
                    "usage": {},
                    "output": """
                    {
                      "intent": "product_system",
                      "audience": "store_staff",
                      "primary_workflow": "ask",
                      "confidence": 0.86,
                      "reason": "用户在门店员工培训场景下询问顾客沟通表达，应该走产品体系话术。"
                    }
                    """,
                }

        repo = DomainHintRepository()
        router = FrontdoorRouter()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo, model_router=router)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "这套对顾客怎么讲才清楚？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["intent"], "product_system")
        self.assertEqual(body["understanding"]["frontdoor_classification"]["mode"], "ai")
        self.assertEqual(body["understanding"]["frontdoor_classification"]["intent"], "product_system")
        self.assertEqual(repo.search_calls[0]["domain_hint"], "product_system")
        self.assertEqual(router.generate_calls[0]["task_type"], "frontdoor_classification")
        self.assertIn("清泡调补养", body["answer"])

    def test_chat_rejects_unsafe_model_output_and_keeps_review_gate(self):
        module = importlib.import_module("apps.api.hxy_knowledge_api")
        router = FakeModelRouter(output="招商可以保证三个月回本，稳赚。")
        self.repo.search_items = [
            {
                "chunk_id": "hxy-inbox:p1:chunk:0",
                "asset_id": "hxy-inbox:p1",
                "title": "清泡调补养产品体系",
                "source_path": "knowledge/raw/inbox/product-system.md",
                "normalized_path": "knowledge/normalized/product/preparation/product-system.md",
                "domain": "product",
                "stage": "preparation",
                "content": "产品体系：清泡是基础放松，调泡按近期状态做针对性表达，补泡强调疲劳恢复，养泡适合长期保养。",
                "score": 30,
            },
            {
                "chunk_id": "hxy-inbox:p2:chunk:0",
                "asset_id": "hxy-inbox:p2",
                "title": "门店泡脚方话术",
                "source_path": "knowledge/raw/inbox/store-training.md",
                "normalized_path": "knowledge/normalized/operations/preparation/store-training.md",
                "domain": "operations",
                "stage": "preparation",
                "content": "门店员工推荐泡脚方时，先问顾客睡眠、疲劳、手脚凉、压力，再推荐清泡调泡补泡养泡。",
                "score": 28,
            },
            {
                "chunk_id": "hxy-inbox:p3:chunk:0",
                "asset_id": "hxy-inbox:p3",
                "title": "草本泡脚风险边界",
                "source_path": "knowledge/raw/inbox/risk-boundary.md",
                "normalized_path": "knowledge/normalized/product/preparation/risk-boundary.md",
                "domain": "product",
                "stage": "preparation",
                "content": "草本泡脚对外只能讲体验、放松和状态建议，不能承诺治疗、治愈或绝对效果。",
                "score": 26,
            },
        ]
        app = module.create_app(root_dir=self.root, repository_factory=lambda: self.repo, model_router=router)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "泡脚方怎么给门店员工讲？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("model_generation", body)
        self.assertEqual(body["model_generation"]["used_model"], False)
        self.assertEqual(body["model_generation"]["reason"], "quality_gate_rejected")
        self.assertNotIn("稳赚", body["answer"])
        self.assertNotIn("保证三个月回本", body["answer"])
        self.assertTrue(body["needs_review"])

    def test_chat_response_includes_hidden_understanding_for_inspector(self):
        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "清泡调补养怎么给门店员工培训？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("understanding", body)
        understanding = body["understanding"]
        self.assertIn("intent", understanding)
        self.assertIn("depth", understanding)
        self.assertIn("applications", understanding)
        self.assertIn("executability_gate", understanding)
        self.assertIn("main_conflict", understanding["depth"]["D5_judgment"])
        self.assertIn("A2_risk_boundary", understanding["applications"])
        self.assertNotIn("D1_perception", body["answer"])
        self.assertNotIn("chunk_id", body["answer"])
        self.assertNotIn("knowledge/raw", body["answer"])

    def test_chat_accepts_scenario_and_returns_operating_brain_fields(self):
        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦的品牌定位是什么？", "scenario": "招商话术"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["scenario"], "招商话术")
        self.assertIn("usage", body)
        self.assertIn("applicable_scenarios", body)
        self.assertIn("answer_status", body)
        self.assertIn("招商", body["usage"])
        self.assertIn("招商话术", body["applicable_scenarios"])
        self.assertIn(body["answer_status"], {"AI 草稿", "待复核", "已批准"})
        self.assertEqual(self.repo.saved_answer["scenario"], "招商话术")

    def test_chat_rewrites_product_answer_for_role_specific_scenarios(self):
        class ProductScenarioRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "product:scenario",
                        "asset_id": "product",
                        "title": "清泡调补养产品体系",
                        "source_path": "knowledge/raw/inbox/product.md",
                        "normalized_path": "",
                        "domain": "product",
                        "stage": "preparation",
                        "content": "清泡调补养产品体系：以草本泡脚方为基础，结合推拿服务和复购产品，形成一人一方的功效泡脚体验。",
                        "score": 60,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = ProductScenarioRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        training_response = client.post(
            "/api/knowledge/chat",
            json={"question": "清泡调补养怎么给门店员工培训？", "scenario": "门店员工培训"},
        )
        franchise_response = client.post(
            "/api/knowledge/chat",
            json={"question": "清泡调补养怎么给加盟商讲？", "scenario": "招商话术"},
        )

        self.assertEqual(training_response.status_code, 200)
        self.assertEqual(franchise_response.status_code, 200)
        training = training_response.json()
        franchise = franchise_response.json()
        training_answer = training["result_card"]["usable_answer"]
        franchise_answer = franchise["result_card"]["usable_answer"]

        self.assertEqual(training["answer"], training_answer)
        self.assertEqual(franchise["answer"], franchise_answer)
        self.assertIn("员工话术：", training_answer)
        self.assertIn("服务动作：", training_answer)
        self.assertIn("禁用表达：", training_answer)
        self.assertIn("招商话术：", franchise_answer)
        self.assertIn("沟通重点：", franchise_answer)
        self.assertIn("风险边界：", franchise_answer)
        self.assertIn("清泡调补养", training_answer)
        self.assertIn("清泡调补养", franchise_answer)
        self.assertNotEqual(training_answer, franchise_answer)

    def test_chat_retries_when_initial_results_are_wrong_domain_noise(self):
        class NoisyFirstRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                if query == "清泡调补养":
                    return [
                        {
                            "chunk_id": "product:clean",
                            "asset_id": "product",
                            "title": "清泡调补养产品体系",
                            "source_path": "knowledge/raw/inbox/product.md",
                            "normalized_path": "",
                            "domain": "product",
                            "stage": "preparation",
                            "content": "清泡调补养产品体系：以草本泡脚方为基础，结合推拿服务和复购产品，形成一人一方的功效泡脚体验。",
                            "score": 70,
                        }
                    ]
                return [
                    {
                        "chunk_id": "external:file-listing",
                        "asset_id": "external",
                        "title": "Desktop",
                        "source_path": "knowledge/raw/inbox/Desktop.zip",
                        "normalized_path": "",
                        "domain": "external",
                        "stage": "preparation",
                        "content": "荷小悦资料/清泡调补养.docx (19604 bytes) - file: 荷小悦资料/系统方案.docx",
                        "score": 90,
                    },
                    {
                        "chunk_id": "finance:noise",
                        "asset_id": "finance",
                        "title": "分账案例",
                        "source_path": "knowledge/raw/inbox/payment.pptx",
                        "normalized_path": "",
                        "domain": "finance",
                        "stage": "preparation",
                        "content": "互联网金融50强。全国抗击新冠肺炎疫情先进企业。门店资金结算。",
                        "score": 80,
                    },
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = NoisyFirstRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "清泡调补养怎么给门店员工培训？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["query"], "清泡调补养")
        self.assertEqual(body["evidence"][0]["domain"], "product")
        self.assertIn("员工话术：", body["answer"])
        self.assertIn("服务动作：", body["answer"])
        self.assertNotIn("互联网金融50强", body["answer"])
        self.assertGreaterEqual(len(repo.search_calls), 2)

    def test_chat_expands_product_system_terms_when_exact_term_has_no_hits(self):
        class ProductSynonymRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                if query == "草本泡脚":
                    return [
                        {
                            "chunk_id": "product:synonym",
                            "asset_id": "product",
                            "title": "荷小悦草本泡脚产品体系",
                            "source_path": "knowledge/raw/inbox/product.md",
                            "normalized_path": "",
                            "domain": "product",
                            "stage": "preparation",
                            "content": "产品体系：草本泡脚、泡脚方、一人一方、推拿服务和离店复购产品组成清泡调补养体验。",
                            "score": 80,
                        }
                    ]
                if query == "清泡调补养":
                    return []
                return [
                    {
                        "chunk_id": "external:file-listing",
                        "asset_id": "external",
                        "title": "Desktop",
                        "source_path": "knowledge/raw/inbox/Desktop.zip",
                        "normalized_path": "",
                        "domain": "external",
                        "stage": "preparation",
                        "content": "荷小悦资料/清泡调补养.docx (19604 bytes) - file: 荷小悦资料/系统方案.docx",
                        "score": 90,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = ProductSynonymRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "清泡调补养怎么给门店员工培训？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["query"], "草本泡脚")
        self.assertEqual(body["evidence"][0]["domain"], "product")
        self.assertIn("员工话术：", body["answer"])
        self.assertIn("清泡调补养体验", body["answer"])

    def test_product_system_answer_skips_slide_and_mascot_noise(self):
        class NoisyProductRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "product:noisy",
                        "asset_id": "product",
                        "title": "荷小悦产品讨论长图",
                        "source_path": "knowledge/raw/inbox/product.png",
                        "normalized_path": "",
                        "domain": "product",
                        "stage": "preparation",
                        "content": (
                            "金木水火土（5种泡脚方式） 逸马 模式创新：到店也到家 产品到家+服务到家。"
                            "吉祥物 学名：荷小悦 昵称：泡泡 带薪泡脚，摸鱼养生。"
                            "产品体系：清泡调补养，以草本泡脚方为基础，结合一人一方、推拿服务和离店复购产品。"
                            "核心卖点：技师根据顾客状态配方，形成完整体验。"
                        ),
                        "score": 90,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = NoisyProductRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "清泡调补养怎么给门店员工培训？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("员工话术：", answer)
        self.assertIn("清泡调补养", answer)
        self.assertIn("一人一方", answer)
        self.assertNotIn("逸马", answer)
        self.assertNotIn("吉祥物", answer)
        self.assertNotIn("摸鱼养生", answer)

    def test_product_system_answer_uses_business_anchor_not_long_slide_prefix(self):
        class LongNoisyProductRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                noisy_prefix = (
                    "金木水火土（5种泡脚方式） 逸马 模式创新：到店也到家 产品到家+服务到家。"
                    "吉祥物 学名：荷小悦 昵称：泡泡 带薪泡脚，摸鱼养生 躺平养生，拿捏松弛。"
                )
                return [
                    {
                        "chunk_id": "product:long-noisy",
                        "asset_id": "product",
                        "title": "荷小悦产品长图",
                        "source_path": "knowledge/raw/inbox/product-long.png",
                        "normalized_path": "",
                        "domain": "product",
                        "stage": "preparation",
                        "content": (
                            noisy_prefix * 4
                            + "荷小悦提供什么产品？可以喝的泡脚汤。A套餐模式+B火锅模式。"
                            "A: 草本泡脚包+套餐按摩。B: 1人1方+任选按摩。"
                            "功效泡脚、对症推拿、好产品做基础。"
                        ),
                        "score": 90,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = LongNoisyProductRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "清泡调补养怎么给门店员工培训？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("员工话术：", answer)
        self.assertIn("草本泡脚包", answer)
        self.assertIn("1人1方", answer)
        self.assertNotIn("逸马", answer)
        self.assertNotIn("吉祥物", answer)
        self.assertNotIn("摸鱼养生", answer)

    def test_product_system_answer_rejects_polluted_only_product_claim(self):
        class PollutedOnlyProductRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "product:polluted-only",
                        "asset_id": "product",
                        "title": "荷小悦产品 OCR 片段",
                        "source_path": "knowledge/raw/inbox/product-ocr.png",
                        "normalized_path": "",
                        "domain": "product",
                        "stage": "pilot",
                        "content": (
                            "清泡调补养：金木水火土（5种泡脚方式） 逸马 模式创新：到店也到家 "
                            "产品到家+服务到家 家居产品 到家服务 逸马 吉祥物 学名：荷小悦 "
                            "昵称：泡泡 荷小悦 带薪泡脚，摸鱼养生 躺平养生，拿捏松弛。"
                        ),
                        "score": 90,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = PollutedOnlyProductRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "清泡调补养怎么给门店员工培训？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        answer = body["answer"]
        self.assertIn("没有可直接用于回答", answer)
        self.assertTrue(body["needs_review"])
        self.assertNotIn("逸马", answer)
        self.assertNotIn("吉祥物", answer)
        self.assertNotIn("摸鱼养生", answer)

    def test_product_system_answer_removes_ocr_table_fragments(self):
        class OcrTableProductRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "product:ocr-table",
                        "asset_id": "product",
                        "title": "荷小悦产品菜单 OCR",
                        "source_path": "knowledge/raw/inbox/product-menu.png",
                        "normalized_path": "",
                        "domain": "product",
                        "stage": "pilot",
                        "content": (
                            "荷小悦提供什么产品？ 可以喝的泡脚汤 A套餐模式+B火锅模式 "
                            "A:草本泡脚包+套餐按摩 模式 项目 时间 价格 泡脚+肩颈按摩 "
                            "09 69 69元-50分钟：草本泡脚+A按摩 草木 配方 "
                            "泡脚+肩颈按摩+腿部按摩 60 79 B:1人1方+任选按摩。"
                        ),
                        "score": 90,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = OcrTableProductRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "清泡调补养怎么给门店员工培训？", "scenario": "门店员工培训"},
        )

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("草本泡脚包", answer)
        self.assertIn("套餐按摩", answer)
        self.assertIn("1人1方", answer)
        for noisy in ["模式 项目 时间 价格", "09 69", "60 79", "草木 配方"]:
            self.assertNotIn(noisy, answer)

    def test_chat_returns_stable_operating_result_card(self):
        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦的品牌定位是什么？", "scenario": "用户端宣传"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("result_card", body)
        card = body["result_card"]
        for key in [
            "result_type",
            "usable_answer",
            "business_result",
            "risk_boundary",
            "quality_gates",
            "review_owner",
            "stability_level",
        ]:
            self.assertIn(key, card)
        self.assertIn("用户端宣传", card["business_result"])
        self.assertIn(card["stability_level"], {"stable", "review_required", "insufficient"})
        self.assertIsInstance(card["quality_gates"], list)
        self.assertGreaterEqual(len(card["quality_gates"]), 5)
        for gate in card["quality_gates"]:
            self.assertIn("name", gate)
            self.assertIn("passed", gate)
            self.assertIn("detail", gate)

    def test_approved_answer_card_response_includes_result_card(self):
        self.client.post(
            "/api/knowledge/answer-cards",
            json={
                "question_pattern": "荷小悦的品牌定位是什么",
                "intent": "brand_positioning",
                "audience": "founder",
                "answer": "权威答案：荷小悦是社区功效泡脚养生品牌。",
                "status": "approved",
            },
        )

        response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦的品牌定位是什么？", "scenario": "招商话术"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["from_answer_card"])
        self.assertIn("result_card", body)
        self.assertEqual(body["result_card"]["stability_level"], "stable")
        self.assertIn("招商话术", body["result_card"]["business_result"])

    def test_compliance_preflight_rejects_risky_approved_answer_card(self):
        response = self.client.post(
            "/api/knowledge/answer-cards",
            json={
                "question_pattern": "泡脚能治什么",
                "intent": "risk_boundary",
                "audience": "customer",
                "answer": "荷小悦泡脚可以治疗失眠，一次见效。",
                "status": "approved",
            },
        )

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("compliance_preflight", body["detail"])
        self.assertEqual(self.repo.saved_answer_card, None)

    def test_compliance_preflight_allows_risky_draft_answer_card_with_warning(self):
        response = self.client.post(
            "/api/knowledge/answer-cards",
            json={
                "question_pattern": "泡脚能治什么",
                "intent": "risk_boundary",
                "audience": "customer",
                "answer": "草稿待改：泡脚可以治疗失眠。",
                "status": "draft",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["status"], "created")
        self.assertIn("compliance_preflight", body)
        self.assertEqual(body["compliance_preflight"]["workflow_status"], "blocked")
        self.assertFalse(body["compliance_preflight"]["can_publish"])
        self.assertEqual(self.repo.saved_answer_card["status"], "draft")

    def test_compliance_preflight_menu_draft_is_dry_run(self):
        response = self.client.post(
            "/api/operating-brain/menu-draft/preflight",
            json={
                "text": "艾灸调理体质，改善慢病。",
                "channel": "项目菜单",
                "audience": "customer",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["version"], "hxy-menu-draft-compliance-preflight.v1")
        self.assertEqual(body["compliance_preflight"]["workflow_type"], "project_menu")
        self.assertEqual(body["compliance_preflight"]["workflow_status"], "blocked")
        self.assertFalse(body["write_to_database"])
        self.assertFalse(body["can_publish"])

    def test_store_model_question_classifies_as_store_model_before_operations(self):
        class StoreModelRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "operations:1",
                        "asset_id": "operations",
                        "title": "门店服务 SOP",
                        "source_path": "knowledge/raw/inbox/sop.md",
                        "normalized_path": "",
                        "domain": "operations",
                        "stage": "preparation",
                        "content": "门店服务流程包括接待、问询、泡脚、推拿和复购提醒。",
                        "score": 80,
                    },
                    {
                        "chunk_id": "store-model:1",
                        "asset_id": "store-model",
                        "title": "荷小悦门店模型",
                        "source_path": "knowledge/raw/inbox/store-model.md",
                        "normalized_path": "",
                        "domain": "store_model",
                        "stage": "preparation",
                        "content": "单店模型关键参数：社区店、100 平左右、围绕高频草本泡脚和推拿服务形成复购。",
                        "score": 30,
                    },
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = StoreModelRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦门店模型的关键参数是什么？", "scenario": "用户端宣传"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["intent"], "store_model")
        self.assertEqual(body["evidence"][0]["domain"], "store_model")
        self.assertIn("单店模型关键参数", body["answer"])
        self.assertNotIn("运营答案", body["answer"])

    def test_user_facing_answer_does_not_expose_file_metadata(self):
        class MetadataOnlyRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "store-model:file-listing",
                        "asset_id": "store-model",
                        "title": "荷小悦门店模型.docx",
                        "source_path": "knowledge/raw/inbox/荷小悦门店模型.docx",
                        "normalized_path": "knowledge/normalized/store_model/preparation/荷小悦门店模型.md",
                        "domain": "store_model",
                        "stage": "preparation",
                        "content": (
                            "荷小悦门店模型.docx (19604 bytes) "
                            "file: knowledge/raw/inbox/荷小悦门店模型.docx "
                            "source_path: knowledge/raw/inbox/荷小悦门店模型.docx "
                            "chunk_id: store-model:file-listing"
                        ),
                        "score": 90,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = MetadataOnlyRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦门店模型的关键参数是什么？", "scenario": "用户端宣传"},
        )

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("当前知识库", answer)
        for forbidden in [".docx", "bytes", "file:", "source_path", "chunk_id", "knowledge/raw", "knowledge/normalized"]:
            self.assertNotIn(forbidden, answer)

    def test_store_model_answer_rejects_unrelated_cross_domain_claims(self):
        class UnrelatedRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "finance:1",
                        "asset_id": "finance",
                        "title": "分账联合收单案例",
                        "source_path": "knowledge/raw/inbox/payment.pdf",
                        "normalized_path": "",
                        "domain": "finance",
                        "stage": "preparation",
                        "content": "互联网金融50强。全国抗击新冠肺炎疫情先进企业。门店可以使用分账能力完成资金结算。",
                        "score": 10,
                    },
                    {
                        "chunk_id": "external:file-listing",
                        "asset_id": "external",
                        "title": "Desktop",
                        "source_path": "knowledge/raw/inbox/Desktop.txt",
                        "normalized_path": "",
                        "domain": "external",
                        "stage": "preparation",
                        "content": "荷小悦 小店模型.pdf (5759432 bytes) - file: 荷小悦资料/荷小悦 小店模型.pdf",
                        "score": 10,
                    },
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = UnrelatedRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦门店模型的关键参数是什么？", "scenario": "用户端宣传"},
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["intent"], "store_model")
        self.assertIn("当前知识库", body["answer"])
        self.assertNotIn("互联网金融50强", body["answer"])
        self.assertNotIn("全国抗击新冠肺炎疫情先进企业", body["answer"])
        self.assertNotIn("分账", body["answer"])

    def test_store_model_answer_extracts_key_parameters_from_model_document(self):
        class RichStoreModelRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "store-model:rich",
                        "asset_id": "store-model",
                        "title": "荷小悦门店模型具象化构思",
                        "source_path": "knowledge/raw/inbox/store-model.md",
                        "normalized_path": "",
                        "domain": "store_model",
                        "stage": "preparation",
                        "content": (
                            "荷小悦门店模型具象化构思。荷小悦，定位：一家健康科技公司。"
                            "两个核心：泡脚+按摩。​ "
                            "一个核心人群：悦己型年轻养生客群 荷小悦到底在解决什么问题？"
                            "不是它想做什么，而是客户为什么必须来。"
                            "一个社区里的人，身体累了，情绪也闷着，走出家门5分钟能到达的地方里，他需要恢复元气。"
                            "产品结构：引流品泡脚、修脚；主力品足疗、推拿；利润品SPA、痛症调理、套盒、储值卡。"
                        ),
                        "score": 60,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = RichStoreModelRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦门店模型的关键参数是什么？", "scenario": "用户端宣传"},
        )

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("泡脚+按摩", answer)
        self.assertIn("悦己型年轻养生客群", answer)
        self.assertIn("5分钟", answer)
        self.assertIn("恢复元气", answer)
        self.assertIn("核心人群：悦己型年轻养生客群", answer)
        self.assertNotIn("试点参数", answer)
        self.assertNotIn("规模化参数", answer)
        self.assertNotIn("一家健康科技公司", answer)
        self.assertNotIn("具象化构思", answer)
        self.assertNotIn("\u200b", answer)
        self.assertNotIn("到底在解决什么问题", answer)
        self.assertNotIn("需要什么", answer)

    def test_chat_retries_with_keywords_when_full_question_has_no_hits(self):
        class KeywordFallbackRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.last_search = {"query": query, "domain": domain, "stage": stage, "limit": limit}
                self.search_calls.append(self.last_search)
                if query in {"泡脚方是什么？", "泡脚方是什么"}:
                    return []
                return super().search(query, domain=domain, stage=stage, limit=limit)

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = KeywordFallbackRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post("/api/knowledge/chat", json={"question": "泡脚方是什么？"})

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["sources"])
        self.assertGreaterEqual(len(repo.search_calls), 2)
        self.assertIn("泡脚", repo.search_calls[-1]["query"])

    def test_chat_prioritizes_image_understanding_for_image_questions(self):
        class ImageQuestionRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.last_search = {"query": query, "domain": domain, "stage": stage, "limit": limit}
                self.search_calls.append(self.last_search)
                if query in {"荷小悦草本泡脚图片表达了什么卖点？", "泡脚"}:
                    return []
                if "图片类型" in query and "业务摘要" in query:
                    return [
                        {
                            "chunk_id": "image:understanding:1",
                            "asset_id": "image",
                            "title": "草本泡脚图片",
                            "source_path": "knowledge/raw/inbox/image.jpg",
                            "normalized_path": "",
                            "domain": "product",
                            "stage": "preparation",
                            "content": "图片类型：menu。视觉摘要：荷小悦草本泡脚产品图。业务摘要：强调今日现煮、草本真材实料、功效泡脚和可复购服务。",
                            "score": 80,
                        }
                    ]
                return []

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = ImageQuestionRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post("/api/knowledge/chat", json={"question": "荷小悦草本泡脚图片表达了什么卖点？"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["evidence"][0]["chunk_id"], "image:understanding:1")
        self.assertIn("图片类型", body["query"])
        self.assertIn("草本真材实料", body["answer"])
        self.assertNotIn("图片类型：menu", body["answer"])

    def test_chat_uses_business_summary_when_image_understanding_has_long_ocr(self):
        class LongImageUnderstandingRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.last_search = {"query": query, "domain": domain, "stage": stage, "limit": limit}
                self.search_calls.append(self.last_search)
                if "图片类型" not in query:
                    return []
                return [
                    {
                        "chunk_id": "image:understanding:long",
                        "asset_id": "image",
                        "title": "长图菜单",
                        "source_path": "knowledge/raw/inbox/long-menu.png",
                        "normalized_path": "",
                        "domain": "product",
                        "stage": "preparation",
                        "content": (
                            "图片类型：menu\n"
                            "视觉摘要：长图菜单是一张产品/菜单类图片，核心可见信息包括 荷小悦, 草本泡脚。"
                            "OCR 摘要：" + ("荷小悦 泡脚养生 高质平价 " * 30) + "\n"
                            "业务摘要：这张图片应作为产品卖点资料使用，重点表达今日现煮、草本真材实料、功效泡脚和复购服务。\n"
                            "识别实体：荷小悦、草本泡脚"
                        ),
                        "score": 80,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = LongImageUnderstandingRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post("/api/knowledge/chat", json={"question": "荷小悦草本泡脚图片表达了什么卖点？"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("今日现煮", body["answer"])
        self.assertIn("业务摘要", body["evidence"][0]["excerpt"])

    def test_chat_rejects_blank_question(self):
        response = self.client.post("/api/knowledge/chat", json={"question": "  "})

        self.assertEqual(response.status_code, 400)

    def test_feedback_persists_answer_quality_signal(self):
        response = self.client.post(
            "/api/knowledge/feedback",
            json={
                "answer_id": "answer-test-id",
                "question": "荷小悦的品牌定位是什么？",
                "rating": "incorrect",
                "note": "答案没有给结论",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["feedback_id"], "feedback-test-id")
        self.assertEqual(body["status"], "recorded")
        self.assertEqual(self.repo.saved_feedback["rating"], "incorrect")

    def test_negative_feedback_creates_review_task(self):
        response = self.client.post(
            "/api/knowledge/feedback",
            json={
                "answer_id": "answer-test-id",
                "question": "荷小悦的品牌定位是什么？",
                "rating": "needs_work",
                "note": "需要权威版本",
            },
        )

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["review_task_id"], "review-task-test-id")
        self.assertEqual(self.repo.saved_review_task["reason"], "needs_work")
        self.assertEqual(self.repo.saved_review_task["priority"], "medium")

    def test_negative_feedback_creates_structured_correction_package(self):
        response = self.client.post(
            "/api/knowledge/feedback",
            json={
                "answer_id": "answer-test-id",
                "question": "荷小悦的核爆点定位是什么？",
                "rating": "incorrect",
                "note": "答案没有区分品牌定位和招商话术",
            },
        )

        self.assertEqual(response.status_code, 200)
        package = self.repo.saved_review_task["correction_package"]
        self.assertEqual(package["failure_type"], "incorrect_answer")
        self.assertEqual(package["target"], "修正答案并沉淀权威答案卡")
        self.assertIn("核爆点定位", package["normalized_question"])
        self.assertIn("核爆点定位", package["answer_card_draft"]["question_pattern"])
        self.assertEqual(package["answer_card_draft"]["status"], "draft")
        self.assertIn("区分品牌定位和招商话术", package["review_notes"][0])
        self.assertIn("correction_package", response.json())

    def test_negative_feedback_creates_actionable_reliability_correction_loop(self):
        response = self.client.post(
            "/api/knowledge/feedback",
            json={
                "answer_id": "answer-test-id",
                "question": "招商怎么讲单店模型？",
                "rating": "incorrect",
                "note": "答案承诺了一定回本，缺少风险边界和真实门店数据。",
            },
        )

        self.assertEqual(response.status_code, 200)
        package = response.json()["correction_package"]
        self.assertEqual(package["error_type"], "overclaim_or_wrong_conclusion")
        self.assertIn("真实门店数据", package["missing_information"])
        self.assertEqual(package["recommended_reviewer"], "招商负责人")
        self.assertIn("替代旧答案", package["replacement_action"])
        draft = package["answer_card_draft"]
        self.assertEqual(draft["status"], "draft")
        self.assertEqual(draft["source_answer_id"], "answer-test-id")
        self.assertIn("不能承诺稳赚", " ".join(draft["corrections"]))
        self.assertIn("复核通过后替代旧答案", " ".join(package["recommended_actions"]))

    def test_review_tasks_return_correction_package_payload(self):
        self.client.post(
            "/api/knowledge/feedback",
            json={
                "answer_id": "answer-test-id",
                "question": "泡脚方有哪些？",
                "rating": "needs_work",
                "note": "缺少适用人群",
            },
        )

        response = self.client.get("/api/knowledge/review-tasks?status=open&limit=20")

        self.assertEqual(response.status_code, 200)
        task = response.json()["items"][0]
        self.assertIn("correction_package", task["payload_json"])
        self.assertIn("补充缺失信息", task["payload_json"]["correction_package"]["target"])

    def test_review_tasks_deduplicate_same_question(self):
        for note in ["第一次反馈", "第二次反馈"]:
            self.client.post(
                "/api/knowledge/feedback",
                json={
                    "answer_id": "answer-test-id",
                    "question": "荷小悦的核爆点定位是什么？",
                    "rating": "incorrect",
                    "note": note,
                },
            )

        response = self.client.get("/api/knowledge/review-tasks?status=open&limit=20")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["count"], 1)
        self.assertEqual(len(body["items"]), 1)
        task = body["items"][0]
        self.assertEqual(
            task["payload_json"]["correction_package"]["normalized_question"],
            "荷小悦的核爆点定位是什么",
        )

    def test_resolve_review_task_marks_feedback_loop_handled(self):
        response = self.client.post("/api/knowledge/review-tasks/review-task-test-id/resolve")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "resolved")
        self.assertEqual(self.repo.resolved_review_task["task_id"], "review-task-test-id")

    def test_create_answer_card_and_chat_uses_approved_card(self):
        create_response = self.client.post(
            "/api/knowledge/answer-cards",
            json={
                "question_pattern": "荷小悦的品牌定位是什么",
                "intent": "brand_positioning",
                "audience": "founder",
                "answer": "权威答案：荷小悦是社区功效泡脚养生品牌。",
                "reasoning": ["已由创始人确认"],
                "evidence": [{"title": "品牌战略汇总", "source_path": "knowledge/raw/inbox/brand.docx"}],
                "status": "approved",
            },
        )
        chat_response = self.client.post(
            "/api/knowledge/chat",
            json={"question": "荷小悦的品牌定位是什么？"},
        )

        self.assertEqual(create_response.status_code, 200)
        self.assertEqual(create_response.json()["card_id"], "answer-card-test-id")
        self.assertEqual(chat_response.status_code, 200)
        body = chat_response.json()
        self.assertTrue(body["from_answer_card"])
        self.assertEqual(body["answer"], "权威答案：荷小悦是社区功效泡脚养生品牌。")

    def test_brand_positioning_prioritizes_owned_brand_evidence(self):
        class MixedDomainRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "competitor:1",
                        "asset_id": "competitor",
                        "title": "竞品经营分析",
                        "source_path": "knowledge/raw/inbox/competitor.pdf",
                        "normalized_path": "",
                        "domain": "competitor",
                        "stage": "preparation",
                        "content": "投资回报分析 品牌定位 市场数据",
                        "score": 80,
                    },
                    {
                        "chunk_id": "brand:1",
                        "asset_id": "brand",
                        "title": "荷小悦品牌战略汇总",
                        "source_path": "knowledge/raw/inbox/brand.docx",
                        "normalized_path": "",
                        "domain": "brand",
                        "stage": "preparation",
                        "content": "荷小悦品牌定位：泡脚养生品类开创者，高质平价，功效泡脚，对症推拿。",
                        "score": 20,
                    },
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = MixedDomainRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post("/api/knowledge/chat", json={"question": "荷小悦的品牌定位是什么？"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["intent"], "brand_positioning")
        self.assertEqual(body["evidence"][0]["domain"], "brand")
        self.assertIn("泡脚养生品类开创者", body["answer"])
        self.assertNotIn("品牌战略", body["answer"])
        self.assertNotIn("证据锚点", body["answer"])
        self.assertNotIn("证据来源", body["answer"])

    def test_brand_positioning_answer_is_conclusion_first_not_source_wrapper(self):
        class RichBrandRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "brand:1",
                        "asset_id": "brand",
                        "title": "荷小悦品牌战略汇总",
                        "source_path": "knowledge/raw/inbox/brand.md",
                        "normalized_path": "",
                        "domain": "brand",
                        "stage": "preparation",
                        "content": "荷小悦品牌定位：社区功效泡脚养生品牌。主张高质平价、功效泡脚、一人一方、对症推拿。",
                        "score": 48,
                    },
                    {
                        "chunk_id": "product:1",
                        "asset_id": "product",
                        "title": "清泡调补养产品体系",
                        "source_path": "knowledge/raw/inbox/product.md",
                        "normalized_path": "",
                        "domain": "product",
                        "stage": "preparation",
                        "content": "清泡调补养是荷小悦的产品体系，围绕泡脚方、草本调理、推拿服务形成复购。",
                        "score": 30,
                    },
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = RichBrandRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post("/api/knowledge/chat", json={"question": "荷小悦的品牌定位是什么？"})

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertLess(len(answer), 180)
        self.assertIn("结论：", answer)
        self.assertIn("社区功效泡脚养生品牌", answer)
        self.assertNotIn("当前判断应以", answer)
        self.assertNotIn("证据锚点", answer)
        self.assertNotIn("完整依据", answer)

    def test_brand_positioning_extracts_core_positioning_from_noisy_brand_excerpt(self):
        class NoisyBrandRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "brand:1",
                        "asset_id": "brand",
                        "title": "荷小悦品牌商业方案",
                        "source_path": "knowledge/raw/inbox/brand.md",
                        "normalized_path": "",
                        "domain": "brand",
                        "stage": "preparation",
                        "content": (
                            "荷小悦 - 足疗界的精品咖啡 荷小悦 足疗界的“精品咖啡” "
                            "100㎡ 社区/写字楼“养生驿站” 核心定位 "
                            "荷小悦不是在做“小号足疗店”，而是在做 “健康耗材的线下体验中心”。"
                            "按摩只是获客入口，高坪效的服务+离店产品转化才是真正的赢利点。"
                        ),
                        "score": 60,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = NoisyBrandRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post("/api/knowledge/chat", json={"question": "荷小悦的核爆点定位是什么？"})

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("健康耗材的线下体验中心", answer)
        self.assertNotIn("足疗界的精品咖啡 荷小悦 足疗界", answer)
        self.assertLess(len(answer), 180)

    def test_brand_positioning_skips_title_and_outline_noise(self):
        class OutlineBrandRepository(FakeRepository):
            def search(self, query, domain=None, stage=None, limit=20):
                self.search_calls.append({"query": query, "domain": domain, "stage": stage, "limit": limit})
                return [
                    {
                        "chunk_id": "brand:outline",
                        "asset_id": "brand",
                        "title": "荷小悦_品牌战略汇总-claude",
                        "source_path": "knowledge/raw/inbox/brand.pdf",
                        "normalized_path": "",
                        "domain": "brand",
                        "stage": "preparation",
                        "content": (
                            "荷小悦 · 品牌战略汇总 新中式 · 草本疗愈 · 社区第三空间 "
                            "战略蓝图 · 定位设计 · 商业模型 · 选址框架 一、品牌核心哲学 — 第一性原理 "
                            "第一性原理：解决社区居民「身体疲劳」的最后一公里问题。"
                            "荷小悦要做的事，只有一件：让人离开后感觉明显不一样。"
                        ),
                        "score": 60,
                    }
                ]

        module = importlib.import_module("apps.api.hxy_knowledge_api")
        repo = OutlineBrandRepository()
        app = module.create_app(root_dir=self.root, repository_factory=lambda: repo)
        client = TestClient(app)

        response = client.post("/api/knowledge/chat", json={"question": "荷小悦的品牌定位是什么？"})

        self.assertEqual(response.status_code, 200)
        answer = response.json()["answer"]
        self.assertIn("身体疲劳", answer)
        self.assertIn("最后一公里问题", answer)
        self.assertNotIn("品牌战略汇总", answer)
        self.assertNotIn("战略蓝图", answer)
        self.assertNotIn("身体疲劳」的...", answer)
        self.assertLess(len(answer), 180)

    def test_import_requires_database_url_when_no_repository_factory(self):
        module = importlib.import_module("apps.api.hxy_knowledge_api")
        os.environ.pop("HXY_DATABASE_URL", None)
        app = module.create_app(root_dir=self.root)
        client = TestClient(app)

        response = client.post("/api/knowledge/import")

        self.assertEqual(response.status_code, 503)


if __name__ == "__main__":
    unittest.main()
