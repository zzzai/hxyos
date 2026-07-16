from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _pending_snapshot() -> dict[str, object]:
    return {
        "server_major": 16,
        "database_matches": True,
        "current_schema": "public",
        "prerequisite_passed": True,
        "migration_count": 1,
        "authority_columns": [],
        "event_table_present": False,
        "event_columns": [],
        "constraints": [],
        "triggers": [],
        "indexes": [],
        "routines": [],
        "asset_count": 141,
        "unsafe_baseline_asset_count": 0,
        "missing_baseline_event_count": 141,
        "invalid_release_event_count": 0,
        "commit_valid": True,
        "worktree_clean": True,
    }


def _applied_snapshot() -> dict[str, object]:
    return {
        **_pending_snapshot(),
        "authority_columns": [
            ("source_origin", "text", "NO", "'unknown'::text"),
            ("source_authority", "text", "NO", "'external_reference'::text"),
            ("authority_version", "integer", "NO", "1"),
            ("authority_organization_id", "uuid", "YES", None),
        ],
        "event_table_present": True,
        "event_columns": [
            ("event_id", "uuid", "NO", "gen_random_uuid()"),
            ("asset_id", "text", "NO", None),
            ("event_type", "text", "NO", None),
            ("organization_id", "uuid", "YES", None),
            ("actor_assignment_id", "uuid", "YES", None),
            ("previous_origin", "text", "YES", None),
            ("new_origin", "text", "NO", None),
            ("previous_authority", "text", "YES", None),
            ("new_authority", "text", "NO", None),
            ("previous_version", "integer", "YES", None),
            ("version_no", "integer", "NO", None),
            ("reason", "text", "NO", None),
            ("created_at", "timestamp with time zone", "NO", "now()"),
        ],
        "constraints": [
            ("hxy_knowledge_assets", "p", ("asset_id",)),
            ("hxy_knowledge_assets", "c", ("source_origin",)),
            ("hxy_knowledge_assets", "c", ("source_authority",)),
            ("hxy_knowledge_assets", "c", ("authority_version",)),
            ("hxy_knowledge_assets", "f", ("authority_organization_id",)),
            ("hxy_knowledge_assets", "c", ("source_origin", "source_authority")),
            ("hxy_knowledge_asset_authority_events", "p", ("event_id",)),
            ("hxy_knowledge_asset_authority_events", "u", ("asset_id", "version_no")),
            ("hxy_knowledge_asset_authority_events", "f", ("asset_id",)),
            ("hxy_knowledge_asset_authority_events", "f", ("organization_id",)),
            ("hxy_knowledge_asset_authority_events", "f", ("actor_assignment_id",)),
            ("hxy_knowledge_asset_authority_events", "c", ("event_type",)),
            ("hxy_knowledge_asset_authority_events", "c", ("previous_origin",)),
            ("hxy_knowledge_asset_authority_events", "c", ("new_origin",)),
            ("hxy_knowledge_asset_authority_events", "c", ("previous_authority",)),
            ("hxy_knowledge_asset_authority_events", "c", ("new_authority",)),
            ("hxy_knowledge_asset_authority_events", "c", ("previous_version",)),
            ("hxy_knowledge_asset_authority_events", "c", ("version_no",)),
            ("hxy_knowledge_asset_authority_events", "c", ("reason",)),
            (
                "hxy_knowledge_asset_authority_events",
                "c",
                (
                    "event_type",
                    "organization_id",
                    "actor_assignment_id",
                    "previous_origin",
                    "previous_authority",
                    "previous_version",
                    "new_origin",
                    "new_authority",
                    "version_no",
                ),
            ),
        ],
        "triggers": [
            (
                "hxy_knowledge_asset_authority_events",
                "trg_hxy_knowledge_asset_authority_events_validate",
                "BEFORE",
                ("INSERT",),
                "ROW",
                "hxy_validate_knowledge_asset_authority_event",
            ),
            (
                "hxy_knowledge_assets",
                "trg_hxy_knowledge_assets_initial_authority",
                "AFTER",
                ("INSERT",),
                "ROW",
                "hxy_record_initial_knowledge_asset_authority",
            ),
            (
                "hxy_knowledge_assets",
                "trg_hxy_knowledge_assets_authority_version_guard",
                "BEFORE",
                ("UPDATE",),
                "ROW",
                "hxy_enforce_knowledge_asset_authority_version",
            ),
            (
                "hxy_knowledge_asset_authority_events",
                "trg_hxy_knowledge_asset_authority_events_append_only",
                "BEFORE",
                ("DELETE", "UPDATE"),
                "ROW",
                "hxy_reject_knowledge_asset_authority_event_mutation",
            ),
            (
                "hxy_knowledge_asset_authority_events",
                "trg_hxy_knowledge_asset_authority_events_no_truncate",
                "BEFORE",
                ("TRUNCATE",),
                "STATEMENT",
                "hxy_reject_knowledge_asset_authority_event_mutation",
            ),
        ],
        "indexes": [
            (
                "hxy_knowledge_asset_authority_events",
                "idx_hxy_knowledge_asset_authority_events_asset",
                ("asset_id", "version_no desc"),
                False,
            )
        ],
        "routines": [
            "hxy_validate_knowledge_asset_authority_event",
            "hxy_record_initial_knowledge_asset_authority",
            "hxy_enforce_knowledge_asset_authority_version",
            "hxy_reject_knowledge_asset_authority_event_mutation",
        ],
        "unsafe_baseline_asset_count": 0,
        "missing_baseline_event_count": 0,
        "invalid_release_event_count": 0,
    }


