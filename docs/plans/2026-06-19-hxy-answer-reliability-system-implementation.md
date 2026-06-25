# HXY Answer Reliability System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn the HXY operating brain from retrieval-style answers into a reliable team answer system with golden questions, approved answer cards, answer quality scoring, and correction loops.

**Architecture:** Add deterministic reliability modules under `apps/api/hxy_knowledge/`: a golden question set, built-in authority answer cards, scoring, and correction packaging. Keep FastAPI and repository contracts intact, and enrich `/api/knowledge/chat` and `/api/knowledge/feedback` responses without requiring a schema migration.

**Tech Stack:** Python 3, FastAPI, unittest, PostgreSQL repository abstraction, static admin HTML.

---

### Task 1: Golden Questions and Authority Cards

**Files:**
- Create: `apps/api/hxy_knowledge/golden_questions.py`
- Test: `tests/test_hxy_knowledge_service.py`

**Steps:**
1. Write failing tests that assert the six core golden questions exist.
2. Include intent, aliases, applicable scenarios, forbidden terms, role-specific versions, review status, and version for each question.
3. Implement `golden_questions()` and `authority_cards()`.
4. Run targeted service tests.

### Task 2: Reliability Scoring

**Files:**
- Create: `apps/api/hxy_knowledge/reliability.py`
- Modify: `apps/api/hxy_knowledge/answer_engine.py`
- Test: `tests/test_hxy_knowledge_service.py`

**Steps:**
1. Write failing tests for answer quality scoring dimensions: domain match, usable conclusion, metadata noise, overclaim risk, review need, answer-card suggestion.
2. Implement `score_answer_quality(...)`.
3. Add score output to synthesized RAG answers and approved-card answers.
4. Run targeted service tests.

### Task 3: Chat Routing Upgrade

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Steps:**
1. Write failing API tests that a golden question returns from an authority answer card before search.
2. Write failing API tests that weak evidence returns a clarifying question or insufficient status instead of a confident answer.
3. Implement built-in card lookup after DB-approved card lookup and before RAG.
4. Attach `quality_score`, `quality_dimensions`, `authority_card`, `role_versions`, `forbidden_terms`, `version`, and `review_status`.
5. Run targeted API tests.

### Task 4: Correction Loop Upgrade

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Create or reuse: `apps/api/hxy_knowledge/reliability.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Steps:**
1. Write failing tests that incorrect/needs_work feedback creates a correction package with error type, missing info, recommended reviewer, replacement answer-card draft, and replace-old-answer action.
2. Implement correction package enrichment.
3. Ensure duplicate review tasks still dedupe by normalized question.
4. Run targeted API tests.

### Task 5: Full Verification

**Files:**
- All changed files.

**Steps:**
1. Run `python3 -m unittest discover -s tests -v`.
2. Run `python3 -m py_compile apps/api/hxy_knowledge/*.py apps/api/hxy_knowledge_api.py scripts/*.py`.
3. Run `node` syntax check for `apps/admin-web/brain.html`.
4. Restart the local API service.
5. Smoke test `/api/knowledge/chat` for all six golden questions.
