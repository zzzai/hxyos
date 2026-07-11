from __future__ import annotations

import json
import hashlib
from pathlib import Path

import pytest

from apps.api.hxy_engines.semantic_benchmark import (
    HumanSemanticReview,
    apply_human_calibration,
    build_blind_item_id,
    human_reviews_from_payload,
)


ROOT = Path(__file__).resolve().parents[1]
CALIBRATION_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-semantic-calibration-v1.json"
SCHEMA_PATH = ROOT / "knowledge" / "benchmarks" / "hxy-semantic-review-v1.schema.json"
DIMENSIONS = (
    "factual_correctness",
    "role_usefulness",
    "evidence_alignment",
    "expression_fitness",
    "actionability",
)
BENCHMARK_SHA256 = json.loads(
    CALIBRATION_PATH.read_text(encoding="utf-8")
)["benchmark_sha256"]
RUBRIC_SHA256 = "b" * 64


def _calibration() -> dict:
    return json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))


def _deterministic_report() -> dict:
    return {
        "version": "hxy-semantic-benchmark-report.v1",
        "benchmark_sha256": BENCHMARK_SHA256,
        "rubric_sha256": RUBRIC_SHA256,
        "case_count": 50,
        "structural_pass_count": 40,
        "structural_fail_count": 10,
        "semantic_status": "deterministic_only",
        "semantic_evaluated_count": 0,
        "quality_claim_allowed": False,
        "cases": [
            {
                "case_id": case_id,
                "answer_sha256": hashlib.sha256(case_id.encode("utf-8")).hexdigest(),
                "review_text_sha256": hashlib.sha256(
                    f"review:{case_id}".encode("utf-8")
                ).hexdigest(),
                "structural_status": "passed",
                "hard_gates": {"output_risk_pattern_clear": True},
            }
            for case_id in _calibration()["case_ids"]
        ],
    }


def _review(case_id: str, reviewer_id: str, score: int = 4, **overrides) -> HumanSemanticReview:
    scores = {dimension: score for dimension in DIMENSIONS}
    scores.update(overrides)
    answer_sha256 = hashlib.sha256(case_id.encode("utf-8")).hexdigest()
    review_text_sha256 = hashlib.sha256(
        f"review:{case_id}".encode("utf-8")
    ).hexdigest()
    return HumanSemanticReview(
        case_id=case_id,
        reviewer_id=reviewer_id,
        answer_sha256=answer_sha256,
        review_text_sha256=review_text_sha256,
        benchmark_sha256=BENCHMARK_SHA256,
        rubric_sha256=RUBRIC_SHA256,
        blind_item_id=build_blind_item_id(
            case_id,
            answer_sha256,
            review_text_sha256,
            BENCHMARK_SHA256,
            RUBRIC_SHA256,
        ),
        scores=scores,
    )


def test_incomplete_reviews_keep_awaiting_state() -> None:
    report = apply_human_calibration(
        _deterministic_report(),
        _calibration(),
        [],
    )

    assert report["semantic_status"] == "awaiting_human_calibration"
    assert report["semantic_evaluated_count"] == 0
    assert len(report["human_calibration"]["missing_case_ids"]) == 10
    assert report["quality_claim_allowed"] is False


def test_two_reviews_per_case_complete_calibration() -> None:
    reviews = [
        _review(case_id, reviewer_id, score)
        for case_id in _calibration()["case_ids"]
        for reviewer_id, score in (("reviewer-a", 4), ("reviewer-b", 5))
    ]

    report = apply_human_calibration(
        _deterministic_report(),
        _calibration(),
        reviews,
    )

    assert report["semantic_status"] == "review_files_complete_unverified"
    assert report["semantic_evaluated_count"] == 0
    assert report["human_calibration"]["accepted_case_count"] == 10
    assert report["human_calibration"]["reviewer_provenance_verified"] is False
    assert report["human_calibration"]["needs_adjudication_case_ids"] == []
    assert report["quality_claim_allowed"] is False


def test_dimension_gap_above_one_requires_adjudication() -> None:
    case_id = _calibration()["case_ids"][0]
    reviews = [
        _review(case_id, "reviewer-a", factual_correctness=2),
        _review(case_id, "reviewer-b", factual_correctness=5),
    ]

    report = apply_human_calibration(
        _deterministic_report(),
        _calibration(),
        reviews,
    )

    assert report["semantic_status"] == "awaiting_human_calibration"
    assert report["human_calibration"]["needs_adjudication_case_ids"] == [case_id]


def test_advisory_judge_cannot_change_human_state_or_hard_gates() -> None:
    deterministic = _deterministic_report()
    judge_results = {
        case_id: {dimension: 5 for dimension in DIMENSIONS}
        for case_id in _calibration()["case_ids"]
    }

    report = apply_human_calibration(
        deterministic,
        _calibration(),
        [],
        judge_results=judge_results,
    )

    assert report["semantic_status"] == "awaiting_human_calibration"
    assert report["advisory_judge"]["evaluated_case_count"] == 10
    assert report["cases"] == deterministic["cases"]
    assert report["quality_claim_allowed"] is False


def test_review_schema_is_bounded_and_requires_five_scores() -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    review = schema["properties"]["reviews"]["items"]

    assert review["additionalProperties"] is False
    assert {
        "answer_sha256",
        "review_text_sha256",
        "benchmark_sha256",
        "rubric_sha256",
        "blind_item_id",
    } <= set(review["required"])
    assert set(review["properties"]["scores"]["required"]) == set(DIMENSIONS)
    assert review["properties"]["scores"]["additionalProperties"] is False


def test_stale_review_for_previous_answer_cannot_calibrate_new_answer() -> None:
    case_id = _calibration()["case_ids"][0]
    reviews = [
        _review(case_id, "reviewer-a"),
        _review(case_id, "reviewer-b"),
    ]
    reviews[1] = HumanSemanticReview(
        case_id=case_id,
        reviewer_id="reviewer-b",
        answer_sha256="c" * 64,
        review_text_sha256="e" * 64,
        benchmark_sha256=BENCHMARK_SHA256,
        rubric_sha256=RUBRIC_SHA256,
        blind_item_id="d" * 64,
        scores={dimension: 4 for dimension in DIMENSIONS},
    )

    report = apply_human_calibration(
        _deterministic_report(),
        _calibration(),
        reviews,
    )

    assert report["semantic_status"] == "awaiting_human_calibration"
    assert report["human_calibration"]["invalid_review_case_ids"] == [case_id]


def test_apply_calibration_rejects_noncanonical_case_set() -> None:
    calibration = _calibration()
    calibration["case_ids"] = calibration["case_ids"][:1]

    with pytest.raises(ValueError, match="semantic calibration catalog mismatch"):
        apply_human_calibration(_deterministic_report(), calibration, [])


def test_review_payload_does_not_coerce_nonstring_identity_fields() -> None:
    with pytest.raises(ValueError, match="reviewer_id must be a string"):
        human_reviews_from_payload(
            {
                "version": "hxy-semantic-review.v1",
                "reviews": [
                    {
                        "case_id": "founder-01",
                        "reviewer_id": 123,
                        "answer_sha256": "a" * 64,
                        "review_text_sha256": "e" * 64,
                        "benchmark_sha256": "b" * 64,
                        "rubric_sha256": "c" * 64,
                        "blind_item_id": "d" * 64,
                        "scores": {dimension: 4 for dimension in DIMENSIONS},
                        "reason_codes": [],
                    }
                ],
            }
        )