def test_release_is_bound_only_to_migration_019_and_new_confirmation() -> None:
    from apps.api.hxy_release.global_source_authority_release import (
        APPLY_CONFIRMATION,
        GLOBAL_SOURCE_AUTHORITY_MIGRATIONS,
        TARGET_RELATIONS,
        migration_inventory,
    )

    assert APPLY_CONFIRMATION == "APPLY-HXY-019"
    assert APPLY_CONFIRMATION != "APPLY-HXY-018"
    assert GLOBAL_SOURCE_AUTHORITY_MIGRATIONS == ("019_hxy_global_source_authority.sql",)
    assert TARGET_RELATIONS == (
        "hxy_knowledge_assets",
        "hxy_knowledge_asset_authority_events",
    )
    inventory = migration_inventory(ROOT, trusted_root=Path("/root/hxy"))
    assert [item["name"] for item in inventory] == list(GLOBAL_SOURCE_AUTHORITY_MIGRATIONS)
    assert len(inventory[0]["sha256"]) == 64


def test_preflight_requires_clean_pending_state() -> None:
    from apps.api.hxy_release.global_source_authority_release import evaluate_release_snapshot

    assert evaluate_release_snapshot(_pending_snapshot(), phase="preflight")["status"] == "passed"

    dirty = _pending_snapshot()
    dirty["worktree_clean"] = False
    assert evaluate_release_snapshot(dirty, phase="preflight")["status"] == "failed"
    assert evaluate_release_snapshot(_applied_snapshot(), phase="preflight")["status"] == "failed"


def test_postflight_requires_complete_semantic_contract_and_safe_baseline() -> None:
    from apps.api.hxy_release.global_source_authority_release import evaluate_release_snapshot

    passed = evaluate_release_snapshot(_applied_snapshot(), phase="postflight")
    assert passed["status"] == "passed"
    assert passed["migration_state"] == "applied"

    unsafe = _applied_snapshot()
    unsafe["unsafe_baseline_asset_count"] = 1
    assert evaluate_release_snapshot(unsafe, phase="postflight")["status"] == "failed"

    missing_guard = _applied_snapshot()
    missing_guard["triggers"] = list(missing_guard["triggers"])[:-1]
    assert evaluate_release_snapshot(missing_guard, phase="postflight")["status"] == "failed"


def test_partial_or_orphan_global_authority_objects_fail_closed() -> None:
    from apps.api.hxy_release.global_source_authority_release import evaluate_release_snapshot

    partial = _pending_snapshot()
    partial["routines"] = ["hxy_reject_knowledge_asset_authority_event_mutation"]
    result = evaluate_release_snapshot(partial, phase="preflight")

    assert result["status"] == "failed"
    assert result["migration_state"] == "partial"


def test_apply_requires_exact_019_confirmation_and_clean_commit(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from apps.api.hxy_release import global_source_authority_release
    from apps.api.hxy_release.guarded_migration import ReleaseAuthorizationError

    delegated = False

    def fake_apply(*_args, **_kwargs):
        nonlocal delegated
        delegated = True
        return {"status": "passed"}

    monkeypatch.setattr(global_source_authority_release, "apply_release_migrations", fake_apply)

    for wrong_confirmation in ("APPLY-HXY-018", "APPLY-HXY-019 ", ""):
        with pytest.raises(ReleaseAuthorizationError, match="exact migration confirmation"):
            global_source_authority_release.apply_global_source_authority_migration(
                ROOT,
                "postgresql://localhost/hxy",
                manifest_path=tmp_path / "manifest.json",
                confirmation=wrong_confirmation,
                git_inspector=lambda _root: {
                    "commit_valid": True,
                    "worktree_clean": True,
                },
            )

    with pytest.raises(ReleaseAuthorizationError, match="clean worktree"):
        global_source_authority_release.apply_global_source_authority_migration(
            ROOT,
            "postgresql://localhost/hxy",
            manifest_path=tmp_path / "manifest.json",
            confirmation="APPLY-HXY-019",
            git_inspector=lambda _root: {
                "commit_valid": True,
                "worktree_clean": False,
            },
        )
    assert delegated is False


def test_cli_exposes_guarded_commands_and_redacts_malformed_dsn(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from apps.api.hxy_release import global_source_authority_release

    parser = global_source_authority_release.build_argument_parser()
    for command in ("preflight", "backup", "apply", "postflight"):
        assert parser.parse_args([command]).command == command
    with pytest.raises(SystemExit):
        parser.parse_args(["restore"])
    capsys.readouterr()

    script = (ROOT / "scripts" / "hxy-global-source-authority-release.py").read_text(
        encoding="utf-8"
    )
    assert "global_source_authority_release" in script
    assert "htops" not in script.lower()

    malformed = "".join(
        (
            "postgresql://",
            "founder",
            ":",
            "test-secret",
            "@[",
            "/root/private-global-authority",
        )
    )
    monkeypatch.setenv("HXY_DATABASE_URL", malformed)
    assert global_source_authority_release.main(["preflight"]) == 2
    output = capsys.readouterr()
    assert "test-secret" not in output.out
    assert "/root/private-global-authority" not in output.out
    assert json.loads(output.out)["status"] == "failed"
    assert output.err == ""
