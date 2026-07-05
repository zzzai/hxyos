#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = Path("/tmp/hxyos-public")
DEFAULT_REMOTE = "git@github.com:zzzai/hxyos.git"

ALLOWLIST = [
    "apps/api/hxy_knowledge/__init__.py",
    "apps/api/hxy_knowledge/brain_benchmark.py",
    "apps/api/hxy_knowledge/config.py",
    "apps/api/hxy_knowledge/enterprise_governance.py",
    "apps/api/hxy_knowledge/ingest_loop.py",
    "apps/api/hxy_knowledge/knowledge_compiler.py",
    "apps/api/hxy_knowledge/loop_engine.py",
    "apps/api/hxy_knowledge/memory_context.py",
    "apps/api/hxy_knowledge/model_router.py",
    "apps/api/hxy_knowledge/process_memory.py",
    "apps/api/hxy_knowledge/reliability.py",
    "apps/api/hxy_knowledge/workspace_events.py",
    "apps/api/requirements.txt",
    "pytest.ini",
    "scripts/compile-hxy-knowledge.py",
    "scripts/run-hxy-brain-benchmark.py",
    "scripts/run-hxy-ingest-loop.py",
    "scripts/run-hxy-loop.py",
]

TEXT_SUFFIXES = {
    ".cfg",
    ".ini",
    ".json",
    ".md",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".yaml",
    ".yml",
}

PRIVATE_PATH_MARKERS = [
    ".env",
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
    "apps/menu-h5/",
    "docs/product/",
    "docs/project-brain/",
]

REPLACEMENTS = [
    ("荷小悦", "ExampleCo"),
    ("荷塘悦色", "Legacy Brand"),
    ("清泡调补养", "service tiers"),
    ("草本真现煮", "visible preparation"),
    ("草本现煮", "visible preparation"),
    ("草本泡脚", "signature service"),
    ("小店模型", "pilot operating model"),
    ("门店模型", "site operating model"),
    ("社区小店", "community site"),
    ("奈晚", "CompetitorA"),
    ("谷小推", "CompetitorB"),
    ("长风拨筋", "CompetitorC"),
    ("郑远元", "CompetitorD"),
    ("秀域", "CompetitorE"),
    ("足康树", "CompetitorF"),
    ("清泡", "entry tier"),
    ("调泡", "adaptive tier"),
    ("补泡", "recovery tier"),
    ("养泡", "continuity tier"),
    ("泡脚", "service session"),
    ("足疗", "service clinic"),
    ("按摩", "bodywork"),
    ("技师", "frontline staff"),
    ("门店员工", "frontline staff"),
    ("员工", "staff"),
    ("店长", "site manager"),
    ("门店", "site"),
    ("招商", "partnership"),
    ("加盟", "partnership"),
    ("会员", "customer account"),
    ("订单", "order record"),
    ("手机号", "phone number"),
    ("/root/htops", "/root/legacy-system"),
    ("htops", "legacy-system"),
    ("HETANG_", "LEGACY_"),
]

BLOCKED_TERMS = [
    "荷小悦",
    "清泡调补养",
    "草本真现煮",
    "草本泡脚",
    "小店模型",
    "长风拨筋",
    "奈晚",
    "谷小推",
    "郑远元",
    "秀域",
    "足康树",
    "荷塘悦色",
    "/root/htops",
    "HETANG_",
    "knowledge/raw/inbox/荷",
    "ghp_",
    "AKIA",
    "xoxb-",
    "xoxp-",
    "xoxa-",
    "xoxr-",
]

README = """# HXYOS Public Scaffold

HXYOS is an organization memory and knowledge-governance scaffold for building an enterprise AI operating system.

This public repository contains reusable engineering pieces only:

- knowledge compilation into extracts, candidate claims, review queues, and draft answer cards
- memory-context budgeting with process-memory governance
- loop runners with hard stop conditions and human-review gates
- model routing metadata that never exposes credentials by default
- workspace event logging with sensitive-content redaction

It intentionally does not contain private brand knowledge, source documents, raw materials, compiled local wiki pages, seeds, run reports, environment files, or production backups.

## Public vs Private

Public code:

```text
apps/api/hxy_knowledge/     # reusable Python modules
scripts/                    # local CLI runners
tests/                      # generic fixtures only
knowledge/examples/         # safe sample material
```

Private local material, excluded from Git:

```text
knowledge/raw/
knowledge/normalized/
knowledge/structured/
knowledge/wiki/
knowledge/runs/
knowledge/reports/
knowledge/okf/core/
data/seeds/
data/backups/
ops/env/*.env
```

## Quick Start

```bash
python -m venv .venv
. .venv/bin/activate
pip install -r apps/api/requirements.txt
pytest
```

Run the sample ingest loop:

```bash
python scripts/run-hxy-ingest-loop.py \\
  --root-dir . \\
  --raw-dir knowledge/examples/raw \\
  --wiki-dir /tmp/hxyos-public-sample/wiki \\
  --report /tmp/hxyos-public-sample/report.json \\
  --runs-dir /tmp/hxyos-public-sample/runs \\
  --run-id sample-ingest
```

The loop stops at `review_required`. It does not publish approved knowledge automatically.

## Governance Rules

1. Raw and reference material is not authority.
2. Process memory is only a context hint.
3. AI-generated extracts, claims, and answer-card drafts require human review.
4. Approved knowledge must have source, owner, version, scope, and review status.
5. Secrets and private business material stay outside the public repo.
"""

