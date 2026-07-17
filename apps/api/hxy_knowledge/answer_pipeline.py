from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

REFERENCE_STATUSES = {"external", "reference", "ai_structured", "draft", "needs_review", "disputed", "superseded"}
REFERENCE_STAGES = {"reference", "preparation", "draft", "pilot", "ai_structured"}
PROCESS_MEMORY_STATUSES = {"process"}
COMMERCIAL_PROMISE_TERMS = ["稳赚", "躺赚", "零风险", "一定盈利", "一定回本", "保证回本", "收益保证"]
COMMERCIAL_BOUNDARY_MARKERS = ["不能说", "不要说", "不得说", "不能承诺", "不承诺", "避免", "禁用", "禁止"]
COMMERCIAL_CONDITION_MARKERS = ["必须基于", "假设", "复核", "风险边界", "风险怎么控", "风险怎么控制"]

try:
    from hxy_knowledge.compliance_rules import check_brand_risk_text
    from hxy_knowledge.reliability import (
        OVERCLAIM_TERMS,
        _overclaim_hits,
        classify_answer_authority,
        evidence_authority_source,
        has_corroborated_internal_evidence,
        is_process_memory_evidence as _reliability_is_process_memory_evidence,
    )
    from hxy_knowledge.workbench import classify_workbench_intake
