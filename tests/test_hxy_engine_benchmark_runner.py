from __future__ import annotations

import json
import subprocess
from pathlib import Path

from apps.api.hxy_engines.benchmark_runner import (
    CaseObservation,
    CurrentContractBaselineExecutor,
    run_contract_baseline,
)


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-engine-benchmark-v1.json"
CLI_PATH = ROOT / "scripts" / "run-hxy-engine-benchmark.py"


def _benchmark() -> dict:
    return json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))


def test_current_contract_executor_runs_all_cases_without_semantic_claim() -> None:
    report = run_contract_baseline(
        _benchmark(),
        CurrentContractBaselineExecutor(),
    )

    assert report["version"] == "hxy-engine-benchmark-report.v1"
    assert report["mode"] == "contract_baseline"
    assert report["case_count"] == 50
    assert report["contract_pass_count"] == 50
    assert report["contract_fail_count"] == 0
    assert report["contract_pass_rate"] == 1.0
    assert report["semantic_status"] == "not_evaluated"
    assert report["semantic_evaluated_count"] == 0
    assert report["quality_claim_allowed"] is False
    assert "pass_rate" not in report
    assert {item["role"] for item in report["cases"]} == {
        "founder",
        "brand_operations",
        "store_manager",
        "store_employee",
        "knowledge_data_admin",
    }


def test_runner_detects_forbidden_evidence_and_private_trace() -> None:
    benchmark = _benchmark()
    benchmark["cases"] = [benchmark["cases"][0]]
    case = benchmark["cases"][0]

    class UnsafeExecutor:
        descriptor = {"name": "unsafe", "version": "v1"}

        def execute(self, _case):
            return CaseObservation(
                returned_evidence_ids=(case["forbidden_evidence_ids"][0],),
                artifact_authorities=("approved",),
                risk_probe_required=False,
                risk_probe_intercepted=False,
                write_attempted=True,
                scope_denied=False,
                latency_ms=1,
                input_tokens=0,
                output_tokens=0,
                trace_record={"path": "/root/hxy/private.txt"},
            )

    report = run_contract_baseline(benchmark, UnsafeExecutor())
    result = report["cases"][0]

    assert result["contract_status"] == "failed"
    assert result["hard_gates"] == {
        "unauthorized_evidence_exposure": False,
        "authority_state_violation": False,
        "prohibited_expression_miss": True,
        "unapproved_write": False,
        "trace_privacy": False,
    }
    assert report["contract_fail_count"] == 1


def test_current_contract_report_contains_no_content_or_server_paths() -> None:
    report = run_contract_baseline(
        _benchmark(),
        CurrentContractBaselineExecutor(),
    )
    serialized = json.dumps(report, ensure_ascii=False).lower()

    for forbidden in (
        "/root/hxy",
        "/root/htops",
        "knowledge/raw",
        "password=",
        "api_key",
        "session_grant",
        "authorization: bearer",
    ):
        assert forbidden not in serialized


def test_contract_baseline_cli_writes_auditable_report(tmp_path: Path) -> None:
    output = tmp_path / "report.json"

    completed = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            str(CLI_PATH),
            "--benchmark",
            str(BENCHMARK_PATH),
            "--output",
            str(output),
            "--mode",
            "contract",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    summary = json.loads(completed.stdout)
    report = json.loads(output.read_text(encoding="utf-8"))
    assert summary == {
        "version": "hxy-engine-benchmark-cli.v1",
        "mode": "contract_baseline",
        "report_path": str(output),
        "case_count": 50,
        "contract_pass_count": 50,
        "semantic_status": "not_evaluated",
    }
    assert report["quality_claim_allowed"] is False


def test_runner_redacts_private_values_from_failed_observation() -> None:
    benchmark = _benchmark()
    benchmark["cases"] = [benchmark["cases"][0]]

    class PrivateValueExecutor:
        descriptor = {"name": "/root/hxy/private-engine", "version": "v1"}

        def execute(self, _case):
            return CaseObservation(
                artifact_authorities=("/root/hxy/approved",),
                trace_record={
                    "engine_name": "/root/hxy/private-engine",
                    "source_path": "/root/hxy/private.txt",
                },
            )

    report = run_contract_baseline(benchmark, PrivateValueExecutor())
    serialized = json.dumps(report, ensure_ascii=False).lower()

    assert report["cases"][0]["contract_status"] == "failed"
    assert "/root/hxy" not in serialized
    assert report["engine"]["name"] == "redacted"
    assert report["cases"][0]["artifact_authorities"] == ["invalid"]


