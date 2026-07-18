from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest

from apps.api.hxy_knowledge_api import create_app


ACCOUNT_ID = "10000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
ORGANIZATION_ID = "30000000-0000-0000-0000-000000000001"
STORE_ID = "hxy-pilot-store"
ENVELOPE_ID = "24000000-0000-0000-0000-000000000001"
EVENT_ID = "81000000-0000-0000-0000-000000000001"
WORKFLOW_ID = "82000000-0000-0000-0000-000000000001"
TASK_ID = "83000000-0000-0000-0000-000000000001"
EVIDENCE_ID = "84000000-0000-0000-0000-000000000001"
CLIENT_EVIDENCE_ID = "85000000-0000-0000-0000-000000000001"
ASSET_ID = "26000000-0000-0000-0000-000000000001"
NOW = datetime(2026, 7, 19, 10, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FakePrincipal:
    account_id: str
    display_name: str
    assignment_id: str


@dataclass(frozen=True)
class FakeAssignment:
    assignment_id: str = ASSIGNMENT_ID
    organization_id: str = ORGANIZATION_ID
    organization_name: str = "荷小悦"
    store_id: str | None = STORE_ID
    store_name: str | None = "首店"
    role: str = "store_manager"


class FakeIdentityRepository:
    def __init__(self, assignment: FakeAssignment | None = None) -> None:
        self.assignment = assignment or FakeAssignment()

    def resolve_session(self, raw_token: str) -> FakePrincipal | None:
        if raw_token != "valid-session":
            return None
        return FakePrincipal(ACCOUNT_ID, "测试用户", self.assignment.assignment_id)

    def list_assignments(self, _account_id: str) -> list[FakeAssignment]:
        return [self.assignment]


class FakeChannelRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.error: Exception | None = None
        self.receipt = {
            "id": ENVELOPE_ID,
            "organization_id": ORGANIZATION_ID,
            "channel": "pwa",
            "assignment_id": ASSIGNMENT_ID,
            "store_id": STORE_ID,
            "status": "queued",
            "received_at": NOW,
        }

    def accept_authenticated_inbound(
        self, payload: dict[str, Any], *, assignment: Any
    ) -> dict[str, Any]:
        self.calls.append({"payload": payload, "assignment": assignment})
        if self.error is not None:
            raise self.error
        return dict(self.receipt)


def _event_row() -> dict[str, Any]:
    return {
        "operating_event_id": EVENT_ID,
        "organization_id": ORGANIZATION_ID,
        "store_id": STORE_ID,
        "event_type": "facility_issue",
        "title": "前台灯闪烁",
        "description": "灯具间歇闪烁，需要检查。",
        "location": "前台",
        "impact": "影响顾客体验",
        "acceptance_criteria": "灯具连续运行两小时无闪烁",
        "reporter_assignment_id": ASSIGNMENT_ID,
        "owner_assignment_id": ASSIGNMENT_ID,
        "severity": "medium",
        "status": "active",
        "occurred_at": NOW,
        "due_at": None,
        "closed_at": None,
        "created_at": NOW,
        "updated_at": NOW,
        "storage_key": "/root/hxy/private/event.json",
        "raw_callback": {"secret": "must-not-leak"},
        "prompt": "must-not-leak",
    }


def _task_row() -> dict[str, Any]:
    return {
        "task_id": TASK_ID,
        "operating_event_id": EVENT_ID,
        "workflow_instance_id": WORKFLOW_ID,
        "title": "处理前台灯具",
        "details": "检查并修复灯具。",
        "priority": "high",
        "status": "in_progress",
        "assignee_assignment_id": ASSIGNMENT_ID,
        "result": None,
        "due_at": None,
        "submitted_at": None,
        "accepted_at": None,
        "created_at": NOW,
        "updated_at": NOW,
        "object_key": "private/task.json",
    }


class FakeOperatingRepository:
    def __init__(self) -> None:
        self.list_calls: list[dict[str, Any]] = []
        self.detail_calls: list[dict[str, Any]] = []

    def list_events(self, **kwargs: Any) -> list[dict[str, Any]]:
        self.list_calls.append(kwargs)
        return [_event_row()]

    def get_event(self, **kwargs: Any) -> dict[str, Any] | None:
        self.detail_calls.append(kwargs)
        return {
            "event": _event_row(),
            "workflow": {
                "workflow_instance_id": WORKFLOW_ID,
                "status": "running",
                "current_state": "task_in_progress",
                "created_at": NOW,
                "updated_at": NOW,
            },
            "tasks": [_task_row()],
            "evidence": [
                {
                    "evidence_id": EVIDENCE_ID,
                    "evidence_type": "photo",
                    "statement": "灯具已修复",
                    "source_asset_id": ASSET_ID,
                    "created_by_assignment_id": ASSIGNMENT_ID,
                    "created_at": NOW,
                    "storage_key": "/root/hxy/private/evidence.jpg",
                }
            ],
        }


class FakeOperatingService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, Any]] = []

    def _receipt(self, name: str, command: Any, task_status: str) -> dict[str, Any]:
        self.calls.append((name, command))
        return {
            "event_id": EVENT_ID,
            "event_status": "active",
            "event_updated_at": NOW,
            "task_id": TASK_ID,
            "task_status": task_status,
            "task_updated_at": NOW,
            "workflow_id": WORKFLOW_ID,
            "workflow_status": "running",
        }

    def start_task(self, command: Any) -> dict[str, Any]:
        return self._receipt("start", command, "in_progress")

    def submit_task(self, command: Any) -> dict[str, Any]:
        return self._receipt("submit", command, "submitted")

    def accept_task(self, command: Any) -> dict[str, Any]:
        return self._receipt("accept", command, "accepted")

    def return_for_rework(self, command: Any) -> dict[str, Any]:
        return self._receipt("rework", command, "rework")

    def escalate_event(self, command: Any) -> dict[str, Any]:
        return self._receipt("escalate", command, "in_progress")


