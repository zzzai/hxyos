"""Choose a document parser from cheap, explainable file signals.

This module deliberately stops before semantic understanding.  Its job is to
keep a lightweight parser as the default and reserve MinerU for documents
whose layout or OCR characteristics justify the extra cost.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile, is_zipfile


TEXT_COMPILER = "hxy_text_compiler"
MARKITDOWN = "markitdown"
MINERU = "mineru"
VISION = "ocr_or_vision"
MANUAL_REVIEW = "manual_review"

_TEXT_SUFFIXES = {".md", ".txt"}
_IMAGE_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
_PDF_SUFFIXES = {".pdf"}
_OFFICE_SUFFIXES = {".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx"}
_UNSUPPORTED_LEGACY_OFFICE_SUFFIXES = {".doc", ".ppt"}
_MARKITDOWN_ONLY_OFFICE_SUFFIXES = {".xls"}
_LIGHT_SUFFIXES = {".csv", ".epub", ".html", ".htm", ".json"}


def _pdf_has_image(page: Any) -> bool:
    try:
        resources = page.get("/Resources") or {}
        if hasattr(resources, "get_object"):
            resources = resources.get_object()
        objects = resources.get("/XObject") or {}
        if hasattr(objects, "get_object"):
            objects = objects.get_object()
        for value in objects.values():
            candidate = value.get_object() if hasattr(value, "get_object") else value
            if candidate.get("/Subtype") == "/Image":
                return True
    except Exception:
        return False
    return False


def _inspect_pdf(path: Path) -> dict[str, Any]:
    try:
        from pypdf import PdfReader
    except ImportError:
        return {"preflight_engine": "unavailable", "preflight_warnings": ["pypdf_not_installed"]}

    try:
        reader = PdfReader(str(path), strict=False)
        page_count = len(reader.pages)
        if not page_count:
            return {
                "preflight_engine": "pypdf",
                "page_count": 0,
                "sampled_page_count": 0,
                "sample_text_chars": 0,
                "image_page_count": 0,
            }
        sample_indices = sorted({0, page_count // 3, (page_count * 2) // 3, page_count - 1})
        sample_text_chars = 0
        image_page_count = 0
        warnings: list[str] = []
        for index in sample_indices:
            try:
                page = reader.pages[index]
                sample_text_chars += len((page.extract_text() or "").strip())
                image_page_count += int(_pdf_has_image(page))
            except Exception:
                warnings.append(f"page_{index + 1}_inspection_failed")
        result: dict[str, Any] = {
            "preflight_engine": "pypdf",
            "page_count": page_count,
            "sampled_page_count": len(sample_indices),
            "sample_text_chars": sample_text_chars,
            "image_page_count": image_page_count,
        }
        if warnings:
            result["preflight_warnings"] = warnings
        return result
    except Exception as error:
        return {
            "preflight_engine": "pypdf",
            "preflight_warnings": [f"pdf_inspection_failed:{type(error).__name__}"],
        }


def _inspect_office_container(path: Path) -> dict[str, Any]:
    if not is_zipfile(path):
        return {"preflight_engine": "zip_metadata", "preflight_warnings": ["not_an_openxml_container"]}
    try:
        with ZipFile(path) as archive:
            members = archive.infolist()
            names = [member.filename for member in members]
            suffix = path.suffix.lower()
            if suffix in {".pptx"}:
                item_names = [
                    name
                    for name in names
                    if name.startswith("ppt/slides/slide") and name.endswith(".xml")
                ]
                media_prefix = "ppt/media/"
                table_marker = b"<a:tbl"
            elif suffix in {".xlsx"}:
                item_names = [
                    name
                    for name in names
                    if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
                ]
                media_prefix = "xl/media/"
                table_marker = b"<table"
            else:
                item_names = ["word/document.xml"] if "word/document.xml" in names else []
                media_prefix = "word/media/"
                table_marker = b"<w:tbl"

            table_signal = any(name.startswith("xl/tables/") for name in names)
            inspected_bytes = 0
            for name in item_names:
                try:
                    member = archive.getinfo(name)
                    if member.file_size > 5 * 1024 * 1024 or inspected_bytes + member.file_size > 20 * 1024 * 1024:
                        continue
                    content = archive.read(member)
                    inspected_bytes += len(content)
                    if table_marker in content:
                        table_signal = True
                        break
                except (KeyError, OSError):
                    continue
            return {
                "preflight_engine": "zip_metadata",
                "item_count": len(item_names),
                "has_media": any(name.startswith(media_prefix) for name in names),
                "table_signal": table_signal,
            }
    except (BadZipFile, OSError) as error:
        return {
            "preflight_engine": "zip_metadata",
            "preflight_warnings": [f"office_inspection_failed:{type(error).__name__}"],
        }


def inspect_document(path: Path) -> dict[str, Any]:
    """Collect bounded, read-only structure signals without semantic analysis."""

    source = Path(path)
    suffix = source.suffix.lower()
    result: dict[str, Any] = {"suffix": suffix}
    try:
        result["size_bytes"] = source.stat().st_size
    except OSError:
        result["size_bytes"] = 0
    if suffix == ".pdf":
        result.update(_inspect_pdf(source))
    elif suffix in {".docx", ".pptx", ".xlsx"}:
        result.update(_inspect_office_container(source))
    return result


def _normalise_preflight(path: Path, preflight: dict[str, Any] | None) -> dict[str, Any]:
    result = dict(preflight) if preflight is not None else inspect_document(path)
    try:
        result.setdefault("size_bytes", path.stat().st_size)
    except OSError:
        result.setdefault("size_bytes", 0)
    result.setdefault("suffix", path.suffix.lower())
    return result


def _as_int(preflight: dict[str, Any], key: str) -> int | None:
    value = preflight.get(key)
    if value is None or isinstance(value, bool):
        return None
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return None


def _as_bool(preflight: dict[str, Any], key: str) -> bool:
    value = preflight.get(key)
    return value is True or (isinstance(value, str) and value.lower() in {"true", "1", "yes"})


def _pdf_signals(preflight: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    page_count = _as_int(preflight, "page_count")
    sample_text_chars = _as_int(preflight, "sample_text_chars")
    image_page_count = _as_int(preflight, "image_page_count")

    sampled_page_count = _as_int(preflight, "sampled_page_count") or page_count
    if sampled_page_count and sample_text_chars is not None:
        # This is intentionally conservative: a small sample can be normal
        # for a short PDF, but not for a long document.
        chars_per_page = sample_text_chars / max(sampled_page_count, 1)
        if sample_text_chars <= 200 or (sampled_page_count >= 2 and chars_per_page < 20):
            signals.append("sparse_text")
    if sampled_page_count and image_page_count is not None and image_page_count > 0:
        image_ratio = image_page_count / max(sampled_page_count, 1)
        text_density = sample_text_chars / max(sampled_page_count, 1) if sample_text_chars is not None else None
        if image_ratio >= 0.5 and (text_density is None or text_density < 400):
            signals.append("image_heavy")
        else:
            signals.append("images_present")
    elif _as_bool(preflight, "image_heavy"):
        signals.append("image_heavy")
    if _as_bool(preflight, "table_signal"):
        signals.append("table_signal")
    if _as_bool(preflight, "has_media"):
        signals.append("embedded_media")
    return signals


def _office_signals(preflight: dict[str, Any]) -> list[str]:
    signals: list[str] = []
    size_bytes = _as_int(preflight, "size_bytes") or 0
    if size_bytes >= 2 * 1024 * 1024:
        signals.append("large_file")
    if _as_bool(preflight, "has_media") or _as_bool(preflight, "image_heavy"):
        signals.append("embedded_media")
    if _as_bool(preflight, "table_signal"):
        signals.append("table_signal")
    if _as_bool(preflight, "layout_complex"):
        signals.append("complex_layout")
    return signals


def _plan(
    *,
    primary: str,
    fallbacks: list[str],
    complexity: str,
    signals: list[str],
    reason: str,
    requires_visual_review: bool,
    preflight: dict[str, Any],
) -> dict[str, Any]:
    automation_state = (
        "manual_attention"
        if primary == MANUAL_REVIEW
        else ("pending_adapter" if primary == VISION else "ready")
    )
    return {
        "version": "hxy-document-parser-plan.v1",
        "primary": primary,
        "fallbacks": fallbacks,
        "complexity": complexity,
        "signals": list(dict.fromkeys(signals)),
        "reason": reason,
        "requires_visual_review": requires_visual_review,
        "preflight": preflight,
        "official_use_allowed": False,
        "requires_human_review": primary == MANUAL_REVIEW,
        "automation_state": automation_state,
    }


def build_parser_plan(path: Path, preflight: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return an explainable parser plan without parsing or interpreting content."""

    source = Path(path)
    suffix = source.suffix.lower()
    signals: list[str] = []
    facts = _normalise_preflight(source, preflight)

    if suffix in _TEXT_SUFFIXES:
        return _plan(
            primary=TEXT_COMPILER,
            fallbacks=[],
            complexity="simple",
            signals=[],
            reason="plain text can be compiled directly without an external parser",
            requires_visual_review=False,
            preflight=facts,
        )

    if suffix in _IMAGE_SUFFIXES:
        return _plan(
            primary=VISION,
            fallbacks=[MANUAL_REVIEW],
            complexity="high",
            signals=["image_input"],
            reason="image understanding needs OCR or vision and a visual quality check",
            requires_visual_review=True,
            preflight=facts,
        )

    if suffix in _PDF_SUFFIXES:
        signals = _pdf_signals(facts)
        if {"sparse_text", "image_heavy"}.intersection(signals):
            return _plan(
                primary=MINERU,
                fallbacks=[MARKITDOWN],
                complexity="high",
                signals=signals,
                reason="sparse or image-heavy PDF needs layout-aware OCR before semantic understanding",
                requires_visual_review=True,
                preflight=facts,
            )
        complexity = "medium" if signals else "simple"
        if "table_signal" in signals or "embedded_media" in signals:
            complexity = "medium"
        return _plan(
            primary=MARKITDOWN,
            fallbacks=[MINERU],
            complexity=complexity,
            signals=signals,
            reason="text-rich PDF starts with the lightweight parser and keeps MinerU as a fidelity fallback",
            requires_visual_review=bool(signals),
            preflight=facts,
        )

    if suffix in _UNSUPPORTED_LEGACY_OFFICE_SUFFIXES:
        return _plan(
            primary=MANUAL_REVIEW,
            fallbacks=[],
            complexity="unknown",
            signals=["legacy_office_format"],
            reason="legacy DOC/PPT needs a safe office converter before document parsing",
            requires_visual_review=True,
            preflight=facts,
        )

    if suffix in _MARKITDOWN_ONLY_OFFICE_SUFFIXES:
        return _plan(
            primary=MARKITDOWN,
            fallbacks=[MANUAL_REVIEW],
            complexity="medium",
            signals=["legacy_office_format"],
            reason="legacy XLS is supported by the lightweight converter but not by MinerU",
            requires_visual_review=True,
            preflight=facts,
        )

    if suffix in _OFFICE_SUFFIXES:
        signals = _office_signals(facts)
        high_fidelity_signals = {"large_file", "embedded_media", "complex_layout"}.intersection(signals)
        if suffix in {".ppt", ".pptx"} and signals:
            high_fidelity_signals.update(signals)
        if high_fidelity_signals:
            return _plan(
                primary=MINERU,
                fallbacks=[MARKITDOWN],
                complexity="high",
                signals=signals,
                reason="large or layout-rich office document benefits from structure-aware extraction",
                requires_visual_review=True,
                preflight=facts,
            )
        if signals:
            return _plan(
                primary=MARKITDOWN,
                fallbacks=[MINERU],
                complexity="medium",
                signals=signals,
                reason="ordinary office structure starts with lightweight conversion and keeps MinerU as fallback",
                requires_visual_review="table_signal" in signals,
                preflight=facts,
            )
        return _plan(
            primary=MARKITDOWN,
            fallbacks=[MINERU],
            complexity="simple",
            signals=[],
            reason="ordinary office document can use lightweight conversion first",
            requires_visual_review=False,
            preflight=facts,
        )

    if suffix in _LIGHT_SUFFIXES:
        return _plan(
            primary=MARKITDOWN,
            fallbacks=[],
            complexity="simple",
            signals=[],
            reason="structured text format is supported by the lightweight converter",
            requires_visual_review=False,
            preflight=facts,
        )

    return _plan(
        primary=MANUAL_REVIEW,
        fallbacks=[],
        complexity="unknown",
        signals=["unsupported_format"],
        reason="format is not safely recognized by the configured parsers",
        requires_visual_review=True,
        preflight=facts,
    )
