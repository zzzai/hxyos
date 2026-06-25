from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

try:
    from hxy_knowledge.answer_pipeline import build_answer_pipeline
    from hxy_knowledge.model_router import ModelRouter
    from hxy_knowledge.reliability import _overclaim_hits
except Exception:  # pragma: no cover - supports direct module loading in tests
    def _load_sibling_module(name: str) -> Any:
        path = Path(__file__).resolve().parent / f"{name}.py"
        spec = importlib.util.spec_from_file_location(f"hxy_eval_runner_{name}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"hxy_eval_runner_{name}"] = module
        assert spec and spec.loader
        spec.loader.exec_module(module)
        return module

    build_answer_pipeline = _load_sibling_module("answer_pipeline").build_answer_pipeline
    ModelRouter = _load_sibling_module("model_router").ModelRouter
    _overclaim_hits = _load_sibling_module("reliability")._overclaim_hits


def _normalize_question_pattern(question: str) -> str:
    stop_chars = "，。！？?；;：:、（）()[]【】\"'“”‘’"
    normalized = question or ""
    for char in stop_chars:
        normalized = normalized.replace(char, "")
    return "".join(normalized.split())


def _dimension(key: str, name: str, passed: bool, detail: str) -> dict[str, Any]:
    return {"key": key, "name": name, "passed": passed, "detail": detail}


def _card_by_question(cards: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_question: dict[str, dict[str, Any]] = {}
    for card in cards:
        question_pattern = str(card.get("question_pattern") or "")
        if question_pattern:
            by_question[_normalize_question_pattern(question_pattern)] = card
        for alias in card.get("aliases") or []:
            if alias:
                by_question[_normalize_question_pattern(str(alias))] = card
    return by_question


def _forbidden_term_hits(card: dict[str, Any]) -> list[str]:
    answer = str(card.get("answer") or "")
    hits = list(_overclaim_hits(answer))
    if not hits and any(marker in answer[:120] for marker in ["不能说", "禁用表达", "避免", "不要说", "不得说", "不能承诺"]):
        return []
    for term in card.get("forbidden_terms") or []:
        if term and term in answer and term not in hits:
            hits.append(str(term))
    return hits


def _evaluate_case(question: dict[str, Any], card: dict[str, Any] | None, model_route: dict[str, Any]) -> dict[str, Any]:
    question_text = str(question.get("question") or "")
    if not card:
        dimensions = [
            _dimension("golden_question", "黄金问题存在", bool(question_text), "黄金问题已登记。"),
            _dimension("answer_card", "权威答案卡存在", False, "没有匹配的权威答案卡。"),
            _dimension("forbidden_terms", "禁用表达干净", False, "无法检查答案，缺少答案卡。"),
            _dimension("pipeline_ready", "Answer Pipeline 可控", False, "缺少答案卡，无法进入权威答案链路。"),
        ]
        return {"question": question_text, "passed": False, "dimensions": dimensions}

    forbidden_hits = _forbidden_term_hits(card)
    answer_card_ready = (
        card.get("status") == "approved"
        and str(card.get("review_status") or "").startswith("approved")
        and bool(str(card.get("answer") or "").strip())
        and bool(card.get("role_versions"))
        and bool(card.get("applicable_scenarios"))
    )
    pipeline = build_answer_pipeline(
        question=question_text,
        scenario=(question.get("applicable_scenarios") or ["经营问答"])[0],
        role="team",
        intent=str(card.get("intent") or question.get("intent") or "unknown"),
        answer=str(card.get("answer") or ""),
        evidence=card.get("evidence") or [{"domain": "approved_answer_card", "strength": "high"}],
        confidence="high" if answer_card_ready else "low",
        needs_review=not answer_card_ready,
        from_answer_card=answer_card_ready,
        model_route=model_route,
    )
    pipeline_ready = (
        pipeline.get("policy_decision", {}).get("action") == "answer"
        and pipeline.get("guardrail_result", {}).get("action") == "send"
        and pipeline.get("answer_builder", {}).get("answer_type") == "authority_answer"
    )
    dimensions = [
        _dimension("golden_question", "黄金问题存在", bool(question_text), "黄金问题已登记。"),
        _dimension(
            "answer_card",
            "权威答案卡可用",
            answer_card_ready,
            "答案卡已批准且具备角色版本、场景和答案。" if answer_card_ready else "答案卡未批准或字段不完整。",
        ),
        _dimension(
            "forbidden_terms",
            "禁用表达干净",
            not forbidden_hits,
            "未在答案中发现禁用表达。" if not forbidden_hits else f"答案包含禁用表达：{'、'.join(forbidden_hits)}。",
        ),
        _dimension(
            "pipeline_ready",
            "Answer Pipeline 可控",
            pipeline_ready,
            "权威答案可直接发送。" if pipeline_ready else "Pipeline 要求复核或拦截。",
        ),
    ]
    passed = all(item["passed"] for item in dimensions)
    return {
        "question": question_text,
        "passed": passed,
        "dimensions": dimensions,
        "pipeline": pipeline,
        "card_version": card.get("version") or "",
    }


def run_golden_evals(
    *,
    questions: list[dict[str, Any]],
    cards: list[dict[str, Any]],
    model_router: ModelRouter | None = None,
) -> dict[str, Any]:
    router = model_router or ModelRouter()
    model_route = router.route("offline_eval")
    by_question = _card_by_question(cards)
    cases = [
        _evaluate_case(question, by_question.get(_normalize_question_pattern(str(question.get("question") or ""))), model_route)
        for question in questions
    ]
    pass_count = sum(1 for case in cases if case["passed"])
    total = len(cases)
    fail_count = total - pass_count
    score = round(pass_count / total, 2) if total else 0.0
    return {
        "version": "hxy-eval-runner.v1",
        "suite": "golden_questions",
        "total": total,
        "pass_count": pass_count,
        "fail_count": fail_count,
        "score": score,
        "model_route": model_route,
        "cases": cases,
    }
