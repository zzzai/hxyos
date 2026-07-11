#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
for import_root in (ROOT, ROOT / "apps" / "api"):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from apps.api.hxy_engines.semantic_benchmark import (  # noqa: E402
    build_blind_review_pack,
    semantic_answer_runs_from_payload,
)


TRACKED_BENCHMARK_DIR = (ROOT / "knowledge" / "benchmarks").resolve()


def _load(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must contain an object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a blind semantic review pack")
    parser.add_argument("--benchmark", required=True, type=Path)
    parser.add_argument("--rubric", required=True, type=Path)
    parser.add_argument("--calibration", required=True, type=Path)
    parser.add_argument("--answers", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--seed", type=int, default=20260711)
    args = parser.parse_args()

    output = args.output.resolve()
    if output.is_relative_to(TRACKED_BENCHMARK_DIR):
        print(
            "private review packs cannot be written under knowledge/benchmarks",
            file=sys.stderr,
        )
        return 2
    try:
        pack = build_blind_review_pack(
            _load(args.benchmark),
            _load(args.rubric),
            _load(args.calibration),
            semantic_answer_runs_from_payload(_load(args.answers)),
            seed=args.seed,
        )
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(pack, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        print(f"review pack input error: {exc}", file=sys.stderr)
        return 2
    print(
        json.dumps(
            {
                "version": "hxy-semantic-review-pack-cli.v1",
                "pack_name": output.name,
                "case_count": pack["case_count"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
