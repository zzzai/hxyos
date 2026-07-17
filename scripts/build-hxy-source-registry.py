#!/usr/bin/env python3
"""Build a private, read-only registry for HXY inbox source files."""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
for path in (PROJECT_ROOT, API_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from apps.api.hxy_product.source_registry import (
    build_source_registry,
    write_registry_reports,
)  # noqa: E402


def main() -> int:
    project_root = PROJECT_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--inbox",
        type=Path,
        default=project_root / "knowledge" / "raw" / "inbox",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_root / "data" / "private" / "source-registry",
    )
    parser.add_argument("--as-of", default=date.today().isoformat())
    args = parser.parse_args()

    registry = build_source_registry(args.inbox, as_of=args.as_of)
    paths = write_registry_reports(
        registry,
        args.output_dir,
        report_date=args.as_of,
    )
    print(
        "source registry built: "
        f"{registry['counts']['path_records']} paths, "
        f"{registry['counts']['content_groups']} content groups"
    )
    print(f"json: {paths['json']}")
    print(f"markdown: {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
