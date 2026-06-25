# HXY Operating Result Delivery Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the current HXY brain from answer-first chat to stable operating result delivery cards.

**Architecture:** Keep the current FastAPI + PostgreSQL + static HTML architecture. Add a deterministic `result_card` layer in `answer_engine.py`, persist it inside the existing answer run payload, and render it in `brain.html` without exposing internal evidence by default.

**Tech Stack:** Python FastAPI, unittest, static HTML/CSS/JavaScript, PostgreSQL-backed repository.

---

### Task 1: Add Result Card API Contract

**Files:**
- Modify: `apps/api/hxy_knowledge/answer_engine.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Steps:**

1. Write a failing API test asserting `/api/knowledge/chat` returns `result_card`.
2. Assert `result_card` includes `result_type`, `usable_answer`, `business_result`, `risk_boundary`, `quality_gates`, `review_owner`, and `stability_level`.
3. Implement deterministic helpers in `answer_engine.py`.
4. Add `result_card` to both synthesized answers and approved answer-card responses.
5. Run the targeted API test.

### Task 2: Add Quality Gates

**Files:**
- Modify: `apps/api/hxy_knowledge/answer_engine.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Steps:**

1. Write failing tests for metadata-noise and unrelated-domain answers.
2. Implement five quality gates: business domain, clean conclusion, no internal noise, scenario fit, no overclaim.
3. Map failed gates to `review_required` or `insufficient`.
4. Run targeted tests.

### Task 3: Render Result Card In Frontend

**Files:**
- Modify: `apps/admin-web/brain.html`
- Test: `tests/test_hxy_brain_frontend.py`

**Steps:**

1. Write failing frontend tests for labels: `经营结果`, `可直接使用版本`, `风险边界`, `质量闸口`.
2. Update `addAnswer` and `updateCurrentDetail` to prefer `result.result_card`.
3. Keep source paths only in internal review.
4. Run frontend tests and JS syntax check.

### Task 4: Verify End To End

**Files:**
- Runtime only.

**Steps:**

1. Run all relevant unittest suites.
2. Run Python compile check.
3. Restart API on `18081`.
4. Open same-origin entry `http://127.0.0.1:18081/brain.html`.
5. POST a real chat request for 门店模型 and confirm `result_card` exists.
