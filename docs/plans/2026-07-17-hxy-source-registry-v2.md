# HXY Source Registry V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a deterministic, read-only registry that classifies every HXY inbox file at source level without approving knowledge or writing to PostgreSQL.

**Architecture:** Extend the existing Source Card contract with independent governance dimensions and share those enums/policies with a filesystem registry builder. The builder hashes files, applies safety-first path rules, links exact duplicates, and atomically writes private JSON and Markdown artifacts. A thin CLI runs the builder without invoking a model, parser worker, or database.

**Tech Stack:** Python 3.11+, standard library (`pathlib`, `hashlib`, `json`, `dataclasses`), pytest.

---

### Task 1: Source Card V2 Governance Contract

**Files:**
- Modify: `apps/api/hxy_product/source_card.py`
- Modify: `tests/test_hxy_material_parser.py`

**Step 1: Write failing contract tests**

Require Source Card V2 to expose `material_class`, `lifecycle`,
`authority_state`, `scope`, `sensitivity`, `business_stage`, `derivation`,
`retrieval_state`, and rule reasons. Verify external and AI-derived defaults
cannot enable official use and invalid values fall back conservatively.

**Step 2: Run the focused test and verify RED**

Run: `.venv/bin/pytest tests/test_hxy_material_parser.py -q`

Expected: FAIL because Source Card V1 lacks the V2 governance fields.

**Step 3: Implement the V2 superset**

Add enums and a shared policy helper. Preserve existing keys and semantics so
the material worker remains compatible. Never return `approved` from a default.

**Step 4: Run the focused test and verify GREEN**

Run: `.venv/bin/pytest tests/test_hxy_material_parser.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/source_card.py tests/test_hxy_material_parser.py
git commit -m "feat: define source card v2 governance contract"
```

### Task 2: Safety-First Path Classifier

**Files:**
- Create: `apps/api/hxy_product/source_registry.py`
- Create: `tests/test_hxy_source_registry.py`

**Step 1: Write failing classifier tests**

Cover processing artifacts, scripts/debug artifacts, financing/legal
sensitivity, external originals, AI summaries/application notes, explicit
candidate compliance files, archived HXY drafts, normal HXY project files, and
unknown-file defaults. Assert rule precedence and that no result is approved.

**Step 2: Run the focused test and verify RED**

Run: `.venv/bin/pytest tests/test_hxy_source_registry.py -q`

Expected: FAIL because the module does not exist.

**Step 3: Implement the minimal deterministic classifier**

Use normalized relative POSIX paths, explicit directory rules, bounded filename
signals, and shared Source Card V2 policy helpers. Return classification reasons
and confidence. Do not inspect semantic document content or call a model.

**Step 4: Run the focused test and verify GREEN**

Run: `.venv/bin/pytest tests/test_hxy_source_registry.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/source_registry.py tests/test_hxy_source_registry.py
git commit -m "feat: classify HXY inbox sources conservatively"
```

### Task 3: Inventory And Exact-Duplicate Registry

**Files:**
- Modify: `apps/api/hxy_product/source_registry.py`
- Modify: `tests/test_hxy_source_registry.py`

**Step 1: Write failing inventory tests**

Build a temporary inbox containing originals, exact duplicates, artifacts, an
unsupported format, and an unreadable/out-of-root symlink. Assert stable SHA-256
content ids, canonical path selection, one path record per file, one group per
hash, restrictive group policy, explicit errors, and stable path ordering.

**Step 2: Run the focused test and verify RED**

Run: `.venv/bin/pytest tests/test_hxy_source_registry.py -q`

Expected: FAIL on missing inventory behavior.

**Step 3: Implement inventory and grouping**

Read files in bounded blocks, reject escaping symlinks, preserve all paths, and
link duplicate records after classification. Keep run metadata separate from
the deterministic record payload.

**Step 4: Run the focused test and verify GREEN**

Run: `.venv/bin/pytest tests/test_hxy_source_registry.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/source_registry.py tests/test_hxy_source_registry.py
git commit -m "feat: inventory and deduplicate HXY source files"
```

### Task 4: Private Atomic Reports And CLI

**Files:**
- Modify: `apps/api/hxy_product/source_registry.py`
- Create: `scripts/build-hxy-source-registry.py`
- Modify: `tests/test_hxy_source_registry.py`

**Step 1: Write failing report and CLI tests**

Require stable JSON, a non-sensitive Markdown summary, atomic replacement,
explicit `--inbox`, `--output-dir`, and `--as-of` arguments, and defaults under
`data/private/source-registry`. Assert that no database module is imported and
no `selection.json` is produced.

**Step 2: Run the focused test and verify RED**

Run: `.venv/bin/pytest tests/test_hxy_source_registry.py -q`

Expected: FAIL on missing writer and CLI.

**Step 3: Implement writer and CLI**

Serialize sorted records and content groups, write temporary files in the
destination directory, `fsync`, and atomically replace final paths. Print only
counts and output paths.

**Step 4: Run the focused test and verify GREEN**

Run: `.venv/bin/pytest tests/test_hxy_source_registry.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/source_registry.py scripts/build-hxy-source-registry.py tests/test_hxy_source_registry.py
git commit -m "feat: write private HXY source registry reports"
```

### Task 5: Real Inbox Registry And Verification

**Files:**
- Create privately, do not commit: `data/private/source-registry/2026-07-17-source-registry.json`
- Create privately, do not commit: `data/private/source-registry/2026-07-17-source-registry.md`

**Step 1: Run the registry against the real inbox**

Run:

```bash
.venv/bin/python scripts/build-hxy-source-registry.py \
  --inbox /root/hxy/knowledge/raw/inbox \
  --output-dir /root/hxy/data/private/source-registry \
  --as-of 2026-07-17
```

Expected: 697 path records or explicit error records, with zero approved
sources and no database writes.

**Step 2: Compare against the audit baseline**

Verify total files, tool artifacts, processing artifacts, duplicate groups,
sensitivity totals, external/AI-derived totals, and the four compliance
candidate files. Investigate classification differences; do not tune rules to
hide uncertainty.

**Step 3: Run focused and full verification**

```bash
.venv/bin/pytest tests/test_hxy_material_parser.py tests/test_hxy_source_registry.py -q
npm test
.venv/bin/python scripts/check-hxy-secrets.py
.venv/bin/python scripts/check-hxy-public-release.py
```

Expected: all tests and scans pass.

**Step 4: Inspect repository safety**

Run: `git status --short`

Expected: private registry artifacts are ignored; only intended source, tests,
and plan files are tracked.

**Step 5: Commit verification adjustments if required**

```bash
git add apps/api/hxy_product/source_card.py apps/api/hxy_product/source_registry.py scripts/build-hxy-source-registry.py tests/test_hxy_material_parser.py tests/test_hxy_source_registry.py
git commit -m "test: verify HXY source registry against inbox"
```
