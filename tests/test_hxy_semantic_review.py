from __future__ import annotations

import json
from pathlib import Path

from apps.api.hxy_engines.semantic_benchmark import (
    HumanSemanticReview,
    apply_human_calibration,
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


def _calibration() -> dict:
    return json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))


def _deterministic_report() -> dict:
    return {
        "version": "hxy-semantic-benchmark-report.v1",
        "case_count": 50,
        "deterministic_pass_count": 40,
        "deterministic_fail_count": 10,
        "semantic_status": "deterministic_only",
        "semantic_evaluated_count": 0,
        "quality_claim_allowed": False,
        "cases": [
            {
                "case_id": case_id,
                "deterministic_status": "passed",
                "hard_gates": {"risk_pattern_clear": True},
            }
            for case_id in _calibration()["case_ids"]
        ],
    }


def _review(case_id: str, reviewer_id: str, score: int = 4, **overrides) -> HumanSemanticReview:
    scores = {dimension: score for dimension in DIMENSIONS}
    scores.update(overrides)
    return HumanSemanticReview(
        case_id=case_id,
        reviewer_id=reviewer_id,
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

    assert report["semantic_status"] == "human_calibrated"
    assert report["semantic_evaluated_count"] == 10
    assert report["human_calibration"]["accepted_case_count"] == 10
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
    assert set(review["properties"]["scores"]["required"]) == set(DIMENSIONS)
    assert review["properties"]["scores"]["additionalProperties"] is False
