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
MINERU_SUFFIXES = {".pdf"}
MARKITDOWN_SUFFIXES = {".csv", ".doc", ".docx", ".epub", ".html", ".htm", ".json", ".ppt", ".pptx", ".xls", ".xlsx"}
VISION_SUFFIXES = {".jpeg", ".jpg", ".png", ".webp"}


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


def _parser_strategy_for_suffix(suffix: str) -> str:
    if suffix in MINERU_SUFFIXES:
        return "mineru"
    if suffix in MARKITDOWN_SUFFIXES:
        return "markitdown"
    if suffix in VISION_SUFFIXES:
        return "ocr_or_vision"
    return "manual_review"


def _extracted_reference_path_for(inbox_dir: Path, source_path: str) -> Path:
    clean_source = source_path.strip("/").replace("\\", "/")
    return inbox_dir / "extracted-reference" / f"{clean_source}.reference.txt"


def _is_file_safely(path: Path) -> bool:
    try:
        return path.is_file()
    except OSError:
        return False


def _existing_extracted_reference_path(inbox_dir: Path, source_path: str) -> Path | None:
    current_path = _extracted_reference_path_for(inbox_dir, source_path)
    if _is_file_safely(current_path):
        return current_path
    legacy_path = inbox_dir / "extracted-reference" / f"{Path(source_path).name}.reference.txt"
    if _is_file_safely(legacy_path):
        return legacy_path
    legacy_stem_path = inbox_dir / "extracted-reference" / f"{Path(source_path).stem}.reference.txt"
    return legacy_stem_path if _is_file_safely(legacy_stem_path) else None


