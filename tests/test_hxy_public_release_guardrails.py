from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_github_ci_runs_secret_scan_and_full_test_suite() -> None:
    workflow = read(".github/workflows/ci.yml")

    assert "python3 scripts/check-hxy-secrets.py" in workflow
    assert "npm test" in workflow
    assert "npm ci" in workflow
    assert "pip install -r apps/api/requirements.txt" in workflow
    assert "pull_request" in workflow
    assert "push" in workflow


def test_public_release_checklist_documents_local_only_materials() -> None:
    checklist = read("docs/operations/hxy-github-public-release-checklist.md")

    for phrase in [
        "品牌知识留在本地",
        "knowledge/raw/",
        "knowledge/wiki/",
        "knowledge/runs/",
        "knowledge/reports/",
        "knowledge/okf/core/",
        "ops/env/*.env",
        "data/backups/",
        "quarantine/",
        "python3 scripts/check-hxy-public-release.py",
        "python3 scripts/check-hxy-secrets.py",
        "scripts/export-hxyos-public.py",
    ]:
        assert phrase in checklist


def test_public_release_preflight_passes_current_repository() -> None:
    result = subprocess.run(
        ["python3", "scripts/check-hxy-public-release.py"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "public_release_preflight_ok=true" in result.stdout
