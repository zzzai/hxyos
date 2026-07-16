from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _pending_snapshot() -> dict[str, object]:
    return {
        "server_major": 16,
        "database_matches": True,
        "current_schema": "public",
        "prerequisite_passed": True,
        "authority_columns": [],
        "authority_event_table_present": False,
        "event_columns": [],
        "constraints": [],
        "triggers": [],
        "indexes": [],
        "routines": [],
        "material_count": 12,
        "non_default_material_count": 0,
        "missing_current_event_count": 12,
        "invalid_event_count": 0,
        "git_commit": "a" * 40,
        "commit_valid": True,
        "worktree_clean": True,
    }


def _applied_snapshot() -> dict[str, object]:
    return {
        **_pending_snapshot(),
        "authority_columns": [
            {
                "column_name": "source_origin",
                "data_type": "text",
                "is_nullable": "NO",
                "column_default": "'unknown'::text",
            },
            {
                "column_name": "source_authority",
                "data_type": "text",
                "is_nullable": "NO",
                "column_default": "'external_reference'::text",
            },
            {
                "column_name": "authority_version",
                "data_type": "integer",
                "is_nullable": "NO",
                "column_default": "1",
            },
        ],
        "authority_event_table_present": True,
        "event_columns": [
            ("event_id", "uuid", "NO", "gen_random_uuid()"),
            ("material_id", "uuid", "NO", None),
            ("owner_assignment_id", "uuid", "NO", None),
            ("actor_assignment_id", "uuid", "NO", None),
            ("previous_origin", "text", "YES", None),
            ("new_origin", "text", "NO", None),
            ("previous_authority", "text", "YES", None),
            ("new_authority", "text", "NO", None),
            ("version_no", "integer", "NO", None),
            ("reason", "text", "NO", None),
            ("created_at", "timestamp with time zone", "NO", "now()"),
        ],
        "constraints": [
            ("hxy_product_materials", "c", ("source_origin",)),
            ("hxy_product_materials", "c", ("source_authority",)),
            ("hxy_product_materials", "c", ("authority_version",)),
            (
                "hxy_product_materials",
                "c",
                ("source_origin", "source_authority"),
            ),
            ("hxy_material_authority_events", "p", ("event_id",)),
            ("hxy_material_authority_events", "u", ("material_id", "version_no")),
            ("hxy_material_authority_events", "f", ("material_id",)),
            ("hxy_material_authority_events", "f", ("owner_assignment_id",)),
            ("hxy_material_authority_events", "f", ("actor_assignment_id",)),
            ("hxy_material_authority_events", "c", ("previous_origin",)),
            ("hxy_material_authority_events", "c", ("new_origin",)),
            ("hxy_material_authority_events", "c", ("previous_authority",)),
            ("hxy_material_authority_events", "c", ("new_authority",)),
            ("hxy_material_authority_events", "c", ("version_no",)),
            ("hxy_material_authority_events", "c", ("reason",)),
        ],
        "triggers": [
            (
                "hxy_material_authority_events",
                "trg_hxy_material_authority_events_validate",
                "BEFORE",
                ("INSERT",),
                "ROW",
                "hxy_validate_material_authority_event",
            ),
            (
                "hxy_product_materials",
                "trg_hxy_product_materials_initial_authority",
                "AFTER",
                ("INSERT",),
                "ROW",
                "hxy_record_initial_material_authority",
            ),
            (
                "hxy_product_materials",
                "trg_hxy_product_materials_authority_version_guard",
                "BEFORE",
                ("UPDATE",),
                "ROW",
                "hxy_enforce_material_authority_version",
            ),
            (
                "hxy_material_authority_events",
                "trg_hxy_material_authority_events_append_only",
                "BEFORE",
                ("DELETE", "UPDATE"),
                "ROW",
                "hxy_reject_material_authority_event_mutation",
            ),
            (
                "hxy_material_authority_events",
                "trg_hxy_material_authority_events_no_truncate",
                "BEFORE",
                ("TRUNCATE",),
                "STATEMENT",
                "hxy_reject_material_authority_event_mutation",
            ),
        ],
        "indexes": [
            (
                "hxy_material_authority_events",
                "idx_hxy_material_authority_events_material",
                ("material_id", "version_no desc"),
                False,
            )
        ],
        "routines": [
            "hxy_validate_material_authority_event",
            "hxy_record_initial_material_authority",
            "hxy_enforce_material_authority_version",
            "hxy_reject_material_authority_event_mutation",
        ],
        "non_default_material_count": 0,
        "missing_current_event_count": 0,
        "invalid_event_count": 0,
    }


