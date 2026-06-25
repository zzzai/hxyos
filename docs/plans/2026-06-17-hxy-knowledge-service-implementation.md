# HXY Knowledge Service Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a working PostgreSQL + optional pgvector + FastAPI + admin web knowledge service for HXY.

**Architecture:** Add a database migration, Python repository/import modules, a FastAPI app, import script, and an admin HTML page. Existing file-based artifacts remain the source input; PostgreSQL becomes the project-level query store.

**Tech Stack:** PostgreSQL, optional pgvector, Python 3.12, FastAPI, psycopg, plain HTML/CSS/JS admin page.

---

### Task 1: Database Schema

**Files:**
- Create: `data/migrations/002_hxy_knowledge_service.sql`

**Steps:**
1. Add extensions `pgcrypto`, `pg_trgm`, and optional `vector` in a guarded block.
2. Create `hxy_knowledge_import_runs`.
3. Create `hxy_knowledge_assets`.
4. Create `hxy_knowledge_chunks`.
5. Add GIN full-text and trigram indexes.
6. Add optional vector index only if vector type exists.

**Verification:**

```bash
psql "$HXY_DATABASE_URL" -f data/migrations/002_hxy_knowledge_service.sql
```

Expected: migration applies when a database is available.

### Task 2: Repository and Import Logic

**Files:**
- Create: `apps/api/hxy_knowledge/__init__.py`
- Create: `apps/api/hxy_knowledge/config.py`
- Create: `apps/api/hxy_knowledge/repository.py`
- Create: `apps/api/hxy_knowledge/importer.py`
- Create: `scripts/import-hxy-knowledge-db.py`
- Test: `tests/test_hxy_knowledge_service.py`

**Steps:**
1. Write tests for loading manifest/search chunks and preparing asset/chunk records.
2. Verify tests fail because modules do not exist.
3. Implement pure preparation functions.
4. Implement repository methods using psycopg.
5. Implement import script.
6. Run tests.

**Verification:**

```bash
python3 -m unittest tests/test_hxy_knowledge_service.py -v
python3 -m py_compile apps/api/hxy_knowledge/*.py scripts/import-hxy-knowledge-db.py
```

Expected: tests pass and scripts compile.

### Task 3: FastAPI Service

**Files:**
- Create: `apps/api/hxy_knowledge_api.py`
- Modify: `apps/api/hxy_knowledge/repository.py`

**Steps:**
1. Add API tests with FastAPI `TestClient` using a fake repository.
2. Verify tests fail.
3. Implement app factory and endpoints.
4. Add upload path validation so uploads stay under `knowledge/raw/inbox`.
5. Run tests.

**Verification:**

```bash
python3 -m unittest tests/test_hxy_knowledge_api.py -v
python3 -m py_compile apps/api/hxy_knowledge_api.py
```

Expected: tests pass and app compiles.

### Task 4: Admin Web Page

**Files:**
- Create: `apps/admin-web/knowledge.html`

**Steps:**
1. Build a quiet dashboard layout for operational use.
2. Add upload form.
3. Add import button.
4. Add search box and filters.
5. Add summary and assets table rendering.
6. Ensure all API calls target the FastAPI service.

**Verification:**

```bash
python3 -m http.server 18990 --directory apps/admin-web
```

Expected: `http://127.0.0.1:18990/knowledge.html` loads.

### Task 5: Dependency and Runtime Setup

**Files:**
- Create: `apps/api/requirements.txt`
- Create: `docs/operations/hxy-knowledge-service-runbook.md`

**Steps:**
1. Add required Python dependencies.
2. Document local PostgreSQL setup.
3. Document migration, import, service start, and admin page commands.

**Verification:**

```bash
python3 -m pip install --break-system-packages -r apps/api/requirements.txt
python3 -c "import fastapi, psycopg, uvicorn; print('deps ok')"
```

Expected: dependencies import.

### Task 6: End-to-End Verification

**Steps:**
1. Apply migration if `HXY_DATABASE_URL` is present.
2. Import current HXY knowledge.
3. Start FastAPI service.
4. Call health, summary, and search endpoints.
5. Serve admin page.
6. Verify no output writes to `/root/htops`.

**Verification:**

```bash
python3 -m unittest tests/test_hxy_knowledge_service.py tests/test_hxy_knowledge_api.py -v
python3 -m py_compile apps/api/hxy_knowledge/*.py apps/api/hxy_knowledge_api.py scripts/import-hxy-knowledge-db.py
rg -n "/root/htops" apps/api apps/admin-web data/migrations/002_hxy_knowledge_service.sql docs/operations/hxy-knowledge-service-runbook.md || true
```

Expected: tests pass, code compiles, and no HXY runtime code writes to htops.
