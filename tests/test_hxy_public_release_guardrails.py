from __future__ import annotations

import runpy
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
        "data/product-materials/",
        "data/backups/",
        "quarantine/",
        "python3 scripts/check-hxy-public-release.py",
        "python3 scripts/check-hxy-secrets.py",
        "scripts/export-hxyos-public.py",
    ]:
        assert phrase in checklist


def test_product_material_uploads_are_git_ignored() -> None:
    result = subprocess.run(
        [
            "git",
            "check-ignore",
            "--quiet",
            "data/product-materials/assignment/material/file.pdf",
        ],
        cwd=ROOT,
    )

    assert result.returncode == 0


def test_release_tools_treat_product_materials_as_private() -> None:
    for relative_path in [
        "scripts/check-hxy-public-release.py",
        "scripts/export-hxyos-public.py",
    ]:
        assert '"data/product-materials/"' in read(relative_path)


def test_public_release_allows_only_explicit_env_and_toml_examples() -> None:
    namespace = runpy.run_path(str(ROOT / "scripts" / "check-hxy-public-release.py"))
    is_allowed_example = namespace.get("_is_allowed_ops_env_example")

    assert callable(is_allowed_example)
    assert is_allowed_example("ops/env/hxy-postgres.env.example")
    assert is_allowed_example("ops/env/hxy-model-router.toml.example")
    assert not is_allowed_example("ops/env/hxy-postgres.env")
    assert not is_allowed_example("ops/env/hxy-model-router.toml")


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
