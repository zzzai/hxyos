from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _bind_reference_to_source(reference: Path, source: Path, source_path: str) -> None:
    from hxy_knowledge.parser_adapter import reference_manifest_path

    manifest_path = reference_manifest_path(reference)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "version": "hxy-parser-reference.v1",
                "source_path": source_path,
                "source_content_hash": _hash_file(source),
                "reference_content_hash": _hash_file(reference),
                "parser": "markitdown",
                "quality": {
                    "version": "hxy-parser-quality.v1",
                    "status": "usable",
                    "needs_fallback": False,
                    "source_path": source_path,
                    "parser_strategy": "markitdown",
                },
                "official_use_allowed": False,
            }
        ),
        encoding="utf-8",
    )


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
    assert task["requires_human_review"] is False


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
    assert pdf_task["parser_hint"] == "markitdown_required"

    ignored = result["ignored_items"][0]
    assert ignored["source_path"] == "knowledge/raw/inbox/danger.bat"
    assert ignored["reason"] == "unsupported_or_unsafe_suffix"


def test_discover_inbox_materials_marks_duplicate_files_without_losing_traceability(tmp_path):
    from hxy_knowledge.ingest_loop import discover_inbox_materials

    inbox = tmp_path / "knowledge" / "raw" / "inbox"
    inbox.mkdir(parents=True)
    (inbox / "a.md").write_text("荷小悦是社区轻养生项目。", encoding="utf-8")
    (inbox / "b.md").write_text("荷小悦是社区轻养生项目。", encoding="utf-8")
    (inbox / "c.md").write_text("清泡调补养不能说治疗。", encoding="utf-8")

    result = discover_inbox_materials(inbox, root_dir=tmp_path)

    assert result["count"] == 3
    assert result["unique_count"] == 2
    assert result["duplicate_count"] == 1
    assert result["duplicate_groups"] == [
        {
            "content_hash": result["items"][0]["content_hash"],
            "canonical_source_path": "knowledge/raw/inbox/a.md",
            "duplicates": ["knowledge/raw/inbox/b.md"],
        }
    ]

    tasks = {item["source_path"]: item for item in result["items"]}
    assert tasks["knowledge/raw/inbox/a.md"]["duplicate_of"] is None
    assert tasks["knowledge/raw/inbox/a.md"]["canonical_source_path"] == "knowledge/raw/inbox/a.md"
    assert tasks["knowledge/raw/inbox/b.md"]["duplicate_of"] == "knowledge/raw/inbox/a.md"
    assert tasks["knowledge/raw/inbox/b.md"]["canonical_source_path"] == "knowledge/raw/inbox/a.md"


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
    assert state["status"] == "candidate_ready"
    assert state["stop_reason"] == "candidate_knowledge_not_promoted"
    assert state["requires_human_review"] is False
    assert state["promotion_review_pending"] is True
    assert state["official_use_allowed"] is False
    assert state["task_count"] == 1
    assert state["claim_count"] >= 1
    assert "claim_triage_cluster_count" in state
    assert "claim_triage_selected_count" in state
    assert "claim_triage_reduction_count" in state
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
    assert tasks["knowledge/raw/inbox/risk.md"]["status"] == "COMPILED"
    assert tasks["knowledge/raw/inbox/risk.md"]["compiler_ready"] is True
    assert tasks["knowledge/raw/inbox/finance.docx"]["status"] == "PARSING_REQUIRED"
    assert tasks["knowledge/raw/inbox/finance.docx"]["compiler_ready"] is False
    assert tasks["knowledge/raw/inbox/finance.docx"]["artifact_refs"] == {}
    assert "先解析 PDF/DOCX/PPTX/图片等非文本资料，再进入编译。" in state["next_actions"]


