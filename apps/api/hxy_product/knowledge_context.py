from __future__ import annotations

from typing import Any

from hxy_engines.adapters.current_retrieval import CurrentRetrievalEngine
from hxy_engines.contracts import EngineContext
from hxy_engines.retrieval import RetrievalRequest


class AssignmentKnowledgeRepository:
    def __init__(
        self,
        base_repository: Any,
        material_repository: Any,
        *,
        engine_context: EngineContext,
        retrieval_engine: Any | None = None,
    ) -> None:
        self.base_repository = base_repository
        self.material_repository = material_repository
        self.engine_context = engine_context
        self.retrieval_engine = retrieval_engine or CurrentRetrievalEngine(
            base_repository,
            material_repository,
        )
        self._last_items: list[dict[str, Any]] = []
        self._last_engine_trace: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self.base_repository, name)

    def search(
        self,
        query: str,
        domain: str | None = None,
        stage: str | None = None,
        limit: int = 20,
        domain_hint: str | None = None,
    ) -> list[dict[str, Any]]:
        result = self.retrieval_engine.execute(
            self.engine_context,
            RetrievalRequest(
                query=query,
                assignment_id=self.engine_context.assignment_id,
                organization_id=self.engine_context.organization_id,
                store_id=self.engine_context.store_id,
                domain=domain,
                stage=stage,
                limit=limit,
                domain_hint=domain_hint,
            ),
        )
        items = list(result.private_output or [])
        self._last_items = items
        self._last_engine_trace = result.as_trace_record()
        return items

    def retrieval_trace(self) -> dict[str, Any]:
        return {
            "retrieval_count": len(self._last_items),
            "private_material_count": sum(
                1
                for item in self._last_items
                if item.get("source_type") == "private_material"
            ),
            "engine": self._last_engine_trace,
        }
