from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any


ASSIGNMENT_ID = "20000000-0000-0000-0000-000000000001"
MATERIAL_ID = "70000000-0000-0000-0000-000000000001"
JOB_ID = "80000000-0000-0000-0000-000000000001"
ROOT = Path(__file__).resolve().parents[1]


def _job() -> dict[str, Any]:
    return {
        "job_id": JOB_ID,
        "assignment_id": ASSIGNMENT_ID,
        "material_id": MATERIAL_ID,
        "parser_strategy": "markitdown",
        "attempt_id": "90000000-0000-0000-0000-000000000001",
        "attempt_number": 1,
        "max_attempts": 3,
        "file_name": "首店资料.docx",
        "extension": ".docx",
        "media_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "size_bytes": 8,
        "sha256": "a" * 64,
        "storage_key": f"{ASSIGNMENT_ID}/{MATERIAL_ID}/首店资料.docx",
        "note": "首店内部资料",
        "understanding": {
            "summary": "首店流程资料。",
            "document_type": "门店流程资料",
            "source_origin": "internal",
            "authority_level": "working_material",
            "knowledge_scale": "micro",
            "domain": "operations",
            "official_use_allowed": False,
        },
    }


class FakeRepository:
    def __init__(self, job: dict[str, Any] | None) -> None:
        self.job = job
        self.claims: list[tuple[str, int]] = []
        self.completions: list[dict[str, Any]] = []
        self.failures: list[dict[str, Any]] = []
        self.reclaimed = 0

    def reclaim_stale_leases(self, *, limit: int) -> int:
        self.reclaimed += 1
        return 0

    def claim_next_job(self, worker_id: str, *, lease_seconds: int):
        self.claims.append((worker_id, lease_seconds))
        job, self.job = self.job, None
        return job

    def complete_job(self, job_id: str, worker_id: str, **kwargs):
        self.completions.append({"job_id": job_id, "worker_id": worker_id, **kwargs})
        return {"id": MATERIAL_ID, "status": "ready"}

    def retry_or_fail_job(self, job_id: str, worker_id: str, **kwargs):
        self.failures.append({"job_id": job_id, "worker_id": worker_id, **kwargs})
        return "retryable_failed" if kwargs["retryable"] else "permanent_failed"


def _write_original(root: Path, job: dict[str, Any]) -> Path:
    path = root / job["storage_key"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"original")
    return path


def test_worker_parses_one_job_and_writes_governed_artifacts(tmp_path: Path) -> None:
    parser_module = importlib.import_module("apps.api.hxy_product.material_parser")
    worker_module = importlib.import_module("apps.api.hxy_product.material_worker")
    job = _job()
    _write_original(tmp_path, job)
    repository = FakeRepository(job)

    def parse(_path: Path):
        return parser_module.MaterialParseResult(
            text_content="# 首店接待\n\n先问顾客状态，再介绍服务。",
            title="首店接待",
            parser_name="markitdown",
            parser_version="0.1.6",
            warnings=(),
        )

    result = worker_module.process_one_material_job(
        repository,
        material_root=tmp_path,
        worker_id="worker-a",
        lease_seconds=90,
        base_retry_seconds=30,
        parser=parse,
    )

    assert result == {"status": "succeeded", "job_id": JOB_ID}
    assert repository.claims == [("worker-a", 90)]
    assert repository.failures == []
    completion = repository.completions[0]
    assert completion["job_id"] == JOB_ID
    assert completion["understanding"]["parse_status"] == "extracted"
    assert completion["understanding"]["official_use_allowed"] is False
    assert completion["chunks"]
    assert completion["chunks"][0]["heading"] == "首店接待"
    assert "先问顾客状态" in completion["chunks"][0]["content"]
    assert completion["chunks"][0]["official_use_allowed"] is False
    artifact_by_type = {item["artifact_type"]: item for item in completion["artifacts"]}
    assert set(artifact_by_type) == {"normalized_markdown", "source_card"}
    normalized = tmp_path / artifact_by_type["normalized_markdown"]["storage_key"]
    source_card_path = tmp_path / artifact_by_type["source_card"]["storage_key"]
    assert "先问顾客状态" in normalized.read_text(encoding="utf-8")
    source_card = json.loads(source_card_path.read_text(encoding="utf-8"))
    assert source_card["official_use_allowed"] is False
    assert "official_answer" in source_card["blocked_use"]


def test_markdown_chunker_preserves_headings_paragraphs_and_overlap() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_chunker")
    text = """# 首店运营

这是第一段，说明首店每天开门前需要检查环境与物料。

这是第二段，店长需要确认排班和预约情况，并处理当天异常。

## 顾客接待

接待时先询问顾客当下状态，再介绍适合的服务，不做治疗承诺。

服务结束后记录顾客反馈，并说明下次到店建议。
"""

    chunks = module.chunk_markdown(
        text,
        target_chars=45,
        overlap_chars=30,
        max_chunks=10,
    )

    assert len(chunks) >= 3
    assert chunks[0].chunk_index == 0
    assert chunks[0].heading == "首店运营"
    assert chunks[-1].heading == "顾客接待"
    assert all(chunk.content.strip() for chunk in chunks)
    assert all(len(chunk.content) <= 200 for chunk in chunks)
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert any("第二段" in chunk.content for chunk in chunks[:2])


