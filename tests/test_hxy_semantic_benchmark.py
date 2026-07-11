from __future__ import annotations

import json
from pathlib import Path

from apps.api.hxy_engines.semantic_benchmark import (
    SemanticAnswerRun,
    evaluate_deterministic_semantics,
)


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-engine-benchmark-v1.json"
RUBRIC_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-semantic-rubric-v1.json"
SCHEMA_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-semantic-answer-run-v1.schema.json"


def _payloads() -> tuple[dict, dict]:
    return (
        json.loads(BENCHMARK_PATH.read_text(encoding="utf-8")),
        json.loads(RUBRIC_PATH.read_text(encoding="utf-8")),
    )


def _single_case() -> tuple[dict, dict, dict, dict]:
    benchmark, rubric = _payloads()
    case = benchmark["cases"][0]
    rubric_case = next(item for item in rubric["cases"] if item["case_id"] == case["case_id"])
    benchmark = {**benchmark, "cases": [case]}
    rubric = {**rubric, "cases": [rubric_case]}
    return benchmark, rubric, case, rubric_case


def _passing_run(case: dict, rubric_case: dict, **overrides) -> SemanticAnswerRun:
    formal_answer = case["expected_authority"] == "approved"
    payload = {
        "case_id": case["case_id"],
        "provider_name": "current-hxy-answer-pipeline",
        "provider_version": "v1",
        "answer": "根据当前已核对证据，先确认事实和未验证假设，再安排负责人完成下一步验证。",
        "answer_authority": case["expected_authority"],
        "evidence_ids": (case["allowed_evidence_ids"][0],),
        "evidence_authorities": (
            "approved" if case["expected_authority"] == "approved" else "reference",
        ),
        "citations": (case["allowed_evidence_ids"][0],),
        "declared_outcomes": tuple(rubric_case["required_outcomes"]),
        "policy_action": "answer" if formal_answer else "needs_review",
        "guardrail_action": "send" if formal_answer else "revise_or_review",
        "latency_ms": 1,
    }
    payload.update(overrides)
    return SemanticAnswerRun(**payload)


def test_noop_answer_run_fails_all_cases() -> None:
    benchmark, rubric = _payloads()

    report = evaluate_deterministic_semantics(benchmark, rubric, {})

    assert report["case_count"] == 50
    assert report["deterministic_pass_count"] == 0
    assert report["deterministic_fail_count"] == 50
    assert report["semantic_status"] == "deterministic_only"
    assert report["quality_claim_allowed"] is False


def test_hard_safety_failure_cannot_be_averaged_away() -> None:
    benchmark, rubric, case, rubric_case = _single_case()
    run = _passing_run(
        case,
        rubric_case,
        answer="我们的服务可以治疗失眠，建议直接购买。",
    )

    report = evaluate_deterministic_semantics(
        benchmark,
        rubric,
        {case["case_id"]: run},
    )
    result = report["cases"][0]

    assert result["deterministic_status"] == "failed"
    assert result["hard_gates"]["risk_pattern_clear"] is False


def test_authorized_citations_and_authorities_pass() -> None:
    benchmark, rubric, case, rubric_case = _single_case()
    run = _passing_run(case, rubric_case)

    report = evaluate_deterministic_semantics(
        benchmark,
        rubric,
        {case["case_id"]: run},
    )

    assert report["deterministic_pass_count"] == 1
    assert report["cases"][0]["deterministic_status"] == "passed"


def test_unknown_evidence_and_private_trace_are_redacted() -> None:
    benchmark, rubric, case, rubric_case = _single_case()
    run = _passing_run(
        case,
        rubric_case,
        evidence_ids=("session_grant",),
        evidence_authorities=("reference",),
        citations=("session_grant",),
        safe_trace={"source_path": "/root/hxy/private.txt"},
    )

    report = evaluate_deterministic_semantics(
        benchmark,
        rubric,
        {case["case_id"]: run},
    )
    serialized = json.dumps(report, ensure_ascii=False).lower()

    assert report["cases"][0]["deterministic_status"] == "failed"
    assert report["cases"][0]["evidence_ids"] == []
    assert report["cases"][0]["redacted_evidence_count"] == 1
    assert "session_grant" not in serialized
    assert "/root/hxy" not in serialized


def test_required_outcome_declarations_are_complete() -> None:
    benchmark, rubric, case, rubric_case = _single_case()
    run = _passing_run(case, rubric_case, declared_outcomes=())

    report = evaluate_deterministic_semantics(
        benchmark,
        rubric,
        {case["case_id"]: run},
    )

    assert report["cases"][0]["hard_gates"]["outcome_declarations"] is False


def test_report_never_contains_answer_text_and_schema_is_bounded() -> None:
    benchmark, rubric, case, rubric_case = _single_case()
    secret_answer = "这是只允许存在于私有运行文件的答案。"
    run = _passing_run(case, rubric_case, answer=secret_answer)

    report = evaluate_deterministic_semantics(
        benchmark,
        rubric,
        {case["case_id"]: run},
    )
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    serialized = json.dumps(report, ensure_ascii=False)

    assert secret_answer not in serialized
    assert len(report["cases"][0]["answer_sha256"]) == 64
    assert schema["properties"]["answers"]["items"]["additionalProperties"] is False
    assert "answer" in schema["properties"]["answers"]["items"]["required"]


def test_approved_answer_requires_authoritative_evidence() -> None:
    benchmark, rubric = _payloads()
    case = next(item for item in benchmark["cases"] if item["expected_authority"] == "approved")
    rubric_case = next(item for item in rubric["cases"] if item["case_id"] == case["case_id"])
    benchmark = {**benchmark, "cases": [case]}
    rubric = {**rubric, "cases": [rubric_case]}
    run = _passing_run(
        case,
        rubric_case,
        evidence_authorities=("reference",),
    )

    report = evaluate_deterministic_semantics(benchmark, rubric, {case["case_id"]: run})

    assert report["cases"][0]["hard_gates"]["authority_alignment"] is False


def test_nonapproved_answer_cannot_use_send_delivery_policy() -> None:
    benchmark, rubric, case, rubric_case = _single_case()
    run = _passing_run(
        case,
        rubric_case,
        policy_action="answer",
        guardrail_action="send",
    )

    report = evaluate_deterministic_semantics(benchmark, rubric, {case["case_id"]: run})

    assert report["cases"][0]["hard_gates"]["delivery_policy"] is False
