from __future__ import annotations

from typing import Any


class AssignmentKnowledgeRepository:
    def __init__(
        self,
        base_repository: Any,
        material_repository: Any,
        *,
        assignment_id: str,
    ) -> None:
        self.base_repository = base_repository
        self.material_repository = material_repository
        self.assignment_id = assignment_id
        self._last_items: list[dict[str, Any]] = []

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
        formal_items = self.base_repository.search(
            query,
            domain=domain,
            stage=stage,
            limit=limit,
            domain_hint=domain_hint,
        )
        private_items = self.material_repository.search_material_chunks(
            self.assignment_id,
            query,
            domain_hint=domain or domain_hint,
            limit=min(limit, 8),
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
            if len(items) >= limit:
                break
        self._last_items = items
        return items

    def retrieval_trace(self) -> dict[str, int]:
        return {
            "retrieval_count": len(self._last_items),
            "private_material_count": sum(
                1
                for item in self._last_items
                if item.get("source_type") == "private_material"
            ),
        }
