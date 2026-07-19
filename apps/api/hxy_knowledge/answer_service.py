from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .answer_engine import (
    build_deterministic_risk_boundary_answer,
    build_result_card,
    build_task_intent_answer,
    classify_intent,
    classify_task_intent,
    synthesize_answer,
)
from .brand_constitution import BrandConstitutionAdapter
from .reliability import (
    evidence_authority_source,
    insufficient_answer,
    is_process_memory_evidence,
    score_answer_quality,
)
from .thinking_lenses import apply_thinking_lenses
from .understanding_engine import understand_text


@dataclass(frozen=True)
class AnswerServiceHooks:
    classify_frontdoor: Callable[..., dict[str, Any]]
    repository_search: Callable[..., list[dict[str, Any]]]
    items_need_better_retrieval: Callable[[list[dict[str, Any]], str], bool]
    fallback_queries: Callable[[str], list[str]]
    answer_from_authority_card: Callable[..., dict[str, Any]]
    attach_model_route: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    attach_answer_pipeline: Callable[..., dict[str, Any]]
    apply_frontdoor_to_answer: Callable[[dict[str, Any], dict[str, Any]], dict[str, Any]]
    maybe_apply_model_answer: Callable[..., None]


def _apply_authority_contract(answer: dict[str, Any]) -> dict[str, Any]:
    pipeline = answer.get("answer_pipeline")
    if not isinstance(pipeline, dict):
        return answer
    for field in [
        "answer_mode",
        "authority_source",
        "authority_provenance",
        "usage_boundary",
        "citations",
        "context_metadata",
    ]:
        if field in pipeline:
            answer[field] = pipeline[field]
    for field in ["evidence", "sources"]:
        items = answer.get(field)
        if isinstance(items, list):
            answer[field] = [item for item in items if not is_process_memory_evidence(item)]
    policy_decision = pipeline.get("policy_decision")
    if isinstance(policy_decision, dict) and policy_decision.get("action") != "answer":
        answer["needs_review"] = True
        if answer.get("answer_status") != "资料不足":
            answer["answer_status"] = "待复核"
    return answer


