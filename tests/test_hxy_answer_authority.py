from __future__ import annotations

from typing import Any

import pytest

from apps.api.hxy_knowledge.answer_pipeline import build_answer_pipeline
from apps.api.hxy_knowledge.answer_service import AnswerServiceHooks, generate_answer


class _AnswerCardRepository:
    def __init__(self) -> None:
        self.saved_answer: dict[str, Any] | None = None

    def find_answer_card(self, question: str, intent: str) -> dict[str, Any]:
        return {
            "card_id": "card-brand-001",
            "intent": intent,
            "answer": "荷小悦按已批准答案卡中的品牌口径表达。",
        }

    def save_answer_run(self, answer: dict[str, Any]) -> str:
        self.saved_answer = answer.copy()
        return "answer-run-001"


class _AuthorityOnlyRouter:
    def route(self, task_type: str) -> dict[str, Any]:
        assert task_type == "authority_answer"
        return {"task_type": task_type, "should_call_model": False}


def _attach_pipeline(answer: dict[str, Any], *, role: str) -> dict[str, Any]:
    answer["answer_pipeline"] = build_answer_pipeline(
        question=answer["question"],
        scenario=answer["scenario"],
        role=role,
        intent=answer["intent"],
        answer=answer["answer"],
        evidence=answer["evidence"],
        confidence=answer["confidence"],
        needs_review=answer["needs_review"],
        from_answer_card=answer["from_answer_card"],
        model_route=answer["model_route"],
    )
    return answer


def _answer_card_hooks() -> AnswerServiceHooks:
    def answer_from_authority_card(**kwargs: Any) -> dict[str, Any]:
        card = kwargs["card"]
        return {
            "question": kwargs["question"],
            "scenario": kwargs["scenario"],
            "intent": card["intent"],
            "answer": card["answer"],
            "evidence": [
                {
                    "source_id": card["card_id"],
                    "domain": "approved_answer_card",
                    "status": "approved",
                }
            ],
            "confidence": "high",
            "needs_review": False,
            "from_answer_card": True,
        }

    def reject_model_override(**kwargs: Any) -> None:
        raise AssertionError("approved answer cards must not be overridden by a model")

    return AnswerServiceHooks(
        classify_frontdoor=lambda **kwargs: {"intent": kwargs["rule_intent"], "mode": "rule"},
        repository_search=lambda *args, **kwargs: [],
        items_need_better_retrieval=lambda items, intent: False,
        fallback_queries=lambda question: [],
        answer_from_authority_card=answer_from_authority_card,
        attach_model_route=lambda answer, route: answer.update(model_route=route) or answer,
        attach_answer_pipeline=_attach_pipeline,
        apply_frontdoor_to_answer=lambda answer, frontdoor: answer,
        maybe_apply_model_answer=reject_model_override,
    )


def _pipeline(
    evidence: list[dict[str, Any]],
    *,
    answer: str = "内部材料形成了可追溯的工作结论。",
    confidence: str = "high",
    needs_review: bool = False,
) -> dict[str, Any]:
    return build_answer_pipeline(
        question="门店应该如何表达这项服务？",
        scenario="门店员工培训",
        role="store_staff",
        intent="operations",
        answer=answer,
        evidence=evidence,
        confidence=confidence,
        needs_review=needs_review,
        from_answer_card=False,
        model_route={"task_type": "answer_synthesis", "should_call_model": True},
    )


def test_approved_answer_card_returns_formal_contract_without_model_override() -> None:
    repository = _AnswerCardRepository()

    result = generate_answer(
        question="荷小悦是什么？",
        scenario="品牌定位",
        domain=None,
        stage=None,
        limit=5,
        repository=repository,
        model_router=_AuthorityOnlyRouter(),
        hooks=_answer_card_hooks(),
    )

    assert result["answer_mode"] == "formal"
    assert result["authority_source"] == "approved_answer_card"
    assert result["usage_boundary"] == "team_standard"
    assert result["model_route"]["should_call_model"] is False
    assert result["answer_pipeline"]["policy_decision"]["action"] == "answer"


def test_corroborated_internal_evidence_returns_working_contract_with_citations() -> None:
    evidence = [
        {
            "source_id": "internal-sop-001",
            "title": "门店服务 SOP",
            "domain": "operations",
            "authority_source": "official_internal",
        },
        {
            "source_id": "internal-training-002",
            "title": "员工培训材料",
            "domain": "operations",
            "authority_source": "internal_material",
        },
    ]

    result = _pipeline(evidence)

    assert result["answer_mode"] == "working"
    assert result["authority_source"] == "official_internal"
    assert result["usage_boundary"] == "internal_working"
    assert [item["source_id"] for item in result["citations"]] == [
        "internal-sop-001",
        "internal-training-002",
    ]
    assert result["policy_decision"]["action"] == "answer"


def test_external_evidence_is_reference_only_and_never_an_official_answer() -> None:
    result = _pipeline(
        [
            {
                "source_id": "external-report-001",
                "title": "外部行业报告",
                "domain": "external",
                "source_type": "external_reference",
                "authority_source": "approved_answer_card",
                "status": "reference",
            }
        ]
    )

    assert result["answer_mode"] == "reference"
    assert result["authority_source"] == "external_reference"
    assert result["usage_boundary"] == "reference_only"
    assert result["answer_mode"] != "formal"
    assert result["policy_decision"]["action"] == "needs_review"


def test_process_memory_is_context_metadata_not_authority_or_citation() -> None:
    result = _pipeline(
        [
            {
                "memory_id": "memory-001",
                "title": "一次讨论中的表达偏好",
                "domain": "process_memory",
                "source_type": "process_memory",
                "status": "process",
                "official_use_allowed": False,
            }
        ]
    )

    assert result["authority_source"] == "none"
    assert result["usage_boundary"] == "review_required"
    assert result["citations"] == []
    assert result["context_metadata"]["process_memory"] == [
        {
            "memory_id": "memory-001",
            "title": "一次讨论中的表达偏好",
            "context_hint_only": True,
        }
    ]
    assert result["policy_decision"]["action"] == "needs_review"


@pytest.mark.parametrize(
    ("evidence", "answer"),
    [
        ([], "模型非常确信这就是正确答案。"),
        (
            [
                {
                    "source_id": "internal-sop-001",
                    "domain": "operations",
                    "authority_source": "official_internal",
                },
                {
                    "source_id": "internal-sop-002",
                    "domain": "operations",
                    "authority_source": "internal_material",
                },
            ],
            "这项服务保证治愈失眠。",
        ),
    ],
    ids=["insufficient-evidence", "high-risk-expression"],
)
def test_high_risk_or_insufficient_evidence_requires_review_despite_model_confidence(
    evidence: list[dict[str, Any]], answer: str
) -> None:
    result = _pipeline(evidence, answer=answer, confidence="high", needs_review=False)

    assert result["model_route"]["should_call_model"] is True
    assert result["policy_decision"]["action"] == "needs_review"
    assert result["policy_decision"]["requires_review"] is True
    assert result["usage_boundary"] == "review_required"