def test_markdown_chunker_splits_long_paragraphs_and_caps_output() -> None:
    module = importlib.import_module("apps.api.hxy_product.material_chunker")
    text = "# 长文\n\n" + "顾客状态需要先询问。" * 200

    chunks = module.chunk_markdown(
        text,
        target_chars=120,
        overlap_chars=20,
        max_chunks=4,
    )

    assert len(chunks) == 4
    assert all(chunk.heading == "长文" for chunk in chunks)
    assert all(1 <= len(chunk.content) <= 160 for chunk in chunks)


def test_worker_records_retryable_parser_failure_without_writing_artifacts(
    tmp_path: Path,
) -> None:
    parser_module = importlib.import_module("apps.api.hxy_product.material_parser")
    worker_module = importlib.import_module("apps.api.hxy_product.material_worker")
    job = _job()
    _write_original(tmp_path, job)
    repository = FakeRepository(job)

    def fail(_path: Path):
        raise parser_module.MaterialParseError(
            "parser_busy",
            "parser is temporarily unavailable at /private/path",
            retryable=True,
        )

    result = worker_module.process_one_material_job(
        repository,
        material_root=tmp_path,
        worker_id="worker-a",
        lease_seconds=90,
        base_retry_seconds=30,
        parser=fail,
    )

    assert result == {
        "status": "retryable_failed",
        "job_id": JOB_ID,
        "error_code": "parser_busy",
    }
    failure = repository.failures[0]
    assert failure["retryable"] is True
    assert failure["retry_delay_seconds"] == 30
    assert "/private/path" not in failure["error_summary"]
    assert not any(path.name in {"normalized.md", "source-card.json"} for path in tmp_path.rglob("*"))


def test_worker_marks_missing_original_as_permanent_failure(tmp_path: Path) -> None:
    worker_module = importlib.import_module("apps.api.hxy_product.material_worker")
    repository = FakeRepository(_job())

    result = worker_module.process_one_material_job(
        repository,
        material_root=tmp_path,
        worker_id="worker-a",
        lease_seconds=90,
        base_retry_seconds=30,
    )

    assert result["status"] == "permanent_failed"
    assert result["error_code"] == "source_missing"
    assert repository.failures[0]["retryable"] is False


def test_worker_returns_idle_without_parser_work(tmp_path: Path) -> None:
    worker_module = importlib.import_module("apps.api.hxy_product.material_worker")
    repository = FakeRepository(None)
    parser_calls: list[Path] = []

    def parser(path: Path):
        parser_calls.append(path)
        raise AssertionError("parser must not run")

    result = worker_module.process_one_material_job(
        repository,
        material_root=tmp_path,
        worker_id="worker-a",
        lease_seconds=90,
        base_retry_seconds=30,
        parser=parser,
    )

    assert result == {"status": "idle"}
    assert parser_calls == []


def test_material_worker_operations_are_hxy_owned_and_private() -> None:
    launcher = (ROOT / "ops" / "hxy-material-worker.sh").read_text(
        encoding="utf-8"
    )
    service = (ROOT / "ops" / "systemd" / "hxy-material-worker.service").read_text(
        encoding="utf-8"
    )
    env_example = (ROOT / "ops" / "env" / "hxy-knowledge-api.env.example").read_text(
        encoding="utf-8"
    )

    assert "scripts/run-hxy-material-worker.py" in launcher
    assert "HXY_MATERIAL_WORKER_POLL_SECONDS" in launcher
    assert "HXY_MATERIAL_WORKER_LEASE_SECONDS" in launcher
    assert "HXY_MATERIAL_WORKER_BASE_RETRY_SECONDS" in launcher
    assert "Description=HXY Material Intake Worker" in service
    assert "WorkingDirectory=/root/hxy/releases/current" in service
    assert "/root/hxy/releases/current/.venv/bin/python" in service
    assert "/root/hxy/releases/current/scripts/run-hxy-material-worker.py" in service
    assert "PYTHONDONTWRITEBYTECODE=1" in service
    assert "UMask=0077" in service
    assert "ReadWritePaths=/root/hxy/data/product-materials" in service
    assert "Restart=always" in service
    assert "HXY_MATERIAL_WORKER_POLL_SECONDS=2" in env_example
    assert "HXY_MATERIAL_WORKER_LEASE_SECONDS=300" in env_example
    assert "htops" not in (launcher + service).lower()


def test_material_intake_runbook_has_one_shot_and_recovery_commands() -> None:
    runbook = (
        ROOT / "docs" / "operations" / "hxy-material-intake-runtime.md"
    ).read_text(encoding="utf-8")

    assert "--once" in runbook
    assert "014_hxy_knowledge_activation.sql" in runbook
    assert "systemctl status hxy-material-worker" in runbook
    assert "journalctl -u hxy-material-worker" in runbook
    assert "不得自动进入正式知识" in runbook
