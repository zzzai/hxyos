from __future__ import annotations

import pytest

from apps.api.hxy_engines.contracts import (
    EngineArtifact,
    EngineBudget,
    EngineContext,
    EnginePolicyDecision,
    EngineResult,
    EngineUsage,
)


def _context(**overrides) -> EngineContext:
    payload = {
        "request_id": "request-001",
        "trace_id": "trace-001",
        "account_id": "account-001",
        "assignment_id": "assignment-001",
        "organization_id": "organization-001",
        "store_id": None,
        "purpose": "answer_synthesis",
        "authority_policy": "approved_plus_reference",
        "budget": EngineBudget(
            max_latency_ms=60_000,
            max_tokens=8_000,
            max_cost_microunits=2_000_000,
        ),
    }
    payload.update(overrides)
    return EngineContext(**payload)


def test_engine_context_requires_governed_identity_scope_and_budget() -> None:
    context = _context(store_id="store-001")

    assert context.assignment_id == "assignment-001"
    assert context.store_id == "store-001"
    assert context.budget.max_tokens == 8_000

    for field in (
        "request_id",
        "trace_id",
        "account_id",
        "assignment_id",
        "organization_id",
        "purpose",
    ):
        with pytest.raises(ValueError, match=field):
            _context(**{field: " "})

    with pytest.raises(ValueError, match="authority_policy"):
        _context(authority_policy="anything_goes")


def test_engine_context_cannot_carry_raw_credentials_by_construction() -> None:
    with pytest.raises(TypeError):
        EngineContext(
            request_id="request-001",
            trace_id="trace-001",
            account_id="account-001",
            assignment_id="assignment-001",
            organization_id="organization-001",
            store_id=None,
            purpose="answer_synthesis",
            authority_policy="approved_only",
            budget=EngineBudget(max_latency_ms=10_000),
            api_key="secret",  # type: ignore[call-arg]
        )


def test_engine_budget_is_bounded() -> None:
    for kwargs in (
        {"max_latency_ms": 0},
        {"max_latency_ms": 600_001},
        {"max_latency_ms": 1_000, "max_tokens": -1},
        {"max_latency_ms": 1_000, "max_tokens": 2_000_001},
        {"max_latency_ms": 1_000, "max_cost_microunits": -1},
    ):
        with pytest.raises(ValueError):
            EngineBudget(**kwargs)


def test_engine_artifacts_cannot_claim_formal_authority() -> None:
    reference = EngineArtifact(
        artifact_id="artifact-001",
        kind="retrieved_evidence",
        authority="reference",
        provenance_ids=("source-001",),
    )
    assert reference.authority == "reference"

    for authority in ("approved", "action_asset", "official"):
        with pytest.raises(ValueError, match="authority"):
            EngineArtifact(
                artifact_id="artifact-001",
                kind="retrieved_evidence",
                authority=authority,
            )


def test_engine_result_records_bounded_trace_metadata() -> None:
    artifact = EngineArtifact(
        artifact_id="artifact-001",
        kind="answer_draft",
        authority="candidate",
        provenance_ids=("evidence-001",),
    )
    result = EngineResult(
        engine_name="current-model-router",
        engine_version="v1",
        status="succeeded",
        artifacts=(artifact,),
        latency_ms=125,
        usage=EngineUsage(
            input_tokens=100,
            output_tokens=30,
            cost_microunits=200,
        ),
        policy_decisions=(
            EnginePolicyDecision(
                policy="knowledge_authority",
                outcome="allow",
                reason_code="reference_draft_only",
            ),
        ),
    )

    trace = result.as_trace_record()

    assert trace == {
        "engine_name": "current-model-router",
        "engine_version": "v1",
        "status": "succeeded",
        "artifact_count": 1,
        "artifact_authorities": ["candidate"],
        "latency_ms": 125,
        "usage": {
            "input_tokens": 100,
            "output_tokens": 30,
            "total_tokens": 130,
            "cost_microunits": 200,
        },
        "policy_decisions": [
            {
                "policy": "knowledge_authority",
                "outcome": "allow",
                "reason_code": "reference_draft_only",
            }
        ],
    }


def test_engine_result_rejects_invalid_status_and_negative_usage() -> None:
    with pytest.raises(ValueError, match="status"):
        EngineResult(
            engine_name="engine",
            engine_version="v1",
            status="unknown",
        )

    with pytest.raises(ValueError, match="input_tokens"):
        EngineUsage(input_tokens=-1)
