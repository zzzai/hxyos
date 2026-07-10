# HXY Material Intake Loop V2 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Turn every uploaded HXY material into a durable background parsing job that produces normalized Markdown and a non-authoritative Source Card.

**Architecture:** FastAPI saves the original and atomically creates a PostgreSQL parser job through `MaterialRepository`. A standalone worker claims jobs with leases, runs a MarkItDown adapter, writes immutable private artifacts, and commits the result or a bounded retry. The existing material API exposes only product-safe states.

**Tech Stack:** Python 3.11+, FastAPI, PostgreSQL 16, psycopg 3, MarkItDown 0.1.6, pytest, systemd.

---

### Task 1: Durable Parser Job Schema

**Files:**
- Create: `data/migrations/013_hxy_material_intake_jobs.sql`
- Create: `tests/test_hxy_material_intake_jobs.py`

**Step 1: Write failing migration contract tests**

Assert that migration 013 creates parser jobs, attempts and artifacts; adds product states; enforces material/assignment ownership; requires running leases; and fixes `official_use_allowed` to false.

**Step 2: Run the focused test and verify RED**

Run: `.venv/bin/pytest tests/test_hxy_material_intake_jobs.py -q`

Expected: FAIL because migration 013 does not exist.

**Step 3: Add the migration**

Use PostgreSQL checks, composite foreign keys and indexes for claim order, stale leases and material artifacts. Keep legacy material statuses valid for rolling migration.

**Step 4: Run the focused test and verify GREEN**

Run: `.venv/bin/pytest tests/test_hxy_material_intake_jobs.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add data/migrations/013_hxy_material_intake_jobs.sql tests/test_hxy_material_intake_jobs.py
git commit -m "feat: add durable material parser jobs"
```

### Task 2: Repository Queue And Lease Semantics

**Files:**
- Modify: `apps/api/hxy_product/material_repository.py`
- Modify: `tests/test_hxy_material_intake_jobs.py`
- Modify: `tests/test_hxy_product_materials.py`

**Step 1: Write failing repository tests**

Cover:

- `create_material` inserts a parser job in the same connection;
- idempotent replay does not enqueue a duplicate;
- `claim_next_job` uses `FOR UPDATE SKIP LOCKED` and creates an attempt;
- `complete_job` is lease-owner guarded;
- `retry_or_fail_job` applies delay and terminal state;
- `reclaim_stale_leases` makes expired work available again.

**Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest tests/test_hxy_material_intake_jobs.py tests/test_hxy_product_materials.py -q`

Expected: FAIL on missing queue methods and enqueue SQL.

**Step 3: Implement minimal repository methods**

Add row mappers and transactional methods. Never accept assignment ids from a worker payload when they can be loaded through the job/material relationship.

**Step 4: Run tests and verify GREEN**

Run: `.venv/bin/pytest tests/test_hxy_material_intake_jobs.py tests/test_hxy_product_materials.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/material_repository.py tests/test_hxy_material_intake_jobs.py tests/test_hxy_product_materials.py
git commit -m "feat: add material parser queue repository"
```

### Task 3: MarkItDown Parser And Source Card

**Files:**
- Create: `apps/api/hxy_product/material_parser.py`
- Create: `apps/api/hxy_product/source_card.py`
- Create: `tests/test_hxy_material_parser.py`

**Step 1: Write failing parser tests**

Test real `.txt` and `.docx` conversion, empty output failure, missing source, deterministic artifact storage keys, Source Card authority boundaries and absence of official-use permissions.

**Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest tests/test_hxy_material_parser.py -q`

Expected: FAIL because modules do not exist.

**Step 3: Implement parser and Source Card builder**

Use the MarkItDown Python API. The parser returns data only. Build Source Card from the preliminary understanding plus parser quality signals; never elevate authority.

**Step 4: Run tests and verify GREEN**

Run: `.venv/bin/pytest tests/test_hxy_material_parser.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/material_parser.py apps/api/hxy_product/source_card.py tests/test_hxy_material_parser.py
git commit -m "feat: parse materials into governed source cards"
```

