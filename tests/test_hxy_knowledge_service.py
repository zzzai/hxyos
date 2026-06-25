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
        answer_text = " ".join(card["answer"] for card in cards)
        for unsafe in ["稳赚", "零风险", "一定回本", "药到病除", "包治"]:
            self.assertNotIn(unsafe, answer_text)

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


if __name__ == "__main__":
    unittest.main()
