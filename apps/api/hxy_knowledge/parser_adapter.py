from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4


MARKITDOWN_STRATEGY = "markitdown"
MINERU_STRATEGY = "mineru"
VISION_STRATEGY = "ocr_or_vision"
MANUAL_REVIEW_STRATEGY = "manual_review"
_SHA256_PATTERN = re.compile(r"^[0-9a-fA-F]{64}$")


class UnsafeOutputError(ValueError):
    """Raised when a parser artifact path crosses its configured trust root."""


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _resolve_cli(command: str) -> str | None:
    return shutil.which(command) or shutil.which(command, path=str(Path(sys.executable).parent))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    staging_path = path.parent / f".{path.name}.{uuid4().hex}.tmp"
    try:
        staging_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        staging_path.replace(path)
    finally:
        staging_path.unlink(missing_ok=True)


def _hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def reference_manifest_path(reference_path: Path) -> Path:
    path_key = hashlib.sha256(reference_path.name.encode("utf-8")).hexdigest()
    return reference_path.parent / ".reference-manifests" / f"{path_key}.json"


def _safe_output_root(output_dir: Path) -> Path:
    output = Path(output_dir)
    if output.is_symlink():
        raise UnsafeOutputError("parser output directory cannot be a symlink")
    output.mkdir(parents=True, exist_ok=True)
    if output.is_symlink() or not output.is_dir():
        raise UnsafeOutputError("parser output directory is not a safe directory")
    return output.resolve()


def _ensure_safe_directory(output_root: Path, directory: Path) -> Path:
    root = output_root.resolve()
    candidate = Path(directory)
    try:
        relative = candidate.relative_to(root)
    except ValueError as error:
        raise UnsafeOutputError("parser artifact directory is outside output root") from error

    current = root
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise UnsafeOutputError("parser artifact directory contains a symlink")
        if current.exists():
            if not current.is_dir():
                raise UnsafeOutputError("parser artifact directory component is not a directory")
        else:
            current.mkdir()
        if current.is_symlink():
            raise UnsafeOutputError("parser artifact directory became a symlink")
        try:
            current.resolve().relative_to(root)
        except ValueError as error:
            raise UnsafeOutputError("parser artifact directory escaped output root") from error
    return current


def _prepare_reference_directories(output_root: Path, reference_path: Path) -> None:
    parent = _ensure_safe_directory(output_root, reference_path.parent)
    if reference_path.is_symlink():
        raise UnsafeOutputError("parser reference cannot replace a symlink")
    _ensure_safe_directory(output_root, parent / ".reference-staging")
    _ensure_safe_directory(output_root, parent / ".reference-manifests")


def _isolated_parser_source(
    source: Path,
    *,
    output_root: Path,
    job_component: str,
) -> tuple[tempfile.TemporaryDirectory[str], Path, Path]:
    attempts_root = _ensure_safe_directory(output_root, output_root / ".parser-attempts")
    temporary = tempfile.TemporaryDirectory(prefix=f"{job_component}-", dir=attempts_root)
    attempt_dir = Path(temporary.name)
    isolated_source = attempt_dir / source.name
    shutil.copyfile(source, isolated_source)
    return temporary, isolated_source, attempt_dir


def _source_hash_or_failure(job: dict[str, Any], source: Path) -> tuple[str | None, dict[str, Any] | None]:
    expected_hash = str(job.get("content_hash") or "")
    if not expected_hash:
        return None, _skip_result(
            job,
            status="FAILED_MISSING_SOURCE_HASH",
            reason="parser job must include the source SHA-256 hash",
        )
    if not _SHA256_PATTERN.fullmatch(expected_hash):
        return None, _skip_result(
            job,
            status="FAILED_INVALID_SOURCE_HASH",
            reason="parser job source hash is not a valid SHA-256 digest",
        )
    expected_hash = expected_hash.lower()
    actual_hash = _hash_file(source)
    if actual_hash != expected_hash:
        return None, _skip_result(
            job,
            status="FAILED_SOURCE_HASH_MISMATCH",
            reason="source content hash no longer matches the parser job",
        )
    return expected_hash, None


def _source_changed_result(job: dict[str, Any], source: Path, expected_hash: str) -> dict[str, Any] | None:
    if _hash_file(source) == expected_hash:
        return None
    return _skip_result(
        job,
        status="FAILED_SOURCE_CHANGED",
        reason="source changed while parser job was running",
    )


