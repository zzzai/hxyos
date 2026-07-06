from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hxy_knowledge.knowledge_compiler import compile_directory


TEXT_COMPILABLE_SUFFIXES = {".md", ".txt"}
PARSING_REQUIRED_SUFFIXES = {
    ".csv",
    ".doc",
    ".docx",
    ".epub",
    ".html",
    ".htm",
    ".jpeg",
    ".jpg",
    ".json",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".webp",
    ".xls",
    ".xlsx",
}
DISCOVERABLE_SUFFIXES = TEXT_COMPILABLE_SUFFIXES | PARSING_REQUIRED_SUFFIXES


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _relative(path: Path, root_dir: Path) -> str:
    try:
        return path.relative_to(root_dir).as_posix()
    except ValueError:
        return path.as_posix()


def discover_inbox_materials(inbox_dir: Path, *, root_dir: Path) -> dict[str, Any]:
    items = []
    ignored_items = []
    for path in sorted(inbox_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        rel_path = _relative(path, root_dir)
        if suffix not in DISCOVERABLE_SUFFIXES:
            ignored_items.append(
                {
                    "source_path": rel_path,
                    "suffix": suffix,
                    "reason": "unsupported_or_unsafe_suffix",
                }
            )
            continue
        compiler_ready = suffix in TEXT_COMPILABLE_SUFFIXES
        content_hash = _hash_file(path)
        timestamp = _utc_now()
        items.append(
            {
                "version": "hxy-ingest-task.v1",
                "task_id": f"hxy-ingest-task:{content_hash[:16]}",
                "source_path": rel_path,
                "source_type": "file",
                "suffix": suffix,
                "content_hash": content_hash,
                "status": "DISCOVERED" if compiler_ready else "PARSING_REQUIRED",
                "compiler_ready": compiler_ready,
                "parse_status": "compiler_ready" if compiler_ready else "external_parser_required",
                "parser_hint": "hxy_text_compiler" if compiler_ready else "mineru_or_markitdown_required",
                "official_use_allowed": False,
                "requires_human_review": True,
                "risk_flags": [],
                "artifact_refs": {},
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
    return {
        "version": "hxy-ingest-discovery.v1",
        "count": len(items),
        "compiler_ready_count": sum(1 for item in items if item["compiler_ready"]),
        "parsing_required_count": sum(1 for item in items if not item["compiler_ready"]),
        "ignored_count": len(ignored_items),
        "items": items,
        "ignored_items": ignored_items,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _public_compiler_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "artifacts"}


def run_ingest_loop(
    *,
    raw_dir: Path,
    wiki_dir: Path,
    report_path: Path,
    runs_dir: Path,
    run_id: str,
    root_dir: Path,
) -> dict[str, Any]:
    discovery = discover_inbox_materials(raw_dir, root_dir=root_dir)
    compiler_report = compile_directory(raw_dir, wiki_dir)
    _write_json(report_path, _public_compiler_report(compiler_report))

    state = {
        "version": "hxy-ingest-loop-state.v1",
        "run_id": run_id,
        "status": "review_required",
        "stop_reason": "human_review_required",
        "task_count": discovery["count"],
        "compiler_ready_count": discovery["compiler_ready_count"],
        "parsing_required_count": discovery["parsing_required_count"],
        "ignored_count": discovery["ignored_count"],
        "extract_count": int(compiler_report.get("extract_count") or 0),
        "claim_count": int(compiler_report.get("claim_count") or 0),
        "review_queue_count": int(compiler_report.get("review_queue_count") or 0),
        "answer_card_draft_count": int(compiler_report.get("answer_card_draft_count") or 0),
        "compliance_review_count": int(compiler_report.get("compliance_review_count") or 0),
        "tasks": [
            {
                **task,
                "status": "REVIEWING" if task.get("compiler_ready") else "PARSING_REQUIRED",
                "artifact_refs": (
                    {
                        "ingest_report": report_path.as_posix(),
                        "review_queue": (wiki_dir / "review-queue.json").as_posix(),
                        "answer_card_drafts": (wiki_dir / "answer-card-drafts.json").as_posix(),
                        "compliance_review_pack": (wiki_dir / "compliance-review-pack.json").as_posix(),
                    }
                    if task.get("compiler_ready")
                    else {}
                ),
                "updated_at": _utc_now(),
            }
            for task in discovery["items"]
        ],
        "ignored_items": discovery["ignored_items"],
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "ingest_loop_outputs_are_candidates_until_human_review",
        "next_actions": [
            "在知识工作台复核 review queue。",
            "先解析 PDF/DOCX/PPTX/图片等非文本资料，再进入编译。",
            "禁止自动发布 approved answer card。",
            "复核后再决定是否进入正式知识库。",
        ],
    }
    _write_json(Path(runs_dir) / run_id / "loop-state.json", state)
    return state
