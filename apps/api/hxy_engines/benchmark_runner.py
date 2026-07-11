from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import Any, Mapping, Protocol

from apps.api.hxy_knowledge.compliance_rules import (
    check_brand_risk_text,
    load_brand_risk_rules,
)

from .adapters.current_retrieval import CurrentRetrievalEngine
from .contracts import EngineBudget, EngineContext
from .retrieval import RetrievalRequest


_ENGINE_ARTIFACT_AUTHORITIES = {
    "candidate",
    "reference",
    "private_reference",
    "process",
}
_SCOPE_RISKS = {
    "enforce_store_scope",
    "prevent_cross_assignment_leakage",
    "require_aggregate_permission",
}
_RISK_PROBES = {
    "block_medical_claim": ("我们的服务可以治疗失眠。", "医疗"),
    "block_guaranteed_effect": ("保证三天见效。", "保证"),
    "block_exaggerated_marketing": ("我们是行业第一。", "夸大"),
}
_PRIVATE_TRACE_KEYS = {
    "authorization",
    "content",
    "cookie",
    "credential",
    "file_path",
    "path",
    "prompt",
    "query",
    "request_body",
    "response_body",
    "secret",
    "session",
    "session_grant",
}
_PRIVATE_TRACE_MARKERS = (
    "/root/",
    "/home/",
    "knowledge/raw",
    "password=",
    "api_key",
    "session_grant",
    "authorization: bearer",
)
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}$")


@dataclass(frozen=True)
class CaseObservation:
    returned_evidence_ids: tuple[str, ...] = ()
    artifact_authorities: tuple[str, ...] = ()
    risk_probe_required: bool = False
    risk_probe_intercepted: bool = False
    write_attempted: bool = False
    scope_denied: bool = False
    latency_ms: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_microunits: int = 0
    trace_record: Mapping[str, Any] = field(default_factory=dict)


class ContractBaselineExecutor(Protocol):
    descriptor: Mapping[str, Any]

    def execute(self, case: Mapping[str, Any]) -> CaseObservation:
        ...


class _SyntheticEvidenceRepository:
    def __init__(
        self,
        allowed_ids: tuple[str, ...],
        forbidden_ids: tuple[str, ...],
        *,
        leak_forbidden_if_called: bool,
    ) -> None:
        self.allowed_ids = allowed_ids
        self.forbidden_ids = forbidden_ids
        self.leak_forbidden_if_called = leak_forbidden_if_called
        self.call_count = 0

    def search(self, *_args: Any, **_kwargs: Any) -> list[dict[str, Any]]:
        self.call_count += 1
        evidence_ids = (
            self.forbidden_ids
            if self.leak_forbidden_if_called
            else self.allowed_ids
        )
        return [
            {
                "chunk_id": evidence_id,
                "asset_id": evidence_id,
                "score": 100 - index,
                "source_type": "approved_knowledge",
            }
            for index, evidence_id in enumerate(evidence_ids)
        ]


class _AssignmentMaterialRepository:
    def __init__(self) -> None:
        self.call_count = 0

    def search_material_chunks(
        self,
        _assignment_id: str,
        _query: str,
        **_kwargs: Any,
    ) -> list[dict[str, Any]]:
        self.call_count += 1
        return []


def _risk_probe_result(risk_expectations: set[str]) -> tuple[bool, bool]:
    probes = [
        probe
        for risk_name, probe in _RISK_PROBES.items()
        if risk_name in risk_expectations
    ]
    if not probes:
        return False, False

    intercepted = True
    for text, expected_type in probes:
        result = check_brand_risk_text(text)
        hit_types = {str(hit.get("type") or "") for hit in result.get("hits") or []}
        intercepted = intercepted and expected_type in hit_types
    return True, intercepted


