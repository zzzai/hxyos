from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from .answer_engine import build_result_card, classify_intent, synthesize_answer
from .reliability import insufficient_answer, score_answer_quality
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
) -> dict[str, Any]:
    """Generate and persist one governed answer without binding to an HTTP framework."""
    understanding = understand_text(question, scenario=scenario, role=role)
    understanding["thinking_lenses"] = apply_thinking_lenses(question, stage="zero_to_one")
    rule_domain_hint, rule_hint_audience = classify_intent(question)
    frontdoor = hooks.classify_frontdoor(
        model_router=model_router,
        question=question,
        scenario=scenario,
        rule_intent=rule_domain_hint,
        rule_audience=rule_hint_audience,
    )
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

    items = hooks.repository_search(
        repository,
        question,
        domain=domain,
        stage=stage,
        limit=limit,
        domain_hint=domain_hint,
    )
    used_query = question
    if hooks.items_need_better_retrieval(items, domain_hint):
        for fallback_query in hooks.fallback_queries(question):
            fallback_items = hooks.repository_search(
                repository,
                fallback_query,
                domain=domain,
                stage=stage,
                limit=limit,
                domain_hint=domain_hint,
            )
            if fallback_items and not hooks.items_need_better_retrieval(fallback_items, domain_hint):
                items = fallback_items
                used_query = fallback_query
                break
            if not items and fallback_items:
                items = fallback_items
                used_query = fallback_query
                break

    intent, _audience = classify_intent(question, items)
    if frontdoor.get("mode") == "ai" and domain_hint != "knowledge_lookup":
        intent = domain_hint
    card = repository.find_answer_card(question, intent)
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
        answer_id = repository.save_answer_run(answer)
        answer["answer_id"] = answer_id
        return answer

    answer = synthesize_answer(question, used_query, items, scenario=scenario)
    answer["from_answer_card"] = False
    answer["understanding"] = understanding
    hooks.apply_frontdoor_to_answer(answer, frontdoor)
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
    if quality_score["level"] == "low" and bool(answer.get("needs_review", True)):
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
    answer_id = repository.save_answer_run(answer)
    answer["answer_id"] = answer_id
    return answer
