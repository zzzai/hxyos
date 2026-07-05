from __future__ import annotations

import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "scripts" / "check-hxy-secrets.py"


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _run_scanner(repo: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(SCANNER), "--repo", str(repo)],
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    (repo / ".gitignore").write_text("ops/env/*.env\n!ops/env/*.env.example\n", encoding="utf-8")
    _git(repo, "add", ".gitignore")
    return repo


def test_secret_scanner_flags_non_ignored_model_keys_without_printing_values(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    leaked_key = "sk-" + ("A" * 32)
    (repo / "SECURITY.md").write_text(
        f"HXY_MODEL_API_KEY={leaked_key}\n",
        encoding="utf-8",
    )
    _git(repo, "add", "SECURITY.md")

    result = _run_scanner(repo)

    assert result.returncode == 1
    assert "SECURITY.md:1" in result.stdout
    assert "HXY_MODEL_API_KEY" in result.stdout
    assert leaked_key not in result.stdout
    assert leaked_key not in result.stderr


def test_secret_scanner_allows_examples_and_redacted_placeholders(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    env_dir = repo / "ops" / "env"
    env_dir.mkdir(parents=True)
    (env_dir / "hxy-postgres.env.example").write_text(
        "\n".join(
            [
                "POSTGRES_PASSWORD=<change-me>",
                "HXY_MODEL_API_KEY=<redacted>",
                "HXY_API_TOKEN=${HXY_API_TOKEN}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    (repo / "SECURITY.md").write_text(
        "POSTGRES_PASSWORD=<redacted>\nHXY_MODEL_API_KEY=<redacted>\n",
        encoding="utf-8",
    )
    _git(repo, "add", "ops/env/hxy-postgres.env.example", "SECURITY.md")

    result = _run_scanner(repo)

    assert result.returncode == 0
    assert "No committed or commit-eligible HXY secrets found" in result.stdout


def test_secret_scanner_skips_gitignored_local_env_files(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    env_dir = repo / "ops" / "env"
    env_dir.mkdir(parents=True)
    (env_dir / "hxy-postgres.env").write_text(
        "POSTGRES_PASSWORD=local-only-secret\n"
        f"HXY_MODEL_API_KEY={'sk-' + ('B' * 32)}\n",
        encoding="utf-8",
    )

    result = _run_scanner(repo)

    assert result.returncode == 0
    assert "hxy-postgres.env" not in result.stdout


def test_secret_scanner_allows_variable_based_database_url_assignments(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    (repo / "runbook.md").write_text(
        "\n".join(
            [
                'HXY_DATABASE_URL="$HXY_DATABASE_URL" python3 scripts/import.py',
                'HXY_DATABASE_URL="$(build_database_dsn)"',
                'HXY_DATABASE_URL="host=127.0.0.1 port=${HXY_PG_HOST_PORT:-55433} password=${POSTGRES_PASSWORD}"',
                "",
            ]
        ),
        encoding="utf-8",
    )
    _git(repo, "add", "runbook.md")

    result = _run_scanner(repo)

    assert result.returncode == 0


def test_secret_scanner_flags_hardcoded_database_urls_without_printing_values(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    password = "hardcoded-secret"
    dsn = f"postgresql://hxy_app:{password}@127.0.0.1:55433/hxy"
    (repo / "runbook.md").write_text(f"HXY_DATABASE_URL={dsn}\n", encoding="utf-8")
    _git(repo, "add", "runbook.md")

    result = _run_scanner(repo)

    assert result.returncode == 1
    assert "runbook.md:1" in result.stdout
    assert "HXY_DATABASE_URL" in result.stdout
    assert password not in result.stdout
    assert dsn not in result.stdout