def test_run_ingest_loop_skips_duplicate_text_compilation_and_builds_parser_jobs(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    raw_dir.mkdir(parents=True)
    duplicate_text = "荷小悦定位是社区轻养生。员工不能说治疗失眠。"
    (raw_dir / "brand-a.md").write_text(duplicate_text, encoding="utf-8")
    (raw_dir / "brand-b.md").write_text(duplicate_text, encoding="utf-8")
    (raw_dir / "deck.pdf").write_bytes(b"%PDF-1.4 placeholder")
    (raw_dir / "plan.docx").write_bytes(b"PK placeholder")
    (raw_dir / "photo.png").write_bytes(b"\x89PNG placeholder")

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        report_path=report_path,
        runs_dir=runs_dir,
        run_id="ingest-loop-test",
        root_dir=tmp_path,
    )

    assert state["task_count"] == 5
    assert state["unique_count"] == 4
    assert state["duplicate_count"] == 1
    assert state["compiler_ready_count"] == 2
    assert state["compiler_ready_unique_count"] == 1
    assert state["extract_count"] == 1
    assert state["parsing_required_count"] == 3

    tasks = {item["source_path"]: item for item in state["tasks"]}
    assert tasks["knowledge/raw/inbox/brand-a.md"]["status"] == "COMPILED"
    assert tasks["knowledge/raw/inbox/brand-b.md"]["status"] == "DUPLICATE"
    assert tasks["knowledge/raw/inbox/brand-b.md"]["artifact_refs"] == {}
    assert tasks["knowledge/raw/inbox/brand-b.md"]["duplicate_of"] == "knowledge/raw/inbox/brand-a.md"

    assert state["parser_job_count"] == 3
    jobs = {item["source_path"]: item for item in state["parser_jobs"]}
    assert jobs["knowledge/raw/inbox/deck.pdf"]["parser_strategy"] == "markitdown"
    assert jobs["knowledge/raw/inbox/plan.docx"]["parser_strategy"] == "markitdown"
    assert jobs["knowledge/raw/inbox/photo.png"]["parser_strategy"] == "ocr_or_vision"
    assert all(job["status"] == "PENDING" for job in state["parser_jobs"])
    assert all(job["official_use_allowed"] is False for job in state["parser_jobs"])
    assert all(job["requires_human_review"] is False for job in state["parser_jobs"])


def test_run_ingest_loop_compiles_extracted_reference_and_skips_completed_parser_job(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "plan.docx"
    source.write_bytes(b"PK placeholder")
    reference = raw_dir / "extracted-reference" / "knowledge" / "raw" / "inbox" / "plan.docx.reference.txt"
    reference.parent.mkdir(parents=True)
    reference.write_text("荷小悦 DOCX 解析文本。员工不能说治疗失眠。", encoding="utf-8")
    _bind_reference_to_source(reference, source, "knowledge/raw/inbox/plan.docx")

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        report_path=report_path,
        runs_dir=runs_dir,
        run_id="ingest-loop-test",
        root_dir=tmp_path,
    )

    assert state["task_count"] == 1
    assert state["parsed_reference_count"] == 1
    assert state["parser_job_count"] == 0
    assert state["compiler_ready_unique_count"] == 0
    assert state["extract_count"] == 1
    assert state["claim_count"] >= 1

    tasks = {item["source_path"]: item for item in state["tasks"]}
    docx_task = tasks["knowledge/raw/inbox/plan.docx"]
    assert docx_task["status"] == "PARSED_REFERENCE_READY"
    assert docx_task["parse_status"] == "extracted_reference_available"
    assert docx_task["artifact_refs"]["extracted_reference"].endswith("plan.docx.reference.txt")

    assert all("extracted-reference/" not in path for path in tasks)


