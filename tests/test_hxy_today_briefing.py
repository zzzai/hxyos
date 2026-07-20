from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import pytest

from apps.api.hxy_knowledge_api import create_app
from apps.api.hxy_product.briefing_schemas import project_brief_items


ORGANIZATION_ID = "10000000-0000-0000-0000-000000000001"
FOUNDER_ID = "40000000-0000-0000-0000-000000000001"
RECORD_ID = "20000000-0000-0000-0000-000000000001"
OTHER_RECORD_ID = "20000000-0000-0000-0000-000000000099"
CAPTURED_AT = datetime(2026, 7, 20, 8, 30, tzinfo=timezone.utc)


def evidence(record_id: str = RECORD_ID, quote: str = "原文依据") -> dict[str, Any]:
    return {
        "source_record_id": record_id,
        "quote": quote,
    }


def interpreted_record(
    *,
    record_id: str = RECORD_ID,
    risks: list[dict[str, Any]] | None = None,
    decisions: list[dict[str, Any]] | None = None,
    progress: list[dict[str, Any]] | None = None,
    captured_at: datetime = CAPTURED_AT,
) -> dict[str, Any]:
    return {
        "id": record_id,
        "captured_at": captured_at,
        "interpretation": {
            "risks": risks or [],
            "decisions": decisions or [],
            "progress": progress or [],
            "missing_information": ["不要展示这条没有证据的缺失信息"],
        },
    }


def test_today_projection_returns_at_most_three_evidence_backed_items() -> None:
    records = [
        interpreted_record(
            risks=[
                {
                    "statement": f"风险 {index}",
                    "severity": "high",
                    "evidence": [evidence(quote=f"风险依据 {index}")],
                }
                for index in range(5)
            ]
        )
    ]

    items = project_brief_items(records, limit=50)

    assert len(items) == 3
    assert all(item["source_record_id"] == RECORD_ID for item in items)
    assert all(item["evidence"] for item in items)


def test_today_projection_omits_unsourced_items_and_missing_information() -> None:
    records = [
        interpreted_record(
            risks=[
                {"statement": "没有证据的风险", "severity": "critical", "evidence": []}
            ],
            decisions=[
                {"statement": "没有证据的决策", "evidence": []}
            ],
            progress=[
                {"statement": "没有证据的进展", "evidence": []}
            ],
        )
    ]

    assert project_brief_items(records) == []


def test_today_projection_ranks_critical_high_risks_then_decisions_then_progress() -> None:
    records = [
        interpreted_record(
            risks=[
                {
                    "statement": "高风险",
                    "severity": "high",
                    "evidence": [evidence(quote="高风险依据")],
                },
                {
                    "statement": "关键风险",
                    "severity": "critical",
                    "evidence": [evidence(quote="关键风险依据")],
                },
            ],
            decisions=[
                {"statement": "已经决定采购", "evidence": [evidence(quote="采购决定依据")]}
            ],
            progress=[
                {"statement": "装修已进入水电", "evidence": [evidence(quote="水电进度依据")]}
            ],
        )
    ]

    items = project_brief_items(records)

    assert [item["kind"] for item in items] == ["risk", "risk", "decision"]
    assert [item["severity"] for item in items[:2]] == ["critical", "high"]


def test_medium_risk_does_not_displace_decision_or_progress() -> None:
    records = [
        interpreted_record(
            risks=[
                {
                    "statement": "中风险",
                    "severity": "medium",
                    "evidence": [evidence(quote="中风险依据")],
                }
            ],
            decisions=[
                {"statement": "关键决定", "evidence": [evidence(quote="决定依据")]}
            ],
            progress=[
                {"statement": "重要进展", "evidence": [evidence(quote="进展依据")]}
            ],
        )
    ]

    items = project_brief_items(records, limit=2)

    assert [item["kind"] for item in items] == ["decision", "progress"]


@dataclass(frozen=True)
class RoutePrincipal:
    account_id: str = "11000000-0000-0000-0000-000000000001"
    display_name: str = "测试创始人"
    assignment_id: str = FOUNDER_ID


@dataclass(frozen=True)
class RouteAssignment:
    assignment_id: str = FOUNDER_ID
    organization_id: str = ORGANIZATION_ID
    organization_name: str = "荷小悦"
    store_id: str | None = None
    store_name: str | None = None
    role: str = "founder"


class IdentityRepository:
    def __init__(self, assignment: RouteAssignment | None = None) -> None:
        self.assignment = assignment or RouteAssignment()

    def resolve_session(self, raw_token: str) -> RoutePrincipal | None:
        if raw_token != "valid-session":
            return None
        return RoutePrincipal(assignment_id=self.assignment.assignment_id)

    def list_assignments(self, _account_id: str) -> list[RouteAssignment]:
        return [self.assignment]


