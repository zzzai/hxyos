from __future__ import annotations

import asyncio
import importlib
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from uuid import uuid4

import httpx
import pytest

from apps.api.hxy_knowledge_api import create_app


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "011_hxy_product_materials.sql"
ACCOUNT_ID = "10000000-0000-0000-0000-000000000001"
ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
FOREIGN_ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000099"
ORGANIZATION_ID = "30000000-0000-0000-0000-000000000001"
MATERIAL_ID = "70000000-0000-0000-0000-000000000001"
FOREIGN_MATERIAL_ID = "70000000-0000-0000-0000-000000000099"
NOW = datetime(2026, 7, 10, 10, 0, tzinfo=timezone.utc)


@dataclass(frozen=True)
class FakePrincipal:
    account_id: str
    display_name: str
    assignment_id: str


@dataclass(frozen=True)
class FakeAssignment:
    assignment_id: str
    organization_id: str
    organization_name: str
    store_id: str | None
    store_name: str | None
    role: str


class FakeIdentityRepository:
    def __init__(self) -> None:
        self.assignment_account_ids: list[str] = []
        self.assignment = FakeAssignment(
            assignment_id=ASSIGNMENT_ID,
            organization_id=ORGANIZATION_ID,
            organization_name="荷小悦",
            store_id="first-store",
            store_name="首店",
            role="store_manager",
        )

    def resolve_session(self, raw_token: str) -> FakePrincipal | None:
        return (
            FakePrincipal(ACCOUNT_ID, "测试店长", self.assignment.assignment_id)
            if raw_token == "valid-session"
            else None
        )

    def list_assignments(self, account_id: str) -> list[FakeAssignment]:
        self.assignment_account_ids.append(account_id)
        return [self.assignment]


class FakeMaterialRepository:
    def __init__(self) -> None:
        self.records: dict[tuple[str, str], dict[str, Any]] = {}
        self.calls: list[tuple[str, str]] = []

    def create_material(self, payload: dict[str, Any]) -> dict[str, Any]:
        existing = self.get_by_client_upload_id(
            payload["assignment_id"],
            payload["client_upload_id"],
        )
        if existing is not None:
            return existing
        self.calls.append(("create", payload["assignment_id"]))
        record = {
            **payload,
            "id": payload["material_id"],
            "status": payload.get("status") or "understood",
            "created_at": NOW,
            "updated_at": NOW,
        }
        self.records[(payload["assignment_id"], payload["material_id"])] = record
        return dict(record)

    def get_by_client_upload_id(
        self,
        assignment_id: str,
        client_upload_id: str,
    ) -> dict[str, Any] | None:
        return next(
            (
                dict(record)
                for (owner, _), record in self.records.items()
                if owner == assignment_id
                and record.get("client_upload_id") == client_upload_id
            ),
            None,
        )

    def list_materials(self, assignment_id: str, *, limit: int) -> list[dict[str, Any]]:
        self.calls.append(("list", assignment_id))
        return [
            dict(record)
            for (owner, _), record in self.records.items()
            if owner == assignment_id
        ][:limit]

    def get_material(self, assignment_id: str, material_id: str) -> dict[str, Any] | None:
        self.calls.append(("get", assignment_id))
        record = self.records.get((assignment_id, material_id))
        return dict(record) if record else None

    def update_understanding(
        self,
        assignment_id: str,
        material_id: str,
        *,
        status: str,
        understanding: dict[str, Any],
    ) -> dict[str, Any] | None:
        record = self.records.get((assignment_id, material_id))
        if record is None:
            return None
        record["status"] = status
        record["understanding"] = understanding
        record["updated_at"] = NOW
        return dict(record)


class ASGIClient:
    def __init__(self, app) -> None:
        self.app = app

    def request(self, method: str, url: str, **kwargs):
        async def run():
            transport = httpx.ASGITransport(app=self.app, raise_app_exceptions=False)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                return await client.request(method, url, **kwargs)

        return asyncio.run(run())


def bearer() -> dict[str, str]:
    return {"Authorization": "Bearer valid-session"}


def upload_form(note: str = "") -> dict[str, str]:
    return {"client_upload_id": str(uuid4()), "note": note}


