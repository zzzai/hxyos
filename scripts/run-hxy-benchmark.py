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

from hxy_knowledge.brain_benchmark import (  # noqa: E402
    build_core_10_contract_runs,
    build_core_10_report,
    load_benchmark,
)


SUITES = {
    "hxyos-core-10": ROOT / "knowledge" / "benchmarks" / "hxyos-core-10.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a deterministic HXYOS benchmark contract.")
    parser.add_argument("--suite", choices=sorted(SUITES), required=True)
    parser.add_argument("--runs", help="Captured product-answer runs in hxyos-core-10-runs.v1 format.")
    parser.add_argument("--output", help="Optional report JSON path.")
    args = parser.parse_args()

    benchmark = load_benchmark(SUITES[args.suite])
    if args.runs:
        captured = json.loads(Path(args.runs).read_text(encoding="utf-8"))
        if captured.get("version") != "hxyos-core-10-runs.v1" or not isinstance(captured.get("runs"), dict):
            parser.error("--runs must contain hxyos-core-10-runs.v1 with a runs object")
        runs = captured["runs"]
        benchmark_kind = "captured_product_answers"
    else:
        runs = build_core_10_contract_runs()
        benchmark_kind = "deterministic_contract"
    report = build_core_10_report(benchmark, runs, benchmark_kind=benchmark_kind)
    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "version": "hxyos-benchmark-cli.v1",
        "suite": args.suite,
        "benchmark_kind": report["benchmark_kind"],
        "business_readiness_claimed": report["business_readiness_claimed"],
        "pass_rate": report["pass_rate"],
        "target_met": report["target_met"],
        "authority_leakage_failures": report["authority_leakage_failures"],
        "high_risk_interception_rate": report["high_risk_interception_rate"],
        "metrics": report["metrics"],
        "report_path": str(Path(args.output)) if args.output else "",
    }, ensure_ascii=False))
    return 0 if report["target_met"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
