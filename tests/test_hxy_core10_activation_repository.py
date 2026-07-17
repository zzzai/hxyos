from __future__ import annotations

import re
from typing import Any

import pytest


class _Result:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict[str, Any]]:
        return self._rows


class _SnapshotConnection:
    def __init__(
        self,
        *,
        assets: dict[str, dict[str, Any]] | None = None,
        chunks: list[dict[str, Any]] | None = None,
        answer_cards: list[dict[str, Any]] | None = None,
    ) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.assets = assets or _asset_rows()
        self.chunks = chunks or []
        self.answer_cards = answer_cards or []

    def __enter__(self) -> "_SnapshotConnection":
        return self

    def __exit__(self, *_args: Any) -> None:
        return None

    def execute(self, sql: str, params: tuple[Any, ...]) -> _Result:
        normalized = " ".join(sql.split())
        self.statements.append((normalized, params))
        if "FROM hxy_knowledge_assets" in normalized:
            selected = set(params[0])
            return _Result(
                [
                    row
                    for asset_id, row in reversed(list(self.assets.items()))
                    if asset_id in selected
                ]
            )
        if "FROM hxy_knowledge_chunks" in normalized:
            selected = set(params[0])
            return _Result(
                [row for row in self.chunks if row.get("asset_id") in selected]
            )
        if "FROM hxy_knowledge_answer_cards" in normalized:
            rows = self.answer_cards
            if "WHERE status = %s" in normalized:
                rows = [row for row in rows if row.get("status") == params[0]]
            return _Result(rows)
        raise AssertionError(normalized)


def _asset_rows() -> dict[str, dict[str, Any]]:
    return {
        "asset-product": {
            "asset_id": "asset-product",
            "title": "产品体系",
            "file_name": "产品体系.md",
            "source_path": "knowledge/private/产品体系.md",
            "normalized_path": "knowledge/private/产品体系.md",
            "source_origin": "internal",
            "source_authority": "internal_material",
            "authority_version": 2,
            "status": "staged",
            "domain": "product",
            "stage": "preparation",
        },
        "asset-product-2": {
            "asset_id": "asset-product-2",
            "title": "产品体系补充",
            "file_name": "产品体系补充.md",
            "source_path": "knowledge/private/产品体系补充.md",
            "normalized_path": "knowledge/private/产品体系补充.md",
            "source_origin": "internal",
            "source_authority": "official_internal",
            "authority_version": 4,
            "status": "active",
            "domain": "product",
            "stage": "official",
        },
        "asset-operations": {
            "asset_id": "asset-operations",
            "title": "首店运营",
            "file_name": "首店运营.md",
            "source_path": "knowledge/private/首店运营.md",
            "normalized_path": "knowledge/private/首店运营.md",
            "source_origin": "internal",
            "source_authority": "internal_material",
            "authority_version": 3,
            "status": "staged",
            "domain": "operations",
            "stage": "first_store",
        },
        "asset-unselected": {
            "asset_id": "asset-unselected",
            "title": "不应返回",
            "file_name": "不应返回.md",
            "source_path": "knowledge/private/不应返回.md",
            "normalized_path": "knowledge/private/不应返回.md",
            "source_origin": "internal",
            "source_authority": "official_internal",
            "authority_version": 99,
            "status": "active",
            "domain": "brand",
            "stage": "official",
        },
    }


def _repository(connection: _SnapshotConnection):
    from apps.api.hxy_knowledge.repository import KnowledgeRepository

    repository = KnowledgeRepository("postgresql://snapshot.test/hxy")
    repository.connect = lambda: connection
    return repository