class CurrentContractBaselineExecutor:
    descriptor = {
        "name": "current-hxy-contract-baseline",
        "version": "engine-ports-v1",
    }

    def execute(self, case: Mapping[str, Any]) -> CaseObservation:
        scope = case["assignment_scope"]
        task = case["task"]
        budget = case["budget"]
        case_id = str(case["case_id"])
        risk_expectations = {str(item) for item in case["risk_expectations"]}
        allowed_ids = tuple(str(item) for item in case["allowed_evidence_ids"])
        forbidden_ids = tuple(str(item) for item in case["forbidden_evidence_ids"])

        context = EngineContext(
            request_id=f"benchmark:{case_id}",
            trace_id=f"benchmark-trace:{case_id}",
            account_id=f"benchmark-account:{case['role']}",
            assignment_id=str(scope["assignment_id"]),
            organization_id=str(scope["organization_id"]),
            store_id=scope["store_id"],
            purpose=str(task["purpose"]),
            authority_policy="approved_plus_reference",
            budget=EngineBudget(
                max_latency_ms=int(budget["max_latency_ms"]),
                max_tokens=int(budget["max_tokens"]),
                max_cost_microunits=int(budget["max_cost_microunits"]),
            ),
        )
        should_deny_scope = bool(risk_expectations & _SCOPE_RISKS)
        base_repository = _SyntheticEvidenceRepository(
            allowed_ids,
            forbidden_ids,
            leak_forbidden_if_called=should_deny_scope,
        )
        material_repository = _AssignmentMaterialRepository()
        engine = CurrentRetrievalEngine(base_repository, material_repository)
        request_assignment_id = str(scope["assignment_id"])
        request_store_id = scope["store_id"]
        aggregate_scope = "require_aggregate_permission" in risk_expectations
        if (
            not aggregate_scope
            and "enforce_store_scope" in risk_expectations
        ):
            request_store_id = f"foreign:{scope['store_id'] or 'organization'}"
        elif (
            not aggregate_scope
            and "prevent_cross_assignment_leakage" in risk_expectations
        ):
            request_assignment_id = f"foreign:{scope['assignment_id']}"
        request = RetrievalRequest(
            query=str(task["input"]),
            assignment_id=request_assignment_id,
            organization_id=str(scope["organization_id"]),
            store_id=request_store_id,
            limit=max(1, min(20, len(allowed_ids) or 1)),
            aggregate_scope=aggregate_scope,
        )

        scope_denied = False
        try:
            result = engine.execute(context, request)
        except PermissionError:
            scope_denied = True
            if base_repository.call_count or material_repository.call_count:
                raise RuntimeError("retrieval repositories were called before scope denial")
            returned_ids: tuple[str, ...] = ()
            authorities: tuple[str, ...] = ()
            latency_ms = 0
            trace_record: Mapping[str, Any] = {
                "engine_name": engine.engine_name,
                "engine_version": engine.engine_version,
                "status": "blocked",
                "artifact_count": 0,
                "artifact_authorities": [],
                "latency_ms": 0,
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "total_tokens": 0,
                    "cost_microunits": 0,
                },
                "policy_decisions": [
                    {
                        "policy": "retrieval_scope",
                        "outcome": "block",
                        "reason_code": "scope_mismatch_before_retrieval",
                    }
                ],
            }
        else:
            returned_ids = tuple(artifact.artifact_id for artifact in result.artifacts)
            authorities = tuple(artifact.authority for artifact in result.artifacts)
            latency_ms = result.latency_ms
            trace_record = result.as_trace_record()

        risk_required, risk_intercepted = _risk_probe_result(risk_expectations)
        return CaseObservation(
            returned_evidence_ids=returned_ids,
            artifact_authorities=authorities,
            risk_probe_required=risk_required,
            risk_probe_intercepted=risk_intercepted,
            write_attempted=False,
            scope_denied=scope_denied,
            latency_ms=latency_ms,
            input_tokens=0,
            output_tokens=0,
            cost_microunits=0,
            trace_record=trace_record,
        )


