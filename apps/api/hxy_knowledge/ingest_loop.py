from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hxy_knowledge.document_router import build_parser_plan
from hxy_knowledge.knowledge_compiler import compile_directory
from hxy_knowledge.parser_adapter import reference_manifest_path


TEXT_COMPILABLE_SUFFIXES = {".md", ".txt"}
PARSING_REQUIRED_SUFFIXES = {
    ".csv",
    ".doc",
    ".docx",
    ".epub",
    ".gif",
    ".html",
    ".htm",
    ".bmp",
    ".jpeg",
    ".jpg",
    ".json",
    ".pdf",
    ".png",
    ".ppt",
    ".pptx",
    ".tif",
    ".tiff",
    ".webp",
    ".xls",
    ".xlsx",
}
DISCOVERABLE_SUFFIXES = TEXT_COMPILABLE_SUFFIXES | PARSING_REQUIRED_SUFFIXES
MINERU_SUFFIXES: set[str] = set()
MARKITDOWN_SUFFIXES = {".csv", ".doc", ".docx", ".epub", ".html", ".htm", ".json", ".pdf", ".ppt", ".pptx", ".xls", ".xlsx"}
VISION_SUFFIXES = {".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp"}


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
    """Keep the suffix helper for older callers; routing is path-aware now."""
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


def _reference_matches_source(reference_path: Path, *, source_path: str, source_content_hash: str) -> bool:
    manifest_path = reference_manifest_path(reference_path)
    if not _is_file_safely(reference_path) or not _is_file_safely(manifest_path):
        return False
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return False
    quality = manifest.get("quality")
    parser = manifest.get("parser")
    if not isinstance(quality, dict):
        return False
    return (
        manifest.get("version") == "hxy-parser-reference.v1"
        and manifest.get("source_path") == source_path
        and manifest.get("source_content_hash") == source_content_hash
        and manifest.get("reference_content_hash") == _hash_file(reference_path)
        and parser in {"markitdown", "mineru", "ocr_or_vision"}
        and manifest.get("official_use_allowed") is False
        and quality.get("version") == "hxy-parser-quality.v1"
        and quality.get("status") in {"usable", "review"}
        and quality.get("needs_fallback") is False
        and quality.get("source_path") == source_path
        and quality.get("parser_strategy") == parser
    )


def _existing_extracted_reference_path(
    inbox_dir: Path,
    source_path: str,
    *,
    source_content_hash: str,
) -> Path | None:
    candidates = [
        _extracted_reference_path_for(inbox_dir, source_path),
        inbox_dir / "extracted-reference" / f"{Path(source_path).name}.reference.txt",
        inbox_dir / "extracted-reference" / f"{Path(source_path).stem}.reference.txt",
    ]
    for candidate in candidates:
        if _reference_matches_source(
            candidate,
            source_path=source_path,
            source_content_hash=source_content_hash,
        ):
            return candidate
    return None


