from __future__ import annotations

import json
import hashlib
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PYTHON = ROOT / ".venv" / "bin" / "python"
BENCHMARK_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-engine-benchmark-v1.json"
RUBRIC_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-semantic-rubric-v1.json"
CALIBRATION_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-semantic-calibration-v1.json"
RUNNER = ROOT / "scripts" / "run-hxy-semantic-benchmark.py"
PACK_BUILDER = ROOT / "scripts" / "build-hxy-semantic-review-pack.py"


def _answer_payload(*, limit: int = 50) -> dict:
    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    answers = []
    for case in benchmark["cases"][:limit]:
        formal = case["expected_authority"] == "approved"
        evidence_id = case["allowed_evidence_ids"][0]
        answers.append(
            {
                "case_id": case["case_id"],
                "provider_name": "current-hxy-answer-pipeline",
                "provider_version": "v1",
                "identity_aliases": [],
                "answer": "根据当前证据先核对事实，再由负责人完成下一步验证；资料不足时不扩大结论。",
                "answer_authority": case["expected_authority"],
                "evidence_ids": [evidence_id],
                "evidence_authorities": ["approved" if formal else "reference"],
                "citations": [evidence_id],
                "declared_outcomes": case["minimum_useful_outcome"],
                "policy_action": "answer" if formal else "needs_review",
                "guardrail_action": "send" if formal else "revise_or_review",
                "latency_ms": 1,
                "input_tokens": 0,
                "output_tokens": 0,
                "cost_microunits": 0,
                "safe_trace": {"status": "synthetic_fixture"},
            }
        )
    return {"version": "hxy-semantic-answer-run.v1", "answers": answers}


