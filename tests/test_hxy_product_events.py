from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from apps.api.hxy_product.auth import Principal
from apps.api.hxy_product.product_event_routes import create_product_event_router
from apps.api.hxy_product.product_event_schemas import ProductEventRequest


ROOT = Path(__file__).resolve().parents[1]
ORGANIZATION_ID = "10000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "10000000-0000-0000-0000-000000000002"
ACCOUNT_ID = "10000000-0000-0000-0000-000000000003"
STORE_ID = "store-first"
CLIENT_EVENT_ID = "10000000-0000-0000-0000-000000000004"
SUBJECT_ID = "10000000-0000-0000-0000-000000000005"


class IdentityRepository:
    def resolve_session(self, _raw_token: str):
        return Principal(
            account_id=ACCOUNT_ID,
            display_name="李师傅",
            assignment_id=ASSIGNMENT_ID,
        )

    def list_assignments(self, account_id: str):
        assert account_id == ACCOUNT_ID
        return [
            SimpleNamespace(
                assignment_id=ASSIGNMENT_ID,
                account_id=ACCOUNT_ID,
                organization_id=ORGANIZATION_ID,
                store_id=STORE_ID,
                role="store_employee",
                status="active",
            )
        ]


class EventRepository:
    def __init__(self, *, source_accessible: bool = True) -> None:
        self.calls: list[dict[str, object]] = []
        self.source_accessible = source_accessible
        self.access_checks: list[dict[str, object]] = []

    def briefing_source_is_accessible(self, **scope: object) -> bool:
        self.access_checks.append(scope)
        return self.source_accessible

    def append_event(self, **event: object):
        self.calls.append(event)
        return {
            "event_id": "10000000-0000-0000-0000-000000000006",
            "event_name": event["event_name"],
            "created_at": "2026-07-21T10:00:00Z",
        }


def test_product_event_request_has_no_free_text_or_dynamic_payload() -> None:
    request = ProductEventRequest(
        client_event_id=UUID(CLIENT_EVENT_ID),
        event_name="briefing_feedback",
        subject_id=UUID(SUBJECT_ID),
        useful=True,
    )

    assert set(request.model_dump()) == {
        "client_event_id",
        "event_name",
        "subject_id",
        "useful",
    }
    with pytest.raises(ValidationError):
        ProductEventRequest.model_validate(
            {
                **request.model_dump(mode="json"),
                "text": "顾客手机号 13800000000",
            }
        )
    with pytest.raises(ValidationError):
        ProductEventRequest(
            client_event_id=UUID(CLIENT_EVENT_ID),
            event_name="arbitrary_event",
            subject_id=UUID(SUBJECT_ID),
        )
    with pytest.raises(ValidationError):
        ProductEventRequest(
            client_event_id=UUID(CLIENT_EVENT_ID),
            event_name="intake_succeeded",
            subject_id=UUID(SUBJECT_ID),
        )


def test_product_event_route_uses_authenticated_assignment_scope() -> None:
    events = EventRepository()
    app = FastAPI()
    app.include_router(
        create_product_event_router(
            lambda: IdentityRepository(),
            lambda: events,
        )
    )
    response = TestClient(app).post(
        "/api/v1/product-events",
        headers={"Authorization": "Bearer " + "t" * 43},
        json={
            "client_event_id": CLIENT_EVENT_ID,
            "event_name": "briefing_feedback",
            "subject_id": SUBJECT_ID,
            "useful": True,
        },
    )

    assert response.status_code == 201
    assert response.json()["event"]["event_name"] == "briefing_feedback"
    assert events.calls == [
        {
            "organization_id": ORGANIZATION_ID,
            "store_id": STORE_ID,
            "assignment_id": ASSIGNMENT_ID,
            "client_event_id": CLIENT_EVENT_ID,
            "event_name": "briefing_feedback",
            "subject_id": SUBJECT_ID,
            "useful": True,
        }
    ]
    assert events.access_checks == [
        {
            "organization_id": ORGANIZATION_ID,
            "store_id": STORE_ID,
            "assignment_id": ASSIGNMENT_ID,
            "role": "store_employee",
            "subject_id": SUBJECT_ID,
        }
    ]


def test_product_event_route_hides_missing_or_unauthorized_brief_source() -> None:
    events = EventRepository(source_accessible=False)
    app = FastAPI()
    app.include_router(
        create_product_event_router(
            lambda: IdentityRepository(),
            lambda: events,
        )
    )
    response = TestClient(app).post(
        "/api/v1/product-events",
        headers={"Authorization": "Bearer " + "t" * 43},
        json={
            "client_event_id": CLIENT_EVENT_ID,
            "event_name": "briefing_feedback",
            "subject_id": SUBJECT_ID,
            "useful": False,
        },
    )

    assert response.status_code == 404
    assert events.calls == []


def test_product_event_migration_is_append_only_and_has_no_content_payload() -> None:
    sql = (ROOT / "data/migrations/026_hxy_product_events.sql").read_text(
        encoding="utf-8"
    )

    assert "CREATE TABLE IF NOT EXISTS hxy_product_events" in sql
    assert "intake_succeeded" in sql
    assert "service_feedback_completed" in sql
    assert "briefing_feedback" in sql
    assert "learning_completed" in sql
    assert "duration_ms" in sql
    assert "useful" in sql
    assert "prevent_hxy_product_event_mutation" in sql
    assert "hxy_record_authoritative_product_event" in sql
    assert "hxy_training_authoritative_product_event" in sql
    assert "hxy_service_feedback_authoritative_product_event" in sql
    assert "BEFORE TRUNCATE" in sql
    assert "UNIQUE (organization_id, assignment_id, event_name, subject_id)" in sql
    lowered = sql.lower()
    assert " json" not in lowered
    assert "payload json" not in lowered
    assert "phone" not in lowered
    assert "content" not in lowered


def test_product_event_route_is_registered_by_the_real_app_factory(tmp_path: Path) -> None:
    from apps.api.hxy_knowledge_api import create_app

    app = create_app(root_dir=tmp_path, repository_factory=lambda: object())

    methods_by_path = {
        route.path: getattr(route, "methods", set()) for route in app.routes
    }
    assert methods_by_path["/api/v1/product-events"] == {"POST"}
