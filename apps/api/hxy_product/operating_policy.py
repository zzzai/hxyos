from __future__ import annotations

from dataclasses import dataclass
from math import isfinite
from typing import Any, Collection, Literal, Mapping


PolicyAction = Literal[
    "auto_accept",
    "request_missing",
    "require_confirmation",
    "escalate",
]
Severity = Literal["low", "medium", "high", "critical"]

CRITICAL_RISK_MARKERS = frozenset(
    {
        "safety",
        "injury",
        "person_injury",
    }
)
HIGH_RISK_MARKERS = frozenset(
    {
        "permit",
        "compliance",
        "major_budget",
        "major_complaint",
        "medical_claim",
        "core_brand_conflict",
    }
)


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    action: PolicyAction
    severity: Severity
    missing_fields: tuple[str, ...]
    policy_version: str = "issue-intake.v1"


def _normalized_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip().lower()


def _risk_flags(value: Any) -> tuple[frozenset[str], bool]:
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(), False

    normalized: set[str] = set()
    for item in value:
        marker = _normalized_text(item)
        if not marker:
            return frozenset(), False
        normalized.add(marker)
    return frozenset(normalized), True


def _confidence(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        return None
    if not isfinite(normalized) or not 0 <= normalized <= 1:
        return None
    return normalized


def _has_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def evaluate_issue_proposal(
    *,
    proposal: Mapping[str, Any],
    published_event_types: Collection[str],
    assignment_is_active: bool,
) -> PolicyDecision:
    event_type = _normalized_text(proposal.get("event_type"))
    risk_flags, risk_flags_are_valid = _risk_flags(proposal.get("risk_flags"))
    risk_markers = risk_flags | ({event_type} if event_type else set())

    if risk_markers & CRITICAL_RISK_MARKERS:
        return PolicyDecision("escalate", "critical", ())
    if risk_markers & HIGH_RISK_MARKERS:
        return PolicyDecision("escalate", "high", ())

    if not assignment_is_active:
        return PolicyDecision("require_confirmation", "medium", ())

    missing_fields: list[str] = []
    if not _normalized_text(proposal.get("location")):
        missing_fields.append("location")
    if not _normalized_text(proposal.get("acceptance_criteria")):
        missing_fields.append("acceptance_criteria")
    if not _has_value(proposal.get("suggested_owner_assignment_id")):
        missing_fields.append("owner_assignment_id")
    if missing_fields:
        return PolicyDecision("request_missing", "low", tuple(missing_fields))

    confidence = _confidence(proposal.get("confidence"))
    normalized_event_types = {
        normalized
        for value in published_event_types
        if (normalized := _normalized_text(value))
    }
    if (
        not event_type
        or event_type not in normalized_event_types
        or confidence is None
        or confidence < 0.75
    ):
        return PolicyDecision("require_confirmation", "medium", ())

    if risk_flags_are_valid and not risk_flags and confidence >= 0.85:
        return PolicyDecision("auto_accept", "low", ())

    return PolicyDecision("require_confirmation", "medium", ())
