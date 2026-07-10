from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from apps.api.hxy_release.activation_release import (
    ACTIVATION_MIGRATIONS,
    ReleaseBoundaryError,
    build_argument_parser,
    database_identity,
    migration_inventory,
    render_result,
    run_postflight,
    run_preflight,
    validate_hxy_boundary,
)


ROOT = Path(__file__).resolve().parents[1]


def test_activation_release_allows_only_migrations_009_through_014() -> None:
    assert ACTIVATION_MIGRATIONS == (
        "009_hxy_product_identity.sql",
        "010_hxy_product_conversations.sql",
        "011_hxy_product_materials.sql",
        "012_hxy_assignment_sessions.sql",
        "013_hxy_material_intake_jobs.sql",
        "014_hxy_knowledge_activation.sql",
    )

    inventory = migration_inventory(ROOT)

    assert [item["name"] for item in inventory] == list(ACTIVATION_MIGRATIONS)
    assert all(len(item["sha256"]) == 64 for item in inventory)
    assert all(set(item) == {"name", "sha256"} for item in inventory)


def test_database_identity_omits_password_and_complete_dsn() -> None:
    password = "release-secret-value"
    dsn = (
        "host=127.0.0.1 port=55433 dbname=hxy_release_test "
        f"user=hxy_app password={password}"
    )

    identity = database_identity(dsn)
    rendered = json.dumps(identity, ensure_ascii=False)

    assert identity == {
        "host": "127.0.0.1",
        "port": "55433",
        "database": "hxy_release_test",
        "user": "hxy_app",
    }
    assert password not in rendered
    assert "password" not in rendered.lower()
    assert dsn not in rendered


def test_release_boundary_rejects_htops_database_or_root() -> None:
    identity = {
        "host": "127.0.0.1",
        "port": "55433",
        "database": "hxy_release_test",
        "user": "hxy_app",
    }

    validate_hxy_boundary(ROOT, identity)

    with pytest.raises(ReleaseBoundaryError, match="database"):
        validate_hxy_boundary(ROOT, identity | {"database": "htops"})
    with pytest.raises(ReleaseBoundaryError, match="root"):
        validate_hxy_boundary(Path("/root/htops"), identity)


def test_release_result_redacts_secrets_and_bounds_nested_values() -> None:
    password = "release-secret-value"
    full_dsn = f"host=127.0.0.1 dbname=hxy user=hxy_app password={password}"

    rendered = render_result(
        {
            "status": "passed",
            "detail": full_dsn,
            "nested": {"token": password, "long": "x" * 2000},
        },
        sensitive_values=(password, full_dsn),
    )

    assert password not in rendered
    assert full_dsn not in rendered
    assert "[redacted]" in rendered
    assert len(json.loads(rendered)["nested"]["long"]) <= 500


def test_activation_release_cli_exposes_only_guarded_commands() -> None:
    parser = build_argument_parser()

    for command in ("preflight", "backup", "apply", "postflight"):
        assert parser.parse_args([command]).command == command

    with pytest.raises(SystemExit):
        parser.parse_args(["restore"])

    script = (ROOT / "scripts" / "hxy-activation-release.py").read_text(encoding="utf-8")
    assert "apps.api.hxy_release.activation_release" in script
    assert "htops" not in script.lower()


class FakeResult:
    def __init__(self, *, row: dict[str, Any] | None = None, rows=None) -> None:
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeInspectionConnection:
    def __init__(self, *, activated: bool) -> None:
        self.activated = activated
        self.read_only = False
        self.queries: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, sql: str, _params=None):
        assert self.read_only is True
        normalized = " ".join(sql.split())
        self.queries.append(normalized)
        if "hxy_release:server" in sql:
            return FakeResult(
                row={
                    "server_version_num": "160013",
                    "database": "hxy_release_test",
                    "user": "hxy_app",
                }
            )
        if "hxy_release:relations" in sql:
            baseline = {"staff_accounts", "stores"}
            activated = {
                "hxy_organizations",
                "hxy_role_assignments",
                "hxy_assignment_sessions",
                "hxy_product_conversations",
                "hxy_product_messages",
                "hxy_product_materials",
                "hxy_material_parser_jobs",
                "hxy_material_artifacts",
                "hxy_material_chunks",
                "hxy_product_answer_traces",
            }
            names = baseline | (activated if self.activated else set())
            return FakeResult(rows=[{"name": name} for name in sorted(names)])
        if "hxy_release:constraints" in sql:
            return FakeResult(
                rows=[
                    {
                        "table_name": "hxy_product_materials",
                        "constraint_type": "c",
                        "definition": "CHECK ((official_use_allowed = false))",
                    },
                    {
                        "table_name": "hxy_material_artifacts",
                        "constraint_type": "c",
                        "definition": "CHECK ((official_use_allowed = false))",
                    },
                    {
                        "table_name": "hxy_material_chunks",
                        "constraint_type": "c",
                        "definition": "CHECK ((official_use_allowed = false))",
                    },
                    {
                        "table_name": "hxy_material_chunks",
                        "constraint_type": "f",
                        "definition": (
                            "FOREIGN KEY (assignment_id, material_id) "
                            "REFERENCES hxy_product_materials(assignment_id, material_id)"
                        ),
                    },
                    {
                        "table_name": "hxy_product_answer_traces",
                        "constraint_type": "u",
                        "definition": "UNIQUE (assistant_message_id)",
                    },
                ]
            )
        if "hxy_release:indexes" in sql:
            return FakeResult(
                rows=[{"index_name": "idx_hxy_material_chunks_content_trgm"}]
            )
        raise AssertionError(normalized)