def _write_reference_manifest(
    reference_path: Path,
    *,
    output_root: Path,
    source_path: str,
    source_content_hash: str,
    parser: str,
    quality: dict[str, Any],
) -> Path:
    manifest_path = reference_manifest_path(reference_path)
    _ensure_safe_directory(output_root, manifest_path.parent)
    if manifest_path.is_symlink():
        raise UnsafeOutputError("parser reference manifest cannot replace a symlink")
    _write_json(
        manifest_path,
        {
            "version": "hxy-parser-reference.v1",
            "source_path": source_path,
            "source_content_hash": source_content_hash,
            "reference_content_hash": _hash_file(reference_path),
            "parser": parser,
            "quality": quality,
            "official_use_allowed": False,
            "created_at": _utc_now(),
        },
    )
    return manifest_path


def _write_reference_artifact(reference_path: Path, text: str, *, output_root: Path) -> None:
    _prepare_reference_directories(output_root, reference_path)
    staging_dir = _ensure_safe_directory(
        output_root,
        reference_path.parent / ".reference-staging",
    )
    staging_path = staging_dir / f"{uuid4().hex}.txt"
    try:
        staging_path.write_text(text, encoding="utf-8")
        staging_path.replace(reference_path)
    finally:
        staging_path.unlink(missing_ok=True)


def _normalise_source_path(source_path: str) -> PurePosixPath | None:
    if not source_path or "\\" in source_path or "\x00" in source_path:
        return None
    relative = PurePosixPath(source_path)
    if relative.is_absolute() or any(part in {"", ".", ".."} for part in relative.parts):
        return None
    if relative.parts[:3] != ("knowledge", "raw", "inbox") or len(relative.parts) < 4:
        return None
    return relative


def _safe_source_path(root_dir: Path, source_path: str) -> Path | None:
    relative = _normalise_source_path(source_path)
    if relative is None:
        return None
    inbox = (root_dir.resolve() / "knowledge" / "raw" / "inbox").resolve()
    candidate = (root_dir.resolve() / Path(*relative.parts)).resolve()
    try:
        candidate.relative_to(inbox)
    except ValueError:
        return None
    return candidate


def _output_path_for(output_dir: Path, source_path: str) -> Path | None:
    relative = _normalise_source_path(source_path)
    if relative is None:
        return None
    output_root = output_dir.resolve()
    candidate = (output_root / f"{relative.as_posix()}.reference.txt").resolve()
    try:
        candidate.relative_to(output_root)
    except ValueError:
        return None
    return candidate


def _safe_artifact_component(value: str) -> str:
    safe = "".join(char if char.isalnum() or char in "._-" else "-" for char in value)
    return safe[:96] or "job"


def _find_mineru_markdown(output_dir: Path, source: Path) -> Path | None:
    markdown_paths = [path for path in output_dir.rglob("*.md") if path.is_file()]
    if not markdown_paths:
        return None

    source_stem = source.stem

    def sort_key(path: Path) -> tuple[int, int, str]:
        stem_match = 0 if path.stem == source_stem else 1
        try:
            size = path.stat().st_size
        except OSError:
            size = 0
        return (stem_match, -size, path.as_posix())

    return sorted(markdown_paths, key=sort_key)[0]


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


def _pending_adapter_result(job: dict[str, Any]) -> dict[str, Any]:
    return {
        "version": "hxy-parser-job-result.v1",
        "job_id": job.get("job_id") or "",
        "source_path": job.get("source_path") or "",
        "parser": job.get("parser_strategy") or VISION_STRATEGY,
        "status": "PENDING_ADAPTER",
        "reason": "configured OCR or vision adapter is not connected yet",
        "output_path": None,
        "official_use_allowed": False,
        "requires_human_review": False,
        "created_at": _utc_now(),
    }


