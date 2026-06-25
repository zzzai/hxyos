# HXY Team Operating Brain Workbench Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first usable team-facing HXY operating brain workbench: a central multimodal conversation entry, lightweight team navigation, hidden Inspector, and backend intake routing contract.

**Architecture:** Keep the current FastAPI + single-file admin HTML architecture. Add a small deterministic `workbench` service for product routing and wire it into the API and frontend without introducing a JS build system.

**Tech Stack:** Python 3, FastAPI, unittest, static HTML/CSS/JS, PostgreSQL repository abstraction already present.

---

### Task 1: Backend Workbench Contract

**Files:**
- Create: `apps/api/hxy_knowledge/workbench.py`
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_service.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Steps:**
1. Write failing service tests for classifying question, upload/intake, correction, training, and operating task inputs.
2. Write failing API test for `POST /api/operating-brain/workbench-intake`.
3. Implement `classify_workbench_intake`.
4. Add Pydantic request model and endpoint.
5. Run targeted tests.

### Task 2: Frontend Product Shape

**Files:**
- Modify: `apps/admin-web/brain.html`
- Test: `tests/test_hxy_brain_frontend.py`

**Steps:**
1. Write failing tests that assert the page is a team workbench, not a strategy-only gate or technical knowledge admin.
2. Add team navigation labels and central super input copy.
3. Add multimodal entry affordances: upload, drag image, paste screenshot, correction, training, task.
4. Add hidden Inspector sections for current understanding, classification, main conflict, missing data, correction, memory action.
5. Keep page scroll locked and chat scrollable.
6. Run frontend tests.

### Task 3: Frontend Workbench Intake Wiring

**Files:**
- Modify: `apps/admin-web/brain.html`
- Test: `tests/test_hxy_brain_frontend.py`

**Steps:**
1. Write failing tests for `/api/operating-brain/workbench-intake` usage.
2. Call intake endpoint before chat answer.
3. Store intake result with each answer.
4. Render intake result only in Inspector.
5. Run frontend tests.

### Task 4: Verification

**Files:**
- All changed files.

**Steps:**
1. Run `python3 -m unittest tests/test_hxy_knowledge_api.py tests/test_hxy_knowledge_service.py tests/test_hxy_brain_frontend.py tests/test_hxy_operating_brain_docs.py -v`.
2. Run JS syntax check for the script inside `brain.html`.
3. Restart the local API service.
4. Smoke test `/brain.html`, `/api/operating-brain/workbench-intake`, `/api/knowledge/chat`.
