#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

PRIVATE_PATTERNS = [
    "knowledge/raw/",
    "knowledge/normalized/",
    "knowledge/structured/",
    "knowledge/wiki/",
    "knowledge/runs/",
    "knowledge/reports/",
    "knowledge/okf/core/",
    "data/seeds/",
    "data/backups/",
    "data/exports/",
    "quarantine/",
    "ops/env/*.env",
    "ops/env/*.toml",
]

REQUIRED_FILES = [
    ".github/workflows/ci.yml",
    "scripts/check-hxy-secrets.py",
    "scripts/export-hxyos-public.py",
    "docs/operations/hxy-github-public-release-checklist.md",
]


def _git_tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=True,
    )
    return [item.decode("utf-8") for item in result.stdout.split(b"\0") if item]


def _read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def _has_gitignore_rule(gitignore: str, pattern: str) -> bool:
    return any(line.strip() == pattern for line in gitignore.splitlines())


def _fail(messages: list[str]) -> int:
    print("public_release_preflight_ok=false")
    for message in messages:
        print(f"- {message}")
    return 1


def main() -> int:
    failures: list[str] = []

    for relative_path in REQUIRED_FILES:
        if not (ROOT / relative_path).is_file():
            failures.append(f"missing required release guardrail file: {relative_path}")

    gitignore = _read(".gitignore") if (ROOT / ".gitignore").is_file() else ""
    for pattern in PRIVATE_PATTERNS:
        if not _has_gitignore_rule(gitignore, pattern):
            failures.append(f".gitignore missing private material rule: {pattern}")

    tracked_files = _git_tracked_files()
    forbidden_tracked_prefixes = [
        "knowledge/raw/",
        "knowledge/normalized/",
        "knowledge/structured/",
        "knowledge/wiki/",
        "knowledge/runs/",
        "knowledge/reports/",
        "knowledge/okf/core/",
        "data/seeds/",
        "data/backups/",
        "data/exports/",
        "quarantine/",
    ]
    for path in tracked_files:
        if any(path.startswith(prefix) for prefix in forbidden_tracked_prefixes):
            failures.append(f"private path is tracked by Git: {path}")
        if path.startswith("ops/env/") and not path.endswith(".env.example"):
            failures.append(f"non-example env material is tracked by Git: {path}")
        if path.endswith((".sensitive.sql", ".bak", ".sqlite", ".db")):
            failures.append(f"private artifact extension is tracked by Git: {path}")

    if failures:
        return _fail(failures)

    print("public_release_preflight_ok=true")
    print("public_release_policy=code_only_private_knowledge_local")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
