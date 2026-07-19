from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _snapshot(**overrides: object) -> dict[str, object]:
    snapshot: dict[str, object] = {
        "server_major": 16,
        "database_matches": True,
        "current_schema": "public",
        "prerequisite_passed": True,
        "migration_count": 4,
        "relation_names": [],
        "required_columns": {},
        "material_identity_check": True,
        "git_commit": "a" * 40,
        "commit_valid": True,
        "worktree_clean": True,
    }
    snapshot.update(overrides)
    return snapshot


def _applied_snapshot() -> dict[str, object]:
    return _snapshot(
        relation_names=[
            "hxy_legal_entities",
            "hxy_operating_mode_catalog",
            "hxy_governance_profiles",
            "hxy_store_operating_relationships",
            "hxy_data_sources",
            "hxy_data_connectors",
            "hxy_dataset_snapshots",
            "hxy_business_facts",
            "hxy_metric_definitions",
            "hxy_asset_bindings",
            "hxy_channel_identity_bindings",
            "hxy_inbound_envelopes",
            "hxy_ai_proposals",
            "hxy_outbox_messages",
            "hxy_outbox_attempts",
            "hxy_operating_events",
            "hxy_workflow_instances",
            "hxy_operating_evidence",
            "hxy_state_transitions",
            "hxy_metric_facts",
            "hxy_operating_command_receipts",
            "hxy_material_scan_results",
            "hxy_material_job_requeue_events",
        ],
        required_columns={
            "hxy_product_materials": ["organization_id", "store_id"],
            "hxy_product_tasks": [
                "operating_event_id",
                "workflow_instance_id",
                "task_type",
                "submitted_at",
                "accepted_at",
                "acceptance_assignment_id",
            ],
            "hxy_inbound_envelopes": ["request_fingerprint"],
            "hxy_material_parser_jobs": ["job_type"],
            "hxy_material_job_attempts": ["source_sha256", "source_size_bytes"],
        },
    )


def test_release_is_bound_to_the_contiguous_020_to_023_migrations() -> None:
    from apps.api.hxy_release.operating_material_release import (
        APPLY_CONFIRMATION,
        OPERATING_MATERIAL_MIGRATIONS,
        migration_inventory,
    )

    assert APPLY_CONFIRMATION == "APPLY-HXY-020-023"
    assert OPERATING_MATERIAL_MIGRATIONS == (
        "020_hxy_data_catalog.sql",
        "021_hxy_operating_loop.sql",
        "022_hxy_operating_api_hardening.sql",
        "023_hxy_material_safety_scan.sql",
    )
    inventory = migration_inventory(ROOT, trusted_root=Path("/root/hxy"))
    assert [item["name"] for item in inventory] == list(OPERATING_MATERIAL_MIGRATIONS)
    assert all(len(item["sha256"]) == 64 for item in inventory)


def test_preflight_accepts_only_a_clean_fully_pending_state() -> None:
    from apps.api.hxy_release.operating_material_release import evaluate_release_snapshot

    result = evaluate_release_snapshot(_snapshot(), phase="preflight")

    assert result["status"] == "passed"
    assert result["migration_state"] == "pending"


def test_pending_state_ignores_preexisting_columns_outside_release_signature() -> None:
    from apps.api.hxy_release.operating_material_release import evaluate_release_snapshot

    result = evaluate_release_snapshot(
        _snapshot(required_columns={"hxy_product_tasks": ["organization_id", "store_id"]}),
        phase="preflight",
    )

    assert result["status"] == "passed"
    assert result["migration_state"] == "pending"


def test_prerequisite_accepts_governed_authority_changes_after_019_release() -> None:
    from apps.api.hxy_release.operating_material_release import (
        _prerequisite_contract_passed,
    )

    checks = [
        {"name": name, "status": "passed"}
        for name in (
            "postgres_major",
            "database_identity",
            "current_schema",
            "source_authority_prerequisite",
            "migration_inventory",
            "global_source_authority_schema",
            "complete_baseline_events",
        )
    ]
    checks.extend(
        [
            {"name": "safe_asset_baseline", "status": "failed"},
            {"name": "release_created_only_baselines", "status": "failed"},
        ]
    )

    assert _prerequisite_contract_passed({"checks": checks}) is True


