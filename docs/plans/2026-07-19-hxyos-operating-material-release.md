# HXYOS Operating And Material Release Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a guarded production release profile for the contiguous HXY migrations `020-023`, then activate the verified code and material safety runtime without touching `/root/htops`.

**Architecture:** Reuse the existing HXY guarded migration primitives for immutable Git source checks, database identity pinning, restorable backups, single-transaction application, advisory locking, and postflight inspection. The profile treats migrations `020-023` as one release because `022` depends on `021` and `023` depends on the existing material job schema. Runtime activation remains separate from schema mutation: ClamAV is a loopback-only sidecar and the API/worker switch happens only after the release seal and migration postflight pass.

**Tech Stack:** Python 3.12, FastAPI, psycopg 3, PostgreSQL 16, systemd, Docker Compose, pytest.

---

### Task 1: Define the guarded release contract

**Files:**
- Create: `tests/test_hxy_operating_material_release.py`
- Create: `apps/api/hxy_release/operating_material_release.py`
- Create: `scripts/hxy-operating-material-release.py`

**Step 1: Write the failing contract tests**

Cover the exact migration tuple, confirmation string, pending/partial/applied state classification, required table/column postflight contract, and rejection of a dirty source.

**Step 2: Run the focused test to verify it fails**

Run: `.venv/bin/pytest tests/test_hxy_operating_material_release.py -q`

Expected: collection fails because the release module does not exist.

**Step 3: Implement the minimal release profile**

Use `MigrationReleaseSpec` and the existing guarded migration functions. Read migration bytes from Git `HEAD`, require a clean commit for preflight/apply, and never accept a caller-selected migration path.

**Step 4: Run the focused test to verify it passes**

Run: `.venv/bin/pytest tests/test_hxy_operating_material_release.py -q`

Expected: all focused release tests pass.

**Step 5: Commit**

```bash
git add apps/api/hxy_release/operating_material_release.py \
  scripts/hxy-operating-material-release.py \
  tests/test_hxy_operating_material_release.py \
  docs/plans/2026-07-19-hxyos-operating-material-release.md
git commit -m "feat: add guarded operating material release"
```

### Task 2: Document production activation

**Files:**
- Create: `docs/operations/hxy-operating-material-release.md`
- Modify: `ops/env/hxy-knowledge-api.env.example`

**Step 1: Write the runbook contract test**

Require the runbook to name the exact release confirmation, backup manifest, ClamAV loopback binding, release seal, atomic `current` switch, and rollback evidence.

**Step 2: Run it to verify it fails**

Run: `.venv/bin/pytest tests/test_hxy_operating_material_release.py -q`

Expected: the documentation assertions fail.

**Step 3: Add the bounded runbook and non-secret scanner settings**

Keep passwords, tokens, and model keys out of tracked files. State that existing HXY uploads remain private and are never copied to `/root/htops`.

**Step 4: Run focused tests and release guards**

Run: `.venv/bin/pytest tests/test_hxy_operating_material_release.py -q`

Run: `python3 scripts/check-hxy-secrets.py && python3 scripts/check-hxy-public-release.py && git diff --check`

### Task 3: Execute the release gates

**Step 1: Build and seal an immutable detached release**

Run the project release checklist from the clean approved commit; do not modify the dirty main worktree.

**Step 2: Run read-only preflight and create a restorable backup**

Use the release CLI with `/root/hxy/ops/env/hxy-knowledge-api.env` loaded without printing it.

**Step 3: Apply only `020-023` with `APPLY-HXY-020-023`**

Stop on any failed preflight, backup validation, postflight, or instance fingerprint check.

**Step 4: Start ClamAV and verify the scanner health**

Bind only `127.0.0.1:3310`, wait for a healthy signature database, then run one material worker cycle.

**Step 5: Atomically activate and smoke test**

Switch `/root/hxy/releases/current`, restart HXY API/web/worker, and verify authenticated material and operating routes plus a real private upload through scan, parse, artifact and search.