def discover_inbox_materials(inbox_dir: Path, *, root_dir: Path) -> dict[str, Any]:
    items = []
    ignored_items = []
    seen_by_hash: dict[str, str] = {}
    for path in sorted(inbox_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        rel_path = _relative(path, root_dir)
        if "extracted-reference/" in rel_path and not rel_path.endswith(".reference.txt"):
            ignored_items.append(
                {
                    "source_path": rel_path,
                    "suffix": suffix,
                    "reason": "parser_runtime_artifact",
                }
            )
            continue
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
        duplicate_of = seen_by_hash.get(content_hash)
        if duplicate_of is None:
            seen_by_hash[content_hash] = rel_path
        extracted_reference_path = None if compiler_ready else _existing_extracted_reference_path(inbox_dir, rel_path)
        extracted_reference_rel = (
            _relative(extracted_reference_path, root_dir)
            if not compiler_ready and extracted_reference_path is not None
            else ""
        )
        parse_status = (
            "compiler_ready"
            if compiler_ready
            else ("extracted_reference_available" if extracted_reference_rel else "external_parser_required")
        )
        timestamp = _utc_now()
        items.append(
            {
                "version": "hxy-ingest-task.v1",
                "task_id": f"hxy-ingest-task:{content_hash[:16]}",
                "source_path": rel_path,
                "source_type": "file",
                "suffix": suffix,
                "content_hash": content_hash,
                "status": (
                    "DISCOVERED"
                    if compiler_ready
                    else ("PARSED_REFERENCE_READY" if extracted_reference_rel else "PARSING_REQUIRED")
                ),
                "compiler_ready": compiler_ready,
                "parse_status": parse_status,
                "parser_hint": (
                    "hxy_text_compiler"
                    if compiler_ready
                    else ("compiled_from_extracted_reference" if extracted_reference_rel else f"{_parser_strategy_for_suffix(suffix)}_required")
                ),
                "duplicate_of": duplicate_of,
                "canonical_source_path": duplicate_of or rel_path,
                "official_use_allowed": False,
                "requires_human_review": True,
                "risk_flags": [],
                "artifact_refs": {"extracted_reference": extracted_reference_rel} if extracted_reference_rel else {},
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
    duplicate_groups = []
    for content_hash, canonical_source_path in seen_by_hash.items():
        duplicates = [
            str(item["source_path"])
            for item in items
            if item.get("content_hash") == content_hash and item.get("duplicate_of")
        ]
        if duplicates:
            duplicate_groups.append(
                {
                    "content_hash": content_hash,
                    "canonical_source_path": canonical_source_path,
                    "duplicates": duplicates,
                }
            )
    return {
        "version": "hxy-ingest-discovery.v1",
        "count": len(items),
        "unique_count": sum(1 for item in items if not item["duplicate_of"]),
        "duplicate_count": sum(1 for item in items if item["duplicate_of"]),
        "compiler_ready_count": sum(1 for item in items if item["compiler_ready"]),
        "compiler_ready_unique_count": sum(
            1 for item in items if item["compiler_ready"] and not item["duplicate_of"]
        ),
        "parsing_required_count": sum(1 for item in items if item["parse_status"] == "external_parser_required"),
        "parsed_reference_count": sum(1 for item in items if item["parse_status"] == "extracted_reference_available"),
        "ignored_count": len(ignored_items),
        "items": items,
        "ignored_items": ignored_items,
        "duplicate_groups": duplicate_groups,
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _public_compiler_report(report: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in report.items() if key != "artifacts"}


def _build_parser_jobs(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
    jobs = []
    for task in tasks:
        if task.get("compiler_ready") or task.get("duplicate_of") or task.get("parse_status") != "external_parser_required":
            continue
        suffix = str(task.get("suffix") or "")
        jobs.append(
            {
                "version": "hxy-parser-job.v1",
                "job_id": f"hxy-parser-job:{str(task.get('content_hash') or '')[:16]}",
                "source_path": task.get("source_path") or "",
                "source_type": task.get("source_type") or "file",
                "suffix": suffix,
                "content_hash": task.get("content_hash") or "",
                "parser_strategy": _parser_strategy_for_suffix(suffix),
                "status": "PENDING",
                "output_contract": "write extracted text/reference artifact, then rerun ingest loop",
                "official_use_allowed": False,
                "requires_human_review": True,
            }
        )
    return jobs


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
    compiler_source_paths = [
        root_dir / str(task["source_path"])
        for task in discovery["items"]
        if task.get("compiler_ready") and not task.get("duplicate_of")
    ]
    compiler_report = compile_directory(raw_dir, wiki_dir, source_paths=compiler_source_paths)
    _write_json(report_path, _public_compiler_report(compiler_report))
    parser_jobs = _build_parser_jobs(discovery["items"])

    state = {
        "version": "hxy-ingest-loop-state.v1",
        "run_id": run_id,
        "status": "review_required",
        "stop_reason": "human_review_required",
        "task_count": discovery["count"],
        "unique_count": discovery["unique_count"],
        "duplicate_count": discovery["duplicate_count"],
        "compiler_ready_count": discovery["compiler_ready_count"],
        "compiler_ready_unique_count": discovery["compiler_ready_unique_count"],
        "parsing_required_count": discovery["parsing_required_count"],
        "parsed_reference_count": discovery["parsed_reference_count"],
        "ignored_count": discovery["ignored_count"],
        "parser_job_count": len(parser_jobs),
        "extract_count": int(compiler_report.get("extract_count") or 0),
        "claim_count": int(compiler_report.get("claim_count") or 0),
        "review_queue_count": int(compiler_report.get("review_queue_count") or 0),
        "answer_card_draft_count": int(compiler_report.get("answer_card_draft_count") or 0),
        "compliance_review_count": int(compiler_report.get("compliance_review_count") or 0),
        "tasks": [
            {
                **task,
                "status": (
                    "DUPLICATE"
                    if task.get("duplicate_of")
                    else (
                        "REVIEWING"
                        if task.get("compiler_ready")
                        else ("PARSED_REFERENCE_READY" if task.get("parse_status") == "extracted_reference_available" else "PARSING_REQUIRED")
                    )
                ),
                "artifact_refs": (
                    {
                        "ingest_report": report_path.as_posix(),
                        "review_queue": (wiki_dir / "review-queue.json").as_posix(),
                        "answer_card_drafts": (wiki_dir / "answer-card-drafts.json").as_posix(),
                        "compliance_review_pack": (wiki_dir / "compliance-review-pack.json").as_posix(),
                    }
                    if task.get("compiler_ready") and not task.get("duplicate_of")
                    else dict(task.get("artifact_refs") or {})
                ),
                "updated_at": _utc_now(),
            }
            for task in discovery["items"]
        ],
        "parser_jobs": parser_jobs,
        "ignored_items": discovery["ignored_items"],
        "duplicate_groups": discovery["duplicate_groups"],
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
