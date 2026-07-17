from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ITEM_KEYS = (
    "brand_constitution",
    "product_system_sources",
    "first_store_operations_sources",
    "reception_standard_answer_card",
)


def _report() -> dict[str, object]:
    return {
        "version": "hxyos-core-10.v1",
        "scores": [
            {"case_id": case_id, "passed": False}
            for case_id in (
                "core-brand-identity",
                "core-product-system",
                "core-operating-decision",
                "core-citation",
                "core-next-action",
            )
        ],
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


def _reception_draft() -> dict[str, object]:
    return {
        "question_pattern": "Fixture reception question?",
        "answer": "Fixture reception answer with a service boundary.",
        "source_ids": ["asset-operations-001"],
    }


def _source(asset_id: str, *, authority_version: int = 2) -> dict[str, object]:
    return {
        "asset_id": asset_id,
        "title": f"Fixture {asset_id}",
        "source_origin": "internal",
        "source_authority": "internal_material",
        "authority_version": authority_version,
    }


def _packet(
    *,
    product_authority_version: int = 2,
    blocked_product: bool = False,
) -> dict[str, object]:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_packet,
    )

    product_source = _source(
        "asset-product-001",
        authority_version=product_authority_version,
    )
    if blocked_product:
        product_source.update(
            source_origin="external",
            source_authority="external_reference",
        )
    return build_core10_activation_packet(
        report=_report(),
        constitution_state={"status": "missing", "active_version": None},
        constitution_draft=_constitution_draft(),
        product_sources=[product_source],
        operations_sources=[_source("asset-operations-001")],
        reception_draft=_reception_draft(),
        existing_answer_cards=[],
        generated_at="2026-07-17T10:00:00+00:00",
    )


def test_write_artifacts_creates_complete_private_business_packet(
    tmp_path: Path,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        write_core10_activation_artifacts,
    )

    packet = _packet()
    paths = write_core10_activation_artifacts(tmp_path, packet)

    assert set(paths) == {"packet_json", "packet_markdown", "decision_sample"}
    assert paths["packet_json"].name == "packet.json"
    assert paths["packet_markdown"].name == "packet.md"
    assert paths["decision_sample"].name == "decisions.sample.json"
    target = paths["packet_json"].parent
    assert target.name == (
        f"core10-activation-{packet['packet_fingerprint'][:12]}"
    )
    assert re.fullmatch(r"core10-activation-[a-f0-9]{12}", target.name)
    assert target.parent == tmp_path.resolve()
    assert all(path.parent == target and path.is_file() for path in paths.values())
    assert {path.name for path in target.iterdir()} == {
        "packet.json",
        "packet.md",
        "decisions.sample.json",
    }
    assert json.loads(paths["packet_json"].read_text(encoding="utf-8")) == packet


def test_markdown_is_founder_readable_and_sanitizes_all_business_fields() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        render_core10_activation_packet_markdown,
    )

    packet = _packet()
    packet["claim_id"] = "private-claim-value"
    packet["items"][0]["current_state"] = {
        "status": "safe current state",
        "source_path": "/root/private/constitution.json",
        "chunk_id": "private-chunk-value",
        "note": "claim_id=private-embedded-claim",
    }
    packet["items"][0]["why_needed"] = (
        "secret credential at postgresql://db.example/private"
    )
    packet["items"][1]["proposed_authority"]["password"] = "hidden-value"
    packet["items"][1]["proposed_authority"]["note"] = (
        "client_secret=private-under-score-value"
    )
    packet["items"][1]["source_evidence"].append(
        {
            "title": "safe evidence title",
            "source_path": r"C:\private\evidence.txt",
            "claim_id": "private-evidence-claim",
        }
    )
    packet["items"][2]["risk_if_approved"] = (
        "UPDATE authority SET active = true"
    )
    packet["items"][2]["risk_if_rejected"] = "rm -rf /root/private"
    packet["items"][3]["blockers"].extend(
        [
            "curl -X POST https://private.example",
            "Please run touch private-output.txt",
            "safe-review-blocker",
        ]
    )

    markdown = render_core10_activation_packet_markdown(packet)
    lowered = markdown.lower()

    assert markdown.startswith("# HXY Core-10 创始人决策包")
    assert markdown.count("\n## ") == 4
    for section in ("当前状态", "拟议方案", "需要原因", "风险", "证据", "阻塞项"):
        assert section in markdown
    assert "safe current state" in markdown
    assert "safe evidence title" in markdown
    assert "safe-review-blocker" in markdown
    for forbidden in (
        "claim_id",
        "chunk_id",
        "private-claim-value",
        "private-chunk-value",
        "private-embedded-claim",
        "private-under-score-value",
        "private-output.txt",
        "/root/",
        r"c:\private",
        "credential",
        "secret",
        "password",
        "postgresql://",
        "mysql://",
        "insert into",
        "update authority",
        "delete from",
        "drop table",
        "rm -rf",
        "curl ",
    ):
        assert forbidden not in lowered


