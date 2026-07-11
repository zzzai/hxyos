#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "apps" / "api"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from apps.api.hxy_engines.semantic_benchmark import (  # noqa: E402
    apply_human_calibration,
    evaluate_semantic_preflight,
    human_reviews_from_payload,
    semantic_answer_runs_from_payload,
    validate_semantic_catalogs,
)


VALIDATOR_PATH = ROOT / "scripts" / "validate-hxy-engine-benchmark.py"


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain an object")
    return payload


def _validate_complete_corpus(path: Path) -> list[str]:
    spec = importlib.util.spec_from_file_location(
        "hxy_engine_benchmark_validator",
        VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        return ["unable to load benchmark validator"]
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    report = module.validate_benchmark_file(path, require_complete=True)
    return list(report.get("errors") or [])


def _atomic_write(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HXYOS semantic benchmark")
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--rubric", required=True, type=Path)
    parser.add_argument("--calibration", required=True, type=Path)
    parser.add_argument("--answers", required=True, type=Path)
    parser.add_argument("--reviews", type=Path)
    parser.add_argument("--judge-results", type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()

    errors = _validate_complete_corpus(args.benchmark)
    if errors:
        print("; ".join(errors), file=sys.stderr)
        return 2
    try:
        benchmark = _load_json(args.benchmark)
        rubric = _load_json(args.rubric)
        calibration = _load_json(args.calibration)
        validate_semantic_catalogs(benchmark, rubric, calibration)
        answer_runs = semantic_answer_runs_from_payload(_load_json(args.answers))
        benchmark_case_ids = {
            str(case.get("case_id") or "") for case in benchmark.get("cases") or []
        }
        if not set(answer_runs) <= benchmark_case_ids:
            raise ValueError("answer run contains unknown case")
        reviews = (
            human_reviews_from_payload(_load_json(args.reviews))
            if args.reviews
            else []
        )
        calibration_ids = set(calibration.get("case_ids") or [])
        if any(review.case_id not in calibration_ids for review in reviews):
            raise ValueError("review contains unknown calibration case")
        judge_results = _load_json(args.judge_results) if args.judge_results else {}
        report = evaluate_semantic_preflight(
            benchmark,
            rubric,
            answer_runs,
        )
        report = apply_human_calibration(
            report,
            calibration,
            reviews,
            judge_results=judge_results.get("results", judge_results),
        )
        _atomic_write(args.output, report)
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"semantic benchmark input error: {exc}", file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "version": "hxy-semantic-benchmark-cli.v1",
                "report_name": args.output.name,
                "case_count": report["case_count"],
                "structural_pass_count": report["structural_pass_count"],
                "semantic_status": report["semantic_status"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
