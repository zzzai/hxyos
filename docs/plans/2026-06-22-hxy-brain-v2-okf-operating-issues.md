# HXY Brain v2 OKF Operating Issues Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn HXY Brain from a chat-first workbench into an OKF-backed operating issue system with knowledge lifecycle metadata.

**Architecture:** Add an HXY-owned OKF loader for Markdown + YAML frontmatter under `knowledge/okf/`. Add an operating issue engine that turns lifecycle signals, conflicts, stale facts, and incoming workbench input into actionable business issues. Expose both through FastAPI and surface them in `brain.html` as the primary work queue.

**Tech Stack:** Python standard library, FastAPI, existing static HTML/CSS/JS, unittest.

---

### Task 1: OKF Lifecycle Loader

**Files:**
- Create: `apps/api/hxy_knowledge/okf.py`
- Test: `tests/test_hxy_knowledge_service.py`

**Steps:**
1. Write failing tests for parsing Markdown frontmatter fields: `type`, `title`, `domain`, `status`, `confidence`, `last_confirmed`, `owner`, `supersedes`, `contradicts`, `used_by`.
2. Implement a small frontmatter parser using standard library only.
3. Add lifecycle summary: status counts, disputed count, stale count, low confidence count.
4. Run targeted tests.

### Task 2: Operating Issue Engine

**Files:**
- Create: `apps/api/hxy_knowledge/operating_issues.py`
- Test: `tests/test_hxy_knowledge_service.py`

**Steps:**
1. Write failing tests that disputed, stale, and low-confidence OKF docs produce prioritized issues.
2. Write failing tests that new intake text becomes a `hxy-operating-issue.v1` record with domain, priority, conflict, action, and memory target.
3. Implement minimal deterministic rules.
4. Run targeted tests.

### Task 3: API Endpoints

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Steps:**
1. Write failing API tests for `GET /api/operating-brain/okf/summary`, `GET /api/operating-brain/issues`, and `POST /api/operating-brain/issues/intake`.
2. Wire endpoints to the OKF loader and issue engine.
3. Run targeted API tests.

### Task 4: Brain Frontend

**Files:**
- Modify: `apps/admin-web/brain.html`
- Test: `tests/test_hxy_brain_frontend.py`

**Steps:**
1. Write failing frontend tests for visible labels: `经营议题台`, `动态经营记忆`, `OKF 生命周期`, `口径冲突`, `证据不足`, `待决策`.
2. Add an issue queue above the first answer area.
3. Fetch `/api/operating-brain/issues` and `/api/operating-brain/okf/summary`.
4. Keep chat as input only; do not expose technical fields in the main answer.
5. Run frontend tests.

### Task 5: Seed OKF Files and Verification

**Files:**
- Create: `knowledge/okf/README.md`
- Create: `knowledge/okf/core/*.md`

**Steps:**
1. Add conservative seed OKF documents for positioning, product script, and store model with lifecycle metadata.
2. Run full unittest discovery.
3. Run Python compile check.
4. Restart API.
5. Browser-verify desktop/mobile.
