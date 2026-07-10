from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .material_chunker import chunk_markdown
from .material_parser import (
    MaterialParseError,
    MaterialParseResult,
    build_artifact_storage_keys,
    parse_with_markitdown,
)
from .material_repository import MaterialJobLeaseLost
from .source_card import build_source_card


Parser = Callable[[Path], MaterialParseResult]


def _safe_path(root: Path, storage_key: str) -> Path | None:
    resolved_root = root.resolve()
    candidate = (resolved_root / storage_key).resolve()
    return candidate if candidate.is_relative_to(resolved_root) else None


def _error_summary(code: str) -> str:
    return {
        "source_missing": "saved source material is unavailable",
        "invalid_storage_path": "saved source material path is invalid",
        "empty_parse_output": "parser produced no usable text",
        "parser_dependency_missing": "document parser is temporarily unavailable",
        "parser_io_error": "document parser could not read the source",
        "parser_error": "document parser could not understand the source",
    }.get(code, "material processing did not complete")


def _deep_understanding(
    preliminary: dict[str, Any],
    parsed: MaterialParseResult,
) -> dict[str, Any]:
    compact = " ".join(parsed.text_content.replace("\x00", " ").split())
    return {
        **preliminary,
        "summary": compact[:600] or str(preliminary.get("summary") or ""),
        "parse_status": "extracted",
        "confidence": "high" if len(parsed.text_content) >= 500 else "medium",
        "warnings": list(parsed.warnings),
        "official_use_allowed": False,
        "use_boundary": str(
            preliminary.get("use_boundary")
            or "可用于理解和整理资料，未经核定不能作为荷小悦正式口径。"
        )[:300],
    }


def _artifact_payload(
    root: Path,
    storage_key: str,
    content: bytes,
    *,
    artifact_type: str,
    metadata: dict[str, Any],
) -> tuple[dict[str, Any], Path]:
    destination = _safe_path(root, storage_key)
    if destination is None:
        raise MaterialParseError(
            "invalid_storage_path",
            "derived artifact path is outside material storage",
            retryable=False,
        )
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f".{destination.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as output:
            output.write(content)
        temporary.chmod(0o600)
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return (
        {
            "artifact_id": str(uuid4()),
            "artifact_type": artifact_type,
            "storage_key": storage_key,
            "sha256": hashlib.sha256(content).hexdigest(),
            "size_bytes": len(content),
            "metadata": metadata,
        },
        destination,
    )


def _record_failure(
    repository: Any,
    job: dict[str, Any],
    worker_id: str,
    error: MaterialParseError,
    *,
    base_retry_seconds: int,
) -> dict[str, str]:
    retry_delay = min(
        max(base_retry_seconds, 1) * (2 ** max(int(job["attempt_number"]) - 1, 0)),
        3600,
    )
    outcome = repository.retry_or_fail_job(
        job["job_id"],
        worker_id,
        retryable=error.retryable,
        error_code=error.code,
        error_summary=_error_summary(error.code),
        retry_delay_seconds=retry_delay,
        parser_name="markitdown",
        parser_version=None,
    )
    return {
        "status": str(outcome),
        "job_id": str(job["job_id"]),
        "error_code": error.code,
    }


def process_one_material_job(
    repository: Any,
    *,
    material_root: Path,
    worker_id: str,
    lease_seconds: int,
    base_retry_seconds: int,
    parser: Parser = parse_with_markitdown,
) -> dict[str, str]:
    repository.reclaim_stale_leases(limit=100)
    job = repository.claim_next_job(worker_id, lease_seconds=lease_seconds)
    if job is None:
        return {"status": "idle"}

    source = _safe_path(material_root, str(job.get("storage_key") or ""))
    if source is None:
        return _record_failure(
            repository,
            job,
            worker_id,
            MaterialParseError(
                "invalid_storage_path",
                "source path is outside material storage",
                retryable=False,
            ),
            base_retry_seconds=base_retry_seconds,
        )
    if not source.is_file():
        return _record_failure(
            repository,
            job,
            worker_id,
            MaterialParseError(
                "source_missing",
                "source material does not exist",
                retryable=False,
            ),
            base_retry_seconds=base_retry_seconds,
        )

    try:
        parsed = parser(source)
    except MaterialParseError as error:
        return _record_failure(
            repository,
            job,
            worker_id,
            error,
            base_retry_seconds=base_retry_seconds,
        )
    except Exception:
        return _record_failure(
            repository,
            job,
            worker_id,
            MaterialParseError(
                "parser_error",
                "unexpected parser error",
                retryable=True,
            ),
            base_retry_seconds=base_retry_seconds,
        )

    material = {
        "material_id": job["material_id"],
        "file_name": job["file_name"],
        "sha256": job["sha256"],
        "size_bytes": job["size_bytes"],
        "understanding": job.get("understanding") or {},
    }
    source_card = build_source_card(material, parsed)
    keys = build_artifact_storage_keys(
        str(job["assignment_id"]),
        str(job["material_id"]),
        str(job["job_id"]),
    )
    written_paths: list[Path] = []
    try:
        markdown_artifact, markdown_path = _artifact_payload(
            material_root,
            keys["normalized_markdown"],
            parsed.text_content.encode("utf-8"),
            artifact_type="normalized_markdown",
            metadata={
                "parser": parsed.parser_name,
                "parser_version": parsed.parser_version,
                "official_use_allowed": False,
            },
        )
        written_paths.append(markdown_path)
        card_bytes = json.dumps(
            source_card,
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        source_card_artifact, source_card_path = _artifact_payload(
            material_root,
            keys["source_card"],
            card_bytes,
            artifact_type="source_card",
            metadata={
                "version": source_card["version"],
                "official_use_allowed": False,
            },
        )
        written_paths.append(source_card_path)
        chunk_records = [
            {
                "chunk_id": str(uuid4()),
                "artifact_id": markdown_artifact["artifact_id"],
                "chunk_index": chunk.chunk_index,
                "heading": chunk.heading,
                "content": chunk.content,
                "char_count": len(chunk.content),
                "official_use_allowed": False,
            }
            for chunk in chunk_markdown(
                parsed.text_content,
                default_heading=parsed.title or str(job.get("file_name") or ""),
            )
        ]
        repository.complete_job(
            job["job_id"],
            worker_id,
            artifacts=[markdown_artifact, source_card_artifact],
            chunks=chunk_records,
            understanding=_deep_understanding(job.get("understanding") or {}, parsed),
            parser_name=parsed.parser_name,
            parser_version=parsed.parser_version,
        )
    except MaterialJobLeaseLost:
        for path in written_paths:
            path.unlink(missing_ok=True)
        return {"status": "lost_lease", "job_id": str(job["job_id"])}
    except MaterialParseError as error:
        for path in written_paths:
            path.unlink(missing_ok=True)
        return _record_failure(
            repository,
            job,
            worker_id,
            error,
            base_retry_seconds=base_retry_seconds,
        )
    except Exception:
        for path in written_paths:
            path.unlink(missing_ok=True)
        return _record_failure(
            repository,
            job,
            worker_id,
            MaterialParseError(
                "artifact_commit_error",
                "artifact commit did not complete",
                retryable=True,
            ),
            base_retry_seconds=base_retry_seconds,
        )

    return {"status": "succeeded", "job_id": str(job["job_id"])}
