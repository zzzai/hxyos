from __future__ import annotations

import json
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MARKITDOWN_STRATEGY = "markitdown"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_source_path(root_dir: Path, source_path: str) -> Path | None:
    root = root_dir.resolve()
    candidate = (root / source_path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate


def _output_path_for(output_dir: Path, source_path: str) -> Path:
    clean_source = source_path.strip("/").replace("\\", "/")
    return output_dir / f"{clean_source}.reference.txt"


def _skip_result(job: dict[str, Any], *, status: str, reason: str, dependency: str | None = None) -> dict[str, Any]:
    result = {
        "version": "hxy-parser-job-result.v1",
        "job_id": job.get("job_id") or "",
        "source_path": job.get("source_path") or "",
        "parser": job.get("parser_strategy") or "",
        "status": status,
        "reason": reason,
        "output_path": None,
        "official_use_allowed": False,
        "requires_human_review": True,
        "created_at": _utc_now(),
    }
    if dependency:
        result["dependency"] = dependency
    return result


def _run_markitdown_job(job: dict[str, Any], *, root_dir: Path, output_dir: Path, timeout_seconds: int) -> dict[str, Any]:
    markitdown = shutil.which("markitdown")
    if not markitdown:
        return _skip_result(
            job,
            status="SKIPPED_DEPENDENCY_MISSING",
            reason="markitdown executable not found in PATH",
            dependency="markitdown",
        )

    source_path = str(job.get("source_path") or "")
    source = _safe_source_path(root_dir, source_path)
    if source is None:
        return _skip_result(job, status="FAILED_INVALID_SOURCE", reason="source path is outside HXY root")
    if not source.is_file():
        return _skip_result(job, status="FAILED_MISSING_SOURCE", reason="source file does not exist")

    try:
        completed = subprocess.run(
            [markitdown, str(source)],
            check=False,
            text=True,
            capture_output=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired:
        return _skip_result(job, status="FAILED_TIMEOUT", reason=f"markitdown exceeded {timeout_seconds}s timeout")

    if completed.returncode != 0:
        return {
            **_skip_result(job, status="FAILED_PARSER_ERROR", reason=(completed.stderr or "").strip()),
            "returncode": completed.returncode,
        }

    output_path = _output_path_for(output_dir, source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(completed.stdout, encoding="utf-8")
    return {
        "version": "hxy-parser-job-result.v1",
        "job_id": job.get("job_id") or "",
        "source_path": source_path,
        "parser": MARKITDOWN_STRATEGY,
        "status": "EXTRACTED",
        "reason": "parsed_by_markitdown_cli",
        "output_path": output_path.as_posix(),
        "byte_count": source.stat().st_size,
        "char_count": len(completed.stdout),
        "official_use_allowed": False,
        "requires_human_review": True,
        "created_at": _utc_now(),
    }


def run_parser_jobs(
    parser_jobs: list[dict[str, Any]],
    *,
    root_dir: Path,
    output_dir: Path,
    strategies: set[str] | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    allowed_strategies = strategies or {MARKITDOWN_STRATEGY}
    items = []
    for job in parser_jobs:
        strategy = str(job.get("parser_strategy") or "")
        if strategy not in allowed_strategies:
            items.append(_skip_result(job, status="SKIPPED_UNSUPPORTED_STRATEGY", reason=f"strategy {strategy} not enabled"))
            continue
        if strategy == MARKITDOWN_STRATEGY:
            items.append(_run_markitdown_job(job, root_dir=root_dir, output_dir=output_dir, timeout_seconds=timeout_seconds))
            continue
        items.append(_skip_result(job, status="SKIPPED_UNSUPPORTED_STRATEGY", reason=f"strategy {strategy} not implemented"))

    payload = {
        "version": "hxy-parser-run.v1",
        "generated_at": _utc_now(),
        "root_dir": root_dir.resolve().as_posix(),
        "output_dir": output_dir.as_posix(),
        "job_count": len(parser_jobs),
        "processed_count": sum(1 for item in items if item["status"] == "EXTRACTED"),
        "failed_count": sum(1 for item in items if str(item["status"]).startswith("FAILED")),
        "skipped_count": sum(1 for item in items if str(item["status"]).startswith("SKIPPED")),
        "items": items,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "parser_outputs_are_reference_materials_until_reviewed",
    }
    _write_json(output_dir / "parser-run-manifest.json", payload)
    return payload
