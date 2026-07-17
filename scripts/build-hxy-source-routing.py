#!/usr/bin/env python3
"""Build a private parser-routing audit for governed HXY source files."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = PROJECT_ROOT / "apps" / "api"
for path in (PROJECT_ROOT, API_ROOT):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from apps.api.hxy_product.source_registry import build_source_registry  # noqa: E402
from hxy_knowledge.source_routing import (  # noqa: E402
    build_source_routing_report,
    write_source_routing_report,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inbox", type=Path, default=PROJECT_ROOT / "knowledge" / "raw" / "inbox")
    parser.add_argument("--registry", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=PROJECT_ROOT / "data" / "private" / "source-routing",
    )
    parser.add_argument("--as-of", default=date.today().isoformat())
    args = parser.parse_args()

    if args.registry:
        registry = json.loads(args.registry.read_text(encoding="utf-8"))
    else:
        registry = build_source_registry(args.inbox, as_of=args.as_of)
    report = build_source_routing_report(args.inbox, registry, as_of=args.as_of)
    paths = write_source_routing_report(report, args.output_dir, report_date=args.as_of)
    print(
        "source routing built: "
        f"{report['counts']['routed_sources']} unique sources, "
        f"{report['counts']['error_sources']} errors"
    )
    print(f"json: {paths['json']}")
    print(f"markdown: {paths['markdown']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
