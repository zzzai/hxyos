from __future__ import annotations

import hashlib
import mimetypes
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".html", ".htm"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _domain_for_text(text: str, file_name: str) -> str:
    combined = f"{file_name} {text}"
    if any(term in combined for term in ["招商", "加盟", "回本"]):
        return "franchise"
    if any(term in combined for term in ["员工", "培训", "话术", "SOP", "服务流程"]):
        return "training"
    if any(term in combined for term in ["清泡", "调泡", "补泡", "养泡", "产品", "菜单", "泡脚方"]):
        return "product"
    if any(term in combined for term in ["门店", "单店", "店长", "排班"]):
        return "store_model"
    if any(term in combined for term in ["定位", "品牌", "核爆点"]):
        return "brand"
    return "external"


def _decode_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ["utf-8", "utf-8-sig", "gb18030"]:
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="ignore")


def _chunk_text(text: str, max_chars: int = 1800) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    chunks: list[str] = []
    current = ""
    for paragraph in cleaned.splitlines():
        paragraph = paragraph.strip()
        if not paragraph:
            continue
        if len(current) + len(paragraph) + 1 > max_chars and current:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n{paragraph}".strip()
    if current:
        chunks.append(current)
    return chunks or [cleaned[:max_chars]]


def build_instant_memory_records(root_dir: Path, uploaded_files: list[dict[str, Any]]) -> dict[str, Any]:
    run_name = "workbench-instant"
    now = datetime.now(timezone.utc).isoformat()
    assets: list[dict[str, Any]] = []
    chunks: list[dict[str, Any]] = []
    uploaded: list[dict[str, Any]] = []

    for file_info in uploaded_files:
        relative_path = file_info.get("relative_path") or ""
        if not relative_path:
            continue
        path = (root_dir / relative_path).resolve()
        if not path.exists() or not path.is_relative_to(root_dir.resolve()):
            continue
        file_name = file_info.get("file_name") or path.name
        extension = path.suffix.lower()
        digest = _sha256(path)
        asset_id = f"hxy-workbench:{digest[:16]}"
        mime_type = file_info.get("mime_type") or mimetypes.guess_type(file_name)[0] or ""
        text = _decode_text(path) if extension in TEXT_EXTENSIONS else ""
        domain = _domain_for_text(text, file_name)
        qa_ready = bool(text.strip())
        status = "indexed" if qa_ready else "needs_review"
        quality_score = 0.86 if qa_ready else 0.42
        quality_grade = "B" if qa_ready else "C"
        asset = {
            "asset_id": asset_id,
            "run_name": run_name,
            "title": Path(file_name).stem,
            "file_name": file_name,
            "source_path": relative_path,
            "normalized_path": relative_path,
            "extension": extension,
            "mime_type": mime_type,
            "file_size": int(file_info.get("size") or path.stat().st_size),
            "sha256": digest,
            "domain": domain,
            "stage": "workbench",
            "status": status,
            "warnings": [] if qa_ready else ["暂未完成正文解析，已进入复核和后续多模态理解流程"],
            "quality_score": quality_score,
            "quality_grade": quality_grade,
            "quality_scores": {
                "overall": quality_score,
                "grade": quality_grade,
                "qa_ready": qa_ready,
                "source": "workbench_instant_ingest",
            },
            "metadata": {
                "ingested_at": now,
                "ingest_source": "operating_brain_workbench",
                "qa_ready": qa_ready,
            },
        }
        assets.append(asset)
        uploaded.append({**file_info, "asset_id": asset_id, "qa_ready": qa_ready, "domain": domain})
        for index, chunk_text in enumerate(_chunk_text(text)):
            chunks.append(
                {
                    "chunk_id": f"{asset_id}:chunk:{index}",
                    "asset_id": asset_id,
                    "run_name": run_name,
                    "chunk_index": index,
                    "title": asset["title"],
                    "source_path": relative_path,
                    "normalized_path": relative_path,
                    "domain": domain,
                    "stage": "workbench",
                    "content": chunk_text,
                    "metadata": {
                        "ingested_at": now,
                        "ingest_source": "operating_brain_workbench",
                        "chunk_type": "instant_text",
                    },
                }
            )

    return {
        "run_name": run_name,
        "assets": assets,
        "chunks": chunks,
        "uploaded_files": uploaded,
        "status": "indexed" if chunks else "needs_review",
        "asset_count": len(assets),
        "chunk_count": len(chunks),
    }