def _trace_is_private(value: Any, *, key: str | None = None) -> bool:
    if key is not None:
        normalized_key = key.lower()
        if normalized_key in _PRIVATE_TRACE_KEYS or normalized_key.endswith("_path"):
            return True
    if isinstance(value, Mapping):
        return any(
            _trace_is_private(item, key=str(item_key))
            for item_key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_trace_is_private(item) for item in value)
    if isinstance(value, str):
        normalized = value.lower().replace("\\", "/")
        return (
            normalized.startswith("/")
            or normalized.startswith("file:/")
            or bool(re.match(r"^[a-z]:/", normalized))
            or any(marker in normalized for marker in _PRIVATE_TRACE_MARKERS)
        )
    return False


def _safe_evidence_ids(
    values: tuple[str, ...],
    known_ids: set[str],
) -> list[str]:
    return [
        value
        for value in values
        if value in known_ids
        and _SAFE_ID.fullmatch(value)
        and not _trace_is_private(value)
    ]


def _safe_label(value: Any, *, maximum: int, fallback: str) -> str:
    normalized = str(value or "").strip()[:maximum]
    if not _SAFE_ID.fullmatch(normalized) or _trace_is_private(normalized):
        return fallback
    return normalized


def _safe_trace_summary(trace: Mapping[str, Any]) -> dict[str, Any]:
    usage = trace.get("usage") if isinstance(trace.get("usage"), Mapping) else {}
    decisions = trace.get("policy_decisions")
    return {
        "engine_name": _safe_label(
            trace.get("engine_name"), maximum=160, fallback="redacted"
        ),
        "engine_version": _safe_label(
            trace.get("engine_version"), maximum=120, fallback="redacted"
        ),
        "status": _safe_label(trace.get("status"), maximum=40, fallback="unknown"),
        "artifact_count": max(0, int(trace.get("artifact_count") or 0)),
        "latency_ms": max(0, int(trace.get("latency_ms") or 0)),
        "usage": {
            "input_tokens": max(0, int(usage.get("input_tokens") or 0)),
            "output_tokens": max(0, int(usage.get("output_tokens") or 0)),
            "total_tokens": max(0, int(usage.get("total_tokens") or 0)),
            "cost_microunits": max(0, int(usage.get("cost_microunits") or 0)),
        },
        "policy_decision_count": (
            len(decisions) if isinstance(decisions, (list, tuple)) else 0
        ),
    }


def _safe_descriptor(descriptor: Mapping[str, Any]) -> dict[str, str]:
    return {
        "name": _safe_label(descriptor.get("name"), maximum=160, fallback="redacted"),
        "version": _safe_label(
            descriptor.get("version"), maximum=120, fallback="redacted"
        ),
    }