def discover_inbox_materials(inbox_dir: Path, *, root_dir: Path) -> dict[str, Any]:
    items = []
    ignored_items = []
    seen_by_hash: dict[str, str] = {}
    for path in sorted(inbox_dir.rglob("*")):
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        rel_path = _relative(path, root_dir)
        if "extracted-reference/" in rel_path:
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
        extracted_reference_path = (
            None
            if compiler_ready
            else _existing_extracted_reference_path(
                inbox_dir,
                rel_path,
                source_content_hash=content_hash,
            )
        )
        extracted_reference_rel = (
            _relative(extracted_reference_path, root_dir)
            if not compiler_ready and extracted_reference_path is not None
            else ""
        )
        parser_plan = (
            build_parser_plan(path)
            if not compiler_ready and not extracted_reference_rel
            else None
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
                    else (
                        "compiled_from_extracted_reference"
                        if extracted_reference_rel
                        else f"{str(parser_plan.get('primary') if parser_plan else _parser_strategy_for_suffix(suffix))}_required"
                    )
                ),
                "parser_plan": parser_plan,
                "duplicate_of": duplicate_of,
                "canonical_source_path": duplicate_of or rel_path,
                "official_use_allowed": False,
                "requires_human_review": bool((parser_plan or {}).get("requires_human_review")),
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
                "parser_strategy": str(
                    (task.get("parser_plan") or {}).get("primary")
                    or _parser_strategy_for_suffix(suffix)
                ),
                "parser_fallbacks": list((task.get("parser_plan") or {}).get("fallbacks") or []),
                "parser_plan": task.get("parser_plan") or {},
                "preflight": dict((task.get("parser_plan") or {}).get("preflight") or {}),
                "status": "PENDING",
                "output_contract": "write extracted text/reference artifact, then rerun ingest loop",
                "official_use_allowed": False,
                "requires_human_review": bool(task.get("requires_human_review")),
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
    compiler_source_paths = []
    for task in discovery["items"]:
        if task.get("duplicate_of"):
            continue
        if task.get("compiler_ready"):
            compiler_source_paths.append(root_dir / str(task["source_path"]))
            continue
        extracted_reference = str((task.get("artifact_refs") or {}).get("extracted_reference") or "")
        if task.get("parse_status") == "extracted_reference_available" and extracted_reference:
            compiler_source_paths.append(root_dir / extracted_reference)
    compiler_report = compile_directory(raw_dir, wiki_dir, source_paths=compiler_source_paths)
    _write_json(report_path, _public_compiler_report(compiler_report))
    parser_jobs = _build_parser_jobs(discovery["items"])
    parser_exception_count = sum(
        1
        for task in discovery["items"]
        if not task.get("duplicate_of") and bool(task.get("requires_human_review"))
    )
    promotion_review_pending = bool(
        int(compiler_report.get("review_queue_count") or 0)
        or int(compiler_report.get("compliance_review_count") or 0)
    )
    if parser_exception_count:
        run_status = "review_required"
        stop_reason = "parser_exception_requires_human"
    elif parser_jobs:
        run_status = "parsing_required"
        stop_reason = "parser_jobs_pending"
    elif promotion_review_pending:
        run_status = "candidate_ready"
        stop_reason = "candidate_knowledge_not_promoted"
    else:
        run_status = "completed"
        stop_reason = "automated_ingest_complete"

    state = {
        "version": "hxy-ingest-loop-state.v1",
        "run_id": run_id,
        "status": run_status,
        "stop_reason": stop_reason,
        "task_count": discovery["count"],
        "unique_count": discovery["unique_count"],
        "duplicate_count": discovery["duplicate_count"],
        "compiler_ready_count": discovery["compiler_ready_count"],
        "compiler_ready_unique_count": discovery["compiler_ready_unique_count"],
        "parsing_required_count": discovery["parsing_required_count"],
        "parsed_reference_count": discovery["parsed_reference_count"],
        "ignored_count": discovery["ignored_count"],
        "parser_job_count": len(parser_jobs),
        "parser_exception_count": parser_exception_count,
        "extract_count": int(compiler_report.get("extract_count") or 0),
        "claim_count": int(compiler_report.get("claim_count") or 0),
        "review_queue_count": int(compiler_report.get("review_queue_count") or 0),
        "claim_triage_cluster_count": int(compiler_report.get("claim_triage_cluster_count") or 0),
        "claim_triage_selected_count": int(compiler_report.get("claim_triage_selected_count") or 0),
        "claim_triage_reduction_count": int(compiler_report.get("claim_triage_reduction_count") or 0),
        "answer_card_draft_count": int(compiler_report.get("answer_card_draft_count") or 0),
        "compliance_review_count": int(compiler_report.get("compliance_review_count") or 0),
        "tasks": [
            {
                **task,
                "status": (
                    "DUPLICATE"
                    if task.get("duplicate_of")
                    else (
                        "COMPILED"
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
        "requires_human_review": bool(parser_exception_count),
        "promotion_review_pending": promotion_review_pending,
        "authority_rule": "ingest_completion_does_not_promote_candidate_knowledge",
        "next_actions": [
            "在知识工作台复核 review queue。",
            "先解析 PDF/DOCX/PPTX/图片等非文本资料，再进入编译。",
            "禁止自动发布 approved answer card。",
            "复核后再决定是否进入正式知识库。",
        ],
    }
    _write_json(Path(runs_dir) / run_id / "loop-state.json", state)
    return state