def assess_extraction_quality(
    text: str,
    *,
    source_path: str = "",
    preflight: dict[str, Any] | None = None,
    parser_strategy: str = "",
) -> dict[str, Any]:
    """Check whether parser output is structurally usable before model analysis.

    This is a parser quality gate, not a truth or authority score.  It only
    decides whether the output is complete enough to pass to the understanding
    layer or whether another parser/visual check should be tried first.
    """

    facts = dict(preflight or {})
    compact = " ".join(str(text or "").replace("\x00", " ").split())
    raw_char_count = len(str(text or ""))
    page_count = facts.get("page_count")
    sampled_page_count = facts.get("sampled_page_count")
    image_page_count = facts.get("image_page_count")
    try:
        pages = max(int(page_count), 0) if page_count is not None else 0
    except (TypeError, ValueError):
        pages = 0
    try:
        sampled_pages = max(int(sampled_page_count), 0) if sampled_page_count is not None else 0
    except (TypeError, ValueError):
        sampled_pages = 0
    try:
        image_pages = max(int(image_page_count), 0) if image_page_count is not None else 0
    except (TypeError, ValueError):
        image_pages = 0

    signals: list[str] = []
    if not compact:
        signals.append("empty_output")
    minimum_chars = 8
    try:
        item_count = max(int(facts.get("item_count")), 0)
    except (TypeError, ValueError):
        item_count = 0
    try:
        size_bytes = max(int(facts.get("size_bytes")), 0)
    except (TypeError, ValueError):
        size_bytes = 0
    if item_count:
        minimum_chars = max(minimum_chars, min(item_count * 4, 128))
    if size_bytes >= 10 * 1024 * 1024:
        minimum_chars = max(minimum_chars, 128)
    elif size_bytes >= 1024 * 1024:
        minimum_chars = max(minimum_chars, 32)
    if compact and len(compact) < minimum_chars:
        signals.append("sparse_output")
    image_ratio_pages = sampled_pages or pages
    if image_ratio_pages and (image_pages / image_ratio_pages >= 0.5 or facts.get("image_heavy") is True):
        signals.append("image_heavy")
    try:
        sampled_chars = max(int(facts.get("sample_text_chars")), 0)
    except (TypeError, ValueError):
        sampled_chars = 0
    if sampled_chars:
        if raw_char_count < max(4, sampled_chars * 0.5) and "sparse_output" not in signals:
            signals.append("sparse_output")
    elif pages and raw_char_count < max(32, pages * 8) and "sparse_output" not in signals:
        signals.append("sparse_output")
    if facts.get("table_signal") is True and "|" not in str(text or ""):
        signals.append("table_structure_unconfirmed")
    if re.search(r"^#{1,6}\s+", str(text or ""), flags=re.MULTILINE):
        signals.append("headings_present")
    if re.search(r"\b(page|页|slide|幻灯片)\s*\d+\b", str(text or ""), flags=re.IGNORECASE):
        signals.append("source_markers_present")

    fatal_signals = {"empty_output", "sparse_output"}.intersection(signals)
    repairable_structure_signals = {"image_heavy", "table_structure_unconfirmed"}.intersection(signals)
    needs_fallback = bool(
        fatal_signals
        or (parser_strategy == MARKITDOWN_STRATEGY and repairable_structure_signals)
    )
    requires_visual_review = "image_heavy" in signals or "table_structure_unconfirmed" in signals
    status = "unusable" if needs_fallback else ("review" if requires_visual_review else "usable")
    return {
        "version": "hxy-parser-quality.v1",
        "status": status,
        "score": 0 if status == "unusable" else (70 if status == "review" else 100),
        "char_count": raw_char_count,
        "signals": signals,
        "needs_fallback": needs_fallback,
        "requires_visual_review": requires_visual_review,
        "source_path": source_path,
        "parser_strategy": parser_strategy,
        "checks": {
            "non_empty": "empty_output" not in signals,
            "not_suspiciously_sparse": "sparse_output" not in signals,
            "heading_structure_observed": "headings_present" in signals,
            "source_markers_observed": "source_markers_present" in signals,
            "table_structure_observed": "table_structure_unconfirmed" not in signals,
            "minimum_content_observed": len(compact) >= minimum_chars,
        },
    }


def _missing_module_from_error(message: str) -> str | None:
    marker = "No module named '"
    if marker not in message:
        return None
    remainder = message.split(marker, 1)[1]
    return remainder.split("'", 1)[0] or None


