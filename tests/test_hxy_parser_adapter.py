from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def test_run_parser_jobs_marks_markitdown_missing_without_failing(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PK placeholder")
    output_dir = tmp_path / "extracted"

    result = run_parser_jobs(
        [
            {
                "version": "hxy-parser-job.v1",
                "job_id": "job-1",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "parser_strategy": "markitdown",
                "status": "PENDING",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
    )

    assert result["version"] == "hxy-parser-run.v1"
    assert result["processed_count"] == 0
    assert result["skipped_count"] == 1
    item = result["items"][0]
    assert item["status"] == "SKIPPED_DEPENDENCY_MISSING"
    assert item["dependency"] == "markitdown"
    assert item["official_use_allowed"] is False
    assert item["requires_human_review"] is True
    assert (output_dir / "parser-run-manifest.json").exists()


def test_run_parser_jobs_executes_markitdown_cli_and_writes_reference_artifact(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "path = pathlib.Path(sys.argv[1])\n"
        "print('解析结果: 荷小悦 DOCX 内容来自 ' + path.name)\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PK placeholder")
    output_dir = tmp_path / "extracted"

    result = run_parser_jobs(
        [
            {
                "version": "hxy-parser-job.v1",
                "job_id": "job-1",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "parser_strategy": "markitdown",
                "status": "PENDING",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
    )

    assert result["processed_count"] == 1
    assert result["failed_count"] == 0
    item = result["items"][0]
    assert item["status"] == "EXTRACTED"
    assert item["parser"] == "markitdown"
    assert item["output_path"].endswith("knowledge/raw/inbox/plan.docx.reference.txt")
    assert item["official_use_allowed"] is False
    assert item["requires_human_review"] is True

    output_path = Path(item["output_path"])
    assert output_path.exists()
    assert "解析结果: 荷小悦 DOCX 内容来自 plan.docx" in output_path.read_text(encoding="utf-8")

    manifest = json.loads((output_dir / "parser-run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["processed_count"] == 1
    assert manifest["items"][0]["source_path"] == "knowledge/raw/inbox/plan.docx"


def test_run_hxy_parser_jobs_cli_reads_ingest_loop_state(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "print('CLI 解析: ' + pathlib.Path(sys.argv[1]).name)\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PK placeholder")
    state_path = root / "knowledge" / "runs" / "ingest-loop-test" / "loop-state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "version": "hxy-ingest-loop-state.v1",
                "parser_jobs": [
                    {
                        "version": "hxy-parser-job.v1",
                        "job_id": "job-1",
                        "source_path": "knowledge/raw/inbox/plan.docx",
                        "parser_strategy": "markitdown",
                        "status": "PENDING",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            "scripts/run-hxy-parser-jobs.py",
            "--state",
            "knowledge/runs/ingest-loop-test/loop-state.json",
            "--output-dir",
            "knowledge/raw/inbox/extracted-reference",
            "--root-dir",
            str(root),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["processed_count"] == 1
    output_path = root / "knowledge" / "raw" / "inbox" / "extracted-reference" / "knowledge/raw/inbox/plan.docx.reference.txt"
    assert output_path.exists()
    assert "CLI 解析: plan.docx" in output_path.read_text(encoding="utf-8")


def test_api_requirements_pin_markitdown_for_parser_jobs():
    requirements = (Path(__file__).resolve().parents[1] / "apps" / "api" / "requirements.txt").read_text(
        encoding="utf-8"
    )

    assert "markitdown" in requirements
