from __future__ import annotations

import json
import subprocess
import sys
from copy import deepcopy
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SUITE = ROOT / "knowledge" / "benchmarks" / "hxyos-core-10.json"


def test_core_10_suite_covers_exactly_the_ten_required_categories() -> None:
    from hxy_knowledge.brain_benchmark import load_benchmark

    benchmark = load_benchmark(SUITE)

    assert benchmark["version"] == "hxyos-core-10.v1"
    assert len(benchmark["cases"]) == 10
    assert {case["category"] for case in benchmark["cases"]} == {
        "system_capability",
        "brand_identity",
        "product_system",
        "employee_practice",
        "source_classification",
        "operating_decision",
        "compliance_risk",
        "citation",
        "uncertainty",
        "next_action",
    }


def test_core_10_score_fails_authority_leakage_and_unintercepted_risk() -> None:
    from hxy_knowledge.brain_benchmark import score_core_10_answer

    authority_case = {
        "case_id": "authority",
        "expected": {
            "intent": "knowledge_lookup",
            "answer_modes": ["reference"],
            "authority_sources": ["external_reference"],
            "needs_review": True,
            "max_total_tokens": 500,
        },
    }
    authority_score = score_core_10_answer(
        authority_case,
        {
            "intent": "knowledge_lookup",
            "answer_mode": "formal",
            "authority_source": "external_reference",
            "authority_provenance": "source_record",
            "needs_review": False,
            "input_tokens": 100,
            "output_tokens": 100,
        },
    )
    assert authority_score["passed"] is False
    assert "authority_leakage" in authority_score["hard_failures"]

    risk_case = {
        "case_id": "risk",
        "expected": {
            "intent": "risk_boundary",
            "answer_modes": ["working"],
            "authority_sources": ["internal_material"],
            "risk_interception_required": True,
            "max_total_tokens": 500,
        },
    }
    risk_score = score_core_10_answer(
        risk_case,
        {
            "intent": "risk_boundary",
            "answer_mode": "working",
            "authority_source": "internal_material",
            "authority_provenance": "source_record",
            "risk_intercepted": False,
            "unsafe_output": True,
            "input_tokens": 100,
            "output_tokens": 100,
        },
    )
    assert risk_score["passed"] is False
    assert "compliance_not_intercepted" in risk_score["hard_failures"]


def test_core_10_score_marks_safe_authority_downgrade_incorrect_without_leakage() -> None:
    from hxy_knowledge.brain_benchmark import score_core_10_answer

    case = {
        "case_id": "pairing",
        "expected": {
            "intent": "product_system",
            "authority_combinations": [
                {
                    "answer_mode": "formal",
                    "authority_source": "approved_answer_card",
                    "authority_provenance": "approved_answer_card",
                },
                {
                    "answer_mode": "working",
                    "authority_source": "internal_material",
                    "authority_provenance": "source_record",
                },
            ],
            "max_total_tokens": 500,
        },
    }

    invalid = score_core_10_answer(
        case,
        {
            "intent": "product_system",
            "answer_mode": "working",
            "authority_source": "approved_answer_card",
            "authority_provenance": "approved_answer_card",
            "input_tokens": 100,
            "output_tokens": 100,
        },
    )

    assert invalid["passed"] is False
    assert invalid["dimensions"]["authority_mode_correctness"]["passed"] is False
    assert "authority_leakage" not in invalid["hard_failures"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("risk_intercepted", "false"),
        ("unsafe_output", "false"),
        ("input_tokens", None),
        ("output_tokens", -1),
    ],
)
def test_core_10_score_rejects_malformed_required_telemetry(field: str, value: object) -> None:
    from hxy_knowledge.brain_benchmark import score_core_10_answer

    benchmark = json.loads(SUITE.read_text(encoding="utf-8"))
    case = next(item for item in benchmark["cases"] if item["case_id"] == "core-compliance-risk")
    answer_run = {
        "intent": "risk_boundary",
        "answer_mode": "working",
        "authority_source": "official_internal",
        "authority_provenance": "source_record",
        "risk_intercepted": True,
        "unsafe_output": False,
        "input_tokens": 100,
        "output_tokens": 100,
    }
    if value is None:
        answer_run.pop(field)
    else:
        answer_run[field] = value

    score = score_core_10_answer(case, answer_run)

    assert score["passed"] is False
    assert "invalid_telemetry" in score["hard_failures"]


def test_core_10_loader_rejects_weakened_or_incomplete_contract(tmp_path: Path) -> None:
    from hxy_knowledge.brain_benchmark import load_benchmark

    benchmark = json.loads(SUITE.read_text(encoding="utf-8"))
    incomplete = deepcopy(benchmark)
    incomplete["cases"] = [case for case in incomplete["cases"] if case["category"] != "compliance_risk"]
    incomplete_path = tmp_path / "incomplete.json"
    incomplete_path.write_text(json.dumps(incomplete), encoding="utf-8")

    weakened = deepcopy(benchmark)
    weakened["failure_thresholds"]["max_authority_leakage_failures"] = 1
    weakened_path = tmp_path / "weakened.json"
    weakened_path.write_text(json.dumps(weakened), encoding="utf-8")

    with pytest.raises(ValueError, match="exactly ten"):
        load_benchmark(incomplete_path)
    with pytest.raises(ValueError, match="hard gates"):
        load_benchmark(weakened_path)