class FakeEvidenceRepository:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create_evidence(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        return {
            "evidence_id": EVIDENCE_ID,
            "task_id": TASK_ID,
            "operating_event_id": EVENT_ID,
            "evidence_type": kwargs["evidence_type"],
            "statement": kwargs["statement"],
            "source_asset_id": kwargs["source_asset_id"],
            "created_at": NOW,
            "storage_key": "/root/hxy/private/evidence.jpg",
            "sha256": "a" * 64,
        }


class ASGIClient:
    def __init__(self, app: Any) -> None:
        self.app = app

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        async def run() -> httpx.Response:
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://testserver"
            ) as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(run())


def _headers() -> dict[str, str]:
    return {"Authorization": "Bearer valid-session"}


@pytest.fixture
def operating_context(tmp_path: Path):
    identity = FakeIdentityRepository()
    channel = FakeChannelRepository()
    operating = FakeOperatingRepository()
    service = FakeOperatingService()
    evidence = FakeEvidenceRepository()
    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=lambda: identity,
        conversation_repository_factory=lambda: object(),
        material_repository_factory=lambda: object(),
        task_repository_factory=lambda: object(),
        product_training_repository_factory=lambda: object(),
        channel_repository_factory=lambda: channel,
        operating_repository_factory=lambda: operating,
        evidence_repository_factory=lambda: evidence,
        operating_service_builder=lambda _repository: service,
    )
    return ASGIClient(app), identity, channel, operating, service, evidence


def test_pwa_intake_uses_authenticated_scope_and_is_async(operating_context) -> None:
    client, _, channel, _, _, _ = operating_context
    client_intake_id = str(uuid4())

    response = client.request(
        "POST",
        "/api/v1/operating/intake",
        headers=_headers(),
        json={
            "client_intake_id": client_intake_id,
            "text": "前台灯闪烁，影响接待。",
            "source_asset_ids": [ASSET_ID],
        },
    )

    assert response.status_code == 202
    assert response.json() == {
        "intake": {
            "id": ENVELOPE_ID,
            "status": "understanding",
            "received_at": NOW.isoformat().replace("+00:00", "Z"),
        }
    }
    call = channel.calls[0]
    assert call["payload"]["organization_id"] == ORGANIZATION_ID
    assert call["payload"]["channel"] == "pwa"
    assert call["payload"]["idempotency_key"] == f"{ASSIGNMENT_ID}:{client_intake_id}"
    assert call["assignment"].assignment_id == ASSIGNMENT_ID
    assert call["assignment"].store_id == STORE_ID


