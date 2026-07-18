from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any

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
    assert packet["preview_only"] is True


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
    assert sample["official_use_allowed"] is False
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
    assert all(
        decision["action"] == "request_correction"
        for decision in decisions_by_key.values()
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


def test_loader_returns_the_packet_snapshot_that_passed_integrity_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from apps.api.hxy_knowledge import core10_activation

    packet = _packet()
    paths = core10_activation.write_core10_activation_artifacts(tmp_path, packet)
    packet_path = paths["packet_json"]
    tampered = json.loads(json.dumps(packet))
    tampered["items"][0]["why_needed"] = "unverified replacement"
    tampered_json = json.dumps(tampered, ensure_ascii=False)
    original_read_text = Path.read_text
    packet_reads = 0

    def replace_between_reads(path: Path, *args: object, **kwargs: object) -> str:
        nonlocal packet_reads
        if path == packet_path:
            packet_reads += 1
            if packet_reads == 1:
                return tampered_json
        return original_read_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", replace_between_reads)

    with pytest.raises(ValueError, match="artifact is invalid"):
        core10_activation.load_core10_activation_artifact(packet_path.parent)

    assert packet_reads == 1


def test_existing_artifact_with_tampered_packet_is_not_reused(
    tmp_path: Path,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        write_core10_activation_artifacts,
    )

    packet = _packet()
    paths = write_core10_activation_artifacts(tmp_path, packet)
    tampered = json.loads(paths["packet_json"].read_text(encoding="utf-8"))
    tampered["items"][0]["why_needed"] = "tampered content"
    paths["packet_json"].write_text(
        json.dumps(tampered, ensure_ascii=False),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="conflict"):
        write_core10_activation_artifacts(tmp_path, packet)


@pytest.mark.parametrize(
    ("artifact_key", "replacement"),
    [
        ("packet_markdown", "tampered markdown\n"),
        ("decision_sample", '{"tampered": true}\n'),
    ],
)
def test_existing_artifact_with_tampered_rendered_file_is_not_reused(
    tmp_path: Path,
    artifact_key: str,
    replacement: str,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        write_core10_activation_artifacts,
    )

    packet = _packet()
    paths = write_core10_activation_artifacts(tmp_path, packet)
    paths[artifact_key].write_text(replacement, encoding="utf-8")

    with pytest.raises(ValueError, match="conflict"):
        write_core10_activation_artifacts(tmp_path, packet)


def test_existing_artifact_with_overly_broad_permissions_is_not_reused(
    tmp_path: Path,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        write_core10_activation_artifacts,
    )

    packet = _packet()
    paths = write_core10_activation_artifacts(tmp_path, packet)
    paths["packet_json"].chmod(0o644)

    with pytest.raises(ValueError, match="conflict"):
        write_core10_activation_artifacts(tmp_path, packet)


def test_existing_artifact_with_tampered_generated_at_is_not_reused(
    tmp_path: Path,
) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        write_core10_activation_artifacts,
    )

    packet = _packet()
    paths = write_core10_activation_artifacts(tmp_path, packet)
    tampered = json.loads(paths["packet_json"].read_text(encoding="utf-8"))
    tampered["generated_at"] = "9999-12-31T23:59:59Z"
    paths["packet_json"].write_text(
        json.dumps(tampered, ensure_ascii=False, sort_keys=True),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="conflict"):
        write_core10_activation_artifacts(tmp_path, packet)


def test_writer_rejects_packet_mutated_after_fingerprinting(tmp_path: Path) -> None:
    from apps.api.hxy_knowledge.core10_activation import (
        write_core10_activation_artifacts,
    )

    packet = _packet()
    packet["items"][0]["why_needed"] = "secret postgresql://hidden.invalid/hxy"

    with pytest.raises(ValueError, match="fingerprint"):
        write_core10_activation_artifacts(tmp_path, packet)


