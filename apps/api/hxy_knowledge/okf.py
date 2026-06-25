from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any


LIST_FIELDS = {"supersedes", "contradicts", "used_by", "replaced_by", "evidence"}


def _parse_scalar(value: str) -> Any:
    cleaned = value.strip().strip('"').strip("'")
    if not cleaned:
        return ""
    if cleaned.startswith("[") and cleaned.endswith("]"):
        inner = cleaned[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part) for part in inner.split(",")]
    try:
        if "." in cleaned:
            return float(cleaned)
        return int(cleaned)
    except ValueError:
        return cleaned


def _parse_frontmatter(markdown: str) -> tuple[dict[str, Any], str]:
    if not markdown.startswith("---"):
        return {}, markdown
    parts = markdown.split("---", 2)
    if len(parts) < 3:
        return {}, markdown
    raw_meta = parts[1]
    body = parts[2].lstrip("\n")
    meta: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in raw_meta.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue
        stripped = line.strip()
        if stripped.startswith("- ") and current_list_key:
            meta.setdefault(current_list_key, []).append(_parse_scalar(stripped[2:]))
            continue
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        raw_value = raw_value.strip()
        if not raw_value:
            meta[key] = [] if key in LIST_FIELDS else ""
            current_list_key = key if key in LIST_FIELDS else None
            continue
        meta[key] = _parse_scalar(raw_value)
        current_list_key = None
    return meta, body


def _as_list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [str(value).strip()]


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return datetime.strptime(value[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _today(value: str | None = None) -> date:
    if value:
        parsed = _parse_date(value)
        if parsed:
            return parsed
    return date.today()


def _document_id(path: Path, root: Path) -> str:
    return path.relative_to(root).with_suffix("").as_posix()


def _build_document(path: Path, root: Path, *, today: str | None, stale_after_days: int) -> dict[str, Any] | None:
    markdown = path.read_text(encoding="utf-8")
    meta, body = _parse_frontmatter(markdown)
    if not meta:
        return None
    confirmed_at = _parse_date(str(meta.get("last_confirmed") or ""))
    current_day = _today(today)
    days_since_confirmed = (current_day - confirmed_at).days if confirmed_at else None
    confidence = _as_float(meta.get("confidence"), default=0.0)
    status = str(meta.get("status") or "draft")
    lifecycle_flags: list[str] = []
    is_stale = bool(days_since_confirmed is not None and days_since_confirmed > stale_after_days)
    if is_stale:
        lifecycle_flags.append("stale")
    if confidence < 0.65:
        lifecycle_flags.append("low_confidence")
    if status in {"disputed", "superseded"}:
        lifecycle_flags.append(status)
    if _as_list(meta.get("contradicts")):
        lifecycle_flags.append("has_conflict")
    return {
        "version": "hxy-okf-document.v1",
        "id": _document_id(path, root),
        "path": path.as_posix(),
        "relative_path": path.relative_to(root).as_posix(),
        "type": str(meta.get("type") or "knowledge"),
        "title": str(meta.get("title") or path.stem),
        "domain": str(meta.get("domain") or "general"),
        "status": status,
        "confidence": confidence,
        "last_confirmed": str(meta.get("last_confirmed") or ""),
        "owner": str(meta.get("owner") or "未指定"),
        "supersedes": _as_list(meta.get("supersedes")),
        "contradicts": _as_list(meta.get("contradicts")),
        "used_by": _as_list(meta.get("used_by")),
        "replaced_by": _as_list(meta.get("replaced_by")),
        "body": body.strip(),
        "is_stale": is_stale,
        "days_since_confirmed": days_since_confirmed,
        "lifecycle_flags": lifecycle_flags,
    }


def load_okf_documents(root: Path, *, today: str | None = None, stale_after_days: int = 90) -> list[dict[str, Any]]:
    okf_root = root.resolve()
    if not okf_root.exists():
        return []
    documents: list[dict[str, Any]] = []
    for path in sorted(okf_root.rglob("*.md")):
        document = _build_document(path, okf_root, today=today, stale_after_days=stale_after_days)
        if document:
            documents.append(document)
    return documents


def summarize_okf_lifecycle(documents: list[dict[str, Any]], *, today: str | None = None) -> dict[str, Any]:
    status_counts = Counter(str(item.get("status") or "draft") for item in documents)
    return {
        "version": "hxy-okf-lifecycle-summary.v1",
        "today": _today(today).isoformat(),
        "total": len(documents),
        "status_counts": dict(status_counts),
        "conflict_count": sum(1 for item in documents if item.get("contradicts") or item.get("status") == "disputed"),
        "stale_count": sum(1 for item in documents if item.get("is_stale")),
        "low_confidence_count": sum(1 for item in documents if _as_float(item.get("confidence")) < 0.65),
        "superseded_count": status_counts.get("superseded", 0),
        "domains": dict(Counter(str(item.get("domain") or "general") for item in documents)),
    }
