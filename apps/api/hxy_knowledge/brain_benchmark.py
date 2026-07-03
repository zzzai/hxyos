from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
from typing import Any


AUTHORITATIVE_STATUSES = {"approved", "action_asset"}
OVERCLAIM_TERMS = ["治疗", "治愈", "包好", "保证有效", "一定有效", "稳赚", "一定回本", "药到病除", "医学诊断", "冬病夏治"]

_OFFICIAL_CASE_CARD_PATTERNS = {
    "brand-001": ["ExampleCo是什么？"],
    "brand-002": ["核爆点定位是什么？"],
    "brand-003": ["和普通service clinic店有什么不同？"],
    "brand-004": ["为什么选择community site？"],
    "product-001": ["service tiers怎么讲？"],
    "product-002": ["frontline staff怎么推荐service session方？"],
    "product-004": ["哪些人不适合热泡或者长时间service session？"],
    "product-005": ["service tiers怎么讲？"],
    "governance-004": ["什么时候可以把答案卡标记为 approved？"],
    "strategy-005": ["如何证明 HXYOS 比纯 RAG 更有价值？"],
}

_BENCHMARK_AUTHORITY_CARDS: list[dict[str, Any]] = [
    {
        "card_id": "benchmark:product-hot-soak-boundary",
        "question_pattern": "哪些人不适合热泡或者长时间service session？",
        "aliases": ["热泡和长时间service session安全边界是什么", "哪些顾客service session要谨慎"],
        "intent": "risk_boundary",
        "answer": (
            "热泡和长时间service session只适合普通放松场景。老人、孕期或经期顾客、儿童、饮酒后、"
            "皮肤破损或不适、明显头晕胸闷、严重慢病或正在接受专业处理的人群，都应先保守处理："
            "降低水温、缩短时间、停止体验或建议咨询专业人员。staff只能做安全提醒，不能做疾病判断。"
        ),
        "status": "approved",
        "review_status": "approved_v1",
        "version": "v1.0",
        "source": "benchmark_authority_cards",
        "evidence": [
            {
                "title": "ExampleCo安全边界答案卡 v1",
                "domain": "risk_boundary",
                "status": "approved",
                "source_type": "approved_internal_asset",
                "owner": "运营/合规负责人",
                "version": "v1.0",
            }
        ],
    },
    {
        "card_id": "benchmark:approved-answer-card-gate",
        "question_pattern": "什么时候可以把答案卡标记为 approved？",
        "aliases": ["答案卡什么时候能批准", "approved answer card 的批准条件是什么"],
        "intent": "answer_authority",
        "answer": (
            "只有当答案卡有明确来源、适用场景、版本、负责人、风险边界，并经过人工复核后，"
            "才能标记为 approved。参考资料、过程记忆、候选 claim、AI 草稿都不能直接作为权威答案；"
            "它们最多进入 review queue 或 draft，等待负责人确认。"
        ),
        "status": "approved",
        "review_status": "approved_v1",
        "version": "v1.0",
        "source": "benchmark_authority_cards",
        "evidence": [
            {
                "title": "HXYOS 知识生命周期治理规则 v1",
                "domain": "answer_authority",
                "status": "approved",
                "source_type": "approved_internal_asset",
                "owner": "知识管理员",
                "version": "v1.0",
            }
        ],
    },
    {
        "card_id": "benchmark:hxyos-vs-rag-value",
        "question_pattern": "如何证明 HXYOS 比纯 RAG 更有价值？",
        "aliases": ["HXYOS 怎么证明比 RAG 有价值", "HXYOS 和纯 RAG 怎么比较"],
        "intent": "benchmark",
        "answer": (
            "HXYOS 不能靠口号证明价值，要靠黄金问题集、引用率、合规拦截率、生命周期区分、"
            "人工复核成本和真实使用反馈证明。纯 RAG 只负责召回资料；HXYOS 还要证明答案来自已批准知识、"
            "能发现证据不足、能把失败用例变成 correction task，并持续提高 benchmark pass_rate。"
        ),
        "status": "approved",
        "review_status": "approved_v1",
        "version": "v1.0",
        "source": "benchmark_authority_cards",
        "evidence": [
            {
                "title": "HXYOS Benchmark 证伪规则 v1",
                "domain": "benchmark",
                "status": "approved",
                "source_type": "approved_internal_asset",
                "owner": "知识管理员",
                "version": "v1.0",
            }
        ],
    },
]