@pytest.mark.parametrize(
    ("field", "unsafe_value"),
    [
        ("preview_only", False),
        ("write_to_database", True),
        ("publish_allowed", True),
        ("official_use_allowed", True),
        ("requires_founder_decision", False),
    ],
)
def test_writer_rejects_refingerprinted_unsafe_governance_contract(
    tmp_path: Path,
    field: str,
    unsafe_value: bool,
) -> None:
    from apps.api.hxy_knowledge import core10_activation

    packet = _packet()
    packet[field] = unsafe_value
    packet["packet_fingerprint"] = core10_activation._packet_fingerprint_digest(
        packet
    )
    packet["packet_id"] = (
        f"core10-activation:{packet['packet_fingerprint'][:12]}"
    )

    with pytest.raises(ValueError, match="governance"):
        core10_activation.write_core10_activation_artifacts(tmp_path, packet)


def test_writer_rejects_numeric_value_for_boolean_governance_flag(
    tmp_path: Path,
) -> None:
    from apps.api.hxy_knowledge import core10_activation

    packet = _packet()
    packet["preview_only"] = 1
    packet["packet_fingerprint"] = core10_activation._packet_fingerprint_digest(
        packet
    )
    packet["packet_id"] = (
        f"core10-activation:{packet['packet_fingerprint'][:12]}"
    )
    packet["artifact_fingerprint"] = (
        core10_activation._artifact_fingerprint_digest(packet)
    )

    with pytest.raises(ValueError, match="governance"):
        core10_activation.write_core10_activation_artifacts(tmp_path, packet)


def test_writer_rejects_invalid_generated_at_even_with_updated_artifact_digest(
    tmp_path: Path,
) -> None:
    from apps.api.hxy_knowledge import core10_activation

    packet = _packet()
    packet["generated_at"] = "not-a-utc-timestamp"
    packet["artifact_fingerprint"] = (
        core10_activation._artifact_fingerprint_digest(packet)
    )

    with pytest.raises(ValueError, match="generated_at"):
        core10_activation.write_core10_activation_artifacts(tmp_path, packet)


def test_writer_rejects_missing_generated_at(tmp_path: Path) -> None:
    from apps.api.hxy_knowledge import core10_activation

    packet = _packet()
    packet["generated_at"] = None
    packet["artifact_fingerprint"] = (
        core10_activation._artifact_fingerprint_digest(packet)
    )

    with pytest.raises(ValueError, match="generated_at"):
        core10_activation.write_core10_activation_artifacts(tmp_path, packet)


def _load_cli_module() -> Any:
    script_path = (
        Path(__file__).resolve().parents[1]
        / "scripts"
        / "build-hxy-core10-activation-packet.py"
    )
    spec = importlib.util.spec_from_file_location(
        "hxy_core10_activation_packet_cli_test",
        script_path,
    )
    if spec is None or spec.loader is None:
        raise AssertionError("could not load core10 activation CLI")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_cli_inputs(
    root: Path,
    *,
    selection_overrides: dict[str, Any] | None = None,
) -> dict[str, Path]:
    private_root = root / "data" / "private" / "core10-activation"
    drafts_root = private_root / "drafts"
    releases_root = root / "data" / "releases" / "authority-answer"
    drafts_root.mkdir(parents=True)
    releases_root.mkdir(parents=True)

    constitution_path = drafts_root / "constitution.json"
    reception_path = drafts_root / "reception.json"
    report_path = releases_root / "core-10-report.json"
    selection_path = private_root / "selection.json"
    constitution_path.write_text(
        json.dumps(_constitution_draft(), ensure_ascii=False),
        encoding="utf-8",
    )
    reception_path.write_text(
        json.dumps(_reception_draft(), ensure_ascii=False),
        encoding="utf-8",
    )
    report_path.write_text(
        json.dumps(_report(), ensure_ascii=False),
        encoding="utf-8",
    )
    selection: dict[str, Any] = {
        "constitution_draft_path": constitution_path.relative_to(root).as_posix(),
        "product_asset_ids": ["asset-product-001"],
        "operations_asset_ids": ["asset-operations-001"],
        "reception_draft_path": reception_path.relative_to(root).as_posix(),
    }
    selection.update(selection_overrides or {})
    selection_path.write_text(
        json.dumps(selection, ensure_ascii=False),
        encoding="utf-8",
    )
    return {
        "private_root": private_root,
        "report": report_path,
        "selection": selection_path,
        "constitution": constitution_path,
        "reception": reception_path,
    }