def test_activation_snapshot_resolves_only_explicit_asset_ids_in_caller_order() -> None:
    connection = _SnapshotConnection()
    repository = _repository(connection)

    snapshot = repository.core10_activation_snapshot(
        product_asset_ids=["asset-product-2", "asset-product"],
        operations_asset_ids=["asset-operations"],
    )

    assert [item["asset_id"] for item in snapshot["product_sources"]] == [
        "asset-product-2",
        "asset-product",
    ]
    assert [item["asset_id"] for item in snapshot["operations_sources"]] == [
        "asset-operations",
    ]
    assert "asset-unselected" not in repr(snapshot)
    asset_sql, asset_params = next(
        statement
        for statement in connection.statements
        if "FROM hxy_knowledge_assets" in statement[0]
    )
    assert "asset_id = ANY(%s)" in asset_sql
    assert asset_params == (
        ["asset-product-2", "asset-product", "asset-operations"],
    )
    assert not any(asset_id in asset_sql for asset_id in asset_params[0])
    assert "postgresql://" not in repr(snapshot)
    assert not any(
        re.search(r"\b(?:INSERT\s+INTO|UPDATE|DELETE\s+FROM)\b", sql, re.IGNORECASE)
        for sql, _params in connection.statements
    )


def test_parent_authority_beats_malicious_chunk_metadata() -> None:
    malicious_chunk = {
        "chunk_id": "secret-chunk-id",
        "asset_id": "asset-product",
        "title": "片段标题",
        "source_path": "knowledge/private/产品体系.md",
        "normalized_path": "knowledge/private/产品体系.md",
        "domain": "product",
        "stage": "preparation",
        "chunk_index": 0,
        "content": "只用于证据的片段内容",
        "source_origin": "internal",
        "source_authority": "official_internal",
        "authority_version": 999,
        "status": "approved",
        "metadata_json": {
            "source_origin": "internal",
            "source_authority": "official_internal",
            "status": "approved",
        },
    }
    connection = _SnapshotConnection(chunks=[malicious_chunk])
    snapshot = _repository(connection).core10_activation_snapshot(
        product_asset_ids=["asset-product"],
        operations_asset_ids=[],
    )

    source = snapshot["product_sources"][0]
    assert source["source_authority"] == "internal_material"
    assert source["authority_version"] == 2
    assert set(source) == {
        "asset_id",
        "title",
        "file_name",
        "source_path",
        "normalized_path",
        "source_origin",
        "source_authority",
        "authority_version",
        "status",
        "domain",
        "stage",
        "evidence",
    }
    assert set(source["evidence"][0]) == {
        "title",
        "source_path",
        "normalized_path",
        "domain",
        "stage",
        "chunk_index",
        "content",
    }
    chunk_sql = next(
        sql for sql, _params in connection.statements if "hxy_knowledge_chunks" in sql
    )
    assert "metadata_json" not in chunk_sql
    assert "source_authority" not in chunk_sql
    assert "source_origin" not in chunk_sql


def test_unknown_asset_ids_fail_closed_and_list_every_unknown_id() -> None:
    repository = _repository(_SnapshotConnection())

    with pytest.raises(LookupError) as error:
        repository.core10_activation_snapshot(
            product_asset_ids=["asset-missing-product"],
            operations_asset_ids=["asset-missing-operations"],
        )

    assert "asset-missing-product" in str(error.value)
    assert "asset-missing-operations" in str(error.value)