def generate_answer(
    *,
    question: str,
    scenario: str,
    domain: str | None,
    stage: str | None,
    limit: int,
    repository: Any,
    model_router: Any,
    hooks: AnswerServiceHooks,
    role: str = "founder",
    pipeline_role: str = "team",
    brand_constitution: BrandConstitutionAdapter | None = None,
    source_asset_id: str | None = None,
) -> dict[str, Any]:
    """Generate and persist one governed answer without binding to an HTTP framework."""
    rule_task_intent = classify_task_intent(question)
    rule_domain_hint, rule_hint_audience = classify_intent(question)
    frontdoor = hooks.classify_frontdoor(
        model_router=model_router,
        question=question,
        scenario=scenario,
        rule_intent=rule_domain_hint,
        rule_audience=rule_hint_audience,
        rule_task_intent=rule_task_intent,
    )
    resolved_task_intent = str(frontdoor.get("intent") or "")
    if resolved_task_intent in {
        "conversation_navigation",
        "system_capability",
        "training",
        "material_ingestion",
        "issue_reporting",
    }:
        return build_task_intent_answer(resolved_task_intent, role=role)

    if brand_constitution is not None and brand_constitution.covers_question(question):
        constitution_answer = brand_constitution.answer_for_brand_identity(role=role)
        if constitution_answer.get("answer_mode") == "formal":
            constitution_answer.update(
                {
                    "question": question,
                    "query": question,
                    "scenario": scenario,
                    "usage": "可作为组织内部统一品牌口径使用。",
                    "applicable_scenarios": [scenario],
                }
            )
            answer_id = repository.save_answer_run(constitution_answer)
            constitution_answer["answer_id"] = answer_id
            return constitution_answer
        constitution_answer.update(
            {
                "question": question,
                "query": question,
                "scenario": scenario,
                "usage": f"仅用于{scenario}中的知识边界提示，不能作为正式品牌口径。",
                "applicable_scenarios": [scenario],
                "from_answer_card": False,
                "reasoning": ["当前没有可验证的生效品牌宪法，系统拒绝用聊天、旧答案卡或检索资料补写正式口径。"],
                "conflicts": ["品牌宪法缺失、失效或完整性校验失败。"],
                "corrections": [],
                "actions": [],
            }
        )
        constitution_answer["result_card"] = build_result_card(
            intent="brand_positioning",
            scenario=scenario,
            answer=constitution_answer["answer"],
            evidence=[],
            confidence="low",
            conflicts=constitution_answer["conflicts"],
            needs_review=True,
        )
        constitution_answer["result_card"]["stability_level"] = "review_required"
        answer_id = repository.save_answer_run(constitution_answer)
        constitution_answer["answer_id"] = answer_id
        return constitution_answer

    understanding = understand_text(question, scenario=scenario, role=role)
    understanding["thinking_lenses"] = apply_thinking_lenses(question, stage="zero_to_one")
    understanding["frontdoor_classification"] = frontdoor
    domain_hint = str(frontdoor.get("intent") or rule_domain_hint)
    allowed_frontdoor_intents = {
        "brand_positioning",
        "product_system",
        "operations",
        "finance",
        "franchise",
        "store_model",
        "knowledge_lookup",
    }
    if domain_hint not in allowed_frontdoor_intents:
        domain_hint = rule_domain_hint

    selected_source_id = str(source_asset_id or "").strip()
    if selected_source_id:
        items = repository.source_evidence(selected_source_id, limit=limit)
    else:
        items = hooks.repository_search(
            repository,
            question,
            domain=domain,
            stage=stage,
            limit=limit,
            domain_hint=domain_hint,
        )
    used_query = question
    usable_items = [item for item in items if not is_process_memory_evidence(item)]
    if not selected_source_id and hooks.items_need_better_retrieval(usable_items, domain_hint):
        for fallback_query in hooks.fallback_queries(question):
            fallback_items = hooks.repository_search(
                repository,
                fallback_query,
                domain=domain,
                stage=stage,
                limit=limit,
                domain_hint=domain_hint,
            )
            usable_fallback_items = [item for item in fallback_items if not is_process_memory_evidence(item)]
            if usable_fallback_items and not hooks.items_need_better_retrieval(usable_fallback_items, domain_hint):
                items = fallback_items
                usable_items = usable_fallback_items
                used_query = fallback_query
                break
            if not usable_items and usable_fallback_items:
                items = fallback_items
                usable_items = usable_fallback_items
                used_query = fallback_query
                break

    intent, _audience = classify_intent(question, usable_items)
    if frontdoor.get("mode") == "ai" and domain_hint != "knowledge_lookup":
        intent = domain_hint
    source_authority_question = selected_source_id and any(
        marker in question for marker in ("正式口径", "正式依据", "权威依据", "直接引用")
    )
    card = None if source_authority_question else repository.find_answer_card(question, intent)
    if card:
        answer = hooks.answer_from_authority_card(
            question=question,
            used_query=used_query,
            scenario=scenario,
            understanding=understanding,
            card=card,
        )
        hooks.attach_model_route(answer, model_router.route("authority_answer"))
        hooks.attach_answer_pipeline(answer, role=pipeline_role)
        _apply_authority_contract(answer)
        answer_id = repository.save_answer_run(answer)
        answer["answer_id"] = answer_id
        return answer

    answer = synthesize_answer(question, used_query, items, scenario=scenario)
    answer["from_answer_card"] = False
    answer["understanding"] = understanding
    hooks.apply_frontdoor_to_answer(answer, frontdoor)
    if source_authority_question:
        authorities = {
            evidence_authority_source(item)
            for item in answer.get("evidence") or []
            if not is_process_memory_evidence(item)
        }
        if "external_reference" in authorities:
            answer["answer"] = (
                "不能直接作为正式口径。这份资料的数据库权威记录是外部参考，"
                "可用于对照和启发；转成荷小悦正式口径前，必须与内部事实核对并由负责人核定。"
            )
        else:
            answer["answer"] = (
                "当前选中资料没有可验证的正式发布授权，不能直接作为正式口径。"
                "请先核对来源权威记录、适用范围和当前版本。"
            )
        answer["needs_review"] = True
        hooks.attach_model_route(
            answer,
            {
                "task_type": "deterministic_source_authority",
                "should_call_model": False,
                "reason": "database_source_authority",
            },
        )
    elif answer.get("intent") == "risk_boundary":
        answer["answer"] = build_deterministic_risk_boundary_answer(question)
        system_policy_evidence = {
            "source_id": "system-policy:medical-claims-boundary:v1",
            "title": "HXYOS 医疗功效表达安全策略",
            "domain": "system_policy",
            "source_type": "system_policy",
            "status": "active",
            "authority_source": "system_policy",
            "authority_recorded": True,
            "authority_version": 1,
            "immutable": True,
        }
        answer["evidence"] = [system_policy_evidence]
        answer["sources"] = [system_policy_evidence]
        answer["confidence"] = "high"
        answer["needs_review"] = False
        answer["answer_status"] = "系统安全边界"
        answer["result_card"] = build_result_card(
            intent="risk_boundary",
            scenario=scenario,
            answer=answer["answer"],
            evidence=[system_policy_evidence],
            confidence="high",
            conflicts=[],
            needs_review=False,
        )
        hooks.attach_model_route(
            answer,
            {
                "task_type": "deterministic_risk_boundary",
                "should_call_model": False,
                "reason": "policy_boundary",
            },
        )
    else:
        hooks.attach_model_route(answer, model_router.route("rag_answer"))
        hooks.maybe_apply_model_answer(model_router=model_router, question=question, answer=answer)
    quality_score = score_answer_quality(
        question=question,
        intent=answer.get("intent") or intent,
        scenario=scenario,
        answer=answer.get("answer") or "",
        evidence=answer.get("evidence") or [],
        confidence=answer.get("confidence") or "low",
        needs_review=bool(answer.get("needs_review", True)),
        from_answer_card=False,
    )
    answer["quality_score"] = quality_score
    answer["quality_dimensions"] = quality_score["dimensions"]
    if (
        quality_score["level"] == "low"
        and bool(answer.get("needs_review", True))
        and answer.get("intent") != "risk_boundary"
    ):
        answer["answer"] = insufficient_answer(question, "当前召回资料没有形成足够稳定的权威结论")
        answer["answer_status"] = "资料不足"
        answer["confidence"] = "low"
        answer["needs_review"] = True
        answer["result_card"] = build_result_card(
            intent=answer.get("intent") or intent,
            scenario=scenario,
            answer=answer["answer"],
            evidence=answer.get("evidence") or [],
            confidence="low",
            conflicts=answer.get("conflicts") or ["证据不足"],
            needs_review=True,
        )
    hooks.attach_answer_pipeline(answer, role=pipeline_role)
    _apply_authority_contract(answer)
    answer_id = repository.save_answer_run(answer)
    answer["answer_id"] = answer_id
    return answer
