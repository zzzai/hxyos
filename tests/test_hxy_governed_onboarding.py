from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "017_hxy_governed_onboarding.sql"


def migration_sql() -> tuple[str, str]:
    sql = MIGRATION.read_text(encoding="utf-8")
    return sql, " ".join(sql.split())


def test_onboarding_migration_scopes_invites_to_hxy_boundaries() -> None:
    sql, normalized = migration_sql()

    assert "CREATE TABLE IF NOT EXISTS hxy_member_invites" in normalized
    assert "CREATE TABLE IF NOT EXISTS hxy_member_invite_events" in normalized
    assert "CHECK (role IN ('store_manager', 'store_employee'))" in normalized
    assert "FOREIGN KEY (organization_id, store_id)" in normalized
    assert (
        "REFERENCES hxy_organization_stores(organization_id, store_id)"
        in normalized
    )
    assert (
        "FOREIGN KEY (organization_id, created_by_assignment_id)" in normalized
    )
    assert (
        "REFERENCES hxy_role_assignments(organization_id, assignment_id)"
        in normalized
    )
    assert (
        "FOREIGN KEY (organization_id, store_id, redeemed_assignment_id)"
        in normalized
    )
    assert (
        "REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)"
        in normalized
    )
    assert "UNIQUE (token_hash)" in normalized
    assert "raw_token" not in sql.lower()
    assert "invite_token" not in sql.lower()


def test_onboarding_migration_enforces_invite_state_shapes() -> None:
    _, normalized = migration_sql()

    assert "status IN ('pending', 'redeemed', 'revoked')" in normalized
    assert (
        "status = 'pending' AND redeemed_account_id IS NULL AND "
        "redeemed_assignment_id IS NULL AND redeemed_at IS NULL AND revoked_at IS NULL"
        in normalized
    )
    assert (
        "status = 'redeemed' AND redeemed_account_id IS NOT NULL AND "
        "redeemed_assignment_id IS NOT NULL AND redeemed_at IS NOT NULL AND "
        "revoked_at IS NULL"
        in normalized
    )
    assert (
        "status = 'revoked' AND redeemed_account_id IS NULL AND "
        "redeemed_assignment_id IS NULL AND redeemed_at IS NULL AND "
        "revoked_at IS NOT NULL"
        in normalized
    )


def test_onboarding_migration_indexes_expiry_and_status() -> None:
    _, normalized = migration_sql()

    assert "CREATE INDEX IF NOT EXISTS idx_hxy_member_invites_expires" in normalized
    assert "ON hxy_member_invites (expires_at)" in normalized
    assert "CREATE INDEX IF NOT EXISTS idx_hxy_member_invites_scope_status" in normalized
    assert (
        "ON hxy_member_invites (organization_id, store_id, status, created_at DESC)"
        in normalized
    )


def test_onboarding_invite_events_are_append_only() -> None:
    _, normalized = migration_sql()

    assert "hxy_member_invite_events is append-only" in normalized
    assert "BEFORE UPDATE OR DELETE ON hxy_member_invite_events" in normalized
    assert "BEFORE TRUNCATE ON hxy_member_invite_events" in normalized


def test_onboarding_migration_contains_no_seed_rows_or_foreign_brand_data() -> None:
    sql, normalized = migration_sql()

    assert "INSERT INTO" not in normalized
    assert "htops" not in sql.lower()
    assert "hetang" not in sql.lower()
