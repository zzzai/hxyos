from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "014_hxy_knowledge_activation.sql"
ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
MATERIAL_ID = "70000000-0000-0000-0000-000000000001"
CHUNK_ID = "a0000000-0000-0000-0000-000000000001"


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


class Result:
    def __init__(self, rows: list[dict[str, Any]] | None = None):
        self.rows = rows or []

    def fetchall(self):
        return self.rows


def _chunk_row() -> dict[str, Any]:
    return {
        "chunk_id": CHUNK_ID,
        "material_id": MATERIAL_ID,
        "original_file_name": "首店接待流程.md",
        "heading": "顾客接待",
        "content": "接待时先询问顾客当下状态，再介绍适合的服务。",
        "domain": "operations",
        "score": 115,
    }


def test_material_search_is_assignment_scoped_and_returns_public_safe_sources() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            calls.append((" ".join(sql.split()), params))
            return Result([_chunk_row()])

    repository.connect = lambda: Connection()

    items = repository.search_material_chunks(
        ASSIGNMENT_ID,
        "首店接待时应该先问什么",
        domain_hint="operations",
        limit=5,
    )

    assert len(items) == 1
    item = items[0]
    assert item["source_type"] == "private_material"
    assert item["source_path"] == f"material:{MATERIAL_ID}"
    assert item["source_url"] == f"/api/v1/materials/{MATERIAL_ID}/content"
    assert item["stage"] == "working_context"
    assert item["status"] == "reference"
    assert item["official_use_allowed"] is False
    assert "storage_key" not in item
    sql, params = calls[0]
    assert "chunk.assignment_id = %s::uuid" in sql
    assert "material.status = 'ready'" in sql
    assert params[0] == ASSIGNMENT_ID


def test_deictic_material_search_uses_latest_ready_material_for_assignment() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_repository")
    repository = module.MaterialRepository("postgresql://materials.test/hxy")
    calls: list[tuple[str, tuple[Any, ...]]] = []

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def execute(self, sql: str, params: tuple[Any, ...]):
            calls.append((" ".join(sql.split()), params))
            return Result([_chunk_row()])

    repository.connect = lambda: Connection()

    items = repository.search_material_chunks(
        ASSIGNMENT_ID,
        "刚上传的资料讲了什么",
        limit=5,
    )

    assert items[0]["material_id"] == MATERIAL_ID
    sql, params = calls[0]
    assert "ORDER BY material.updated_at DESC" in sql
    assert "similarity(chunk.content" not in sql
    assert params == (ASSIGNMENT_ID, 5)


def test_assignment_context_repository_merges_private_context_and_delegates_authority() -> None:
    module = importlib.import_module("apps.api.hxy_product.knowledge_context")

    class BaseRepository:
        def __init__(self) -> None:
            self.saved: list[dict[str, Any]] = []

        def search(self, *_args, **_kwargs):
            return [
                {
                    "chunk_id": "formal-1",
                    "asset_id": "asset-1",
                    "title": "正式知识",
                    "source_path": "formal:asset-1",
                    "domain": "operations",
                    "stage": "approved",
                    "status": "approved",
                    "source_type": "formal_knowledge",
                    "score": 80,
                    "content": "正式流程要求先了解顾客状态。",
                }
            ]

        def find_answer_card(self, question: str, intent: str):
            return {"question": question, "intent": intent, "status": "approved"}

        def save_answer_run(self, payload: dict[str, Any]):
            self.saved.append(payload)
            return "answer-id"

    class MaterialRepository:
        def search_material_chunks(self, assignment_id: str, *_args, **_kwargs):
            assert assignment_id == ASSIGNMENT_ID
            return [
                {
                    **_chunk_row(),
                    "asset_id": MATERIAL_ID,
                    "title": "首店接待流程.md",
                    "source_path": f"material:{MATERIAL_ID}",
                    "source_url": f"/api/v1/materials/{MATERIAL_ID}/content",
                    "stage": "working_context",
                    "status": "reference",
                    "source_type": "private_material",
                    "official_use_allowed": False,
                }
            ]

    base = BaseRepository()
    repository = module.AssignmentKnowledgeRepository(
        base,
        MaterialRepository(),
        assignment_id=ASSIGNMENT_ID,
    )

    items = repository.search("顾客接待", limit=5, domain_hint="operations")

    assert [item["source_type"] for item in items] == [
        "private_material",
        "formal_knowledge",
    ]
    assert repository.retrieval_trace()["private_material_count"] == 1
    assert repository.find_answer_card("问题", "operations")["status"] == "approved"
    assert repository.save_answer_run({"answer": "test"}) == "answer-id"