AGENTS = """# AGENTS

Project scope: this repository.

## Mission

HXYOS is a reusable enterprise AI operating-system scaffold.

The public repository must not contain private brand knowledge, internal source documents, secrets, backups, production data, or local run artifacts.

## Rules

1. Keep real organizational knowledge in local/private storage.
2. Do not commit `knowledge/raw`, `knowledge/wiki`, `knowledge/runs`, `knowledge/reports`, `knowledge/okf/core`, `data/seeds`, backups, exports, or `.env` files.
3. Public fixtures must be generic examples.
4. Process memory must never be treated as approved knowledge.
5. AI-generated drafts must stop at human review.
6. Runtime services should read credentials from environment variables only.
"""

GITIGNORE = """# Local secrets
ops/env/*.env
ops/env/*.toml
!ops/env/*.env.example
.env
.env.*

# Private knowledge and operating artifacts
knowledge/raw/
knowledge/normalized/
knowledge/structured/
knowledge/reports/
knowledge/runs/
knowledge/wiki/
knowledge/okf/core/
knowledge/taxonomy-overrides.json
data/seeds/
data/exports/
data/backups/

# Runtime and dependency artifacts
.venv/
node_modules/
dist/
build/
.next/
.turbo/
.cache/
.pytest_cache/
__pycache__/
*.pyc
tmp/
quarantine/

# Logs
*.log
logs/
ops/logs/
"""

EXAMPLE_SOURCE = """# ExampleCo Knowledge Note

ExampleCo is evaluating whether its first site positioning is clear enough for staff and customers.

The current operating hypothesis is that the team should turn raw references into candidate claims, review tasks, and approved answer cards only after human review.

Staff must not claim treatment, guaranteed results, guaranteed revenue, or unverifiable market leadership.
"""

PUBLIC_TEST = '''from pathlib import Path

from hxy_knowledge.enterprise_governance import build_enterprise_governance_report
from hxy_knowledge.ingest_loop import run_ingest_loop
from hxy_knowledge.knowledge_compiler import compile_directory
from hxy_knowledge.memory_context import build_memory_context
from hxy_knowledge.process_memory import build_memory_promotion_draft, build_process_memory_record
from hxy_knowledge.workspace_events import create_workspace_event, list_workspace_events


def test_compiler_creates_review_artifacts_without_approval(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    wiki_dir = tmp_path / "wiki"
    raw_dir.mkdir()
    (raw_dir / "note.md").write_text(
        "ExampleCo should validate first-site positioning. Staff must not promise guaranteed results.",
        encoding="utf-8",
    )

    report = compile_directory(raw_dir, wiki_dir)

    assert report["extract_count"] == 1
    assert report["claim_count"] >= 1
    assert report["approved_count"] == 0
    assert (wiki_dir / "review-queue.json").exists()
    assert (wiki_dir / "answer-card-drafts.json").exists()


def test_ingest_loop_stops_at_human_review(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    (raw_dir / "source.md").write_text("ExampleCo reference material requires review.", encoding="utf-8")

    state = run_ingest_loop(
        raw_dir=raw_dir,
        wiki_dir=tmp_path / "wiki",
        report_path=tmp_path / "reports" / "ingest.json",
        runs_dir=tmp_path / "runs",
        run_id="sample",
        root_dir=tmp_path,
    )

    assert state["status"] == "review_required"
    assert state["official_use_allowed"] is False
    assert state["requires_human_review"] is True


def test_process_memory_is_context_hint_not_authority() -> None:
    record = build_process_memory_record(
        "Do not turn founder preferences into official policy without review.",
        source="test",
        actor="tester",
        confidence=0.8,
    )
    promotion = build_memory_promotion_draft(record, target_domain="governance")

    assert record["official_use_allowed"] is False
    assert promotion["target_status"] == "current_candidate"
    assert promotion["requires_human_review"] is True

    context = build_memory_context(
        working_memory={"goal": "answer with governance"},
        short_term_messages=[],
        retrieved_memories=[
            {
                "id": "approved-1",
                "status": "approved",
                "source_type": "approved_answer_card",
                "semantic_relevance": 0.9,
                "importance": 0.8,
            },
            {
                "id": "process-1",
                "status": "process",
                "source_type": "process_memory",
                "semantic_relevance": 0.9,
                "importance": 0.9,
            },
        ],
    )

    assert context["formal_knowledge"][0]["id"] == "approved-1"
    assert context["process_memory_hints"][0]["context_hint_only"] is True
    assert context["authority_rule"] == "process_memory_cannot_be_authority"


def test_governance_lints_reference_used_by_approved_card() -> None:
    report = build_enterprise_governance_report(
        assets=[],
        claims=[],
        evidence=[],
        relations=[],
        answer_cards=[
            {
                "card_id": "card-1",
                "status": "approved",
                "evidence": [{"status": "reference", "title": "unreviewed note"}],
            }
        ],
    )

    issue_codes = {issue["code"] for issue in report["lint_issues"]}
    assert "reference_used_as_approved_source" in issue_codes
    assert report["release_gate"]["can_publish"] is False


def test_workspace_events_redact_sensitive_private_material(tmp_path: Path) -> None:
    store_path = tmp_path / "events.jsonl"
    event = create_workspace_event(
        {
            "topic": "fundraising note",
            "input": "valuation and token should be restricted",
            "ai_output": {"summary": "contains sensitive terms"},
        },
        store_path=store_path,
        now=lambda: "2026-01-01T00:00:00Z",
    )

    assert event["visibility"] == "restricted_role"

    listed = list_workspace_events(store_path)
    assert listed["count"] == 1
    assert listed["items"][0]["input"] == "[redacted]"
'''


