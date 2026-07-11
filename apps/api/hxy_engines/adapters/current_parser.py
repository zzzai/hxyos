from __future__ import annotations

from pathlib import Path
from time import perf_counter
from typing import Any, Callable

from hxy_knowledge.parser_adapter import run_parser_jobs

from ..contracts import (
    EngineArtifact,
    EngineContext,
    EnginePolicyDecision,
    EngineResult,
)
from ..document_parser import DocumentParseRequest


ParserRunner = Callable[..., dict[str, Any]]


class CurrentDocumentParser:
    engine_name = "current-document-parser"
    engine_version = "v1"

    def __init__(
        self,
        *,
        root_dir: Path,
        output_dir: Path,
        runner: ParserRunner = run_parser_jobs,
    ) -> None:
        self.root_dir = root_dir.resolve()
        self.output_dir = output_dir
        self.runner = runner

    def execute(
        self,
        context: EngineContext,
        request: DocumentParseRequest,
    ) -> EngineResult:
        job_id = f"parse-{request.source_id}"
        started = perf_counter()
        raw = self.runner(
            [
                {
                    "job_id": job_id,
                    "source_path": request.storage_ref,
                    "parser_strategy": request.parser_strategy,
                    "media_type": request.media_type,
                }
            ],
            root_dir=self.root_dir,
            output_dir=self.output_dir,
            strategies={request.parser_strategy},
            timeout_seconds=max(1, context.budget.max_latency_ms // 1000),
        )
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        processed_count = int(raw.get("processed_count") or 0)
        failed_count = int(raw.get("failed_count") or 0)
        skipped_count = int(raw.get("skipped_count") or 0)
        artifacts: tuple[EngineArtifact, ...] = ()
        if processed_count > 0:
            artifacts = (
                EngineArtifact(
                    artifact_id=job_id,
                    kind="parsed_document",
                    authority="reference",
                    provenance_ids=(request.source_id,),
                ),
            )
        status = (
            "succeeded"
            if processed_count > 0
            else "failed"
            if failed_count > 0
            else "skipped"
        )
        return EngineResult(
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            status=status,
            artifacts=artifacts,
            latency_ms=latency_ms,
            policy_decisions=(
                EnginePolicyDecision(
                    policy="knowledge_authority",
                    outcome="review" if artifacts else "allow",
                    reason_code=(
                        "parser_output_is_reference"
                        if artifacts
                        else "parser_failed"
                        if failed_count > 0
                        else "parser_skipped"
                    ),
                ),
            ),
            private_output=raw,
        )
