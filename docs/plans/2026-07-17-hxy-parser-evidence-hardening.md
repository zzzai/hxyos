# HXY Parser Evidence Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make routed document parsing filesystem-safe, source-version-bound, retry-isolated, and exception-reviewed before any parsed artifact reaches the understanding layer.

**Architecture:** Keep the existing preflight and parser routing design. Harden the adapter at its trust boundaries: accept sources only from the HXY inbox, confine generated artifacts to the configured output directory, bind each extraction to a SHA-256 source version, isolate every MinerU attempt, and distinguish automatic completion from true review exceptions.

**Tech Stack:** Python 3.11+, pathlib, hashlib, subprocess, pytest, MarkItDown CLI, MinerU CLI.

---

### Task 1: Filesystem Confinement

**Files:**
- Modify: `apps/api/hxy_knowledge/parser_adapter.py`
- Test: `tests/test_hxy_parser_adapter.py`

1. Add failing tests proving jobs cannot read outside `knowledge/raw/inbox` and cannot escape `output_dir` through mixed separators or traversal components.
2. Run those tests and confirm the current adapter fails them for the expected reason.
3. Resolve and validate source and output paths against their explicit trust roots.
4. Re-run the focused tests.

### Task 2: Source Version Binding

**Files:**
- Modify: `apps/api/hxy_knowledge/parser_adapter.py`
- Modify: `apps/api/hxy_knowledge/ingest_loop.py`
- Test: `tests/test_hxy_parser_adapter.py`
- Test: `tests/test_hxy_ingest_loop.py`

1. Add failing tests for a stale job hash, a source changed during parsing, and a stale pre-existing reference.
2. Verify the tests fail against current behavior.
3. Check the SHA-256 before and after parser execution and persist a sidecar manifest beside each reference.
4. Accept an existing reference only when its sidecar source hash matches the current source.
5. Re-run focused tests.

### Task 3: MinerU Attempt Isolation And Artifact Preservation

**Files:**
- Modify: `apps/api/hxy_knowledge/parser_adapter.py`
- Test: `tests/test_hxy_parser_adapter.py`

1. Add failing tests proving a retry cannot reuse an earlier MinerU Markdown artifact and a failed run cannot delete a reference it did not create.
2. Verify both failures.
3. Use a unique temporary work directory per MinerU attempt and replace canonical outputs only after a successful quality-gated extraction.
4. Re-run focused tests.

### Task 4: Quality Fallback And Exception Review

**Files:**
- Modify: `apps/api/hxy_knowledge/parser_adapter.py`
- Modify: `apps/api/hxy_knowledge/ingest_loop.py`
- Modify: `apps/api/hxy_knowledge/document_router.py`
- Test: `tests/test_hxy_parser_adapter.py`
- Test: `tests/test_hxy_ingest_loop.py`
- Test: `tests/test_hxy_document_router.py`

1. Add failing tests that image/table structural warnings try an available fallback before asking for review.
2. Add failing tests that normal parser-ready tasks complete without human review while missing adapters, failed quality gates, and legacy unsupported formats remain exceptions.
3. Add a format parity test for all routed image suffixes.
4. Implement the minimum state and suffix changes needed for those tests.
5. Re-run focused tests.

### Task 5: Verification And Private Audit

**Files:**
- Refresh local-only reports under: `data/private/source-routing/`

1. Run parser, router, ingest, and source routing tests.
2. Run the full Python and frontend test suites.
3. Run compile, diff, secret, and public release checks.
4. Rebuild the real inbox routing report without invoking parsers or models and confirm no raw file changed.
5. Review the final diff and commit only code, tests, and documentation.