def test_preflight_rejects_partial_or_applied_state() -> None:
    from apps.api.hxy_release.operating_material_release import evaluate_release_snapshot

    partial = _snapshot(relation_names=["hxy_inbound_envelopes"])
    applied = _applied_snapshot()

    partial_result = evaluate_release_snapshot(partial, phase="preflight")
    applied_result = evaluate_release_snapshot(applied, phase="preflight")

    assert partial_result["status"] == "failed"
    assert partial_result["migration_state"] == "partial"
    assert applied_result["status"] == "failed"
    assert applied_result["migration_state"] == "applied"


def test_preflight_rejects_dirty_source() -> None:
    from apps.api.hxy_release.operating_material_release import evaluate_release_snapshot

    result = evaluate_release_snapshot(
        _snapshot(worktree_clean=False),
        phase="preflight",
    )

    assert result["status"] == "failed"
    assert {item["name"] for item in result["checks"] if item["status"] == "failed"} == {
        "worktree_clean"
    }


def test_postflight_requires_the_complete_operating_and_material_contract() -> None:
    from apps.api.hxy_release.operating_material_release import evaluate_release_snapshot

    result = evaluate_release_snapshot(_applied_snapshot(), phase="postflight")

    assert result["status"] == "passed"
    assert result["migration_state"] == "applied"
    assert all(item["status"] == "passed" for item in result["checks"])


def test_postflight_rejects_missing_required_column() -> None:
    from apps.api.hxy_release.operating_material_release import evaluate_release_snapshot

    snapshot = _applied_snapshot()
    snapshot["required_columns"] = {
        **snapshot["required_columns"],
        "hxy_inbound_envelopes": [],
    }

    result = evaluate_release_snapshot(snapshot, phase="postflight")

    assert result["status"] == "failed"
    assert any(
        item["name"] == "required_columns" and item["status"] == "failed"
        for item in result["checks"]
    )


def test_runbook_keeps_activation_and_rollback_gates_explicit() -> None:
    runbook = (ROOT / "docs" / "operations" / "hxy-operating-material-release.md").read_text(
        encoding="utf-8"
    )

    for phrase in (
        "APPLY-HXY-020-023",
        "pg_dump",
        "127.0.0.1:3310",
        "releases/current",
        "rollback",
        "/root/htops",
    ):
        assert phrase in runbook


def test_runbook_stops_all_writers_before_switching_the_release() -> None:
    runbook = (ROOT / "docs" / "operations" / "hxy-operating-material-release.md").read_text(
        encoding="utf-8"
    )

    stop_writers = (
        "systemctl stop hxy-knowledge-api.service "
        "hxy-material-worker.service hxy-outbox-worker.service"
    )
    verify_writers = (
        "systemctl is-active hxy-knowledge-api.service "
        "hxy-material-worker.service hxy-outbox-worker.service"
    )
    switch_release = "ln -sfn \"$HXY_CANDIDATE_RELEASE\" /root/hxy/releases/current.next"
    start_services = (
        "systemctl start hxy-knowledge-api.service hxy-product-web.service "
        "hxy-material-worker.service hxy-outbox-worker.service"
    )

    assert stop_writers in runbook
    assert verify_writers in runbook
    assert 'test "$(systemctl is-active "$unit")" = "inactive"' in runbook
    assert switch_release in runbook
    assert start_services in runbook
    assert runbook.index(stop_writers) < runbook.index(verify_writers)
    assert runbook.index(verify_writers) < runbook.index(switch_release)
    assert runbook.index(switch_release) < runbook.index(start_services)


def test_runbook_requires_isolated_product_smoke_without_visible_uploads() -> None:
    runbook = (ROOT / "docs" / "operations" / "hxy-operating-material-release.md").read_text(
        encoding="utf-8"
    )

    assert "scripts/run-hxy-isolated-product-smoke.py" in runbook
    assert "Do not use the real Founder assignment" in runbook
    assert "Do not upload release canary materials" in runbook