@pytest.mark.parametrize(
    ("product_ids", "operations_ids", "message"),
    [
        (["asset-product", "asset-product"], [], "duplicate"),
        (["asset-product"], ["asset-product"], "duplicate"),
        ([f"asset-{index}" for index in range(21)], [], "20"),
        ([""], [], "non-empty"),
        ([123], [], "string"),
        (("asset-product",), [], "list"),
    ],
)
def test_selected_asset_ids_are_unique_typed_and_bounded(
    product_ids: list[Any],
    operations_ids: list[Any],
    message: str,
) -> None:
    repository = _repository(_SnapshotConnection())

    with pytest.raises(ValueError, match=message):
        repository.core10_activation_snapshot(
            product_asset_ids=product_ids,
            operations_asset_ids=operations_ids,
        )


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"evidence_limit_per_asset": 0}, "evidence_limit_per_asset"),
        ({"evidence_limit_per_asset": 11}, "evidence_limit_per_asset"),
        ({"evidence_limit_per_asset": True}, "evidence_limit_per_asset"),
        ({"excerpt_chars": 0}, "excerpt_chars"),
        ({"excerpt_chars": 2001}, "excerpt_chars"),
        ({"excerpt_chars": True}, "excerpt_chars"),
    ],
)
def test_evidence_bounds_fail_closed(overrides: dict[str, Any], message: str) -> None:
    repository = _repository(_SnapshotConnection())

    with pytest.raises(ValueError, match=message):
        repository.core10_activation_snapshot(
            product_asset_ids=[],
            operations_asset_ids=[],
            **overrides,
        )


def test_evidence_count_and_content_are_bounded_per_asset() -> None:
    chunks = [
        {
            "asset_id": "asset-product",
            "title": f"片段 {index}",
            "source_path": "knowledge/private/产品体系.md",
            "normalized_path": "knowledge/private/产品体系.md",
            "domain": "product",
            "stage": "preparation",
            "chunk_index": index,
            "content": "一二三四五六七八九十" * 20,
        }
        for index in range(5)
    ]
    connection = _SnapshotConnection(chunks=chunks)
    snapshot = _repository(connection).core10_activation_snapshot(
        product_asset_ids=["asset-product"],
        operations_asset_ids=[],
        evidence_limit_per_asset=2,
        excerpt_chars=12,
    )

    evidence = snapshot["product_sources"][0]["evidence"]
    assert [item["chunk_index"] for item in evidence] == [0, 1]
    assert all(len(item["content"]) <= 12 for item in evidence)
    chunk_sql, chunk_params = next(
        statement
        for statement in connection.statements
        if "FROM hxy_knowledge_chunks" in statement[0]
    )
    assert "PARTITION BY" in chunk_sql
    assert "LEFT(content, %s)" in chunk_sql
    assert "%s" in chunk_sql
    assert chunk_params == (["asset-product"], 12, 2)


def test_snapshot_returns_only_approved_answer_cards() -> None:
    cards = [
        {
            "card_id": "card-approved",
            "question_pattern": "如何接待顾客？",
            "intent": "reception",
            "audience": "employee",
            "answer": "先询问顾客状态和偏好。",
            "status": "approved",
        },
        {
            "card_id": "card-draft",
            "question_pattern": "草稿问题",
            "intent": "reception",
            "audience": "employee",
            "answer": "草稿答案",
            "status": "draft",
        },
    ]
    connection = _SnapshotConnection(answer_cards=cards)
    snapshot = _repository(connection).core10_activation_snapshot(
        product_asset_ids=[],
        operations_asset_ids=[],
    )

    assert [card["card_id"] for card in snapshot["approved_answer_cards"]] == [
        "card-approved",
    ]
    card_sql, card_params = next(
        statement
        for statement in connection.statements
        if "answer_cards" in statement[0]
    )
    assert "WHERE status = %s" in card_sql
    assert "LIMIT %s" in card_sql
    assert card_params == ("approved", 100)


def test_snapshot_is_select_only_and_empty_categories_do_not_scan_sources() -> None:
    connection = _SnapshotConnection()
    snapshot = _repository(connection).core10_activation_snapshot(
        product_asset_ids=[],
        operations_asset_ids=[],
    )

    assert snapshot == {
        "product_sources": [],
        "operations_sources": [],
        "approved_answer_cards": [],
    }
    assert not any("hxy_knowledge_assets" in sql for sql, _ in connection.statements)
    assert not any("hxy_knowledge_chunks" in sql for sql, _ in connection.statements)
    assert all(re.match(r"^SELECT\b", sql, re.IGNORECASE) for sql, _ in connection.statements)
