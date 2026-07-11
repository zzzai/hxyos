from __future__ import annotations

import pytest

from apps.api.hxy_engines.adapters.current_retrieval import CurrentRetrievalEngine
from apps.api.hxy_engines.contracts import EngineBudget, EngineContext
from apps.api.hxy_engines.retrieval import RetrievalRequest


def _context(**overrides) -> EngineContext:
    payload = {
        "request_id": "request-retrieval-001",
        "trace_id": "trace-retrieval-001",
        "account_id": "account-001",
        "assignment_id": "assignment-001",
        "organization_id": "organization-001",
        "store_id": "store-001",
        "purpose": "answer_retrieval",
        "authority_policy": "approved_plus_reference",
        "budget": EngineBudget(max_latency_ms=15_000),
    }
    payload.update(overrides)
    return EngineContext(**payload)


def _request(**overrides) -> RetrievalRequest:
    payload = {
        "query": "首店接待怎么做",
        "assignment_id": "assignment-001",
        "organization_id": "organization-001",
        "store_id": "store-001",
        "limit": 5,
        "domain": "operations",
        "stage": None,
        "domain_hint": "operations",
    }
    payload.update(overrides)
    return RetrievalRequest(**payload)


class FormalRepository:
    def __init__(self) -> None:
        self.calls = []

    def search(self, query, **kwargs):
        self.calls.append((query, kwargs))
        return [
            {
                "chunk_id": "formal-001",
                "title": "/root/hxy/knowledge/approved/接待标准.md",
                "source_path": "/root/hxy/knowledge/approved/接待标准.md",
                "content": "先询问顾客状态。",
                "status": "approved",
                "score": 100,
                "source_type": "approved_knowledge",
            }
        ]


class MaterialRepository:
    def __init__(self) -> None:
        self.calls = []

    def search_material_chunks(self, assignment_id, query, **kwargs):
        self.calls.append((assignment_id, query, kwargs))
        return [
            {
                "chunk_id": "private-001",
                "material_id": "material-001",
                "title": "首店接待草稿.md",
                "source_path": "material:material-001",
                "source_url": "/api/v1/materials/70000000-0000-0000-0000-000000000001/content",
                "content": "接待草稿仅供当前岗位参考。",
                "status": "reference",
                "score": 120,
                "source_type": "private_material",
                "official_use_allowed": False,
            }
        ]


def test_retrieval_scope_is_checked_before_any_repository_call() -> None:
    formal = FormalRepository()
    materials = MaterialRepository()
    engine = CurrentRetrievalEngine(formal, materials)

    for request in (
        _request(assignment_id="assignment-other"),
        _request(organization_id="organization-other"),
        _request(store_id="store-other"),
    ):
        with pytest.raises(PermissionError, match="scope"):
            engine.execute(_context(), request)

    assert formal.calls == []
    assert materials.calls == []


def test_current_retrieval_uses_only_context_assignment_and_bounds_results() -> None:
    formal = FormalRepository()
    materials = MaterialRepository()
    result = CurrentRetrievalEngine(formal, materials).execute(
        _context(),
        _request(),
    )

    assert result.status == "succeeded"
    assert materials.calls[0][0] == "assignment-001"
    assert len(result.private_output) == 2
    assert result.private_output[0]["chunk_id"] == "private-001"
    assert [item.authority for item in result.artifacts] == [
        "private_reference",
        "reference",
    ]
    assert result.policy_decisions[0].reason_code == "scope_verified_before_retrieval"


def test_retrieval_trace_never_exposes_private_content_or_server_paths() -> None:
    result = CurrentRetrievalEngine(
        FormalRepository(),
        MaterialRepository(),
    ).execute(_context(), _request())

    trace = str(result.as_trace_record())
    assert "/root/hxy" not in trace
    assert "接待草稿仅供当前岗位参考" not in trace
    assert "material:material-001" not in trace
    assert {item.artifact_id for item in result.artifacts} == {
        "formal-001",
        "private-001",
    }


def test_retrieval_request_requires_explicit_scope_and_bounded_limit() -> None:
    for overrides in (
        {"assignment_id": ""},
        {"organization_id": ""},
        {"limit": 0},
        {"limit": 51},
        {"query": ""},
    ):
        with pytest.raises(ValueError):
            _request(**overrides)