def test_run_ingest_loop_rejects_reference_not_bound_to_current_source(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    raw_dir.mkdir(parents=True)
    (raw_dir / "plan.docx").write_bytes(b"current source")
    reference = raw_dir / "extracted-reference" / "knowledge" / "raw" / "inbox" / "plan.docx.reference.txt"
    reference.parent.mkdir(parents=True)
    reference.write_text("这是旧版本的解析文本，不应进入编译层。", encoding="utf-8")
    from hxy_knowledge.parser_adapter import reference_manifest_path

    manifest_path = reference_manifest_path(reference)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "version": "hxy-parser-reference.v1",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "source_content_hash": "0" * 64,
                "reference_content_hash": "0" * 64,
                "parser": "markitdown",
            }
        ),
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

    tasks = {item["source_path"]: item for item in state["tasks"]}
    source_task = tasks["knowledge/raw/inbox/plan.docx"]
    assert source_task["status"] == "PARSING_REQUIRED"
    assert source_task["parse_status"] == "external_parser_required"
    assert source_task["artifact_refs"] == {}
    assert state["parsed_reference_count"] == 0
    assert state["parser_job_count"] == 1
    assert state["extract_count"] == 0
    assert all("extracted-reference/" not in path for path in tasks)


def test_run_ingest_loop_rejects_reference_with_incomplete_quality_manifest(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop
    from hxy_knowledge.parser_adapter import reference_manifest_path

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "plan.docx"
    source.write_bytes(b"current source")
    source_path = "knowledge/raw/inbox/plan.docx"
    reference = raw_dir / "extracted-reference" / f"{source_path}.reference.txt"
    reference.parent.mkdir(parents=True)
    reference.write_text("缺少质量证据的旧解析文本不能进入编译层。", encoding="utf-8")
    manifest_path = reference_manifest_path(reference)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(
            {
                "version": "hxy-parser-reference.v1",
                "source_path": source_path,
                "source_content_hash": _hash_file(source),
                "reference_content_hash": _hash_file(reference),
                "parser": "markitdown",
            }
        ),
        encoding="utf-8",
    )

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        report_path=report_path,
        runs_dir=runs_dir,
        run_id="incomplete-reference-manifest",
        root_dir=tmp_path,
    )

    task = {item["source_path"]: item for item in state["tasks"]}[source_path]
    assert task["parse_status"] == "external_parser_required"
    assert state["parsed_reference_count"] == 0
    assert state["extract_count"] == 0


def test_run_ingest_loop_accepts_legacy_extracted_reference_location(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "deck.pdf"
    source.write_bytes(b"%PDF-1.4 placeholder")
    reference = raw_dir / "extracted-reference" / "deck.pdf.reference.txt"
    reference.parent.mkdir(parents=True)
    reference.write_text("荷小悦 PDF 解析文本。不能承诺治疗。", encoding="utf-8")
    _bind_reference_to_source(reference, source, "knowledge/raw/inbox/deck.pdf")

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        report_path=report_path,
        runs_dir=runs_dir,
        run_id="ingest-loop-test",
        root_dir=tmp_path,
    )

    tasks = {item["source_path"]: item for item in state["tasks"]}
    pdf_task = tasks["knowledge/raw/inbox/deck.pdf"]
    assert pdf_task["status"] == "PARSED_REFERENCE_READY"
    assert pdf_task["artifact_refs"]["extracted_reference"] == "knowledge/raw/inbox/extracted-reference/deck.pdf.reference.txt"
    assert state["parser_job_count"] == 0
    assert state["parsed_reference_count"] == 1
    assert state["extract_count"] == 1


def test_run_ingest_loop_accepts_legacy_stem_extracted_reference_location(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    raw_dir.mkdir(parents=True)
    source = raw_dir / "deck.pdf"
    source.write_bytes(b"%PDF-1.4 placeholder")
    reference = raw_dir / "extracted-reference" / "deck.reference.txt"
    reference.parent.mkdir(parents=True)
    reference.write_text("荷小悦 PDF 解析文本。不能承诺治疗。", encoding="utf-8")
    _bind_reference_to_source(reference, source, "knowledge/raw/inbox/deck.pdf")

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        report_path=report_path,
        runs_dir=runs_dir,
        run_id="ingest-loop-test",
        root_dir=tmp_path,
    )

    tasks = {item["source_path"]: item for item in state["tasks"]}
    pdf_task = tasks["knowledge/raw/inbox/deck.pdf"]
    assert pdf_task["status"] == "PARSED_REFERENCE_READY"
    assert pdf_task["artifact_refs"]["extracted_reference"] == "knowledge/raw/inbox/extracted-reference/deck.reference.txt"
    assert state["parser_job_count"] == 0
    assert state["parsed_reference_count"] == 1
    assert state["extract_count"] == 1


