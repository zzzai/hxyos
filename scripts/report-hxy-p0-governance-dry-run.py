#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from hxy_knowledge.loop_engine import build_p0_governance_status, validate_p0_review_decisions  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Render a read-only HXY P0 governance dry-run report.")
    parser.add_argument(
        "--run-dir",
        default=str(ROOT / "knowledge" / "runs" / "benchmark-loop-latest"),
        help="Path to a benchmark loop run directory.",
    )
    parser.add_argument("--run-id", default="", help="Run id used in product-facing API links.")
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
    parser.add_argument("--output", default="", help="Optional path to write the dry-run report JSON.")
    return parser


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def _reviewer_todo_payload(payload: dict[str, Any] | None, *, run_id: str) -> dict[str, Any]:
    if not payload:
        return {
            "version": "hxy-p0-reviewer-todo.v1",
            "status": "missing",
            "run_id": run_id,
            "item_count": 0,
            "pending_count": 0,
            "actioned_count": 0,
            "items": [],
            "official_use_allowed": False,
            "publish_allowed": False,
            "write_to_database": False,
            "requires_human_review": True,
            "authority_rule": "p0_reviewer_todo_does_not_publish_approved_cards",
        }
    items: list[dict[str, Any]] = []
    for item in payload.get("items") or []:
        if not isinstance(item, dict):
            continue
        public = dict(item)
        public["official_use_allowed"] = False
        public["publish_allowed"] = False
        public["write_to_database"] = False
        public.setdefault("next_human_action", "choose approve, reject, or needs_revision manually")
        items.append(public)
    return {
        **payload,
        "version": payload.get("version") or "hxy-p0-reviewer-todo.v1",
        "status": "ready",
        "run_id": run_id,
        "item_count": int(payload.get("item_count") or len(items)),
        "pending_count": int(payload.get("pending_count") or 0),
        "actioned_count": int(payload.get("actioned_count") or 0),
        "items": items,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "p0_reviewer_todo_does_not_publish_approved_cards",
    }


def _notification_payload(status: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    details = status.get("details") if isinstance(status.get("details"), dict) else {}
    pending_count = int(details.get("pending_count") or 0)
    actioned_count = int(details.get("actioned_count") or 0)
    status_api = f"/api/v1/hxy/p0/governance-status?run_id={run_id}"
    reviewer_todo_api = f"/api/v1/hxy/p0/reviewer-todo?run_id={run_id}"
    text = "\n".join(
        [
            "HXY P0 Governance Status",
            f"Run: {run_id}",
            f"Current step: {status.get('current_step') or 'unknown'}",
            f"Blocked: {'yes' if status.get('blocked') else 'no'}",
            f"Pending: {pending_count}",
            f"Actioned: {actioned_count}",
            "write_to_database: false",
            "publish_allowed: false",
            f"Next action: {status.get('next_action') or ''}",
            f"Status API: {status_api}",
            f"Reviewer todo API: {reviewer_todo_api}",
        ]
    )
    return {
        "version": "hxy-p0-governance-notification.v1",
        "channel": "hermes_feishu",
        "run_id": run_id,
        "text": text,
        "links": {
            "status_api": status_api,
            "reviewer_todo_api": reviewer_todo_api,
        },
        "current_step": status.get("current_step") or "unknown",
        "blocked": bool(status.get("blocked")),
        "pending_count": pending_count,
        "actioned_count": actioned_count,
        "send_allowed": False,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "notification_payload_is_read_only_and_does_not_send_messages",
    }


def _safe_next_dry_run(status: dict[str, Any]) -> dict[str, Any]:
    next_command = str(status.get("next_command") or "")
    human_gate = status.get("current_step") == "blocked_at_empty_manual_decisions" and not next_command
    stopped_reason = "human_decision_required" if human_gate else "manual_safe_next_required"
    return {
        "version": "hxy-p0-governance-safe-next-dry-run.v1",
        "stopped_reason": stopped_reason,
        "would_execute_count": 0,
        "would_execute_steps": [],
        "final_status": status,
        "write_to_database": False,
        "authority_rule": "dry_run_report_does_not_execute_safe_next",
    }


def _decision_preview_template(stub: dict[str, Any] | None) -> dict[str, Any]:
    decisions = {
        "version": "hxy-p0-review-decisions.v1",
        "items": [],
        "write_to_database": False,
        "publish_allowed": False,
    }
    validation = validate_p0_review_decisions(stub or {}, decisions)
    return {
        "version": "hxy-p0-decision-preview.v1",
        "preview_only": True,
        "valid": bool(validation.get("valid")),
        "validation": validation,
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "decision_preview_template_does_not_write_manual_decisions",
    }


def main() -> int:
    args = _build_parser().parse_args()
    run_dir = Path(args.run_dir)
    run_id = args.run_id or run_dir.name
    benchmark_path = Path(args.benchmark)
    report_path = Path(args.report)

    status = build_p0_governance_status(
        run_dir,
        benchmark_path=benchmark_path,
        report_path=report_path,
    )
    governance_status = {
        **status,
        "run_id": run_id,
        "p0_reviewer_todo_url": f"/api/v1/hxy/p0/reviewer-todo?run_id={run_id}",
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
    }
    reviewer_todo = _reviewer_todo_payload(_read_json(run_dir / "p0-reviewer-todo.json"), run_id=run_id)
    notification = _notification_payload(status, run_id=run_id)
    decision_preview = _decision_preview_template(_read_json(run_dir / "p0-review-decisions.stub.json"))

    payload = {
        "version": "hxy-p0-governance-dry-run-report.v1",
        "run_id": run_id,
        "run_dir": str(run_dir),
        "safe_next": _safe_next_dry_run(status),
        "api_payloads": {
            "governance_status": governance_status,
            "reviewer_todo": reviewer_todo,
            "notification": notification,
            "decision_preview_template": decision_preview,
        },
        "official_use_allowed": False,
        "publish_allowed": False,
        "write_to_database": False,
        "requires_human_review": True,
        "authority_rule": "p0_governance_dry_run_report_is_read_only",
    }

    if args.output:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
