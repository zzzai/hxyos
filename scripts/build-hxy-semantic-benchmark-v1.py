#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-engine-benchmark-v1.json"
RUBRIC_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-semantic-rubric-v1.json"
CALIBRATION_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-semantic-calibration-v1.json"
ROLE_ORDER = (
    "founder",
    "brand_operations",
    "store_manager",
    "store_employee",
    "knowledge_data_admin",
)
DIMENSIONS = (
    "factual_correctness",
    "role_usefulness",
    "evidence_alignment",
    "expression_fitness",
    "actionability",
)


def _canonical_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def build_payloads() -> tuple[dict[str, Any], dict[str, Any]]:
    benchmark = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    benchmark_sha256 = hashlib.sha256(_canonical_bytes(benchmark)).hexdigest()
    rubric_cases = [
        {
            "case_id": str(case["case_id"]),
            "role": str(case["role"]),
            "required_outcomes": list(case["minimum_useful_outcome"]),
            "risk_expectations": list(case["risk_expectations"]),
            "evidence_authority_by_id": {
                evidence_id: (
                    "approved"
                    if case["expected_authority"] == "approved"
                    else "reference"
                )
                for evidence_id in case["allowed_evidence_ids"]
            },
            "dimensions": list(DIMENSIONS),
        }
        for case in benchmark["cases"]
    ]
    calibration_ids: list[str] = []
    for role in ROLE_ORDER:
        role_ids = [
            str(case["case_id"])
            for case in benchmark["cases"]
            if case["role"] == role
        ]
        if len(role_ids) < 2:
            raise ValueError(f"role {role} requires at least two benchmark cases")
        calibration_ids.extend((role_ids[0], role_ids[-1]))

    rubric = {
        "version": "hxy-semantic-rubric.v1",
        "benchmark_id": benchmark["benchmark_id"],
        "benchmark_sha256": benchmark_sha256,
        "dimensions": {
            "factual_correctness": "Claims are correct within the supplied evidence.",
            "role_usefulness": "The answer helps the assigned role make progress.",
            "evidence_alignment": "Conclusions remain within authorized evidence.",
            "expression_fitness": "Language fits the role, scenario, and risk boundary.",
            "actionability": "The answer gives a usable next action or clear stop condition.",
        },
        "score_scale": {"minimum": 1, "maximum": 5},
        "cases": rubric_cases,
    }
    calibration = {
        "version": "hxy-semantic-calibration.v1",
        "benchmark_id": benchmark["benchmark_id"],
        "benchmark_sha256": benchmark_sha256,
        "selection": "first_and_last_case_per_role",
        "reviews_required_per_case": 2,
        "case_ids": calibration_ids,
    }
    return rubric, calibration


def _write(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    rubric, calibration = build_payloads()
    _write(RUBRIC_PATH, rubric)
    _write(CALIBRATION_PATH, calibration)
    print(
        json.dumps(
            {
                "version": "hxy-semantic-catalog-builder.v1",
                "rubric_case_count": len(rubric["cases"]),
                "calibration_case_count": len(calibration["case_ids"]),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