class _ReadOnlySnapshotRepository:
    created_with: list[str] = []
    snapshot_calls: list[dict[str, Any]] = []

    def __init__(self, database_url: str) -> None:
        self.created_with.append(database_url)

    def core10_activation_snapshot(self, **selection: Any) -> dict[str, Any]:
        self.snapshot_calls.append(selection)
        return {
            "product_sources": [_source("asset-product-001")],
            "operations_sources": [_source("asset-operations-001")],
            "approved_answer_cards": [],
        }


class _MissingConstitutionAdapter:
    def __init__(self, _root: Path) -> None:
        pass

    def load_active(self) -> SimpleNamespace:
        return SimpleNamespace(payload=None, reason="missing_active_version")


def test_cli_builds_packet_from_one_read_only_snapshot_without_leaking_content(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _load_cli_module()
    inputs = _write_cli_inputs(tmp_path)
    _ReadOnlySnapshotRepository.created_with = []
    _ReadOnlySnapshotRepository.snapshot_calls = []
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "KnowledgeRepository", _ReadOnlySnapshotRepository)
    monkeypatch.setattr(cli, "BrandConstitutionAdapter", _MissingConstitutionAdapter)
    database_url = "postgresql://snapshot.test/hxy"
    monkeypatch.setenv("HXY_TEST_DATABASE_URL", database_url)

    result = cli.main(
        [
            "--report",
            str(inputs["report"]),
            "--selection",
            str(inputs["selection"]),
            "--output-root",
            "data/private/core10-activation",
            "--database-url-env",
            "HXY_TEST_DATABASE_URL",
        ]
    )

    assert result == 0
    assert _ReadOnlySnapshotRepository.created_with == [database_url]
    assert _ReadOnlySnapshotRepository.snapshot_calls == [
        {
            "product_asset_ids": ["asset-product-001"],
            "operations_asset_ids": ["asset-operations-001"],
        }
    ]
    output = capsys.readouterr()
    assert output.err == ""
    assert "item_count=4" in output.out
    assert "preview_only=true" in output.out
    assert "write_to_database=false" in output.out
    assert "publish_allowed=false" in output.out
    assert "official_use_allowed=false" in output.out
    assert "status=ready_for_founder_decision" in output.out
    assert "packet.json" in output.out
    assert str(tmp_path) not in output.out
    assert database_url not in output.out
    assert "Fixture identity" not in output.out
    artifact_dirs = [
        path
        for path in inputs["private_root"].iterdir()
        if path.name.startswith("core10-activation-") and path.is_dir()
    ]
    assert len(artifact_dirs) == 1
    assert (artifact_dirs[0] / "packet.json").is_file()


