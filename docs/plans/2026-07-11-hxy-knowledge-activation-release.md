# HXY Knowledge Activation Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a guarded, auditable release package for activating HXY Knowledge Activation Loop V1 without automatically changing production.

**Architecture:** A small Python release module owns DSN redaction, the exact `009-014` migration inventory, read-only PostgreSQL checks, backup manifests and migration authorization. A thin CLI exposes preflight, backup, apply and postflight commands. Production service activation remains a documented operator gate after isolated PostgreSQL 16 rehearsal.

**Tech Stack:** Python 3.12, psycopg 3, PostgreSQL 16 command-line tools, pytest, Bash/systemd runbooks.

---

### Task 1: Release Contract And Safe CLI

**Files:**
- Create: `apps/api/hxy_release/__init__.py`
- Create: `apps/api/hxy_release/activation_release.py`
- Create: `scripts/hxy-activation-release.py`
- Create: `tests/test_hxy_activation_release.py`

**Step 1: Write failing release-contract tests**

Test that the release module:

- allows exactly migrations `009-014` in order;
- computes a SHA-256 for every migration;
- parses a psycopg DSN into host, port, database and user without returning the password;
- rejects an htops database name or root path;
- emits bounded JSON without full DSNs or credentials;
- exposes only `preflight`, `backup`, `apply` and `postflight` commands.

**Step 2: Run tests and verify RED**

```bash
.venv/bin/pytest tests/test_hxy_activation_release.py -q
```

Expected: fail because `hxy_release.activation_release` and the CLI do not exist.

**Step 3: Implement the minimal release contract**

Add:

```python
ACTIVATION_MIGRATIONS = (
    "009_hxy_product_identity.sql",
    "010_hxy_product_conversations.sql",
    "011_hxy_product_materials.sql",
    "012_hxy_assignment_sessions.sql",
    "013_hxy_material_intake_jobs.sql",
    "014_hxy_knowledge_activation.sql",
)
```

Implement migration inventory, credential-free database identity, HXY boundary validation, structured result helpers and argument parsing. Do not connect to PostgreSQL or run subprocesses yet.

**Step 4: Run tests and verify GREEN**

```bash
.venv/bin/pytest tests/test_hxy_activation_release.py -q
```

**Step 5: Commit**

```bash
git add apps/api/hxy_release scripts/hxy-activation-release.py tests/test_hxy_activation_release.py
git commit -m "feat: add guarded activation release contract"
```

### Task 2: Read-Only Preflight And Postflight

**Files:**
- Modify: `apps/api/hxy_release/activation_release.py`
- Modify: `scripts/hxy-activation-release.py`
- Modify: `tests/test_hxy_activation_release.py`
- Modify: `tests/test_hxy_material_jobs_postgres.py`

**Step 1: Write failing read-only check tests**

Use fake psycopg connections to require:

- `preflight` enables a read-only transaction before inspection;
- PostgreSQL major version must be 16;
- baseline tables `staff_accounts` and `stores` must exist;
- database and root boundaries must be HXY-owned;
- migration inventory is present and stable;
- preflight reports postflight tables as pending without treating that as a write;
- `postflight` requires all product/material/chunk/Trace tables, governance constraints and the trigram index;
- SQL inspection never contains `INSERT`, `UPDATE`, `DELETE`, `ALTER`, `CREATE`, `DROP` or `TRUNCATE`.

Extend the optional PostgreSQL test to call postflight after applying `001-014`.

**Step 2: Run tests and verify RED**

```bash
.venv/bin/pytest tests/test_hxy_activation_release.py tests/test_hxy_material_jobs_postgres.py -q
```

Expected: release tests fail; PostgreSQL test may skip without `HXY_TEST_DATABASE_URL`.

**Step 3: Implement database inspection**

Add injectable connection creation and these read-only checks:

```text
server_version_num
current_database/current_user/server address
baseline table existence
activation table existence
official_use_allowed check constraints
assignment ownership foreign keys
assistant Trace uniqueness
idx_hxy_material_chunks_content_trgm
```

Return only check names, status and bounded metadata. Do not return SQL, row data, paths, DSNs or credentials.

**Step 4: Run focused tests and verify GREEN**