def test_pwa_intake_rejects_browser_selected_scope(operating_context) -> None:
    client, _, channel, _, _, _ = operating_context

    response = client.request(
        "POST",
        "/api/v1/operating/intake",
        headers=_headers(),
        json={
            "client_intake_id": str(uuid4()),
            "text": "伪造范围",
            "organization_id": str(uuid4()),
            "store_id": "other-store",
            "reporter_assignment_id": str(uuid4()),
        },
    )

    assert response.status_code == 422
    assert channel.calls == []


def test_duplicate_intake_returns_same_receipt(operating_context) -> None:
    client, _, channel, _, _, _ = operating_context
    payload = {
        "client_intake_id": str(uuid4()),
        "text": "前台灯闪烁",
        "source_asset_ids": [],
    }

    first = client.request(
        "POST", "/api/v1/operating/intake", headers=_headers(), json=payload
    )
    second = client.request(
        "POST", "/api/v1/operating/intake", headers=_headers(), json=payload
    )

    assert first.status_code == second.status_code == 202
    assert first.json() == second.json()
    assert [call["payload"]["idempotency_key"] for call in channel.calls] == [
        f"{ASSIGNMENT_ID}:{payload['client_intake_id']}",
        f"{ASSIGNMENT_ID}:{payload['client_intake_id']}",
    ]


