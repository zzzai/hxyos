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

from hxy_knowledge.brain_benchmark import build_approved_answer_runs, build_benchmark_report, load_benchmark  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run HXY Brain Benchmark.")
    parser.add_argument("--benchmark", required=True, help="Path to benchmark JSON.")
    parser.add_argument("--output", required=True, help="Path to output report JSON.")
    args = parser.parse_args()

    benchmark = load_benchmark(args.benchmark)
    report = build_benchmark_report(benchmark, build_approved_answer_runs(benchmark))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({"version": "hxy-brain-benchmark-cli.v1", "report_path": str(output_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
