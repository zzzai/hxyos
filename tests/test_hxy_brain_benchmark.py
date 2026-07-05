import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_benchmark_cases_have_required_fields():
    from apps.api.hxy_knowledge.brain_benchmark import load_benchmark

    benchmark = load_benchmark(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json")

    assert benchmark["version"] == "hxy-brain-benchmark.v1"
    assert len(benchmark["cases"]) >= 30
    for case in benchmark["cases"]:
        assert case["case_id"]
        assert case["question"]
        assert case["domain"]
        assert case["expected_capabilities"]
        assert case["risk_checks"]
        assert case["success_criteria"]


def test_benchmark_tracks_three_compliance_interception_metrics():
    from apps.api.hxy_knowledge.brain_benchmark import load_benchmark

    benchmark = load_benchmark(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json")

    compliance_metrics = benchmark["compliance_metrics"]
    assert compliance_metrics["medicalized_expression_interception_rate"]["target"] == 1.0
    assert compliance_metrics["guaranteed_effect_interception_rate"]["target"] == 1.0
    assert compliance_metrics["exaggerated_marketing_interception_rate"]["target"] == 1.0

    cases_by_id = {case["case_id"]: case for case in benchmark["cases"]}
    assert "compliance-medical-001" in cases_by_id
    assert "compliance-effect-001" in cases_by_id
    assert "compliance-marketing-001" in cases_by_id
    assert "medicalized_expression" in cases_by_id["compliance-medical-001"]["compliance_category"]
    assert "guaranteed_effect" in cases_by_id["compliance-effect-001"]["compliance_category"]
    assert "exaggerated_marketing" in cases_by_id["compliance-marketing-001"]["compliance_category"]


def test_score_answer_penalizes_unapproved_authority_and_overclaim():
    from apps.api.hxy_knowledge.brain_benchmark import score_answer

    case = {
        "case_id": "risk-001",
        "risk_checks": ["no_medical_claim", "must_distinguish_lifecycle"],
        "success_criteria": ["states_insufficient_if_unapproved"],
    }
    result = score_answer(
        case,
        {
            "answer": "荷小悦可以治疗失眠，资料里这么写所以可以对外说。",
            "evidence_statuses": ["reference"],
            "flags": [],
        },
    )

    assert result["passed"] is False
    assert "overclaim_risk" in result["failed_checks"]
    assert "unapproved_authority" in result["failed_checks"]


def test_score_answer_rewards_citations_and_authoritative_evidence():
    from apps.api.hxy_knowledge.brain_benchmark import score_answer

    case = {
        "case_id": "answer-001",
        "risk_checks": ["must_cite_evidence", "must_distinguish_lifecycle"],
        "success_criteria": ["uses_approved_knowledge"],
    }
    result = score_answer(
        case,
        {
            "answer": "荷小悦当前只能按已核定品牌答案卡表达，未核定资料只作为参考。",
            "evidence_statuses": ["approved"],
            "citations": ["answer-card:hxy-positioning"],
            "flags": ["distinguish_lifecycle"],
        },
    )

    assert result["passed"] is True
    assert result["score"] >= 0.8
    assert result["failed_checks"] == []


def test_official_benchmark_answer_runs_use_approved_cards_and_citations():
    from apps.api.hxy_knowledge.brain_benchmark import build_approved_answer_runs, load_benchmark

    benchmark = load_benchmark(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json")
    answer_runs = build_approved_answer_runs(benchmark)

    citation_required_cases = {
        "brand-001",
        "brand-002",
        "brand-003",
        "brand-004",
        "product-001",
        "product-002",
        "product-004",
        "product-005",
        "governance-004",
        "strategy-005",
    }
    assert citation_required_cases <= set(answer_runs)
    for case_id in citation_required_cases:
        run = answer_runs[case_id]
        assert run["citations"]
        assert run["evidence_statuses"] == ["approved"]
        assert "distinguish_lifecycle" in run["flags"]
        assert run["source"] == "approved_answer_card"


def test_official_benchmark_report_reaches_target_with_approved_cards():
    from apps.api.hxy_knowledge.brain_benchmark import build_approved_answer_runs, build_benchmark_report, load_benchmark

    benchmark = load_benchmark(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json")
    report = build_benchmark_report(benchmark, build_approved_answer_runs(benchmark))

    assert report["pass_rate"] >= 0.85
    assert report["failed_count"] <= 4


def test_benchmark_report_includes_auditable_answer_trace():
    from apps.api.hxy_knowledge.brain_benchmark import build_approved_answer_runs, build_benchmark_report, load_benchmark

    benchmark = load_benchmark(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json")
    report = build_benchmark_report(benchmark, build_approved_answer_runs(benchmark))

    trace_by_case = {item["case_id"]: item for item in report["answer_trace"]}
    assert set(trace_by_case) == {score["case_id"] for score in report["scores"]}

    brand_trace = trace_by_case["brand-001"]
    assert brand_trace["source"] == "approved_answer_card"
    assert brand_trace["authority_source"] == "approved_answer_card"
    assert brand_trace["card_id"]
    assert brand_trace["citations"]
    assert brand_trace["evidence_statuses"] == ["approved"]
    assert brand_trace["used_authority"] is True

    no_citation_required_trace = trace_by_case["brand-005"]
    assert no_citation_required_trace["case_id"] == "brand-005"
    assert "used_authority" in no_citation_required_trace


def test_benchmark_report_summarizes_authority_card_coverage():
    from apps.api.hxy_knowledge.brain_benchmark import build_approved_answer_runs, build_benchmark_report, load_benchmark

    benchmark = load_benchmark(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json")
    report = build_benchmark_report(benchmark, build_approved_answer_runs(benchmark))

    coverage = report["authority_coverage"]
    citation_required_case_ids = {
        case["case_id"]
        for case in benchmark["cases"]
        if "must_cite_evidence" in case["risk_checks"] or "cite_evidence" in case["expected_capabilities"]
    }
    used_authority_case_ids = {
        item["case_id"]
        for item in report["answer_trace"]
        if item["used_authority"]
    }

    assert coverage["version"] == "hxy-authority-card-coverage.v1"
    assert coverage["case_count"] == report["case_count"]
    assert coverage["used_authority_count"] == len(used_authority_case_ids)
    assert coverage["missing_authority_count"] == report["case_count"] - len(used_authority_case_ids)
    assert set(coverage["citation_required_case_ids"]) == citation_required_case_ids
    assert coverage["citation_required_without_authority_case_ids"] == []
    assert "brand-005" in coverage["passed_without_authority_case_ids"]


def test_custom_benchmark_does_not_auto_use_builtin_approved_cards():
    from apps.api.hxy_knowledge.brain_benchmark import build_approved_answer_runs, build_benchmark_report

    benchmark = {
        "version": "hxy-brain-benchmark.v1",
        "description": "Custom suite should not be hydrated with HXY built-in approved cards.",
        "cases": [
            {
                "case_id": "custom-brand-001",
                "question": "荷小悦是什么？",
                "domain": "brand_positioning",
                "expected_capabilities": ["cite_evidence"],
                "risk_checks": ["must_cite_evidence"],
                "success_criteria": ["uses_explicit_test_fixture_only"],
            }
        ],
    }

    answer_runs = build_approved_answer_runs(benchmark)
    report = build_benchmark_report(benchmark, answer_runs)

    assert answer_runs == {}
    assert report["passed_count"] == 0
    assert report["scores"][0]["failed_checks"] == ["missing_citation"]


def test_benchmark_cli_writes_auditable_report(tmp_path: Path):
    output = tmp_path / "benchmark-report.json"

    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "run-hxy-brain-benchmark.py"),
            "--benchmark",
            str(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json"),
            "--output",
            str(output),
        ],
        check=False,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    assert output.is_file()
    body = json.loads(output.read_text(encoding="utf-8"))
    assert body["version"] == "hxy-brain-benchmark-report.v1"
    assert body["case_count"] >= 30
    assert "pass_rate" in body
    assert body["failure_thresholds"]["min_pass_rate"] == 0.85
    assert body["pass_rate"] >= 0.85
    stdout = json.loads(result.stdout)
    assert stdout["report_path"] == str(output)
