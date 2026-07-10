# HXY Knowledge Activation Loop V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Make parsed assignment-private materials searchable and citable in HXYOS conversations without promoting them to formal knowledge.

**Architecture:** PostgreSQL stores a separate assignment-scoped material chunk index and product answer traces. The material worker writes chunks when parsing succeeds. A product repository adapter merges private reference context with the existing governed answer pipeline while preserving approved answer-card precedence.

**Tech Stack:** Python 3.12, FastAPI, PostgreSQL 16, psycopg 3, React/TypeScript, pytest, Vitest, Playwright.

---

### Task 1: Private Chunk And Trace Schema

**Files:**
- Create: `data/migrations/014_hxy_knowledge_activation.sql`
- Create: `tests/test_hxy_knowledge_activation.py`

**Steps:**

1. Write failing migration contract tests for chunks, assignment ownership, non-authority checks, trigram indexes and answer traces.
2. Run `.venv/bin/pytest tests/test_hxy_knowledge_activation.py -q` and verify RED.
3. Add migration 014 without seed data or formal knowledge writes.
4. Run the focused test and verify GREEN.
5. Commit as `feat: add private material knowledge activation schema`.

### Task 2: Deterministic Chunking And Worker Persistence

**Files:**
- Create: `apps/api/hxy_product/material_chunker.py`
- Modify: `apps/api/hxy_product/material_worker.py`
- Modify: `apps/api/hxy_product/material_repository.py`
- Modify: `tests/test_hxy_material_worker.py`
- Modify: `tests/test_hxy_material_intake_jobs.py`

**Steps:**

1. Write failing tests for heading preservation, paragraph boundaries, overlap, caps and empty content.
2. Write failing worker/repository tests requiring chunks in the same completion transaction.
3. Run focused tests and verify RED.
4. Implement the pure chunker and transactional chunk inserts.
5. Run focused tests and verify GREEN.
6. Commit as `feat: index parsed materials for private retrieval`.

### Task 3: Assignment-Scoped Retrieval Adapter

**Files:**
- Create: `apps/api/hxy_product/knowledge_context.py`
- Modify: `apps/api/hxy_product/material_repository.py`
- Modify: `tests/test_hxy_knowledge_activation.py`

**Steps:**

1. Write failing tests for keyword retrieval, latest-material retrieval, public-safe source ids and assignment isolation.
2. Write failing adapter tests for merged ranking and repository delegation.
3. Run focused tests and verify RED.
4. Implement material search SQL and the assignment repository adapter.
5. Run focused tests and verify GREEN.
6. Commit as `feat: retrieve assignment private knowledge context`.

### Task 4: Product Answers, Citations And Trace

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `apps/api/hxy_knowledge/answer_engine.py`
- Modify: `apps/api/hxy_product/conversation_routes.py`
- Modify: `apps/api/hxy_product/conversation_repository.py`
- Modify: `apps/api/hxy_product/conversation_schemas.py`
- Modify: `apps/hxy-web/src/api/conversations.ts`
- Modify: `apps/hxy-web/src/App.tsx`
- Modify: relevant Python and web tests

**Steps:**

1. Write failing product answer tests proving private context is assignment-scoped and never approved.
2. Write failing source-link sanitization and Trace persistence tests.
3. Run focused Python/web tests and verify RED.
4. Inject the assignment repository adapter into product answer generation.
5. Preserve safe material source URLs through the evidence and public payload layers.
6. Persist one Trace with assistant completion and render an optional source link in the existing detail drawer.
7. Run focused tests and verify GREEN.
8. Commit as `feat: cite private materials in governed conversations`.

### Task 5: Real Database And Full Verification

**Files:**
- Modify: `tests/test_hxy_material_jobs_postgres.py`
- Modify: `docs/operations/hxy-material-intake-runtime.md`

**Steps:**

1. Extend the optional PostgreSQL test through migration 014, chunk search, assignment isolation and answer Trace constraints.
2. Apply migrations 001-014 to an isolated PostgreSQL 16 database.
3. Run the integration test with `HXY_TEST_DATABASE_URL`.
4. Run `npm test`.
5. Run `npm run build:web`.
6. Run secret and public-release scans.
7. Commit operations updates and push the feature branch.
