from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping

from apps.api.hxy_knowledge.compliance_rules import check_brand_risk_text


_ANSWER_AUTHORITIES = {"approved", "candidate", "reference", "insufficient"}
_EVIDENCE_AUTHORITIES = {
    "approved",
    "action_asset",
    "candidate",
    "reference",
    "private_reference",
    "process",
}
_POLICY_ACTIONS = {"answer", "needs_review", "deny"}
_GUARDRAIL_ACTIONS = {"send", "revise_or_review", "deny"}
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")
_PRIVATE_MARKERS = (
    "/root/",
    "/home/",
    "knowledge/raw",
    "password=",
    "api_key",
    "session_grant",
    "authorization: bearer",
)
_PRIVATE_KEYS = {
    "answer",
    "authorization",
    "content",
    "cookie",
    "credential",
    "path",
    "prompt",
    "query",
    "secret",
    "session",
    "session_grant",
}


def _bounded_text(name: str, value: str, *, maximum: int = 160) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} is invalid")
    return normalized


@dataclass(frozen=True)
class SemanticAnswerRun:
    case_id: str
    provider_name: str
    provider_version: str
    answer: str = field(repr=False, compare=False)
    answer_authority: str = "insufficient"
    evidence_ids: tuple[str, ...] = ()
    evidence_authorities: tuple[str, ...] = ()
    citations: tuple[str, ...] = ()
    declared_outcomes: tuple[str, ...] = ()
    policy_action: str = "needs_review"
    guardrail_action: str = "revise_or_review"
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_microunits: int = 0
    safe_trace: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("case_id", "provider_name", "provider_version"):
            object.__setattr__(
                self,
                name,
                _bounded_text(name, str(getattr(self, name))),
            )
        if self.answer_authority not in _ANSWER_AUTHORITIES:
            raise ValueError("answer_authority is invalid")
        if any(item not in _EVIDENCE_AUTHORITIES for item in self.evidence_authorities):
            raise ValueError("evidence_authority is invalid")
        if self.policy_action not in _POLICY_ACTIONS:
            raise ValueError("policy_action is invalid")
        if self.guardrail_action not in _GUARDRAIL_ACTIONS:
            raise ValueError("guardrail_action is invalid")
        for name in ("latency_ms", "input_tokens", "output_tokens", "cost_microunits"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} is invalid")


def _canonical_sha256(payload: Any) -> str:
    serialized = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(serialized).hexdigest()


def _contains_private(value: Any, *, key: str | None = None) -> bool:
    if key is not None:
        normalized_key = key.lower()
        if normalized_key in _PRIVATE_KEYS or normalized_key.endswith("_path"):
            return True
    if isinstance(value, Mapping):
        return any(
            _contains_private(item, key=str(item_key))
            for item_key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_private(item) for item in value)
    if isinstance(value, str):
        normalized = value.lower().replace("\\", "/")
        return (
            normalized.startswith("/")
            or normalized.startswith("file:/")
            or bool(re.match(r"^[a-z]:/", normalized))
            or any(marker in normalized for marker in _PRIVATE_MARKERS)
        )
    return False


def _answer_contains_private_marker(answer: str) -> bool:
    normalized = answer.lower().replace("\\", "/")
    return (
        "source_path" in normalized
        or "chunk_id" in normalized
        or _contains_private(normalized)
    )


def _safe_label(value: str, fallback: str = "redacted") -> str:
    normalized = str(value or "").strip()[:160]
    if not _SAFE_ID.fullmatch(normalized) or _contains_private(normalized):
        return fallback
    return normalized


def _safe_known_ids(values: tuple[str, ...], known_ids: set[str]) -> list[str]:
    return [
        value
        for value in values
        if value in known_ids
        and _SAFE_ID.fullmatch(value)
        and not _contains_private(value)
    ]


def _missing_result(case: Mapping[str, Any]) -> dict[str, Any]:
    hard_gates = {
        "answer_present": False,
        "evidence_scope": False,
        "authority_alignment": False,
        "delivery_policy": False,
        "citation_coverage": False,
        "outcome_declarations": False,
        "risk_pattern_clear": False,
        "trace_privacy": False,
    }
    return {
        "case_id": _safe_label(str(case.get("case_id") or "")),
        "role": _safe_label(str(case.get("role") or "")),
        "deterministic_status": "failed",
        "reason_codes": ["missing_answer_run"],
        "hard_gates": hard_gates,
        "budget_checks": {"latency": False, "tokens": False, "cost": False},
        "answer_sha256": None,
        "provider": {"name": "missing", "version": "missing"},
        "answer_authority": "insufficient",
        "evidence_ids": [],
        "redacted_evidence_count": 0,
        "usage": {
            "latency_ms": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost_microunits": 0,
        },
    }


