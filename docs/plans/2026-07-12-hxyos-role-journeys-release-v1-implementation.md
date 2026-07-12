# HXYOS Role Journeys Release V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a guarded, testable release path for migrations `015-016` and document activation from a clean immutable release worktree.

**Architecture:** Extract the database-agnostic backup, manifest and transactional migration mechanics from the existing activation release into an internal guarded migration module while preserving the current `009-014` CLI contract. Add a dedicated role-journeys release profile with its own prerequisite inspection, postflight rules, confirmation phrase, backup namespace and CLI.

**Tech Stack:** Python 3.12, argparse, psycopg 3, PostgreSQL 16, pg_dump/pg_restore/psql, pytest, systemd runbook.

---

### Task 1: Introduce Generic Guarded Migration Primitives

**Files:**
- Create: `apps/api/hxy_release/guarded_migration.py`
- Create: `tests/test_hxy_guarded_migration.py`

**Step 1: Write failing tests**

Cover a `MigrationReleaseSpec` with:

```python
spec = MigrationReleaseSpec(
    release_id="test-015-016",
    manifest_version="test-backup.v1",
    migrations=("015.sql", "016.sql"),
    confirmation="APPLY-TEST-015-016",
    advisory_lock="test-015-016",
    dump_filename="before-test.dump",
)
```

Tests must prove:

- migration inventory is checksum-bound to the spec;
- backup manifests include the release id, Git commit and exact inventory;
- another release spec cannot validate the manifest;
- stale, altered or wrong-database manifests fail;
- the exact confirmation is required;
- apply uses `--single-transaction`, `ON_ERROR_STOP=1`, one advisory lock and only the profile migrations;
- failed migration or failed postflight raises `ReleaseExecutionError`;
- rendered results redact DSN and password.

**Step 2: Verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_guarded_migration.py -q
```

Expected: FAIL because `apps.api.hxy_release.guarded_migration` does not exist.

**Step 3: Implement minimal generic core**

Move or implement the reusable mechanics without product-specific table checks:

```python
@dataclass(frozen=True)
class MigrationReleaseSpec:
    release_id: str
    manifest_version: str
    migrations: tuple[str, ...]
    confirmation: str
    advisory_lock: str
    dump_filename: str
```

Public functions:

```text
migration_inventory
database_identity
validate_hxy_boundary
render_result
create_release_backup
validate_release_backup_manifest
apply_release_migrations
```

The core accepts injected preflight/postflight inspectors and command runners for tests.

**Step 4: Verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_hxy_guarded_migration.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_release/guarded_migration.py tests/test_hxy_guarded_migration.py
git commit -m "feat: add generic guarded migration release core"
```

### Task 2: Preserve The Existing Activation Release Contract

**Files:**
- Modify: `apps/api/hxy_release/activation_release.py`
- Test: `tests/test_hxy_activation_release.py`

**Step 1: Add regression assertions before refactoring**

Add or retain tests proving:

```text
ACTIVATION_MIGRATIONS = 009-014
confirmation = APPLY-HXY-009-014
manifest version remains hxy-activation-backup.v1
dump filename remains hxy-before-activation.dump
CLI JSON and exit codes remain unchanged
```

**Step 2: Verify tests pass before refactor**

Run:

```bash
.venv/bin/pytest tests/test_hxy_activation_release.py -q
```

Expected: PASS.

**Step 3: Delegate common mechanics**

Define an activation release spec and keep the existing public wrapper names:

```python
ACTIVATION_RELEASE = MigrationReleaseSpec(...)

def create_backup(...):
    return create_release_backup(ACTIVATION_RELEASE, ...)
```

Keep activation-specific preflight and postflight inspection in
`activation_release.py`.

**Step 4: Verify no regression**

Run:

```bash
.venv/bin/pytest tests/test_hxy_activation_release.py tests/test_hxy_guarded_migration.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_release/activation_release.py tests/test_hxy_activation_release.py
git commit -m "refactor: share guarded release mechanics"
```

### Task 3: Add The Role Journeys Release Profile

**Files:**
- Create: `apps/api/hxy_release/role_journeys_release.py`
- Create: `scripts/hxy-role-journeys-release.py`
- Create: `tests/test_hxy_role_journeys_release.py`

**Step 1: Write failing profile tests**

Test these constants and behavior:

```text
migrations = 015_hxy_product_tasks.sql, 016_hxy_product_training.sql
confirmation = APPLY-HXY-015-016
manifest = hxy-role-journeys-backup.v1
dump = hxy-before-role-journeys.dump
backup root = data/backups/role-journeys
```

Preflight tests must fail when activation prerequisites are missing and pass when
`009-014` structures and assignment session scope exist.

