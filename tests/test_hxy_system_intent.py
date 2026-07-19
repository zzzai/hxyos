from __future__ import annotations

import json
from typing import Any

import pytest

from apps.api.hxy_knowledge.answer_engine import (
    build_task_intent_answer,
    classify_intent,
    classify_task_intent,
)
from apps.api.hxy_knowledge.answer_service import AnswerServiceHooks, generate_answer
from apps.api.hxy_knowledge_api import _classify_frontdoor
from apps.api.hxy_product.conversation_routes import _role_result_envelope


class _Router:
    def __init__(self, output: str | None = None, *, failure: Exception | None = None) -> None:
        self.output = output
        self.failure = failure
        self.generated: list[str] = []

    def route(self, task_type: str) -> dict[str, Any]:
        return {"task_type": task_type, "should_call_model": True}

    def generate(self, task_type: str, **_kwargs: Any) -> dict[str, Any]:
        self.generated.append(task_type)
        if self.failure is not None:
            raise self.failure
        return {
            "used_model": True,
            "output": self.output or "{}",
            "reason": "ok",
        }


class _NoPrivateKnowledgeRepository:
    def __getattr__(self, name: str) -> Any:
        raise AssertionError(f"system intent must not access repository.{name}")


def _hooks() -> AnswerServiceHooks:
    def forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("system intent must short-circuit before knowledge retrieval")

    return AnswerServiceHooks(
        classify_frontdoor=_classify_frontdoor,
        repository_search=forbidden,
        items_need_better_retrieval=forbidden,
        fallback_queries=forbidden,
        answer_from_authority_card=forbidden,
        attach_model_route=forbidden,
        attach_answer_pipeline=forbidden,
        apply_frontdoor_to_answer=forbidden,
        maybe_apply_model_answer=forbidden,
    )


@pytest.mark.parametrize(
    "question",
    ["你会什么", "你能做什么？", "有哪些功能", "你有什么功能", "你能干什么", "能帮我做什么"],
)
def test_capability_equivalents_route_deterministically(question: str) -> None:
    assert classify_task_intent(question) == "system_capability"


def test_business_question_is_not_mistaken_for_system_capability() -> None:
    assert classify_task_intent("泡脚能做什么？") is None


@pytest.mark.parametrize("question", ["会话", "打开会话", "返回对话"])
def test_conversation_navigation_never_routes_to_business_knowledge(question: str) -> None:
    assert classify_task_intent(question) == "conversation_navigation"


def test_conversation_navigation_answer_skips_knowledge_and_governance_language() -> None:
    router = _Router(failure=AssertionError("navigation must not call model"))

    result = generate_answer(
        question="会话",
        scenario="创始人内部决策",
        domain=None,
        stage=None,
        limit=5,
        repository=_NoPrivateKnowledgeRepository(),
        model_router=router,
        hooks=_hooks(),
        role="founder",
        pipeline_role="founder",
    )

    assert result["task_intent"] == "conversation_navigation"
    assert result["answer"] == "这里是工作会话。直接说要推进的事。"
    assert result["needs_review"] is False
    assert result["evidence"] == []
    assert result["actions"] == []
    serialized = json.dumps(result, ensure_ascii=False)
    for forbidden in ("知识库", "权威", "复核", "答案卡", "selected_model", "model_route"):
        assert forbidden not in serialized


def test_medical_efficacy_question_routes_to_risk_boundary() -> None:
    assert classify_intent("泡脚能治疗失眠吗？") == ("risk_boundary", "compliance")


def test_first_store_opening_priority_routes_to_operations_without_model() -> None:
    question = "首店开业前当前最应该先做什么？"
    rule_intent, rule_audience = classify_intent(question)
    router = _Router(failure=AssertionError("clear opening operations question must not call a model"))

    result = _classify_frontdoor(
        model_router=router,
        question=question,
        scenario="创始人内部决策",
        rule_intent=rule_intent,
        rule_audience=rule_audience,
        rule_task_intent=None,
    )

    assert (rule_intent, rule_audience) == ("operations", "operations")
    assert result["intent"] == "operations"
    assert router.generated == []


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("首店开业前选址要看哪些参数？", ("store_model", "founder")),
        ("首店开业前需要准备多少投资？", ("finance", "founder")),
    ],
)
def test_first_store_opening_keeps_explicit_specialist_domain(
    question: str,
    expected: tuple[str, str],
) -> None:
    assert classify_intent(question) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("你都会什么", "system_capability"),
        ("我想上传一份资料", "material_ingestion"),
        ("帮我上传资料", "material_ingestion"),
        ("请帮我练一下接待", "training"),
        ("我想反馈一个门店问题", "issue_reporting"),
    ],
)
def test_common_clear_variants_still_use_deterministic_routing(
    question: str,
    expected: str,
) -> None:
    assert classify_task_intent(question) == expected


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("我要练接待", "training"),
        ("我要上传资料", "material_ingestion"),
        ("我要反馈门店问题", "issue_reporting"),
    ],
)
def test_explicit_work_commands_route_to_product_workflow(question: str, expected: str) -> None:
    assert classify_task_intent(question) == expected


