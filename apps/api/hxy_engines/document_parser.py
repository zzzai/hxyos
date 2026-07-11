from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Protocol

from .contracts import EngineContext, EngineResult


@dataclass(frozen=True)
class DocumentParseRequest:
    source_id: str
    storage_ref: str
    media_type: str
    parser_strategy: str

    def __post_init__(self) -> None:
        for name in ("source_id", "media_type", "parser_strategy"):
            value = getattr(self, name).strip()
            if not value or len(value) > 200:
                raise ValueError(f"{name} is invalid")
            object.__setattr__(self, name, value)
        normalized_ref = self.storage_ref.strip().replace("\\", "/")
        path = PurePosixPath(normalized_ref)
        if (
            not normalized_ref
            or path.is_absolute()
            or ".." in path.parts
            or len(normalized_ref) > 500
        ):
            raise ValueError("storage_ref is invalid")
        object.__setattr__(self, "storage_ref", path.as_posix())


class DocumentParser(Protocol):
    def execute(
        self,
        context: EngineContext,
        request: DocumentParseRequest,
    ) -> EngineResult:
        ...
