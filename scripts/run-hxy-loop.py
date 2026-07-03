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

from hxy_knowledge.loop_engine import (  # noqa: E402
    BenchmarkImprovementLoopConfig,
    CompileKnowledgeLoopConfig,
    LoopThresholds,
    run_benchmark_improvement_loop,
    run_compile_knowledge_loop,
)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run allowlisted HXY loop workflows.")
    subparsers = parser.add_subparsers(dest="loop_name", required=True)

    compile_parser = subparsers.add_parser("compile_knowledge", help="Compile HXY reference materials with loop gates.")
    compile_parser.add_argument("--raw-dir", required=True, help="Directory containing raw .md/.txt HXY materials.")
    compile_parser.add_argument("--wiki-dir", required=True, help="Directory for compiled wiki artifacts.")
    compile_parser.add_argument("--report", required=True, help="Path to compiler report JSON.")
    compile_parser.add_argument("--run-id", default="knowledge-loop-latest", help="Loop run id.")
    compile_parser.add_argument("--runs-dir", default=str(ROOT / "knowledge" / "runs"), help="Directory for loop run artifacts.")
    compile_parser.add_argument("--min-review-queue", type=int, default=20, help="Minimum review queue items required.")
    compile_parser.add_argument("--min-answer-card-drafts", type=int, default=10, help="Minimum answer card drafts required.")
    compile_parser.add_argument("--min-claim-count", type=int, default=1, help="Minimum claim count required.")
    compile_parser.add_argument("--max-iterations", type=int, default=2, help="Hard iteration limit.")

    benchmark_parser = subparsers.add_parser("benchmark_improvement", help="Run HXY benchmark and create correction tasks.")
    benchmark_parser.add_argument("--benchmark", required=True, help="Path to benchmark JSON.")
    benchmark_parser.add_argument("--report", required=True, help="Path to benchmark report JSON.")
    benchmark_parser.add_argument("--run-id", default="benchmark-loop-latest", help="Loop run id.")
    benchmark_parser.add_argument("--runs-dir", default=str(ROOT / "knowledge" / "runs"), help="Directory for loop run artifacts.")
    benchmark_parser.add_argument("--min-pass-rate", type=float, default=None, help="Optional benchmark pass-rate threshold.")
    benchmark_parser.add_argument("--max-iterations", type=int, default=1, help="Hard iteration limit.")
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    if args.loop_name == "compile_knowledge":
        state = run_compile_knowledge_loop(
            CompileKnowledgeLoopConfig(
                raw_dir=Path(args.raw_dir),
                wiki_dir=Path(args.wiki_dir),
                report_path=Path(args.report),
                runs_dir=Path(args.runs_dir),
                run_id=args.run_id,
                thresholds=LoopThresholds(
                    min_review_queue=args.min_review_queue,
                    min_answer_card_drafts=args.min_answer_card_drafts,
                    min_claim_count=args.min_claim_count,
                ),
                max_iterations=args.max_iterations,
            )
        )
        state_path = Path(args.runs_dir) / args.run_id / "loop-state.json"
        print(
            json.dumps(
                {
                    "version": "hxy-loop-runner-cli.v1",
                    "loop_name": state["loop_name"],
                    "run_id": state["run_id"],
                    "status": state["status"],
                    "stop_reason": state["stop_reason"],
                    "iteration_count": state["iteration_count"],
                    "state_path": str(state_path),
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.loop_name == "benchmark_improvement":
        state = run_benchmark_improvement_loop(
            BenchmarkImprovementLoopConfig(
                benchmark_path=Path(args.benchmark),
                report_path=Path(args.report),
                runs_dir=Path(args.runs_dir),
                run_id=args.run_id,
                max_iterations=args.max_iterations,
                min_pass_rate=args.min_pass_rate,
            )
        )
        state_path = Path(args.runs_dir) / args.run_id / "loop-state.json"
        print(
            json.dumps(
                {
                    "version": "hxy-loop-runner-cli.v1",
                    "loop_name": state["loop_name"],
                    "run_id": state["run_id"],
                    "status": state["status"],
                    "stop_reason": state["stop_reason"],
                    "iteration_count": state["iteration_count"],
                    "state_path": str(state_path),
                },
                ensure_ascii=False,
            )
        )
        return 0

    parser.error(f"unsupported loop: {args.loop_name}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