@pytest.fixture
def material_context(tmp_path: Path):
    identity_repository = FakeIdentityRepository()
    material_repository = FakeMaterialRepository()
    understanding_calls: list[dict[str, Any]] = []

    def fake_understanding(**kwargs) -> dict[str, Any]:
        understanding_calls.append(kwargs)
        return {
            "summary": "首店员工接待流程草稿，重点是先问顾客状态，再介绍服务。",
            "document_type": "门店流程资料",
            "source_origin": "internal",
            "authority_level": "working_material",
            "knowledge_scale": "micro",
            "domain": "operations",
            "parse_status": "extracted",
            "confidence": "medium",
            "warnings": [],
            "official_use_allowed": False,
            "use_boundary": "可用于整理候选流程，不能直接作为正式 SOP。",
        }

    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=lambda: identity_repository,
        conversation_repository_factory=lambda: object(),
        material_repository_factory=lambda: material_repository,
        material_understanding_builder=fake_understanding,
    )
    return (
        ASGIClient(app),
        tmp_path,
        identity_repository,
        material_repository,
        understanding_calls,
    )


def test_material_endpoints_require_authentication(material_context) -> None:
    client, _, identity_repository, repository, _ = material_context

    response = client.request("GET", "/api/v1/materials")

    assert response.status_code == 401
    assert identity_repository.assignment_account_ids == []
    assert repository.calls == []


def test_upload_returns_receipt_original_link_and_preliminary_understanding(material_context) -> None:
    client, root, identity_repository, repository, understanding_calls = material_context

    response = client.request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form("这是首店内部流程草稿"),
        files={"file": ("首店接待流程.md", "先问顾客状态，再介绍服务。", "text/markdown")},
    )

    assert response.status_code == 201
    material = response.json()["material"]
    assert material["file_name"] == "首店接待流程.md"
    assert material["receipt"]["status"] == "已收到"
    assert material["original"]["url"] == f"/api/v1/materials/{material['id']}/content"
    assert material["original"]["can_preview"] is True
    assert material["understanding"]["domain"] == "operations"
    assert material["understanding"]["authority_level"] == "working_material"
    assert material["understanding"]["official_use_allowed"] is False
    assert material["understanding"]["use_boundary"] == "可用于整理候选流程，不能直接作为正式 SOP。"
    serialized = response.text
    for forbidden in ("storage_key", "assignment_id", "sha256", str(root), "/root/hxy"):
        assert forbidden not in serialized
    assert identity_repository.assignment_account_ids == [ACCOUNT_ID]
    assert repository.calls == [("create", ASSIGNMENT_ID)]
    assert understanding_calls[0]["role"] == "store_manager"
    assert understanding_calls[0]["note"] == "这是首店内部流程草稿"
    saved_files = [path for path in (root / "data" / "product-materials").rglob("*") if path.is_file()]
    assert len(saved_files) == 1
    assert saved_files[0].read_text(encoding="utf-8") == "先问顾客状态，再介绍服务。"


def test_understanding_failure_keeps_original_and_returns_retriable_receipt(
    tmp_path: Path,
) -> None:
    identity_repository = FakeIdentityRepository()
    material_repository = FakeMaterialRepository()

    def failed_understanding(**_kwargs) -> dict[str, Any]:
        raise RuntimeError("parser unavailable")

    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=lambda: identity_repository,
        conversation_repository_factory=lambda: object(),
        material_repository_factory=lambda: material_repository,
        material_understanding_builder=failed_understanding,
    )

    response = ASGIClient(app).request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form(),
        files={"file": ("门店问题.txt", "原始问题记录".encode(), "text/plain")},
    )

    assert response.status_code == 201
    material = response.json()["material"]
    assert material["receipt"]["status"] == "已收到"
    assert material["status"] == "understanding_failed"
    assert material["understanding"]["official_use_allowed"] is False
    assert material["understanding"]["parse_status"] == "metadata_only"
    assert any("稍后重试" in item for item in material["understanding"]["warnings"])
    stored = [path for path in (tmp_path / "data" / "product-materials").rglob("*") if path.is_file()]
    assert len(stored) == 1
    assert stored[0].read_bytes() == "原始问题记录".encode()


def test_upload_retry_with_same_client_id_returns_one_material(material_context) -> None:
    client, root, _, repository, understanding_calls = material_context
    client_upload_id = str(uuid4())
    request = {
        "headers": bearer(),
        "data": {"client_upload_id": client_upload_id, "note": ""},
        "files": {
            "file": (
                "首店接待流程.md",
                "先问状态，再介绍服务。",
                "text/markdown",
            )
        },
    }

    first = client.request("POST", "/api/v1/materials", **request)
    replay = client.request("POST", "/api/v1/materials", **request)

    assert first.status_code == replay.status_code == 201
    assert first.json()["material"]["id"] == replay.json()["material"]["id"]
    assert len(repository.records) == 1
    assert len(understanding_calls) == 1
    stored = [
        path
        for path in (root / "data" / "product-materials").rglob("*")
        if path.is_file()
    ]
    assert len(stored) == 1


