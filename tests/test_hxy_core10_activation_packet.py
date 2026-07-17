from __future__ import annotations

import json


FAILED_CASES = (
    "core-brand-identity",
    "core-product-system",
    "core-operating-decision",
    "core-citation",
    "core-next-action",
)


def _report(*failed_case_ids: str) -> dict[str, object]:
    failed = set(failed_case_ids)
    return {
        "version": "fixture-report.v1",
        "scores": [
            {"case_id": case_id, "passed": case_id not in failed}
            for case_id in FAILED_CASES
        ],
    }


def _source(asset_id: str) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "title": f"Fixture {asset_id}",
        "source_origin": "internal",
        "source_authority": "internal_material",
        "authority_version": 2,
    }


def _packet_inputs() -> dict[str, object]:
    return {
        "report": _report(*FAILED_CASES),
        "constitution_state": {
            "status": "missing",
            "active_version": None,
        },
        "constitution_draft": {
            "version": "fixture-constitution.v1",
            "core_statements": {"brand_identity": "Fixture identity."},
            "source_references": [{"source_id": "asset-brand-001"}],
        },
        "product_sources": [_source("asset-product-001")],
        "operations_sources": [_source("asset-operations-001")],
        "reception_draft": {
            "question": "Fixture reception question?",
            "answer": "Fixture reception answer with a clear service boundary.",
            "source_ids": ["asset-operations-001"],
        },
        "existing_answer_cards": [],
        "generated_at": "2026-07-17T10:00:00+00:00",
    }


def test_builds_read_only_four_group_packet_for_current_core10_failures() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        DECISION_OPTIONS,
        PACKET_VERSION,
        build_core10_activation_packet,
    )

    packet = build_core10_activation_packet(**_packet_inputs())

    assert packet["version"] == PACKET_VERSION
    assert packet["generated_at"] == "2026-07-17T10:00:00+00:00"
    assert packet["item_count"] == 4
    assert packet["write_to_database"] is False
    assert packet["publish_allowed"] is False
    assert [item["group_id"] for item in packet["items"]] == [
        "brand_constitution",
        "product_system_sources",
        "first_store_operations_sources",
        "reception_standard_answer_card",
    ]

    expected_cases = {
        "brand_constitution": ["core-brand-identity"],
        "product_system_sources": ["core-product-system"],
        "first_store_operations_sources": [
            "core-operating-decision",
            "core-next-action",
        ],
        "reception_standard_answer_card": ["core-citation"],
    }
    required_fields = {
        "current_state",
        "proposed_authority",
        "source_evidence",
        "why_needed",
        "affected_core10_cases",
        "risk_if_approved",
        "risk_if_rejected",
        "exact_write_intents",
        "blockers",
        "decision_options",
        "official_use_allowed",
        "write_allowed",
    }
    for item in packet["items"]:
        assert required_fields <= item.keys()
        assert item["affected_core10_cases"] == expected_cases[item["group_id"]]
        assert item["decision_options"] == list(DECISION_OPTIONS)
        assert item["official_use_allowed"] is False
        assert item["write_allowed"] is False

    encoded = json.dumps(packet, ensure_ascii=True, sort_keys=True)
    assert "claim_id" not in encoded
    assert "chunk_id" not in encoded


def test_ignores_mapped_cases_that_are_not_currently_failing() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["report"] = _report("core-product-system")

    packet = build_core10_activation_packet(**inputs)
    cases_by_group = {
        item["group_id"]: item["affected_core10_cases"] for item in packet["items"]
    }

    assert cases_by_group == {
        "brand_constitution": [],
        "product_system_sources": ["core-product-system"],
        "first_store_operations_sources": [],
        "reception_standard_answer_card": [],
    }


def test_fail_closed_blockers_cover_missing_external_unselected_and_unsafe_inputs() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs.update(
        constitution_draft=None,
        product_sources=[
            {
                **_source("asset-product-external"),
                "source_origin": "external",
                "source_authority": "external_reference",
            }
        ],
        operations_sources=[],
        reception_draft={
            "question": "Fixture efficacy question?",
            "answer": "This service guarantees efficacy and can 治疗失眠.",
            "source_ids": ["asset-operations-001"],
        },
    )

    packet = build_core10_activation_packet(**inputs)
    blockers = {
        item["group_id"]: item["blockers"] for item in packet["items"]
    }

    assert "missing_constitution_draft" in blockers["brand_constitution"]
    assert "external_source_not_eligible" in blockers["product_system_sources"]
    assert (
        "missing_source_selection"
        in blockers["first_store_operations_sources"]
    )
    assert "unsafe_answer_wording" in blockers["reception_standard_answer_card"]


