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

from hxy_knowledge.brand_decision import review_brand_artifact, write_brand_review_record


def main() -> int:
    parser = argparse.ArgumentParser(description="Review a first-store HXY brand artifact.")
    parser.add_argument("--artifact-type", default="opening_content")
    parser.add_argument("--stage", default="first_store_opening")
    parser.add_argument("--text", required=True)
    parser.add_argument("--reviews-dir", default="knowledge/brand/reviews")
    args = parser.parse_args()

    review = review_brand_artifact(
        {
            "artifact_type": args.artifact_type,
            "stage": args.stage,
            "text": args.text,
        }
    )
    review_path = write_brand_review_record(review, reviews_dir=Path(args.reviews_dir))
    print(
        json.dumps(
            {
                "version": "hxy-brand-decision-cli.v1",
                "review": review,
                "review_path": review_path.as_posix(),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
