from __future__ import annotations

from typing import Any

try:
    from hxy_knowledge.reliability import OVERCLAIM_TERMS, _overclaim_hits
    from hxy_knowledge.workbench import classify_workbench_intake
except Exception:  # pragma: no cover - supports direct module loading in tests
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


def _risk_flags(question: str, answer: str, scenario: str) -> list[str]:
    text = f"{question} {answer} {scenario}"
    flags: list[str] = []
    if any(term in text for term in ["回本", "收益", "稳赚", "保证"]):
        flags.append("收益承诺")
    if any(term in text for term in ["治疗", "治愈", "药效", "祛病", "排毒治病"]):
        flags.append("医疗功效")
    if "价格" in text or "政策" in text:
        flags.append("价格政策")
    hits = _overclaim_hits(answer)
    if hits and "夸大表达" not in flags:
        flags.append("夸大表达")
    return flags


def _evidence_sources(evidence: list[dict[str, Any]], from_answer_card: bool) -> list[str]:
    sources: list[str] = []
    if from_answer_card:
        sources.append("权威答案卡")
    domains = {str(item.get("domain") or "") for item in evidence if item.get("domain")}
    if "approved_answer_card" in domains and "权威答案卡" not in sources:
        sources.append("权威答案卡")
    if domains - {"approved_answer_card"}:
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
    if from_answer_card and not needs_review:
        return "answer"
    if not evidence or needs_review or confidence == "low":
        return "needs_review"
    if risk_flags and any(flag in risk_flags for flag in ["收益承诺", "医疗功效", "夸大表达"]):
        return "needs_review"
    return "answer"


def _guardrail_result(
    *,
    answer: str,
    policy_action: str,
    risk_flags: list[str],
    from_answer_card: bool,
) -> dict[str, Any]:
    findings: list[str] = []
    if "source_path" in answer or "chunk_id" in answer or "knowledge/raw" in answer:
        findings.append("技术痕迹")
    overclaim_hits = _overclaim_hits(answer)
    if overclaim_hits:
        findings.append(f"高风险表达：{'、'.join(overclaim_hits)}")
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
    policy_action = _policy_action(
        evidence=evidence,
        confidence=confidence,
        needs_review=needs_review,
        from_answer_card=from_answer_card,
        risk_flags=risk_flags,
    )
    evidence_sources = _evidence_sources(evidence, from_answer_card)
    guardrail = _guardrail_result(
        answer=answer,
        policy_action=policy_action,
        risk_flags=risk_flags,
        from_answer_card=from_answer_card,
    )
    answer_type = "authority_answer" if from_answer_card else ("insufficient_answer" if policy_action == "needs_review" and confidence == "low" else "rag_answer")
    loop_contract = {
        "version": "hxy-loop-contract.v1",
        "goal": {
            "text": f"{scenario} · {intent}",
            "measurable_target": "output a usable answer or a review task",
        },
        "context_budget": {
            "evidence_items": len(evidence),
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
                "证据不足不硬答",
                "疗效、收益、价格政策必须保守表达",
                "用户主答案只给可用答案",
            ],
        },
        "evidence_plan": {
            "sources": evidence_sources,
            "evidence_count": len(evidence),
            "needs_more_evidence": not evidence or policy_action != "answer",
            "preferred_order": ["权威答案卡", "HXY 知识库", "图片理解", "经营数据", "人工复核"],
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
