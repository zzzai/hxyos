from __future__ import annotations

import importlib.util
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER_PATH = ROOT / "scripts" / "build-hxy-semantic-benchmark-v1.py"
BENCHMARK_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-engine-benchmark-v1.json"
RUBRIC_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-semantic-rubric-v1.json"
CALIBRATION_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-semantic-calibration-v1.json"


def _load_builder():
    spec = importlib.util.spec_from_file_location("hxy_semantic_builder", BUILDER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_semantic_catalogs_cover_all_cases_and_two_per_role() -> None:
    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    rubric = json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    calibration = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    case_roles = {case["case_id"]: case["role"] for case in benchmark["cases"]}

    assert rubric["version"] == "hxy-semantic-rubric.v1"
    assert len(rubric["cases"]) == 50
    assert {item["case_id"] for item in rubric["cases"]} == set(case_roles)
    assert all(len(item["dimensions"]) == 5 for item in rubric["cases"])

    assert calibration["version"] == "hxy-semantic-calibration.v1"
    assert len(calibration["case_ids"]) == 10
    assert Counter(case_roles[case_id] for case_id in calibration["case_ids"]) == {
        "founder": 2,
        "brand_operations": 2,
        "store_manager": 2,
        "store_employee": 2,
        "knowledge_data_admin": 2,
    }


def test_semantic_catalogs_are_reproducible_and_public_safe() -> None:
    module = _load_builder()
    rubric, calibration = module.build_payloads()

    assert rubric == json.loads(RUBRIC_PATH.read_text(encoding="utf-8"))
    assert calibration == json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    assert rubric["benchmark_sha256"] == calibration["benchmark_sha256"]
    assert len(rubric["benchmark_sha256"]) == 64

    serialized = json.dumps(
        {"rubric": rubric, "calibration": calibration},
        ensure_ascii=False,
    ).lower()
    for forbidden in (
        "/root/hxy",
        "/root/htops",
        "knowledge/raw",
        "password=",
        "api_key",
        "session_grant",
        "authorization: bearer",
        "answer_text",
    ):
        assert forbidden not in serialized