def run(command: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=cwd, text=True, check=check, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def ensure_safe_target(target: Path) -> None:
    resolved = target.resolve()
    if resolved == Path("/") or resolved == ROOT.resolve() or ROOT.resolve() in resolved.parents:
        raise SystemExit(f"Refusing unsafe target: {resolved}")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def copy_allowlisted_files(target: Path) -> None:
    for relative in ALLOWLIST:
        source = ROOT / relative
        if not source.exists():
            raise SystemExit(f"Missing allowlisted source: {relative}")
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)


def write_public_templates(target: Path) -> None:
    write_text(target / "README.md", README)
    write_text(target / "AGENTS.md", AGENTS)
    write_text(target / ".gitignore", GITIGNORE)
    write_text(target / "knowledge/examples/raw/example-source.md", EXAMPLE_SOURCE)
    write_text(target / "tests/test_public_governance.py", PUBLIC_TEST)


def sanitize_text_files(target: Path) -> None:
    for path in target.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8")
        original = text
        for before, after in REPLACEMENTS:
            text = text.replace(before, after)
        if text != original:
            path.write_text(text, encoding="utf-8")


def assert_no_private_paths(target: Path) -> None:
    for path in target.rglob("*"):
        relative = path.relative_to(target).as_posix()
        if any(marker in relative for marker in PRIVATE_PATH_MARKERS):
            raise SystemExit(f"Private path leaked into export: {relative}")
        if path.is_file() and path.suffix.lower() in {".env", ".sql", ".sqlite", ".db", ".bak", ".tar", ".gz"}:
            raise SystemExit(f"Private artifact extension leaked into export: {relative}")


def assert_no_blocked_terms(target: Path) -> None:
    hits: list[str] = []
    for path in target.rglob("*"):
        if not path.is_file() or ".git/" in path.as_posix() or path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for term in BLOCKED_TERMS:
            if term in text:
                hits.append(f"{path.relative_to(target)}: {term}")
    if hits:
        raise SystemExit("Blocked terms found in public export:\n" + "\n".join(hits[:80]))


def python_for_tests() -> str:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists():
        return str(venv_python)
    return sys.executable


def verify_export(target: Path) -> None:
    assert_no_private_paths(target)
    assert_no_blocked_terms(target)
    result = run([python_for_tests(), "-m", "pytest"], cwd=target)
    print(result.stdout, end="")


def initialize_git(target: Path, *, message: str, remote: str, push: bool) -> None:
    run(["git", "init"], cwd=target)
    run(["git", "branch", "-M", "main"], cwd=target)
    run(["git", "config", "user.name", "HXYOS Publisher"], cwd=target)
    run(["git", "config", "user.email", "hxyos@example.local"], cwd=target)
    run(["git", "add", "."], cwd=target)
    run(["git", "commit", "-m", message], cwd=target)
    run(["git", "remote", "add", "origin", remote], cwd=target)
    if push:
        run(["git", "push", "-u", "origin", "main"], cwd=target)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Export a sanitized HXYOS public scaffold without private brand knowledge.")
    parser.add_argument("--target", default=str(DEFAULT_TARGET), help="Target directory for the public export.")
    parser.add_argument("--no-verify", action="store_true", help="Skip tests and leak checks.")
    parser.add_argument("--git", action="store_true", help="Initialize a fresh git repository and commit the export.")
    parser.add_argument("--push", action="store_true", help="Push the fresh public repository to the configured remote.")
    parser.add_argument("--remote", default=DEFAULT_REMOTE, help="Git remote used when --git or --push is set.")
    parser.add_argument("--commit-message", default="chore: publish hxyos public scaffold")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = Path(args.target).resolve()
    ensure_safe_target(target)
    if args.push:
        args.git = True

    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    copy_allowlisted_files(target)
    write_public_templates(target)
    sanitize_text_files(target)
    assert_no_private_paths(target)
    assert_no_blocked_terms(target)

    if not args.no_verify:
        verify_export(target)
    if args.git:
        initialize_git(target, message=args.commit_message, remote=args.remote, push=args.push)

    print(f"Public export ready: {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