def _inspection_factory(connection: FakeInspectionConnection):
    def connect(_database_url: str):
        return connection

    return connect


def _assert_queries_are_read_only(queries: list[str]) -> None:
    forbidden = re.compile(r"\b(INSERT|UPDATE|DELETE|ALTER|CREATE|DROP|TRUNCATE)\b", re.I)
    assert queries
    assert all(forbidden.search(query) is None for query in queries)


def test_preflight_is_read_only_and_reports_activation_as_pending() -> None:
    connection = FakeInspectionConnection(activated=False)
    result = run_preflight(
        ROOT,
        "host=127.0.0.1 port=55433 dbname=hxy_release_test user=hxy_app",
        connect_factory=_inspection_factory(connection),
    )

    assert result["status"] == "passed"
    assert result["phase"] == "preflight"
    assert result["database"]["database"] == "hxy_release_test"
    assert result["server_major"] == 16
    assert result["pending_tables"] == [
        "hxy_assignment_sessions",
        "hxy_material_artifacts",
        "hxy_material_chunks",
        "hxy_material_parser_jobs",
        "hxy_organizations",
        "hxy_product_answer_traces",
        "hxy_product_conversations",
        "hxy_product_materials",
        "hxy_product_messages",
        "hxy_role_assignments",
    ]
    _assert_queries_are_read_only(connection.queries)


def test_preflight_fails_for_wrong_postgres_major_or_missing_baseline() -> None:
    connection = FakeInspectionConnection(activated=False)

    original_execute = connection.execute

    def execute(sql: str, params=None):
        result = original_execute(sql, params)
        if "hxy_release:server" in sql:
            result.row["server_version_num"] = "150009"
        if "hxy_release:relations" in sql:
            result.rows = [row for row in result.rows if row["name"] != "stores"]
        return result

    connection.execute = execute
    result = run_preflight(
        ROOT,
        "host=127.0.0.1 dbname=hxy_release_test user=hxy_app",
        connect_factory=_inspection_factory(connection),
    )

    assert result["status"] == "failed"
    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert failed == {"postgres_major", "baseline_tables"}
    _assert_queries_are_read_only(connection.queries)


def test_postflight_requires_governed_activation_schema() -> None:
    connection = FakeInspectionConnection(activated=True)
    result = run_postflight(
        ROOT,
        "host=127.0.0.1 port=55433 dbname=hxy_release_test user=hxy_app",
        connect_factory=_inspection_factory(connection),
    )

    assert result["status"] == "passed"
    assert result["phase"] == "postflight"
    assert result["pending_tables"] == []
    assert all(item["status"] == "passed" for item in result["checks"])
    _assert_queries_are_read_only(connection.queries)


def test_postflight_fails_without_private_chunk_governance() -> None:
    connection = FakeInspectionConnection(activated=True)
    original_execute = connection.execute

    def execute(sql: str, params=None):
        result = original_execute(sql, params)
        if "hxy_release:constraints" in sql:
            result.rows = [
                row
                for row in result.rows
                if not (
                    row["table_name"] == "hxy_material_chunks"
                    and row["constraint_type"] == "c"
                )
            ]
        return result

    connection.execute = execute
    result = run_postflight(
        ROOT,
        "host=127.0.0.1 dbname=hxy_release_test user=hxy_app",
        connect_factory=_inspection_factory(connection),
    )

    assert result["status"] == "failed"
    failed = {item["name"] for item in result["checks"] if item["status"] == "failed"}
    assert "private_chunk_non_authority" in failed