Postflight tests must verify:

- `hxy_product_tasks`;
- `hxy_product_task_events`;
- `hxy_product_training_sessions`;
- `parent_task_id`;
- same-store parent foreign key;
- task event append-only triggers;
- training append-only triggers;
- organization/store/assignment foreign keys;
- active-task and training indexes.

**Step 2: Verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_role_journeys_release.py -q
```

Expected: FAIL because the profile and CLI do not exist.

**Step 3: Implement profile and CLI**

Commands:

```bash
python3 scripts/hxy-role-journeys-release.py preflight
python3 scripts/hxy-role-journeys-release.py backup
python3 scripts/hxy-role-journeys-release.py apply \
  --backup-manifest <path> \
  --confirm APPLY-HXY-015-016
python3 scripts/hxy-role-journeys-release.py postflight
```

All mutating behavior must flow through the generic guarded migration core.

**Step 4: Verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_hxy_role_journeys_release.py \
  tests/test_hxy_guarded_migration.py \
  tests/test_hxy_activation_release.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_release/role_journeys_release.py \
  scripts/hxy-role-journeys-release.py \
  tests/test_hxy_role_journeys_release.py
git commit -m "feat: guard role journeys database release"
```

### Task 4: Add Internal Release Runbook And Static Gates

**Files:**
- Create: `docs/operations/hxy-role-journeys-release.md`
- Modify: `scripts/check-hxy-public-release.py` only if a private-data exclusion check is missing
- Test: `tests/test_hxy_role_journeys_release.py`

**Step 1: Write a failing runbook contract test**

Assert the runbook contains:

```text
clean immutable release worktree
exact target commit
verified backup
APPLY-HXY-015-016
API and web from one commit
founder, manager and employee canaries
application rollback before database restore
no /root/htops writes
```

It must not contain credentials or a public project description.

**Step 2: Verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_role_journeys_release.py -q
```

Expected: FAIL because the runbook is missing.

**Step 3: Write the internal runbook**

Document these stop gates:

```text
code and clean commit
read-only preflight
verified backup
transactional apply
read-only postflight
API activation from release path
web activation from same commit
three role canaries
mobile smoke
completion record
```

Do not add repository marketing copy or public GitHub documentation.

**Step 4: Verify GREEN**

Run:

```bash
.venv/bin/pytest tests/test_hxy_role_journeys_release.py -q
python3 scripts/check-hxy-public-release.py
git diff --check
```

Expected: PASS.

**Step 5: Commit**

```bash
git add docs/operations/hxy-role-journeys-release.md \
  tests/test_hxy_role_journeys_release.py
git commit -m "docs: add internal role journeys release runbook"
```

### Task 5: Verify Real PostgreSQL Upgrade Paths

**Files:**
- Test only; do not change production database.

**Step 1: Verify old production shape upgrade**

Create a disposable PostgreSQL database, apply current `001-014`, run the new release CLI
against it, and verify:

```text
backup passes
015-016 apply passes
postflight passes
same-store parent accepted
cross-store parent rejected
```

**Step 2: Verify idempotent existing-015 upgrade**

Create another disposable database, apply `001-015`, then apply current `016` through the
profile and verify the same postflight contract.

**Step 3: Verify fresh install**

Apply `001-016` to a third disposable database and verify all release tables exist.

**Step 4: Record only bounded evidence**

Do not commit dumps, manifests, passwords, DSNs or private knowledge. Remove all disposable
databases after verification.

### Task 6: Full Verification, Review And Push

**Files:**
- No new production behavior unless review finds an issue.

**Step 1: Run full verification**

```bash
.venv/bin/pytest -q
npm --prefix apps/hxy-web test -- --run
npm --prefix apps/hxy-web run build
npm --prefix apps/hxy-web run test:e2e
python3 scripts/check-hxy-public-release.py
git diff --check
```

Expected:

```text
all Python tests pass
all web tests pass
build succeeds
all Playwright role journeys pass
public release preflight passes
no whitespace errors
```

**Step 2: Request independent review**

Review only Critical/Important findings for:

- credential redaction;
- backup binding and freshness;
- wrong-database protection;
- exact migration inventory;
- transaction and advisory lock behavior;
- activation release regression;
- `/root/htops` boundary;
- runbook rollback safety.

**Step 3: Remove local dependency symlinks**

```bash
rm apps/hxy-web/node_modules
```

Do not remove the shared dependency target or private `knowledge/raw` source.

**Step 4: Push internal branch**

```bash
git push -u origin feature/hxyos-role-journeys-release-v1
```

Do not add a public project description. GitHub integration may remain a minimal internal
branch until API authentication is repaired.
