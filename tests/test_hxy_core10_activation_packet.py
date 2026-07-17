from __future__ import annotations

import json

import pytest


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


def _constitution_draft() -> dict[str, object]:
    return {
        "version": "fixture-constitution.v1",
        "core_statements": {
            "brand_identity": "Fixture identity.",
            "service_facts": ["Fixture service fact."],
        },
        "role_variants": {
            "founder": "Fixture founder wording.",
            "headquarters": "Fixture headquarters wording.",
            "store_manager": "Fixture store manager wording.",
            "store_staff": "Fixture store staff wording.",
        },
        "forbidden_interpretations": [
            {
                "statement": "Fixture forbidden interpretation.",
                "blocked_terms": ["fixture-blocked-term"],
            }
        ],
        "source_references": [
            {
                "source_id": "asset-brand-001",
                "authority": "official_internal",
            }
        ],
    }


def _packet_inputs() -> dict[str, object]:
    return {
        "report": _report(*FAILED_CASES),
        "constitution_state": {
            "status": "missing",
            "active_version": None,
        },
        "constitution_draft": _constitution_draft(),
        "product_sources": [_source("asset-product-001")],
        "operations_sources": [_source("asset-operations-001")],
        "reception_draft": {
            "question_pattern": "Fixture reception question?",
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


def test_canonical_reception_draft_drives_proposal_and_write_intent() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    packet = build_core10_activation_packet(**_packet_inputs())
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "invalid_reception_draft" not in reception_item["blockers"]
    proposed_draft = reception_item["proposed_authority"]["draft"]
    assert proposed_draft["question_pattern"] == "Fixture reception question?"
    assert "question" not in proposed_draft
    create_intent = next(
        intent
        for intent in reception_item["exact_write_intents"]
        if intent["operation"] == "create_approved_answer_card"
    )
    assert create_intent["question_pattern"] == "Fixture reception question?"
    assert "question" not in create_intent


def test_legacy_reception_question_is_normalized_to_question_pattern() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    reception_draft = dict(inputs["reception_draft"])
    reception_draft["question"] = reception_draft.pop("question_pattern")
    inputs["reception_draft"] = reception_draft

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "invalid_reception_draft" not in reception_item["blockers"]
    proposed_draft = reception_item["proposed_authority"]["draft"]
    assert proposed_draft["question_pattern"] == "Fixture reception question?"
    assert "question" not in proposed_draft


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


@pytest.mark.parametrize(
    ("approved_answer", "expected_matches", "expected_conflicts"),
    [
        ("Fixture reception answer with a clear service boundary.", 1, 0),
        ("A different approved fixture answer.", 0, 1),
    ],
)
def test_approved_reception_card_uses_real_question_pattern_field(
    approved_answer: str,
    expected_matches: int,
    expected_conflicts: int,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["existing_answer_cards"] = [
        {
            "card_id": "fixture-card-real-shape",
            "status": "approved",
            "question_pattern": "Fixture reception question?",
            "answer": approved_answer,
        }
    ]

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    state = reception_item["current_state"]
    assert state["approved_match_count"] == expected_matches
    assert state["approved_conflict_count"] == expected_conflicts
    if expected_conflicts:
        assert "approved_answer_card_conflict" in reception_item["blockers"]
    else:
        assert "approved_answer_card_conflict" not in reception_item["blockers"]
        assert reception_item["exact_write_intents"] == []


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


@pytest.mark.parametrize(
    "unsafe_answer",
    [
        "本服务保证效果。",
        "本服务提供疗效保证。",
        "本服务承诺疗效。",
        "本服务确保有效。",
        "本服务100%有效。",
        "可诊断失眠。",
        "This service offers guaranteed results.",
        "This service can diagnose insomnia.",
        "This service guarantees a cure.",
        "This service will cure insomnia.",
        "This service is 100% effective.",
    ],
)
def test_high_risk_reception_wording_fails_closed(unsafe_answer: str) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["reception_draft"] = {
        "question": "Fixture reception question?",
        "answer": unsafe_answer,
        "source_ids": ["asset-operations-001"],
    }

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "unsafe_answer_wording" in reception_item["blockers"]
    assert reception_item["exact_write_intents"] == []


@pytest.mark.parametrize(
    "bounded_answer",
    [
        "不能保证效果，实际体验因人而异。",
        "本服务不会保证效果。",
        "本服务不用于诊断，身体不适请及时就医。",
        "本服务不能用于诊断。",
        "本服务不可用于治疗疾病。",
        "This service does not guarantee results.",
        "This service cannot diagnose insomnia.",
        "This service is not intended to treat disease.",
        "This service is not used to cure disease.",
    ],
)
def test_explicit_negative_boundary_is_not_misclassified(
    bounded_answer: str,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["reception_draft"] = {
        "question": "Fixture reception question?",
        "answer": bounded_answer,
        "source_ids": ["asset-operations-001"],
    }

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "unsafe_answer_wording" not in reception_item["blockers"]


@pytest.mark.parametrize(
    "unsafe_asset_id",
    [
        "/root/private/credentials.sql",
        "postgresql://example.invalid/hxy",
        "select-from-knowledge",
        "rm-rf-private",
        "credentials-secret",
        "api-token",
        "private-key",
        "asset/path",
        r"asset\path",
        "a" * 129,
    ],
)
def test_unsafe_source_asset_id_fails_closed(unsafe_asset_id: str) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["product_sources"] = [
        {
            "asset_id": unsafe_asset_id,
            "title": "Fixture unsafe identifier",
            "source_origin": "unknown",
            "source_authority": "external_reference",
            "authority_version": 1,
        }
    ]

    packet = build_core10_activation_packet(**inputs)
    product_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "product_system_sources"
    )

    assert "invalid_source_record" in product_item["blockers"]
    assert product_item["exact_write_intents"] == []


@pytest.mark.parametrize(
    "safe_asset_id",
    ["asset-001", "Asset_02:v1.3", "a" * 128],
)
def test_public_source_asset_id_style_remains_eligible(safe_asset_id: str) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["product_sources"] = [
        {
            "asset_id": safe_asset_id,
            "title": "Fixture safe identifier",
            "source_origin": "unknown",
            "source_authority": "external_reference",
            "authority_version": 1,
        }
    ]

    packet = build_core10_activation_packet(**inputs)
    product_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "product_system_sources"
    )

    assert product_item["blockers"] == []
    assert len(product_item["exact_write_intents"]) == 1


@pytest.mark.parametrize(
    "unsafe_source_id",
    [
        "/root/private/credentials.sql",
        "postgresql://example.invalid/hxy",
        "api-token",
    ],
)
def test_reception_source_ids_use_the_same_public_id_gate(
    unsafe_source_id: str,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["reception_draft"] = {
        "question": "Fixture reception question?",
        "answer": "Fixture reception answer with a clear service boundary.",
        "source_ids": [unsafe_source_id],
    }

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "invalid_source_record" in reception_item["blockers"]
    assert reception_item["exact_write_intents"] == []
    assert reception_item["source_evidence"] == []


def test_reception_card_requires_at_least_one_source_id() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["reception_draft"] = {
        "question": "Fixture reception question?",
        "answer": "Fixture reception answer with a clear service boundary.",
        "source_ids": [],
    }

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "missing_source_selection" in reception_item["blockers"]
    assert reception_item["exact_write_intents"] == []


@pytest.mark.parametrize(
    "invalid_case",
    [
        "unsafe_version",
        "blank_brand_identity",
        "empty_service_facts",
        "non_string_service_fact",
        "missing_role_variant",
        "blank_role_variant",
        "empty_forbidden_interpretations",
        "blank_forbidden_statement",
        "empty_blocked_terms",
        "empty_source_references",
        "unsafe_source_id",
        "invalid_source_authority",
    ],
)
def test_nonempty_invalid_constitution_draft_fails_closed(
    invalid_case: str,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    invalid_draft = _constitution_draft()
    if invalid_case == "unsafe_version":
        invalid_draft["version"] = "../fixture"
    elif invalid_case == "blank_brand_identity":
        invalid_draft["core_statements"]["brand_identity"] = "   "
    elif invalid_case == "empty_service_facts":
        invalid_draft["core_statements"]["service_facts"] = []
    elif invalid_case == "non_string_service_fact":
        invalid_draft["core_statements"]["service_facts"] = [7]
    elif invalid_case == "missing_role_variant":
        invalid_draft["role_variants"].pop("store_staff")
    elif invalid_case == "blank_role_variant":
        invalid_draft["role_variants"]["store_staff"] = "   "
    elif invalid_case == "empty_forbidden_interpretations":
        invalid_draft["forbidden_interpretations"] = []
    elif invalid_case == "blank_forbidden_statement":
        invalid_draft["forbidden_interpretations"][0]["statement"] = "   "
    elif invalid_case == "empty_blocked_terms":
        invalid_draft["forbidden_interpretations"][0]["blocked_terms"] = []
    elif invalid_case == "empty_source_references":
        invalid_draft["source_references"] = []
    elif invalid_case == "unsafe_source_id":
        invalid_draft["source_references"][0]["source_id"] = "../fixture"
    elif invalid_case == "invalid_source_authority":
        invalid_draft["source_references"][0]["authority"] = "external_reference"

    inputs = _packet_inputs()
    inputs["constitution_draft"] = invalid_draft

    packet = build_core10_activation_packet(**inputs)
    constitution_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "brand_constitution"
    )

    assert "invalid_constitution_draft" in constitution_item["blockers"]
    assert constitution_item["exact_write_intents"] == []


@pytest.mark.parametrize(
    "allowed_authority",
    ["official_internal", "approved_answer_card"],
)
def test_constitution_draft_accepts_only_allowed_source_authorities(
    allowed_authority: str,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    constitution_draft = _constitution_draft()
    constitution_draft["source_references"][0]["authority"] = allowed_authority
    inputs["constitution_draft"] = constitution_draft

    packet = build_core10_activation_packet(**inputs)
    constitution_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "brand_constitution"
    )

    assert "invalid_constitution_draft" not in constitution_item["blockers"]


@pytest.mark.parametrize(
    ("field", "invalid_value"),
    [
        ("question_pattern", None),
        ("question_pattern", "   "),
        ("question_pattern", 7),
        ("answer", None),
        ("answer", "   "),
        ("answer", ["Fixture answer"]),
    ],
)
def test_invalid_reception_draft_shape_fails_closed(
    field: str,
    invalid_value: object,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    reception_draft = dict(inputs["reception_draft"])
    if invalid_value is None:
        reception_draft.pop(field)
    else:
        reception_draft[field] = invalid_value
    inputs["reception_draft"] = reception_draft

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "invalid_reception_draft" in reception_item["blockers"]
    assert reception_item["exact_write_intents"] == []


def test_unresolved_reception_source_evidence_fails_closed() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["reception_draft"] = {
        "question": "Fixture reception question?",
        "answer": "Fixture reception answer with a clear service boundary.",
        "source_ids": ["asset-operations-001", "asset-unknown"],
    }

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "unresolved_source_evidence" in reception_item["blockers"]
    assert reception_item["exact_write_intents"] == []
    assert reception_item["source_evidence"] == [
        {"asset_id": "asset-operations-001"}
    ]


@pytest.mark.parametrize(
    "resolved_source_id",
    ["asset-product-001", "asset-operations-001"],
)
def test_reception_evidence_accepts_sources_resolved_by_current_packet(
    resolved_source_id: str,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["reception_draft"] = {
        "question": "Fixture reception question?",
        "answer": "Fixture reception answer with a clear service boundary.",
        "source_ids": [resolved_source_id],
    }

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "unresolved_source_evidence" not in reception_item["blockers"]
    assert reception_item["source_evidence"] == [
        {"asset_id": resolved_source_id}
    ]


@pytest.mark.parametrize(
    "source_record",
    [
        {
            "asset_id": "asset-untrusted-snapshot",
            "source_origin": "external",
            "source_authority": "external_reference",
            "authority_version": 1,
        },
        {
            "asset_id": "asset-untrusted-snapshot",
            "source_origin": "unknown",
            "source_authority": "external_reference",
            "authority_version": 1,
        },
        {
            "asset_id": "asset-untrusted-snapshot",
            "source_origin": "internal",
            "source_authority": "external_reference",
            "authority_version": 1,
        },
        {
            "asset_id": "asset-untrusted-snapshot",
            "source_origin": "internal",
            "source_authority": "internal_material",
            "authority_version": 0,
        },
    ],
)
def test_untrusted_source_snapshot_cannot_resolve_reception_evidence(
    source_record: dict[str, object],
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["product_sources"] = [source_record]
    inputs["reception_draft"] = {
        "question_pattern": "Fixture reception question?",
        "answer": "Fixture reception answer with a clear service boundary.",
        "source_ids": ["asset-untrusted-snapshot"],
    }

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "unresolved_source_evidence" in reception_item["blockers"]
    assert reception_item["exact_write_intents"] == []
    assert reception_item["source_evidence"] == []


def test_constitution_draft_self_report_cannot_resolve_reception_evidence() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    inputs = _packet_inputs()
    inputs["reception_draft"] = {
        "question_pattern": "Fixture reception question?",
        "answer": "Fixture reception answer with a clear service boundary.",
        "source_ids": ["asset-brand-001"],
    }

    packet = build_core10_activation_packet(**inputs)
    reception_item = next(
        item
        for item in packet["items"]
        if item["group_id"] == "reception_standard_answer_card"
    )

    assert "unresolved_source_evidence" in reception_item["blockers"]
    assert reception_item["exact_write_intents"] == []
    assert reception_item["source_evidence"] == []
