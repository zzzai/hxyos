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

from hxy_product.outbox_repository import OutboxRepository  # noqa: E402
from hxy_product.outbox_worker import process_one_outbox_message  # noqa: E402
from hxy_product.channel_repository import ChannelRepository  # noqa: E402
from hxy_product.issue_understanding import (  # noqa: E402
    IssueProposalRepository,
    build_issue_understanding_handler,
)
from hxy_product.operating_policy import evaluate_issue_proposal  # noqa: E402
from hxy_product.operating_metrics import (  # noqa: E402
    OperatingMetricsRepository,
    build_closed_event_metrics_handler,
)
from hxy_knowledge.model_router import ModelRouter  # noqa: E402


def build_handlers(
    database_url: str,
    *,
    channel_repository=None,
    operating_repository=None,
    model_router=None,
    metrics_repository=None,
) -> dict:
    channel = channel_repository or ChannelRepository(database_url)
    operating = operating_repository or IssueProposalRepository(database_url)
    router = model_router or ModelRouter()
    metrics = metrics_repository or OperatingMetricsRepository(database_url)
    return {
        "understand.inbound.issue": build_issue_understanding_handler(
            channel,
            operating,
            router,
            evaluate_issue_proposal,
        ),
        "metrics.operating_event.closed": build_closed_event_metrics_handler(metrics),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the HXY durable outbox worker.")
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--lease-seconds", type=int, default=120)
    parser.add_argument("--base-retry-seconds", type=int, default=15)
    parser.add_argument("--worker-id", default=f"{socket.gethostname()}-{os.getpid()}")
    args = parser.parse_args()

    database_url = os.getenv("HXY_DATABASE_URL", "").strip()
    if not database_url:
        print(json.dumps({"status": "error", "error_code": "database_not_configured"}))
        return 2

    repository = OutboxRepository(database_url)
    handlers = build_handlers(database_url)
    while True:
        result = process_one_outbox_message(
            repository,
            handlers,
            worker_id=args.worker_id,
            lease_seconds=max(args.lease_seconds, 1),
            base_retry_seconds=max(args.base_retry_seconds, 1),
        )
        print(json.dumps(result, ensure_ascii=False), flush=True)
        if args.once:
            return 0
        if result["status"] == "idle":
            time.sleep(max(args.poll_seconds, 0.1))


if __name__ == "__main__":
    raise SystemExit(main())
