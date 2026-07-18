from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "021_hxy_operating_loop.sql"


def migration_sql() -> str:
    assert MIGRATION.exists(), "missing 021_hxy_operating_loop.sql"
    return MIGRATION.read_text(encoding="utf-8")


def normalized_sql() -> str:
    return " ".join(migration_sql().split())


def table_sql(table: str, next_marker: str) -> str:
    normalized = normalized_sql()
    return normalized.split(f"CREATE TABLE IF NOT EXISTS {table}", 1)[1].split(
        next_marker,
        1,
    )[0]


def test_operating_loop_defines_channel_ai_work_and_evidence_objects() -> None:
    sql = migration_sql()
    normalized = normalized_sql()

    for table in (
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
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in normalized

    assert "organization_id UUID NOT NULL" in normalized
    assert "UNIQUE (organization_id, channel, idempotency_key)" in normalized
    assert (
        "status IN ('pending', 'leased', 'retryable_failed', 'succeeded', "
        "'dead_letter')"
    ) in normalized
    assert "actor_type IN ('user', 'policy', 'system')" in normalized
    assert "htops" not in sql.lower()


def test_operating_events_snapshot_relationship_and_governance_versions() -> None:
    event_sql = table_sql(
        "hxy_operating_events",
        "CREATE TABLE IF NOT EXISTS hxy_workflow_instances",
    )

    for field in (
        "store_operating_relationship_id UUID NOT NULL",
        "store_operating_relationship_version INTEGER NOT NULL",
        "governance_profile_id UUID NOT NULL",
        "governance_profile_version INTEGER NOT NULL",
    ):
        assert field in event_sql

    assert "fk_hxy_operating_events_relationship_snapshot" in event_sql
    assert "fk_hxy_operating_events_governance_snapshot" in event_sql


def test_ai_proposals_cannot_be_state_transition_actors() -> None:
    proposal_sql = table_sql(
        "hxy_ai_proposals",
        "CREATE TABLE IF NOT EXISTS hxy_outbox_messages",
    )
    transition_sql = table_sql(
        "hxy_state_transitions",
        "CREATE TABLE IF NOT EXISTS hxy_metric_facts",
    )

    assert "actor_type" not in proposal_sql
    assert "'ai'" not in transition_sql
    assert "actor_type IN ('user', 'policy', 'system')" in transition_sql


def test_policy_and_system_decisions_require_a_nonempty_actor_reference() -> None:
    proposal_sql = table_sql(
        "hxy_ai_proposals",
        "CREATE TABLE IF NOT EXISTS hxy_outbox_messages",
    )
    transition_sql = table_sql(
        "hxy_state_transitions",
        "CREATE TABLE IF NOT EXISTS hxy_metric_facts",
    )

    assert "decision_policy_version IS NOT NULL" in proposal_sql
    assert "actor_reference IS NOT NULL" in transition_sql


def test_append_only_outbox_attempts_can_record_start_and_final_outcome() -> None:
    attempt_sql = table_sql(
        "hxy_outbox_attempts",
        "CREATE TABLE IF NOT EXISTS hxy_operating_events",
    )

    assert (
        "UNIQUE (organization_id, outbox_message_id, attempt_number, outcome)"
        in attempt_sql
    )


def test_evidence_reuses_source_assets_instead_of_binary_metadata() -> None:
    evidence_sql = table_sql(
        "hxy_operating_evidence",
        "CREATE TABLE IF NOT EXISTS hxy_state_transitions",
    )

    assert "source_asset_id UUID NOT NULL" in evidence_sql
    assert "REFERENCES hxy_product_materials(organization_id, material_id)" in evidence_sql
    assert "FOREIGN KEY (organization_id, store_id, task_id)" in evidence_sql
    assert "REFERENCES hxy_product_tasks(organization_id, store_id, task_id)" in evidence_sql
    assert "supersedes_evidence_id UUID" in evidence_sql
    assert "object_key" not in evidence_sql


def test_metric_facts_require_published_metric_definitions() -> None:
    normalized = normalized_sql()
    metric_sql = table_sql("hxy_metric_facts", "ALTER TABLE hxy_product_tasks")

    assert "metric_definition_id UUID NOT NULL" in metric_sql
    assert "metric_definition_version INTEGER NOT NULL" in metric_sql
    assert "fk_hxy_metric_facts_definition" in metric_sql
    assert "hxy_require_published_metric_definition" in normalized
    assert "metric_definition.status <> 'published'" in normalized


def test_operating_history_is_guarded_from_in_place_mutation() -> None:
    normalized = normalized_sql()

    for table in (
        "hxy_outbox_attempts",
        "hxy_operating_evidence",
        "hxy_state_transitions",
        "hxy_metric_facts",
    ):
        assert f"ON {table}" in normalized

    assert "hxy_reject_operating_history_mutation" in normalized
    assert "BEFORE UPDATE OR DELETE" in normalized
    assert "BEFORE TRUNCATE" in normalized


def test_operating_loop_extends_tasks_without_destroying_history() -> None:
    sql = migration_sql()
    normalized = normalized_sql()

    for field in (
        "operating_event_id",
        "workflow_instance_id",
        "task_type",
        "submitted_at",
        "accepted_at",
        "acceptance_assignment_id",
    ):
        assert (
            f"ALTER TABLE hxy_product_tasks ADD COLUMN IF NOT EXISTS {field}"
            in normalized
        )

    assert "status IN ( 'open', 'assigned', 'in_progress', 'submitted', 'accepted'" in normalized
    assert "DROP TABLE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()
