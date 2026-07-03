from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from hxy_knowledge.knowledge_compiler import compile_directory


SUPPORTED_SUFFIXES = {".md", ".txt"}


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
    for path in sorted(inbox_dir.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        content_hash = _hash_file(path)
        rel_path = _relative(path, root_dir)
        timestamp = _utc_now()
        items.append(
            {
                "version": "hxy-ingest-task.v1",
                "task_id": f"hxy-ingest-task:{content_hash[:16]}",
                "source_path": rel_path,
                "source_type": "file",
                "content_hash": content_hash,
                "status": "DISCOVERED",
                "official_use_allowed": False,
                "requires_human_review": True,
                "risk_flags": [],
                "artifact_refs": {},
                "created_at": timestamp,
                "updated_at": timestamp,
            }
        )
    return {"version": "hxy-ingest-discovery.v1", "count": len(items), "items": items}


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
        "extract_count": int(compiler_report.get("extract_count") or 0),
        "claim_count": int(compiler_report.get("claim_count") or 0),
        "review_queue_count": int(compiler_report.get("review_queue_count") or 0),
        "answer_card_draft_count": int(compiler_report.get("answer_card_draft_count") or 0),
        "tasks": [
            {
                **task,
                "status": "REVIEWING",
                "artifact_refs": {
                    "ingest_report": report_path.as_posix(),
                    "review_queue": (wiki_dir / "review-queue.json").as_posix(),
                    "answer_card_drafts": (wiki_dir / "answer-card-drafts.json").as_posix(),
                },
                "updated_at": _utc_now(),
            }
            for task in discovery["items"]
        ],
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "ingest_loop_outputs_are_candidates_until_human_review",
        "next_actions": [
            "在知识工作台复核 review queue。",
            "禁止自动发布 approved answer card。",
            "复核后再决定是否进入正式知识库。",
        ],
    }
    _write_json(Path(runs_dir) / run_id / "loop-state.json", state)
    return state
