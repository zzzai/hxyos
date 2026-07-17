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

MATERIAL_CLASSES = {
    "internal_project",
    "internal_record",
    "external_primary",
    "external_secondary",
    "ai_derived",
    "processing_artifact",
    "tool_artifact",
}
LIFECYCLES = {"current_candidate", "historical", "superseded", "undetermined"}
AUTHORITY_STATES = {"unclassified", "candidate", "approved", "rejected"}
SCOPES = {
    "brand",
    "strategy",
    "product",
    "first_store",
    "operations",
    "customer",
    "finance",
    "legal",
    "technology",
    "design",
    "compliance",
    "external_method",
}
SENSITIVITIES = {"public", "internal", "restricted", "founder_only"}
BUSINESS_STAGES = {
    "first_store",
    "pilot",
    "chain",
    "financing",
    "future_vision",
    "evergreen",
}
DERIVATIONS = {
    "original",
    "extracted_copy",
    "ai_summary",
    "application_draft",
    "duplicate_copy",
}

_DOMAIN_SCOPE = {
    "brand": "brand",
    "product": "product",
    "operations": "operations",
    "store": "first_store",
    "customer": "customer",
    "finance": "finance",
    "organization": "operations",
    "compliance": "compliance",
    "external": "external_method",
    "general": "external_method",
}


def _scopes(value: Any, *, fallback: str) -> list[str]:
    if not isinstance(value, list) or not value:
        return [fallback]
    normalized = [str(item).strip() for item in value]
    if any(item not in SCOPES for item in normalized):
        return [fallback]
    return list(dict.fromkeys(normalized))


def build_source_use_policy(material_class: str) -> dict[str, Any]:
    if material_class in {"processing_artifact", "tool_artifact"}:
        allowed = ["audit_only"]
        blocked = ["retrieval", "generation_context"]
        retrieval_state = "excluded"
    elif material_class == "ai_derived":
        allowed = ["reference", "ideation", "draft"]
        blocked = ["evidence_citation", "formal_hxy_fact", "automatic_publication"]
        retrieval_state = "eligible_reference"
    elif material_class in {"external_primary", "external_secondary"}:
        allowed = ["reference", "research", "draft"]
        blocked = ["formal_hxy_fact", "automatic_publication"]
        retrieval_state = "eligible_reference"
    else:
        allowed = ["internal_context", "draft"]
        blocked = ["automatic_publication"]
        retrieval_state = "pending_source_decision"

    return {
        "allowed_use": allowed,
        "blocked_use": list(dict.fromkeys([*_BLOCKED_USE, *blocked])),
        "retrieval_state": retrieval_state,
        "official_use_allowed": False,
    }


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
    default_class = "external_secondary" if origin == "external" else "internal_project"
    material_class = _choice(
        understanding.get("material_class"),
        MATERIAL_CLASSES,
        default_class,
    )
    lifecycle = _choice(
        understanding.get("lifecycle"),
        LIFECYCLES,
        "undetermined",
    )
    requested_authority_state = str(understanding.get("authority_state") or "").strip()
    authority_state = (
        requested_authority_state
        if requested_authority_state in {"unclassified", "candidate", "rejected"}
        else "unclassified"
    )
    domain = _choice(understanding.get("domain"), _DOMAINS, "general")
    policy = build_source_use_policy(material_class)
    return {
        "version": "hxy-source-card.v2",
        "source_id": f"material:{material_id}",
        "material_id": material_id,
        "source_hash": str(material.get("sha256") or ""),
        "file_name": str(material.get("file_name") or "")[:180],
        "document_type": str(understanding.get("document_type") or "文档资料")[:80],
        "source_origin": origin,
        "authority_level": authority,
        "domain": domain,
        "knowledge_scale": _choice(
            understanding.get("knowledge_scale"),
            _SCALES,
            "unknown",
        ),
        "material_class": material_class,
        "lifecycle": lifecycle,
        "authority_state": authority_state,
        "scope": _scopes(
            understanding.get("scope"),
            fallback=_DOMAIN_SCOPE[domain],
        ),
        "sensitivity": _choice(
            understanding.get("sensitivity"),
            SENSITIVITIES,
            "public" if origin == "external" else "internal",
        ),
        "business_stage": _choice(
            understanding.get("business_stage"),
            BUSINESS_STAGES,
            "evergreen",
        ),
        "derivation": _choice(
            understanding.get("derivation"),
            DERIVATIONS,
            "original",
        ),
        "retrieval_state": policy["retrieval_state"],
        "classification_confidence": _choice(
            understanding.get("classification_confidence"),
            {"low", "medium", "high"},
            "low",
        ),
        "classification_reasons": ["source_card:preliminary_understanding"],
        "quality_signals": {
            "source_hash_present": len(str(material.get("sha256") or "")) == 64,
            "source_size_bytes": int(material.get("size_bytes") or 0),
            "extracted_char_count": len(parsed.text_content),
            "title_detected": bool(parsed.title),
            "parser_warning_count": len(parsed.warnings),
        },
        "allowed_use": policy["allowed_use"],
        "blocked_use": policy["blocked_use"],
        "official_use_allowed": policy["official_use_allowed"],
        "understanding_summary": str(understanding.get("summary") or "")[:600],
        "parser": {
            "name": parsed.parser_name,
            "version": parsed.parser_version,
            "warnings": list(parsed.warnings),
        },
        "created_at": _timestamp(created_at),
    }
