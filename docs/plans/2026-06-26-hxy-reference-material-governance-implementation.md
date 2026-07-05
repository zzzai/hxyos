# HXY Reference Material Governance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make HXY treat all non-approved materials as reference-only evidence that can be organized by AI but cannot become authoritative answers without human review.

**Architecture:** Extend the existing answer pipeline with evidence lifecycle detection. Approved answer-card evidence keeps the current direct-answer behavior. Reference-only, draft, low-confidence, stale, or disputed evidence forces `needs_review`, changes the answer type to a draft/review response, and triggers answer-card draft plus review-task actions. Keep the implementation deterministic and model-router compatible.

**Tech Stack:** Python standard library, existing FastAPI knowledge service, unittest/pytest, current `ModelRouter`.

---

### Task 1: Add Reference-Only Pipeline Tests

**Files:**
- Modify: `tests/test_hxy_knowledge_service.py`

**Steps:**
1. Add a failing test that calls `build_answer_pipeline` with evidence status `reference`.
2. Assert `policy_decision.action == "needs_review"`.
3. Assert `answer_builder.answer_type == "reference_draft"`.
4. Assert `evidence_plan.sources` includes `参考资料`.
5. Assert `evolution_actions` includes `create_review_task` and `create_answer_card_draft`.
6. Run `python -m pytest tests/test_hxy_knowledge_service.py -q`.

### Task 2: Implement Evidence Lifecycle Detection

**Files:**
- Modify: `apps/api/hxy_knowledge/answer_pipeline.py`

**Steps:**
1. Add small helpers that inspect evidence `status`, `stage`, `domain`, and `source_type`.
2. Treat only approved answer cards as authoritative.
3. Treat `reference`, `ai_structured`, `draft`, `needs_review`, `disputed`, and `superseded` as not authoritative.
4. Make reference-only evidence force `needs_review`.
5. Keep existing overclaim and low-confidence behavior intact.
6. Run targeted tests.

### Task 3: Add Conflict/Disputed Pipeline Tests

**Files:**
- Modify: `tests/test_hxy_knowledge_service.py`

**Steps:**
1. Add a failing test with evidence status `disputed` or `contradicts`.
2. Assert the answer requires review.
3. Assert the risk flags or evidence plan indicate conflict.
4. Run targeted tests.

### Task 4: Implement Conflict Guardrail

**Files:**
- Modify: `apps/api/hxy_knowledge/answer_pipeline.py`

**Steps:**
1. Detect evidence fields `status=disputed`, `contradicts`, or `conflict=true`.
2. Add a user-safe finding such as `证据冲突`.
3. Force review and draft output.
4. Avoid exposing technical fields in the main answer.
5. Run targeted tests.

### Task 5: Document API/Product Semantics

**Files:**
- Modify: `README.md`
- Modify: `knowledge/okf/README.md`

**Steps:**
1. Add a short section explaining reference material governance.
2. State that all current materials are reference-only until approved.
3. State that approved answer cards are the only authoritative source for direct answers.
4. Run markdown-free smoke checks via tests.

### Task 6: Full Verification

**Files:**
- No new files.

**Steps:**
1. Run `npm test`.
2. Run `npm audit --audit-level=moderate`.
3. Run `git status --short`.
4. Report changed files and verification results.