### Task 4: Worker Runtime

**Files:**
- Create: `apps/api/hxy_product/material_worker.py`
- Create: `scripts/run-hxy-material-worker.py`
- Modify: `tests/test_hxy_material_intake_jobs.py`
- Create: `tests/test_hxy_material_worker.py`

**Step 1: Write failing worker tests**

Cover success, retryable failure, permanent failure, artifact cleanup on transaction failure, lease heartbeat/ownership and one-shot idle behavior.

**Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest tests/test_hxy_material_worker.py tests/test_hxy_material_intake_jobs.py -q`

Expected: FAIL because worker does not exist.

**Step 3: Implement one-job worker loop**

Claim a job, parse outside transactions, atomically write two artifact files, then call repository completion. Sanitize all persisted and logged errors.

**Step 4: Run tests and verify GREEN**

Run: `.venv/bin/pytest tests/test_hxy_material_worker.py tests/test_hxy_material_intake_jobs.py -q`

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/material_worker.py scripts/run-hxy-material-worker.py tests/test_hxy_material_worker.py tests/test_hxy_material_intake_jobs.py
git commit -m "feat: add material intake worker"
```

### Task 5: API Product States And Retry Requeue

**Files:**
- Modify: `apps/api/hxy_product/material_routes.py`
- Modify: `apps/api/hxy_product/material_schemas.py`
- Modify: `tests/test_hxy_product_materials.py`
- Modify: `apps/hxy-web/src/api/materials.ts`
- Modify: `apps/hxy-web/src/App.tsx`
- Modify: `apps/hxy-web/src/App.test.tsx`

**Step 1: Write failing API and UI tests**

Require upload response `processing`, successful detail `ready`, terminal failure `needs_attention`, and manual retry to requeue without invoking parser code in the request.

**Step 2: Run tests and verify RED**

Run: `.venv/bin/pytest tests/test_hxy_product_materials.py -q`

Run: `npm --prefix apps/hxy-web test -- --run`

Expected: FAIL on old internal status and synchronous retry behavior.

**Step 3: Implement product-safe mapping and polling**

Keep the existing receipt placement and composer. Add only status refresh behavior; do not add a materials dashboard.

**Step 4: Run tests and verify GREEN**

Run both focused suites again. Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/material_routes.py apps/api/hxy_product/material_schemas.py tests/test_hxy_product_materials.py apps/hxy-web/src/api/materials.ts apps/hxy-web/src/App.tsx apps/hxy-web/src/App.test.tsx
git commit -m "feat: expose durable material understanding states"
```

### Task 6: Operations And End-to-End Verification

**Files:**
- Create: `ops/systemd/hxy-material-worker.service`
- Create: `ops/hxy-material-worker.sh`
- Modify: `ops/env/hxy-knowledge-api.env.example`
- Modify: `docs/runbooks/hxy-product-runtime.md` if present, otherwise create it
- Modify: relevant operations tests under `tests/`

**Step 1: Write failing operations contract tests**

Assert HXY-owned service names, root paths, environment loading, restart policy, one-shot health command and no htops references.

**Step 2: Run focused tests and verify RED**

Run: `.venv/bin/pytest tests/test_hxy_material_worker.py tests/test_hxy_product_materials.py -q`

Expected: FAIL on missing service and launcher.

**Step 3: Add launcher, service and runbook**

Use `.venv/bin/python`, configurable poll/lease/retry values and structured stdout logs. Do not install or enable the service automatically.

**Step 4: Verify real PostgreSQL behavior**

Apply migrations 001-013 to an isolated PostgreSQL 16 database. Verify concurrent claims, stale lease reclaim, idempotent upload enqueue and artifact ownership.

**Step 5: Run full verification**

```bash
npm test
npm run build:web
.venv/bin/python scripts/check-hxy-secrets.py
.venv/bin/python scripts/check-hxy-public-release.py
```

Expected: all tests, build and scans pass.

**Step 6: Commit and push**

```bash
git add ops scripts docs tests
git commit -m "ops: run durable HXY material intake"
git push
```