def test_intake_idempotency_conflict_returns_http_409(operating_context) -> None:
    from hxy_product.channel_repository import IntakeIdempotencyConflict

    client, _, channel, _, _, _ = operating_context
    channel.error = IntakeIdempotencyConflict("request fingerprint differs")

    response = client.request(
        "POST",
        "/api/v1/operating/intake",
        headers=_headers(),
        json={
            "client_intake_id": str(uuid4()),
            "text": "前台灯闪烁",
            "source_asset_ids": [],
        },
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Idempotency key conflict"}


def test_event_list_and_detail_use_assignment_scope_and_redact_internals(
    operating_context,
) -> None:
    client, _, _, operating, _, _ = operating_context

    listed = client.request("GET", "/api/v1/operating/events", headers=_headers())
    detailed = client.request(
        "GET", f"/api/v1/operating/events/{EVENT_ID}", headers=_headers()
    )

    assert listed.status_code == detailed.status_code == 200
    assert listed.json()["items"][0]["title"] == "前台灯闪烁"
    assert detailed.json()["event"]["tasks"][0]["id"] == TASK_ID
    assert detailed.json()["event"]["evidence"][0]["id"] == EVIDENCE_ID
    combined = listed.text + detailed.text
    for forbidden in (
        "storage_key",
        "object_key",
        "raw_callback",
        "must-not-leak",
        "/root/hxy",
    ):
        assert forbidden not in combined
    assert operating.list_calls[0] == {
        "organization_id": ORGANIZATION_ID,
        "store_id": STORE_ID,
        "assignment_id": ASSIGNMENT_ID,
        "role": "store_manager",
        "limit": 50,
    }
    assert operating.detail_calls[0]["organization_id"] == ORGANIZATION_ID
    assert operating.detail_calls[0]["store_id"] == STORE_ID


def test_governed_task_commands_derive_actor_from_session(operating_context) -> None:
    client, _, _, _, service, _ = operating_context
    expected = NOW.isoformat()

    started = client.request(
        "POST",
        f"/api/v1/operating/tasks/{TASK_ID}/start",
        headers=_headers(),
        json={"expected_updated_at": expected},
    )
    submitted = client.request(
        "POST",
        f"/api/v1/operating/tasks/{TASK_ID}/submit",
        headers=_headers(),
        json={
            "expected_updated_at": expected,
            "evidence_ids": [EVIDENCE_ID],
            "result": "灯具已修复并连续观察两小时。",
        },
    )
    accepted = client.request(
        "POST",
        f"/api/v1/operating/tasks/{TASK_ID}/accept",
        headers=_headers(),
        json={"expected_updated_at": expected, "reason": "现场验收通过"},
    )
    reworked = client.request(
        "POST",
        f"/api/v1/operating/tasks/{TASK_ID}/rework",
        headers=_headers(),
        json={"expected_updated_at": expected, "reason": "仍有闪烁"},
    )
    escalated = client.request(
        "POST",
        f"/api/v1/operating/events/{EVENT_ID}/escalate",
        headers=_headers(),
        json={
            "expected_updated_at": expected,
            "severity": "high",
            "reason": "存在用电安全风险",
        },
    )

    assert [response.status_code for response in (started, submitted, accepted, reworked, escalated)] == [
        200,
        200,
        200,
        200,
        200,
    ]
    for _, command in service.calls:
        assert str(command.organization_id) == ORGANIZATION_ID
        assert str(command.actor_assignment_id) == ASSIGNMENT_ID


def test_evidence_binds_existing_source_asset_without_exposing_storage(
    operating_context,
) -> None:
    client, _, _, _, _, evidence = operating_context

    response = client.request(
        "POST",
        f"/api/v1/operating/tasks/{TASK_ID}/evidence",
        headers=_headers(),
        json={
            "client_evidence_id": CLIENT_EVIDENCE_ID,
            "source_asset_id": ASSET_ID,
            "evidence_type": "photo",
            "statement": "灯具已修复",
        },
    )

    assert response.status_code == 201
    assert response.json()["evidence"] == {
        "id": EVIDENCE_ID,
        "task_id": TASK_ID,
        "event_id": EVENT_ID,
        "type": "photo",
        "statement": "灯具已修复",
        "source_asset_id": ASSET_ID,
        "created_at": NOW.isoformat().replace("+00:00", "Z"),
    }
    assert evidence.calls[0]["organization_id"] == ORGANIZATION_ID
    assert evidence.calls[0]["store_id"] == STORE_ID
    assert evidence.calls[0]["actor_assignment_id"] == ASSIGNMENT_ID
    assert evidence.calls[0]["client_evidence_id"] == CLIENT_EVIDENCE_ID
    assert "storage_key" not in response.text
    assert "/root/hxy" not in response.text


def test_store_employee_cannot_use_accept_or_escalate_capabilities(tmp_path: Path) -> None:
    identity = FakeIdentityRepository(FakeAssignment(role="store_employee"))
    service = FakeOperatingService()
    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=lambda: identity,
        conversation_repository_factory=lambda: object(),
        material_repository_factory=lambda: object(),
        task_repository_factory=lambda: object(),
        product_training_repository_factory=lambda: object(),
        channel_repository_factory=lambda: FakeChannelRepository(),
        operating_repository_factory=lambda: FakeOperatingRepository(),
        evidence_repository_factory=lambda: FakeEvidenceRepository(),
        operating_service_builder=lambda _repository: service,
    )
    client = ASGIClient(app)

    accepted = client.request(
        "POST",
        f"/api/v1/operating/tasks/{TASK_ID}/accept",
        headers=_headers(),
        json={"expected_updated_at": NOW.isoformat(), "reason": "越权验收"},
    )
    escalated = client.request(
        "POST",
        f"/api/v1/operating/events/{EVENT_ID}/escalate",
        headers=_headers(),
        json={
            "expected_updated_at": NOW.isoformat(),
            "severity": "high",
            "reason": "越权升级",
        },
    )

    assert accepted.status_code == escalated.status_code == 403
    assert service.calls == []