```bash
.venv/bin/pytest tests/test_hxy_activation_release.py tests/test_hxy_material_jobs_postgres.py -q
```

**Step 5: Commit**

```bash
git add apps/api/hxy_release/activation_release.py scripts/hxy-activation-release.py tests/test_hxy_activation_release.py tests/test_hxy_material_jobs_postgres.py
git commit -m "feat: verify activation release boundaries"
```

### Task 3: Verified Backup And Bounded Migration

**Files:**
- Modify: `apps/api/hxy_release/activation_release.py`
- Modify: `scripts/hxy-activation-release.py`
- Modify: `tests/test_hxy_activation_release.py`

**Step 1: Write failing backup and apply tests**

With an injected subprocess runner, test that:

- backup invokes `pg_dump` custom format without placing the password in arguments;
- backup verifies the dump with `pg_restore --list`;
- backup directory is `0700` and files are `0600`;
- manifest contains redacted database identity, dump SHA-256, size, time, Git commit and exact migration checksums;
- a partial or unverifiable dump is rejected;
- apply rejects a missing, stale, mismatched or modified manifest;
- apply rejects every confirmation except `APPLY-HXY-009-014`;
- apply invokes `psql` with one transaction, `ON_ERROR_STOP=1`, an advisory lock and only files `009-014`;
- subprocess arguments and structured output never contain the password;
- apply does not start, stop or restart any service.

**Step 2: Run tests and verify RED**

```bash
.venv/bin/pytest tests/test_hxy_activation_release.py -q
```

**Step 3: Implement backup and apply**

Convert the DSN into `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD` subprocess environment variables. Never pass the complete DSN in argv.

Run backup as:

```text
pg_dump --format=custom --no-owner --no-acl --file <dump>
pg_restore --list <dump>
```

Run apply as one `psql --single-transaction` process with the exact migration files and an advisory transaction lock. Validate the backup manifest immediately before spawning `psql`, then run postflight after successful migration.

**Step 4: Run focused tests and verify GREEN**

```bash
.venv/bin/pytest tests/test_hxy_activation_release.py -q
```

**Step 5: Commit**

```bash
git add apps/api/hxy_release/activation_release.py scripts/hxy-activation-release.py tests/test_hxy_activation_release.py
git commit -m "feat: guard activation backup and migration"
```

### Task 4: Runbook, Isolated Rehearsal And Full Verification

**Files:**
- Create: `docs/operations/hxy-knowledge-activation-release.md`
- Modify: `docs/operations/hxy-material-intake-runtime.md`
- Modify: `tests/test_hxy_activation_release.py`

**Step 1: Write failing runbook contract tests**

Require the runbook to document:

- preflight, backup, apply and postflight commands;
- API-first and worker-second canary order;
- the exact confirmation phrase;
- assignment-isolation acceptance;
- stop conditions;
- code rollback before database restore;
- no automatic restore, formal-knowledge approval or production deployment;
- no htops paths or services.

**Step 2: Run tests and verify RED**

```bash
.venv/bin/pytest tests/test_hxy_activation_release.py -q
```

**Step 3: Write the operator runbook**

Document exact commands with placeholders for local secrets. Keep production execution as a separate explicit decision. Link the material runtime document to the release runbook and mark the old all-migration script as bootstrap-only.

**Step 4: Rehearse in isolated PostgreSQL 16**

1. Create an isolated HXY test database.
2. Apply migrations `001-008` as the simulated current state.
3. Run release preflight.
4. Run release backup and validate its manifest.
5. Run guarded apply with `APPLY-HXY-009-014`.
6. Run postflight.
7. Run `tests/test_hxy_material_jobs_postgres.py` against the same database.
8. Delete the isolated database and backup directory.

Do not point the rehearsal at the production `hxy` database.

**Step 5: Run full verification**

```bash
npm test
npm run build:web
.venv/bin/python scripts/check-hxy-secrets.py
.venv/bin/python scripts/check-hxy-public-release.py
git diff --check
```

**Step 6: Commit and push**

```bash
git add docs/operations tests/test_hxy_activation_release.py
git commit -m "docs: add activation release runbook"
git push origin feature/hxyos-product-shell-v1
```

Production database migration and service activation remain out of scope for this plan.
