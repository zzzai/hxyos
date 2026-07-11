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
    canonical_payload_sha256,
    evaluate_deterministic_semantics,
    human_reviews_from_payload,
    semantic_answer_runs_from_payload,
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
        benchmark_sha256 = canonical_payload_sha256(benchmark)
        if (
            rubric.get("benchmark_sha256") != benchmark_sha256
            or calibration.get("benchmark_sha256") != benchmark_sha256
        ):
            raise ValueError("catalog benchmark digest mismatch")
        answer_runs = semantic_answer_runs_from_payload(_load_json(args.answers))
        reviews = (
            human_reviews_from_payload(_load_json(args.reviews))
            if args.reviews
            else []
        )
        judge_results = _load_json(args.judge_results) if args.judge_results else {}
        report = evaluate_deterministic_semantics(
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
                "deterministic_pass_count": report["deterministic_pass_count"],
                "semantic_status": report["semantic_status"],
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
