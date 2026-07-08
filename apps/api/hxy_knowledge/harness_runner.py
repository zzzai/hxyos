from __future__ import annotations

import json
import subprocess
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _default_command_runner(command: str, cwd: Path) -> dict[str, Any]:
    completed = subprocess.run(command.split(), cwd=cwd, text=True, capture_output=True, check=False)
    return {
        "command": command,
        "returncode": completed.returncode,
        "stdout": completed.stdout[-4000:],
        "stderr": completed.stderr[-4000:],
    }


def run_harness_round(
    spec: dict[str, Any],
    *,
    root_dir: str | Path,
    run_id: str,
    round_number: int,
    command_runner: Any | None = None,
) -> dict[str, Any]:
    root = Path(root_dir)
    validation = validate_harness_spec(spec, root_dir=root)
    if not validation["valid"]:
        report = {
            "version": "hxy-harness-round-report.v1",
            "round": round_number,
            "status": "blocked",
            "validation": validation,
            "command_results": [],
            "write_to_database": False,
            "official_use_allowed": False,
        }
        _write_json(root / "knowledge" / "runs" / run_id / f"round-{round_number}.json", report)
        return report

    runner = command_runner or _default_command_runner
    command_results = [runner(str(command), root) for command in spec.get("verification_commands") or []]
    passed = all(int(result.get("returncode") or 0) == 0 for result in command_results)
    report = {
        "version": "hxy-harness-round-report.v1",
        "round": round_number,
        "status": "passed" if passed else "failed",
        "command_results": command_results,
        "write_to_database": False,
        "official_use_allowed": False,
        "requires_human_review": True,
        "authority_rule": "harness_round_reports_evidence_only",
    }
    _write_json(root / "knowledge" / "runs" / run_id / f"round-{round_number}.json", report)
    return report


def build_harness_state(
    *,
    spec: dict[str, Any],
    run_id: str,
    round_reports: list[dict[str, Any]],
    champion_commit: str,
) -> dict[str, Any]:
    max_rounds = int(spec.get("max_rounds") or 1)
    status = "running"
    stop_reason = ""
    if round_reports and round_reports[-1].get("status") == "passed":
        status = "succeeded"
        stop_reason = "verification_passed"
    if len(round_reports) >= max_rounds and status != "succeeded":
        status = "blocked"
        stop_reason = "max_rounds_reached"

    signatures = [str(report.get("failure_signature") or "") for report in round_reports[-3:]]
    if len(signatures) == 3 and signatures[0] and len(set(signatures)) == 1 and status != "succeeded":
        status = "blocked"
        stop_reason = "repeated_failure_requires_root_cause_analysis"

    return {
        "version": "hxy-harness-state.v1",
        "run_id": run_id,
        "run_name": spec.get("run_name") or "",
        "status": status,
        "current_round": len(round_reports),
        "max_rounds": max_rounds,
        "champion_commit": champion_commit,
        "rounds": round_reports,
        "stop_reason": stop_reason,
        "write_to_database": False,
        "official_use_allowed": False,
        "requires_human_review": True,
    }
