from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import pytest

from apps.api.hxy_release import onboarding_release
from apps.api.hxy_release.onboarding_release import (
    APPLY_CONFIRMATION,
    BACKUP_VERSION,
    ONBOARDING_MIGRATIONS,
    ONBOARDING_RELEASE,
    build_argument_parser,
    migration_inventory,
    run_postflight,
    run_preflight,
)


ROOT = Path(__file__).resolve().parents[1]


def test_release_profile_is_isolated_to_017() -> None:
    assert ONBOARDING_MIGRATIONS == ("017_hxy_governed_onboarding.sql",)
    assert ONBOARDING_RELEASE.release_id == "hxy-governed-onboarding-017"
    assert ONBOARDING_RELEASE.migrations == ONBOARDING_MIGRATIONS
    assert ONBOARDING_RELEASE.confirmation == "APPLY-HXY-017"
    assert ONBOARDING_RELEASE.advisory_lock == "hxy-governed-onboarding-017"
    assert ONBOARDING_RELEASE.dump_filename == "hxy-before-onboarding.dump"
    assert BACKUP_VERSION == "hxy-governed-onboarding-backup.v1"
    assert APPLY_CONFIRMATION == "APPLY-HXY-017"

    inventory = migration_inventory(ROOT, trusted_root=Path("/root/hxy"))

    assert inventory == [
        {
            "name": "017_hxy_governed_onboarding.sql",
            "sha256": hashlib.sha256(
                (ROOT / "data/migrations/017_hxy_governed_onboarding.sql").read_bytes()
            ).hexdigest(),
        }
    ]