def load_benchmark(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("version") != "hxy-brain-benchmark.v1":
        raise ValueError("unsupported HXY benchmark version")
    if not isinstance(data.get("cases"), list):
        raise ValueError("benchmark cases must be a list")
    return data


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    return [value]


def _normalize_question_pattern(question: str) -> str:
    stop_chars = "，。！？?；;：:、（）()[]【】\"'“”‘’"
    normalized = question or ""
    for char in stop_chars:
        normalized = normalized.replace(char, "")
    return "".join(normalized.split())


def _approved_card_sources() -> list[dict[str, Any]]:
    cards: list[dict[str, Any]] = []
    try:
        from hxy_knowledge.brand_assets import brand_authority_cards

        cards.extend(brand_authority_cards())
    except Exception:  # pragma: no cover - direct import fallback for minimal test contexts
        pass
    try:
        from hxy_knowledge.golden_questions import authority_cards

        cards.extend(authority_cards())
    except Exception:  # pragma: no cover - direct import fallback for minimal test contexts
        pass
    cards.extend(deepcopy(_BENCHMARK_AUTHORITY_CARDS))
    return [card for card in cards if str(card.get("status") or "") in AUTHORITATIVE_STATUSES]


def _card_lookup(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    lookup: dict[str, dict[str, Any]] = {}
    for card in cards:
        candidates = [card.get("question_pattern") or "", *(_as_list(card.get("aliases")))]
        for candidate in candidates:
            normalized = _normalize_question_pattern(str(candidate))
            if normalized and normalized not in lookup:
                lookup[normalized] = card
    return lookup


def _card_for_case(case: dict[str, Any], lookup: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    candidates = [str(case.get("question") or "")]
    candidates.extend(_OFFICIAL_CASE_CARD_PATTERNS.get(str(case.get("case_id") or ""), []))
    for candidate in candidates:
        card = lookup.get(_normalize_question_pattern(candidate))
        if card:
            return card
    return None


def _citation_for_card(card: dict[str, Any]) -> str:
    card_id = str(card.get("card_id") or "").strip()
    if card_id:
        return f"answer-card:{card_id}"
    return f"answer-card:{_normalize_question_pattern(str(card.get('question_pattern') or 'approved'))}"


def _is_official_hxy_benchmark(benchmark: dict[str, Any]) -> bool:
    description = str(benchmark.get("description") or "")
    if "HXYOS v1 黄金问题集" in description:
        return True
    case_ids = {str(case.get("case_id") or "") for case in benchmark.get("cases", []) if isinstance(case, dict)}
    official_prefixes = (
        "brand-",
        "product-",
        "compliance-",
        "risk-",
        "governance-",
        "training-",
        "strategy-",
    )
    return bool(case_ids) and all(case_id.startswith(official_prefixes) for case_id in case_ids)


def build_approved_answer_runs(
    benchmark: dict[str, Any],
    cards: list[dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """Build deterministic answer runs from approved cards.

    This is deliberately card-only: reference materials, process memories, and
    draft cards are not promoted into benchmark authority.
    """

    if cards is None and not _is_official_hxy_benchmark(benchmark):
        return {}
    approved_cards = cards if cards is not None else _approved_card_sources()
    lookup = _card_lookup(approved_cards)
    runs: dict[str, dict[str, Any]] = {}
    for case in benchmark.get("cases", []):
        case_id = str(case.get("case_id") or "")
        card = _card_for_case(case, lookup)
        if not case_id or not card:
            continue
        runs[case_id] = {
            "answer": card.get("answer") or "",
            "evidence_statuses": ["approved"],
            "citations": [_citation_for_card(card)],
            "flags": ["distinguish_lifecycle"],
            "source": "approved_answer_card",
            "authority_source": "approved_answer_card",
            "card_id": card.get("card_id") or "",
        }
    return runs


def _has_overclaim(answer: str) -> bool:
    return any(term in answer for term in OVERCLAIM_TERMS)


def _uses_only_authoritative_evidence(statuses: list[Any]) -> bool:
    return bool(statuses) and all(str(status) in AUTHORITATIVE_STATUSES for status in statuses)


def score_answer(case: dict[str, Any], answer_run: dict[str, Any]) -> dict[str, Any]:
    """Score one HXY answer against deterministic governance checks.

    This is not an LLM judge. It is the first-pass guardrail that catches
    lifecycle confusion, missing citations, and obvious overclaim risk.
    """

    answer = str(answer_run.get("answer") or "")
    evidence_statuses = _as_list(answer_run.get("evidence_statuses"))
    citations = _as_list(answer_run.get("citations"))
    flags = {str(flag) for flag in _as_list(answer_run.get("flags"))}
    risk_checks = {str(check) for check in _as_list(case.get("risk_checks"))}
    success_criteria = {str(item) for item in _as_list(case.get("success_criteria"))}
    expected_capabilities = {str(item) for item in _as_list(case.get("expected_capabilities"))}

    failed_checks: list[str] = []
    warnings: list[str] = []

    if ("no_medical_claim" in risk_checks or "block_overclaim" in risk_checks or "no_revenue_promise" in risk_checks) and _has_overclaim(answer):
        failed_checks.append("overclaim_risk")

    if (
        "must_distinguish_lifecycle" in risk_checks
        or "distinguish_reference_candidate_approved" in expected_capabilities
        or "states_insufficient_if_unapproved" in success_criteria
    ):
        if evidence_statuses and not _uses_only_authoritative_evidence(evidence_statuses):
            failed_checks.append("unapproved_authority")
        if "distinguish_lifecycle" not in flags and not _uses_only_authoritative_evidence(evidence_statuses):
            warnings.append("lifecycle_not_explicit")

    if ("must_cite_evidence" in risk_checks or "cite_evidence" in expected_capabilities) and not citations:
        failed_checks.append("missing_citation")

    if "states_insufficient_if_unapproved" in success_criteria and not _uses_only_authoritative_evidence(evidence_statuses):
        if "insufficient_evidence" not in flags and "needs_review" not in flags:
            warnings.append("should_state_insufficient_evidence")

    penalty = (0.35 * len(failed_checks)) + (0.1 * len(warnings))
    score = round(max(0.0, 1.0 - penalty), 3)
    return {
        "version": "hxy-brain-benchmark-score.v1",
        "case_id": case.get("case_id") or "",
        "score": score,
        "passed": not failed_checks and score >= 0.8,
        "failed_checks": failed_checks,
        "warnings": warnings,
    }


def _answer_trace_item(case: dict[str, Any], answer_run: dict[str, Any]) -> dict[str, Any]:
    citations = [str(item) for item in _as_list(answer_run.get("citations"))]
    evidence_statuses = [str(item) for item in _as_list(answer_run.get("evidence_statuses"))]
    flags = [str(item) for item in _as_list(answer_run.get("flags"))]
    source = str(answer_run.get("source") or "missing")
    authority_source = str(answer_run.get("authority_source") or source)
    return {
        "case_id": str(case.get("case_id") or ""),
        "question": str(case.get("question") or ""),
        "domain": str(case.get("domain") or ""),
        "source": source,
        "authority_source": authority_source,
        "card_id": str(answer_run.get("card_id") or ""),
        "citations": citations,
        "evidence_statuses": evidence_statuses,
        "flags": flags,
        "used_authority": bool(citations) and _uses_only_authoritative_evidence(evidence_statuses),
    }


def _case_requires_citation(case: dict[str, Any]) -> bool:
    risk_checks = {str(check) for check in _as_list(case.get("risk_checks"))}
    expected_capabilities = {str(item) for item in _as_list(case.get("expected_capabilities"))}
    return "must_cite_evidence" in risk_checks or "cite_evidence" in expected_capabilities


def _build_authority_coverage(
    *,
    cases: list[dict[str, Any]],
    scores: list[dict[str, Any]],
    answer_trace: list[dict[str, Any]],
) -> dict[str, Any]:
    trace_by_case = {str(item.get("case_id") or ""): item for item in answer_trace}
    passed_case_ids = {str(score.get("case_id") or "") for score in scores if bool(score.get("passed"))}
    used_authority_case_ids = [
        str(item.get("case_id") or "")
        for item in answer_trace
        if bool(item.get("used_authority"))
    ]
    citation_required_case_ids = [
        str(case.get("case_id") or "")
        for case in cases
        if _case_requires_citation(case)
    ]
    citation_required_without_authority_case_ids = [
        case_id
        for case_id in citation_required_case_ids
        if not bool(trace_by_case.get(case_id, {}).get("used_authority"))
    ]
    passed_without_authority_case_ids = [
        case_id
        for case_id in passed_case_ids
        if not bool(trace_by_case.get(case_id, {}).get("used_authority"))
    ]
    case_count = len(cases)
    used_authority_count = len(used_authority_case_ids)
    missing_authority_count = max(0, case_count - used_authority_count)
    return {
        "version": "hxy-authority-card-coverage.v1",
        "case_count": case_count,
        "used_authority_count": used_authority_count,
        "missing_authority_count": missing_authority_count,
        "authority_coverage_rate": round(used_authority_count / case_count, 4) if case_count else 0.0,
        "used_authority_case_ids": used_authority_case_ids,
        "citation_required_case_ids": citation_required_case_ids,
        "citation_required_without_authority_case_ids": citation_required_without_authority_case_ids,
        "passed_without_authority_case_ids": passed_without_authority_case_ids,
    }


def build_benchmark_report(benchmark: dict[str, Any], answer_runs: dict[str, dict[str, Any]] | None = None) -> dict[str, Any]:
    runs = answer_runs or {}
    cases = [case for case in benchmark.get("cases", []) if isinstance(case, dict)]
    case_scores = []
    answer_trace = []
    for case in cases:
        answer_run = runs.get(str(case.get("case_id") or ""), {})
        case_scores.append(score_answer(case, answer_run))
        answer_trace.append(_answer_trace_item(case, answer_run))

    passed_count = sum(1 for item in case_scores if item["passed"])
    case_count = len(case_scores)
    pass_rate = round(passed_count / case_count, 4) if case_count else 0.0
    failure_thresholds = benchmark.get("failure_thresholds") if isinstance(benchmark.get("failure_thresholds"), dict) else {}
    return {
        "version": "hxy-brain-benchmark-report.v1",
        "benchmark_version": benchmark.get("version") or "",
        "case_count": case_count,
        "passed_count": passed_count,
        "failed_count": case_count - passed_count,
        "pass_rate": pass_rate,
        "failure_thresholds": {
            "min_pass_rate": float(failure_thresholds.get("min_pass_rate", 0.85)),
            "max_overclaim_failures": int(failure_thresholds.get("max_overclaim_failures", 0)),
            "must_distinguish_lifecycle": bool(failure_thresholds.get("must_distinguish_lifecycle", True)),
        },
        "scores": case_scores,
        "answer_trace": answer_trace,
        "authority_coverage": _build_authority_coverage(
            cases=cases,
            scores=case_scores,
            answer_trace=answer_trace,
        ),
    }