def run_contract_baseline(
    benchmark: Mapping[str, Any],
    executor: ContractBaselineExecutor,
) -> dict[str, Any]:
    case_results: list[dict[str, Any]] = []
    for case in benchmark.get("cases") or []:
        observation = executor.execute(case)
        allowed_ids = {str(item) for item in case["allowed_evidence_ids"]}
        forbidden_ids = {str(item) for item in case["forbidden_evidence_ids"]}
        returned_ids = set(observation.returned_evidence_ids)
        risk_expectations = {str(item) for item in case["risk_expectations"]}
        scope_probe_required = bool(risk_expectations & _SCOPE_RISKS)
        risk_probe_required = bool(risk_expectations & set(_RISK_PROBES))
        evidence_boundary_passed = (
            observation.scope_denied and not returned_ids
            if scope_probe_required
            else bool(returned_ids) and returned_ids <= allowed_ids
        )
        authority_boundary_passed = (
            len(observation.artifact_authorities)
            == len(observation.returned_evidence_ids)
            and all(
                authority in _ENGINE_ARTIFACT_AUTHORITIES
                for authority in observation.artifact_authorities
            )
        )
        hard_gates = {
            "unauthorized_evidence_exposure": evidence_boundary_passed,
            "authority_state_violation": authority_boundary_passed,
            "prohibited_expression_miss": (
                not risk_probe_required
                or (
                    observation.risk_probe_required
                    and observation.risk_probe_intercepted
                )
            ),
            "unapproved_write": not observation.write_attempted,
            "trace_privacy": not _trace_is_private(observation.trace_record),
        }
        budget = case["budget"]
        total_tokens = observation.input_tokens + observation.output_tokens
        budget_checks = {
            "latency": 0 <= observation.latency_ms <= int(budget["max_latency_ms"]),
            "tokens": (
                observation.input_tokens >= 0
                and observation.output_tokens >= 0
                and total_tokens <= int(budget["max_tokens"])
            ),
            "cost": 0 <= observation.cost_microunits <= int(budget["max_cost_microunits"]),
        }
        contract_passed = all(hard_gates.values()) and all(budget_checks.values())
        safe_returned_ids = _safe_evidence_ids(
            observation.returned_evidence_ids,
            allowed_ids | forbidden_ids,
        )
        case_results.append(
            {
                "case_id": _safe_label(
                    case["case_id"], maximum=120, fallback="redacted"
                ),
                "role": _safe_label(case["role"], maximum=80, fallback="redacted"),
                "contract_status": "passed" if contract_passed else "failed",
                "hard_gates": hard_gates,
                "budget_checks": budget_checks,
                "scope_denied": observation.scope_denied,
                "returned_evidence_ids": safe_returned_ids,
                "redacted_evidence_count": (
                    len(observation.returned_evidence_ids)
                    - len(safe_returned_ids)
                ),
                "artifact_authorities": [
                    authority
                    if authority in _ENGINE_ARTIFACT_AUTHORITIES
                    else "invalid"
                    for authority in observation.artifact_authorities
                ],
                "risk_pattern_required": risk_probe_required,
                "risk_pattern_check_executed": observation.risk_probe_required,
                "risk_pattern_detected": (
                    observation.risk_probe_required
                    and observation.risk_probe_intercepted
                ),
                "usage": {
                    "latency_ms": max(0, observation.latency_ms),
                    "input_tokens": max(0, observation.input_tokens),
                    "output_tokens": max(0, observation.output_tokens),
                    "total_tokens": max(0, total_tokens),
                    "cost_microunits": max(0, observation.cost_microunits),
                },
                "trace": _safe_trace_summary(observation.trace_record),
            }
        )

    pass_count = sum(item["contract_status"] == "passed" for item in case_results)
    case_count = len(case_results)
    benchmark_json = json.dumps(
        benchmark,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    rules = load_brand_risk_rules()
    rules_json = json.dumps(
        rules.get("rules") or [],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    checker_metadata = check_brand_risk_text("")
    return {
        "version": "hxy-engine-benchmark-report.v1",
        "runner_version": "hxy-contract-baseline-runner.v1",
        "mode": "contract_baseline",
        "benchmark_id": _safe_label(
            benchmark.get("benchmark_id"), maximum=120, fallback="redacted"
        ),
        "benchmark_sha256": hashlib.sha256(benchmark_json).hexdigest(),
        "policy": {
            "checker_version": checker_metadata["version"],
            "rules_version": checker_metadata["rules_version"],
            "rules_status": checker_metadata["rules_status"],
            "rules_sha256": hashlib.sha256(rules_json).hexdigest(),
        },
        "engine": _safe_descriptor(executor.descriptor),
        "case_count": case_count,
        "contract_pass_count": pass_count,
        "contract_fail_count": case_count - pass_count,
        "contract_pass_rate": round(pass_count / case_count, 4) if case_count else 0.0,
        "semantic_status": "not_evaluated",
        "semantic_evaluated_count": 0,
        "quality_claim_allowed": False,
        "cases": case_results,
    }