def test_release_is_checksum_bound_to_only_migration_018() -> None:
    from apps.api.hxy_release.source_authority_release import (
        APPLY_CONFIRMATION,
        SOURCE_AUTHORITY_MIGRATIONS,
        migration_inventory,
    )

    assert APPLY_CONFIRMATION == "APPLY-HXY-018"
    assert SOURCE_AUTHORITY_MIGRATIONS == ("018_hxy_source_authority.sql",)
    inventory = migration_inventory(ROOT, trusted_root=Path("/root/hxy"))
    assert [item["name"] for item in inventory] == list(SOURCE_AUTHORITY_MIGRATIONS)
    assert len(inventory[0]["sha256"]) == 64


def test_preflight_accepts_only_a_clean_pending_state() -> None:
    from apps.api.hxy_release.source_authority_release import evaluate_release_snapshot

    result = evaluate_release_snapshot(_pending_snapshot(), phase="preflight")

    assert result["status"] == "passed"
    assert result["migration_state"] == "pending"


def test_preflight_rejects_partial_or_already_applied_state() -> None:
    from apps.api.hxy_release.source_authority_release import evaluate_release_snapshot

    partial = _pending_snapshot()
    partial["authority_columns"] = [_applied_snapshot()["authority_columns"][0]]

    partial_result = evaluate_release_snapshot(partial, phase="preflight")
    applied_result = evaluate_release_snapshot(_applied_snapshot(), phase="preflight")

    assert partial_result["status"] == "failed"
    assert partial_result["migration_state"] == "partial"
    assert applied_result["status"] == "failed"
    assert applied_result["migration_state"] == "applied"


def test_preflight_requires_an_immutable_clean_git_source() -> None:
    from apps.api.hxy_release.source_authority_release import evaluate_release_snapshot

    dirty = _pending_snapshot()
    dirty["worktree_clean"] = False

    result = evaluate_release_snapshot(dirty, phase="preflight")

    assert result["status"] == "failed"
    assert {
        check["name"]
        for check in result["checks"]
        if check["status"] == "failed"
    } == {"worktree_clean"}


def test_postflight_requires_the_complete_contract_and_default_baseline() -> None:
    from apps.api.hxy_release.source_authority_release import evaluate_release_snapshot

    result = evaluate_release_snapshot(_applied_snapshot(), phase="postflight")

    assert result["status"] == "passed"
    assert result["migration_state"] == "applied"
    assert all(check["status"] == "passed" for check in result["checks"])


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("non_default_material_count", 1),
        ("missing_current_event_count", 1),
        ("invalid_event_count", 1),
    ],
)
def test_postflight_rejects_reclassification_or_incomplete_event_history(
    field: str,
    unsafe_value: int,
) -> None:
    from apps.api.hxy_release.source_authority_release import evaluate_release_snapshot

    snapshot = _applied_snapshot()
    snapshot[field] = unsafe_value

    result = evaluate_release_snapshot(snapshot, phase="postflight")

    assert result["status"] == "failed"
    failed = {check["name"] for check in result["checks"] if check["status"] == "failed"}
    assert "migration_default_baseline" in failed or "authority_event_baseline" in failed


def test_postflight_rejects_a_missing_append_only_trigger() -> None:
    from apps.api.hxy_release.source_authority_release import evaluate_release_snapshot

    snapshot = _applied_snapshot()
    snapshot["triggers"] = [
        item
        for item in snapshot["triggers"]
        if item[1] != "trg_hxy_material_authority_events_append_only"
    ]

    result = evaluate_release_snapshot(snapshot, phase="postflight")

    assert result["status"] == "failed"
    assert any(
        check["name"] == "authority_triggers" and check["status"] == "failed"
        for check in result["checks"]
    )


