from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


def test_discover_inbox_materials_returns_hash_stable_tasks(tmp_path):
    from hxy_knowledge.ingest_loop import discover_inbox_materials

    inbox = tmp_path / "knowledge" / "raw" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "brand.md").write_text("荷小悦是社区轻养生项目。", encoding="utf-8")

    result = discover_inbox_materials(inbox, root_dir=tmp_path)

    assert result["version"] == "hxy-ingest-discovery.v1"
    assert result["count"] == 1
    task = result["items"][0]
    assert task["version"] == "hxy-ingest-task.v1"
    assert task["status"] == "DISCOVERED"
    assert task["source_path"] == "knowledge/raw/inbox/brand.md"
    assert task["content_hash"]
    assert task["official_use_allowed"] is False
    assert task["requires_human_review"] is True


def test_discover_inbox_materials_tracks_parse_readiness_and_ignores_scripts(tmp_path):
    from hxy_knowledge.ingest_loop import discover_inbox_materials

    inbox = tmp_path / "knowledge" / "raw" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "brand.md").write_text("荷小悦是社区轻养生项目。", encoding="utf-8")
    (inbox / "deck.pdf").write_bytes(b"%PDF-1.4 placeholder")
    (inbox / "danger.bat").write_text("echo do-not-ingest", encoding="utf-8")

    result = discover_inbox_materials(inbox, root_dir=tmp_path)

    assert result["count"] == 2
    assert result["compiler_ready_count"] == 1
    assert result["parsing_required_count"] == 1
    assert result["ignored_count"] == 1

    tasks = {item["source_path"]: item for item in result["items"]}
    text_task = tasks["knowledge/raw/inbox/brand.md"]
    assert text_task["status"] == "DISCOVERED"
    assert text_task["compiler_ready"] is True
    assert text_task["parse_status"] == "compiler_ready"
    assert text_task["parser_hint"] == "hxy_text_compiler"

    pdf_task = tasks["knowledge/raw/inbox/deck.pdf"]
    assert pdf_task["status"] == "PARSING_REQUIRED"
    assert pdf_task["compiler_ready"] is False
    assert pdf_task["parse_status"] == "external_parser_required"
    assert pdf_task["parser_hint"] == "mineru_or_markitdown_required"

    ignored = result["ignored_items"][0]
    assert ignored["source_path"] == "knowledge/raw/inbox/danger.bat"
    assert ignored["reason"] == "unsupported_or_unsafe_suffix"


def test_run_ingest_loop_compiles_and_stops_at_review(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    raw_dir.mkdir(parents=True)
    (raw_dir / "brand.md").write_text(
        "荷小悦定位是社区轻养生。员工不能说治疗失眠。",
        encoding="utf-8",
    )

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        report_path=report_path,
        runs_dir=runs_dir,
        run_id="ingest-loop-test",
        root_dir=tmp_path,
    )

    assert state["version"] == "hxy-ingest-loop-state.v1"
    assert state["status"] == "review_required"
    assert state["stop_reason"] == "human_review_required"
    assert state["official_use_allowed"] is False
    assert state["task_count"] == 1
    assert state["claim_count"] >= 1
    assert state["review_queue_count"] >= 1
    assert "compliance_review_count" in state
    assert state["compliance_review_count"] >= 1
    assert state["tasks"][0]["artifact_refs"]["compliance_review_pack"].endswith("compliance-review-pack.json")
    assert (wiki_dir / "compliance-review-pack.json").exists()
    assert report_path.exists()
    assert (runs_dir / "ingest-loop-test" / "loop-state.json").exists()


def test_run_ingest_loop_separates_compiler_ready_and_parsing_required_tasks(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    raw_dir.mkdir(parents=True)
    (raw_dir / "risk.md").write_text("员工不能说治疗失眠，不能承诺一定有效。", encoding="utf-8")
    (raw_dir / "finance.docx").write_bytes(b"PK placeholder")

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        report_path=report_path,
        runs_dir=runs_dir,
        run_id="ingest-loop-test",
        root_dir=tmp_path,
    )

    assert state["task_count"] == 2
    assert state["compiler_ready_count"] == 1
    assert state["parsing_required_count"] == 1
    assert state["ignored_count"] == 0
    assert state["claim_count"] >= 1

    tasks = {item["source_path"]: item for item in state["tasks"]}
    assert tasks["knowledge/raw/inbox/risk.md"]["status"] == "REVIEWING"
    assert tasks["knowledge/raw/inbox/risk.md"]["compiler_ready"] is True
    assert tasks["knowledge/raw/inbox/finance.docx"]["status"] == "PARSING_REQUIRED"
    assert tasks["knowledge/raw/inbox/finance.docx"]["compiler_ready"] is False
    assert tasks["knowledge/raw/inbox/finance.docx"]["artifact_refs"] == {}
    assert "先解析 PDF/DOCX/PPTX/图片等非文本资料，再进入编译。" in state["next_actions"]


def test_ingest_loop_cli_writes_state(tmp_path):
    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    raw_dir.mkdir(parents=True)
    (raw_dir / "brand.md").write_text("荷小悦品牌资料。", encoding="utf-8")
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run-hxy-ingest-loop.py",
            "--raw-dir",
            str(raw_dir),
            "--wiki-dir",
            str(tmp_path / "knowledge" / "wiki"),
            "--report",
            str(report_path),
            "--runs-dir",
            str(runs_dir),
            "--run-id",
            "ingest-loop-test",
            "--root-dir",
            str(tmp_path),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    state = json.loads((runs_dir / "ingest-loop-test" / "loop-state.json").read_text(encoding="utf-8"))
    assert state["status"] == "review_required"
