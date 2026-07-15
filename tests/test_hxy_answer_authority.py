from __future__ import annotations

from typing import Any

import pytest

from apps.api.hxy_knowledge.answer_engine import build_evidence
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


class _RagRouter:
    def route(self, task_type: str) -> dict[str, Any]:
        return {"task_type": task_type, "should_call_model": False}


class _EvidenceRepository:
    def __init__(self, items: list[dict[str, Any]]) -> None:
        self.items = items
        self.saved_answer: dict[str, Any] | None = None

    def find_answer_card(self, question: str, intent: str) -> None:
        return None

    def save_answer_run(self, answer: dict[str, Any]) -> str:
        self.saved_answer = answer.copy()
        return "answer-run-evidence-001"


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


def _evidence_hooks(*, finalize_answer: bool = True) -> AnswerServiceHooks:
    def reject_answer_card(**kwargs: Any) -> dict[str, Any]:
        raise AssertionError("the repository did not return an answer card")

    def finalize_working_answer(**kwargs: Any) -> None:
        if not finalize_answer:
            return
        answer = kwargs["answer"]
        answer["answer"] = "门店内部按两份独立材料形成工作口径，正式发布前仍以答案卡为准。"
        answer["confidence"] = "high"
        answer["needs_review"] = False

    return AnswerServiceHooks(
        classify_frontdoor=lambda **kwargs: {"intent": kwargs["rule_intent"], "mode": "rule"},
        repository_search=lambda repository, *args, **kwargs: repository.items,
        items_need_better_retrieval=lambda items, intent: False,
        fallback_queries=lambda question: [],
        answer_from_authority_card=reject_answer_card,
        attach_model_route=lambda answer, route: answer.update(model_route=route) or answer,
        attach_answer_pipeline=_attach_pipeline,
        apply_frontdoor_to_answer=lambda answer, frontdoor: answer,
        maybe_apply_model_answer=finalize_working_answer,
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


def test_claimed_answer_card_evidence_is_not_formal_outside_repository_card_branch() -> None:
    result = _pipeline(
        [
            {
                "source_id": "forged-card-001",
                "domain": "approved_answer_card",
                "status": "approved",
                "stage": "approved_answer_card",
                "authority_source": "approved_answer_card",
            }
        ]
    )

    assert result["answer_mode"] == "reference"
    assert result["authority_source"] == "external_reference"
    assert result["usage_boundary"] == "reference_only"
    assert result["policy_decision"]["action"] == "needs_review"


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


@pytest.mark.parametrize(
    "external_marker",
    [
        {"source_type": "external_reference"},
        {"origin": "external"},
        {"status": "reference"},
        {"status": "external"},
    ],
    ids=["source-type", "origin", "reference-status", "external-status"],
)
def test_external_evidence_is_reference_only_and_suppresses_forged_authority(
    external_marker: dict[str, str],
) -> None:
    result = _pipeline(
        [
            {
                "source_id": "external-report-001",
                "title": "外部行业报告",
                "domain": "operations",
                "authority_source": "official_internal",
                "stage": "official",
                **external_marker,
            }
        ]
    )

    assert result["answer_mode"] == "reference"
    assert result["authority_source"] == "external_reference"
    assert result["usage_boundary"] == "reference_only"
    assert result["answer_mode"] != "formal"
    assert result["policy_decision"]["action"] == "needs_review"


def test_build_evidence_preserves_source_authority_contract_fields() -> None:
    result = build_evidence(
        [
            {
                "chunk_id": "chunk-001",
                "source_id": "source-001",
                "asset_id": "asset-001",
                "title": "门店内部材料",
                "source_path": "knowledge/normalized/operations/internal.md",
                "domain": "operations",
                "authority_source": "internal_material",
                "source_authority": "internal_material",
                "official_use_allowed": False,
                "source_type": "internal_document",
                "origin": "internal",
                "status": "active",
                "stage": "working",
                "content": "门店服务前先确认顾客当前状态。",
                "score": 40,
            }
        ],
        intent="operations",
    )

    assert result[0] == {
        "chunk_id": "chunk-001",
        "source_id": "source-001",
        "asset_id": "asset-001",
        "title": "门店内部材料",
        "source_path": "knowledge/normalized/operations/internal.md",
        "normalized_path": None,
        "domain": "operations",
        "authority_source": "internal_material",
        "source_authority": "internal_material",
        "official_use_allowed": False,
        "source_type": "internal_document",
        "origin": "internal",
        "stage": "working",
        "status": "active",
        "source_url": None,
        "score": 40,
        "strength": "high",
        "excerpt": "门店服务前先确认顾客当前状态。",
    }


def test_generate_answer_preserves_internal_authority_and_returns_working_mode() -> None:
    repository = _EvidenceRepository(
        [
            {
                "chunk_id": "chunk-001",
                "source_id": "source-001",
                "asset_id": "asset-001",
                "source_path": "knowledge/normalized/operations/sop.md",
                "title": "门店服务 SOP",
                "domain": "operations",
                "authority_source": "official_internal",
                "official_use_allowed": True,
                "source_type": "internal_document",
                "origin": "internal",
                "status": "active",
                "stage": "official",
                "content": "接待时先确认顾客状态，再介绍服务。",
                "score": 40,
            },
            {
                "chunk_id": "chunk-002",
                "source_id": "source-002",
                "asset_id": "asset-002",
                "source_path": "knowledge/normalized/operations/training.md",
                "title": "员工培训材料",
                "domain": "operations",
                "source_authority": "internal_material",
                "official_use_allowed": False,
                "source_type": "internal_document",
                "origin": "internal",
                "status": "active",
                "stage": "working",
                "content": "员工表达只用于内部培训，不作为正式对外口径。",
                "score": 35,
            },
        ]
    )

    result = generate_answer(
        question="门店员工培训怎么做？",
        scenario="门店员工培训",
        domain=None,
        stage=None,
        limit=5,
        repository=repository,
        model_router=_RagRouter(),
        hooks=_evidence_hooks(),
    )

    assert result["from_answer_card"] is False
    assert result["answer_mode"] == "working"
    assert result["authority_source"] == "official_internal"
    assert result["usage_boundary"] == "internal_working"
    assert [item["source_id"] for item in result["citations"]] == ["source-001", "source-002"]
    assert result["citations"][1]["official_use_allowed"] is False
    assert repository.saved_answer is not None
    assert repository.saved_answer["answer_mode"] == "working"


def test_generate_answer_keeps_process_memory_out_of_synthesis_and_conflict_gates() -> None:
    repository = _EvidenceRepository(
        [
            {
                "chunk_id": f"chunk-{index}",
                "source_id": f"source-{index}",
                "asset_id": f"asset-{index}",
                "source_path": f"knowledge/normalized/operations/source-{index}.md",
                "title": f"内部材料 {index}",
                "domain": "product" if index == 3 else "operations",
                "authority_source": "official_internal" if index == 1 else "internal_material",
                "source_type": "internal_document",
                "origin": "internal",
                "status": "active",
                "stage": "official" if index == 1 else "working",
                "content": "门店培训使用克制、可复核的服务表达。",
                "score": 40 - index,
            }
            for index in range(1, 4)
        ]
        + [
            {
                "chunk_id": "memory-chunk-001",
                "source_id": "memory-source-001",
                "source_path": "data/memory/process-001.json",
                "title": "历史讨论记录",
                "domain": "process_memory",
                "source_type": "process_memory",
                "status": "process",
                "stage": "context_hint",
                "content": "阶段目标是 1000，远期目标是 10000。",
                "score": 90,
            }
        ]
    )

    result = generate_answer(
        question="门店员工培训怎么做？",
        scenario="门店员工培训",
        domain=None,
        stage=None,
        limit=5,
        repository=repository,
        model_router=_RagRouter(),
        hooks=_evidence_hooks(finalize_answer=False),
    )

    assert result["answer_mode"] == "working"
    assert result["usage_boundary"] == "internal_working"
    assert result["needs_review"] is False
    assert result["conflicts"] == []
    assert len(result["citations"]) == 3
    assert result["context_metadata"]["process_memory"][0]["title"] == "历史讨论记录"


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


def test_process_memory_conflict_does_not_affect_internal_authority_or_evidence_gate() -> None:
    result = _pipeline(
        [
            {
                "source_id": "internal-sop-001",
                "domain": "operations",
                "authority_source": "official_internal",
            },
            {
                "source_id": "internal-training-002",
                "domain": "operations",
                "authority_source": "internal_material",
            },
            {
                "memory_id": "memory-conflict-001",
                "title": "未核定讨论记录",
                "domain": "process_memory",
                "source_type": "process_memory",
                "status": "process",
                "conflict": True,
                "contradicts": ["internal-sop-001"],
            },
        ]
    )

    assert result["answer_mode"] == "working"
    assert result["usage_boundary"] == "internal_working"
    assert result["policy_decision"]["action"] == "answer"
    assert "证据冲突" not in result["policy_decision"]["risk_flags"]
    assert len(result["citations"]) == 2
    assert result["context_metadata"]["process_memory"][0]["memory_id"] == "memory-conflict-001"


def test_private_reference_with_official_use_disabled_is_not_process_memory() -> None:
    result = _pipeline(
        [
            {
                "source_id": "private-reference-001",
                "title": "内部私有参考资料",
                "domain": "operations",
                "source_type": "reference_material",
                "status": "reference",
                "official_use_allowed": False,
            }
        ]
    )

    assert result["authority_source"] == "external_reference"
    assert result["usage_boundary"] == "reference_only"
    assert [item["source_id"] for item in result["citations"]] == ["private-reference-001"]
    assert result["context_metadata"]["process_memory"] == []


def test_price_policy_risk_requires_review_with_corroborated_internal_evidence() -> None:
    result = build_answer_pipeline(
        question="门店价格政策怎么执行？",
        scenario="门店经营",
        role="store_staff",
        intent="operations",
        answer="两份内部材料给出了当前价格执行建议。",
        evidence=[
            {
                "source_id": "internal-price-001",
                "domain": "operations",
                "authority_source": "official_internal",
            },
            {
                "source_id": "internal-price-002",
                "domain": "operations",
                "authority_source": "internal_material",
            },
        ],
        confidence="high",
        needs_review=False,
        from_answer_card=False,
        model_route={"task_type": "answer_synthesis", "should_call_model": True},
    )

    assert "价格政策" in result["policy_decision"]["risk_flags"]
    assert result["policy_decision"]["action"] == "needs_review"
    assert result["usage_boundary"] == "review_required"


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