@pytest.mark.parametrize(
    ("field", "mutate"),
    [
        (
            "triggers",
            lambda rows: [
                {
                    "table_name": item[0],
                    "trigger_name": item[1],
                    "timing": item[2],
                    "events": item[3],
                    "level": item[4],
                    "function_name": item[5],
                    "enabled": "D" if item[1].endswith("append_only") else "O",
                    "predicate": None,
                    "function_schema": "public",
                    "function_source_valid": True,
                    "function_definition_valid": True,
                }
                for item in rows
            ],
        ),
        (
            "constraints",
            lambda rows: [
                {
                    "table_name": item[0],
                    "constraint_type": item[1],
                    "columns": item[2],
                    "validated": True,
                    "semantic_valid": False
                    if item[0] == "hxy_product_materials"
                    and item[2] == ("source_authority",)
                    else True,
                }
                for item in rows
            ],
        ),
        (
            "indexes",
            lambda rows: [
                {
                    "table_name": item[0],
                    "index_name": item[1],
                    "columns": item[2],
                    "is_unique": item[3],
                    "is_valid": False,
                    "predicate": None,
                }
                for item in rows
            ],
        ),
        (
            "routines",
            lambda rows: [
                {
                    "function_name": item,
                    "function_schema": "public",
                    "source_valid": item != "hxy_reject_material_authority_event_mutation",
                    "definition_valid": True,
                }
                for item in rows
            ],
        ),
    ],
)
def test_postflight_rejects_disabled_or_semantically_modified_guards(
    field: str,
    mutate,
) -> None:
    from apps.api.hxy_release.source_authority_release import evaluate_release_snapshot

    snapshot = _applied_snapshot()
    snapshot[field] = mutate(snapshot[field])

    result = evaluate_release_snapshot(snapshot, phase="postflight")

    assert result["status"] == "failed"
    assert result["migration_state"] == "partial"


def test_trigger_parser_preserves_update_of_columns() -> None:
    from apps.api.hxy_release.source_authority_release import _parse_trigger_definition

    definition = (
        "CREATE TRIGGER trg_hxy_product_materials_authority_version_guard "
        "BEFORE UPDATE OF source_origin, source_authority, authority_version "
        "ON public.hxy_product_materials FOR EACH ROW "
        "EXECUTE FUNCTION hxy_enforce_material_authority_version()"
    )

    assert _parse_trigger_definition(definition) == (
        "BEFORE",
        ("UPDATE",),
        "ROW",
        ("authority_version", "source_authority", "source_origin"),
    )


def test_trigger_contract_rejects_update_guard_on_wrong_columns() -> None:
    from apps.api.hxy_release.source_authority_release import _normalized_triggers

    rows = _applied_snapshot()["triggers"]
    materialized = [
        {
            "table_name": item[0],
            "trigger_name": item[1],
            "timing": item[2],
            "events": item[3],
            "level": item[4],
            "function_name": item[5],
            "enabled": "O",
            "predicate": None,
            "function_schema": "public",
            "function_source_valid": True,
            "function_definition_valid": True,
            "update_columns": ("title",)
            if item[1] == "trg_hxy_product_materials_authority_version_guard"
            else (),
        }
        for item in rows
    ]

    assert _normalized_triggers(materialized) != set(rows)


@pytest.mark.parametrize(
    "definition",
    [
        "CHECK (source_authority = ANY (ARRAY['official_internal'::text, "
        "'internal_material'::text, 'external_reference'::text]) OR TRUE)",
        "CHECK (source_authority = ANY (ARRAY['official_internal'::text, "
        "'internal_material'::text, 'external_reference'::text, 'model_approved'::text]))",
    ],
)
def test_constraint_semantics_rejects_weakened_authority_enum(definition: str) -> None:
    from apps.api.hxy_release.source_authority_release import _constraint_semantically_valid

    assert not _constraint_semantically_valid(
        {
            "convalidated": True,
            "source_schema": "public",
            "table_name": "hxy_product_materials",
            "constraint_type": "c",
            "columns": ("source_authority",),
            "definition": definition,
        }
    )


def test_routine_semantics_rejects_guard_markers_hidden_in_comments() -> None:
    from apps.api.hxy_release.source_authority_release import _routine_semantics

    source = """
    BEGIN
      -- RAISE EXCEPTION 'hxy material authority events are append-only';
      RETURN OLD;
    END;
    """
    definition = (
        "CREATE FUNCTION hxy_reject_material_authority_event_mutation() "
        "RETURNS trigger LANGUAGE plpgsql AS $$ " + source + " $$"
    )

    assert _routine_semantics(
        "hxy_reject_material_authority_event_mutation",
        source,
        definition,
    ) == (False, False)