def test_inventory_hashes_supplied_head_blob_bytes() -> None:
    blob = b"-- exact committed migration bytes\n"

    inventory = migration_inventory(
        ROOT,
        trusted_root=Path("/root/hxy"),
        migration_loader=lambda _root, name: (
            blob
            if name == "017_hxy_governed_onboarding.sql"
            else pytest.fail(f"unexpected migration: {name}")
        ),
    )

    assert inventory == [
        {
            "name": "017_hxy_governed_onboarding.sql",
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
    ]


def test_cli_exposes_only_guarded_release_commands() -> None:
    parser = build_argument_parser()

    for command in ("preflight", "backup", "apply", "postflight"):
        assert parser.parse_args([command]).command == command
    for rejected in ("restore", "migrate", "seed", "publish"):
        with pytest.raises(SystemExit):
            parser.parse_args([rejected])

    script = (ROOT / "scripts/hxy-governed-onboarding-release.py").read_text(
        encoding="utf-8"
    )
    assert "apps.api.hxy_release.onboarding_release" in script
    assert "htops" not in script.lower()


def test_release_module_exports_guarded_operations() -> None:
    assert callable(onboarding_release.run_preflight)
    assert callable(onboarding_release.create_backup)
    assert callable(onboarding_release.apply_onboarding_migration)
    assert callable(onboarding_release.run_postflight)
    assert callable(onboarding_release.main)


PREREQUISITE = {
    "status": "passed",
    "database": {
        "host": "127.0.0.1",
        "port": "55433",
        "database": "hxy_release_test",
        "user": "hxy_app",
    },
    "server_major": 16,
}


class FakeResult:
    def __init__(
        self,
        *,
        row: dict[str, Any] | None = None,
        rows: list[dict[str, Any]] | None = None,
    ) -> None:
        self.row = row
        self.rows = rows or []

    def fetchone(self):
        return self.row

    def fetchall(self):
        return self.rows


class FakeOnboardingInspectionConnection:
    def __init__(self) -> None:
        self.read_only = False
        self.queries: list[str] = []
        self.omit: set[str] = set()
        self.overrides: dict[str, dict[str, Any]] = {}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def _filtered(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        filtered: list[dict[str, Any]] = []
        for source in rows:
            marker = str(source["marker"])
            if marker in self.omit:
                continue
            row = dict(source)
            row.update(self.overrides.get(marker, {}))
            filtered.append(row)
        return filtered

    def execute(self, sql: str, _params=None):
        assert self.read_only is True
        normalized = " ".join(sql.split())
        self.queries.append(normalized)
        if "hxy_onboarding_release:schema" in sql:
            return FakeResult(row={"current_schema": "public"})
        if "hxy_onboarding_release:relations" in sql:
            return FakeResult(
                rows=[
                    {"name": name}
                    for name in (
                        "hxy_member_invite_events",
                        "hxy_member_invites",
                    )
                    if f"relation:{name}" not in self.omit
                ]
            )
        if "hxy_onboarding_release:columns" in sql:
            return FakeResult(rows=self._filtered(_column_rows()))
        if "hxy_onboarding_release:constraints" in sql:
            return FakeResult(rows=self._filtered(_constraint_rows()))
        if "hxy_onboarding_release:triggers" in sql:
            return FakeResult(rows=self._filtered(_trigger_rows()))
        if "hxy_onboarding_release:indexes" in sql:
            return FakeResult(rows=self._filtered(_index_rows()))
        raise AssertionError(normalized)


def _column_rows() -> list[dict[str, Any]]:
    specifications = {
        "hxy_member_invites": (
            ("invite_id", "uuid", "NO", "gen_random_uuid()"),
            ("organization_id", "uuid", "NO", None),
            ("store_id", "text", "NO", None),
            ("role", "text", "NO", None),
            ("display_name", "text", "NO", None),
            ("token_hash", "text", "NO", None),
            ("created_by_assignment_id", "uuid", "NO", None),
            ("status", "text", "NO", "'pending'::text"),
            ("expires_at", "timestamp with time zone", "NO", None),
            ("redeemed_account_id", "uuid", "YES", None),
            ("redeemed_assignment_id", "uuid", "YES", None),
            ("redeemed_at", "timestamp with time zone", "YES", None),
            ("revoked_at", "timestamp with time zone", "YES", None),
            ("created_at", "timestamp with time zone", "NO", "now()"),
            ("updated_at", "timestamp with time zone", "NO", "now()"),
        ),
        "hxy_member_invite_events": (
            ("event_id", "uuid", "NO", "gen_random_uuid()"),
            ("organization_id", "uuid", "NO", None),
            ("store_id", "text", "NO", None),
            ("invite_id", "uuid", "YES", None),
            ("actor_assignment_id", "uuid", "NO", None),
            ("subject_assignment_id", "uuid", "YES", None),
            ("event_type", "text", "NO", None),
            ("payload", "jsonb", "NO", "'{}'::jsonb"),
            ("created_at", "timestamp with time zone", "NO", "now()"),
        ),
    }
    return [
        {
            "marker": f"column:{table}.{name}",
            "table_schema": "public",
            "table_name": table,
            "column_name": name,
            "data_type": data_type,
            "is_nullable": nullable,
            "column_default": default,
        }
        for table, columns in specifications.items()
        for name, data_type, nullable, default in columns
    ]


def _constraint_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    def local(
        marker: str,
        constraint_type: str,
        table: str,
        columns: tuple[str, ...],
        expression: str | None = None,
    ) -> None:
        rows.append(
            {
                "marker": f"constraint:{marker}",
                "constraint_name": marker,
                "constraint_type": constraint_type,
                "source_schema": "public",
                "source_table": table,
                "source_columns": list(columns),
                "target_schema": "",
                "target_table": "",
                "target_columns": [],
                "convalidated": True,
                "confdeltype": " ",
                "check_expression": expression,
            }
        )

    def foreign(
        marker: str,
        table: str,
        columns: tuple[str, ...],
        target: str,
        target_columns: tuple[str, ...],
    ) -> None:
        rows.append(
            {
                "marker": f"constraint:{marker}",
                "constraint_name": marker,
                "constraint_type": "f",
                "source_schema": "public",
                "source_table": table,
                "source_columns": list(columns),
                "target_schema": "public",
                "target_table": target,
                "target_columns": list(target_columns),
                "convalidated": True,
                "confdeltype": "r",
                "check_expression": None,
            }
        )

    local("hxy_member_invites_pkey", "p", "hxy_member_invites", ("invite_id",))
    local(
        "uq_hxy_member_invites_token_hash",
        "u",
        "hxy_member_invites",
        ("token_hash",),
    )
    local(
        "hxy_member_invite_events_pkey",
        "p",
        "hxy_member_invite_events",
        ("event_id",),
    )
    for marker, table, expression in (
        (
            "invites_role",
            "hxy_member_invites",
            "role = ANY (ARRAY['store_manager'::text, 'store_employee'::text])",
        ),
        (
            "invites_display_name",
            "hxy_member_invites",
            "char_length(btrim(display_name)) >= 1 AND char_length(btrim(display_name)) <= 80",
        ),
        (
            "invites_token_hash",
            "hxy_member_invites",
            "token_hash ~ '^[0-9a-f]{64}$'::text",
        ),
        (
            "invites_status",
            "hxy_member_invites",
            "status = ANY (ARRAY['pending'::text, 'redeemed'::text, 'revoked'::text])",
        ),
        (
            "chk_hxy_member_invites_expiry",
            "hxy_member_invites",
            "expires_at > created_at",
        ),
        (
            "chk_hxy_member_invites_state_shape",
            "hxy_member_invites",
            "status = 'pending' AND redeemed_account_id IS NULL AND redeemed_assignment_id IS NULL AND redeemed_at IS NULL AND revoked_at IS NULL OR status = 'redeemed' AND redeemed_account_id IS NOT NULL AND redeemed_assignment_id IS NOT NULL AND redeemed_at IS NOT NULL AND revoked_at IS NULL OR status = 'revoked' AND redeemed_account_id IS NULL AND redeemed_assignment_id IS NULL AND redeemed_at IS NULL AND revoked_at IS NOT NULL",
        ),
        (
            "events_type",
            "hxy_member_invite_events",
            "event_type = ANY (ARRAY['created'::text, 'redeemed'::text, 'revoked'::text, 'member_deactivated'::text])",
        ),
        (
            "events_payload",
            "hxy_member_invite_events",
            "payload = '{}'::jsonb",
        ),
        (
            "chk_hxy_member_invite_events_subject",
            "hxy_member_invite_events",
            "event_type = ANY (ARRAY['created'::text, 'revoked'::text]) AND invite_id IS NOT NULL AND subject_assignment_id IS NULL OR event_type = 'redeemed' AND invite_id IS NOT NULL AND subject_assignment_id IS NOT NULL OR event_type = 'member_deactivated' AND invite_id IS NULL AND subject_assignment_id IS NOT NULL",
        ),
    ):
        local(marker, "c", table, (), expression)

    for args in (
        ("invites_org", "hxy_member_invites", ("organization_id",), "hxy_organizations", ("organization_id",)),
        ("invites_store", "hxy_member_invites", ("store_id",), "stores", ("store_id",)),
        ("invites_redeemed_account", "hxy_member_invites", ("redeemed_account_id",), "staff_accounts", ("id",)),
        ("invites_redeemed_assignment", "hxy_member_invites", ("redeemed_assignment_id",), "hxy_role_assignments", ("assignment_id",)),
        ("fk_hxy_member_invites_organization_store", "hxy_member_invites", ("organization_id", "store_id"), "hxy_organization_stores", ("organization_id", "store_id")),
        ("fk_hxy_member_invites_creator_organization", "hxy_member_invites", ("organization_id", "created_by_assignment_id"), "hxy_role_assignments", ("organization_id", "assignment_id")),
        ("fk_hxy_member_invites_redeemed_identity_store", "hxy_member_invites", ("organization_id", "store_id", "redeemed_assignment_id", "redeemed_account_id"), "hxy_role_assignments", ("organization_id", "store_id", "assignment_id", "account_id")),
        ("events_org", "hxy_member_invite_events", ("organization_id",), "hxy_organizations", ("organization_id",)),
        ("events_store", "hxy_member_invite_events", ("store_id",), "stores", ("store_id",)),
        ("fk_hxy_member_invite_events_organization_store", "hxy_member_invite_events", ("organization_id", "store_id"), "hxy_organization_stores", ("organization_id", "store_id")),
        ("fk_hxy_member_invite_events_invite_store", "hxy_member_invite_events", ("organization_id", "store_id", "invite_id"), "hxy_member_invites", ("organization_id", "store_id", "invite_id")),
        ("fk_hxy_member_invite_events_actor_organization", "hxy_member_invite_events", ("organization_id", "actor_assignment_id"), "hxy_role_assignments", ("organization_id", "assignment_id")),
        ("fk_hxy_member_invite_events_subject_store", "hxy_member_invite_events", ("organization_id", "store_id", "subject_assignment_id"), "hxy_role_assignments", ("organization_id", "store_id", "assignment_id")),
    ):
        foreign(*args)
    return rows


def _trigger_rows() -> list[dict[str, Any]]:
    function_source = (
        "BEGIN RAISE EXCEPTION 'hxy_member_invite_events is append-only'; END;"
    )
    return [
        {
            "marker": "trigger:append_only",
            "table_schema": "public",
            "table_name": "hxy_member_invite_events",
            "trigger_name": "trg_hxy_member_invite_events_append_only",
            "tgenabled": "O",
            "tgqual": None,
            "function_schema": "public",
            "function_name": "hxy_reject_member_invite_event_mutation",
            "prosrc": function_source,
            "function_definition": f"CREATE FUNCTION x() RETURNS trigger LANGUAGE plpgsql AS $$ {function_source} $$",
            "definition": "CREATE TRIGGER trg_hxy_member_invite_events_append_only BEFORE UPDATE OR DELETE ON public.hxy_member_invite_events FOR EACH ROW EXECUTE FUNCTION hxy_reject_member_invite_event_mutation()",
        },
        {
            "marker": "trigger:no_truncate",
            "table_schema": "public",
            "table_name": "hxy_member_invite_events",
            "trigger_name": "trg_hxy_member_invite_events_no_truncate",
            "tgenabled": "O",
            "tgqual": None,
            "function_schema": "public",
            "function_name": "hxy_reject_member_invite_event_mutation",
            "prosrc": function_source,
            "function_definition": f"CREATE FUNCTION x() RETURNS trigger LANGUAGE plpgsql AS $$ {function_source} $$",
            "definition": "CREATE TRIGGER trg_hxy_member_invite_events_no_truncate BEFORE TRUNCATE ON public.hxy_member_invite_events FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_member_invite_event_mutation()",
        },
    ]


def _index_rows() -> list[dict[str, Any]]:
    specifications = (
        ("hxy_role_assignments", "uq_hxy_role_assignments_onboarding_identity", ("organization_id", "store_id", "assignment_id", "account_id"), True, None),
        ("hxy_member_invites", "uq_hxy_member_invites_scope_invite", ("organization_id", "store_id", "invite_id"), True, None),
        ("hxy_member_invites", "idx_hxy_member_invites_expires", ("expires_at",), False, None),
        ("hxy_member_invites", "idx_hxy_member_invites_scope_status", ("organization_id", "store_id", "status", "created_at desc"), False, None),
        ("hxy_member_invite_events", "idx_hxy_member_invite_events_invite_created", ("invite_id", "created_at", "event_id"), False, "invite_id IS NOT NULL"),
        ("hxy_member_invite_events", "idx_hxy_member_invite_events_scope_created", ("organization_id", "store_id", "created_at desc"), False, None),
    )
    return [
        {
            "marker": f"index:{name}",
            "table_schema": "public",
            "table_name": table,
            "index_name": name,
            "index_definition": (
                f"CREATE {'UNIQUE ' if unique else ''}INDEX {name} ON public.{table} "
                f"USING btree ({', '.join(columns)})"
            ),
            "indisvalid": True,
            "indisunique": unique,
            "predicate": predicate,
        }
        for table, name, columns, unique, predicate in specifications
    ]


def _prerequisite(_root: Path, _database_url: str, **_kwargs: Any) -> dict[str, Any]:
    return dict(PREREQUISITE)


def test_postflight_validates_complete_read_only_schema_contract() -> None:
    connection = FakeOnboardingInspectionConnection()

    result = run_postflight(
        ROOT,
        "test-dsn",
        connect_factory=lambda _dsn: connection,
        prerequisite_runner=_prerequisite,
        trusted_root=Path("/root/hxy"),
        migration_loader=lambda _root, _name: b"-- migration\n",
    )

    assert result["status"] == "passed"
    assert result["phase"] == "postflight"
    assert connection.read_only is True
    assert len(connection.queries) == 6
    assert {item["status"] for item in result["checks"]} == {"passed"}
    serialized = repr(result).lower()
    for forbidden in ("token_hash_value", "display_name_value", "cookie", "test-dsn"):
        assert forbidden not in serialized


@pytest.mark.parametrize(
    ("marker", "override"),
    (
        ("relation:hxy_member_invites", None),
        ("column:hxy_member_invites.token_hash", {"data_type": "bytea"}),
        ("constraint:fk_hxy_member_invites_organization_store", {"convalidated": False}),
        ("constraint:fk_hxy_member_invite_events_subject_store", {"confdeltype": "c"}),
        ("constraint:invites_token_hash", {"check_expression": "token_hash <> ''"}),
        ("trigger:append_only", {"tgenabled": "D"}),
        ("trigger:no_truncate", {"definition": "CREATE TRIGGER wrong AFTER TRUNCATE ON x FOR EACH STATEMENT EXECUTE FUNCTION y()"}),
        ("index:uq_hxy_role_assignments_onboarding_identity", {"indisunique": False}),
        ("index:idx_hxy_member_invites_scope_status", {"indisvalid": False}),
    ),
)
def test_postflight_fails_closed_for_malformed_contract(
    marker: str,
    override: dict[str, Any] | None,
) -> None:
    connection = FakeOnboardingInspectionConnection()
    if override is None:
        connection.omit.add(marker)
    else:
        connection.overrides[marker] = override

    result = run_postflight(
        ROOT,
        "test-dsn",
        connect_factory=lambda _dsn: connection,
        prerequisite_runner=_prerequisite,
        trusted_root=Path("/root/hxy"),
        migration_loader=lambda _root, _name: b"-- migration\n",
    )

    assert result["status"] == "failed"
    assert "failed" in {item["status"] for item in result["checks"]}


def test_preflight_requires_prerequisite_postgres_16_clean_git_and_017() -> None:
    passed = run_preflight(
        ROOT,
        "test-dsn",
        prerequisite_runner=_prerequisite,
        git_inspector=lambda _root: {
            "status": "passed",
            "commit": "a" * 40,
            "commit_valid": True,
            "worktree_clean": True,
            "detail": "clean",
        },
        trusted_root=Path("/root/hxy"),
        migration_loader=lambda _root, _name: b"-- migration\n",
    )
    assert passed["status"] == "passed"
    assert passed["server_major"] == 16

    wrong_postgres = run_preflight(
        ROOT,
        "test-dsn",
        prerequisite_runner=lambda *_args, **_kwargs: {
            **PREREQUISITE,
            "server_major": 15,
        },
        git_inspector=lambda _root: {
            "status": "passed",
            "commit": "a" * 40,
            "commit_valid": True,
            "worktree_clean": True,
            "detail": "clean",
        },
        trusted_root=Path("/root/hxy"),
        migration_loader=lambda _root, _name: b"-- migration\n",
    )
    assert wrong_postgres["status"] == "failed"