def test_evidence_asset_validation_rejects_unsafe_or_mismatched_assets() -> None:
    from apps.api.hxy_product.evidence_repository import (
        EvidenceAssetRejected,
        validate_evidence_asset,
    )

    valid = {
        "store_id": STORE_ID,
        "extension": ".jpg",
        "media_type": "image/jpeg",
        "size_bytes": 1024,
        "sha256": "a" * 64,
        "scan_status": "clean",
        "status": "ready",
    }
    validate_evidence_asset(
        valid,
        evidence_type="photo",
        expected_store_id=STORE_ID,
        max_bytes=10 * 1024,
    )

    unsafe_variants = [
        {**valid, "scan_status": "pending"},
        {**valid, "extension": ".exe", "media_type": "application/x-msdownload"},
        {**valid, "media_type": "text/plain"},
        {**valid, "sha256": "not-a-hash"},
        {**valid, "size_bytes": 10 * 1024 + 1},
        {**valid, "store_id": "another-store"},
    ]
    for asset in unsafe_variants:
        with pytest.raises(EvidenceAssetRejected):
            validate_evidence_asset(
                asset,
                evidence_type="photo",
                expected_store_id=STORE_ID,
                max_bytes=10 * 1024,
            )


def test_evidence_repository_binds_clean_source_asset_in_one_transaction() -> None:
    from apps.api.hxy_product.evidence_repository import EvidenceRepository

    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Result:
        def __init__(self, row: dict[str, Any] | None = None) -> None:
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append((normalized, params))
            if "FROM hxy_product_tasks AS task" in normalized:
                return Result(
                    {
                        "task_id": TASK_ID,
                        "organization_id": ORGANIZATION_ID,
                        "store_id": STORE_ID,
                        "operating_event_id": EVENT_ID,
                        "workflow_instance_id": WORKFLOW_ID,
                        "assignee_assignment_id": ASSIGNMENT_ID,
                        "status": "in_progress",
                    }
                )
            if "FROM hxy_role_assignments" in normalized:
                return Result(
                    {
                        "assignment_id": ASSIGNMENT_ID,
                        "organization_id": ORGANIZATION_ID,
                        "store_id": STORE_ID,
                        "role": "store_employee",
                        "status": "active",
                    }
                )
            if "FROM hxy_product_materials AS material" in normalized:
                return Result(
                    {
                        "material_id": ASSET_ID,
                        "assignment_id": ASSIGNMENT_ID,
                        "organization_id": ORGANIZATION_ID,
                        "store_id": STORE_ID,
                        "extension": ".jpg",
                        "media_type": "image/jpeg",
                        "size_bytes": 1024,
                        "sha256": "a" * 64,
                        "status": "ready",
                        "scan_status": "clean",
                        "visibility_scope": {"uploader": True},
                    }
                )
            if "FROM hxy_operating_evidence AS evidence" in normalized:
                return Result(None)
            if "INSERT INTO hxy_operating_evidence" in normalized:
                assert len(params) == 12
                return Result(
                    {
                        "evidence_id": EVIDENCE_ID,
                        "operating_event_id": EVENT_ID,
                        "workflow_instance_id": WORKFLOW_ID,
                        "task_id": TASK_ID,
                        "client_evidence_id": CLIENT_EVIDENCE_ID,
                        "evidence_type": "photo",
                        "source_asset_id": ASSET_ID,
                        "statement": "灯具已修复",
                        "created_by_assignment_id": ASSIGNMENT_ID,
                        "created_at": NOW,
                    }
                )
            if "INSERT INTO hxy_asset_bindings" in normalized:
                return Result()
            raise AssertionError(normalized)

    repository = EvidenceRepository(
        "postgresql://evidence.test/hxy",
        max_evidence_bytes=10 * 1024,
    )
    repository.connect = lambda: Connection()

    evidence = repository.create_evidence(
        organization_id=ORGANIZATION_ID,
        store_id=STORE_ID,
        task_id=TASK_ID,
        client_evidence_id=CLIENT_EVIDENCE_ID,
        source_asset_id=ASSET_ID,
        evidence_type="photo",
        statement="灯具已修复",
        actor_assignment_id=ASSIGNMENT_ID,
    )

    assert evidence["evidence_id"] == EVIDENCE_ID
    evidence_insert = next(
        i for i, (sql, _) in enumerate(calls) if "INSERT INTO hxy_operating_evidence" in sql
    )
    binding_insert = next(
        i for i, (sql, _) in enumerate(calls) if "INSERT INTO hxy_asset_bindings" in sql
    )
    assert evidence_insert < binding_insert