def test_cli_exposes_only_guarded_release_commands() -> None:
    from apps.api.hxy_release.source_authority_release import build_argument_parser

    parser = build_argument_parser()
    for command in ("preflight", "backup", "apply", "postflight"):
        assert parser.parse_args([command]).command == command
    with pytest.raises(SystemExit):
        parser.parse_args(["restore"])

    script = (ROOT / "scripts" / "hxy-source-authority-release.py").read_text(
        encoding="utf-8"
    )
    assert "apps.api.hxy_release.source_authority_release" in script
    assert "htops" not in script.lower()


def test_cli_requires_database_url_without_echoing_secret(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from apps.api.hxy_release import source_authority_release

    monkeypatch.delenv("HXY_DATABASE_URL", raising=False)

    assert source_authority_release.main(["preflight"]) == 2
    assert json.loads(capsys.readouterr().out) == {
        "error": "HXY_DATABASE_URL is required",
        "status": "failed",
    }


def test_cli_redacts_malformed_database_configuration_without_traceback(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from apps.api.hxy_release import source_authority_release

    malformed = "".join(
        ("postgresql://", "founder", ":", "test-value", "@[", "/root/private-release")
    )
    monkeypatch.setenv("HXY_DATABASE_URL", malformed)

    assert source_authority_release.main(["preflight"]) == 2

    output = capsys.readouterr()
    payload = json.loads(output.out)
    assert payload["status"] == "failed"
    assert "test-value" not in output.out
    assert "/root/private-release" not in output.out
    assert output.err == ""


def test_apply_requires_exact_confirmation_and_clean_committed_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from apps.api.hxy_release import source_authority_release
    from apps.api.hxy_release.guarded_migration import ReleaseAuthorizationError

    delegated = False

    def fake_apply(*_args, **_kwargs):
        nonlocal delegated
        delegated = True
        return {"status": "passed"}

    monkeypatch.setattr(source_authority_release, "apply_release_migrations", fake_apply)

    with pytest.raises(ReleaseAuthorizationError, match="exact migration confirmation"):
        source_authority_release.apply_source_authority_migration(
            ROOT,
            "postgresql://localhost/hxy",
            manifest_path=tmp_path / "manifest.json",
            confirmation="APPLY-HXY-018 ",
            git_inspector=lambda _root: {
                "commit_valid": True,
                "worktree_clean": True,
            },
        )

    with pytest.raises(ReleaseAuthorizationError, match="clean worktree"):
        source_authority_release.apply_source_authority_migration(
            ROOT,
            "postgresql://localhost/hxy",
            manifest_path=tmp_path / "manifest.json",
            confirmation="APPLY-HXY-018",
            git_inspector=lambda _root: {
                "commit_valid": True,
                "worktree_clean": False,
            },
        )

    assert delegated is False


class _Result:
    def __init__(self, *, row=None, rows=None):
        self._row = row
        self._rows = rows or []

    def fetchone(self):
        return self._row

    def fetchall(self):
        return self._rows


class _OrphanObjectConnection:
    read_only = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query, *_args):
        marker = str(query)
        if ":server */" in marker:
            return _Result(
                row={
                    "server_version_num": "160000",
                    "database": "hxy",
                    "current_schema": "public",
                }
            )
        if ":material_columns */" in marker:
            return _Result(rows=[])
        if ":event_table */" in marker:
            return _Result(row={"present": False})
        if ":routines */" in marker:
            return _Result(
                rows=[
                    {
                        "function_name": "hxy_reject_material_authority_event_mutation",
                        "function_schema": "public",
                        "function_source": "BEGIN RETURN OLD; END;",
                        "function_definition": "CREATE FUNCTION x() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RETURN OLD; END; $$",
                    }
                ]
            )
        return _Result(rows=[])


def test_preflight_detects_orphan_target_named_objects() -> None:
    from apps.api.hxy_release.source_authority_release import run_preflight

    result = run_preflight(
        ROOT,
        "host=localhost port=5432 dbname=hxy user=tester "
        "passfile=/tmp/hxy-test-passfile",
        connect_factory=lambda _dsn: _OrphanObjectConnection(),
        migration_loader=lambda _root, _name: b"-- migration\n",
        prerequisite_runner=lambda *_args, **_kwargs: {"status": "passed"},
        git_inspector=lambda _root: {
            "commit": "a" * 40,
            "commit_valid": True,
            "worktree_clean": True,
            "detail": "clean",
        },
    )

    assert result["status"] == "failed"
    assert result["migration_state"] == "partial"
