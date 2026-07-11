from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


_AUTHORITY_POLICIES = {
    "approved_only",
    "approved_plus_reference",
    "reference_only",
    "process_context",
}
_ENGINE_ARTIFACT_AUTHORITIES = {
    "candidate",
    "reference",
    "private_reference",
    "process",
}
_ENGINE_STATUSES = {"succeeded", "failed", "skipped", "blocked"}
_POLICY_OUTCOMES = {"allow", "block", "review"}


def _required_text(name: str, value: str, *, maximum: int = 160) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > maximum:
        raise ValueError(f"{name} is invalid")
    return normalized


@dataclass(frozen=True)
class EngineBudget:
    max_latency_ms: int
    max_tokens: int = 0
    max_cost_microunits: int = 0

    def __post_init__(self) -> None:
        if not 1 <= self.max_latency_ms <= 600_000:
            raise ValueError("max_latency_ms is invalid")
        if not 0 <= self.max_tokens <= 2_000_000:
            raise ValueError("max_tokens is invalid")
        if not 0 <= self.max_cost_microunits <= 1_000_000_000_000:
            raise ValueError("max_cost_microunits is invalid")


@dataclass(frozen=True)
class EngineContext:
    request_id: str
    trace_id: str
    account_id: str
    assignment_id: str
    organization_id: str
    store_id: str | None
    purpose: str
    authority_policy: str
    budget: EngineBudget
    permissions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for name in (
            "request_id",
            "trace_id",
            "account_id",
            "assignment_id",
            "organization_id",
            "purpose",
        ):
            object.__setattr__(self, name, _required_text(name, getattr(self, name)))
        if self.store_id is not None:
            object.__setattr__(
                self,
                "store_id",
                _required_text("store_id", self.store_id),
            )
        if self.authority_policy not in _AUTHORITY_POLICIES:
            raise ValueError("authority_policy is invalid")
        object.__setattr__(
            self,
            "permissions",
            tuple(
                sorted(
                    {
                        _required_text("permission", item)
                        for item in self.permissions
                    }
                )
            ),
        )


@dataclass(frozen=True)
class EngineArtifact:
    artifact_id: str
    kind: str
    authority: str
    provenance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "artifact_id",
            _required_text("artifact_id", self.artifact_id),
        )
        object.__setattr__(self, "kind", _required_text("kind", self.kind))
        if self.authority not in _ENGINE_ARTIFACT_AUTHORITIES:
            raise ValueError("authority is invalid for an engine artifact")
        normalized_ids = tuple(
            _required_text("provenance_id", item) for item in self.provenance_ids
        )
        object.__setattr__(self, "provenance_ids", normalized_ids)


@dataclass(frozen=True)
class EngineUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cost_microunits: int = 0

    def __post_init__(self) -> None:
        for name in ("input_tokens", "output_tokens", "cost_microunits"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} is invalid")

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    def as_dict(self) -> dict[str, int]:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "total_tokens": self.total_tokens,
            "cost_microunits": self.cost_microunits,
        }


@dataclass(frozen=True)
class EnginePolicyDecision:
    policy: str
    outcome: str
    reason_code: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "policy", _required_text("policy", self.policy))
        object.__setattr__(
            self,
            "reason_code",
            _required_text("reason_code", self.reason_code),
        )
        if self.outcome not in _POLICY_OUTCOMES:
            raise ValueError("outcome is invalid")

    def as_dict(self) -> dict[str, str]:
        return {
            "policy": self.policy,
            "outcome": self.outcome,
            "reason_code": self.reason_code,
        }


@dataclass(frozen=True)
class EngineResult:
    engine_name: str
    engine_version: str
    status: str
    artifacts: tuple[EngineArtifact, ...] = ()
    latency_ms: int = 0
    usage: EngineUsage = field(default_factory=EngineUsage)
    policy_decisions: tuple[EnginePolicyDecision, ...] = ()
    private_output: Any | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "engine_name",
            _required_text("engine_name", self.engine_name),
        )
        object.__setattr__(
            self,
            "engine_version",
            _required_text("engine_version", self.engine_version),
        )
        if self.status not in _ENGINE_STATUSES:
            raise ValueError("status is invalid")
        if self.latency_ms < 0:
            raise ValueError("latency_ms is invalid")

    def as_trace_record(self) -> dict[str, Any]:
        return {
            "engine_name": self.engine_name,
            "engine_version": self.engine_version,
            "status": self.status,
            "artifact_count": len(self.artifacts),
            "artifact_authorities": [item.authority for item in self.artifacts],
            "latency_ms": self.latency_ms,
            "usage": self.usage.as_dict(),
            "policy_decisions": [item.as_dict() for item in self.policy_decisions],
        }
