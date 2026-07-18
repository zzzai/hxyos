#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_ROOT = ROOT / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from hxy_product.material_repository import MaterialRepository  # noqa: E402
from hxy_product.material_scanner import scanner_from_environment  # noqa: E402
from hxy_product.material_worker import process_one_material_job  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the HXY durable material intake worker.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--lease-seconds", type=int, default=300)
    parser.add_argument("--base-retry-seconds", type=int, default=30)
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}-{os.getpid()}")
    args = parser.parse_args()

    database_url = os.getenv("HXY_DATABASE_URL", "").strip()
    if not database_url:
        print(json.dumps({"status": "error", "error_code": "database_not_configured"}))
        return 2
    root_dir = Path(os.getenv("HXY_ROOT_DIR", str(ROOT))).resolve()
    material_root = root_dir / "data" / "product-materials"
    repository = MaterialRepository(database_url)
    scanner = scanner_from_environment()

    while True:
        result = process_one_material_job(
            repository,
            material_root=material_root,
            worker_id=args.worker_id,
            lease_seconds=max(args.lease_seconds, 1),
            base_retry_seconds=max(args.base_retry_seconds, 1),
            scanner=scanner.scan,
        )
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.once:
            return 0
        if result["status"] == "idle":
            time.sleep(max(args.poll_seconds, 0.1))


if __name__ == "__main__":
    raise SystemExit(main())