def test_failed_understanding_can_retry_against_the_saved_original(
    tmp_path: Path,
) -> None:
    identity_repository = FakeIdentityRepository()
    material_repository = FakeMaterialRepository()
    attempts = 0

    def recoverable_understanding(**_kwargs) -> dict[str, Any]:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("parser unavailable")
        return {
            "summary": "已重新理解门店问题记录。",
            "document_type": "文档资料",
            "source_origin": "internal",
            "authority_level": "working_material",
            "knowledge_scale": "micro",
            "domain": "operations",
            "parse_status": "extracted",
            "confidence": "medium",
            "warnings": [],
            "official_use_allowed": False,
            "use_boundary": "未经核定不能作为正式口径。",
        }

    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=lambda: identity_repository,
        conversation_repository_factory=lambda: object(),
        material_repository_factory=lambda: material_repository,
        material_understanding_builder=recoverable_understanding,
    )
    client = ASGIClient(app)
    uploaded = client.request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form(),
        files={"file": ("门店问题.txt", "问题记录".encode(), "text/plain")},
    )
    material_id = uploaded.json()["material"]["id"]

    retried = client.request(
        "POST",
        f"/api/v1/materials/{material_id}/understanding",
        headers=bearer(),
    )

    assert uploaded.json()["material"]["status"] == "understanding_failed"
    assert retried.status_code == 200
    assert retried.json()["material"]["id"] == material_id
    assert retried.json()["material"]["status"] == "understood"
    assert retried.json()["material"]["understanding"]["summary"] == (
        "已重新理解门店问题记录。"
    )
    assert attempts == 2
    assert len(material_repository.records) == 1


def test_uploaded_original_can_be_viewed_by_its_assignment(material_context) -> None:
    client, _, _, _, _ = material_context
    uploaded = client.request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form(),
        files={"file": ("门店说明.txt", "原始内容".encode(), "text/plain")},
    )
    material_id = uploaded.json()["material"]["id"]

    response = client.request(
        "GET",
        f"/api/v1/materials/{material_id}/content",
        headers=bearer(),
    )

    assert response.status_code == 200
    assert response.content == "原始内容".encode()
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["cache-control"] == "private, no-store"
    assert quote("门店说明.txt", safe="") in response.headers["content-disposition"]
    assert response.headers["content-security-policy"] == "sandbox; default-src 'none'"


def test_original_rejects_multi_range_requests_before_file_response(
    material_context,
) -> None:
    client, _, _, _, _ = material_context
    uploaded = client.request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form(),
        files={"file": ("门店说明.txt", b"0123456789", "text/plain")},
    )
    material_id = uploaded.json()["material"]["id"]

    response = client.request(
        "GET",
        f"/api/v1/materials/{material_id}/content",
        headers={**bearer(), "Range": "bytes=0-1,2-3,4-5"},
    )

    assert response.status_code == 416


def test_list_and_detail_are_assignment_scoped_and_hide_storage_metadata(material_context) -> None:
    client, _, _, repository, _ = material_context
    uploaded = client.request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form(),
        files={"file": ("产品说明.txt", "清泡调补养".encode(), "text/plain")},
    )
    material_id = uploaded.json()["material"]["id"]
    repository.records[(FOREIGN_ASSIGNMENT_ID, FOREIGN_MATERIAL_ID)] = {
        **repository.records[(ASSIGNMENT_ID, material_id)],
        "id": FOREIGN_MATERIAL_ID,
        "material_id": FOREIGN_MATERIAL_ID,
        "assignment_id": FOREIGN_ASSIGNMENT_ID,
    }

    listed = client.request("GET", "/api/v1/materials", headers=bearer())
    detail = client.request("GET", f"/api/v1/materials/{material_id}", headers=bearer())
    foreign = client.request("GET", f"/api/v1/materials/{FOREIGN_MATERIAL_ID}", headers=bearer())
    foreign_content = client.request(
        "GET",
        f"/api/v1/materials/{FOREIGN_MATERIAL_ID}/content",
        headers=bearer(),
    )

    assert listed.status_code == 200
    assert listed.json()["count"] == 1
    assert listed.json()["items"][0]["id"] == material_id
    assert detail.status_code == 200
    assert detail.json()["material"]["id"] == material_id
    assert foreign.status_code == 404
    assert foreign_content.status_code == 404
    assert foreign.json() == foreign_content.json() == {"detail": "Not Found"}
    assert "storage_key" not in listed.text + detail.text