def test_decision_sample_binds_exactly_four_items_with_safe_defaults() -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        build_core10_activation_decision_sample,
    )

    packet = _packet(blocked_product=True)
    sample = build_core10_activation_decision_sample(packet)

    assert sample["actor"] == {
        "id": "founder-placeholder",
        "role": "founder",
    }
    assert sample["packet_id"] == packet["packet_id"]
    assert sample["packet_fingerprint"] == packet["packet_fingerprint"]
    assert sample["preview_only"] is True
    assert sample["write_to_database"] is False
    assert sample["publish_allowed"] is False
    assert len(sample["decisions"]) == 4
    assert [decision["item_key"] for decision in sample["decisions"]] == list(
        ITEM_KEYS
    )

    items_by_key = {item["item_key"]: item for item in packet["items"]}
    decisions_by_key = {
        decision["item_key"]: decision for decision in sample["decisions"]
    }
    for item_key, decision in decisions_by_key.items():
        assert set(decision) == {
            "item_key",
            "item_fingerprint",
            "action",
            "reason",
        }
        assert decision["item_fingerprint"] == items_by_key[item_key][
            "item_fingerprint"
        ]
        assert decision["reason"]
    assert decisions_by_key["product_system_sources"]["action"] == (
        "request_correction"
    )
    assert all(
        decision["action"] == "approve"
        for item_key, decision in decisions_by_key.items()
        if item_key != "product_system_sources"
    )


def test_artifact_replace_failure_preserves_other_complete_packet_and_cleans_temp(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.hxy_knowledge import core10_activation

    first_paths = core10_activation.write_core10_activation_artifacts(
        tmp_path,
        _packet(),
    )
    first_target = first_paths["packet_json"].parent
    before = {path.name: path.read_bytes() for path in first_target.iterdir()}
    changed = _packet(product_authority_version=3)
    changed_target = tmp_path / (
        f"core10-activation-{changed['packet_fingerprint'][:12]}"
    )

    def fail_replace(_source: object, _target: object) -> None:
        raise OSError("simulated atomic publish failure")

    monkeypatch.setattr(core10_activation.os, "replace", fail_replace)

    with pytest.raises(OSError, match="simulated atomic publish failure"):
        core10_activation.write_core10_activation_artifacts(tmp_path, changed)

    assert first_target.is_dir()
    assert {path.name: path.read_bytes() for path in first_target.iterdir()} == before
    assert not changed_target.exists()
    assert list(tmp_path.iterdir()) == [first_target]


def test_existing_target_conflict_is_rejected_without_overwrite(
    tmp_path: Path,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        write_core10_activation_artifacts,
    )

    packet = _packet()
    target = tmp_path / (
        f"core10-activation-{packet['packet_fingerprint'][:12]}"
    )
    target.mkdir()
    (target / "packet.json").write_text(
        json.dumps({"packet_fingerprint": "f" * 64}),
        encoding="utf-8",
    )
    (target / "packet.md").write_text("existing packet", encoding="utf-8")
    (target / "decisions.sample.json").write_text("{}", encoding="utf-8")
    before = {path.name: path.read_bytes() for path in target.iterdir()}

    with pytest.raises(ValueError, match="conflict"):
        write_core10_activation_artifacts(tmp_path, packet)

    assert {path.name: path.read_bytes() for path in target.iterdir()} == before


def test_incomplete_existing_target_is_rejected_without_repair(
    tmp_path: Path,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        write_core10_activation_artifacts,
    )

    packet = _packet()
    target = tmp_path / (
        f"core10-activation-{packet['packet_fingerprint'][:12]}"
    )
    target.mkdir()
    packet_path = target / "packet.json"
    packet_path.write_text(json.dumps(packet), encoding="utf-8")

    with pytest.raises(ValueError, match="conflict"):
        write_core10_activation_artifacts(tmp_path, packet)

    assert {path.name for path in target.iterdir()} == {"packet.json"}
    assert json.loads(packet_path.read_text(encoding="utf-8")) == packet


def test_existing_complete_artifact_is_reused_idempotently(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.hxy_knowledge import core10_activation

    packet = _packet()
    first = core10_activation.write_core10_activation_artifacts(tmp_path, packet)
    before = {key: path.read_bytes() for key, path in first.items()}

    def unexpected_replace(_source: object, _target: object) -> None:
        raise AssertionError("idempotent reuse must not publish another directory")

    monkeypatch.setattr(core10_activation.os, "replace", unexpected_replace)

    second = core10_activation.write_core10_activation_artifacts(tmp_path, packet)

    assert second == first
    assert {key: path.read_bytes() for key, path in second.items()} == before
    assert list(tmp_path.iterdir()) == [first["packet_json"].parent]
