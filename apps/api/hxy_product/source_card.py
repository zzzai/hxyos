from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .material_parser import MaterialParseResult


_ORIGINS = {"internal", "external", "unknown"}
_AUTHORITIES = {"working_material", "claimed_official", "reference", "fragment"}
_SCALES = {"macro", "meso", "micro", "unknown"}
_DOMAINS = {
    "brand",
    "product",
    "operations",
    "store",
    "customer",
    "finance",
    "organization",
    "compliance",
    "external",
    "general",
}
_BLOCKED_USE = [
    "official_answer",
    "external_marketing",
    "financing_statement",
    "medical_claim",
]


def _choice(value: Any, allowed: set[str], default: str) -> str:
    candidate = str(value or "").strip()
    return candidate if candidate in allowed else default


def _timestamp(value: datetime | None) -> str:
    current = value or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return current.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def build_source_card(
    material: dict[str, Any],
    parsed: MaterialParseResult,
    *,
    created_at: datetime | None = None,
) -> dict[str, Any]:
    understanding = material.get("understanding")
    if not isinstance(understanding, dict):
        understanding = {}
    material_id = str(material.get("material_id") or material.get("id") or "")
    origin = _choice(understanding.get("source_origin"), _ORIGINS, "unknown")
    authority = _choice(
        understanding.get("authority_level"),
        _AUTHORITIES,
        "working_material",
    )
    allowed_use = ["reference", "draft"] if origin == "external" else ["internal_context", "draft"]
    return {
        "version": "hxy-source-card.v1",
        "source_id": f"material:{material_id}",
        "material_id": material_id,
        "source_hash": str(material.get("sha256") or ""),
        "file_name": str(material.get("file_name") or "")[:180],
        "document_type": str(understanding.get("document_type") or "文档资料")[:80],
        "source_origin": origin,
        "authority_level": authority,
        "domain": _choice(understanding.get("domain"), _DOMAINS, "general"),
        "knowledge_scale": _choice(
            understanding.get("knowledge_scale"),
            _SCALES,
            "unknown",
        ),
        "quality_signals": {
            "source_hash_present": len(str(material.get("sha256") or "")) == 64,
            "source_size_bytes": int(material.get("size_bytes") or 0),
            "extracted_char_count": len(parsed.text_content),
            "title_detected": bool(parsed.title),
            "parser_warning_count": len(parsed.warnings),
        },
        "allowed_use": allowed_use,
        "blocked_use": list(_BLOCKED_USE),
        "official_use_allowed": False,
        "understanding_summary": str(understanding.get("summary") or "")[:600],
        "parser": {
            "name": parsed.parser_name,
            "version": parsed.parser_version,
            "warnings": list(parsed.warnings),
        },
        "created_at": _timestamp(created_at),
    }
