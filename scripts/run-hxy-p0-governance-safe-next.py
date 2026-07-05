#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from hxy_knowledge.loop_engine import build_p0_governance_status  # noqa: E402


SAFE_VALIDATE_COMMANDS = {
    "sample",
    "review-packet",
    "init-decisions",
    "edit-guide",
    "decision-audit",
    "reviewer-worksheet",
    "reviewer-todo",
    "validate",
    "decision-report",
}


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the next safe HXY P0 governance artifact step.")
    parser.add_argument(
        "--run-dir",
        default=str(ROOT / "knowledge" / "runs" / "benchmark-loop-latest"),
        help="Path to a benchmark loop run directory.",
    )
    parser.add_argument(
        "--benchmark",
        default=str(ROOT / "knowledge" / "benchmarks" / "hxy-brain-benchmark-v1.json"),
        help="Path to HXY brain benchmark JSON.",
    )
    parser.add_argument(
        "--report",
        default=str(ROOT / "knowledge" / "reports" / "benchmark-latest.json"),
        help="Path to benchmark report JSON.",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=8,
        help="Maximum safe commands to execute before stopping.",
    )
    return parser


def _status(run_dir: Path, benchmark_path: Path, report_path: Path) -> dict[str, Any]:
    return build_p0_governance_status(
        run_dir,
        benchmark_path=benchmark_path,
        report_path=report_path,
    )


def _safe_command_args(command: str) -> list[str] | None:
    if not command:
        return None
    try:
        args = shlex.split(command)
    except ValueError:
        return None
    if len(args) < 3:
        return None
    script_name = Path(args[1]).name
    if script_name != "validate-hxy-p0-review-decisions.py":
        return None
    subcommand = args[2]
    if subcommand not in SAFE_VALIDATE_COMMANDS:
        return None
    return args


def _stop_reason(status: dict[str, Any], safe_args: list[str] | None) -> str:
    if status.get("current_step") == "blocked_at_empty_manual_decisions" and not status.get("next_command"):
        return "human_decision_required"
    if not safe_args:
        return "unsafe_or_unsupported_command"
    return "max_steps_reached"


def main() -> int:
    args = _build_parser().parse_args()
    run_dir = Path(args.run_dir)
    benchmark_path = Path(args.benchmark)
    report_path = Path(args.report)
    max_steps = max(0, int(args.max_steps))

    executed_steps: list[dict[str, Any]] = []
    current_status = _status(run_dir, benchmark_path, report_path)

    for _ in range(max_steps):
        command = str(current_status.get("next_command") or "")
        safe_args = _safe_command_args(command)
        if not safe_args:
            break
        before_step = str(current_status.get("current_step") or "")
        result = subprocess.run(
            safe_args,
            cwd=ROOT,
            check=False,
            text=True,
            capture_output=True,
        )
        executed_steps.append(
            {
                "from_step": before_step,
                "command": command,
                "returncode": result.returncode,
                "stdout": result.stdout.strip(),
                "stderr": result.stderr.strip(),
            }
        )
        if result.returncode != 0:
            current_status = _status(run_dir, benchmark_path, report_path)
            payload = {
                "version": "hxy-p0-governance-safe-next.v1",
                "valid": False,
                "run_dir": str(run_dir),
                "executed_count": len(executed_steps),
                "executed_steps": executed_steps,
                "stopped_reason": "safe_command_failed",
                "final_status": current_status,
                "write_to_database": False,
            }
            print(json.dumps(payload, ensure_ascii=False))
            return 1
        current_status = _status(run_dir, benchmark_path, report_path)

    final_command = str(current_status.get("next_command") or "")
    final_safe_args = _safe_command_args(final_command)
    stopped_reason = _stop_reason(current_status, final_safe_args)
    valid = stopped_reason in {"human_decision_required", "max_steps_reached"}
    payload = {
        "version": "hxy-p0-governance-safe-next.v1",
        "valid": valid,
        "run_dir": str(run_dir),
        "executed_count": len(executed_steps),
        "executed_steps": executed_steps,
        "stopped_reason": stopped_reason,
        "final_status": current_status,
        "write_to_database": False,
    }
    print(json.dumps(payload, ensure_ascii=False))
    return 0 if valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