def _evaluate_case(
    case: Mapping[str, Any],
    rubric_case: Mapping[str, Any],
    run: SemanticAnswerRun,
) -> dict[str, Any]:
    allowed_ids = {str(item) for item in case.get("allowed_evidence_ids") or []}
    forbidden_ids = {str(item) for item in case.get("forbidden_evidence_ids") or []}
    evidence_ids = set(run.evidence_ids)
    citations = set(run.citations)
    required_outcomes = {
        str(item) for item in rubric_case.get("required_outcomes") or []
    }
    declared_outcomes = set(run.declared_outcomes)
    compliance_hits = check_brand_risk_text(run.answer).get("hits") or []
    expected_authority = str(case.get("expected_authority") or "")
    evidence_authority_aligned = (
        len(run.evidence_ids) == len(run.evidence_authorities)
        and (
            expected_authority != "approved"
            or all(
                authority in {"approved", "action_asset"}
                for authority in run.evidence_authorities
            )
        )
    )
    delivery_policy_aligned = (
        run.policy_action == "answer" and run.guardrail_action == "send"
        if expected_authority == "approved"
        else run.policy_action in {"needs_review", "deny"}
        and run.guardrail_action in {"revise_or_review", "deny"}
    )
    hard_gates = {
        "answer_present": bool(run.answer.strip()),
        "evidence_scope": bool(evidence_ids) and evidence_ids <= allowed_ids,
        "authority_alignment": (
            run.answer_authority == expected_authority
            and evidence_authority_aligned
        ),
        "delivery_policy": delivery_policy_aligned,
        "citation_coverage": (
            bool(citations)
            and evidence_ids <= citations
            and citations <= allowed_ids
        ),
        "outcome_declarations": (
            bool(required_outcomes)
            and declared_outcomes == required_outcomes
        ),
        "risk_pattern_clear": not compliance_hits,
        "trace_privacy": (
            not _contains_private(run.safe_trace)
            and not _answer_contains_private_marker(run.answer)
        ),
    }
    budget = case.get("budget") or {}
    total_tokens = run.input_tokens + run.output_tokens
    budget_checks = {
        "latency": run.latency_ms <= int(budget.get("max_latency_ms") or 0),
        "tokens": total_tokens <= int(budget.get("max_tokens") or 0),
        "cost": run.cost_microunits <= int(budget.get("max_cost_microunits") or 0),
    }
    passed = all(hard_gates.values()) and all(budget_checks.values())
    reason_codes = [name for name, value in hard_gates.items() if not value]
    reason_codes.extend(
        f"budget_{name}" for name, value in budget_checks.items() if not value
    )
    safe_evidence_ids = _safe_known_ids(
        run.evidence_ids,
        allowed_ids | forbidden_ids,
    )
    return {
        "case_id": _safe_label(run.case_id),
        "role": _safe_label(str(case.get("role") or "")),
        "deterministic_status": "passed" if passed else "failed",
        "reason_codes": reason_codes,
        "hard_gates": hard_gates,
        "budget_checks": budget_checks,
        "answer_sha256": hashlib.sha256(run.answer.encode("utf-8")).hexdigest(),
        "provider": {
            "name": _safe_label(run.provider_name),
            "version": _safe_label(run.provider_version),
        },
        "answer_authority": run.answer_authority,
        "evidence_ids": safe_evidence_ids,
        "redacted_evidence_count": len(run.evidence_ids) - len(safe_evidence_ids),
        "usage": {
            "latency_ms": run.latency_ms,
            "input_tokens": run.input_tokens,
            "output_tokens": run.output_tokens,
            "total_tokens": total_tokens,
            "cost_microunits": run.cost_microunits,
        },
    }


def evaluate_deterministic_semantics(
    benchmark: Mapping[str, Any],
    rubric: Mapping[str, Any],
    answer_runs: Mapping[str, SemanticAnswerRun],
) -> dict[str, Any]:
    rubric_by_case = {
        str(item.get("case_id") or ""): item
        for item in rubric.get("cases") or []
        if isinstance(item, Mapping)
    }
    results: list[dict[str, Any]] = []
    for case in benchmark.get("cases") or []:
        case_id = str(case.get("case_id") or "")
        run = answer_runs.get(case_id)
        rubric_case = rubric_by_case.get(case_id, {})
        if run is None or not rubric_case:
            results.append(_missing_result(case))
            continue
        if run.case_id != case_id:
            results.append(_missing_result(case))
            continue
        results.append(_evaluate_case(case, rubric_case, run))

    pass_count = sum(item["deterministic_status"] == "passed" for item in results)
    case_count = len(results)
    return {
        "version": "hxy-semantic-benchmark-report.v1",
        "mode": "deterministic_semantic_baseline",
        "benchmark_sha256": _canonical_sha256(dict(benchmark)),
        "rubric_sha256": _canonical_sha256(dict(rubric)),
        "case_count": case_count,
        "answer_run_count": len(answer_runs),
        "deterministic_pass_count": pass_count,
        "deterministic_fail_count": case_count - pass_count,
        "deterministic_pass_rate": (
            round(pass_count / case_count, 4) if case_count else 0.0
        ),
        "semantic_status": "deterministic_only",
        "semantic_evaluated_count": 0,
        "quality_claim_allowed": False,
        "cases": results,
    }
