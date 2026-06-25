# HXY Employee Training Closed Loop Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make the first HXY Brain value loop usable for stores: employees practice scripts, AI scores them, managers see retrain priorities, and repeated mistakes become operating issue signals.

**Architecture:** Keep the current FastAPI + static H5 architecture. Add manager-facing routes and APIs on top of the existing training session repository, without introducing a new JS build chain or touching htops data.

**Tech Stack:** FastAPI, PostgreSQL, plain HTML/CSS/JS H5, unittest, Playwright/browser verification.

---

### Task 1: Training Session History API

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_api.py`

**Steps:**
1. Write a failing test for `GET /api/operating-brain/training/sessions`.
2. Add the route and delegate to `KnowledgeRepository.training_sessions`.
3. Verify the endpoint returns filtered items with count and query parameters.

### Task 2: Manager Training H5

**Files:**
- Create: `apps/manager-web/training.html`
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_api.py`
- Modify: `tests/test_hxy_brain_frontend.py`

**Steps:**
1. Write failing tests for `/manager/training` and required manager UI labels.
2. Add the static route.
3. Build a mobile-first manager page that fetches `manager-summary` and shows retrain priorities, top mistakes, and suggested actions.

### Task 3: Operating Issue Signal

**Files:**
- Modify: `apps/api/hxy_knowledge/repository.py`
- Modify: `tests/test_hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_service.py`

**Steps:**
1. Write failing tests expecting `operating_issue_signal` in manager summary.
2. Generate an issue signal when retrain count or repeated mistakes are present.
3. Keep it business-readable and free of technical labels.

### Task 4: Employee H5 Polish

**Files:**
- Modify: `apps/employee-web/training.html`
- Modify: `tests/test_hxy_brain_frontend.py`

**Steps:**
1. Write tests for local identity persistence and submit loading state.
2. Store employee/store fields in `localStorage`.
3. Disable submit during scoring and render a clear loading label.

### Task 5: Verification

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 -m py_compile apps/api/hxy_knowledge/*.py apps/api/hxy_knowledge_api.py scripts/*.py
scripts/start-hxy-knowledge-api.sh --restart
```

Then verify `/employee/training` and `/manager/training` in a mobile viewport.