def test_unknown_source_produces_only_a_declarative_classification_intent() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["product_sources"] = [
        {
            "asset_id": "asset-product-unknown",
            "title": "Fixture unknown source",
            "source_origin": "unknown",
            "source_authority": "external_reference",
            "authority_version": 7,
        }
    ]

    packet = build_core10_activation_packet(**inputs)
    product_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "product_system_sources"
    )
    source_intents = [
        intent
        for intent in product_item["exact_write_intents"]
        if intent.get("operation") == "classify_source_authority"
    ]

    assert len(source_intents) == 1
    intent = source_intents[0]
    assert set(intent) == {
        "operation",
        "asset_id",
        "expected_previous_version",
        "source_origin",
        "source_authority",
        "reason",
        "payload_sha256",
    }
    assert intent["asset_id"] == "asset-product-unknown"
    assert intent["expected_previous_version"] == 7
    assert intent["source_origin"] == "internal"
    assert intent["source_authority"] == "internal_material"
    assert len(intent["payload_sha256"]) == 64
    assert set(intent["payload_sha256"]) <= set("0123456789abcdef")
    assert "write_allowed" not in intent
    serialized = json.dumps(intent, ensure_ascii=True).lower()
    assert "select " not in serialized
    assert "insert " not in serialized
    assert "update " not in serialized
    assert "delete " not in serialized
    assert "/root/" not in serialized
    assert "postgresql://" not in serialized
    assert "credential" not in serialized


def test_external_source_never_produces_a_classification_intent() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["product_sources"] = [
        {
            **_source("asset-product-external"),
            "source_origin": "external",
            "source_authority": "external_reference",
        }
    ]

    packet = build_core10_activation_packet(**inputs)
    product_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "product_system_sources"
    )

    assert "external_source_not_eligible" in product_item["blockers"]
    assert not any(
        intent.get("operation") == "classify_source_authority"
        for intent in product_item["exact_write_intents"]
    )


def test_conflicting_approved_reception_card_fails_closed() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["existing_answer_cards"] = [
        {
            "card_id": "fixture-card-001",
            "status": "approved",
            "question": "Fixture reception question?",
            "answer": "A different approved fixture answer.",
        }
    ]

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "approved_answer_card_conflict" in reception_item["blockers"]
    assert reception_item["current_state"]["approved_conflict_count"] == 1


def test_forbidden_claim_and_chunk_keys_are_removed_from_all_output_levels() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["constitution_state"] = {
        "status": "missing",
        "claim_id": "forbidden-claim",
        "nested": {"chunk_id": "forbidden-chunk"},
    }
    inputs["product_sources"] = [
        {
            **_source("asset-product-001"),
            "claim_id": "forbidden-claim",
            "metadata": {"chunk_id": "forbidden-chunk"},
        }
    ]

    packet = build_core10_activation_packet(**inputs)

    def walk(value: object) -> None:
        if isinstance(value, dict):
            assert "claim_id" not in value
            assert "chunk_id" not in value
            for nested in value.values():
                walk(nested)
        elif isinstance(value, list):
            for nested in value:
                walk(nested)

    walk(packet)


def test_builder_is_deterministic_when_generated_at_is_not_supplied() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["generated_at"] = None

    first = build_core10_activation_packet(**inputs)
    second = build_core10_activation_packet(**inputs)

    assert first == second
    assert first["generated_at"] is None


def test_existing_official_source_is_never_downgraded_by_write_intent() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["product_sources"] = [
        {
            **_source("asset-product-official"),
            "source_authority": "official_internal",
        }
    ]

    packet = build_core10_activation_packet(**inputs)
    product_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "product_system_sources"
    )

    assert product_item["blockers"] == []
    assert product_item["exact_write_intents"] == []


def test_invalid_source_governance_record_fails_closed() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["operations_sources"] = [
        {
            "asset_id": "asset-operations-invalid",
            "source_origin": "unknown",
            "source_authority": "internal_material",
            "authority_version": 1,
        }
    ]

    packet = build_core10_activation_packet(**inputs)
    operations_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "first_store_operations_sources"
    )

    assert "invalid_source_record" in operations_item["blockers"]
    assert operations_item["exact_write_intents"] == []
