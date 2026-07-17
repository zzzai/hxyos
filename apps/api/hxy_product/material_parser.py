from __future__ import annotations

from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from typing import Any
from uuid import UUID

from hxy_knowledge.image_adapter import IMAGE_SUFFIXES, ImageAdapterError, recognize_image


@dataclass(frozen=True)
class MaterialParseResult:
    text_content: str
    title: str | None
    parser_name: str
    parser_version: str
    warnings: tuple[str, ...]
    quality: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)


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


def parse_material(path: Path) -> MaterialParseResult:
    source = path.resolve()
    if source.suffix.lower() not in IMAGE_SUFFIXES:
        return parse_with_markitdown(source)
    try:
        recognized = recognize_image(source)
    except ImageAdapterError as error:
        raise MaterialParseError(
            error.code,
            "image OCR and visual understanding did not complete",
            retryable=error.retryable,
        ) from error
    if recognized.quality.get("status") == "unusable":
        raise MaterialParseError(
            "image_quality_gate_failed",
            "image OCR and visual understanding produced no usable reference",
            retryable=False,
        )
    return MaterialParseResult(
        text_content=recognized.text_content,
        title=recognized.title,
        parser_name=recognized.parser_name,
        parser_version=recognized.parser_version,
        warnings=recognized.warnings,
        quality=dict(recognized.quality),
        metadata=dict(recognized.metadata),
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
