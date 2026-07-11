from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .contracts import EngineContext, EngineResult


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    assignment_id: str
    organization_id: str
    store_id: str | None
    limit: int = 20
    domain: str | None = None
    stage: str | None = None
    domain_hint: str | None = None

    def __post_init__(self) -> None:
        for name in ("query", "assignment_id", "organization_id"):
            value = getattr(self, name).strip()
            if not value or len(value) > 500:
                raise ValueError(f"{name} is invalid")
            object.__setattr__(self, name, value)
        if self.store_id is not None:
            store_id = self.store_id.strip()
            if not store_id or len(store_id) > 160:
                raise ValueError("store_id is invalid")
            object.__setattr__(self, "store_id", store_id)
        if not 1 <= self.limit <= 50:
            raise ValueError("limit is invalid")


class RetrievalEngine(Protocol):
    def execute(
        self,
        context: EngineContext,
        request: RetrievalRequest,
    ) -> EngineResult:
        ...
