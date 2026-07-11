from __future__ import annotations

from time import perf_counter
from typing import Any

from ..contracts import (
    EngineArtifact,
    EngineContext,
    EnginePolicyDecision,
    EngineResult,
    EngineUsage,
)
from ..model_gateway import ModelRequest


def _usage(raw: dict[str, Any]) -> EngineUsage:
    usage = raw.get("usage") or {}
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
    return EngineUsage(
        input_tokens=max(0, int(input_tokens or 0)),
        output_tokens=max(0, int(output_tokens or 0)),
    )


class CurrentModelGateway:
    engine_name = "current-model-router"
    engine_version = "v1"

    def __init__(self, router: Any) -> None:
        self.router = router

    def execute(self, context: EngineContext, request: ModelRequest) -> EngineResult:
        if request.task_type == "authority_answer":
            return EngineResult(
                engine_name=self.engine_name,
                engine_version=self.engine_version,
                status="skipped",
                policy_decisions=(
                    EnginePolicyDecision(
                        policy="knowledge_authority",
                        outcome="allow",
                        reason_code="authority_answer_bypasses_model",
                    ),
                ),
            )

        started = perf_counter()
        raw = self.router.generate(
            request.task_type,
            messages=list(request.messages) or None,
            prompt=request.prompt,
            metadata={key: True for key in request.metadata_keys},
        )
        latency_ms = max(0, round((perf_counter() - started) * 1000))
        used_model = bool(raw.get("used_model"))
        output = raw.get("output")
        artifacts: tuple[EngineArtifact, ...] = ()
        if used_model and isinstance(output, str) and output.strip():
            artifact_id = str(
                raw.get("provider_response_id")
                or f"{context.request_id}:model-output"
            )
            artifacts = (
                EngineArtifact(
                    artifact_id=artifact_id,
                    kind="model_output",
                    authority="candidate",
                ),
            )
        reason = str(raw.get("reason") or "unknown")
        reason_code = "model_disabled" if reason == "disabled" else f"model_{reason}"
        return EngineResult(
            engine_name=self.engine_name,
            engine_version=self.engine_version,
            status="succeeded" if artifacts else "skipped",
            artifacts=artifacts,
            latency_ms=latency_ms,
            usage=_usage(raw),
            policy_decisions=(
                EnginePolicyDecision(
                    policy="knowledge_authority",
                    outcome="review" if artifacts else "allow",
                    reason_code="model_output_is_candidate" if artifacts else reason_code,
                ),
            ),
            private_output=output,
        )
