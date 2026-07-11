#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any


ROLES = {
    "founder",
    "brand_operations",
    "store_manager",
    "store_employee",
    "knowledge_data_admin",
}
AUTHORITIES = {"approved", "candidate", "reference", "insufficient"}
REQUIRED_CASE_FIELDS = {
    "case_id",
    "role",
    "assignment_scope",
    "task",
    "allowed_evidence_ids",
    "forbidden_evidence_ids",
    "expected_authority",
    "risk_expectations",
    "minimum_useful_outcome",
    "budget",
}
FORBIDDEN_TEXT = (
    "/root/hxy",
    "/root/htops",
    "password=",
    "api_key",
    "session_grant",
    "authorization: bearer",
)


def _nonempty(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _validate_budget(case_id: str, budget: Any, errors: list[str]) -> None:
    if not isinstance(budget, dict):
        errors.append(f"{case_id}: budget must be an object")
        return
    latency = budget.get("max_latency_ms")
    tokens = budget.get("max_tokens")
    cost = budget.get("max_cost_microunits")
    if not isinstance(latency, int) or isinstance(latency, bool) or not 1 <= latency <= 600_000:
        errors.append(f"{case_id}: max_latency_ms is invalid")
    if not isinstance(tokens, int) or isinstance(tokens, bool) or not 0 <= tokens <= 2_000_000:
        errors.append(f"{case_id}: max_tokens is invalid")
    if not isinstance(cost, int) or isinstance(cost, bool) or not 0 <= cost <= 1_000_000_000_000:
        errors.append(f"{case_id}: max_cost_microunits is invalid")


def validate_benchmark_file(path: Path, *, require_complete: bool) -> dict[str, Any]:
    errors: list[str] = []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "version": "hxy-engine-benchmark-validation.v1",
            "status": "failed",
            "case_count": 0,
            "role_counts": {},
            "errors": [f"unable to read benchmark: {type(exc).__name__}"],
        }

    if payload.get("version") != "hxy-engine-benchmark.v1":
        errors.append("version must be hxy-engine-benchmark.v1")
    if not _nonempty(payload.get("benchmark_id")):
        errors.append("benchmark_id is required")
    if not isinstance(payload.get("candidate_engine"), dict):
        errors.append("candidate_engine is required")
    hard_gates = payload.get("hard_gates")
    if not isinstance(hard_gates, dict) or any(value != 0 for value in hard_gates.values()):
        errors.append("all hard gate maxima must be zero")

    cases = payload.get("cases")
    if not isinstance(cases, list):
        cases = []
        errors.append("cases must be an array")
    seen_ids: set[str] = set()
    role_counts: Counter[str] = Counter()
    for index, case in enumerate(cases):
        if not isinstance(case, dict):
            errors.append(f"case[{index}] must be an object")
            continue
        case_id = str(case.get("case_id") or f"case[{index}]")
        missing = sorted(REQUIRED_CASE_FIELDS - set(case))
        if missing:
            errors.append(f"{case_id}: missing fields {', '.join(missing)}")
        if case_id in seen_ids:
            errors.append(f"{case_id}: duplicate case_id")
        seen_ids.add(case_id)
        role = case.get("role")
        if role not in ROLES:
            errors.append(f"{case_id}: role is invalid")
        else:
            role_counts[role] += 1
        scope = case.get("assignment_scope")
        if not isinstance(scope, dict) or not _nonempty(scope.get("assignment_id")) or not _nonempty(scope.get("organization_id")):
            errors.append(f"{case_id}: assignment scope is invalid")
        task = case.get("task")
        if not isinstance(task, dict) or not all(_nonempty(task.get(key)) for key in ("type", "purpose", "input")):
            errors.append(f"{case_id}: task is invalid")
        allowed = case.get("allowed_evidence_ids")
        forbidden = case.get("forbidden_evidence_ids")
        if not isinstance(allowed, list) or not isinstance(forbidden, list):
            errors.append(f"{case_id}: evidence ids must be arrays")
        elif set(allowed) & set(forbidden):
            errors.append(f"{case_id}: allowed and forbidden evidence sets overlap")
        if case.get("expected_authority") not in AUTHORITIES:
            errors.append(f"{case_id}: expected_authority is invalid")
        if not isinstance(case.get("risk_expectations"), list) or not case.get("risk_expectations"):
            errors.append(f"{case_id}: risk_expectations are required")
        if not isinstance(case.get("minimum_useful_outcome"), list) or not case.get("minimum_useful_outcome"):
            errors.append(f"{case_id}: minimum_useful_outcome is required")
        _validate_budget(case_id, case.get("budget"), errors)

    if require_complete:
        if len(cases) != 50:
            errors.append("complete benchmark requires exactly 50 cases")
        for role in sorted(ROLES):
            if role_counts[role] != 10:
                errors.append(f"complete benchmark requires 10 cases for role {role}")

    serialized = json.dumps(payload, ensure_ascii=False).lower()
    for marker in FORBIDDEN_TEXT:
        if marker in serialized:
            errors.append(f"benchmark contains forbidden private marker: {marker}")

    return {
        "version": "hxy-engine-benchmark-validation.v1",
        "status": "failed" if errors else "passed",
        "case_count": len(cases),
        "role_counts": dict(sorted(role_counts.items())),
        "errors": errors,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate an HXYOS engine benchmark")
    parser.add_argument("path", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    args = parser.parse_args()
    report = validate_benchmark_file(args.path, require_complete=args.require_complete)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0 if report["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
