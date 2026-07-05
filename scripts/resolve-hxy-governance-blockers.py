#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from hxy_knowledge.enterprise_governance import build_governance_review_task_drafts  # noqa: E402
from hxy_knowledge.repository import KnowledgeRepository  # noqa: E402


POLLUTED_ANSWER_CARD_CODES = {
    "reference_used_as_approved_source",
    "process_memory_used_as_approved_source",
}


def _load_package(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("governance package must be a JSON object")
    return payload


def _blocking_issues(package: dict[str, Any]) -> list[dict[str, Any]]:
    report = package.get("governance_report") if isinstance(package.get("governance_report"), dict) else {}
    issues = report.get("lint_issues") if isinstance(report.get("lint_issues"), list) else []
    return [issue for issue in issues if isinstance(issue, dict) and issue.get("blocks_release")]


def _polluted_answer_card_ids(package: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for issue in _blocking_issues(package):
        if issue.get("code") not in POLLUTED_ANSWER_CARD_CODES:
            continue
        if issue.get("target_type") != "answer_card":
            continue
        target_id = str(issue.get("target_id") or "").strip()
        if target_id and target_id not in ids:
            ids.append(target_id)
    return ids


def _review_task_drafts(package: dict[str, Any]) -> list[dict[str, Any]]:
    report = package.get("governance_report") if isinstance(package.get("governance_report"), dict) else {}
    if isinstance(package.get("review_task_drafts"), list):
        return [item for item in package["review_task_drafts"] if isinstance(item, dict)]
    if isinstance(report, dict):
        return build_governance_review_task_drafts(report, run_id=str(package.get("run_id") or ""))
    return []


def _create_review_tasks(repo: KnowledgeRepository, drafts: list[dict[str, Any]], limit: int) -> list[str]:
    created: list[str] = []
    for draft in drafts[:limit]:
        created.append(
            repo.create_review_task(
                {
                    "question": draft.get("question") or "",
                    "intent": draft.get("intent") or "knowledge_governance",
                    "reason": draft.get("reason") or "knowledge_governance",
                    "priority": draft.get("priority") or "medium",
                    "correction_package": draft.get("correction_package") or {},
                    "payload": draft.get("payload_json") or draft,
                }
            )
        )
    return created


def main() -> int:
    parser = argparse.ArgumentParser(description="Resolve HXY governance release blockers with auditable actions.")
    parser.add_argument("--package", required=True, help="Path to HXY governance run-package.json")
    parser.add_argument("--dry-run", action="store_true", help="Only report planned actions")
    parser.add_argument("--target-status", default="draft", choices=["draft", "archived"])
    parser.add_argument("--create-review-tasks", action="store_true")
    parser.add_argument("--review-task-limit", type=int, default=20)
    args = parser.parse_args()

    package = _load_package(Path(args.package))
    polluted_card_ids = _polluted_answer_card_ids(package)
    updated_card_ids: list[str] = []
    created_task_ids: list[str] = []
    if not args.dry_run and (polluted_card_ids or args.create_review_tasks):
        database_url = os.environ.get("HXY_DATABASE_URL", "")
        if not database_url:
            raise SystemExit("HXY_DATABASE_URL is required")
        repo = KnowledgeRepository(database_url)
        updated_card_ids = repo.downgrade_answer_cards(polluted_card_ids, status=args.target_status)
        if args.create_review_tasks:
            created_task_ids = _create_review_tasks(repo, _review_task_drafts(package), args.review_task_limit)

    result = {
        "version": "hxy-governance-blocker-resolution.v1",
        "dry_run": bool(args.dry_run),
        "target_status": args.target_status,
        "polluted_answer_card_count": len(polluted_card_ids),
        "polluted_answer_card_ids": polluted_card_ids,
        "updated_answer_card_count": len(updated_card_ids),
        "updated_answer_card_ids": updated_card_ids,
        "created_review_task_count": len(created_task_ids),
        "created_review_task_ids": created_task_ids,
        "policy": "已批准答案卡引用 reference/process_memory 时先降级，复核通过后才能重新 approved。",
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
