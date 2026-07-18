from __future__ import annotations

from typing import Any

from apps.api.hxy_product.operating_policy import evaluate_issue_proposal


def proposal(**overrides: Any) -> dict[str, Any]:
    value: dict[str, Any] = {
        "event_type": "facility_defect",
        "confidence": 0.92,
        "risk_flags": [],
        "location": "前台",
        "acceptance_criteria": "更换后灯光稳定",
        "suggested_owner_assignment_id": "manager-id",
    }
    value.update(overrides)
    return value


def evaluate(value: dict[str, Any], *, assignment_is_active: bool = True):
    return evaluate_issue_proposal(
        proposal=value,
        published_event_types={"facility_defect", "safety", "permit"},
        assignment_is_active=assignment_is_active,
    )


def test_low_risk_high_confidence_issue_auto_advances() -> None:
    decision = evaluate(proposal())

    assert decision.action == "auto_accept"
    assert decision.severity == "low"
    assert decision.missing_fields == ()
    assert decision.policy_version == "issue-intake.v1"


def test_safety_or_injury_never_auto_advances() -> None:
    decision = evaluate(
        proposal(
            event_type="safety",
            confidence=0.99,
            risk_flags=["person_injury"],
            location="施工区",
            acceptance_criteria="完成安全处理",
        )
    )

    assert decision.action == "escalate"
    assert decision.severity == "critical"


def test_governed_high_risk_markers_escalate_without_becoming_critical() -> None:
    decision = evaluate(proposal(event_type="permit", risk_flags=["permit"]))

    assert decision.action == "escalate"
    assert decision.severity == "high"


def test_escalation_precedes_assignment_and_missing_field_checks() -> None:
    decision = evaluate(
        proposal(
            event_type="safety",
            risk_flags=["safety"],
            location="",
            acceptance_criteria="",
            suggested_owner_assignment_id=None,
        ),
        assignment_is_active=False,
    )

    assert decision.action == "escalate"
    assert decision.severity == "critical"
    assert decision.missing_fields == ()


def test_inactive_or_unmapped_assignment_requires_confirmation_before_questions() -> None:
    decision = evaluate(
        proposal(
            location="",
            acceptance_criteria="",
            suggested_owner_assignment_id=None,
        ),
        assignment_is_active=False,
    )

    assert decision.action == "require_confirmation"
    assert decision.severity == "medium"
    assert decision.missing_fields == ()


def test_only_blocking_missing_fields_are_requested_in_stable_order() -> None:
    decision = evaluate(
        proposal(
            confidence=0.81,
            location=" ",
            acceptance_criteria="",
            suggested_owner_assignment_id=None,
            optional_note="not blocking",
        )
    )

    assert decision.action == "request_missing"
    assert decision.severity == "low"
    assert decision.missing_fields == (
        "location",
        "acceptance_criteria",
        "owner_assignment_id",
    )


def test_unpublished_event_type_requires_confirmation() -> None:
    decision = evaluate(proposal(event_type="unpublished_type", confidence=0.99))

    assert decision.action == "require_confirmation"
    assert decision.severity == "medium"


def test_confidence_below_point_seven_five_requires_confirmation() -> None:
    decision = evaluate(proposal(confidence=0.7499))

    assert decision.action == "require_confirmation"
    assert decision.severity == "medium"


def test_point_eight_five_is_the_auto_accept_boundary() -> None:
    assert evaluate(proposal(confidence=0.85)).action == "auto_accept"
    assert evaluate(proposal(confidence=0.8499)).action == "require_confirmation"


def test_unknown_risk_flag_never_auto_advances() -> None:
    decision = evaluate(proposal(confidence=0.99, risk_flags=["new_unmapped_risk"]))

    assert decision.action == "require_confirmation"
    assert decision.severity == "medium"


def test_malformed_confidence_fails_closed() -> None:
    decision = evaluate(proposal(confidence="not-a-number"))

    assert decision.action == "require_confirmation"
    assert decision.severity == "medium"
