#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from hxy_knowledge.eval_runner import run_golden_evals
from hxy_knowledge.golden_questions import authority_cards, golden_questions


def main() -> int:
    result = run_golden_evals(questions=golden_questions(), cards=authority_cards())
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["fail_count"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
