from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "014_hxy_knowledge_activation.sql"


def test_activation_migration_separates_private_chunks_from_formal_knowledge() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "CREATE TABLE IF NOT EXISTS hxy_material_chunks" in sql
    assert "assignment_id UUID NOT NULL" in normalized
    assert "material_id UUID NOT NULL" in normalized
    assert "artifact_type TEXT NOT NULL DEFAULT 'normalized_markdown'" in normalized
    assert "CHECK (artifact_type = 'normalized_markdown')" in normalized
    assert "FOREIGN KEY (assignment_id, material_id)" in normalized
    assert "REFERENCES hxy_product_materials(assignment_id, material_id)" in normalized
    assert "FOREIGN KEY (artifact_id, assignment_id, material_id, artifact_type)" in normalized
    assert "REFERENCES hxy_material_artifacts(artifact_id, assignment_id, material_id, artifact_type)" in normalized
    assert "official_use_allowed BOOLEAN NOT NULL DEFAULT FALSE" in normalized
    assert "CHECK (official_use_allowed = FALSE)" in normalized
    assert "UNIQUE (artifact_id, chunk_index)" in normalized
    assert "idx_hxy_material_chunks_content_trgm" in sql
    assert "gin_trgm_ops" in sql


def test_activation_migration_records_bounded_product_answer_traces() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())

    assert "CREATE TABLE IF NOT EXISTS hxy_product_answer_traces" in sql
    assert "private_material_count INTEGER NOT NULL DEFAULT 0" in normalized
    assert "authority_card_hit BOOLEAN NOT NULL DEFAULT FALSE" in normalized
    assert "outcome TEXT NOT NULL" in normalized
    assert "outcome IN ('succeeded', 'failed')" in normalized
    assert "FOREIGN KEY (assignment_id, conversation_id)" in normalized
    assert "FOREIGN KEY (assignment_id, conversation_id, user_message_id)" in normalized
    assert "FOREIGN KEY (assignment_id, conversation_id, assistant_message_id)" in normalized
    assert "payload_json JSONB NOT NULL DEFAULT '{}'::jsonb" in normalized
    assert "char_length(model_name) <= 120" in normalized
    assert "INSERT INTO" not in sql.upper()