def test_runner_rejects_negative_token_usage() -> None:
    benchmark = _benchmark()
    benchmark["cases"] = [benchmark["cases"][0]]

    class NegativeUsageExecutor:
        descriptor = {"name": "negative-usage", "version": "v1"}

        def execute(self, _case):
            return CaseObservation(input_tokens=-1, output_tokens=1)

    report = run_contract_baseline(benchmark, NegativeUsageExecutor())
    result = report["cases"][0]

    assert result["contract_status"] == "failed"
    assert result["budget_checks"]["tokens"] is False


def test_noop_executor_cannot_pass_case_derived_contract_gates() -> None:
    benchmark = _benchmark()

    class NoopExecutor:
        descriptor = {"name": "noop", "version": "v1"}

        def execute(self, _case):
            return CaseObservation()

    report = run_contract_baseline(benchmark, NoopExecutor())

    assert report["contract_pass_count"] == 0
    assert report["contract_fail_count"] == 50


def test_contract_baseline_cli_rejects_incomplete_corpus(tmp_path: Path) -> None:
    benchmark = _benchmark()
    benchmark["cases"] = benchmark["cases"][:1]
    benchmark_path = tmp_path / "incomplete.json"
    output = tmp_path / "report.json"
    benchmark_path.write_text(json.dumps(benchmark), encoding="utf-8")

    completed = subprocess.run(
        [
            str(ROOT / ".venv" / "bin" / "python"),
            str(CLI_PATH),
            "--benchmark",
            str(benchmark_path),
            "--output",
            str(output),
            "--mode",
            "contract",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert not output.exists()
    assert "complete benchmark requires exactly 50 cases" in completed.stderr


def test_report_records_benchmark_and_policy_digests() -> None:
    report = run_contract_baseline(
        _benchmark(),
        CurrentContractBaselineExecutor(),
    )

    assert len(report["benchmark_sha256"]) == 64
    assert report["runner_version"] == "hxy-contract-baseline-runner.v1"
    assert report["policy"]["checker_version"] == "hxy-brand-risk-check.v1"
    assert report["policy"]["rules_version"] == "hxy-brand-risk-rules.v1"
    assert len(report["policy"]["rules_sha256"]) == 64
    risk_case = next(
        item for item in report["cases"] if item["risk_pattern_required"]
    )
    assert risk_case["risk_pattern_detected"] is True
    assert "risk_probe_intercepted" not in risk_case


def test_returned_evidence_requires_matching_authority_metadata() -> None:
    benchmark = _benchmark()
    benchmark["cases"] = [benchmark["cases"][0]]
    case = benchmark["cases"][0]

    class MissingAuthorityExecutor:
        descriptor = {"name": "missing-authority", "version": "v1"}

        def execute(self, _case):
            return CaseObservation(
                returned_evidence_ids=(case["allowed_evidence_ids"][0],),
                artifact_authorities=(),
            )

    report = run_contract_baseline(benchmark, MissingAuthorityExecutor())
    result = report["cases"][0]

    assert result["contract_status"] == "failed"
    assert result["hard_gates"]["authority_state_violation"] is False


def test_unknown_private_evidence_ids_are_never_echoed() -> None:
    benchmark = _benchmark()
    benchmark["cases"] = [benchmark["cases"][0]]

    class PrivateEvidenceExecutor:
        descriptor = {"name": "private-evidence", "version": "v1"}

        def execute(self, _case):
            return CaseObservation(
                returned_evidence_ids=("session_grant",),
                artifact_authorities=("reference",),
            )

    report = run_contract_baseline(benchmark, PrivateEvidenceExecutor())
    result = report["cases"][0]
    serialized = json.dumps(report, ensure_ascii=False).lower()

    assert result["contract_status"] == "failed"
    assert result["returned_evidence_ids"] == []
    assert result["redacted_evidence_count"] == 1
    assert "session_grant" not in serialized
