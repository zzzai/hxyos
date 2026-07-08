from __future__ import annotations

from pathlib import Path
from typing import Any


ALLOWED_COMMAND_PREFIXES = (
    "npm test",
    ".venv/bin/pytest",
    ".venv/bin/python scripts/run-hxy-brain-benchmark.py",
    "python3 scripts/check-hxy-secrets.py",
    "python3 scripts/check-hxy-public-release.py",
)

FORBIDDEN_SCOPE_PREFIXES = ("/root/htops", "root/htops")


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


def _is_allowed_command(command: str) -> bool:
    clean = " ".join(str(command or "").strip().split())
    return any(clean == prefix or clean.startswith(f"{prefix} ") for prefix in ALLOWED_COMMAND_PREFIXES)


def validate_harness_spec(spec: dict[str, Any], *, root_dir: str | Path) -> dict[str, Any]:
    errors: list[dict[str, Any]] = []
    if spec.get("version") != "hxy-harness-spec.v1":
        errors.append(_error("invalid_version", "Harness spec version must be hxy-harness-spec.v1."))
    if not str(spec.get("run_name") or "").strip():
        errors.append(_error("missing_run_name", "run_name is required."))
    if not str(spec.get("target") or "").strip():
        errors.append(_error("missing_target", "target is required."))
    max_rounds = int(spec.get("max_rounds") or 0)
    if max_rounds < 1 or max_rounds > 10:
        errors.append(_error("invalid_max_rounds", "max_rounds must be between 1 and 10."))
    for path in spec.get("scope") or []:
        clean = str(path or "").strip()
        if clean.startswith(FORBIDDEN_SCOPE_PREFIXES):
            errors.append(_error("forbidden_scope_path", "Scope cannot include htops paths.", path=clean))
    commands = spec.get("verification_commands") if isinstance(spec.get("verification_commands"), list) else []
    if not commands:
        errors.append(_error("missing_verification_commands", "At least one verification command is required."))
    for command in commands:
        if not _is_allowed_command(str(command or "")):
            errors.append(
                _error(
                    "command_not_allowlisted",
                    "Command is not allowed for Harness V1.",
                    command=str(command or ""),
                )
            )
    return {
        "version": "hxy-harness-spec-validation.v1",
        "valid": not errors,
        "error_count": len(errors),
        "errors": errors,
        "write_to_database": False,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "harness_spec_validation_does_not_execute_or_publish",
    }
