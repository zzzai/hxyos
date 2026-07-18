# HXYOS Governed Operating Workflow Review Fixes Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Close the Task 7 review findings so governed operating tasks cannot bypass policy, historical proposal decisions remain truthful, and aggregate inconsistencies fail closed.

**Architecture:** Keep the V1 modular monolith and single active workflow per operating event. Enforce governance at repository/service boundaries, preserve immutable historical decision facts, and reject inconsistent or unsupported aggregate shapes instead of inferring state.

**Tech Stack:** Python 3, FastAPI, psycopg 3, PostgreSQL, pytest

---

### Task 1: Block Legacy Task Mutation

**Files:**
- Modify: `apps/api/hxy_product/task_repository.py`
- Modify: `apps/api/hxy_product/task_routes.py`
- Test: `tests/test_hxy_product_tasks.py`

**Steps:**
1. Add a failing route/repository test proving `PATCH /api/v1/tasks/{id}` rejects a task with `operating_event_id`.
2. Run the focused test and verify the expected failure.
3. Return the operating marker from the repository and raise a governed-workflow conflict before legacy mutation.
4. Run the focused task tests and verify green.

### Task 2: Preserve Accepted Proposal History

**Files:**
- Modify: `apps/api/hxy_product/operating_repository.py`
- Modify: `apps/api/hxy_product/operating_service.py`
- Test: `tests/test_hxy_operating_workflow.py`

**Steps:**
1. Add failing tests for original `decided_at` and an inactive historical decider.
2. Run each test and verify the expected failure.
3. Read `decided_at`, avoid reauthorizing a completed decision, and record materialization separately from decision state history.
4. Run the operating workflow tests and verify green.

### Task 3: Enforce Governance and Aggregate Consistency

**Files:**
- Modify: `apps/api/hxy_product/operating_repository.py`
- Modify: `apps/api/hxy_product/operating_service.py`
- Modify: `apps/api/hxy_product/operating_schemas.py`
- Test: `tests/test_hxy_operating_workflow.py`

**Steps:**
1. Add failing tests for governance action-role restriction, task/workflow event mismatch, and multiple workflow instances.
2. Run the focused tests and verify the expected failures.
3. Validate aggregate ownership, reject unsupported multiple workflows, and let governance configuration only narrow the safe role ceilings.
4. Synchronize the event owner on assignment.
5. Run focused operating and task tests and verify green.

### Task 4: Verify and Commit

**Files:**
- Verify all Task 7 files and migrations.

**Steps:**
1. Run focused tests for operating workflows and legacy tasks.
2. Run the full pytest suite.
3. Run Python compile checks and `git diff --check`.
4. Inspect `git status` for unrelated or generated files.
5. Commit the reviewed Task 7 change as `feat: add governed operating workflow`.