def test_run_ingest_loop_does_not_create_reference_of_reference_tasks(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    raw_dir.mkdir(parents=True)
    long_name = f"{'荷小悦品牌资产参考书' * 8}.epub"
    source = raw_dir / long_name
    source.write_bytes(b"epub placeholder")
    reference = raw_dir / "extracted-reference" / f"{Path(long_name).stem}.reference.txt"
    reference.parent.mkdir(parents=True)
    reference.write_text("荷小悦参考书解析文本。不能承诺治疗。", encoding="utf-8")
    _bind_reference_to_source(reference, source, f"knowledge/raw/inbox/{long_name}")

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        report_path=report_path,
        runs_dir=runs_dir,
        run_id="ingest-loop-test",
        root_dir=tmp_path,
    )

    assert state["task_count"] == 1
    assert state["parser_job_count"] == 0
    assert all(
        not item["source_path"].endswith(".reference.txt.reference.txt")
        for item in state["tasks"]
    )
    assert all("extracted-reference/" not in item["source_path"] for item in state["tasks"])


def test_run_ingest_loop_ignores_parser_run_manifest_in_extracted_reference(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    wiki_dir = tmp_path / "knowledge" / "wiki"
    report_path = tmp_path / "knowledge" / "reports" / "ingest-latest.json"
    runs_dir = tmp_path / "knowledge" / "runs"
    manifest = raw_dir / "extracted-reference" / "parser-run-manifest.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"version":"hxy-parser-run.v1"}', encoding="utf-8")

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=wiki_dir,
        report_path=report_path,
        runs_dir=runs_dir,
        run_id="ingest-loop-test",
        root_dir=tmp_path,
    )

    assert state["task_count"] == 0
    assert state["parser_job_count"] == 0
    assert state["ignored_count"] == 1
    assert state["ignored_items"][0]["source_path"] == "knowledge/raw/inbox/extracted-reference/parser-run-manifest.json"


def test_discovery_routes_all_supported_image_suffixes_consistently(tmp_path):
    from hxy_knowledge.ingest_loop import discover_inbox_materials

    inbox = tmp_path / "knowledge" / "raw" / "inbox"
    inbox.mkdir(parents=True)
    suffixes = [".jpeg", ".jpg", ".png", ".webp", ".gif", ".bmp", ".tif", ".tiff"]
    for index, suffix in enumerate(suffixes):
        (inbox / f"image-{index}{suffix}").write_bytes(f"image-{index}".encode("ascii"))

    discovery = discover_inbox_materials(inbox, root_dir=tmp_path)

    assert discovery["count"] == len(suffixes)
    assert discovery["ignored_count"] == 0
    assert {item["suffix"] for item in discovery["items"]} == set(suffixes)
    assert all(item["parser_plan"]["primary"] == "ocr_or_vision" for item in discovery["items"])
    assert all(item["requires_human_review"] is False for item in discovery["items"])


def test_run_ingest_loop_requires_human_only_for_manual_parser_exception(tmp_path):
    from hxy_knowledge.ingest_loop import run_ingest_loop

    raw_dir = tmp_path / "knowledge" / "raw" / "inbox"
    raw_dir.mkdir(parents=True)
    (raw_dir / "legacy.ppt").write_bytes(b"legacy presentation")

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=tmp_path / "knowledge" / "wiki",
        report_path=tmp_path / "knowledge" / "reports" / "ingest-latest.json",
        runs_dir=tmp_path / "knowledge" / "runs",
        run_id="manual-exception",
        root_dir=tmp_path,
    )

    assert state["status"] == "review_required"
    assert state["stop_reason"] == "parser_exception_requires_human"
    assert state["requires_human_review"] is True
    assert state["tasks"][0]["requires_human_review"] is True
    assert state["parser_jobs"][0]["requires_human_review"] is True


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
    assert state["status"] == "completed"
