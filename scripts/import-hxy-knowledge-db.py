#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "apps" / "api"))

from hxy_knowledge.config import get_settings
from hxy_knowledge.importer import load_current_records, load_image_understanding_records
from hxy_knowledge.repository import KnowledgeRepository


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="")
    parser.add_argument("--run-name", default="")
    parser.add_argument("--database-url", default="")
    args = parser.parse_args()
    settings = get_settings()
    root = Path(args.root).resolve() if args.root else settings.root_dir
    run_name = args.run_name or settings.run_name
    database_url = args.database_url or settings.database_url
    if not database_url:
        raise SystemExit("HXY_DATABASE_URL or --database-url is required")
    manifest, assets, chunks = load_current_records(root, run_name)
    repo = KnowledgeRepository(database_url)
    manifest_path = f"knowledge/structured/hxy-inbox-manifest-{run_name}.json"
    index_path = f"knowledge/structured/hxy-inbox-search-index-{run_name}.json"
    repo.clear_run(run_name)
    repo.upsert_run(run_name, manifest_path, index_path, len(assets), len(chunks), status="completed")
    repo.upsert_assets(assets)
    repo.upsert_chunks(chunks)
    image_understandings = load_image_understanding_records(root, run_name)
    repo.upsert_image_understandings(image_understandings)
    print(
        json.dumps(
            {
                "run_name": run_name,
                "assets": len(assets),
                "chunks": len(chunks),
                "image_understandings": len(image_understandings),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