def test_evidence_repository_retry_returns_original_before_task_revalidation() -> None:
    from apps.api.hxy_product.evidence_repository import EvidenceRepository

    calls: list[str] = []

    class Result:
        def __init__(self, row: dict[str, Any] | None = None) -> None:
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            calls.append(normalized)
            if "FROM hxy_role_assignments" in normalized:
                return Result(
                    {
                        "assignment_id": ASSIGNMENT_ID,
                        "organization_id": ORGANIZATION_ID,
                        "store_id": STORE_ID,
                        "role": "store_employee",
                        "status": "active",
                    }
                )
            if "FROM hxy_operating_evidence AS evidence" in normalized:
                return Result(
                    {
                        "evidence_id": EVIDENCE_ID,
                        "operating_event_id": EVENT_ID,
                        "workflow_instance_id": WORKFLOW_ID,
                        "task_id": TASK_ID,
                        "client_evidence_id": CLIENT_EVIDENCE_ID,
                        "evidence_type": "photo",
                        "source_asset_id": ASSET_ID,
                        "statement": "灯具已修复",
                        "created_by_assignment_id": ASSIGNMENT_ID,
                        "created_at": NOW,
                    }
                )
            raise AssertionError(f"retry must not revalidate task or asset: {normalized}")

    repository = EvidenceRepository(
        "postgresql://evidence.test/hxy",
        max_evidence_bytes=10 * 1024,
    )
    repository.connect = lambda: Connection()

    evidence = repository.create_evidence(
        organization_id=ORGANIZATION_ID,
        store_id=STORE_ID,
        task_id=TASK_ID,
        client_evidence_id=CLIENT_EVIDENCE_ID,
        source_asset_id=ASSET_ID,
        evidence_type="photo",
        statement="灯具已修复",
        actor_assignment_id=ASSIGNMENT_ID,
    )

    assert evidence["evidence_id"] == EVIDENCE_ID
    assert not any("hxy_product_tasks" in sql for sql in calls)
    assert not any("hxy_product_materials" in sql for sql in calls)


def test_evidence_repository_rejects_reused_client_id_with_different_payload() -> None:
    from apps.api.hxy_product.evidence_repository import (
        EvidenceRepository,
        EvidenceStateConflict,
    )

    existing = {
        "task_id": TASK_ID,
        "source_asset_id": ASSET_ID,
        "evidence_type": "photo",
        "statement": "原始证据",
    }

    with pytest.raises(EvidenceStateConflict, match="already used"):
        EvidenceRepository._return_matching_existing(
            existing,
            task_id=TASK_ID,
            source_asset_id=ASSET_ID,
            evidence_type="photo",
            statement="不同证据",
        )


def test_evidence_repository_rejects_employee_who_is_not_task_assignee() -> None:
    from apps.api.hxy_product.evidence_repository import (
        EvidencePermissionDenied,
        EvidenceRepository,
    )

    queried_assets: list[None] = []

    class Result:
        def __init__(self, row: dict[str, Any] | None = None) -> None:
            self.row = row

        def fetchone(self):
            return self.row

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, _params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            if "FROM hxy_product_tasks AS task" in normalized:
                return Result(
                    {
                        "task_id": TASK_ID,
                        "organization_id": ORGANIZATION_ID,
                        "store_id": STORE_ID,
                        "operating_event_id": EVENT_ID,
                        "workflow_instance_id": WORKFLOW_ID,
                        "assignee_assignment_id": str(uuid4()),
                        "status": "in_progress",
                    }
                )
            if "FROM hxy_role_assignments" in normalized:
                return Result(
                    {
                        "assignment_id": ASSIGNMENT_ID,
                        "organization_id": ORGANIZATION_ID,
                        "store_id": STORE_ID,
                        "role": "store_employee",
                        "status": "active",
                    }
                )
            if "FROM hxy_operating_evidence AS evidence" in normalized:
                return Result(None)
            if "FROM hxy_product_materials AS material" in normalized:
                queried_assets.append(None)
            raise AssertionError(normalized)

    repository = EvidenceRepository(
        "postgresql://evidence.test/hxy",
        max_evidence_bytes=10 * 1024,
    )
    repository.connect = lambda: Connection()

    with pytest.raises(EvidencePermissionDenied):
        repository.create_evidence(
            organization_id=ORGANIZATION_ID,
            store_id=STORE_ID,
            task_id=TASK_ID,
            client_evidence_id=CLIENT_EVIDENCE_ID,
            source_asset_id=ASSET_ID,
            evidence_type="photo",
            statement="越权证据",
            actor_assignment_id=ASSIGNMENT_ID,
        )

    assert queried_assets == []