def _run_cli(tmp_path: Path, answers: dict) -> subprocess.CompletedProcess[str]:
    answers_path = tmp_path / "answers.json"
    output_path = tmp_path / "report.json"
    answers_path.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")
    return subprocess.run(
        [
            str(PYTHON),
            str(RUNNER),
            "--benchmark",
            str(BENCHMARK_PATH),
            "--rubric",
            str(RUBRIC_PATH),
            "--calibration",
            str(CALIBRATION_PATH),
            "--answers",
            str(answers_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_semantic_cli_writes_safe_awaiting_report(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, _answer_payload())
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    serialized = json.dumps(report, ensure_ascii=False)

    assert completed.returncode == 0, completed.stderr
    assert report["case_count"] == 50
    assert report["structural_pass_count"] == 50
    assert report["metric_scope"] == "structural_preflight_not_semantic_quality"
    assert report["semantic_status"] == "awaiting_human_calibration"
    assert report["quality_claim_allowed"] is False
    assert "根据当前证据" not in serialized
    assert str(tmp_path) not in completed.stdout
    assert json.loads(completed.stdout)["report_name"] == "report.json"


def test_semantic_cli_keeps_missing_answer_case_as_failure(tmp_path: Path) -> None:
    completed = _run_cli(tmp_path, _answer_payload(limit=49))
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))

    assert completed.returncode == 0
    assert report["case_count"] == 50
    assert report["structural_fail_count"] == 1
    assert report["cases"][-1]["reason_codes"] == ["missing_answer_run"]


def test_semantic_cli_rejects_incomplete_benchmark(tmp_path: Path) -> None:
    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    benchmark["cases"] = benchmark["cases"][:1]
    benchmark_path = tmp_path / "incomplete.json"
    answers_path = tmp_path / "answers.json"
    output_path = tmp_path / "report.json"
    benchmark_path.write_text(json.dumps(benchmark), encoding="utf-8")
    answers_path.write_text(json.dumps(_answer_payload(limit=1)), encoding="utf-8")

    completed = subprocess.run(
        [
            str(PYTHON),
            str(RUNNER),
            "--benchmark",
            str(benchmark_path),
            "--rubric",
            str(RUBRIC_PATH),
            "--calibration",
            str(CALIBRATION_PATH),
            "--answers",
            str(answers_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert not output_path.exists()
    assert "complete benchmark requires exactly 50 cases" in completed.stderr


def test_review_pack_is_blind_and_contains_private_answer_only_in_pack(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    output_path = tmp_path / "review-pack.json"
    answers = _answer_payload()
    answers["answers"][0]["identity_aliases"] = [
        "Anthropic Sonnet 4",
        "Azure OpenAI o3",
        "阿里通义模型",
    ]
    answers["answers"][0]["answer"] = (
        "Generated by provider-secret-model-v9. Powered by Anthropic Sonnet 4. "
        "This was generated using Azure OpenAI o3. 本回答由阿里通义模型生成。"
        "I am qwen-max-2026. 由 DeepSeek 生成。根据当前证据先核对事实。"
    )
    answers_path.write_text(
        json.dumps(answers, ensure_ascii=False),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            str(PYTHON),
            str(PACK_BUILDER),
            "--benchmark",
            str(BENCHMARK_PATH),
            "--rubric",
            str(RUBRIC_PATH),
            "--calibration",
            str(CALIBRATION_PATH),
            "--answers",
            str(answers_path),
            "--output",
            str(output_path),
            "--seed",
            "20260711",
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    pack = json.loads(output_path.read_text(encoding="utf-8"))
    serialized = json.dumps(pack, ensure_ascii=False)

    assert completed.returncode == 0, completed.stderr
    assert pack["version"] == "hxy-semantic-masked-review-pack.v1"
    assert pack["blind"] is False
    assert pack["blind_status"] == "identity_redaction_unverified"
    assert len(pack["items"]) == 10
    assert "根据当前证据" in serialized
    assert "provider_name" not in serialized
    assert "provider_version" not in serialized
    assert "provider-secret-model-v9" not in serialized
    assert "qwen-max-2026" not in serialized.lower()
    assert "deepseek" not in serialized.lower()
    assert "anthropic sonnet" not in serialized.lower()
    assert "azure openai" not in serialized.lower()
    assert "阿里通义模型" not in serialized
    assert "[identity redacted]" in serialized
    for item in pack["items"]:
        assert item["review_text_sha256"] == hashlib.sha256(
            item["answer"].encode("utf-8")
        ).hexdigest()


def test_review_pack_refuses_tracked_benchmark_directory(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(_answer_payload()), encoding="utf-8")
    forbidden_output = ROOT / "knowledge" / "benchmarks" / "review-pack-private.json"

    completed = subprocess.run(
        [
            str(PYTHON),
            str(PACK_BUILDER),
            "--benchmark",
            str(BENCHMARK_PATH),
            "--rubric",
            str(RUBRIC_PATH),
            "--calibration",
            str(CALIBRATION_PATH),
            "--answers",
            str(answers_path),
            "--output",
            str(forbidden_output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert not forbidden_output.exists()
    assert "private review packs cannot be written" in completed.stderr


def test_semantic_cli_rejects_catalog_from_another_benchmark(tmp_path: Path) -> None:
    rubric = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    rubric["benchmark_sha256"] = "0" * 64
    rubric_path = tmp_path / "wrong-rubric.json"
    answers_path = tmp_path / "answers.json"
    output_path = tmp_path / "report.json"
    rubric_path.write_text(json.dumps(rubric), encoding="utf-8")
    answers_path.write_text(json.dumps(_answer_payload()), encoding="utf-8")

    completed = subprocess.run(
        [
            str(PYTHON),
            str(RUNNER),
            "--benchmark",
            str(BENCHMARK_PATH),
            "--rubric",
            str(rubric_path),
            "--calibration",
            str(CALIBRATION_PATH),
            "--answers",
            str(answers_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert not output_path.exists()
    assert "catalog benchmark digest mismatch" in completed.stderr


def test_semantic_cli_rejects_forged_calibration_case_ids(tmp_path: Path) -> None:
    calibration = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    calibration["case_ids"][0] = "/root/hxy/private-case"
    calibration_path = tmp_path / "forged-calibration.json"
    answers_path = tmp_path / "answers.json"
    output_path = tmp_path / "report.json"
    calibration_path.write_text(json.dumps(calibration), encoding="utf-8")
    answers_path.write_text(json.dumps(_answer_payload()), encoding="utf-8")

    completed = subprocess.run(
        [
            str(PYTHON),
            str(RUNNER),
            "--benchmark",
            str(BENCHMARK_PATH),
            "--rubric",
            str(RUBRIC_PATH),
            "--calibration",
            str(calibration_path),
            "--answers",
            str(answers_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert not output_path.exists()
    assert "semantic calibration catalog mismatch" in completed.stderr


def test_semantic_cli_rejects_nonobject_safe_trace(tmp_path: Path) -> None:
    answers = _answer_payload()
    answers["answers"][0]["safe_trace"] = "/root/private/credential.json"

    completed = _run_cli(tmp_path, answers)

    assert completed.returncode == 2
    assert not (tmp_path / "report.json").exists()
    assert "safe_trace must be an object" in completed.stderr


def test_review_pack_refuses_other_tracked_repository_directories(tmp_path: Path) -> None:
    answers_path = tmp_path / "answers.json"
    answers_path.write_text(json.dumps(_answer_payload()), encoding="utf-8")
    forbidden_output = ROOT / "docs" / "review-pack-private-test.json"

    completed = subprocess.run(
        [
            str(PYTHON),
            str(PACK_BUILDER),
            "--benchmark",
            str(BENCHMARK_PATH),
            "--rubric",
            str(RUBRIC_PATH),
            "--calibration",
            str(CALIBRATION_PATH),
            "--answers",
            str(answers_path),
            "--output",
            str(forbidden_output),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert not forbidden_output.exists()
    assert "private review packs cannot be written" in completed.stderr


def test_review_pack_fails_closed_on_unremoved_identity_marker(tmp_path: Path) -> None:
    answers = _answer_payload()
    answers["answers"][0]["answer"] = (
        "模型：q\u200bwen-max。回答引擎：神秘星云。"
        "本回答通过神秘星云完成。根据当前证据核对事实。"
    )
    answers_path = tmp_path / "answers.json"
    output_path = tmp_path / "review-pack.json"
    answers_path.write_text(json.dumps(answers, ensure_ascii=False), encoding="utf-8")

    completed = subprocess.run(
        [
            str(PYTHON),
            str(PACK_BUILDER),
            "--benchmark",
            str(BENCHMARK_PATH),
            "--rubric",
            str(RUBRIC_PATH),
            "--calibration",
            str(CALIBRATION_PATH),
            "--answers",
            str(answers_path),
            "--output",
            str(output_path),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 2
    assert not output_path.exists()
    assert "blind review identity marker remains" in completed.stderr
