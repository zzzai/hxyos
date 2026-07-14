import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def write_risk_material_fixtures(root: Path) -> None:
    risk_dir = root / "knowledge" / "raw" / "inbox" / "荷小悦资料" / "09_知识库与参考资料" / "09_风险与合规"
    risk_dir.mkdir(parents=True)
    (risk_dir / "荷小悦禁用表达库.md").write_text(
        """# 风险词库

### 4.1 疾病与症状承诺类

```text
治疗脚气
改善睡眠
```

## 6. 常见错误与替换

|不要这样说|建议这样说|
|---|---|
|治疗颈椎病|久坐肩颈紧，按一按松一点|
""",
        encoding="utf-8",
    )
    (risk_dir / "荷小悦员工功效问题标准话术.md").write_text(
        """# 员工话术

## 2. 员工绝对不能说

```text
你这是湿气重
```
""",
        encoding="utf-8",
    )
    (risk_dir / "荷小悦项目红线卡.md").write_text(
        """# 项目红线

        |不能怎么说|调理体质、改善慢病|
""",
        encoding="utf-8",
    )


def load_module(name: str, relative_path: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HxyKnowledgeServiceTest(unittest.TestCase):
    def test_brand_asset_center_defines_pre_open_brand_first_scope(self):
        brand_assets = load_module("hxy_brand_assets", "apps/api/hxy_knowledge/brand_assets.py")

        result = brand_assets.build_brand_asset_center()

        self.assertEqual(result["version"], "hxy-brand-assets.v1")
        self.assertEqual(result["stage"], "pre_open_brand_first")
        self.assertIn("客户消费数据开店后再接入", " ".join(result["excluded_now"]))
        self.assertEqual(
            {module["key"] for module in result["modules"]},
            {
                "brand_strategy",
                "product_service",
                "store_model",
                "operations_sop",
                "customer_insight",
                "technician_training",
                "competitor_intelligence",
                "franchise_financing",
            },
        )
        module_text = json.dumps(result["modules"], ensure_ascii=False)
        self.assertIn("品牌定位", module_text)
        self.assertIn("清泡调补养", module_text)
        self.assertIn("招商融资", module_text)
        self.assertNotIn("客户消费记录", module_text)

    def test_brand_asset_center_builds_golden_questions_and_deliverables(self):
        brand_assets = load_module("hxy_brand_assets_questions", "apps/api/hxy_knowledge/brand_assets.py")

        result = brand_assets.build_brand_asset_center()

        self.assertGreaterEqual(len(result["golden_questions"]), 30)
        question_text = " ".join(item["question"] for item in result["golden_questions"])
        for expected in [
            "荷小悦是什么？",
            "核爆点定位是什么？",
            "为什么选择社区小店？",
            "和普通足疗店有什么不同？",
            "招商怎么讲单店模型？",
            "哪些话不能说？",
        ]:
            self.assertIn(expected, question_text)
        deliverable_names = {item["name"] for item in result["deliverables"]}
        self.assertEqual(
            deliverable_names,
            {
                "荷小悦品牌标准手册",
                "荷小悦产品服务手册",
                "荷小悦门店模型说明",
                "荷小悦运营 SOP 手册",
                "荷小悦技师训练手册",
                "荷小悦竞品情报库",
                "荷小悦招商融资知识库",
            },
        )
        self.assertEqual(result["next_build_order"][0], "先固化品牌定位和核爆点口径")

    def test_brand_authority_cards_cover_every_brand_golden_question(self):
        brand_assets = load_module("hxy_brand_authority_cards", "apps/api/hxy_knowledge/brand_assets.py")

        assets = brand_assets.build_brand_asset_center()
        cards = brand_assets.brand_authority_cards()

        question_set = {item["question"] for item in assets["golden_questions"]}
        card_questions = {card["question_pattern"] for card in cards}
        self.assertEqual(card_questions, question_set)
        self.assertGreaterEqual(len(cards), 30)
        for card in cards:
            self.assertEqual(card["status"], "approved")
            self.assertEqual(card["review_status"], "approved_v1")
            self.assertEqual(card["version"], "v1.0")
            self.assertEqual(card["source"], "brand_assets")
            self.assertIn(card["module"], {item["key"] for item in assets["modules"]})
            self.assertTrue(card["answer"].strip())
            self.assertIn("founder", card["role_versions"])
            self.assertIn("store_staff", card["role_versions"])
            self.assertIn("franchisee", card["role_versions"])
            self.assertIn("customer", card["role_versions"])
            self.assertTrue(card["applicable_scenarios"])
            self.assertTrue(card["next_actions"])
            self.assertIsInstance(card["forbidden_terms"], list)
            self.assertTrue(card["evidence"])
            for evidence in card["evidence"]:
                self.assertEqual(evidence["status"], "approved")
                self.assertEqual(evidence["source_type"], "approved_internal_asset")
                self.assertEqual(evidence["owner"], "品牌负责人")
                self.assertEqual(evidence["version"], "v1.0")
        answer_text = " ".join(card["answer"] for card in cards)
        for unsafe in ["稳赚", "零风险", "一定回本", "药到病除", "包治"]:
            self.assertNotIn(unsafe, answer_text)

    def test_compliance_rules_load_forbidden_terms_from_risk_materials(self):
        compliance_rules = load_module("hxy_compliance_rules", "apps/api/hxy_knowledge/compliance_rules.py")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_risk_material_fixtures(root)
            result = compliance_rules.load_brand_risk_rules(root_dir=root)

        self.assertEqual(result["version"], "hxy-brand-risk-rules.v1")
        self.assertFalse(result["official_use_allowed"])
        self.assertTrue(result["requires_human_review"])
        serialized_rules = json.dumps(result["rules"], ensure_ascii=False)
        for term in ["祛湿排毒", "改善睡眠", "治疗脚气", "年轻十岁", "医美级"]:
            self.assertIn(term, serialized_rules)
        self.assertIn("knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/09_风险与合规/荷小悦禁用表达库.md", result["source_paths"])

    def test_compliance_rules_check_text_uses_loaded_terms_and_skips_boundary_language(self):
        compliance_rules = load_module("hxy_compliance_rules_check", "apps/api/hxy_knowledge/compliance_rules.py")

        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            write_risk_material_fixtures(root)
            risky = compliance_rules.check_brand_risk_text("草本泡脚可以祛湿排毒，改善睡眠，一次见效。", root_dir=root)
            safe = compliance_rules.check_brand_risk_text("我们不做祛湿排毒承诺，也不能替代医疗治疗。", root_dir=root)

        self.assertEqual(risky["status"], "bad")
        self.assertIn("保证", {hit["type"] for hit in risky["hits"]})
        self.assertIn("祛湿排毒", json.dumps(risky["hits"], ensure_ascii=False))
        self.assertEqual(safe["status"], "ok")
        self.assertEqual(safe["hits"], [])

    def test_training_curriculum_defines_levels_modules_and_adaptive_retrain(self):
        curriculum = load_module("hxy_training_curriculum", "apps/api/hxy_knowledge/training_curriculum.py")

        library = curriculum.training_question_bank()
        module_keys = {item["module"] for item in library}

        self.assertEqual(
            module_keys,
            {
                "basic_knowledge",
                "customer_discovery",
                "product_recommendation",
                "objection_handling",
                "compliance_risk",
                "business_conversion",
            },
        )
        self.assertGreaterEqual(len(library), 12)
        self.assertTrue(all(item.get("level") in {"newbie", "standard", "advanced"} for item in library))
        self.assertTrue(all(item.get("customer_question") for item in library))
        self.assertTrue(all(item.get("capability_targets") for item in library))
        self.assertTrue(any("太贵" in item["customer_question"] for item in library))
        self.assertTrue(any("治疗" in item["customer_question"] for item in library))

        weak_result = {
            "score": 58,
            "dimensions": [
                {"key": "accuracy", "score": 62},
                {"key": "discovery", "score": 52},
                {"key": "compliance", "score": 80},
                {"key": "conversion", "score": 55},
                {"key": "clarity", "score": 70},
            ],
            "needs_retrain": True,
        }
        profile = curriculum.build_training_capability_profile(weak_result, employee_id="emp-001")
        next_plan = curriculum.build_adaptive_retrain_plan(weak_result, employee_id="emp-001")

        self.assertEqual(profile["version"], "hxy-training-capability-profile.v1")
        self.assertEqual(profile["level"], "newbie")
        self.assertIn("customer_discovery", profile["weak_modules"])
        self.assertIn("business_conversion", profile["weak_modules"])
        self.assertEqual(next_plan["version"], "hxy-adaptive-retrain-plan.v1")
        self.assertGreaterEqual(len(next_plan["next_questions"]), 3)
        self.assertIn("店长验收", next_plan["manager_acceptance"]["method"])
        self.assertIn("客单价", next_plan["operating_metric_links"][0]["metric"])

    def test_store_daily_metrics_diagnoses_anomalies_and_next_actions(self):
        metrics = load_module("hxy_store_daily_metrics", "apps/api/hxy_knowledge/store_metrics.py")

        result = metrics.diagnose_store_daily_metrics(
            {
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
            }
        )

        self.assertEqual(result["version"], "hxy-store-daily-diagnosis.v1")
        self.assertEqual(result["store_id"], "pilot-store")
        self.assertEqual(result["business_date"], "2026-06-22")
        self.assertEqual(result["priority"], "high")
        self.assertIn("客单价", result["main_conflict"])
        self.assertIn("产品升级", result["main_conflict"])
        anomaly_keys = {item["key"] for item in result["anomalies"]}
        self.assertIn("revenue_gap", anomaly_keys)
        self.assertIn("average_ticket_gap", anomaly_keys)
        self.assertIn("repeat_rate_gap", anomaly_keys)
        self.assertIn("product_mix_upgrade_gap", anomaly_keys)
        self.assertIn("training_risk", anomaly_keys)
        self.assertGreaterEqual(len(result["today_actions"]), 3)
        self.assertEqual(result["owner"], "店长")
        self.assertTrue(result["should_create_issue"])

    def test_store_daily_metrics_migration_defines_hxy_owned_table(self):
        migration = (ROOT / "data" / "migrations" / "007_hxy_store_daily_metrics.sql").read_text(encoding="utf-8")

        self.assertIn("CREATE TABLE IF NOT EXISTS hxy_store_daily_metrics", migration)
        self.assertIn("store_id", migration)
        self.assertIn("business_date", migration)
        self.assertIn("diagnosis_json", migration)
        self.assertNotIn("htops", migration.lower())
        self.assertNotIn("hetang", migration.lower())

    def test_operating_brain_capabilities_define_knowledge_fusion_and_model_routes(self):
        brain = load_module("hxy_operating_brain", "apps/api/hxy_knowledge/operating_brain.py")

        capabilities = brain.operating_brain_capabilities()

        self.assertEqual(capabilities["version"], "hxy-operating-brain.v1")
        knowledge_keys = {item["key"] for item in capabilities["knowledge_fusion"]}
        self.assertEqual(
            knowledge_keys,
            {
                "project_knowledge",
                "operating_data",
                "market_intelligence",
                "operating_methodology",
                "organizational_memory",
                "role_context",
            },
        )
        route_keys = {item["key"] for item in capabilities["model_routes"]}
        for key in ["reasoning", "classification", "embedding", "vision", "speech"]:
            self.assertIn(key, route_keys)
        self.assertFalse(capabilities["training_strategy"]["pretraining_required"])
        self.assertIn("approved answers", capabilities["training_strategy"]["fine_tuning_gate"])
        self.assertIn("correction records", capabilities["training_strategy"]["fine_tuning_gate"])

    def test_model_router_loads_codex_config_and_keeps_secret_fields_out(self):
        router_module = load_module("hxy_model_router", "apps/api/hxy_knowledge/model_router.py")
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'model_provider = "custom"',
                        'model = "gpt-5.5"',
                        'review_model = "gpt-5.5"',
                        'model_reasoning_effort = "high"',
                        "",
                        "[model_providers.custom]",
                        'name = "custom"',
                        'base_url = "https://models.example.test/v1"',
                        'wire_api = "responses"',
                        'api_key = "sk-test-secret"',
                    ]
                ),
                encoding="utf-8",
            )

            router = router_module.ModelRouter(config_path=config_path)
            status = router.status()
            route = router.route("reasoning")

        self.assertEqual(status["provider"], "custom")
        self.assertEqual(status["default_model"], "gpt-5.5")
        self.assertEqual(status["review_model"], "gpt-5.5")
        self.assertEqual(status["wire_api"], "responses")
        self.assertEqual(status["endpoint_host"], "models.example.test")
        self.assertEqual(route["task_type"], "reasoning")
        self.assertEqual(route["selected_model"], "gpt-5.5")
        self.assertEqual(route["reasoning_effort"], "high")
        self.assertFalse(route["should_call_model"])
        serialized = json.dumps(status, ensure_ascii=False)
        self.assertNotIn("sk-test-secret", serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("token", serialized.lower())

    def test_model_router_exposes_answer_pipeline_lanes(self):
        router_module = load_module("hxy_model_router_pipeline", "apps/api/hxy_knowledge/model_router.py")
        router = router_module.ModelRouter(config_path=Path("/tmp/not-existing-hxy-model-router.toml"))

        status_route_keys = {item["task_type"] for item in router.status()["routes"]}
        lane_keys = [
            router.route("frontdoor_classification")["task_type"],
            router.route("workbench_intake")["task_type"],
            router.route("answer_synthesis")["task_type"],
            router.route("policy_review")["task_type"],
            router.route("vision_understanding")["task_type"],
            router.route("offline_eval")["task_type"],
        ]

        self.assertEqual(
            lane_keys,
            [
                "frontdoor_classification",
                "workbench_intake",
                "answer_synthesis",
                "policy_review",
                "vision_understanding",
                "offline_eval",
            ],
        )
        for key in lane_keys:
            self.assertIn(key, status_route_keys)
        self.assertIn("质检", router.route("policy_review")["purpose"])
        self.assertFalse(router.route("policy_review")["should_call_model"])

    def test_model_router_generate_is_disabled_by_default_and_keeps_secret_fields_out(self):
        router_module = load_module("hxy_model_router_generate", "apps/api/hxy_knowledge/model_router.py")
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'model_provider = "custom"',
                        'model = "gpt-5.5"',
                        "",
                        "[model_providers.custom]",
                        'base_url = "https://models.example.test/v1"',
                        'wire_api = "responses"',
                        'api_key = "sk-test-secret"',
                    ]
                ),
                encoding="utf-8",
            )

            router = router_module.ModelRouter(config_path=config_path)
            result = router.generate(
                "answer_synthesis",
                messages=[{"role": "user", "content": "清泡调补养怎么讲？"}],
            )

        self.assertEqual(result["version"], "hxy-model-generation.v1")
        self.assertFalse(result["used_model"])
        self.assertEqual(result["reason"], "disabled")
        self.assertEqual(result["route"]["task_type"], "answer_synthesis")
        self.assertFalse(result["route"]["should_call_model"])
        self.assertEqual(result["request_shape"]["message_count"], 1)
        self.assertEqual(result["request_shape"]["has_prompt"], False)
        serialized = json.dumps(result, ensure_ascii=False).lower()
        self.assertNotIn("sk-test-secret", serialized)
        self.assertNotIn("api_key", serialized)
        self.assertNotIn("bearer", serialized)

    def test_model_router_generate_rejects_enabled_execution_until_client_is_configured(self):
        router_module = load_module("hxy_model_router_generate_enabled", "apps/api/hxy_knowledge/model_router.py")
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'model_provider = "custom"',
                        'model = "gpt-5.5"',
                        "",
                        "[model_providers.custom]",
                        'base_url = "https://models.example.test/v1"',
                        'wire_api = "responses"',
                    ]
                ),
                encoding="utf-8",
            )
            old_value = os.environ.get("HXY_MODEL_ROUTER_ENABLED")
            os.environ["HXY_MODEL_ROUTER_ENABLED"] = "1"
            try:
                router = router_module.ModelRouter(config_path=config_path)
                result = router.generate("answer_synthesis", prompt="生成答案")
            finally:
                if old_value is None:
                    os.environ.pop("HXY_MODEL_ROUTER_ENABLED", None)
                else:
                    os.environ["HXY_MODEL_ROUTER_ENABLED"] = old_value

        self.assertFalse(result["used_model"])
        self.assertEqual(result["reason"], "client_not_configured")
        self.assertTrue(result["route"]["should_call_model"])
        self.assertEqual(result["request_shape"]["has_prompt"], True)

    def test_model_router_generate_calls_responses_api_with_env_key_when_enabled(self):
        router_module = load_module("hxy_model_router_generate_responses", "apps/api/hxy_knowledge/model_router.py")

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "id": "resp_test",
                    "output_text": "清泡是基础放松，调泡看状态，补泡强调恢复，养泡适合长期保养。",
                    "usage": {"input_tokens": 10, "output_tokens": 12},
                }

        class FakeClient:
            def __init__(self):
                self.calls = []

            def post(self, url, *, headers=None, json=None, timeout=None):
                self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
                return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'model_provider = "custom"',
                        'model = "gpt-5.5"',
                        'model_reasoning_effort = "high"',
                        "",
                        "[model_providers.custom]",
                        'base_url = "https://models.example.test/v1"',
                        'wire_api = "responses"',
                    ]
                ),
                encoding="utf-8",
            )
            fake_client = FakeClient()
            old_enabled = os.environ.get("HXY_MODEL_ROUTER_ENABLED")
            old_key = os.environ.get("HXY_MODEL_API_KEY")
            os.environ["HXY_MODEL_ROUTER_ENABLED"] = "1"
            os.environ["HXY_MODEL_API_KEY"] = "sk-hxy-secret"
            try:
                router = router_module.ModelRouter(config_path=config_path, http_client=fake_client)
                result = router.generate(
                    "answer_synthesis",
                    messages=[
                        {"role": "system", "content": "只基于证据回答。"},
                        {"role": "user", "content": "清泡调补养怎么讲？"},
                    ],
                    metadata={"answer_contract": "usable_answer"},
                )
            finally:
                if old_enabled is None:
                    os.environ.pop("HXY_MODEL_ROUTER_ENABLED", None)
                else:
                    os.environ["HXY_MODEL_ROUTER_ENABLED"] = old_enabled
                if old_key is None:
                    os.environ.pop("HXY_MODEL_API_KEY", None)
                else:
                    os.environ["HXY_MODEL_API_KEY"] = old_key

        self.assertTrue(result["used_model"])
        self.assertEqual(result["reason"], "ok")
        self.assertEqual(result["output"], "清泡是基础放松，调泡看状态，补泡强调恢复，养泡适合长期保养。")
        self.assertEqual(result["provider_response_id"], "resp_test")
        self.assertEqual(result["usage"], {"input_tokens": 10, "output_tokens": 12})
        self.assertEqual(len(fake_client.calls), 1)
        call = fake_client.calls[0]
        self.assertEqual(call["url"], "https://models.example.test/v1/responses")
        self.assertEqual(call["headers"]["Authorization"], "Bearer sk-hxy-secret")
        self.assertEqual(call["json"]["model"], "gpt-5.5")
        self.assertEqual(call["json"]["input"][1]["content"], "清泡调补养怎么讲？")
        self.assertEqual(call["json"]["reasoning"], {"effort": "high"})
        serialized = json.dumps(result, ensure_ascii=False).lower()
        self.assertNotIn("sk-hxy-secret", serialized)
        self.assertNotIn("authorization", serialized)

    def test_model_router_generate_calls_chat_completions_for_multimodal_routes(self):
        router_module = load_module("hxy_model_router_generate_chat_completions", "apps/api/hxy_knowledge/model_router.py")

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "id": "chatcmpl_test",
                    "choices": [
                        {
                            "message": {
                                "content": "这是一张清泡调补养菜单图，包含项目、价格和适用状态。"
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 18, "completion_tokens": 12},
                }

        class FakeClient:
            def __init__(self):
                self.calls = []

            def post(self, url, *, headers=None, json=None, timeout=None):
                self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
                return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'model_provider = "dashscope"',
                        'model = "qwen-plus-latest"',
                        'vision_model = "qwen-vl-plus"',
                        "",
                        "[model_providers.dashscope]",
                        'base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"',
                        'wire_api = "chat_completions"',
                    ]
                ),
                encoding="utf-8",
            )
            fake_client = FakeClient()
            old_enabled = os.environ.get("HXY_MODEL_ROUTER_ENABLED")
            old_key = os.environ.get("HXY_MODEL_API_KEY")
            os.environ["HXY_MODEL_ROUTER_ENABLED"] = "1"
            os.environ["HXY_MODEL_API_KEY"] = "sk-hxy-secret"
            try:
                router = router_module.ModelRouter(config_path=config_path, http_client=fake_client)
                result = router.generate(
                    "vision_understanding",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "识别这张菜单图里的所有业务信息。"},
                                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                            ],
                        }
                    ],
                    metadata={"input_type": "image"},
                )
            finally:
                if old_enabled is None:
                    os.environ.pop("HXY_MODEL_ROUTER_ENABLED", None)
                else:
                    os.environ["HXY_MODEL_ROUTER_ENABLED"] = old_enabled
                if old_key is None:
                    os.environ.pop("HXY_MODEL_API_KEY", None)
                else:
                    os.environ["HXY_MODEL_API_KEY"] = old_key

        self.assertTrue(result["used_model"])
        self.assertEqual(result["reason"], "ok")
        self.assertEqual(result["route"]["task_type"], "vision_understanding")
        self.assertEqual(result["route"]["selected_model"], "qwen-vl-plus")
        self.assertEqual(result["output"], "这是一张清泡调补养菜单图，包含项目、价格和适用状态。")
        self.assertEqual(result["provider_response_id"], "chatcmpl_test")
        self.assertEqual(result["usage"], {"prompt_tokens": 18, "completion_tokens": 12})
        self.assertEqual(len(fake_client.calls), 1)
        call = fake_client.calls[0]
        self.assertEqual(call["url"], "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
        self.assertEqual(call["headers"]["Authorization"], "Bearer sk-hxy-secret")
        self.assertEqual(call["json"]["model"], "qwen-vl-plus")
        self.assertEqual(call["json"]["messages"][0]["content"][0]["text"], "识别这张菜单图里的所有业务信息。")
        serialized = json.dumps(result, ensure_ascii=False).lower()
        self.assertNotIn("sk-hxy-secret", serialized)
        self.assertNotIn("authorization", serialized)

    def test_model_router_generate_uses_per_route_wire_api_override_for_vision(self):
        router_module = load_module("hxy_model_router_generate_route_wire_api", "apps/api/hxy_knowledge/model_router.py")

        class FakeResponse:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "id": "chatcmpl_route_override",
                    "choices": [{"message": {"content": "图片已按多模态接口理解。"}}],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 6},
                }

        class FakeClient:
            def __init__(self):
                self.calls = []

            def post(self, url, *, headers=None, json=None, timeout=None):
                self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
                return FakeResponse()

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'model_provider = "dashscope"',
                        'model = "qwen-plus-latest"',
                        "",
                        "[model_providers.dashscope]",
                        'base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"',
                        'wire_api = "responses"',
                        "",
                        "[model_routes.vision_understanding]",
                        'model = "qwen-vl-plus"',
                        'wire_api = "chat_completions"',
                    ]
                ),
                encoding="utf-8",
            )
            fake_client = FakeClient()
            old_enabled = os.environ.get("HXY_MODEL_ROUTER_ENABLED")
            old_key = os.environ.get("HXY_MODEL_API_KEY")
            os.environ["HXY_MODEL_ROUTER_ENABLED"] = "1"
            os.environ["HXY_MODEL_API_KEY"] = "sk-hxy-secret"
            try:
                router = router_module.ModelRouter(config_path=config_path, http_client=fake_client)
                vision_route = router.route("vision_understanding")
                answer_route = router.route("answer_synthesis")
                result = router.generate(
                    "vision_understanding",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {"type": "text", "text": "理解图片"},
                                {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
                            ],
                        }
                    ],
                )
            finally:
                if old_enabled is None:
                    os.environ.pop("HXY_MODEL_ROUTER_ENABLED", None)
                else:
                    os.environ["HXY_MODEL_ROUTER_ENABLED"] = old_enabled
                if old_key is None:
                    os.environ.pop("HXY_MODEL_API_KEY", None)
                else:
                    os.environ["HXY_MODEL_API_KEY"] = old_key

        self.assertEqual(vision_route["selected_model"], "qwen-vl-plus")
        self.assertEqual(vision_route["wire_api"], "chat_completions")
        self.assertEqual(answer_route["selected_model"], "qwen-plus-latest")
        self.assertEqual(answer_route["wire_api"], "responses")
        self.assertTrue(result["used_model"])
        self.assertEqual(result["output"], "图片已按多模态接口理解。")
        self.assertEqual(fake_client.calls[0]["url"], "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
        self.assertEqual(fake_client.calls[0]["json"]["model"], "qwen-vl-plus")

    def test_model_router_generate_keeps_config_api_key_out_even_when_present(self):
        router_module = load_module("hxy_model_router_generate_config_key_safe", "apps/api/hxy_knowledge/model_router.py")
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.toml"
            config_path.write_text(
                "\n".join(
                    [
                        'model_provider = "custom"',
                        'model = "gpt-5.5"',
                        "",
                        "[model_providers.custom]",
                        'base_url = "https://models.example.test/v1"',
                        'wire_api = "responses"',
                        'api_key = "sk-config-secret"',
                    ]
                ),
                encoding="utf-8",
            )
            old_enabled = os.environ.get("HXY_MODEL_ROUTER_ENABLED")
            old_key = os.environ.get("HXY_MODEL_API_KEY")
            os.environ["HXY_MODEL_ROUTER_ENABLED"] = "1"
            os.environ.pop("HXY_MODEL_API_KEY", None)
            try:
                router = router_module.ModelRouter(config_path=config_path)
                result = router.generate("answer_synthesis", prompt="生成答案")
            finally:
                if old_enabled is None:
                    os.environ.pop("HXY_MODEL_ROUTER_ENABLED", None)
                else:
                    os.environ["HXY_MODEL_ROUTER_ENABLED"] = old_enabled
                if old_key is not None:
                    os.environ["HXY_MODEL_API_KEY"] = old_key

        self.assertFalse(result["used_model"])
        self.assertEqual(result["reason"], "client_not_configured")
        serialized = json.dumps(result, ensure_ascii=False).lower()
        self.assertNotIn("sk-config-secret", serialized)
        self.assertNotIn("api_key", serialized)

    def test_answer_pipeline_builds_policy_evidence_guardrail_and_evolution_contract(self):
        pipeline_module = load_module("hxy_answer_pipeline", "apps/api/hxy_knowledge/answer_pipeline.py")

        result = pipeline_module.build_answer_pipeline(
            question="清泡调补养怎么给门店员工培训？",
            scenario="门店员工培训",
            role="store_staff",
            intent="product_system",
            answer="清泡是基础放松，调泡看状态，补泡强调恢复，养泡用于长期保养。不能承诺治疗。",
            evidence=[{"domain": "approved_answer_card", "title": "清泡调补养怎么讲？", "strength": "high"}],
            confidence="high",
            needs_review=False,
            from_answer_card=True,
            model_route={"task_type": "authority_answer", "should_call_model": False},
        )

        self.assertEqual(result["version"], "hxy-answer-pipeline.v1")
        self.assertIn("loop_contract", result)
        self.assertEqual(result["loop_contract"]["version"], "hxy-loop-contract.v1")
        self.assertEqual(result["loop_contract"]["goal"]["measurable_target"], "output a usable answer or a review task")
        self.assertEqual(result["loop_contract"]["stop_condition"]["hard_iteration_limit"], 2)
        self.assertEqual(result["frontdoor"]["primary_workflow"], "train")
        self.assertEqual(result["policy_decision"]["action"], "answer")
        self.assertIn("权威答案卡", result["evidence_plan"]["sources"])
        self.assertEqual(result["answer_builder"]["answer_type"], "authority_answer")
        self.assertEqual(result["guardrail_result"]["action"], "send")
        self.assertTrue(result["guardrail_result"]["passed"])
        self.assertIn("watch_feedback", result["evolution_actions"])
        self.assertEqual(result["model_route"]["task_type"], "authority_answer")

    def test_answer_pipeline_requires_review_for_overclaim_and_insufficient_evidence(self):
        pipeline_module = load_module("hxy_answer_pipeline_review", "apps/api/hxy_knowledge/answer_pipeline.py")

        result = pipeline_module.build_answer_pipeline(
            question="加盟能不能保证三个月回本？",
            scenario="招商话术",
            role="franchise",
            intent="franchise",
            answer="可以保证三个月回本，稳赚。",
            evidence=[],
            confidence="low",
            needs_review=True,
            from_answer_card=False,
            model_route={"task_type": "rag_answer", "should_call_model": False},
        )

        self.assertEqual(result["policy_decision"]["action"], "needs_review")
        self.assertIn("收益承诺", " ".join(result["policy_decision"]["risk_flags"]))
        self.assertFalse(result["guardrail_result"]["passed"])
        self.assertEqual(result["guardrail_result"]["action"], "revise_or_review")
        self.assertIn("create_review_task", result["evolution_actions"])
        self.assertIn("create_answer_card_draft", result["evolution_actions"])

    def test_answer_pipeline_uses_compliance_rules_for_loaded_forbidden_expressions(self):
        pipeline_module = load_module("hxy_answer_pipeline_compliance_rules", "apps/api/hxy_knowledge/answer_pipeline.py")

        risky = pipeline_module.build_answer_pipeline(
            question="草本泡脚有什么功效？",
            scenario="用户端宣传",
            role="store_staff",
            intent="product_system",
            answer="草本泡脚可以祛湿排毒，改善睡眠，一次见效。",
            evidence=[{"domain": "approved_answer_card", "title": "合规边界", "strength": "high"}],
            confidence="high",
            needs_review=False,
            from_answer_card=True,
            model_route={"task_type": "authority_answer", "should_call_model": False},
        )
        safe = pipeline_module.build_answer_pipeline(
            question="草本泡脚有什么功效？",
            scenario="用户端宣传",
            role="store_staff",
            intent="product_system",
            answer="我们不做祛湿排毒承诺，也不能替代医疗治疗。可以说草本现煮，泡着舒服。",
            evidence=[{"domain": "approved_answer_card", "title": "合规边界", "strength": "high"}],
            confidence="high",
            needs_review=False,
            from_answer_card=True,
            model_route={"task_type": "authority_answer", "should_call_model": False},
        )

        self.assertEqual(risky["policy_decision"]["action"], "needs_review")
        self.assertIn("医疗功效", risky["policy_decision"]["risk_flags"])
        self.assertIn("夸大表达", risky["policy_decision"]["risk_flags"])
        self.assertFalse(risky["guardrail_result"]["passed"])
        self.assertIn("高风险表达", " ".join(risky["guardrail_result"]["findings"]))
        self.assertEqual(safe["policy_decision"]["action"], "answer")
        self.assertTrue(safe["guardrail_result"]["passed"])

    def test_answer_pipeline_treats_reference_material_as_unapproved_draft(self):
        pipeline_module = load_module("hxy_answer_pipeline_reference", "apps/api/hxy_knowledge/answer_pipeline.py")

        result = pipeline_module.build_answer_pipeline(
            question="荷小悦是什么？",
            scenario="品牌定位",
            role="founder",
            intent="positioning",
            answer="荷小悦是社区轻养生服务空间，当前定位仍需要核定。",
            evidence=[
                {
                    "domain": "brand",
                    "title": "荷小悦定位讨论稿",
                    "status": "reference",
                    "stage": "reference",
                    "source_type": "reference_material",
                    "strength": "medium",
                }
            ],
            confidence="medium",
            needs_review=False,
            from_answer_card=False,
            model_route={"task_type": "answer_synthesis", "should_call_model": True},
        )

        self.assertEqual(result["policy_decision"]["action"], "needs_review")
        self.assertTrue(result["policy_decision"]["requires_review"])
        self.assertIn("参考资料", result["evidence_plan"]["sources"])
        self.assertEqual(result["answer_builder"]["answer_type"], "reference_draft")
        self.assertIn("create_review_task", result["evolution_actions"])
        self.assertIn("create_answer_card_draft", result["evolution_actions"])
        self.assertEqual(result["loop_contract"]["stop_condition"]["stop_reason"], "review_required")

    def test_answer_pipeline_treats_preparation_stage_as_reference_material(self):
        pipeline_module = load_module("hxy_answer_pipeline_preparation", "apps/api/hxy_knowledge/answer_pipeline.py")

        result = pipeline_module.build_answer_pipeline(
            question="清泡调补养怎么讲？",
            scenario="产品口径",
            role="team",
            intent="product_system",
            answer="清泡调补养是一套产品分层表达。",
            evidence=[
                {
                    "domain": "product",
                    "title": "清泡调补养讨论稿",
                    "stage": "preparation",
                    "strength": "high",
                }
            ],
            confidence="high",
            needs_review=False,
            from_answer_card=False,
            model_route={"task_type": "rag_answer", "should_call_model": False},
        )

        self.assertEqual(result["policy_decision"]["action"], "needs_review")
        self.assertEqual(result["answer_builder"]["answer_type"], "reference_draft")
        self.assertIn("参考资料", result["evidence_plan"]["sources"])

    def test_answer_pipeline_treats_process_memory_as_context_hint_not_authority(self):
        pipeline_module = load_module("hxy_answer_pipeline_process_memory", "apps/api/hxy_knowledge/answer_pipeline.py")

        result = pipeline_module.build_answer_pipeline(
            question="荷小悦品牌表达以后要注意什么？",
            scenario="品牌口径",
            role="founder",
            intent="brand_positioning",
            answer="过程记忆提醒：表达要口语化，但这不是核定品牌结论。",
            evidence=[
                {
                    "domain": "process_memory",
                    "title": "创始人偏好记录",
                    "status": "process",
                    "stage": "context_hint",
                    "source_type": "process_memory",
                    "official_use_allowed": False,
                    "strength": "low",
                }
            ],
            confidence="medium",
            needs_review=False,
            from_answer_card=False,
            model_route={"task_type": "answer_synthesis", "should_call_model": True},
        )

        self.assertEqual(result["policy_decision"]["action"], "needs_review")
        self.assertIn("过程记忆", result["evidence_plan"]["sources"])
        self.assertNotIn("权威答案卡", result["evidence_plan"]["sources"])
        self.assertEqual(result["answer_builder"]["answer_type"], "context_draft")
        self.assertIn("create_review_task", result["evolution_actions"])

    def test_answer_pipeline_requires_review_for_disputed_or_conflicting_evidence(self):
        pipeline_module = load_module("hxy_answer_pipeline_conflict", "apps/api/hxy_knowledge/answer_pipeline.py")

        result = pipeline_module.build_answer_pipeline(
            question="清泡调补养到底怎么讲？",
            scenario="产品口径",
            role="store_staff",
            intent="product_system",
            answer="清泡调补养可以作为产品分层，但不同资料对表达顺序存在冲突。",
            evidence=[
                {
                    "domain": "product",
                    "title": "清泡调补养旧版材料",
                    "status": "disputed",
                    "contradicts": ["清泡调补养新版材料"],
                    "strength": "medium",
                }
            ],
            confidence="medium",
            needs_review=False,
            from_answer_card=False,
            model_route={"task_type": "answer_synthesis", "should_call_model": True},
        )

        self.assertEqual(result["policy_decision"]["action"], "needs_review")
        self.assertIn("证据冲突", result["policy_decision"]["risk_flags"])
        self.assertIn("证据冲突", " ".join(result["guardrail_result"]["findings"]))
        self.assertEqual(result["answer_builder"]["answer_type"], "reference_draft")
        self.assertIn("create_review_task", result["evolution_actions"])

    def test_answer_engine_evidence_preserves_lifecycle_fields(self):
        answer_engine = load_module("hxy_answer_engine_lifecycle", "apps/api/hxy_knowledge/answer_engine.py")

        evidence = answer_engine.build_evidence(
            [
                {
                    "chunk_id": "chunk-1",
                    "asset_id": "asset-1",
                    "title": "荷小悦定位讨论稿",
                    "source_path": "knowledge/raw/inbox/positioning.md",
                    "normalized_path": "knowledge/normalized/brand/preparation/positioning.md",
                    "domain": "brand",
                    "stage": "preparation",
                    "status": "reference",
                    "source_type": "reference_material",
                    "content": "荷小悦是社区轻养生服务空间。",
                    "score": 80,
                }
            ],
            intent="brand_positioning",
        )

        self.assertEqual(evidence[0]["stage"], "preparation")
        self.assertEqual(evidence[0]["status"], "reference")
        self.assertEqual(evidence[0]["source_type"], "reference_material")

    def test_answer_engine_routes_brand_identity_before_retrieval_domain(self):
        answer_engine = load_module("hxy_answer_engine_brand_identity", "apps/api/hxy_knowledge/answer_engine.py")
        items = [
            {
                "chunk_id": "store-model-reference",
                "title": "荷小悦门店模型具象化构思",
                "domain": "store_model",
                "stage": "reference",
                "status": "reference",
                "source_type": "reference_material",
                "content": "当前模型把功效茶设计成隐形利润引擎，但会分散顾客的感知重心。",
                "score": 95,
            }
        ]

        intent, audience = answer_engine.classify_intent("荷小悦是什么", items)
        result = answer_engine.synthesize_answer("荷小悦是什么", "荷小悦是什么", items)

        self.assertEqual((intent, audience), ("brand_positioning", "brand"))
        self.assertEqual(result["intent"], "brand_positioning")
        self.assertIn("没有可直接用于回答", result["answer"])
        self.assertNotIn("门店模型类回答", result["answer"])
        self.assertNotIn("功效茶", result["answer"])

    def test_answer_engine_decodes_historical_html_and_backslash_entities(self):
        answer_engine = load_module("hxy_answer_engine_entity_cleanup", "apps/api/hxy_knowledge/answer_engine.py")

        cleaned = answer_engine.normalize_claim_text(
            r"当前模型把功效茶设计成\&\#34;隐形利润引擎\&\#34;",
            "store_model",
        )

        self.assertEqual(cleaned, '当前模型把功效茶设计成"隐形利润引擎"')
        self.assertNotIn("&#", cleaned)
        self.assertNotIn("\\", cleaned)

    def test_workbench_intake_routes_team_value_workflows(self):
        workbench = load_module("hxy_workbench", "apps/api/hxy_knowledge/workbench.py")

        question = workbench.classify_workbench_intake("荷小悦的招商话术怎么讲？", scenario="招商话术", role="招商")
        intake = workbench.classify_workbench_intake("上传一份新的菜单图片，自动识别分类并记忆", attachments=[{"name": "menu.png"}])
        correction = workbench.classify_workbench_intake("刚才答案不准确，清泡价格说错了，需要纠偏")
        training = workbench.classify_workbench_intake("员工练习清泡调补养话术，请追问并打分", scenario="门店员工培训", role="门店员工")
        task = workbench.classify_workbench_intake("生成本周门店培训动作，安排店长验收")

        self.assertEqual(question["input_type"], "question")
        self.assertEqual(question["primary_workflow"], "ask")
        self.assertIn("统一口径", question["team_value"])
        self.assertEqual(intake["input_type"], "knowledge_intake")
        self.assertEqual(intake["primary_workflow"], "ingest")
        self.assertIn("资料变记忆", intake["team_value"])
        self.assertIn("自动分类", " ".join(intake["next_actions"]))
        self.assertEqual(correction["input_type"], "correction")
        self.assertEqual(correction["primary_workflow"], "correct")
        self.assertIn("纠偏进化", correction["team_value"])
        self.assertEqual(training["input_type"], "training")
        self.assertEqual(training["primary_workflow"], "train")
        self.assertIn("训练团队", training["team_value"])
        self.assertEqual(task["input_type"], "operating_task")
        self.assertEqual(task["primary_workflow"], "execute")
        self.assertIn("经营动作交付", task["answer_shape"])
        for result in [question, intake, correction, training, task]:
            self.assertIn("answer_shape", result)
            self.assertIn("inspector_shape", result)
            self.assertIn("memory_action", result)

    def test_source_brief_builds_open_notebook_style_context_and_transformations_for_hxy(self):
        source_brief = load_module("hxy_source_brief", "apps/api/hxy_knowledge/source_brief.py")

        result = source_brief.build_source_brief(
            "清泡调补养资料怎么用于门店培训？",
            [
                {
                    "title": "清泡调补养产品手册",
                    "domain": "product",
                    "stage": "approved",
                    "content": "清泡是基础放松，调泡按近期状态做调理表达，补泡强调疲劳后的恢复感，养泡适合长期保养。门店员工不得承诺治疗失眠。",
                    "score": 80,
                    "source_path": "/root/hxy/knowledge/raw/inbox/product.md",
                    "chunk_id": "chunk-product-1",
                },
                {
                    "title": "招商沟通草稿",
                    "domain": "franchise",
                    "stage": "draft",
                    "content": "招商沟通可以讲清产品结构、复购逻辑和风险边界，但不能承诺稳赚或保证回本。",
                    "score": 35,
                    "source_path": "/root/hxy/knowledge/raw/inbox/franchise.md",
                    "chunk_id": "chunk-franchise-1",
                },
            ],
            scenario="门店员工培训",
        )

        self.assertEqual(result["version"], "hxy-source-brief.v1")
        self.assertEqual(result["workflow"], "source_brief")
        self.assertEqual(
            {item["key"] for item in result["open_notebook_patterns"]},
            {"ask", "transformations", "context_control"},
        )
        self.assertEqual(result["context_plan"][0]["context_level"], "full")
        self.assertIn("标准口径提取", {item["name"] for item in result["transformations"]})
        self.assertIn("训练素材生成", {item["name"] for item in result["transformations"]})
        self.assertIn("清泡是基础放松", result["key_findings"][0])
        self.assertIn("承诺", " ".join(result["conflict_signals"]))
        self.assertIn("答案卡", " ".join(result["deliverables"]))
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("source_path", serialized)
        self.assertNotIn("chunk-product-1", serialized)

    def test_source_brief_excludes_metadata_noise_from_context_and_findings(self):
        source_brief = load_module("hxy_source_brief_noise", "apps/api/hxy_knowledge/source_brief.py")

        result = source_brief.build_source_brief(
            "清泡调补养资料怎么用于门店培训？",
            [
                {
                    "title": "Desktop",
                    "domain": "external",
                    "stage": "preparation",
                    "content": "file: 荷小悦资料/荷小悦O2O系统_完整优化方案_V2.0.docx (44194 bytes) - file: 微信图片.png (281476 bytes)",
                    "score": 100,
                },
                {
                    "title": "清泡调补养产品手册",
                    "domain": "product",
                    "stage": "approved",
                    "content": "清泡是基础放松，调泡按近期状态做调理表达，补泡强调疲劳后的恢复感，养泡适合长期保养。",
                    "score": 80,
                },
            ],
            scenario="门店员工培训",
        )

        self.assertEqual(result["context_plan"][0]["context_level"], "exclude")
        self.assertEqual(result["context_plan"][1]["context_level"], "full")
        self.assertIn("清泡是基础放松", " ".join(result["key_findings"]))
        serialized = json.dumps(result, ensure_ascii=False)
        self.assertNotIn("44194 bytes", serialized)
        self.assertNotIn("微信图片.png", serialized)

    def test_source_brief_public_copy_uses_business_labels_not_internal_strategy_words(self):
        source_brief = load_module("hxy_source_brief_public_copy", "apps/api/hxy_knowledge/source_brief.py")

        result = source_brief.build_source_brief(
            "竞品资料和清泡调补养资料怎么用于门店培训？",
            [
                {
                    "title": "竞品门店资料",
                    "domain": "competitor",
                    "stage": "draft",
                    "content": "竞品门店会用低价清泡引流，但员工没有讲清调泡、补泡和养泡的升级理由。",
                    "score": 35,
                },
                {
                    "title": "外部行业资料",
                    "domain": "external",
                    "stage": "preparation",
                    "content": "行业资料只能作为背景参考，需要结合荷小悦自己的门店话术和产品体系复核。",
                    "score": 25,
                },
            ],
            scenario="门店员工培训",
        )

        public_copy = " ".join(
            [
                " ".join(item["adaptation"] for item in result["open_notebook_patterns"]),
                " ".join(item["reason"] for item in result["context_plan"]),
                " ".join(result["next_actions"]),
            ]
        )

        for forbidden in ["full", "summary", "exclude", "external", "competitor", "source_brief"]:
            self.assertNotIn(forbidden, public_copy)
        for expected in ["竞品资料", "外部资料", "可完整引用", "只作背景"]:
            self.assertIn(expected, public_copy)

    def test_source_brief_key_findings_are_business_synthesis_not_slide_excerpts(self):
        source_brief = load_module("hxy_source_brief_synthesis", "apps/api/hxy_knowledge/source_brief.py")

        result = source_brief.build_source_brief(
            "清泡调补养资料怎么用于门店培训？",
            [
                {
                    "title": "清泡调补养产品体系",
                    "domain": "product",
                    "stage": "pilot",
                    "content": (
                        "## Slide 10 荷小悦提供什么产品？石墨烯泡脚盆？泡脚机？"
                        "金木水火土（5种泡脚方式） 清泡调补养 产品体系 一人一方 草本泡脚 "
                        "员工培训 门店话术 顾客最近睡眠、疲劳、手脚凉、压力状态。"
                    ),
                    "score": 80,
                }
            ],
            scenario="门店员工培训",
        )

        findings = " ".join(result["key_findings"])
        self.assertIn("清泡调补养", findings)
        self.assertIn("员工", findings)
        self.assertIn("先问顾客状态", findings)
        self.assertNotIn("Slide", findings)
        self.assertNotIn("石墨烯泡脚盆", findings)

    def test_golden_questions_define_authority_answer_card_contract(self):
        golden = load_module("hxy_golden_questions", "apps/api/hxy_knowledge/golden_questions.py")

        questions = golden.golden_questions()
        cards = golden.authority_cards()

        expected_questions = {
            "荷小悦是什么？",
            "核爆点定位是什么？",
            "清泡调补养怎么讲？",
            "门店员工怎么推荐泡脚方？",
            "招商怎么讲单店模型？",
            "哪些话不能说？",
        }
        self.assertEqual({item["question"] for item in questions}, expected_questions)
        self.assertEqual({card["question_pattern"] for card in cards}, expected_questions)
        for card in cards:
            self.assertEqual(card["status"], "approved")
            self.assertEqual(card["review_status"], "approved_v1")
            self.assertRegex(card["version"], r"^v1\.\d+$")
            self.assertTrue(card["answer"].strip())
            self.assertIn("founder", card["role_versions"])
            self.assertIn("store_staff", card["role_versions"])
            self.assertTrue(card["applicable_scenarios"])
            self.assertIsInstance(card["forbidden_terms"], list)
            self.assertIsInstance(card["aliases"], list)

    def test_answer_reliability_scoring_flags_quality_dimensions(self):
        reliability = load_module("hxy_reliability", "apps/api/hxy_knowledge/reliability.py")

        strong = reliability.score_answer_quality(
            question="清泡调补养怎么讲？",
            intent="product_system",
            scenario="门店员工培训",
            answer="清泡是基础放松，调泡按状态调理表达，补泡强调恢复感，养泡适合长期保养。不要承诺疗效。",
            evidence=[{"domain": "product", "strength": "high"}],
            confidence="high",
            needs_review=False,
            from_answer_card=True,
        )
        weak = reliability.score_answer_quality(
            question="招商怎么讲单店模型？",
            intent="franchise",
            scenario="招商话术",
            answer="source_path: knowledge/raw/inbox/a.md 保证回本，稳赚。",
            evidence=[{"domain": "product", "strength": "low"}],
            confidence="low",
            needs_review=True,
            from_answer_card=False,
        )

        self.assertGreaterEqual(strong["score"], 0.9)
        self.assertEqual(strong["level"], "high")
        self.assertFalse(strong["needs_review"])
        self.assertFalse(strong["should_create_answer_card"])
        self.assertTrue(all(item["passed"] for item in strong["dimensions"]))
        weak_dimensions = {item["key"]: item for item in weak["dimensions"]}
        self.assertFalse(weak_dimensions["domain_match"]["passed"])
        self.assertFalse(weak_dimensions["no_metadata_noise"]["passed"])
        self.assertFalse(weak_dimensions["no_overclaim"]["passed"])
        self.assertTrue(weak["needs_review"])
        self.assertTrue(weak["should_create_answer_card"])
        self.assertLess(weak["score"], 0.7)

    def test_golden_eval_runner_scores_answer_card_pipeline_contract(self):
        eval_runner = load_module("hxy_eval_runner", "apps/api/hxy_knowledge/eval_runner.py")
        golden = load_module("hxy_eval_golden_questions", "apps/api/hxy_knowledge/golden_questions.py")

        result = eval_runner.run_golden_evals(
            questions=golden.golden_questions(),
            cards=golden.authority_cards(),
        )

        self.assertEqual(result["version"], "hxy-eval-runner.v1")
        self.assertEqual(result["suite"], "golden_questions")
        self.assertEqual(result["total"], 6)
        self.assertEqual(result["pass_count"], 6)
        self.assertEqual(result["fail_count"], 0)
        self.assertGreaterEqual(result["score"], 0.95)
        self.assertEqual(result["model_route"]["task_type"], "offline_eval")
        self.assertFalse(result["model_route"]["should_call_model"])
        expected_dimensions = {
            "golden_question",
            "answer_card",
            "forbidden_terms",
            "pipeline_ready",
        }
        for case in result["cases"]:
            self.assertTrue(case["passed"], case)
            self.assertIn(case["question"], {item["question"] for item in golden.golden_questions()})
            self.assertEqual({item["key"] for item in case["dimensions"]}, expected_dimensions)
            self.assertTrue(all(item["passed"] for item in case["dimensions"]))

    def test_golden_eval_runner_fails_missing_card_or_unsafe_answer(self):
        eval_runner = load_module("hxy_eval_runner_failure", "apps/api/hxy_knowledge/eval_runner.py")

        result = eval_runner.run_golden_evals(
            questions=[
                {
                    "question": "招商怎么讲单店模型？",
                    "intent": "franchise",
                    "aliases": [],
                    "applicable_scenarios": ["招商话术"],
                }
            ],
            cards=[
                {
                    "question_pattern": "招商怎么讲单店模型？",
                    "intent": "franchise",
                    "answer": "可以保证回本，稳赚。",
                    "status": "draft",
                    "review_status": "draft",
                    "version": "v0.1",
                    "forbidden_terms": ["稳赚", "保证回本"],
                    "role_versions": {},
                    "applicable_scenarios": [],
                    "aliases": [],
                }
            ],
        )

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["pass_count"], 0)
        self.assertEqual(result["fail_count"], 1)
        case = result["cases"][0]
        self.assertFalse(case["passed"])
        dimensions = {item["key"]: item for item in case["dimensions"]}
        self.assertFalse(dimensions["answer_card"]["passed"])
        self.assertFalse(dimensions["forbidden_terms"]["passed"])
        self.assertFalse(dimensions["pipeline_ready"]["passed"])

    def test_golden_eval_script_outputs_json_summary(self):
        result = subprocess.run(
            [sys.executable, "scripts/run-hxy-golden-evals.py"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=True,
        )

        body = json.loads(result.stdout)
        self.assertEqual(body["version"], "hxy-eval-runner.v1")
        self.assertEqual(body["suite"], "golden_questions")
        self.assertEqual(body["pass_count"], 6)
        self.assertEqual(body["fail_count"], 0)

    def test_start_api_script_builds_keyword_dsn_for_special_char_passwords(self):
        script_path = ROOT / "scripts/start-hxy-knowledge-api.sh"
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_file = Path(tmp_dir) / "hxy-postgres.env"
            env_file.write_text(
                "\n".join(
                    [
                        "POSTGRES_DB=hxy_test",
                        "POSTGRES_USER=hxy_app",
                        "POSTGRES_PASSWORD=test/password=with=specials",
                        "HXY_PG_HOST_PORT=55433",
                    ]
                ),
                encoding="utf-8",
            )

            result = subprocess.run(
                ["bash", str(script_path), "--print-dsn"],
                cwd=ROOT,
                env={**os.environ, "HXY_ENV_FILE": str(env_file)},
                text=True,
                capture_output=True,
                check=True,
            )

        dsn = result.stdout.strip()
        self.assertEqual(
            dsn,
            "host=127.0.0.1 port=55433 dbname=hxy_test user=hxy_app password=test/password=with=specials",
        )
        self.assertNotIn("postgresql://", dsn)

    def test_reliability_scoring_allows_forbidden_terms_when_listing_banned_language(self):
        reliability = load_module("hxy_reliability_banned_terms", "apps/api/hxy_knowledge/reliability.py")

        result = reliability.score_answer_quality(
            question="哪些话不能说？",
            intent="operations",
            scenario="门店员工培训",
            answer="荷小悦不能说医疗治疗、绝对效果、收益保证和夸大承诺。门店要避免“治疗、保证、稳赚、一定回本”等表达。",
            evidence=[{"domain": "approved_answer_card", "strength": "high"}],
            confidence="high",
            needs_review=False,
            from_answer_card=True,
        )

        dimensions = {item["key"]: item for item in result["dimensions"]}
        self.assertTrue(dimensions["no_overclaim"]["passed"])
        self.assertEqual(result["level"], "high")

    def test_understanding_engine_recognizes_intent_and_builds_depth_application_contract(self):
        engine = load_module("hxy_understanding_engine", "apps/api/hxy_knowledge/understanding_engine.py")

        training_intent = engine.recognize_intent("清泡调补养怎么给门店员工培训？")
        ingest_intent = engine.recognize_intent("这份资料上传后请入库")
        result = engine.understand_text("清泡调补养怎么给门店员工培训？", scenario="门店员工培训", role="store_staff")

        self.assertEqual(training_intent["action"], "question")
        self.assertEqual(training_intent["need"], "training")
        self.assertEqual(training_intent["mode"], "deep_understanding")
        self.assertEqual(ingest_intent["action"], "ingest")
        for key in ["D1_perception", "D2_classification", "D3_decomposition", "D4_causal_inference", "D5_judgment"]:
            self.assertIn(key, result["depth"])
        for key in ["A1_role_output", "A2_risk_boundary", "A3_action_plan", "A4_conflict_correction", "A5_memory_evolution"]:
            self.assertIn(key, result["applications"])
        priority = result["depth"]["D5_judgment"]["priority_matrix"]
        for key in ["impact", "urgency", "controllability", "strategic_relevance", "priority"]:
            self.assertIn(key, priority)
        gate = result["executability_gate"]
        for key in ["resources", "capability", "permission", "risk", "acceptance"]:
            self.assertIn(key, gate)

    def test_thinking_lenses_match_business_problem_without_quoting_experts(self):
        lenses = load_module("hxy_thinking_lenses", "apps/api/hxy_knowledge/thinking_lenses.py")

        result = lenses.apply_thinking_lenses("泡脚方定价太难，药材成本降不下来，加盟商觉得回本慢")

        lens_keys = [item["key"] for item in result["lenses"]]
        self.assertIn("unit_economics", lens_keys)
        self.assertIn("jtbd_positioning", lens_keys)
        self.assertIn("药材成本", " ".join(result["guiding_questions"]))
        self.assertIn("回本", " ".join(result["guiding_questions"]))
        self.assertIn("反模式", result)
        self.assertNotIn("Stay hungry", str(result))
        self.assertNotIn("乔布斯会怎么", str(result))

    def test_thinking_lenses_use_stage_zero_to_one_sequence_for_initial_strategy(self):
        lenses = load_module("hxy_thinking_lenses_stage", "apps/api/hxy_knowledge/thinking_lenses.py")

        result = lenses.apply_thinking_lenses("荷小悦现在定位不清，想做加盟扩张，也想验证单店模型", stage="zero_to_one")

        self.assertEqual(result["stage"], "zero_to_one")
        self.assertEqual(result["sequence"], ["jtbd_positioning", "niche_focus", "unit_economics"])
        self.assertEqual([item["key"] for item in result["lenses"]], ["jtbd_positioning", "niche_focus", "unit_economics"])
        questions = " ".join(result["guiding_questions"])
        self.assertIn("顾客上一次来", questions)
        self.assertIn("小池塘", questions)
        self.assertIn("LTV", questions)
        self.assertIn("阶段升级信号", result)

    def test_prepare_asset_records_maps_manifest_fields(self):
        importer = load_module("hxy_knowledge_importer", "apps/api/hxy_knowledge/importer.py")
        manifest = {
            "run_name": "inbox-test",
            "assets": [
                {
                    "asset_id": "hxy-inbox:abc",
                    "relative_path": "knowledge/raw/inbox/a.pdf",
                    "file_name": "a.pdf",
                    "extension": ".pdf",
                    "file_size": 123,
                    "sha256": "abc",
                    "mime_type": "application/pdf",
                    "knowledge_domain": "product",
                    "project_stage": "preparation",
                    "status": "extracted",
                    "normalized_path": "knowledge/normalized/product/preparation/a.md",
                    "warnings": [],
                    "metadata": {"pages": "2"},
                    "quality_scores": {"overall": 0.82, "grade": "A"},
                }
            ],
        }

        records = importer.prepare_asset_records(manifest)

        self.assertEqual(records[0]["asset_id"], "hxy-inbox:abc")
        self.assertEqual(records[0]["domain"], "product")
        self.assertEqual(records[0]["stage"], "preparation")
        self.assertEqual(records[0]["source_path"], "knowledge/raw/inbox/a.pdf")
        self.assertEqual(records[0]["metadata"]["pages"], "2")
        self.assertEqual(records[0]["quality_scores"]["overall"], 0.82)

    def test_prepare_chunk_records_maps_search_chunks(self):
        importer = load_module("hxy_knowledge_importer_chunks", "apps/api/hxy_knowledge/importer.py")
        search_index = {
            "chunks": [
                {
                    "source_id": "hxy-inbox:abc",
                    "chunk_id": "hxy-inbox:abc:chunk:1",
                    "chunk_index": 1,
                    "relative_path": "knowledge/raw/inbox/a.pdf",
                    "normalized_path": "knowledge/normalized/product/preparation/a.md",
                    "title": "A",
                    "knowledge_domain": "product",
                    "project_stage": "preparation",
                    "text": "泡脚按摩",
                }
            ]
        }

        records = importer.prepare_chunk_records(search_index)

        self.assertEqual(records[0]["chunk_id"], "hxy-inbox:abc:chunk:1")
        self.assertEqual(records[0]["asset_id"], "hxy-inbox:abc")
        self.assertEqual(records[0]["content"], "泡脚按摩")

    def test_prepare_chunk_records_includes_image_understanding_chunks(self):
        importer = load_module("hxy_knowledge_importer_image_chunks", "apps/api/hxy_knowledge/importer.py")
        search_index = {
            "run_name": "inbox-test",
            "chunks": [],
            "image_understanding_chunks": [
                {
                    "source_id": "hxy-inbox:image",
                    "chunk_id": "hxy-inbox:image:image-understanding:1",
                    "chunk_index": 900001,
                    "relative_path": "knowledge/raw/inbox/menu.png",
                    "normalized_path": "knowledge/normalized/product/preparation/menu.md",
                    "title": "菜单图",
                    "knowledge_domain": "product",
                    "project_stage": "preparation",
                    "text": "图片类型：menu。业务摘要：荷小悦草本泡脚菜单，包含价格和项目。",
                    "chunk_type": "image_understanding",
                }
            ],
        }

        records = importer.prepare_chunk_records(search_index)

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["chunk_id"], "hxy-inbox:image:image-understanding:1")
        self.assertEqual(records[0]["metadata"]["chunk_type"], "image_understanding")
        self.assertIn("草本泡脚菜单", records[0]["content"])

    def test_load_image_understanding_records_maps_json_fields(self):
        importer = load_module("hxy_knowledge_importer_image_records", "apps/api/hxy_knowledge/importer.py")
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "knowledge" / "structured"
            target.mkdir(parents=True)
            (target / "hxy-image-understandings-inbox-test.json").write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "asset_id": "hxy-inbox:image",
                                "source_path": "knowledge/raw/inbox/menu.png",
                                "image_type": "menu",
                                "visual_summary": "菜单图",
                                "business_summary": "草本泡脚菜单",
                                "ocr_text": "荷小悦 草本泡脚",
                                "detected_entities": ["荷小悦", "草本泡脚"],
                                "prices": ["¥68"],
                                "related_domains": ["product"],
                                "confidence": 0.82,
                                "qa_ready": True,
                                "needs_review": False,
                            }
                        ]
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            records = importer.load_image_understanding_records(root, "inbox-test")

        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["image_type"], "menu")
        self.assertEqual(records[0]["prices"], ["¥68"])
        self.assertTrue(records[0]["qa_ready"])

    def test_duplicate_content_assets_keep_path_distinct_ids(self):
        importer = load_module("hxy_knowledge_importer_dupes", "apps/api/hxy_knowledge/importer.py")
        manifest = {
            "run_name": "inbox-test",
            "assets": [
                {
                    "asset_id": "hxy-inbox:same",
                    "relative_path": "knowledge/raw/inbox/a.docx",
                    "file_name": "a.docx",
                    "knowledge_domain": "product",
                    "project_stage": "preparation",
                },
                {
                    "asset_id": "hxy-inbox:same",
                    "relative_path": "knowledge/raw/inbox/b.docx",
                    "file_name": "b.docx",
                    "knowledge_domain": "product",
                    "project_stage": "preparation",
                },
            ],
        }
        search_index = {
            "chunks": [
                {
                    "source_id": "hxy-inbox:same",
                    "chunk_id": "hxy-inbox:same:chunk:1",
                    "chunk_index": 1,
                    "relative_path": "knowledge/raw/inbox/a.docx",
                    "text": "A",
                },
                {
                    "source_id": "hxy-inbox:same",
                    "chunk_id": "hxy-inbox:same:chunk:1",
                    "chunk_index": 1,
                    "relative_path": "knowledge/raw/inbox/b.docx",
                    "text": "B",
                },
            ]
        }

        assets = importer.prepare_asset_records(manifest)
        chunks = importer.prepare_chunk_records(search_index)

        self.assertEqual(len({asset["asset_id"] for asset in assets}), 2)
        self.assertEqual(len({chunk["chunk_id"] for chunk in chunks}), 2)
        self.assertEqual(Counter(asset["source_path"] for asset in assets)["knowledge/raw/inbox/a.docx"], 1)
        self.assertEqual({chunk["asset_id"] for chunk in chunks}, {asset["asset_id"] for asset in assets})

    def test_repository_builds_safe_search_sql(self):
        repo = load_module("hxy_knowledge_repository", "apps/api/hxy_knowledge/repository.py")

        sql, params = repo.build_search_query("泡脚", domain="product", stage="preparation", limit=5)

        self.assertIn("hxy_knowledge_chunks", sql)
        self.assertIn("domain = %s", sql)
        self.assertIn("stage = %s", sql)
        self.assertEqual(params[-3:], ["product", "preparation", 5])

    def test_repository_builds_token_fallback_search_sql(self):
        repo = load_module("hxy_knowledge_repository_token", "apps/api/hxy_knowledge/repository.py")

        sql, params = repo.build_search_query("产品菜单类图片 草本泡脚 复购话术", limit=5)

        self.assertIn(" OR ", sql)
        self.assertIn("content ILIKE %s", sql)
        self.assertGreater(len(params), 3)
        self.assertNotIn(" AND ".join(["content ILIKE %s", "content ILIKE %s"]), sql)

    def test_repository_extracts_strong_store_model_tokens(self):
        repo = load_module("hxy_knowledge_repository_store_model_tokens", "apps/api/hxy_knowledge/repository.py")

        tokens = repo._search_tokens("荷小悦门店模型的关键参数是什么？")

        self.assertIn("门店模型", tokens)
        self.assertIn("关键参数", tokens)
        self.assertLess(tokens.index("门店模型"), tokens.index("门店"))

    def test_repository_search_query_boosts_matching_domain_when_provided(self):
        repo = load_module("hxy_knowledge_repository_domain_boost", "apps/api/hxy_knowledge/repository.py")

        sql, params = repo.build_search_query("荷小悦门店模型的关键参数是什么？", domain_hint="store_model", limit=5)

        self.assertIn("CASE WHEN domain = %s THEN 40 ELSE 0 END", sql)
        self.assertIn("store_model", params)

    def test_repository_normalizes_review_task_question(self):
        repo = load_module("hxy_knowledge_repository_review_normalize", "apps/api/hxy_knowledge/repository.py")

        normalized = repo.normalize_review_question(" 荷小悦的核爆点定位是什么？ ")

        self.assertEqual(normalized, "荷小悦的核爆点定位是什么")

    def test_repository_builds_existing_open_review_task_query(self):
        repo = load_module("hxy_knowledge_repository_review_dedupe_sql", "apps/api/hxy_knowledge/repository.py")

        sql, params = repo.build_existing_open_review_task_query("荷小悦的核爆点定位是什么？")

        self.assertIn("hxy_knowledge_review_tasks", sql)
        self.assertIn("status = 'open'", sql)
        self.assertIn("normalized_question", sql)
        self.assertEqual(params, ["荷小悦的核爆点定位是什么"])

    def test_repository_review_task_dedupe_can_scope_by_reason(self):
        repo = load_module("hxy_knowledge_repository_review_dedupe_reason_sql", "apps/api/hxy_knowledge/repository.py")

        sql, params = repo.build_existing_open_review_task_query(
            "顾客问：清泡调补养有什么区别？",
            reason="training_answer_card_candidate",
        )

        self.assertIn("reason = %s", sql)
        self.assertEqual(params, ["顾客问清泡调补养有什么区别", "training_answer_card_candidate"])

    def test_repository_exposes_clear_run_for_repeatable_imports(self):
        repo = load_module("hxy_knowledge_repository_clear", "apps/api/hxy_knowledge/repository.py")

        self.assertTrue(hasattr(repo.KnowledgeRepository, "clear_run"))
        self.assertTrue(hasattr(repo.KnowledgeRepository, "upsert_image_understandings"))

    def test_scoring_model_penalizes_review_only_images_and_rewards_core_docs(self):
        ingest = load_module("hxy_inbox_ingest_scoring", "scripts/ingest-hxy-inbox-knowledge.py")
        image_extract = ingest.Extracted(
            parser="image_metadata",
            text="图片资料，已记录图像元信息。",
            metadata={"width": 800, "height": 600},
            warnings=["image_ocr_not_run_indexed_by_metadata", "image_ocr_empty_needs_visual_review"],
            status="needs_review",
        )
        doc_extract = ingest.Extracted(
            parser="docx_xml",
            text="荷小悦品牌定位 核心定位 功效泡脚 一人一方 小店模型 复购 " * 40,
            metadata={"paragraph_count": 40},
            warnings=[],
            status="extracted",
        )
        image_classification = {
            "domain": "external",
            "stage": "evergreen",
            "confidence": 0.25,
            "reasons": ["fallback:insufficient_keywords"],
            "secondary_domains": [],
        }
        doc_classification = {
            "domain": "brand",
            "stage": "preparation",
            "confidence": 0.97,
            "reasons": ["explicit:filename:品牌资料"],
            "secondary_domains": ["product", "store_model"],
        }

        image_scores = ingest.score_asset_quality(
            "knowledge/raw/inbox/a.jpg",
            image_extract,
            image_classification,
            duplicate_of=None,
            mtime="2026-06-11T00:00:00+08:00",
        )
        doc_scores = ingest.score_asset_quality(
            "knowledge/raw/inbox/荷小悦_品牌战略汇总.docx",
            doc_extract,
            doc_classification,
            duplicate_of=None,
            mtime="2026-06-11T00:00:00+08:00",
        )

        self.assertIn("overall", image_scores)
        self.assertIn("dimensions", image_scores)
        self.assertLess(image_scores["overall"], 0.5)
        self.assertGreater(doc_scores["overall"], image_scores["overall"])
        self.assertGreaterEqual(doc_scores["dimensions"]["business_value"], 0.7)
        self.assertGreaterEqual(doc_scores["dimensions"]["answerability"], 0.7)

    def test_migration_has_quality_score_columns(self):
        migration = (ROOT / "data" / "migrations" / "002_hxy_knowledge_service.sql").read_text()

        self.assertIn("quality_score", migration)
        self.assertIn("quality_grade", migration)
        self.assertIn("quality_scores_json", migration)

    def test_image_understanding_model_outputs_business_fields(self):
        module = load_module("hxy_image_understanding", "scripts/understand-hxy-images.py")
        asset = {
            "asset_id": "hxy-inbox:image",
            "title": "荷小悦草本泡脚菜单",
            "relative_path": "knowledge/raw/inbox/menu.png",
            "knowledge_domain": "product",
            "project_stage": "preparation",
            "metadata": {"ocr_line_count": 6, "ocr_avg_confidence": 0.98},
            "quality_score": 0.72,
            "quality_grade": "B",
        }
        text = "OCR 识别文本：\n荷小悦\n草本泡脚\n今日现煮\n¥68\n一人一方"

        result = module.understand_image(asset, text)

        self.assertEqual(result["asset_id"], "hxy-inbox:image")
        self.assertEqual(result["image_type"], "menu")
        self.assertIn("草本泡脚", result["business_summary"])
        self.assertIn("product", result["related_domains"])
        self.assertTrue(result["qa_ready"])
        self.assertGreater(result["confidence"], 0.5)
        self.assertIn("荷小悦", result["detected_entities"])

    def test_migration_has_image_understanding_table(self):
        migration = (ROOT / "data" / "migrations" / "005_hxy_image_understanding.sql").read_text()

        self.assertIn("hxy_knowledge_image_understandings", migration)
        self.assertIn("visual_summary", migration)
        self.assertIn("business_summary", migration)

    def test_training_system_migration_defines_sessions_and_manager_indexes(self):
        migration = (ROOT / "data" / "migrations" / "006_hxy_training_system.sql").read_text()

        self.assertIn("hxy_training_sessions", migration)
        self.assertIn("employee_id", migration)
        self.assertIn("store_id", migration)
        self.assertIn("score", migration)
        self.assertIn("needs_retrain", migration)
        self.assertIn("dimensions_json", migration)
        self.assertIn("correction_points_json", migration)
        self.assertIn("idx_hxy_training_sessions_store_created", migration)
        self.assertIn("idx_hxy_training_sessions_employee_created", migration)

    def test_training_system_migration_defines_manager_acceptance_and_metric_links(self):
        migration = (ROOT / "data" / "migrations" / "008_hxy_training_curriculum.sql").read_text()

        self.assertIn("CREATE TABLE IF NOT EXISTS hxy_training_manager_acceptances", migration)
        self.assertIn("session_id", migration)
        self.assertIn("manager_id", migration)
        self.assertIn("accepted", migration)
        self.assertIn("operating_metric_links_json", migration)
        self.assertIn("CREATE TABLE IF NOT EXISTS hxy_training_capability_levels", migration)
        self.assertIn("current_level", migration)
        self.assertIn("accepted_count", migration)
        self.assertIn("hxy_training_sessions", migration)
        self.assertNotIn("htops", migration.lower())
        self.assertNotIn("hetang", migration.lower())

    def test_repository_exposes_training_session_persistence_and_manager_summary(self):
        repo = load_module("hxy_knowledge_repository_training", "apps/api/hxy_knowledge/repository.py")

        self.assertTrue(hasattr(repo.KnowledgeRepository, "save_training_session"))
        self.assertTrue(hasattr(repo.KnowledgeRepository, "training_sessions"))
        self.assertTrue(hasattr(repo.KnowledgeRepository, "training_manager_summary"))
        self.assertTrue(hasattr(repo.KnowledgeRepository, "save_training_manager_acceptance"))
        self.assertTrue(hasattr(repo.KnowledgeRepository, "training_acceptance_evidence"))
        self.assertTrue(hasattr(repo.KnowledgeRepository, "upsert_training_capability_level"))
        self.assertTrue(hasattr(repo.KnowledgeRepository, "training_capability_levels"))
        repository_source = (ROOT / "apps" / "api" / "hxy_knowledge" / "repository.py").read_text()
        training_sessions_block = repository_source[
            repository_source.index("def training_sessions") : repository_source.index("def training_manager_summary")
        ]
        self.assertIn("capability_profile_json", training_sessions_block)
        self.assertIn("adaptive_retrain_plan_json", training_sessions_block)
        self.assertIn("operating_metric_links_json", training_sessions_block)
        acceptance_block = repository_source[
            repository_source.index("def training_acceptance_evidence") : repository_source.index("def training_manager_summary")
        ]
        self.assertIn("required_pass_count", acceptance_block)
        self.assertIn("consecutive_pass_count", acceptance_block)
        self.assertIn("pass_score", acceptance_block)
        self.assertIn('"employee_id": session["employee_id"]', acceptance_block)
        self.assertIn('"store_id": session["store_id"]', acceptance_block)
        self.assertIn('"training_item": session["training_item"]', acceptance_block)
        self.assertIn("hxy_training_capability_levels", repository_source)
        self.assertIn("ON CONFLICT", repository_source)
        self.assertIn("def training_capability_levels", repository_source)

    def test_training_manager_summary_builds_operating_issue_signal(self):
        repo = load_module("hxy_knowledge_repository_training_issue", "apps/api/hxy_knowledge/repository.py")

        self.assertTrue(hasattr(repo, "build_training_operating_issue_signal"))
        signal = repo.build_training_operating_issue_signal(
            store_id="store-001",
            days=7,
            retrain_count=3,
            top_mistakes=[
                {"mistake": "不能承诺治疗、治愈、保证或肯定有效，只能表达放松、改善体验和状态建议。", "count": 3}
            ],
        )

        self.assertTrue(signal["should_create_issue"])
        self.assertEqual(signal["priority"], "high")
        self.assertIn("话术复训", signal["title"])
        self.assertIn("治疗", signal["reason"])

    def test_training_manager_summary_builds_operating_impact_signals(self):
        repo = load_module("hxy_knowledge_repository_training_impact", "apps/api/hxy_knowledge/repository.py")

        self.assertTrue(hasattr(repo, "build_training_operating_impact_signals"))
        signals = repo.build_training_operating_impact_signals(
            days=7,
            retrain_count=3,
            low_score_employees=[
                {"employee_id": "emp-001", "employee_name": "小悦", "average_score": 62, "retrain_count": 2}
            ],
            top_mistakes=[
                {"mistake": "不能承诺治疗、治愈、保证或肯定有效，只能表达放松和状态建议。", "count": 2}
            ],
        )

        self.assertGreaterEqual(len(signals), 2)
        metrics = {item["metric"] for item in signals}
        self.assertIn("调补养占比", metrics)
        self.assertIn("投诉风险", metrics)
        for item in signals:
            self.assertIn(item["risk_level"], {"low", "medium", "high"})
            self.assertIn("training_signal", item)
            self.assertIn("next_action", item)

    def test_okf_loader_parses_lifecycle_frontmatter_and_relationships(self):
        okf = load_module("hxy_okf", "apps/api/hxy_knowledge/okf.py")
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            concept = root / "core" / "qingpao.md"
            concept.parent.mkdir(parents=True)
            concept.write_text(
                """---
type: operating_claim
title: 清泡调补养如何向顾客解释
domain: product_system
status: approved
confidence: 0.82
last_confirmed: 2026-06-01
owner: 运营负责人
supersedes:
  - old-qingpao-script-v1
contradicts:
  - old-price-card-v2
used_by:
  - employee_training
  - franchise_pitch
---

清泡是基础放松，调泡按近期状态沟通，补泡强调恢复感，养泡适合长期保养。
""",
                encoding="utf-8",
            )

            docs = okf.load_okf_documents(root, today="2026-06-22")
            summary = okf.summarize_okf_lifecycle(docs, today="2026-06-22")

        self.assertEqual(len(docs), 1)
        doc = docs[0]
        self.assertEqual(doc["version"], "hxy-okf-document.v1")
        self.assertEqual(doc["id"], "core/qingpao")
        self.assertEqual(doc["title"], "清泡调补养如何向顾客解释")
        self.assertEqual(doc["status"], "approved")
        self.assertEqual(doc["confidence"], 0.82)
        self.assertEqual(doc["last_confirmed"], "2026-06-01")
        self.assertEqual(doc["supersedes"], ["old-qingpao-script-v1"])
        self.assertEqual(doc["contradicts"], ["old-price-card-v2"])
        self.assertEqual(doc["used_by"], ["employee_training", "franchise_pitch"])
        self.assertFalse(doc["is_stale"])
        self.assertEqual(summary["version"], "hxy-okf-lifecycle-summary.v1")
        self.assertEqual(summary["total"], 1)
        self.assertEqual(summary["status_counts"]["approved"], 1)
        self.assertEqual(summary["conflict_count"], 1)
        self.assertEqual(summary["low_confidence_count"], 0)

    def test_okf_lifecycle_marks_stale_and_superseded_knowledge(self):
        okf = load_module("hxy_okf_stale", "apps/api/hxy_knowledge/okf.py")
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            (root / "strategy.md").write_text(
                """---
type: decision
title: 旧版招商单店模型
domain: franchise
status: superseded
confidence: 0.44
last_confirmed: 2026-01-01
owner: 创始人
replaced_by: franchise-model-v2
---

旧版招商模型已经被新模型替代。
""",
                encoding="utf-8",
            )

            docs = okf.load_okf_documents(root, today="2026-06-22", stale_after_days=90)
            summary = okf.summarize_okf_lifecycle(docs, today="2026-06-22")

        self.assertTrue(docs[0]["is_stale"])
        self.assertEqual(docs[0]["status"], "superseded")
        self.assertEqual(docs[0]["replaced_by"], ["franchise-model-v2"])
        self.assertEqual(summary["stale_count"], 1)
        self.assertEqual(summary["superseded_count"], 1)
        self.assertEqual(summary["low_confidence_count"], 1)

    def test_operating_issues_prioritize_conflicts_stale_knowledge_and_intake(self):
        issues_module = load_module("hxy_operating_issues", "apps/api/hxy_knowledge/operating_issues.py")
        okf_docs = [
            {
                "id": "core/qingpao",
                "title": "清泡调补养如何向顾客解释",
                "domain": "product_system",
                "status": "disputed",
                "confidence": 0.58,
                "is_stale": False,
                "contradicts": ["old-price-card-v2"],
                "used_by": ["employee_training"],
            },
            {
                "id": "core/franchise-model",
                "title": "招商单店模型",
                "domain": "franchise",
                "status": "approved",
                "confidence": 0.72,
                "is_stale": True,
                "contradicts": [],
                "used_by": ["franchise_pitch"],
            },
        ]

        issues = issues_module.build_operating_issues(okf_docs, today="2026-06-22")
        intake_issue = issues_module.issue_from_intake(
            "员工说清泡可以治疗失眠，需要纠偏并复训",
            scenario="门店员工培训",
            role="运营",
        )

        self.assertGreaterEqual(len(issues), 2)
        self.assertEqual(issues[0]["version"], "hxy-operating-issue.v1")
        self.assertEqual(issues[0]["issue_type"], "口径冲突")
        self.assertEqual(issues[0]["priority"], "high")
        self.assertIn("清泡调补养", issues[0]["title"])
        self.assertEqual(issues[0]["memory_target"], "training_card")
        self.assertIn("复核", " ".join(issues[0]["next_actions"]))
        visible_issue_text = " ".join(
            " ".join([issue.get("evidence_gap", ""), issue.get("risk_boundary", ""), *issue.get("next_actions", [])])
            for issue in issues
        )
        self.assertNotIn("last_confirmed", visible_issue_text)
        self.assertNotIn("confidence", visible_issue_text)
        self.assertEqual(intake_issue["issue_type"], "员工训练纠偏")
        self.assertEqual(intake_issue["domain"], "training")
        self.assertEqual(intake_issue["priority"], "high")
        self.assertIn("治疗", intake_issue["risk_boundary"])

    def test_enterprise_governance_lint_blocks_reference_approval_and_scores_quality(self):
        governance = load_module("hxy_enterprise_governance", "apps/api/hxy_knowledge/enterprise_governance.py")
        assets = [
            {
                "asset_id": "asset-reference",
                "title": "外部 LLM Wiki 方法论",
                "source_path": "knowledge/raw/inbox/wechat-articles/llm-wiki/article.md",
                "domain": "external",
                "stage": "evergreen",
                "status": "reference",
                "quality_score": 0.83,
                "quality_grade": "A",
                "metadata": {"source_type": "external_article"},
            },
            {
                "asset_id": "asset-approved",
                "title": "荷小悦是什么",
                "source_path": "knowledge/okf/core/hxy-positioning.md",
                "domain": "brand",
                "stage": "preparation",
                "status": "approved",
                "quality_score": 0.91,
                "quality_grade": "A",
                "metadata": {"owner": "品牌负责人", "sources": ["source-a"]},
            },
        ]
        claims = [
            {
                "claim_id": "claim-no-owner",
                "claim_type": "brand_positioning",
                "claim": "荷小悦是社区轻恢复品牌",
                "status": "current_candidate",
                "confidence": 0.62,
                "evidence_ids": [],
                "needs_validation": True,
            },
            {
                "claim_id": "claim-risky",
                "claim_type": "product_service",
                "claim": "清泡可以治疗失眠，保证有效",
                "status": "current_candidate",
                "confidence": 0.78,
                "evidence_ids": ["e1"],
                "needs_validation": False,
            },
        ]
        evidence = [
            {"evidence_id": "e1", "source_id": "asset-reference", "snippet": "外部文章方法论"},
        ]
        answer_cards = [
            {
                "card_id": "card-reference",
                "question_pattern": "LLM Wiki 能不能直接作为荷小悦结论？",
                "status": "approved",
                "intent": "knowledge_governance",
                "evidence": [{"asset_id": "asset-reference", "status": "reference"}],
            }
        ]

        report = governance.build_enterprise_governance_report(
            assets=assets,
            claims=claims,
            evidence=evidence,
            relations=[],
            answer_cards=answer_cards,
            okf_documents=[
                {
                    "id": "core/bad-approved",
                    "title": "缺负责人 OKF",
                    "status": "approved",
                    "owner": "未指定",
                    "last_confirmed": "",
                    "evidence": ["source-a"],
                }
            ],
            today="2026-06-27",
        )

        self.assertEqual(report["version"], "hxy-enterprise-knowledge-governance.v1")
        self.assertEqual(report["summary"]["asset_count"], 2)
        self.assertEqual(report["summary"]["claim_count"], 2)
        self.assertGreaterEqual(report["summary"]["blocking_issue_count"], 2)
        self.assertLess(report["quality_score"], 1.0)
        issue_codes = {item["code"] for item in report["lint_issues"]}
        self.assertIn("reference_used_as_approved_source", issue_codes)
        self.assertIn("claim_missing_evidence", issue_codes)
        self.assertIn("claim_overclaim_risk", issue_codes)
        self.assertIn("okf_approved_missing_owner", issue_codes)
        self.assertIn("okf_approved_missing_last_confirmed", issue_codes)
        self.assertFalse(report["release_gate"]["can_publish"])
        self.assertIn("approved", report["release_gate"]["blocked_statuses"])
        action_types = {item["action_type"] for item in report["evolution_actions"]}
        self.assertIn("create_review_task", action_types)
        self.assertIn("draft_answer_card_revision", action_types)
        self.assertIn("downgrade_to_reference", action_types)
        self.assertIn("review_task_drafts", report)
        self.assertGreaterEqual(len(report["review_task_drafts"]), 1)
        self.assertEqual(report["review_task_drafts"][0]["intent"], "knowledge_governance")
        self.assertEqual(report["issue_summary"]["version"], "hxy-governance-issue-summary.v1")
        self.assertGreaterEqual(report["issue_summary"]["blocking_issue_count"], 2)

    def test_enterprise_governance_keeps_candidate_overclaims_review_only_not_publish_blocking(self):
        governance = load_module("hxy_enterprise_governance_candidate_overclaim", "apps/api/hxy_knowledge/enterprise_governance.py")

        report = governance.build_enterprise_governance_report(
            assets=[],
            claims=[
                {
                    "claim_id": "candidate-risky",
                    "claim": "讨论稿里出现冬病夏治和保证有效，这只能作为待复核候选。",
                    "status": "current_candidate",
                    "confidence": 0.72,
                    "evidence_ids": ["evidence-1"],
                }
            ],
            evidence=[{"evidence_id": "evidence-1"}],
            relations=[],
            answer_cards=[],
            today="2026-06-27",
        )

        issues = [item for item in report["lint_issues"] if item["code"] == "claim_overclaim_risk"]
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]["severity"], "high")
        self.assertFalse(issues[0]["blocks_release"])
        self.assertTrue(report["release_gate"]["can_publish"])
        self.assertEqual(report["summary"]["blocking_issue_count"], 0)
        self.assertIn("draft_answer_card_revision", {item["action_type"] for item in report["evolution_actions"]})

    def test_enterprise_governance_blocks_approved_overclaims_and_process_memory_as_authority(self):
        governance = load_module("hxy_enterprise_governance_approved_overclaim", "apps/api/hxy_knowledge/enterprise_governance.py")

        report = governance.build_enterprise_governance_report(
            assets=[],
            claims=[
                {
                    "claim_id": "approved-risky",
                    "claim": "荷小悦可以保证有效。",
                    "status": "approved",
                    "confidence": 0.92,
                    "evidence_ids": ["evidence-1"],
                }
            ],
            evidence=[{"evidence_id": "evidence-1"}],
            relations=[],
            answer_cards=[
                {
                    "card_id": "card-process-memory",
                    "question_pattern": "品牌表达偏好是什么？",
                    "status": "approved",
                    "evidence": [
                        {
                            "asset_id": "memory-1",
                            "status": "process",
                            "source_type": "process_memory",
                            "official_use_allowed": False,
                        }
                    ],
                }
            ],
            today="2026-06-27",
        )

        blocking_codes = {item["code"] for item in report["lint_issues"] if item.get("blocks_release")}
        self.assertIn("claim_overclaim_risk", blocking_codes)
        self.assertIn("process_memory_used_as_approved_source", blocking_codes)
        self.assertFalse(report["release_gate"]["can_publish"])

    def test_governance_builds_overclaim_correction_packages_for_reviewers(self):
        governance = load_module("hxy_enterprise_governance_overclaim_packages", "apps/api/hxy_knowledge/enterprise_governance.py")
        claim = {
            "claim_id": "claim-risk",
            "claim_type": "brand_positioning",
            "claim": "主色是荷花粉，温柔、治愈、女性化。三伏天可说冬病夏治。",
            "status": "current_candidate",
            "confidence": 0.78,
            "evidence_ids": ["evidence-risk"],
        }

        packages = governance.build_overclaim_correction_packages(
            claims=[claim],
            evidence=[{"evidence_id": "evidence-risk", "title": "荷小悦 品牌策划全案"}],
        )

        self.assertEqual(len(packages), 1)
        package = packages[0]
        self.assertEqual(package["version"], "hxy-overclaim-correction-package.v1")
        self.assertEqual(package["claim_id"], "claim-risk")
        self.assertEqual(package["claim_type"], "brand_positioning")
        self.assertEqual(package["source_evidence_ids"], ["evidence-risk"])
        self.assertEqual(package["source_titles"], ["荷小悦 品牌策划全案"])
        self.assertIn("治愈", package["risk_terms"])
        self.assertIn("冬病夏治", package["risk_terms"])
        self.assertIn("medical_effect", package["risk_types"])
        self.assertIn("治愈", package["risk_excerpt"])
        self.assertEqual(package["promotion_allowed"], False)
        self.assertEqual(package["recommended_action"], "archive_or_reextract")
        self.assertIn("放松", package["safe_expression_suggestion"])
        self.assertIn("不能进入 approved", package["review_notes"][0])

    def test_enterprise_governance_report_includes_overclaim_correction_packages(self):
        governance = load_module("hxy_enterprise_governance_overclaim_report", "apps/api/hxy_knowledge/enterprise_governance.py")

        report = governance.build_enterprise_governance_report(
            assets=[],
            claims=[
                {
                    "claim_id": "candidate-risky",
                    "claim_type": "product_service",
                    "claim": "清泡可以治疗失眠，保证有效。",
                    "status": "current_candidate",
                    "confidence": 0.72,
                    "evidence_ids": ["evidence-1"],
                }
            ],
            evidence=[{"evidence_id": "evidence-1", "title": "产品讨论稿"}],
            relations=[],
            answer_cards=[],
            today="2026-06-27",
        )

        self.assertIn("risk_correction_packages", report)
        self.assertEqual(len(report["risk_correction_packages"]), 1)
        package = report["risk_correction_packages"][0]
        self.assertEqual(package["claim_id"], "candidate-risky")
        self.assertEqual(package["recommended_action"], "archive_or_reextract")
        self.assertFalse(package["promotion_allowed"])
        risk_draft = next(draft for draft in report["review_task_drafts"] if draft["reason"] == "claim_overclaim_risk")
        self.assertEqual(risk_draft["correction_package"]["overclaim_correction_package"]["claim_id"], "candidate-risky")

    def test_enterprise_governance_moves_remediated_overclaims_to_audit_not_active_risk(self):
        governance = load_module("hxy_enterprise_governance_remediated_overclaim", "apps/api/hxy_knowledge/enterprise_governance.py")

        report = governance.build_enterprise_governance_report(
            assets=[],
            claims=[
                {
                    "claim_id": "remediated-risk",
                    "claim_type": "product_service",
                    "claim": "清泡可以治疗失眠，保证有效。",
                    "status": "disputed",
                    "confidence": 0.72,
                    "evidence_ids": ["evidence-1"],
                    "governance_remediation": {
                        "reason": "claim_overclaim_risk",
                        "promotion_allowed": False,
                        "recommended_next_action": "archive_or_reextract",
                    },
                }
            ],
            evidence=[{"evidence_id": "evidence-1", "title": "产品讨论稿"}],
            relations=[],
            answer_cards=[],
            today="2026-06-27",
        )

        self.assertEqual([issue for issue in report["lint_issues"] if issue["code"] == "claim_overclaim_risk"], [])
        self.assertEqual(len(report["risk_correction_packages"]), 0)
        self.assertEqual(len(report["remediated_risk_claims"]), 1)
        self.assertEqual(report["remediated_risk_claims"][0]["claim_id"], "remediated-risk")
        self.assertEqual(report["triage_plan"]["workstreams"][1]["issue_count"], 0)

    def test_incremental_compile_plan_detects_added_changed_deleted_and_dependents(self):
        governance = load_module("hxy_enterprise_governance_incremental", "apps/api/hxy_knowledge/enterprise_governance.py")
        previous_manifest = {
            "assets": [
                {
                    "asset_id": "asset-a",
                    "relative_path": "knowledge/raw/inbox/a.docx",
                    "sha256": "old-a",
                    "normalized_path": "knowledge/normalized/brand/a.md",
                },
                {
                    "asset_id": "asset-b",
                    "relative_path": "knowledge/raw/inbox/b.docx",
                    "sha256": "same-b",
                    "normalized_path": "knowledge/normalized/product/b.md",
                },
                {
                    "asset_id": "asset-c",
                    "relative_path": "knowledge/raw/inbox/c.docx",
                    "sha256": "gone-c",
                    "normalized_path": "knowledge/normalized/store_model/c.md",
                },
            ]
        }
        current_manifest = {
            "assets": [
                {
                    "asset_id": "asset-a",
                    "relative_path": "knowledge/raw/inbox/a.docx",
                    "sha256": "new-a",
                    "normalized_path": "knowledge/normalized/brand/a.md",
                },
                {
                    "asset_id": "asset-b",
                    "relative_path": "knowledge/raw/inbox/b.docx",
                    "sha256": "same-b",
                    "normalized_path": "knowledge/normalized/product/b.md",
                },
                {
                    "asset_id": "asset-d",
                    "relative_path": "knowledge/raw/inbox/d.docx",
                    "sha256": "new-d",
                    "normalized_path": "knowledge/normalized/external/d.md",
                },
            ]
        }
        relations = [
            {"relation_type": "supports", "from_id": "asset-a", "to_id": "claim-a"},
            {"relation_type": "used_by", "from_id": "claim-a", "to_id": "answer-card-a"},
        ]

        plan = governance.build_incremental_compile_plan(
            previous_manifest=previous_manifest,
            current_manifest=current_manifest,
            relations=relations,
        )

        self.assertEqual(plan["version"], "hxy-incremental-compile-plan.v1")
        self.assertEqual(plan["summary"]["added"], 1)
        self.assertEqual(plan["summary"]["changed"], 1)
        self.assertEqual(plan["summary"]["deleted"], 1)
        self.assertEqual(plan["summary"]["unchanged"], 1)
        self.assertEqual({item["asset_id"] for item in plan["added"]}, {"asset-d"})
        self.assertEqual({item["asset_id"] for item in plan["changed"]}, {"asset-a"})
        self.assertEqual({item["asset_id"] for item in plan["deleted"]}, {"asset-c"})
        stages = {task["stage"] for task in plan["tasks"]}
        self.assertIn("extract", stages)
        self.assertIn("compile_claims", stages)
        self.assertIn("rebuild_relations", stages)
        self.assertIn("lint", stages)
        affected_ids = {item["id"] for item in plan["affected_nodes"]}
        self.assertIn("claim-a", affected_ids)
        self.assertIn("answer-card-a", affected_ids)

    def test_enterprise_governance_distinguishes_compiled_memory_layers(self):
        governance = load_module("hxy_enterprise_governance_layers", "apps/api/hxy_knowledge/enterprise_governance.py")
        layers = governance.classify_memory_layer(
            [
                {"status": "raw", "source_path": "knowledge/raw/inbox/a.pdf"},
                {"status": "reference", "source_path": "knowledge/normalized/external/a.md"},
                {"status": "current_candidate", "claim_id": "claim-a"},
                {"status": "approved", "card_id": "card-a"},
                {"status": "action_asset", "card_type": "training_card"},
            ]
        )

        self.assertEqual(layers["version"], "hxy-memory-layer-classification.v1")
        self.assertEqual(layers["counts"]["L0_raw_material"], 1)
        self.assertEqual(layers["counts"]["L1_structured_extract"], 1)
        self.assertEqual(layers["counts"]["L2_candidate_claim"], 1)
        self.assertEqual(layers["counts"]["L3_approved_knowledge"], 1)
        self.assertEqual(layers["counts"]["L4_action_asset"], 1)
        self.assertEqual(layers["policy"]["direct_answer_allowed"], ["L3_approved_knowledge", "L4_action_asset"])
        self.assertIn("L1_structured_extract", layers["policy"]["requires_review"])

    def test_build_file_manifest_hashes_raw_materials_with_stable_ids(self):
        governance = load_module("hxy_enterprise_governance_manifest", "apps/api/hxy_knowledge/enterprise_governance.py")

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            raw = root / "knowledge" / "raw" / "inbox"
            raw.mkdir(parents=True)
            (raw / "brand.md").write_text("荷小悦品牌定位", encoding="utf-8")
            (raw / "notes.tmp").write_text("ignore me", encoding="utf-8")
            nested = raw / "external"
            nested.mkdir()
            (nested / "method.md").write_text("外部方法论参考", encoding="utf-8")

            manifest = governance.build_file_manifest(
                raw,
                root_dir=root,
                today="2026-06-27",
                ignore_globs=["*.tmp"],
            )

        self.assertEqual(manifest["version"], "hxy-file-manifest.v1")
        self.assertEqual(manifest["generated_at"], "2026-06-27")
        self.assertEqual(manifest["summary"]["asset_count"], 2)
        self.assertEqual(manifest["summary"]["ignored_count"], 1)
        paths = [item["relative_path"] for item in manifest["assets"]]
        self.assertEqual(paths, ["knowledge/raw/inbox/brand.md", "knowledge/raw/inbox/external/method.md"])
        for asset in manifest["assets"]:
            self.assertTrue(asset["asset_id"].startswith("hxy-file:"))
            self.assertEqual(len(asset["sha256"]), 64)
            self.assertEqual(asset["status"], "raw")
            self.assertEqual(asset["memory_layer"], "L0_raw_material")

    def test_okf_frontmatter_lint_blocks_approved_knowledge_without_governance_fields(self):
        governance = load_module("hxy_enterprise_governance_okf_lint", "apps/api/hxy_knowledge/enterprise_governance.py")
        documents = [
            {
                "id": "core/hxy-positioning",
                "title": "荷小悦定位",
                "domain": "brand",
                "status": "approved",
                "confidence": 0.82,
                "last_confirmed": "",
                "owner": "未指定",
                "evidence": ["source-a"],
                "body": "荷小悦是社区轻恢复品牌。",
            },
            {
                "id": "product/qingpao",
                "title": "清泡",
                "domain": "product",
                "status": "approved",
                "confidence": 0.88,
                "last_confirmed": "2026-06-01",
                "owner": "产品负责人",
                "evidence": ["source-b"],
                "body": "清泡用于日常放松，不承诺治疗。",
            },
        ]

        issues = governance.lint_okf_documents(documents)

        self.assertEqual({item["code"] for item in issues}, {"okf_approved_missing_owner", "okf_approved_missing_last_confirmed"})
        self.assertTrue(all(item["blocks_release"] for item in issues))
        self.assertEqual({item["target_id"] for item in issues}, {"core/hxy-positioning"})

    def test_build_governance_run_package_combines_manifest_plan_report_and_persistence_payload(self):
        governance = load_module("hxy_enterprise_governance_run_package", "apps/api/hxy_knowledge/enterprise_governance.py")

        previous_manifest = {
            "assets": [
                {"asset_id": "hxy-file:old", "relative_path": "knowledge/raw/inbox/old.md", "sha256": "old"},
            ]
        }
        current_manifest = {
            "assets": [
                {"asset_id": "hxy-file:old", "relative_path": "knowledge/raw/inbox/old.md", "sha256": "new"},
            ]
        }
        report = governance.build_enterprise_governance_report(
            assets=[
                {
                    "asset_id": "asset-approved",
                    "title": "荷小悦是什么",
                    "status": "approved",
                    "metadata": {"owner": "品牌负责人", "sources": ["source-a"]},
                }
            ],
            claims=[],
            evidence=[],
            relations=[],
            answer_cards=[],
            today="2026-06-27",
        )

        package = governance.build_governance_run_package(
            run_id="governance-2026-06-27",
            previous_manifest=previous_manifest,
            current_manifest=current_manifest,
            governance_report=report,
            relations=[],
            today="2026-06-27",
        )

        self.assertEqual(package["version"], "hxy-governance-run-package.v1")
        self.assertEqual(package["run_id"], "governance-2026-06-27")
        self.assertEqual(package["summary"]["changed_assets"], 1)
        self.assertEqual(package["summary"]["blocking_issues"], 0)
        self.assertEqual(package["release_gate"]["can_publish"], True)
        self.assertIn("incremental_compile_plan", package)
        self.assertIn("governance_report", package)
        self.assertIn("review_task_drafts", package)
        self.assertEqual(
            package["recommended_persistence"],
            {
                "manifest_path": "knowledge/reports/governance-2026-06-27/manifest.json",
                "plan_path": "knowledge/reports/governance-2026-06-27/incremental-plan.json",
                "report_path": "knowledge/reports/governance-2026-06-27/governance-report.json",
                "package_path": "knowledge/reports/governance-2026-06-27/run-package.json",
            },
        )

    def test_governance_review_task_drafts_turn_blocking_issues_into_actionable_review_payloads(self):
        governance = load_module("hxy_enterprise_governance_review_tasks", "apps/api/hxy_knowledge/enterprise_governance.py")
        report = {
            "version": "hxy-enterprise-knowledge-governance.v1",
            "lint_issues": [
                {
                    "code": "claim_missing_evidence",
                    "severity": "high",
                    "target_type": "claim",
                    "target_id": "claim-a",
                    "message": "候选主张缺少证据。",
                    "action": "补齐 evidence_ids。",
                    "blocks_release": True,
                },
                {
                    "code": "business_material_still_reference",
                    "severity": "medium",
                    "target_type": "asset",
                    "target_id": "asset-b",
                    "message": "关键业务资料仍是参考态。",
                    "action": "编译为候选主张。",
                    "blocks_release": False,
                },
                {
                    "code": "claim_missing_evidence",
                    "severity": "high",
                    "target_type": "claim",
                    "target_id": "claim-a",
                    "message": "候选主张缺少证据。",
                    "action": "补齐 evidence_ids。",
                    "blocks_release": True,
                },
            ],
        }

        drafts = governance.build_governance_review_task_drafts(report, run_id="governance-run")

        self.assertEqual(len(drafts), 2)
        first = drafts[0]
        self.assertEqual(first["version"], "hxy-governance-review-task-draft.v1")
        self.assertEqual(first["intent"], "knowledge_governance")
        self.assertEqual(first["reason"], "claim_missing_evidence")
        self.assertEqual(first["priority"], "high")
        self.assertIn("claim-a", first["question"])
        self.assertEqual(first["correction_package"]["version"], "hxy-governance-correction-package.v1")
        self.assertEqual(first["correction_package"]["source_run_id"], "governance-run")
        self.assertEqual(first["correction_package"]["normalized_question"], "知识治理复核claimclaim-a")
        self.assertEqual(first["correction_package"]["target_id"], "claim-a")
        self.assertEqual(first["correction_package"]["recommended_reviewer"], "知识管理员/业务负责人")
        self.assertIn("补齐 evidence_ids", " ".join(first["correction_package"]["recommended_actions"]))
        self.assertTrue(first["correction_package"]["requires_human_approval"])
        self.assertEqual(first["dedupe_key"], "knowledge_governance:claim_missing_evidence:claim:claim-a")
        self.assertEqual(drafts[1]["priority"], "medium")

    def test_governance_review_task_drafts_prioritize_risk_and_batch_low_confidence(self):
        governance = load_module("hxy_enterprise_governance_review_task_priority", "apps/api/hxy_knowledge/enterprise_governance.py")
        report = {
            "version": "hxy-enterprise-knowledge-governance.v1",
            "lint_issues": [
                {
                    "code": "claim_low_confidence",
                    "severity": "medium",
                    "target_type": "claim",
                    "target_id": "claim-low-a",
                    "message": "候选主张置信度低。",
                    "action": "补证据、复核或降低召回权重。",
                    "blocks_release": False,
                },
                {
                    "code": "claim_low_confidence",
                    "severity": "medium",
                    "target_type": "claim",
                    "target_id": "claim-low-b",
                    "message": "候选主张置信度低。",
                    "action": "补证据、复核或降低召回权重。",
                    "blocks_release": False,
                },
                {
                    "code": "claim_overclaim_risk",
                    "severity": "high",
                    "target_type": "claim",
                    "target_id": "claim-risk",
                    "message": "候选主张包含医疗、效果或收益过度承诺。",
                    "action": "改写为状态建议/体验表达，并提交合规复核。",
                    "blocks_release": False,
                },
            ],
        }

        drafts = governance.build_governance_review_task_drafts(report, run_id="governance-run")

        self.assertEqual(len(drafts), 2)
        self.assertEqual(drafts[0]["reason"], "claim_overclaim_risk")
        self.assertEqual(drafts[0]["priority"], "high")
        self.assertEqual(drafts[0]["dedupe_key"], "knowledge_governance:claim_overclaim_risk:claim:claim-risk")
        self.assertEqual(drafts[1]["reason"], "claim_low_confidence")
        self.assertEqual(drafts[1]["priority"], "medium")
        self.assertEqual(drafts[1]["dedupe_key"], "knowledge_governance_batch:claim_low_confidence:claim")
        self.assertEqual(drafts[1]["correction_package"]["target_count"], 2)
        self.assertEqual(drafts[1]["correction_package"]["sample_target_ids"], ["claim-low-a", "claim-low-b"])

    def test_governance_issue_summary_groups_issues_into_readable_next_actions(self):
        governance = load_module("hxy_enterprise_governance_issue_summary", "apps/api/hxy_knowledge/enterprise_governance.py")
        issues = [
            {
                "code": "claim_missing_evidence",
                "severity": "high",
                "target_type": "claim",
                "target_id": "claim-a",
                "message": "候选主张缺少证据。",
                "action": "补齐 evidence_ids。",
                "blocks_release": True,
            },
            {
                "code": "claim_missing_evidence",
                "severity": "high",
                "target_type": "claim",
                "target_id": "claim-b",
                "message": "候选主张缺少证据。",
                "action": "补齐 evidence_ids。",
                "blocks_release": True,
            },
            {
                "code": "claim_low_confidence",
                "severity": "medium",
                "target_type": "claim",
                "target_id": "claim-c",
                "message": "候选主张置信度低。",
                "action": "补证据、复核或降低召回权重。",
                "blocks_release": False,
            },
        ]

        summary = governance.summarize_governance_issues(issues, limit=2)

        self.assertEqual(summary["version"], "hxy-governance-issue-summary.v1")
        self.assertEqual(summary["total_issue_count"], 3)
        self.assertEqual(summary["blocking_issue_count"], 2)
        self.assertEqual(summary["top_groups"][0]["code"], "claim_missing_evidence")
        self.assertEqual(summary["top_groups"][0]["count"], 2)
        self.assertEqual(summary["top_groups"][0]["blocking_count"], 2)
        self.assertEqual(summary["top_groups"][0]["sample_targets"], ["claim-a", "claim-b"])
        self.assertIn("补齐 evidence_ids", summary["top_groups"][0]["recommended_action"])
        self.assertEqual(len(summary["next_actions"]), 2)
        self.assertEqual(summary["next_actions"][0]["priority"], "high")

    def test_governance_triage_plan_turns_many_issues_into_focused_workstreams(self):
        governance = load_module("hxy_enterprise_governance_triage", "apps/api/hxy_knowledge/enterprise_governance.py")
        report = {
            "version": "hxy-enterprise-knowledge-governance.v1",
            "lint_issues": [
                {
                    "code": "reference_used_as_approved_source",
                    "severity": "critical",
                    "target_type": "answer_card",
                    "target_id": "card-a",
                    "message": "已批准答案卡引用了未核定参考资料。",
                    "action": "降级复核。",
                    "blocks_release": True,
                },
                {
                    "code": "claim_overclaim_risk",
                    "severity": "high",
                    "target_type": "claim",
                    "target_id": "claim-risk",
                    "message": "候选主张包含医疗、效果或收益过度承诺。",
                    "action": "改写为状态建议/体验表达，并提交合规复核。",
                    "blocks_release": False,
                },
                {
                    "code": "claim_low_confidence",
                    "severity": "medium",
                    "target_type": "claim",
                    "target_id": "claim-low-a",
                    "message": "候选主张置信度低。",
                    "action": "补证据、复核或降低召回权重。",
                    "blocks_release": False,
                },
                {
                    "code": "claim_low_confidence",
                    "severity": "medium",
                    "target_type": "claim",
                    "target_id": "claim-low-b",
                    "message": "候选主张置信度低。",
                    "action": "补证据、复核或降低召回权重。",
                    "blocks_release": False,
                },
            ],
        }

        triage = governance.build_governance_triage_plan(report)

        self.assertEqual(triage["version"], "hxy-governance-triage-plan.v1")
        streams = {item["key"]: item for item in triage["workstreams"]}
        self.assertEqual(streams["release_blockers"]["issue_count"], 1)
        self.assertEqual(streams["risk_review"]["issue_count"], 1)
        self.assertEqual(streams["quality_backlog"]["issue_count"], 2)
        self.assertEqual(streams["quality_backlog"]["task_mode"], "batch")
        self.assertEqual(triage["recommended_sequence"][0], "release_blockers")
        self.assertIn("risk_review", triage["recommended_sequence"])

    def test_process_memory_adapter_classifies_memory_and_adds_governance_fields(self):
        memory = load_module("hxy_process_memory", "apps/api/hxy_knowledge/process_memory.py")

        record = memory.build_process_memory_record(
            "不要再用满电回家这个表达，太抽象。以后品牌表达要口语化、简单、好传播。",
            source="chat",
            actor="founder",
            observed_at="2026-06-27T10:00:00+08:00",
            confidence=0.82,
        )

        self.assertEqual(record["version"], "hxy-process-memory.v1")
        self.assertEqual(record["memory_type"], "rejection")
        self.assertEqual(record["status"], "process")
        self.assertEqual(record["source"], "chat")
        self.assertEqual(record["actor"], "founder")
        self.assertEqual(record["confidence"], 0.82)
        self.assertTrue(record["promotable"])
        self.assertFalse(record["reviewed"])
        self.assertEqual(record["official_use_allowed"], False)
        self.assertEqual(record["governance"]["formal_knowledge_status"], "not_official")
        self.assertEqual(record["governance"]["promotion_required"], True)
        self.assertIn("过程记忆不能直接作为企业正式结论", record["governance"]["usage_boundary"])
        self.assertTrue(record["memory_id"].startswith("hxy-process-memory:"))

    def test_process_memory_adapter_covers_core_memory_types(self):
        memory = load_module("hxy_process_memory_types", "apps/api/hxy_knowledge/process_memory.py")

        samples = {
            "preference": "以后荷小悦表达要更口语化，少用抽象战略词。",
            "historical_decision": "历史决策：首店优先做社区店，不先做高端 SPA。",
            "hypothesis": "待验证假设：社区高疲劳人群愿意为草本泡脚加轻恢复付费。",
            "retrospective": "门店复盘：员工讲不清清泡调补养，顾客就难以升级。",
        }

        types = {
            memory.build_process_memory_record(text, source="chat")["memory_type"]
            for text in samples.values()
        }

        self.assertEqual(types, set(samples))

    def test_process_memory_promotion_draft_requires_review_before_official_knowledge(self):
        memory = load_module("hxy_process_memory_promotion", "apps/api/hxy_knowledge/process_memory.py")
        record = memory.build_process_memory_record(
            "待验证假设：清泡调补养是荷小悦核爆点，需要员工复述和用户复述验证。",
            source="strategy_discussion",
            actor="founder",
            observed_at="2026-06-27T10:00:00+08:00",
            confidence=0.76,
        )

        draft = memory.build_memory_promotion_draft(record, target_domain="brand_strategy")

        self.assertEqual(draft["version"], "hxy-memory-promotion-draft.v1")
        self.assertEqual(draft["source_memory_id"], record["memory_id"])
        self.assertEqual(draft["target_domain"], "brand_strategy")
        self.assertEqual(draft["target_status"], "current_candidate")
        self.assertEqual(draft["requires_human_review"], True)
        self.assertEqual(draft["official_use_allowed"], False)
        self.assertIn("不能直接进入 approved", draft["risk_boundary"])
        self.assertEqual(draft["review_task"]["intent"], "process_memory_promotion")
        self.assertEqual(draft["review_task"]["reason"], "promote_process_memory")
        self.assertEqual(draft["review_task"]["priority"], "medium")
        self.assertEqual(
            draft["review_task"]["correction_package"]["normalized_question"],
            f"过程记忆晋升{record['memory_id']}",
        )


if __name__ == "__main__":
    unittest.main()