def test_employee_event_list_is_limited_to_personal_or_store_visible_work() -> None:
    from apps.api.hxy_product.operating_repository import OperatingRepository

    executed: list[tuple[str, tuple[Any, ...]]] = []

    class Result:
        def fetchall(self):
            return []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            executed.append((" ".join(sql.split()), params))
            return Result()

    repository = OperatingRepository("postgresql://operating.test/hxy")
    repository.connect = lambda: Connection()

    repository.list_events(
        organization_id=ORGANIZATION_ID,
        store_id=STORE_ID,
        assignment_id=ASSIGNMENT_ID,
        role="store_employee",
        limit=50,
    )

    sql, params = executed[0]
    assert "event.store_id = %s" in sql
    assert "event.reporter_assignment_id = %s::uuid" in sql
    assert "event.owner_assignment_id = %s::uuid" in sql
    assert "EXISTS ( SELECT 1 FROM hxy_product_tasks AS visible_task" in sql
    assert "visible_task.assignee_assignment_id = %s::uuid" in sql
    assert "visible_task.visibility = 'store'" in sql
    assert params == (
        ORGANIZATION_ID,
        STORE_ID,
        ASSIGNMENT_ID,
        ASSIGNMENT_ID,
        ASSIGNMENT_ID,
        50,
    )


def test_employee_event_detail_filters_other_tasks_and_private_evidence() -> None:
    from apps.api.hxy_product.operating_repository import OperatingRepository

    executed: list[tuple[str, tuple[Any, ...]]] = []

    class Result:
        def __init__(self, row: dict[str, Any] | None = None) -> None:
            self.row = row

        def fetchone(self):
            return self.row

        def fetchall(self):
            return []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            normalized = " ".join(sql.split())
            executed.append((normalized, params))
            if "FROM hxy_operating_events AS event" in normalized:
                return Result(_event_row())
            return Result()

    repository = OperatingRepository("postgresql://operating.test/hxy")
    repository.connect = lambda: Connection()

    detail = repository.get_event(
        organization_id=ORGANIZATION_ID,
        event_id=EVENT_ID,
        store_id=STORE_ID,
        assignment_id=ASSIGNMENT_ID,
        role="store_employee",
    )

    assert detail is not None
    task_sql, task_params = next(
        (sql, params) for sql, params in executed if "FROM hxy_product_tasks AS task" in sql
    )
    assert "task.assignee_assignment_id = %s::uuid" in task_sql
    assert "task.visibility = 'store'" in task_sql
    assert task_params == (ORGANIZATION_ID, EVENT_ID, ASSIGNMENT_ID)
    evidence_sql, evidence_params = next(
        (sql, params) for sql, params in executed if "FROM hxy_operating_evidence AS evidence" in sql
    )
    assert "evidence.created_by_assignment_id = %s::uuid" in evidence_sql
    assert "evidence.visibility_scope @> '{\"task_assignee\": true}'::jsonb" in evidence_sql
    assert "evidence.visibility_scope @> '{\"store_employee\": true}'::jsonb" in evidence_sql
    assert evidence_params == (
        ORGANIZATION_ID,
        EVENT_ID,
        ASSIGNMENT_ID,
        ASSIGNMENT_ID,
    )
