from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

from apps.api.hxy_engines.descriptor import EngineDescriptor


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-engine-benchmark-v1.schema.json"
SAMPLE_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-engine-benchmark-v1.sample.json"
VALIDATOR_PATH = ROOT / "scripts" / "validate-hxy-engine-benchmark.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("hxy_engine_benchmark_validator", VALIDATOR_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_engine_descriptor_is_bounded_and_exportable() -> None:
    descriptor = EngineDescriptor(
        name="current-assignment-retrieval",
        version="v1",
        capabilities=("hybrid_retrieval", "assignment_filter"),
        license_id="HXY-owned",
        deployment="in_process",
        data_export="canonical_ids_and_scores",
        healthcheck="adapter_constructor",
        rollback="select_previous_adapter",
    )

    assert descriptor.as_dict()["capabilities"] == [
        "assignment_filter",
        "hybrid_retrieval",
    ]

    with pytest.raises(ValueError):
        EngineDescriptor(
            name="",
            version="v1",
            capabilities=(),
            license_id="unknown",
            deployment="unknown",
            data_export="none",
            healthcheck="none",
            rollback="none",
        )


def test_engine_benchmark_schema_requires_governed_case_contract() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert schema["properties"]["cases"]["items"] == {"$ref": "#/$defs/case"}
    case_schema = schema["$defs"]["case"]

    assert schema["$schema"].endswith("2020-12/schema")
    assert set(case_schema["required"]) >= {
        "case_id",
        "role",
        "assignment_scope",
        "task",
        "allowed_evidence_ids",
        "forbidden_evidence_ids",
        "expected_authority",
        "risk_expectations",
        "minimum_useful_outcome",
        "budget",
    }
    assert case_schema["additionalProperties"] is False


def test_engine_benchmark_sample_covers_five_roles_without_private_data() -> None:
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))

    assert sample["version"] == "hxy-engine-benchmark.v1"
    assert len(sample["cases"]) == 5
    assert {item["role"] for item in sample["cases"]} == {
        "founder",
        "brand_operations",
        "store_manager",
        "store_employee",
        "knowledge_data_admin",
    }
    serialized = json.dumps(sample, ensure_ascii=False).lower()
    for forbidden in (
        "/root/hxy",
        "/root/htops",
        "password",
        "api_key",
        "session_grant",
        "bearer ",
    ):
        assert forbidden not in serialized


def test_validator_accepts_sample_and_requires_fifty_for_complete_mode() -> None:
    module = _load_validator()

    report = module.validate_benchmark_file(SAMPLE_PATH, require_complete=False)
    assert report["status"] == "passed"
    assert report["case_count"] == 5
    assert report["role_counts"] == {
        "brand_operations": 1,
        "founder": 1,
        "knowledge_data_admin": 1,
        "store_employee": 1,
        "store_manager": 1,
    }

    complete = module.validate_benchmark_file(SAMPLE_PATH, require_complete=True)
    assert complete["status"] == "failed"
    assert "complete benchmark requires exactly 50 cases" in complete["errors"]


def test_validator_rejects_scope_leakage_and_unbounded_budget(tmp_path: Path) -> None:
    module = _load_validator()
    sample = json.loads(SAMPLE_PATH.read_text(encoding="utf-8"))
    sample["cases"][0]["allowed_evidence_ids"] = ["evidence-shared"]
    sample["cases"][0]["forbidden_evidence_ids"] = ["evidence-shared"]
    sample["cases"][0]["budget"]["max_latency_ms"] = 700_000
    invalid_path = tmp_path / "invalid.json"
    invalid_path.write_text(json.dumps(sample), encoding="utf-8")

    report = module.validate_benchmark_file(invalid_path, require_complete=False)

    assert report["status"] == "failed"
    assert any("evidence sets overlap" in item for item in report["errors"])
    assert any("max_latency_ms" in item for item in report["errors"])
