from __future__ import annotations

from time import perf_counter
from typing import Any

from ..contracts import (
    EngineArtifact,
    EngineContext,
    EnginePolicyDecision,
    EngineResult,
)
from ..retrieval import RetrievalRequest


def _scope_matches(context: EngineContext, request: RetrievalRequest) -> bool:
    return (
        context.assignment_id == request.assignment_id
        and context.organization_id == request.organization_id
        and context.store_id == request.store_id
    )


def _artifact_id(item: dict[str, Any], request_id: str, index: int) -> str:
    for key in ("chunk_id", "material_id", "asset_id", "claim_id"):
        value = str(item.get(key) or "").strip()
        if value and "/" not in value and "\\" not in value:
            return value[:160]
    return f"{request_id}:retrieval:{index}"


def _provenance_ids(item: dict[str, Any]) -> tuple[str, ...]:
    values: list[str] = []
    for key in ("material_id", "asset_id", "claim_id", "answer_card_id"):
        value = str(item.get(key) or "").strip()
        if value and "/" not in value and "\\" not in value and value not in values:
            values.append(value[:160])
    return tuple(values)


class CurrentRetrievalEngine:
    engine_name = "current-assignment-retrieval"
    engine_version = "v1"

    def __init__(self, base_repository: Any, material_repository: Any) -> None:
        self.base_repository = base_repository
        self.material_repository = material_repository

    def execute(
        self,
        context: EngineContext,
        request: RetrievalRequest,
    ) -> EngineResult:
        if not _scope_matches(context, request):
            raise PermissionError("retrieval scope does not match engine context")

        started = perf_counter()
        formal_items = self.base_repository.search(
            request.query,
            domain=request.domain,
            stage=request.stage,
            limit=request.limit,
            domain_hint=request.domain_hint,
        )
        private_items = self.material_repository.search_material_chunks(
            context.assignment_id,
            request.query,
            domain_hint=request.domain or request.domain_hint,
            limit=min(request.limit, 8),
        )
        combined = [*formal_items, *private_items]
        combined.sort(
            key=lambda item: (
                int(item.get("score") or 0),
                item.get("source_type") == "private_material",
            ),
            reverse=True,
        )
        seen: set[str] = set()
        items: list[dict[str, Any]] = []
        for item in combined:
            key = str(item.get("chunk_id") or item.get("source_path") or "")
            if not key or key in seen:
                continue
            seen.add(key)
            items.append(item)
            if len(items) >= request.limit:
                break

        artifacts = tuple(
            EngineArtifact(
                artifact_id=_artifact_id(item, context.request_id, index),
                kind="retrieved_evidence",
                authority=(
                    "private_reference"
                    if item.get("source_type") == "private_material"
                    else "reference"
                ),
                provenance_ids=_provenance_ids(item),
            )
            for index, item in enumerate(items)
        )
        return EngineResult(
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            status="succeeded",
            artifacts=artifacts,
            latency_ms=max(0, round((perf_counter() - started) * 1000)),
            policy_decisions=(
                EnginePolicyDecision(
                    policy="retrieval_scope",
                    outcome="allow",
                    reason_code="scope_verified_before_retrieval",
                ),
            ),
            private_output=items,
        )