class BriefingRepository:
    def __init__(self, records: list[dict[str, Any]]) -> None:
        self.records = records
        self.scopes: list[dict[str, Any]] = []

    def list_briefing_records(self, **scope: Any) -> list[dict[str, Any]]:
        self.scopes.append(scope)
        return self.records


class RouteClient:
    def __init__(self, app: Any) -> None:
        self.app = app

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        async def run() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.get(url, **kwargs)

        return asyncio.run(run())


def briefing_client(
    tmp_path: Path,
    briefing_repository: BriefingRepository,
    assignment: RouteAssignment | None = None,
) -> RouteClient:
    identity = IdentityRepository(assignment)
    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=lambda: identity,
        briefing_repository_factory=lambda: briefing_repository,
    )
    return RouteClient(app)


def test_today_route_uses_role_scope_and_hard_maximum_of_three(tmp_path: Path) -> None:
    repository = BriefingRepository(
        [
            interpreted_record(
                risks=[
                    {
                        "statement": "有证据的风险",
                        "severity": "critical",
                        "evidence": [evidence(quote="风险依据")],
                    }
                ]
            )
        ]
    )
    client = briefing_client(tmp_path, repository)

    response = client.get(
        "/api/v1/today?limit=50",
        headers={"Authorization": "Bearer valid-session"},
    )

    assert response.status_code == 200
    assert len(response.json()["items"]) <= 3
    assert repository.scopes[0] == {
        "organization_id": ORGANIZATION_ID,
        "assignment_id": FOUNDER_ID,
        "role": "founder",
        "store_id": None,
        "limit": 100,
    }


def test_system_admin_cannot_read_today(tmp_path: Path) -> None:
    repository = BriefingRepository([])
    client = briefing_client(
        tmp_path,
        repository,
        RouteAssignment(assignment_id=FOUNDER_ID, role="system_admin"),
    )

    response = client.get(
        "/api/v1/today",
        headers={"Authorization": "Bearer valid-session"},
    )

    assert response.status_code == 403
    assert repository.scopes == []


class QueryResult:
    def __init__(self, rows: list[dict[str, Any]] | None = None) -> None:
        self.rows = rows or []

    def fetchall(self) -> list[dict[str, Any]]:
        return self.rows


class RecordingConnection:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self) -> "RecordingConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> QueryResult:
        self.executed.append((" ".join(sql.split()), params))
        return QueryResult()


def test_store_employee_briefing_query_is_limited_to_own_submission() -> None:
    from apps.api.hxy_product.briefing_repository import BriefingRepository as Repository

    connection = RecordingConnection()
    repository = Repository("postgresql://briefing.test/hxy")
    repository.connect = lambda: connection

    repository.list_briefing_records(
        organization_id=ORGANIZATION_ID,
        assignment_id=FOUNDER_ID,
        role="store_employee",
        store_id="store-1",
    )

    sql, params = connection.executed[0]
    assert "envelope.sender_assignment_id = %s::uuid" in sql
    assert params == (ORGANIZATION_ID, FOUNDER_ID, 100)


def test_store_manager_briefing_query_is_limited_to_active_store() -> None:
    from apps.api.hxy_product.briefing_repository import BriefingRepository as Repository

    connection = RecordingConnection()
    repository = Repository("postgresql://briefing.test/hxy")
    repository.connect = lambda: connection

    repository.list_briefing_records(
        organization_id=ORGANIZATION_ID,
        assignment_id=FOUNDER_ID,
        role="store_manager",
        store_id="store-1",
    )

    sql, params = connection.executed[0]
    assert "envelope.store_id = %s" in sql
    assert params == (ORGANIZATION_ID, "store-1", 100)


def test_briefing_query_prioritizes_evidenced_items_before_freshness_window() -> None:
    from apps.api.hxy_product.briefing_repository import BriefingRepository as Repository

    connection = RecordingConnection()
    repository = Repository("postgresql://briefing.test/hxy")
    repository.connect = lambda: connection

    repository.list_briefing_records(
        organization_id=ORGANIZATION_ID,
        assignment_id=FOUNDER_ID,
        role="founder",
        store_id=None,
    )

    sql, _params = connection.executed[0]
    priority_position = sql.index("CASE")
    freshness_position = sql.index("envelope.received_at DESC")
    assert "item ->> 'severity' = 'critical'" in sql
    assert "jsonb_typeof(item -> 'evidence') = 'array'" in sql
    assert (
        "evidence ->> 'source_record_id' = envelope.envelope_id::text" in sql
    )
    assert "NULLIF(BTRIM(evidence ->> 'quote'), '') IS NOT NULL" in sql
    assert priority_position < freshness_position
