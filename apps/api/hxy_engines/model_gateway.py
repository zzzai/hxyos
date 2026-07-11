from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .contracts import EngineContext, EngineResult


@dataclass(frozen=True)
class ModelRequest:
    task_type: str
    messages: tuple[dict[str, Any], ...] = ()
    prompt: str | None = None
    metadata_keys: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        task_type = self.task_type.strip()
        if not task_type or len(task_type) > 120:
            raise ValueError("task_type is invalid")
        object.__setattr__(self, "task_type", task_type)
        if not self.messages and not (self.prompt or "").strip():
            raise ValueError("model request requires messages or prompt")
        object.__setattr__(
            self,
            "metadata_keys",
            tuple(sorted({item.strip() for item in self.metadata_keys if item.strip()})),
        )


class ModelGateway(Protocol):
    def execute(self, context: EngineContext, request: ModelRequest) -> EngineResult:
        ...