def test_cli_reads_private_data_from_trusted_root_when_code_runs_from_release(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _load_cli_module()
    release_root = tmp_path / "releases" / "authority-answer" / "candidate"
    trusted_root = tmp_path / "hxy"
    release_root.mkdir(parents=True)
    inputs = _write_cli_inputs(trusted_root)
    _ReadOnlySnapshotRepository.created_with = []
    _ReadOnlySnapshotRepository.snapshot_calls = []

    class RecordingConstitutionAdapter(_MissingConstitutionAdapter):
        created_with: list[Path] = []

        def __init__(self, root: Path) -> None:
            self.created_with.append(root)

    monkeypatch.setattr(cli, "ROOT", release_root)
    monkeypatch.setattr(cli, "KnowledgeRepository", _ReadOnlySnapshotRepository)
    monkeypatch.setattr(cli, "BrandConstitutionAdapter", RecordingConstitutionAdapter)
    monkeypatch.setenv("HXY_ROOT_DIR", str(trusted_root))
    monkeypatch.setenv("HXY_TEST_DATABASE_URL", "postgresql://snapshot.test/hxy")

    result = cli.main(
        [
            "--report",
            str(inputs["report"]),
            "--selection",
            str(inputs["selection"]),
            "--output-root",
            "data/private/core10-activation",
            "--database-url-env",
            "HXY_TEST_DATABASE_URL",
        ]
    )

    assert result == 0
    assert RecordingConstitutionAdapter.created_with == [trusted_root]
    output = capsys.readouterr()
    assert output.err == ""
    assert str(trusted_root) not in output.out
    assert any(
        path.is_dir() and path.name.startswith("core10-activation-")
        for path in inputs["private_root"].iterdir()
    )


@pytest.mark.parametrize(
    "selection_overrides",
    [
        {"unknown_key": "not allowed"},
        {"product_asset_ids": [1]},
        {"operations_asset_ids": "asset-operations-001"},
    ],
)
def test_cli_rejects_invalid_selection_before_repository_access(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    selection_overrides: dict[str, Any],
) -> None:
    cli = _load_cli_module()
    inputs = _write_cli_inputs(
        tmp_path,
        selection_overrides=selection_overrides,
    )

    class UnexpectedRepository:
        def __init__(self, _database_url: str) -> None:
            raise AssertionError("repository must not be opened")

    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setattr(cli, "KnowledgeRepository", UnexpectedRepository)
    monkeypatch.setenv("HXY_DATABASE_URL", "postgresql://must-not-appear")

    assert cli.main(
        [
            "--report",
            str(inputs["report"]),
            "--selection",
            str(inputs["selection"]),
        ]
    ) == 2
    captured = capsys.readouterr()
    assert "must-not-appear" not in captured.err
    assert "invalid private input" in captured.err.lower()


def test_cli_rejects_draft_path_outside_private_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _load_cli_module()
    outside = tmp_path / "outside-draft.json"
    outside.write_text("{}", encoding="utf-8")
    inputs = _write_cli_inputs(
        tmp_path,
        selection_overrides={"constitution_draft_path": str(outside)},
    )
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setenv("HXY_DATABASE_URL", "postgresql://must-not-appear")

    assert cli.main(
        [
            "--report",
            str(inputs["report"]),
            "--selection",
            str(inputs["selection"]),
        ]
    ) == 2
    captured = capsys.readouterr()
    assert "invalid private input" in captured.err.lower()
    assert str(outside) not in captured.err
    assert "must-not-appear" not in captured.err


def test_cli_rejects_symlinked_selection_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _load_cli_module()
    inputs = _write_cli_inputs(tmp_path)
    selection_link = inputs["private_root"] / "selection-link.json"
    selection_link.symlink_to(inputs["selection"])
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setenv("HXY_DATABASE_URL", "postgresql://must-not-appear")

    assert cli.main(
        [
            "--report",
            str(inputs["report"]),
            "--selection",
            str(selection_link),
        ]
    ) == 2
    captured = capsys.readouterr()
    assert "invalid private input" in captured.err.lower()
    assert "must-not-appear" not in captured.err


def test_cli_rejects_report_outside_allowlisted_project_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _load_cli_module()
    inputs = _write_cli_inputs(tmp_path)
    outside_report = tmp_path / "outside-report.json"
    outside_report.write_text(json.dumps(_report()), encoding="utf-8")
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setenv("HXY_DATABASE_URL", "postgresql://must-not-appear")

    assert cli.main(
        [
            "--report",
            str(outside_report),
            "--selection",
            str(inputs["selection"]),
        ]
    ) == 2
    captured = capsys.readouterr()
    assert "invalid private input" in captured.err.lower()
    assert str(outside_report) not in captured.err
    assert "must-not-appear" not in captured.err


def test_cli_missing_database_env_fails_without_creating_artifacts_or_leaking_name(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _load_cli_module()
    inputs = _write_cli_inputs(tmp_path)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.delenv("HXY_MISSING_DATABASE_URL", raising=False)

    assert cli.main(
        [
            "--report",
            str(inputs["report"]),
            "--selection",
            str(inputs["selection"]),
            "--database-url-env",
            "HXY_MISSING_DATABASE_URL",
        ]
    ) == 2
    captured = capsys.readouterr()
    assert "database configuration is unavailable" in captured.err.lower()
    assert "HXY_MISSING_DATABASE_URL" not in captured.err
    assert not any(
        path.is_dir() and path.name.startswith("core10-activation-")
        for path in inputs["private_root"].iterdir()
    )


def test_cli_rejects_alternate_private_output_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    cli = _load_cli_module()
    inputs = _write_cli_inputs(tmp_path)
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    monkeypatch.setenv("HXY_DATABASE_URL", "postgresql://snapshot.test/hxy")

    assert cli.main(
        [
            "--report",
            str(inputs["report"]),
            "--selection",
            str(inputs["selection"]),
            "--output-root",
            "data/private/alternate-core10-output",
        ]
    ) == 2
    captured = capsys.readouterr()
    assert "invalid private input" in captured.err.lower()