@pytest.mark.parametrize(
    ("file_name", "content", "expected_status"),
    [
        ("../outside.md", b"content", 400),
        ("malware.exe", b"MZ", 415),
        ("renamed.pdf", b"MZ executable", 415),
        ("empty.txt", b"", 400),
    ],
)
def test_upload_rejects_unsafe_or_misidentified_files(
    material_context,
    file_name: str,
    content: bytes,
    expected_status: int,
) -> None:
    client, root, _, repository, _ = material_context

    response = client.request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form(),
        files={"file": (file_name, content, "application/octet-stream")},
    )

    assert response.status_code == expected_status
    assert repository.calls == []
    material_root = root / "data" / "product-materials"
    assert not material_root.exists() or not any(path.is_file() for path in material_root.rglob("*"))


def test_upload_size_limit_and_note_limit_fail_before_material_is_created(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HXY_MAX_UPLOAD_BYTES", "4")
    repository = FakeMaterialRepository()
    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=FakeIdentityRepository,
        conversation_repository_factory=lambda: object(),
        material_repository_factory=lambda: repository,
    )
    client = ASGIClient(app)

    too_large = client.request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form(),
        files={"file": ("large.txt", b"12345", "text/plain")},
    )
    note_too_long = client.request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form("x" * 1001),
        files={"file": ("note.txt", b"ok", "text/plain")},
    )

    assert too_large.status_code == 413
    assert note_too_long.status_code == 422
    assert repository.calls == []
    material_root = tmp_path / "data" / "product-materials"
    assert not material_root.exists() or not any(path.is_file() for path in material_root.rglob("*"))


def test_declared_oversized_material_request_is_rejected_before_creation(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("HXY_MAX_UPLOAD_BYTES", "4")
    repository = FakeMaterialRepository()
    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=FakeIdentityRepository,
        conversation_repository_factory=lambda: object(),
        material_repository_factory=lambda: repository,
    )

    response = ASGIClient(app).request(
        "POST",
        "/api/v1/materials",
        headers={**bearer(), "Content-Length": "70000"},
        data=upload_form(),
        files={"file": ("small.txt", b"ok", "text/plain")},
    )

    assert response.status_code == 413
    assert repository.calls == []


def test_low_disk_watermark_stops_material_intake(
    tmp_path: Path,
    monkeypatch,
) -> None:
    module = importlib.import_module("apps.api.hxy_product.material_routes")
    monkeypatch.setattr(
        module.shutil,
        "disk_usage",
        lambda _path: type("Usage", (), {"total": 100, "used": 99, "free": 1})(),
    )
    repository = FakeMaterialRepository()
    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=FakeIdentityRepository,
        conversation_repository_factory=lambda: object(),
        material_repository_factory=lambda: repository,
    )

    response = ASGIClient(app).request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form(),
        files={"file": ("small.txt", b"ok", "text/plain")},
    )

    assert response.status_code == 507
    assert repository.calls == []


def test_repository_failure_removes_untracked_file(tmp_path: Path) -> None:
    class FailedRepository(FakeMaterialRepository):
        def create_material(self, payload: dict[str, Any]) -> dict[str, Any]:
            raise RuntimeError("database unavailable")

    app = create_app(
        root_dir=tmp_path,
        repository_factory=lambda: object(),
        product_identity_repository_factory=FakeIdentityRepository,
        conversation_repository_factory=lambda: object(),
        material_repository_factory=FailedRepository,
    )

    response = ASGIClient(app).request(
        "POST",
        "/api/v1/materials",
        headers=bearer(),
        data=upload_form(),
        files={"file": ("orphan.txt", b"content", "text/plain")},
    )

    assert response.status_code == 500
    material_root = tmp_path / "data" / "product-materials"
    assert not material_root.exists() or not any(path.is_file() for path in material_root.rglob("*"))


def test_system_admin_does_not_receive_business_material_access(material_context) -> None:
    client, _, identity_repository, repository, _ = material_context
    identity_repository.assignment = FakeAssignment(
        assignment_id=ASSIGNMENT_ID,
        organization_id=ORGANIZATION_ID,
        organization_name="荷小悦",
        store_id=None,
        store_name=None,
        role="system_admin",
    )

    response = client.request("GET", "/api/v1/materials", headers=bearer())

    assert response.status_code == 403
    assert repository.calls == []


