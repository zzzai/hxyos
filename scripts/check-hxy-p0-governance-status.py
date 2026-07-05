#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from hxy_knowledge.loop_engine import build_p0_governance_status  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Check HXY P0 answer card governance status.")
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
        "--human",
        action="store_true",
        help="Print operator-readable status instead of JSON.",
    )
    return parser


def _human_status(status: dict) -> str:
    missing_files = status.get("missing_files") if isinstance(status.get("missing_files"), list) else []
    missing_text = ", ".join(str(item) for item in missing_files) if missing_files else "-"
    lines = [
        "HXY P0 Governance Status",
        f"Current step: {status.get('current_step') or ''}",
        f"Blocked: {'yes' if status.get('blocked') else 'no'}",
        f"Missing files: {missing_text}",
        f"Next action: {status.get('next_action') or ''}",
    ]
    next_command = str(status.get("next_command") or "")
    if next_command:
        lines.extend(["Next command:", next_command])
    details = status.get("details") if isinstance(status.get("details"), dict) else {}
    if details:
        if "decision_count" in details:
            lines.append(f"Decision count: {int(details.get('decision_count') or 0)}")
        if "pending_count" in details:
            lines.append(f"Pending count: {int(details.get('pending_count') or 0)}")
        if "actioned_count" in details:
            lines.append(f"Actioned count: {int(details.get('actioned_count') or 0)}")
        pending_case_ids = details.get("pending_case_ids")
        if isinstance(pending_case_ids, list) and pending_case_ids:
            lines.append(f"Pending case IDs: {', '.join(str(case_id) for case_id in pending_case_ids)}")
        if "decision_edit_guide_status" in details:
            lines.append(f"Decision edit guide status: {details.get('decision_edit_guide_status') or ''}")
        if "decision_edit_guide_path" in details:
            lines.append(f"Decision edit guide path: {details.get('decision_edit_guide_path') or ''}")
        if "decision_audit_status" in details:
            lines.append(f"Decision audit status: {details.get('decision_audit_status') or ''}")
        if "decision_audit_path" in details:
            lines.append(f"Decision audit path: {details.get('decision_audit_path') or ''}")
        if "decision_audit_changed_count" in details:
            lines.append(f"Decision audit changed count: {int(details.get('decision_audit_changed_count') or 0)}")
        if "decision_audit_metadata_gap_count" in details:
            lines.append(f"Decision audit metadata gap count: {int(details.get('decision_audit_metadata_gap_count') or 0)}")
        if "reviewer_worksheet_status" in details:
            lines.append(f"Reviewer worksheet status: {details.get('reviewer_worksheet_status') or ''}")
        if "reviewer_worksheet_path" in details:
            lines.append(f"Reviewer worksheet path: {details.get('reviewer_worksheet_path') or ''}")
        if "reviewer_todo_status" in details:
            lines.append(f"Reviewer todo status: {details.get('reviewer_todo_status') or ''}")
        if "reviewer_todo_path" in details:
            lines.append(f"Reviewer todo path: {details.get('reviewer_todo_path') or ''}")
        stale_file = str(details.get("stale_file") or "")
        if stale_file:
            lines.append(f"Stale file: {stale_file}")
        upstream_name = str(details.get("upstream_name") or "")
        if upstream_name:
            lines.append(f"Upstream changed: {upstream_name}")
    lines.append(f"write_to_database: {'true' if status.get('write_to_database') else 'false'}")
    return "\n".join(lines)


def main() -> int:
    args = _build_parser().parse_args()
    status = build_p0_governance_status(
        Path(args.run_dir),
        benchmark_path=Path(args.benchmark),
        report_path=Path(args.report),
    )
    if args.human:
        print(_human_status(status))
        return 0
    print(
        json.dumps(
            {
                "version": "hxy-p0-governance-status-cli.v1",
                "status": status,
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