def test_clear_command_does_not_call_model() -> None:
    router = _Router(failure=AssertionError("model must not be called"))

    result = _classify_frontdoor(
        model_router=router,
        question="我要上传资料",
        scenario="门店员工工作问答",
        rule_intent="knowledge_lookup",
        rule_audience="general",
        rule_task_intent="material_ingestion",
    )

    assert result["intent"] == "material_ingestion"
    assert result["primary_workflow"] == "ingest"
    assert router.generated == []


def test_ambiguous_input_uses_semantic_model_classification() -> None:
    router = _Router(
        json.dumps(
            {
                "intent": "training",
                "audience": "store_employee",
                "primary_workflow": "train",
                "confidence": 0.91,
                "reason": "用户希望改善现场表达能力",
            },
            ensure_ascii=False,
        )
    )

    result = _classify_frontdoor(
        model_router=router,
        question="我想把现场表达练得更自然一些",
        scenario="门店员工工作问答",
        rule_intent="knowledge_lookup",
        rule_audience="general",
        rule_task_intent=None,
    )

    assert result["intent"] == "training"
    assert result["mode"] == "ai"
    assert router.generated == ["frontdoor_classification"]


def test_model_failure_falls_back_without_claiming_a_workflow() -> None:
    router = _Router(failure=RuntimeError("provider unavailable"))

    result = _classify_frontdoor(
        model_router=router,
        question="我想把现场表达做得更好",
        scenario="组织内部工作问答",
        rule_intent="knowledge_lookup",
        rule_audience="general",
        rule_task_intent=None,
    )

    assert result["intent"] == "knowledge_lookup"
    assert result["mode"] == "rule_fallback"
    assert router.generated == ["frontdoor_classification"]


def test_model_cannot_turn_an_ordinary_business_question_into_a_workflow() -> None:
    router = _Router(
        json.dumps(
            {
                "intent": "training",
                "audience": "store_employee",
                "primary_workflow": "train",
                "confidence": 0.99,
                "reason": "接待表达相关",
            },
            ensure_ascii=False,
        )
    )

    result = _classify_frontdoor(
        model_router=router,
        question="接待时应该怎么说？",
        scenario="门店员工工作问答",
        rule_intent="knowledge_lookup",
        rule_audience="general",
        rule_task_intent=None,
    )

    assert result["intent"] == "knowledge_lookup"
    assert result["mode"] == "rule_fallback"


def test_capability_answer_skips_private_knowledge_and_review_creation() -> None:
    router = _Router(failure=AssertionError("clear capability question must not call model"))

    result = generate_answer(
        question="你会什么？",
        scenario="门店员工工作问答",
        domain=None,
        stage=None,
        limit=5,
        repository=_NoPrivateKnowledgeRepository(),
        model_router=router,
        hooks=_hooks(),
        role="store_staff",
        pipeline_role="store_staff",
    )

    assert result["task_intent"] == "system_capability"
    assert result["needs_review"] is False
    assert result["evidence"] == []
    assert [item["type"] for item in result["actions"]] == [
        "training",
        "material_upload",
        "issue",
    ]
    serialized = json.dumps(result, ensure_ascii=False)
    for forbidden in ("selected_model", "token", "frontdoor_classification", "model_route"):
        assert forbidden not in serialized


def test_founder_can_start_reception_practice() -> None:
    result = build_task_intent_answer("training", role="founder")

    assert [item["type"] for item in result["actions"]] == ["training"]


def test_product_envelope_keeps_only_actions_allowed_for_the_role() -> None:
    answer = {
        "task_intent": "system_capability",
        "actions": [
            {"type": "training", "label": "开始练接待"},
            {"type": "material_upload", "label": "选择资料"},
            {"type": "tasks", "label": "查看待办"},
        ],
    }

    assert _role_result_envelope("store_employee", answer) == {
        "result_type": "system_capability",
        "actions": [
            {"type": "training", "label": "开始练接待"},
            {"type": "material_upload", "label": "选择资料"},
            {"type": "tasks", "label": "查看待办"},
        ],
    }
    assert _role_result_envelope("system_admin", answer) == {
        "result_type": "system_capability",
        "actions": [],
    }


@pytest.mark.parametrize(
    ("task_intent", "role"),
    [
        ("training", "store_manager"),
        ("issue_reporting", "founder"),
        ("material_ingestion", "system_admin"),
    ],
)
def test_roles_without_workflow_permission_receive_a_truthful_boundary(
    task_intent: str,
    role: str,
) -> None:
    result = build_task_intent_answer(task_intent, role=role)

    assert result["actions"] == []
    assert "当前角色" in result["answer"]
    assert not result["answer"].startswith(("可以", "现在开始"))