def _run_markitdown_job(
    job: dict[str, Any],
    *,
    root_dir: Path,
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    markitdown = _resolve_cli("markitdown")
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
    source_content_hash, hash_failure = _source_hash_or_failure(job, source)
    if hash_failure is not None:
        return hash_failure
    assert source_content_hash is not None

    try:
        temporary, isolated_source, _attempt_dir = _isolated_parser_source(
            source,
            output_root=output_dir,
            job_component=_safe_artifact_component(str(job.get("job_id") or source.stem)),
        )
    except UnsafeOutputError as error:
        return _skip_result(job, status="FAILED_UNSAFE_OUTPUT", reason=str(error))
    except OSError as error:
        return _skip_result(job, status="FAILED_INPUT_COPY", reason=str(error))

    with temporary:
        try:
            completed = subprocess.run(
                [markitdown, str(isolated_source)],
                check=False,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return _skip_result(
                job,
                status="FAILED_TIMEOUT",
                reason=f"markitdown exceeded {timeout_seconds}s timeout",
            )

        if completed.returncode != 0:
            return {
                **_skip_result(
                    job,
                    status="FAILED_PARSER_ERROR",
                    reason=(completed.stderr or "").strip(),
                ),
                "returncode": completed.returncode,
            }

        source_changed = _source_changed_result(job, source, source_content_hash)
        if source_changed is not None:
            return source_changed

        output_path = _output_path_for(output_dir, source_path)
        if output_path is None:
            return _skip_result(
                job,
                status="FAILED_INVALID_OUTPUT",
                reason="reference path is outside parser output directory",
            )
        quality = assess_extraction_quality(
            completed.stdout,
            source_path=source_path,
            preflight=job.get("preflight"),
            parser_strategy=MARKITDOWN_STRATEGY,
        )
        return {
            "version": "hxy-parser-job-result.v1",
            "job_id": job.get("job_id") or "",
            "source_path": source_path,
            "parser": MARKITDOWN_STRATEGY,
            "status": "EXTRACTED",
            "reason": "parsed_by_markitdown_cli",
            "output_path": None,
            "source_content_hash": source_content_hash,
            "_extracted_text": completed.stdout,
            "byte_count": source.stat().st_size,
            "char_count": len(completed.stdout),
            "quality": quality,
            "official_use_allowed": False,
            "requires_human_review": quality["status"] != "usable",
            "created_at": _utc_now(),
        }


def _run_mineru_job(job: dict[str, Any], *, root_dir: Path, output_dir: Path, timeout_seconds: int) -> dict[str, Any]:
    mineru = _resolve_cli("mineru")
    if not mineru:
        return _skip_result(
            job,
            status="SKIPPED_DEPENDENCY_MISSING",
            reason="mineru executable not found in PATH",
            dependency="mineru",
        )

    source_path = str(job.get("source_path") or "")
    source = _safe_source_path(root_dir, source_path)
    if source is None:
        return _skip_result(job, status="FAILED_INVALID_SOURCE", reason="source path is outside HXY root")
    if not source.is_file():
        return _skip_result(job, status="FAILED_MISSING_SOURCE", reason="source file does not exist")
    source_content_hash, hash_failure = _source_hash_or_failure(job, source)
    if hash_failure is not None:
        return hash_failure
    assert source_content_hash is not None

    try:
        temporary, isolated_source, attempt_dir = _isolated_parser_source(
            source,
            output_root=output_dir,
            job_component=_safe_artifact_component(str(job.get("job_id") or source.stem)),
        )
    except UnsafeOutputError as error:
        return _skip_result(job, status="FAILED_UNSAFE_OUTPUT", reason=str(error))
    except OSError as error:
        return _skip_result(job, status="FAILED_INPUT_COPY", reason=str(error))

    with temporary:
        mineru_output_dir = attempt_dir / "mineru-output"
        mineru_output_dir.mkdir()
        try:
            completed = subprocess.run(
                [
                    mineru,
                    "-p",
                    str(isolated_source),
                    "-o",
                    str(mineru_output_dir),
                    "-b",
                    "pipeline",
                    "-m",
                    "auto",
                ],
                check=False,
                text=True,
                capture_output=True,
                timeout=timeout_seconds,
            )
        except subprocess.TimeoutExpired:
            return _skip_result(
                job,
                status="FAILED_TIMEOUT",
                reason=f"mineru exceeded {timeout_seconds}s timeout",
            )

        if completed.returncode != 0:
            reason = (completed.stderr or completed.stdout or "").strip()
            missing_module = _missing_module_from_error(reason)
            if missing_module:
                return _skip_result(
                    job,
                    status="SKIPPED_DEPENDENCY_MISSING",
                    reason=reason,
                    dependency=missing_module,
                )
            return {
                **_skip_result(job, status="FAILED_PARSER_ERROR", reason=reason),
                "returncode": completed.returncode,
            }

        source_changed = _source_changed_result(job, source, source_content_hash)
        if source_changed is not None:
            return source_changed

        markdown_path = _find_mineru_markdown(mineru_output_dir, isolated_source)
        if markdown_path is None:
            return _skip_result(
                job,
                status="FAILED_NO_OUTPUT",
                reason="mineru did not produce a markdown artifact",
            )

        extracted_text = markdown_path.read_text(encoding="utf-8")
        quality = assess_extraction_quality(
            extracted_text,
            source_path=source_path,
            preflight=job.get("preflight"),
            parser_strategy=MINERU_STRATEGY,
        )
        output_path = _output_path_for(output_dir, source_path)
        if output_path is None:
            return _skip_result(
                job,
                status="FAILED_INVALID_OUTPUT",
                reason="reference path is outside parser output directory",
            )
        return {
            "version": "hxy-parser-job-result.v1",
            "job_id": job.get("job_id") or "",
            "source_path": source_path,
            "parser": MINERU_STRATEGY,
            "status": "EXTRACTED",
            "reason": "parsed_by_mineru_cli",
            "output_path": None,
            "source_content_hash": source_content_hash,
            "_extracted_text": extracted_text,
            "mineru_artifact_path": markdown_path.relative_to(attempt_dir).as_posix(),
            "mineru_artifact_retained": False,
            "byte_count": source.stat().st_size,
            "char_count": len(extracted_text),
            "quality": quality,
            "official_use_allowed": False,
            "requires_human_review": quality["status"] != "usable",
            "created_at": _utc_now(),
        }


def _run_parser_job_once(
    job: dict[str, Any],
    strategy: str,
    *,
    root_dir: Path,
    output_dir: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    attempt_job = {**job, "parser_strategy": strategy}
    if strategy == MARKITDOWN_STRATEGY:
        return _run_markitdown_job(
            attempt_job,
            root_dir=root_dir,
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
        )
    if strategy == MINERU_STRATEGY:
        return _run_mineru_job(
            attempt_job,
            root_dir=root_dir,
            output_dir=output_dir,
            timeout_seconds=timeout_seconds,
        )
    return _skip_result(
        attempt_job,
        status="SKIPPED_UNSUPPORTED_STRATEGY",
        reason=f"strategy {strategy} not implemented",
    )


def run_parser_jobs(
    parser_jobs: list[dict[str, Any]],
    *,
    root_dir: Path,
    output_dir: Path,
    strategies: set[str] | None = None,
    timeout_seconds: int = 120,
) -> dict[str, Any]:
    try:
        output_root = _safe_output_root(output_dir)
    except (OSError, UnsafeOutputError) as error:
        return {
            "version": "hxy-parser-run.v1",
            "generated_at": _utc_now(),
            "root_dir": root_dir.resolve().as_posix(),
            "output_dir": Path(output_dir).as_posix(),
            "job_count": len(parser_jobs),
            "processed_count": 0,
            "failed_count": len(parser_jobs),
            "skipped_count": 0,
            "pending_count": 0,
            "items": [
                _skip_result(
                    job,
                    status="FAILED_UNSAFE_OUTPUT",
                    reason=str(error),
                )
                for job in parser_jobs
            ],
            "official_use_allowed": False,
            "requires_human_review": bool(parser_jobs),
            "authority_rule": "parser_outputs_are_non_authoritative_and_review_is_exception_based",
        }

    allowed_strategies = strategies if strategies is not None else {MARKITDOWN_STRATEGY, MINERU_STRATEGY}
    items = []
    for job in parser_jobs:
        source_path = str(job.get("source_path") or "")
        source = _safe_source_path(root_dir, source_path)
        if source is None:
            items.append(
                _skip_result(
                    job,
                    status="FAILED_INVALID_SOURCE",
                    reason="source path is outside HXY inbox",
                )
            )
            continue
        if not source.is_file():
            items.append(
                _skip_result(
                    job,
                    status="FAILED_MISSING_SOURCE",
                    reason="source file does not exist",
                )
            )
            continue
        _source_hash, hash_failure = _source_hash_or_failure(job, source)
        if hash_failure is not None:
            items.append(hash_failure)
            continue

        primary_strategy = str(job.get("parser_strategy") or "")
        automation_state = str((job.get("parser_plan") or {}).get("automation_state") or "")
        if primary_strategy == VISION_STRATEGY or automation_state == "pending_adapter":
            pending = _pending_adapter_result(job)
            pending["attempts"] = [
                {
                    "parser": primary_strategy or VISION_STRATEGY,
                    "status": "PENDING_ADAPTER",
                    "reason": pending["reason"],
                    "quality": None,
                }
            ]
            items.append(pending)
            continue

        strategies_for_job = [str(job.get("parser_strategy") or "")]
        strategies_for_job.extend(str(value) for value in (job.get("parser_fallbacks") or []))
        strategies_for_job = list(dict.fromkeys(value for value in strategies_for_job if value))
        attempts: list[dict[str, Any]] = []
        selected: dict[str, Any] | None = None
        last_result: dict[str, Any] | None = None

        for strategy in strategies_for_job:
            if strategy not in allowed_strategies:
                result = _skip_result(
                    {**job, "parser_strategy": strategy},
                    status="SKIPPED_UNSUPPORTED_STRATEGY",
                    reason=f"strategy {strategy} not enabled",
                )
            else:
                result = _run_parser_job_once(
                    job,
                    strategy,
                    root_dir=root_dir,
                    output_dir=output_root,
                    timeout_seconds=timeout_seconds,
                )
            last_result = result
            attempts.append(
                {
                    "parser": result.get("parser") or strategy,
                    "status": result.get("status"),
                    "reason": result.get("reason"),
                    "quality": result.get("quality"),
                }
            )
            if result.get("status") != "EXTRACTED":
                continue
            if result.get("quality", {}).get("needs_fallback"):
                continue
            selected = result
            break

        if selected is None:
            selected = last_result or _skip_result(
                job,
                status="SKIPPED_NO_STRATEGY",
                reason="no parser strategy was supplied",
            )
            if selected.get("status") == "EXTRACTED" and selected.get("quality", {}).get("needs_fallback"):
                selected = {
                    **selected,
                    "status": "FAILED_QUALITY_GATE",
                    "reason": "all configured parsers produced structurally unusable output",
                    "output_path": None,
                    "requires_human_review": True,
                }
        elif selected.get("status") == "EXTRACTED":
            source_path = str(selected.get("source_path") or "")
            source = _safe_source_path(root_dir, source_path)
            canonical_output = _output_path_for(output_root, source_path)
            source_content_hash = str(selected.get("source_content_hash") or "")
            if source is None or canonical_output is None:
                selected = _skip_result(
                    job,
                    status="FAILED_INVALID_OUTPUT",
                    reason="selected parser output cannot be confined to its trust boundary",
                )
            elif source_content_hash and _hash_file(source) != source_content_hash:
                selected = _skip_result(
                    job,
                    status="FAILED_SOURCE_CHANGED",
                    reason="source changed before parser output was committed",
                )
            else:
                extracted_text = str(selected.pop("_extracted_text", ""))
                try:
                    _prepare_reference_directories(output_root, canonical_output)
                    _write_reference_artifact(
                        canonical_output,
                        extracted_text,
                        output_root=output_root,
                    )
                    manifest_path = _write_reference_manifest(
                        canonical_output,
                        output_root=output_root,
                        source_path=source_path,
                        source_content_hash=source_content_hash,
                        parser=str(selected.get("parser") or ""),
                        quality=dict(selected.get("quality") or {}),
                    )
                except (OSError, UnsafeOutputError) as error:
                    selected = _skip_result(
                        job,
                        status="FAILED_UNSAFE_OUTPUT",
                        reason=str(error),
                    )
                else:
                    selected["output_path"] = canonical_output.as_posix()
                    selected["reference_manifest_path"] = manifest_path.as_posix()
        selected.pop("_extracted_text", None)
        selected["attempts"] = attempts
        items.append(selected)

    payload = {
        "version": "hxy-parser-run.v1",
        "generated_at": _utc_now(),
        "root_dir": root_dir.resolve().as_posix(),
        "output_dir": output_dir.as_posix(),
        "job_count": len(parser_jobs),
        "processed_count": sum(1 for item in items if item["status"] == "EXTRACTED"),
        "failed_count": sum(1 for item in items if str(item["status"]).startswith("FAILED")),
        "skipped_count": sum(1 for item in items if str(item["status"]).startswith("SKIPPED")),
        "pending_count": sum(1 for item in items if item["status"] == "PENDING_ADAPTER"),
        "items": items,
        "official_use_allowed": False,
        "requires_human_review": any(bool(item.get("requires_human_review")) for item in items),
        "authority_rule": "parser_outputs_are_non_authoritative_and_review_is_exception_based",
    }
    _write_json(output_root / "parser-run-manifest.json", payload)
    return payload