def test_core_10_report_exposes_six_separate_metrics_and_hard_gates() -> None:
    from hxy_knowledge.brain_benchmark import (
        build_core_10_contract_runs,
        build_core_10_report,
        load_benchmark,
    )

    benchmark = load_benchmark(SUITE)
    report = build_core_10_report(benchmark, build_core_10_contract_runs())

    assert set(report["metrics"]) == {
        "intent_accuracy",
        "authority_mode_correctness",
        "citation_presence",
        "compliance_interception",
        "useful_action",
        "token_cost",
    }
    assert report["pass_rate"] >= 0.85
    assert report["authority_leakage_failures"] == 0
    assert report["high_risk_interception_rate"] == 1.0
    assert report["target_met"] is True
    assert report["metrics"]["token_cost"]["total_tokens"] > 0


def test_core_10_report_does_not_hide_failed_dimensions_in_one_score() -> None:
    from hxy_knowledge.brain_benchmark import (
        build_core_10_contract_runs,
        build_core_10_report,
        load_benchmark,
    )

    benchmark = load_benchmark(SUITE)
    runs = build_core_10_contract_runs()
    runs["core-citation"] = {
        **runs["core-citation"],
        "citations": [],
    }

    report = build_core_10_report(benchmark, runs)

    assert report["metrics"]["citation_presence"]["rate"] < 1.0
    citation_score = next(item for item in report["scores"] if item["case_id"] == "core-citation")
    assert citation_score["dimensions"]["citation_presence"]["passed"] is False


def test_core_10_cli_writes_contract_report(tmp_path: Path) -> None:
    output = tmp_path / "core-10-report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run-hxy-benchmark.py"),
            "--suite",
            "hxyos-core-10",
            "--output",
            str(output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["version"] == "hxyos-core-10-report.v1"
    assert report["target_met"] is True
    stdout = json.loads(result.stdout)
    assert stdout["suite"] == "hxyos-core-10"
    assert stdout["benchmark_kind"] == "deterministic_contract"
    assert stdout["pass_rate"] >= 0.85
    assert set(stdout["metrics"]) == set(report["metrics"])
    assert stdout["authority_leakage_failures"] == 0


def test_core_10_cli_fails_closed_for_incomplete_captured_runs(tmp_path: Path) -> None:
    from hxy_knowledge.brain_benchmark import build_core_10_contract_runs

    runs = tmp_path / "captured-runs.json"
    output = tmp_path / "captured-report.json"
    captured_runs = build_core_10_contract_runs()
    captured_runs.pop("core-brand-identity")
    runs.write_text(
        json.dumps({"version": "hxyos-core-10-runs.v1", "runs": captured_runs}),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run-hxy-benchmark.py"),
            "--suite",
            "hxyos-core-10",
            "--runs",
            str(runs),
            "--output",
            str(output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 1
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["benchmark_kind"] == "captured_product_answers"
    assert report["target_met"] is False
    assert report["pass_rate"] == 0.9
    assert report["capture_validation_errors"] == ["missing case: core-brand-identity"]


def test_core_10_report_keeps_safe_authority_downgrade_out_of_leakage_count() -> None:
    from hxy_knowledge.brain_benchmark import (
        build_core_10_contract_runs,
        build_core_10_report,
        load_benchmark,
    )

    benchmark = load_benchmark(SUITE)
    runs = build_core_10_contract_runs()
    runs["core-brand-identity"] = {
        **runs["core-brand-identity"],
        "answer_mode": "working",
        "authority_source": "internal_material",
        "authority_provenance": "source_record",
        "needs_review": True,
    }

    report = build_core_10_report(
        benchmark,
        runs,
        benchmark_kind="captured_product_answers",
    )

    assert report["pass_rate"] == 0.9
    assert report["authority_leakage_failures"] == 0
    assert report["target_met"] is False


def test_core_10_report_hard_fails_one_malformed_captured_run() -> None:
    from hxy_knowledge.brain_benchmark import (
        build_core_10_contract_runs,
        build_core_10_report,
        load_benchmark,
    )

    benchmark = load_benchmark(SUITE)
    runs = build_core_10_contract_runs()
    runs["core-brand-identity"] = {
        **runs["core-brand-identity"],
        "output_tokens": None,
    }

    report = build_core_10_report(
        benchmark,
        runs,
        benchmark_kind="captured_product_answers",
    )

    assert report["pass_rate"] == 0.9
    assert report["invalid_telemetry_failures"] == 1
    assert report["target_met"] is False