except Exception:  # pragma: no cover - supports direct module loading in tests
    try:
        from compliance_rules import check_brand_risk_text  # type: ignore
    except Exception:
        sibling = Path(__file__).with_name("compliance_rules.py")
        sibling_spec = importlib.util.spec_from_file_location("hxy_compliance_rules_sibling", sibling)
        if sibling_spec and sibling_spec.loader:
            sibling_module = importlib.util.module_from_spec(sibling_spec)
            sibling_spec.loader.exec_module(sibling_module)
            check_brand_risk_text = sibling_module.check_brand_risk_text  # type: ignore
        else:
            def check_brand_risk_text(text: str, *, root_dir: str | None = None) -> dict[str, Any]:  # type: ignore
                return {"status": "ok", "hits": []}

    OVERCLAIM_TERMS = ["治疗", "治愈", "保证", "稳赚", "一定回本", "绝对", "药到病除", "排毒治病"]
    NEGATION_MARKERS = ["不", "不要", "不能", "禁止", "避免", "禁用", "不得", "不要承诺", "不能承诺"]

    def _overclaim_hits(answer: str) -> list[str]:
        if any(marker in answer[:120] for marker in ["不能说", "禁用表达", "避免", "不要说", "不得说", "不能承诺"]):
            return []
        hits: list[str] = []
        for term in OVERCLAIM_TERMS:
            start = 0
            while True:
                index = answer.find(term, start)
                if index == -1:
                    break
                window = answer[max(0, index - 8) : index]
                if not any(marker in window for marker in NEGATION_MARKERS):
                    hits.append(term)
                    break
                start = index + len(term)
        return hits

    reliability_sibling = Path(__file__).with_name("reliability.py")
    reliability_spec = importlib.util.spec_from_file_location("hxy_reliability_sibling", reliability_sibling)
    if not reliability_spec or not reliability_spec.loader:
        raise ImportError("unable to load sibling reliability module")
    reliability_module = importlib.util.module_from_spec(reliability_spec)
    reliability_spec.loader.exec_module(reliability_module)
    classify_answer_authority = reliability_module.classify_answer_authority
    evidence_authority_source = reliability_module.evidence_authority_source
    has_corroborated_internal_evidence = reliability_module.has_corroborated_internal_evidence
    _reliability_is_process_memory_evidence = reliability_module.is_process_memory_evidence

    def classify_workbench_intake(
        input_text: str,
        *,
        scenario: str = "经营问答",
        role: str = "team",
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        combined = f"{input_text} {scenario} {role}"
        primary_workflow = "train" if any(term in combined for term in ["培训", "员工", "店长", "门店员工", "练习", "话术"]) else "ask"
        return {
            "input_type": "question",
            "primary_workflow": primary_workflow,
            "team_value": ["统一口径"],
            "answer_shape": ["结论"],
            "inspector_shape": ["当前理解"],
            "memory_action": "若稳定则沉淀。",
            "next_actions": [],
        }


def _sentence_window(text: str, index: int) -> str:
    left = max(text.rfind("。", 0, index), text.rfind("！", 0, index), text.rfind("？", 0, index), text.rfind("\n", 0, index))
    right_candidates = [pos for pos in [text.find("。", index), text.find("！", index), text.find("？", index), text.find("\n", index)] if pos != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left + 1 : right].strip()


def _is_commercial_boundary(sentence: str, index_in_sentence: int) -> bool:
    before = sentence[max(0, index_in_sentence - 16) : index_in_sentence]
    if any(marker in before for marker in COMMERCIAL_BOUNDARY_MARKERS):
        return True
    return any(marker in sentence for marker in COMMERCIAL_CONDITION_MARKERS)


def _commercial_promise_hits(answer: str) -> list[str]:
    hits: list[str] = []
    for term in COMMERCIAL_PROMISE_TERMS:
        start = 0
        while True:
            index = answer.find(term, start)
            if index == -1:
                break
            sentence = _sentence_window(answer, index)
            index_in_sentence = sentence.find(term)
            if not _is_commercial_boundary(sentence, index_in_sentence):
                hits.append(term)
                break
            start = index + len(term)

    start = 0
    while True:
        index = answer.find("保证", start)
        if index == -1:
            break
        sentence = _sentence_window(answer, index)
        index_in_sentence = sentence.find("保证")
        if ("回本" in sentence or "收益" in sentence) and not _is_commercial_boundary(sentence, index_in_sentence):
            hits.append("保证回本/收益")
            break
        start = index + len("保证")

    return list(dict.fromkeys(hits))


def _risk_flags(question: str, answer: str, scenario: str) -> list[str]:
    policy_text = f"{question} {answer} {scenario}"
    flags: list[str] = []
    if _commercial_promise_hits(answer):
        flags.append("收益承诺")
    if "价格" in policy_text or "政策" in policy_text:
        flags.append("价格政策")
    hits = _overclaim_hits(answer)
    if hits and "夸大表达" not in flags:
        flags.append("夸大表达")
    compliance_hits = check_brand_risk_text(answer).get("hits") or []
    hit_types = {str(hit.get("type") or "") for hit in compliance_hits}
    if "医疗" in hit_types and "医疗功效" not in flags:
        flags.append("医疗功效")
    if ({"保证", "夸大"} & hit_types) and "夸大表达" not in flags:
        flags.append("夸大表达")
    return flags


def _is_approved_answer_card_evidence(item: dict[str, Any]) -> bool:
    if _is_process_memory_evidence(item):
        return False
    domain = str(item.get("domain") or "")
    status = str(item.get("status") or "")
    stage = str(item.get("stage") or "")
    return domain == "approved_answer_card" or status == "approved" and stage == "approved_answer_card"


def _is_process_memory_evidence(item: dict[str, Any]) -> bool:
    return _reliability_is_process_memory_evidence(item)


def _has_reference_only_evidence(evidence: list[dict[str, Any]], from_answer_card: bool) -> bool:
    if from_answer_card:
        return False
    authority_sources = {
        evidence_authority_source(item) for item in evidence if not _is_process_memory_evidence(item)
    }
    if not authority_sources:
        return False
    return not authority_sources & {"official_internal", "internal_material"}


def _has_unapproved_reference_evidence(evidence: list[dict[str, Any]]) -> bool:
    for item in evidence:
        if _is_process_memory_evidence(item):
            continue
        if evidence_authority_source(item) in {
            "approved_answer_card",
            "official_internal",
            "internal_material",
            "system_policy",
        }:
            continue
        status = str(item.get("status") or "").lower()
        stage = str(item.get("stage") or "").lower()
        source_type = str(item.get("source_type") or "").lower()
        if status in REFERENCE_STATUSES or stage in REFERENCE_STAGES or source_type == "reference_material":
            return True
    return False


def _has_conflicting_evidence(evidence: list[dict[str, Any]]) -> bool:
    for item in evidence:
        if _is_process_memory_evidence(item):
            continue
        status = str(item.get("status") or "").lower()
        if status == "disputed" or bool(item.get("conflict")) or bool(item.get("contradicts")):
            return True
    return False


def _evidence_sources(evidence: list[dict[str, Any]], from_answer_card: bool) -> list[str]:
    sources: list[str] = []
    if from_answer_card:
        sources.append("权威答案卡")
    if any(evidence_authority_source(item) == "system_policy" for item in evidence):
        sources.append("系统安全策略")
    domains = {str(item.get("domain") or "") for item in evidence if item.get("domain")}
    if any(_is_process_memory_evidence(item) for item in evidence):
        sources.append("过程记忆")
    if _has_unapproved_reference_evidence(evidence) or _has_reference_only_evidence(evidence, from_answer_card):
        if not sources or sources != ["过程记忆"]:
            sources.append("参考资料")
    elif domains - {"approved_answer_card"}:
        sources.append("知识库检索")
    if not sources:
        sources.append("无稳定证据")
    return sources


def _policy_action(
    *,
    evidence: list[dict[str, Any]],
    confidence: str,
    needs_review: bool,
    from_answer_card: bool,
    risk_flags: list[str],
) -> str:
    if risk_flags:
        return "needs_review"
    if from_answer_card and not needs_review:
        return "answer"
    if _has_reference_only_evidence(evidence, from_answer_card):
        return "needs_review"
    if _has_conflicting_evidence(evidence):
        return "needs_review"
    internal_evidence = [
        item
        for item in evidence
        if evidence_authority_source(item) in {"official_internal", "internal_material"}
    ]
    if internal_evidence and not has_corroborated_internal_evidence(internal_evidence):
        return "needs_review"
    usable_evidence = [item for item in evidence if not _is_process_memory_evidence(item)]
    if not usable_evidence or needs_review or confidence == "low":
        return "needs_review"
    return "answer"


def _guardrail_result(
    *,
    answer: str,
    policy_action: str,
    risk_flags: list[str],
    from_answer_card: bool,
    evidence_has_conflict: bool = False,
    trusted_system_policy: bool = False,
) -> dict[str, Any]:
    findings: list[str] = []
    if "source_path" in answer or "chunk_id" in answer or "knowledge/raw" in answer:
        findings.append("技术痕迹")
    if not trusted_system_policy:
        overclaim_hits = _overclaim_hits(answer)
        if overclaim_hits:
            findings.append(f"高风险表达：{'、'.join(overclaim_hits)}")
        compliance_hits = check_brand_risk_text(answer).get("hits") or []
        compliance_words = [word for hit in compliance_hits for word in (hit.get("words") or [])]
        if compliance_words:
            findings.append(f"高风险表达：{'、'.join(compliance_words)}")
    if evidence_has_conflict:
        findings.append("证据冲突")
    if policy_action != "answer":
        findings.append("需要复核")
    passed = not findings or (from_answer_card and findings == ["需要复核"])
    return {
        "passed": passed,
        "action": "send" if passed else "revise_or_review",
        "findings": findings,
        "risk_flags": risk_flags,
        "rules": [
            "权威答案卡优先于模型生成",
            "资料不足必须说明不足",
            "不得承诺疗效或回本",
            "不得暴露路径、chunk 或内部技术字段",
        ],
    }


def _evolution_actions(
    *,
    policy_action: str,
    guardrail_passed: bool,
    from_answer_card: bool,
    confidence: str,
    needs_review: bool,
) -> list[str]:
    actions: list[str] = ["watch_feedback"]
    if policy_action != "answer" or not guardrail_passed or needs_review:
        actions.append("create_review_task")
    if not from_answer_card and (needs_review or confidence != "high"):
        actions.append("create_answer_card_draft")
    if guardrail_passed and from_answer_card:
        actions.append("track_authority_card_usage")
    return actions


def build_answer_pipeline(
    *,
    question: str,
    scenario: str,
    role: str,
    intent: str,
    answer: str,
    evidence: list[dict[str, Any]],
    confidence: str,
    needs_review: bool,
    from_answer_card: bool,
    model_route: dict[str, Any],
) -> dict[str, Any]:
    frontdoor = classify_workbench_intake(question, scenario=scenario, role=role)
    risk_flags = _risk_flags(question, answer, scenario)
    evidence_has_conflict = _has_conflicting_evidence(evidence)
    reference_only = _has_reference_only_evidence(evidence, from_answer_card)
    process_memory_only = bool(evidence) and all(_is_process_memory_evidence(item) for item in evidence)
    system_policy_boundary = (
        model_route.get("task_type") == "deterministic_risk_boundary"
        and bool(evidence)
        and all(evidence_authority_source(item) == "system_policy" for item in evidence)
    )
    if system_policy_boundary:
        risk_flags = []
    if evidence_has_conflict and "证据冲突" not in risk_flags:
        risk_flags.append("证据冲突")
    policy_action = (
        "answer"
        if system_policy_boundary
        else _policy_action(
            evidence=evidence,
            confidence=confidence,
            needs_review=needs_review,
            from_answer_card=from_answer_card,
            risk_flags=risk_flags,
        )
    )
    evidence_sources = _evidence_sources(evidence, from_answer_card)
    guardrail = _guardrail_result(
        answer=answer,
        policy_action=policy_action,
        risk_flags=risk_flags,
        from_answer_card=from_answer_card,
        evidence_has_conflict=evidence_has_conflict,
        trusted_system_policy=system_policy_boundary,
    )
    authority_contract = classify_answer_authority(
        evidence=evidence,
        from_answer_card=from_answer_card,
        requires_review=policy_action != "answer",
    )
    answer_type = (
        "safety_boundary"
        if system_policy_boundary
        else (
            "authority_answer"
            if from_answer_card
            else (
                "insufficient_answer"
                if policy_action == "needs_review" and confidence == "low" and not reference_only
                else (
                    "context_draft"
                    if policy_action == "needs_review" and process_memory_only
                    else ("reference_draft" if policy_action == "needs_review" and reference_only else "rag_answer")
                )
            )
        )
    )
    loop_contract = {
        "version": "hxy-loop-contract.v1",
        "goal": {
            "text": f"{scenario} · {intent}",
            "measurable_target": "output a usable answer or a review task",
        },
        "context_budget": {
            "evidence_items": len(authority_contract["citations"]),
            "process_memory_items": len(authority_contract["context_metadata"]["process_memory"]),
            "intent": intent,
            "scenario": scenario,
            "role": role,
        },
        "tool_or_agent": {
            "source": "model_router" if model_route.get("should_call_model") else "rules_plus_knowledge",
            "uses_model": bool(model_route.get("should_call_model")),
        },
        "evaluation": {
            "policy_action": policy_action,
            "guardrail_passed": bool(guardrail["passed"]),
            "quality_gate_count": len(guardrail.get("findings") or []),
        },
        "stop_condition": {
            "stop_reason": "answer_ready" if policy_action == "answer" and guardrail["passed"] else "review_required",
            "hard_iteration_limit": 2,
            "max_iterations_reached": False,
            "goal_drift": False,
            "context_overflow": len(evidence) > 8,
        },
    }
    return {
        "version": "hxy-answer-pipeline.v1",
        **authority_contract,
        "loop_contract": loop_contract,
        "frontdoor": {
            "input_type": frontdoor.get("input_type"),
            "primary_workflow": frontdoor.get("primary_workflow"),
            "team_value": frontdoor.get("team_value") or [],
            "answer_shape": frontdoor.get("answer_shape") or [],
        },
        "policy_decision": {
            "action": policy_action,
            "risk_flags": risk_flags,
            "requires_clarification": False,
            "requires_review": policy_action != "answer",
            "constitution": [
                "权威答案卡优先",
                "未核定资料只能生成梳理稿",
                "证据不足不硬答",
                "疗效、收益、价格政策必须保守表达",
                "用户主答案只给可用答案",
            ],
        },
        "evidence_plan": {
            "sources": evidence_sources,
            "evidence_count": len(authority_contract["citations"]),
            "needs_more_evidence": not authority_contract["citations"] or policy_action != "answer",
            "preferred_order": ["权威答案卡", "人工核定", "HXY 参考资料", "图片理解", "经营数据"],
        },
        "answer_builder": {
            "answer_type": answer_type,
            "intent": intent,
            "scenario": scenario,
            "role": role,
            "uses_model": bool(model_route.get("should_call_model")),
        },
        "guardrail_result": guardrail,
        "evolution_actions": _evolution_actions(
            policy_action=policy_action,
            guardrail_passed=bool(guardrail["passed"]),
            from_answer_card=from_answer_card,
            confidence=confidence,
            needs_review=needs_review,
        ),
        "model_route": model_route,
    }
