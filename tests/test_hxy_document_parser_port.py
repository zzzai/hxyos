from __future__ import annotations

from pathlib import Path

from apps.api.hxy_engines.adapters.current_parser import CurrentDocumentParser
from apps.api.hxy_engines.contracts import EngineBudget, EngineContext
from apps.api.hxy_engines.document_parser import DocumentParseRequest


def _context() -> EngineContext:
    return EngineContext(
        request_id="request-parser-001",
        trace_id="trace-parser-001",
        account_id="account-001",
        assignment_id="assignment-001",
        organization_id="organization-001",
        store_id="store-001",
        purpose="material_understanding",
        authority_policy="reference_only",
        budget=EngineBudget(max_latency_ms=120_000),
    )


def test_current_parser_keeps_paths_private_and_artifacts_reference_only(tmp_path) -> None:
    calls = []

    def runner(jobs, *, root_dir, output_dir, strategies, timeout_seconds):
        calls.append(
            {
                "jobs": jobs,
                "root_dir": root_dir,
                "output_dir": output_dir,
                "strategies": strategies,
                "timeout_seconds": timeout_seconds,
            }
        )
        return {
            "version": "hxy-parser-run.v1",
            "processed_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "items": [
                {
                    "job_id": "parse-source-001",
                    "status": "EXTRACTED",
                    "parser": "markitdown",
                    "output_path": "/root/hxy/private/reference.txt",
                    "char_count": 123,
                    "official_use_allowed": False,
                }
            ],
        }

    parser = CurrentDocumentParser(
        root_dir=tmp_path,
        output_dir=tmp_path / "artifacts",
        runner=runner,
    )
    result = parser.execute(
        _context(),
        DocumentParseRequest(
            source_id="source-001",
            storage_ref="knowledge/raw/inbox/example.pdf",
            media_type="application/pdf",
            parser_strategy="markitdown",
        ),
    )

    assert result.status == "succeeded"
    assert result.artifacts[0].authority == "reference"
    assert result.artifacts[0].provenance_ids == ("source-001",)
    assert result.private_output["items"][0]["output_path"].startswith("/root/hxy")
    assert "/root/hxy" not in str(result.as_trace_record())
    assert calls[0]["jobs"][0]["source_path"] == "knowledge/raw/inbox/example.pdf"
    assert calls[0]["strategies"] == {"markitdown"}


def test_parser_maps_failed_and_skipped_legacy_runs(tmp_path) -> None:
    def failed_runner(*_args, **_kwargs):
        return {
            "version": "hxy-parser-run.v1",
            "processed_count": 0,
            "failed_count": 1,
            "skipped_count": 0,
            "items": [{"status": "FAILED_PARSER_ERROR"}],
        }

    failed = CurrentDocumentParser(
        root_dir=tmp_path,
        output_dir=tmp_path / "out",
        runner=failed_runner,
    ).execute(
        _context(),
        DocumentParseRequest(
            source_id="source-001",
            storage_ref="knowledge/raw/inbox/example.pdf",
            media_type="application/pdf",
            parser_strategy="markitdown",
        ),
    )
    assert failed.status == "failed"
    assert failed.artifacts == ()

    def skipped_runner(*_args, **_kwargs):
        return {
            "version": "hxy-parser-run.v1",
            "processed_count": 0,
            "failed_count": 0,
            "skipped_count": 1,
            "items": [{"status": "SKIPPED_DEPENDENCY_MISSING"}],
        }

    skipped = CurrentDocumentParser(
        root_dir=tmp_path,
        output_dir=tmp_path / "out",
        runner=skipped_runner,
    ).execute(
        _context(),
        DocumentParseRequest(
            source_id="source-001",
            storage_ref="knowledge/raw/inbox/example.pdf",
            media_type="application/pdf",
            parser_strategy="markitdown",
        ),
    )
    assert skipped.status == "skipped"


def test_parse_request_rejects_absolute_or_parent_storage_refs() -> None:
    for storage_ref in ("/root/hxy/private.pdf", "../private.pdf", "a/../../b.pdf"):
        try:
            DocumentParseRequest(
                source_id="source-001",
                storage_ref=storage_ref,
                media_type="application/pdf",
                parser_strategy="markitdown",
            )
        except ValueError as exc:
            assert "storage_ref" in str(exc)
        else:
            raise AssertionError(f"unsafe storage ref accepted: {storage_ref}")
