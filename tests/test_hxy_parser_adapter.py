from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_run_parser_jobs_rejects_source_outside_hxy_inbox(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "print(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    secret = root / "ops" / "env" / "model.env"
    secret.parent.mkdir(parents=True)
    secret.write_text("MODEL_API_KEY=must-not-be-read", encoding="utf-8")
    output_dir = tmp_path / "extracted"

    result = run_parser_jobs(
        [
            {
                "job_id": "job-outside-inbox",
                "source_path": "ops/env/model.env",
                "parser_strategy": "markitdown",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
    )

    item = result["items"][0]
    assert item["status"] == "FAILED_INVALID_SOURCE"
    assert item["output_path"] is None
    assert not list(output_dir.rglob("*.reference.txt"))


def test_run_parser_jobs_rejects_backslash_path_before_building_output(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\nprint('should not run')\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    inbox = root / "knowledge" / "raw" / "inbox"
    inbox.mkdir(parents=True)
    unsafe_name = r"..\..\..\..\escaped.docx"
    (inbox / unsafe_name).write_bytes(b"PK placeholder")
    output_dir = tmp_path / "extracted"
    escaped_output = output_dir.parent / "escaped.docx.reference.txt"

    result = run_parser_jobs(
        [
            {
                "job_id": "job-backslash-output",
                "source_path": f"knowledge/raw/inbox/{unsafe_name}",
                "parser_strategy": "markitdown",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
    )

    assert result["items"][0]["status"] == "FAILED_INVALID_SOURCE"
    assert not escaped_output.exists()


def test_run_parser_jobs_marks_markitdown_missing_without_failing(tmp_path, monkeypatch):
    import hxy_knowledge.parser_adapter as parser_adapter

    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setattr(parser_adapter.sys, "executable", str(tmp_path / "empty-bin" / "python"))
    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PK placeholder")
    output_dir = tmp_path / "extracted"

    result = parser_adapter.run_parser_jobs(
        [
            {
                "version": "hxy-parser-job.v1",
                "job_id": "job-1",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "content_hash": _sha256(source),
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


def test_run_parser_jobs_finds_cli_next_to_active_python(tmp_path, monkeypatch):
    import hxy_knowledge.parser_adapter as parser_adapter

    bin_dir = tmp_path / "venv" / "bin"
    bin_dir.mkdir(parents=True)
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/bin/sh\n"
        "printf '%s\\n' '虚拟环境内的 MarkItDown 解析结果足够完整。'\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path / "empty-path"))
    monkeypatch.setattr(parser_adapter.sys, "executable", str(bin_dir / "python"))

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PK placeholder")

    result = parser_adapter.run_parser_jobs(
        [
            {
                "job_id": "job-venv-cli",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "content_hash": _sha256(source),
                "parser_strategy": "markitdown",
            }
        ],
        root_dir=root,
        output_dir=tmp_path / "extracted",
    )

    assert result["processed_count"] == 1
    assert result["items"][0]["parser"] == "markitdown"


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
    source_hash = _sha256(source)
    output_dir = tmp_path / "extracted"

    result = run_parser_jobs(
        [
            {
                "version": "hxy-parser-job.v1",
                "job_id": "job-1",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "content_hash": source_hash,
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
    assert item["requires_human_review"] is False
    assert item["source_content_hash"] == source_hash
    assert result["requires_human_review"] is False
    assert result["authority_rule"] == "parser_outputs_are_non_authoritative_and_review_is_exception_based"

    output_path = Path(item["output_path"])
    assert output_path.exists()
    assert "解析结果: 荷小悦 DOCX 内容来自 plan.docx" in output_path.read_text(encoding="utf-8")
    reference_manifest = json.loads(
        Path(item["reference_manifest_path"]).read_text(encoding="utf-8")
    )
    assert reference_manifest["source_path"] == "knowledge/raw/inbox/plan.docx"
    assert reference_manifest["source_content_hash"] == source_hash
    assert reference_manifest["reference_content_hash"] == _sha256(output_path)
    assert reference_manifest["parser"] == "markitdown"

    manifest = json.loads((output_dir / "parser-run-manifest.json").read_text(encoding="utf-8"))
    assert manifest["processed_count"] == 1
    assert manifest["items"][0]["source_path"] == "knowledge/raw/inbox/plan.docx"


def test_run_parser_jobs_rejects_stale_job_hash_before_parser_execution(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "parser-ran"
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
        "print('unexpected parse')\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"new source version")

    result = run_parser_jobs(
        [
            {
                "job_id": "job-stale-hash",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "content_hash": "0" * 64,
                "parser_strategy": "markitdown",
            }
        ],
        root_dir=root,
        output_dir=tmp_path / "extracted",
    )

    assert result["items"][0]["status"] == "FAILED_SOURCE_HASH_MISMATCH"
    assert not marker.exists()


def test_run_parser_jobs_rejects_missing_or_malformed_source_hash_before_execution(
    tmp_path,
    monkeypatch,
):
    import hxy_knowledge.parser_adapter as parser_adapter

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    marker = tmp_path / "parser-ran"
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib\n"
        f"pathlib.Path({str(marker)!r}).write_text('ran', encoding='utf-8')\n"
        "print('unexpected parse')\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source version one")

    result = parser_adapter.run_parser_jobs(
        [
            {
                "job_id": "job-missing-hash",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "parser_strategy": "markitdown",
            },
            {
                "job_id": "job-invalid-hash",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "content_hash": "not-a-sha256",
                "parser_strategy": "markitdown",
            },
        ],
        root_dir=root,
        output_dir=tmp_path / "extracted",
    )

    assert [item["status"] for item in result["items"]] == [
        "FAILED_MISSING_SOURCE_HASH",
        "FAILED_INVALID_SOURCE_HASH",
    ]
    assert not marker.exists()


def test_parser_subprocess_receives_isolated_copy_instead_of_raw_source(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "source = pathlib.Path(sys.argv[1])\n"
        "source.write_bytes(b'parser-mutated-copy')\n"
        "print('解析器只修改了隔离副本，原始资料保持不变。')\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    original = b"immutable raw source"
    source.write_bytes(original)

    result = run_parser_jobs(
        [
            {
                "job_id": "job-isolated-input",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "content_hash": _sha256(source),
                "parser_strategy": "markitdown",
            }
        ],
        root_dir=root,
        output_dir=tmp_path / "extracted",
    )

    assert result["items"][0]["status"] == "EXTRACTED"
    assert source.read_bytes() == original


def test_run_parser_jobs_isolates_source_mutations_made_by_parser(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "source = pathlib.Path(sys.argv[1])\n"
        "source.write_bytes(source.read_bytes() + b'-changed')\n"
        "print('解析结果不应被采用')\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source version one")
    source_hash = _sha256(source)
    output_dir = tmp_path / "extracted"

    result = run_parser_jobs(
        [
            {
                "job_id": "job-source-changed",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "content_hash": source_hash,
                "parser_strategy": "markitdown",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
    )

    assert result["items"][0]["status"] == "EXTRACTED"
    assert _sha256(source) == source_hash
    assert source.read_bytes() == b"source version one"
    assert (output_dir / "knowledge/raw/inbox/plan.docx.reference.txt").exists()


def test_run_parser_jobs_marks_mineru_missing_without_failing(tmp_path, monkeypatch):
    import hxy_knowledge.parser_adapter as parser_adapter

    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setattr(parser_adapter.sys, "executable", str(tmp_path / "empty-bin" / "python"))
    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "brand.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF placeholder")
    output_dir = tmp_path / "extracted"

    result = parser_adapter.run_parser_jobs(
        [
            {
                "version": "hxy-parser-job.v1",
                "job_id": "job-pdf-1",
                "source_path": "knowledge/raw/inbox/brand.pdf",
                "content_hash": _sha256(source),
                "parser_strategy": "mineru",
                "status": "PENDING",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
        strategies={"mineru"},
    )

    assert result["processed_count"] == 0
    assert result["skipped_count"] == 1
    item = result["items"][0]
    assert item["status"] == "SKIPPED_DEPENDENCY_MISSING"
    assert item["dependency"] == "mineru"
    assert item["official_use_allowed"] is False
    assert item["requires_human_review"] is True


def test_run_parser_jobs_executes_mineru_cli_and_writes_reference_artifact(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_mineru = bin_dir / "mineru"
    fake_mineru.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "assert sys.argv[sys.argv.index('-b') + 1] == 'pipeline'\n"
        "assert sys.argv[sys.argv.index('-m') + 1] == 'auto'\n"
        "source = pathlib.Path(sys.argv[sys.argv.index('-p') + 1])\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "artifact = out / source.stem / (source.stem + '.md')\n"
        "artifact.parent.mkdir(parents=True, exist_ok=True)\n"
        "artifact.write_text('# 荷小悦 PDF 解析\\n\\n来自 ' + source.name, encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_mineru.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "brand.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF placeholder")
    output_dir = tmp_path / "extracted"

    result = run_parser_jobs(
        [
            {
                "version": "hxy-parser-job.v1",
                "job_id": "job-pdf-1",
                "source_path": "knowledge/raw/inbox/brand.pdf",
                "content_hash": _sha256(source),
                "parser_strategy": "mineru",
                "status": "PENDING",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
        strategies={"mineru"},
    )

    assert result["processed_count"] == 1
    assert result["failed_count"] == 0
    item = result["items"][0]
    assert item["status"] == "EXTRACTED"
    assert item["parser"] == "mineru"
    assert item["output_path"].endswith("knowledge/raw/inbox/brand.pdf.reference.txt")
    assert item["official_use_allowed"] is False
    assert item["requires_human_review"] is False
    assert result["requires_human_review"] is False

    output_path = Path(item["output_path"])
    assert output_path.exists()
    assert "来自 brand.pdf" in output_path.read_text(encoding="utf-8")


def test_run_parser_jobs_does_not_reuse_mineru_artifact_from_previous_attempt(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    counter = tmp_path / "mineru-counter"
    fake_mineru = bin_dir / "mineru"
    fake_mineru.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        f"counter = pathlib.Path({str(counter)!r})\n"
        "source = pathlib.Path(sys.argv[sys.argv.index('-p') + 1])\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "if not counter.exists():\n"
        "    counter.write_text('1', encoding='utf-8')\n"
        "    artifact = out / source.stem / (source.stem + '.md')\n"
        "    artifact.parent.mkdir(parents=True, exist_ok=True)\n"
        "    artifact.write_text('# 第一次解析\\n\\n本次产物有效。', encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_mineru.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "brand.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF placeholder")
    output_dir = tmp_path / "extracted"
    job = {
        "job_id": "same-mineru-job",
        "source_path": "knowledge/raw/inbox/brand.pdf",
        "content_hash": _sha256(source),
        "parser_strategy": "mineru",
    }

    first = run_parser_jobs([job], root_dir=root, output_dir=output_dir, strategies={"mineru"})
    second = run_parser_jobs([job], root_dir=root, output_dir=output_dir, strategies={"mineru"})

    assert first["items"][0]["status"] == "EXTRACTED"
    assert second["items"][0]["status"] == "FAILED_NO_OUTPUT"
    assert first["items"][0]["mineru_artifact_path"] != second["items"][0].get("mineru_artifact_path")


def test_parser_failure_preserves_reference_created_by_earlier_run(tmp_path, monkeypatch):
    import hxy_knowledge.parser_adapter as parser_adapter

    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))
    monkeypatch.setattr(parser_adapter.sys, "executable", str(tmp_path / "empty-bin" / "python"))
    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"PK placeholder")
    output_dir = tmp_path / "extracted"
    reference = output_dir / "knowledge" / "raw" / "inbox" / "plan.docx.reference.txt"
    reference.parent.mkdir(parents=True)
    reference.write_text("上一次已通过质量闸的解析结果。", encoding="utf-8")
    manifest = parser_adapter.reference_manifest_path(reference)
    manifest.parent.mkdir(parents=True)
    manifest.write_text('{"version":"hxy-parser-reference.v1"}', encoding="utf-8")

    result = parser_adapter.run_parser_jobs(
        [
            {
                "job_id": "job-transient-failure",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "content_hash": _sha256(source),
                "parser_strategy": "markitdown",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
    )

    assert result["items"][0]["status"] == "SKIPPED_DEPENDENCY_MISSING"
    assert reference.read_text(encoding="utf-8") == "上一次已通过质量闸的解析结果。"
    assert manifest.exists()


def test_parser_rejects_symlinked_internal_output_directory(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\nprint('这是长度足够的解析结果。')\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "plan.docx"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"source version one")
    output_dir = tmp_path / "extracted"
    canonical_parent = output_dir / "knowledge" / "raw" / "inbox"
    canonical_parent.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    (canonical_parent / ".reference-manifests").symlink_to(outside, target_is_directory=True)

    result = run_parser_jobs(
        [
            {
                "job_id": "job-symlinked-manifests",
                "source_path": "knowledge/raw/inbox/plan.docx",
                "content_hash": _sha256(source),
                "parser_strategy": "markitdown",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
    )

    assert result["items"][0]["status"] == "FAILED_UNSAFE_OUTPUT"
    assert not list(outside.iterdir())


def test_run_parser_jobs_marks_mineru_runtime_module_missing_as_dependency(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_mineru = bin_dir / "mineru"
    fake_mineru.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stderr.write(\"ModuleNotFoundError: No module named 'torch'\\n\")\n"
        "raise SystemExit(1)\n",
        encoding="utf-8",
    )
    fake_mineru.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "brand.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF placeholder")
    output_dir = tmp_path / "extracted"

    result = run_parser_jobs(
        [
            {
                "version": "hxy-parser-job.v1",
                "job_id": "job-pdf-1",
                "source_path": "knowledge/raw/inbox/brand.pdf",
                "content_hash": _sha256(source),
                "parser_strategy": "mineru",
                "status": "PENDING",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
        strategies={"mineru"},
    )

    item = result["items"][0]
    assert item["status"] == "SKIPPED_DEPENDENCY_MISSING"
    assert item["dependency"] == "torch"
    assert item["official_use_allowed"] is False
    assert item["requires_human_review"] is True


def test_run_parser_jobs_uses_fallback_when_primary_output_fails_quality_gate(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\n"
        "print('x')\n",
        encoding="utf-8",
    )
    fake_mineru = bin_dir / "mineru"
    fake_mineru.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "source = pathlib.Path(sys.argv[sys.argv.index('-p') + 1])\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "artifact = out / source.stem / (source.stem + '.md')\n"
        "artifact.parent.mkdir(parents=True, exist_ok=True)\n"
        "artifact.write_text('# 标题\\n\\n这是一个可用的完整解析结果。', encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    fake_mineru.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "scan.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF placeholder")
    output_dir = tmp_path / "extracted"

    result = run_parser_jobs(
        [
            {
                "version": "hxy-parser-job.v1",
                "job_id": "job-fallback-1",
                "source_path": "knowledge/raw/inbox/scan.pdf",
                "content_hash": _sha256(source),
                "parser_strategy": "markitdown",
                "parser_fallbacks": ["mineru"],
                "preflight": {"page_count": 80, "sample_text_chars": 10, "image_page_count": 78},
                "status": "PENDING",
            }
        ],
        root_dir=root,
        output_dir=output_dir,
    )

    item = result["items"][0]
    assert item["status"] == "EXTRACTED"
    assert item["parser"] == "mineru"
    assert [attempt["parser"] for attempt in item["attempts"]] == ["markitdown", "mineru"]
    assert item["attempts"][0]["quality"]["needs_fallback"] is True
    assert item["quality"]["status"] == "review"
    assert item["quality"]["requires_visual_review"] is True
    assert item["requires_human_review"] is True


def test_run_parser_jobs_uses_mineru_fallback_when_markitdown_loses_table_structure(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\nprint('表格字段被展开成普通文字，结构关系无法确认。')\n",
        encoding="utf-8",
    )
    fake_mineru = bin_dir / "mineru"
    fake_mineru.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "source = pathlib.Path(sys.argv[sys.argv.index('-p') + 1])\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "artifact = out / source.stem / (source.stem + '.md')\n"
        "artifact.parent.mkdir(parents=True, exist_ok=True)\n"
        "artifact.write_text('| 项目 | 价格 |\\n|---|---|\\n| 清泡 | 39 |', encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    fake_mineru.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "menu.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF placeholder")

    result = run_parser_jobs(
        [
            {
                "job_id": "job-table-fallback",
                "source_path": "knowledge/raw/inbox/menu.pdf",
                "content_hash": _sha256(source),
                "parser_strategy": "markitdown",
                "parser_fallbacks": ["mineru"],
                "preflight": {"table_signal": True},
            }
        ],
        root_dir=root,
        output_dir=tmp_path / "extracted",
    )

    item = result["items"][0]
    assert item["parser"] == "mineru"
    assert [attempt["parser"] for attempt in item["attempts"]] == ["markitdown", "mineru"]
    assert item["attempts"][0]["quality"]["needs_fallback"] is True
    assert item["quality"]["status"] == "usable"


def test_run_parser_jobs_uses_mineru_fallback_for_image_heavy_markitdown_output(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_markitdown = bin_dir / "markitdown"
    fake_markitdown.write_text(
        "#!/usr/bin/env python3\nprint('文字长度足够，但图片主导版面仍可能遗漏关键信息。')\n",
        encoding="utf-8",
    )
    fake_mineru = bin_dir / "mineru"
    fake_mineru.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "source = pathlib.Path(sys.argv[sys.argv.index('-p') + 1])\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "artifact = out / source.stem / (source.stem + '.md')\n"
        "artifact.parent.mkdir(parents=True, exist_ok=True)\n"
        "artifact.write_text('# 版面解析\\n\\n图片主导文档已完成版面与文字提取。', encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_markitdown.chmod(0o755)
    fake_mineru.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "poster.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF placeholder")

    result = run_parser_jobs(
        [
            {
                "job_id": "job-image-fallback",
                "source_path": "knowledge/raw/inbox/poster.pdf",
                "content_hash": _sha256(source),
                "parser_strategy": "markitdown",
                "parser_fallbacks": ["mineru"],
                "preflight": {
                    "page_count": 4,
                    "sampled_page_count": 4,
                    "sample_text_chars": 20,
                    "image_page_count": 4,
                },
            }
        ],
        root_dir=root,
        output_dir=tmp_path / "extracted",
    )

    item = result["items"][0]
    assert item["parser"] == "mineru"
    assert [attempt["parser"] for attempt in item["attempts"]] == ["markitdown", "mineru"]
    assert item["attempts"][0]["quality"]["needs_fallback"] is True
    assert item["quality"]["needs_fallback"] is False


def test_extraction_quality_requires_review_for_sparse_structured_output():
    from hxy_knowledge.parser_adapter import assess_extraction_quality

    quality = assess_extraction_quality(
        "只有一行",
        source_path="knowledge/raw/inbox/scanned.pdf",
        preflight={"page_count": 40, "sample_text_chars": 12, "image_page_count": 39},
    )

    assert quality["status"] == "unusable"
    assert quality["needs_fallback"] is True
    assert quality["requires_visual_review"] is True
    assert "sparse_output" in quality["signals"]


def test_extraction_quality_uses_sampled_pages_for_image_ratio():
    from hxy_knowledge.parser_adapter import assess_extraction_quality

    quality = assess_extraction_quality(
        "这是从抽样页面提取出的足够长文本，用于验证解析结果可继续进入资料理解层。",
        source_path="knowledge/raw/inbox/illustrated-report.pdf",
        preflight={
            "page_count": 100,
            "sampled_page_count": 4,
            "sample_text_chars": 30,
            "image_page_count": 4,
        },
    )

    assert quality["status"] == "review"
    assert quality["needs_fallback"] is False
    assert quality["requires_visual_review"] is True
    assert "image_heavy" in quality["signals"]


def test_extraction_quality_rejects_tiny_output_without_pdf_page_signals():
    from hxy_knowledge.parser_adapter import assess_extraction_quality

    quality = assess_extraction_quality(
        "x",
        source_path="knowledge/raw/inbox/plan.docx",
        preflight={"size_bytes": 2 * 1024 * 1024, "item_count": 12},
        parser_strategy="markitdown",
    )

    assert quality["status"] == "unusable"
    assert quality["needs_fallback"] is True
    assert "sparse_output" in quality["signals"]


def test_image_job_stays_pending_adapter_without_creating_human_review(tmp_path):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "store-photo.png"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"image placeholder")

    result = run_parser_jobs(
        [
            {
                "job_id": "job-image-adapter",
                "source_path": "knowledge/raw/inbox/store-photo.png",
                "content_hash": _sha256(source),
                "parser_strategy": "ocr_or_vision",
                "parser_fallbacks": ["manual_review"],
                "parser_plan": {"automation_state": "pending_adapter"},
            }
        ],
        root_dir=root,
        output_dir=tmp_path / "extracted",
    )

    assert result["items"][0]["status"] == "PENDING_ADAPTER"
    assert result["items"][0]["requires_human_review"] is False
    assert result["pending_count"] == 1
    assert result["requires_human_review"] is False


def test_run_parser_jobs_blocks_reference_when_all_outputs_fail_quality_gate(tmp_path, monkeypatch):
    from hxy_knowledge.parser_adapter import run_parser_jobs

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for command in ("markitdown", "mineru"):
        executable = bin_dir / command
        if command == "markitdown":
            body = "print('x')\n"
        else:
            body = (
                "import pathlib, sys\n"
                "source = pathlib.Path(sys.argv[sys.argv.index('-p') + 1])\n"
                "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
                "artifact = out / source.stem / (source.stem + '.md')\n"
                "artifact.parent.mkdir(parents=True, exist_ok=True)\n"
                "artifact.write_text('x', encoding='utf-8')\n"
            )
        executable.write_text("#!/usr/bin/env python3\n" + body, encoding="utf-8")
        executable.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "scan.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF placeholder")
    output_dir = tmp_path / "extracted"

    result = run_parser_jobs(
        [
            {
                "job_id": "job-quality-fail",
                "source_path": "knowledge/raw/inbox/scan.pdf",
                "content_hash": _sha256(source),
                "parser_strategy": "markitdown",
                "parser_fallbacks": ["mineru"],
                "preflight": {"page_count": 80, "sample_text_chars": 100, "image_page_count": 78},
            }
        ],
        root_dir=root,
        output_dir=output_dir,
    )

    item = result["items"][0]
    assert item["status"] == "FAILED_QUALITY_GATE"
    assert item["output_path"] is None
    assert result["failed_count"] == 1
    assert not (output_dir / "knowledge/raw/inbox/scan.pdf.reference.txt").exists()


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
                        "content_hash": _sha256(source),
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


def test_parser_cli_honors_mineru_job_route_without_strategy_override(tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fake_mineru = bin_dir / "mineru"
    fake_mineru.write_text(
        "#!/usr/bin/env python3\n"
        "import pathlib, sys\n"
        "source = pathlib.Path(sys.argv[sys.argv.index('-p') + 1])\n"
        "out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])\n"
        "artifact = out / source.stem / (source.stem + '.md')\n"
        "artifact.parent.mkdir(parents=True, exist_ok=True)\n"
        "artifact.write_text('# MinerU CLI\\n\\n高保真解析内容', encoding='utf-8')\n",
        encoding="utf-8",
    )
    fake_mineru.chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")

    root = tmp_path / "hxy"
    source = root / "knowledge" / "raw" / "inbox" / "scan.pdf"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"%PDF placeholder")
    state_path = root / "knowledge" / "runs" / "route" / "loop-state.json"
    state_path.parent.mkdir(parents=True)
    state_path.write_text(
        json.dumps(
            {
                "parser_jobs": [
                    {
                        "job_id": "mineru-cli-job",
                        "source_path": "knowledge/raw/inbox/scan.pdf",
                        "content_hash": _sha256(source),
                        "parser_strategy": "mineru",
                        "parser_fallbacks": ["markitdown"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    script = Path(__file__).resolve().parents[1] / "scripts" / "run-hxy-parser-jobs.py"

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--state",
            "knowledge/runs/route/loop-state.json",
            "--output-dir",
            "knowledge/raw/inbox/extracted-reference",
            "--root-dir",
            str(root),
        ],
        cwd=Path(__file__).resolve().parents[1],
        text=True,
        capture_output=True,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["processed_count"] == 1
    assert payload["items"][0]["parser"] == "mineru"


def test_api_requirements_pin_markitdown_for_parser_jobs():
    requirements = (Path(__file__).resolve().parents[1] / "apps" / "api" / "requirements.txt").read_text(
        encoding="utf-8"
    )

    assert "markitdown[docx,pdf,pptx,xls,xlsx]" in requirements