def test_material_access_uses_session_assignment_not_another_owned_role(
    material_context,
) -> None:
    client, _, identity_repository, repository, _ = material_context
    founder_assignment = identity_repository.assignment
    admin_assignment = FakeAssignment(
        assignment_id=FOREIGN_ASSIGNMENT_ID,
        organization_id=ORGANIZATION_ID,
        organization_name="荷小悦",
        store_id=None,
        store_name=None,
        role="system_admin",
    )

    def resolve_admin_session(raw_token: str) -> FakePrincipal | None:
        return (
            FakePrincipal(ACCOUNT_ID, "系统管理员", admin_assignment.assignment_id)
            if raw_token == "valid-session"
            else None
        )

    identity_repository.resolve_session = resolve_admin_session
    identity_repository.list_assignments = lambda _account_id: [
        founder_assignment,
        admin_assignment,
    ]

    response = client.request("GET", "/api/v1/materials", headers=bearer())

    assert response.status_code == 403
    assert repository.calls == []


def test_material_repository_queries_are_assignment_scoped() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    captured: list[tuple[str, tuple[Any, ...]]] = []

    class Result:
        def fetchone(self):
            return None

        def fetchall(self):
            return []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            captured.append((" ".join(sql.split()), params))
            return Result()

    repository.connect = lambda: Connection()

    repository.list_materials(ASSIGNMENT_ID, limit=20)
    repository.get_material(ASSIGNMENT_ID, MATERIAL_ID)

    assert len(captured) == 2
    for sql, params in captured:
        assert "assignment_id = %s::uuid" in sql
        assert params[0] == ASSIGNMENT_ID


def test_material_repository_locks_assignment_before_enforcing_storage_quota() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[str] = []

    class Result:
        def __init__(self, row=None) -> None:
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
            if "FOR UPDATE" in normalized:
                return Result({"assignment_id": ASSIGNMENT_ID})
            if "client_upload_id =" in normalized:
                return Result(None)
            if "COALESCE(SUM(size_bytes), 0)" in normalized:
                return Result({"used_bytes": 100})
            raise AssertionError(normalized)

    repository.connect = lambda: Connection()
    payload = {
        "material_id": MATERIAL_ID,
        "assignment_id": ASSIGNMENT_ID,
        "client_upload_id": str(uuid4()),
        "file_name": "资料.txt",
        "extension": ".txt",
        "media_type": "text/plain",
        "size_bytes": 1,
        "sha256": "a" * 64,
        "storage_key": "assignment/material/资料.txt",
        "note": "",
        "status": "understood",
        "understanding": {},
        "max_assignment_storage_bytes": 100,
    }

    with pytest.raises(module.MaterialStorageQuotaExceeded):
        repository.create_material(payload)

    assert any("FOR UPDATE" in sql for sql in calls)
    assert not any("INSERT INTO hxy_product_materials" in sql for sql in calls)


def test_nginx_material_limit_leaves_room_for_multipart_overhead() -> None:
    config = (ROOT / "ops" / "nginx" / "hxy-knowledge-api.conf").read_text(
        encoding="utf-8"
    )

    assert "client_max_body_size 11m;" in config


def test_rule_understanding_classifies_source_scale_and_boundary(tmp_path: Path) -> None:
    module = importlib.import_module("apps.api.hxy_product.material_understanding")
    source = tmp_path / "荷小悦首店接待SOP草稿.md"
    source.write_text("员工接待时先问顾客当下状态，再介绍门店服务流程。", encoding="utf-8")

    understanding = module.build_material_understanding(
        path=source,
        file_name=source.name,
        media_type="text/markdown",
        note="首店内部工作资料",
        role="store_manager",
    )

    assert understanding["source_origin"] == "internal"
    assert understanding["authority_level"] == "fragment"
    assert understanding["knowledge_scale"] == "micro"
    assert understanding["domain"] == "operations"
    assert understanding["parse_status"] == "extracted"
    assert understanding["official_use_allowed"] is False
    assert "不能作为荷小悦正式口径" in understanding["use_boundary"]


def test_material_migration_is_private_raw_intake_not_formal_knowledge() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "CREATE TABLE IF NOT EXISTS hxy_product_materials" in sql
    assert "material_id UUID PRIMARY KEY" in normalized
    assert "assignment_id UUID NOT NULL REFERENCES hxy_role_assignments(assignment_id)" in normalized
    assert "storage_key TEXT NOT NULL UNIQUE" in normalized
    assert "sha256 CHAR(64) NOT NULL" in normalized
    assert "client_upload_id UUID NOT NULL" in normalized
    assert "UNIQUE (assignment_id, client_upload_id)" in normalized
    assert "understanding_json JSONB NOT NULL" in normalized
    assert "official_use_allowed BOOLEAN NOT NULL DEFAULT FALSE" in normalized
    assert "CHECK (official_use_allowed = FALSE)" in normalized
    assert "CREATE INDEX IF NOT EXISTS" in normalized
    assert "INSERT INTO" not in sql.upper()
