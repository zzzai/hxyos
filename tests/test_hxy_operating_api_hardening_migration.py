from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "022_hxy_operating_api_hardening.sql"


def test_evidence_client_idempotency_is_enforced_by_database() -> None:
    assert MIGRATION.exists(), "missing 022_hxy_operating_api_hardening.sql"
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())

    assert "ALTER TABLE hxy_operating_evidence ADD COLUMN IF NOT EXISTS client_evidence_id UUID" in sql
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_operating_evidence_client_request" in sql
    assert "organization_id, created_by_assignment_id, client_evidence_id" in sql
    assert "WHERE client_evidence_id IS NOT NULL" in sql


def test_inbound_intake_idempotency_binds_key_to_request_fingerprint() -> None:
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())

    assert "ALTER TABLE hxy_inbound_envelopes ADD COLUMN IF NOT EXISTS request_fingerprint" in sql
    assert "request_fingerprint ~ '^[0-9a-f]{64}$'" in sql
    assert "ALTER COLUMN request_fingerprint SET NOT NULL" in sql


def test_operating_command_receipts_are_durable_unique_and_append_only() -> None:
    sql = " ".join(MIGRATION.read_text(encoding="utf-8").split())

    assert "CREATE TABLE IF NOT EXISTS hxy_operating_command_receipts" in sql
    assert "request_fingerprint CHAR(64) NOT NULL" in sql
    assert "receipt_json JSONB NOT NULL" in sql
    assert "UNIQUE (organization_id, correlation_id)" in sql
    assert "request_fingerprint ~ '^[0-9a-f]{64}$'" in sql
    assert "trg_hxy_operating_command_receipts_append_only" in sql
    assert "trg_hxy_operating_command_receipts_no_truncate" in sql
    assert "hxy_reject_operating_history_mutation()" in sql
