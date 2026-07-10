from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from uuid import UUID


@dataclass(frozen=True)
class MaterialParseResult:
    text_content: str
    title: str | None
    parser_name: str
    parser_version: str
    warnings: tuple[str, ...]


class MaterialParseError(Exception):
    def __init__(self, code: str, message: str, *, retryable: bool) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


def _package_version() -> str:
    try:
        return version("markitdown")
    except PackageNotFoundError:
        return "unknown"


def parse_with_markitdown(path: Path) -> MaterialParseResult:
    source = path.resolve()
    if not source.is_file():
        raise MaterialParseError(
            "source_missing",
            "material source does not exist",
            retryable=False,
        )
    try:
        from markitdown import MarkItDown
    except ImportError as error:
        raise MaterialParseError(
            "parser_dependency_missing",
            "markitdown is not installed",
            retryable=True,
        ) from error

    try:
        converted = MarkItDown(enable_builtins=True).convert(source)
    except OSError as error:
        raise MaterialParseError(
            "parser_io_error",
            "markitdown could not read the material",
            retryable=True,
        ) from error
    except Exception as error:
        raise MaterialParseError(
            "parser_error",
            "markitdown could not parse the material",
            retryable=True,
        ) from error

    text = str(getattr(converted, "markdown", None) or "").strip()
    if not text:
        raise MaterialParseError(
            "empty_parse_output",
            "markitdown produced no usable text",
            retryable=False,
        )
    title_value = str(getattr(converted, "title", None) or "").strip()
    return MaterialParseResult(
        text_content=text,
        title=title_value or None,
        parser_name="markitdown",
        parser_version=_package_version(),
        warnings=(),
    )


def build_artifact_storage_keys(
    assignment_id: str,
    material_id: str,
    job_id: str,
) -> dict[str, str]:
    normalized = [str(UUID(value)) for value in (assignment_id, material_id, job_id)]
    assignment, material, job = normalized
    prefix = f"{assignment}/{material}/derived/{job}"
    return {
        "normalized_markdown": f"{prefix}/normalized.md",
        "source_card": f"{prefix}/source-card.json",
    }
