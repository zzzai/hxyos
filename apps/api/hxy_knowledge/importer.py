from __future__ import annotations

import json
from hashlib import sha1
from pathlib import Path
from collections import Counter
from typing import Any


_GOVERNANCE_METADATA_KEYS = {
    "source_origin",
    "origin",
    "source_authority",
    "authority_source",
    "authority_version",
    "authority_organization_id",
    "authority_recorded",
    "official_use_allowed",
    "source_type",
}


def _content_metadata(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {
        key: metadata_value
        for key, metadata_value in value.items()
        if key not in _GOVERNANCE_METADATA_KEYS
    }


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _path_sensitive_id(base_id: str, relative_path: str) -> str:
    if not base_id:
        return f"path:{relative_path}"
    if not relative_path:
        return base_id
    path_hash = sha1(relative_path.encode("utf-8")).hexdigest()[:10]
    return f"{base_id}:path:{path_hash}"


def _asset_id_for_record(record: dict[str, Any], duplicate_base_ids: set[str] | None = None) -> str:
    base_id = record.get("asset_id") or record.get("source_id") or ""
    if duplicate_base_ids is not None and base_id not in duplicate_base_ids:
        return base_id or f"path:{record.get('relative_path') or ''}"
    return _path_sensitive_id(
        base_id,
        record.get("relative_path") or "",
    )


def prepare_asset_records(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    run_name = manifest.get("run_name") or "unknown"
    records: list[dict[str, Any]] = []
    assets = manifest.get("assets", [])
    base_counts = Counter(asset.get("asset_id") or f"path:{asset.get('relative_path', '')}" for asset in assets)
    duplicate_base_ids = {base_id for base_id, count in base_counts.items() if count > 1}
    for asset in assets:
        asset_id = _asset_id_for_record(asset, duplicate_base_ids)
        records.append(
            {
                "asset_id": asset_id,
                "source_asset_id": asset.get("asset_id") or "",
                "run_name": run_name,
                "title": asset.get("title") or Path(asset.get("file_name", "")).stem,
                "file_name": asset.get("file_name") or "",
                "source_path": asset.get("relative_path") or "",
                "normalized_path": asset.get("normalized_path") or "",
                "extension": asset.get("extension") or "",
                "mime_type": asset.get("mime_type") or "",
                "file_size": int(asset.get("file_size") or 0),
                "sha256": asset.get("sha256") or "",
                "domain": asset.get("knowledge_domain") or "external",
                "stage": asset.get("project_stage") or "evergreen",
                "status": asset.get("status") or "staged",
                "warnings": asset.get("warnings") or [],
                "quality_score": float(asset.get("quality_score") or (asset.get("quality_scores") or {}).get("overall") or 0),
                "quality_grade": asset.get("quality_grade") or (asset.get("quality_scores") or {}).get("grade") or "unknown",
                "quality_scores": asset.get("quality_scores") or {},
                "metadata": _content_metadata(asset.get("metadata")),
            }
        )
    return records


def prepare_chunk_records(search_index: dict[str, Any], run_name: str | None = None) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    inferred_run = run_name or search_index.get("run_name") or "unknown"
    chunks = list(search_index.get("chunks", []))
    known_chunk_ids = {
        chunk.get("chunk_id") or f"{chunk.get('source_id', 'unknown')}:chunk:{chunk.get('chunk_index', 0)}"
        for chunk in chunks
    }
    for chunk in search_index.get("image_understanding_chunks", []):
        chunk_id = chunk.get("chunk_id") or f"{chunk.get('source_id', 'unknown')}:image-understanding:1"
        if chunk_id not in known_chunk_ids:
            chunks.append(chunk)
            known_chunk_ids.add(chunk_id)
    base_chunk_ids = [
        chunk.get("chunk_id") or f"{chunk.get('source_id', 'unknown')}:chunk:{chunk.get('chunk_index', 0)}"
        for chunk in chunks
    ]
    duplicate_chunk_base_ids = {
        chunk_id
        for chunk_id, count in Counter(base_chunk_ids).items()
        if count > 1
    }
    duplicate_asset_base_ids = {
        chunk.get("source_id") or chunk.get("asset_id") or ""
        for chunk, chunk_id in zip(chunks, base_chunk_ids)
        if chunk_id in duplicate_chunk_base_ids
    }
    for chunk, source_chunk_id in zip(chunks, base_chunk_ids):
        asset_id = _asset_id_for_record(chunk, duplicate_asset_base_ids)
        chunk_index = int(chunk.get("chunk_index") or 0)
        chunk_id = f"{asset_id}:chunk:{chunk_index}" if source_chunk_id in duplicate_chunk_base_ids else source_chunk_id
        records.append(
            {
                "chunk_id": chunk_id,
                "asset_id": asset_id,
                "source_chunk_id": chunk.get("chunk_id") or "",
                "source_asset_id": chunk.get("source_id") or chunk.get("asset_id") or "",
                "run_name": inferred_run,
                "chunk_index": chunk_index,
                "title": chunk.get("title") or "",
                "source_path": chunk.get("relative_path") or "",
                "normalized_path": chunk.get("normalized_path") or "",
                "domain": chunk.get("knowledge_domain") or "external",
                "stage": chunk.get("project_stage") or "evergreen",
                "content": chunk.get("text") or "",
                "metadata": {
                    key: value
                    for key, value in chunk.items()
                    if key
                    not in {
                        "chunk_id",
                        "source_id",
                        "asset_id",
                        "chunk_index",
                        "title",
                        "relative_path",
                        "normalized_path",
                        "knowledge_domain",
                        "project_stage",
                        "text",
                        *_GOVERNANCE_METADATA_KEYS,
                    }
                },
            }
        )
    return records


def load_current_records(root_dir: Path, run_name: str) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    manifest_path = root_dir / "knowledge" / "structured" / f"hxy-inbox-manifest-{run_name}.json"
    index_path = root_dir / "knowledge" / "structured" / f"hxy-inbox-search-index-{run_name}.json"
    manifest = load_json(manifest_path)
    search_index = load_json(index_path)
    return manifest, prepare_asset_records(manifest), prepare_chunk_records(search_index, run_name=run_name)


def load_image_understanding_records(root_dir: Path, run_name: str) -> list[dict[str, Any]]:
    path = root_dir / "knowledge" / "structured" / f"hxy-image-understandings-{run_name}.json"
    if not path.exists():
        return []
    payload = load_json(path)
    records: list[dict[str, Any]] = []
    for item in payload.get("items", []):
        records.append(
            {
                "asset_id": item.get("asset_id") or "",
                "run_name": run_name,
                "source_path": item.get("source_path") or "",
                "normalized_path": item.get("normalized_path") or "",
                "title": item.get("title") or "",
                "image_type": item.get("image_type") or "general_image",
                "visual_summary": item.get("visual_summary") or "",
                "business_summary": item.get("business_summary") or "",
                "ocr_text": item.get("ocr_text") or "",
                "detected_entities": item.get("detected_entities") or [],
                "prices": item.get("prices") or [],
                "related_domains": item.get("related_domains") or [],
                "confidence": float(item.get("confidence") or 0),
                "qa_ready": bool(item.get("qa_ready")),
                "needs_review": bool(item.get("needs_review", True)),
                "payload": item,
            }
        )
    return records
