from __future__ import annotations

from dataclasses import dataclass


def _text(name: str, value: str) -> str:
    normalized = value.strip()
    if not normalized or len(normalized) > 240:
        raise ValueError(f"{name} is invalid")
    return normalized


@dataclass(frozen=True)
class EngineDescriptor:
    name: str
    version: str
    capabilities: tuple[str, ...]
    license_id: str
    deployment: str
    data_export: str
    healthcheck: str
    rollback: str

    def __post_init__(self) -> None:
        for name in (
            "name",
            "version",
            "license_id",
            "deployment",
            "data_export",
            "healthcheck",
            "rollback",
        ):
            object.__setattr__(self, name, _text(name, getattr(self, name)))
        normalized = tuple(
            sorted({_text("capability", item) for item in self.capabilities})
        )
        if not normalized:
            raise ValueError("capabilities are required")
        object.__setattr__(self, "capabilities", normalized)

    def as_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "version": self.version,
            "capabilities": list(self.capabilities),
            "license_id": self.license_id,
            "deployment": self.deployment,
            "data_export": self.data_export,
            "healthcheck": self.healthcheck,
            "rollback": self.rollback,
        }
