# HXYOS Governed Onboarding Release V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a guarded, repeatable production release path for migration `017` and the governed organization onboarding API/Web experience.

**Architecture:** Reuse the existing HXY-owned guarded migration primitives instead of changing the proven `015-016` release profile. Add one isolated onboarding release profile that checks the exact `017` Git blob, verifies prerequisite `009-016` structures, performs a restorable backup, applies only `017`, and validates its complete PostgreSQL contract. Keep edge throttling and atomic API/Web activation explicit in a release runbook so public invite redemption cannot be deployed without body limits, rate limiting, release markers, canaries, and rollback evidence.

**Tech Stack:** Python 3.12, psycopg 3, PostgreSQL 16, pytest, Nginx, systemd, React/Vite release artifacts.

---

### Task 1: Define The Isolated `017` Release Profile

**Files:**
- Create: `tests/test_hxy_governed_onboarding_release.py`
- Create: `apps/api/hxy_release/onboarding_release.py`
- Create: `scripts/hxy-governed-onboarding-release.py`

**Step 1: Write failing profile and CLI tests**

Require a release profile with exactly one migration, `017_hxy_governed_onboarding.sql`, confirmation `APPLY-HXY-017`, a dedicated advisory lock and backup manifest version. Require only `preflight`, `backup`, `apply`, and `postflight` commands, and prove the wrapper imports only the HXY release module.

**Step 2: Run the focused tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_governed_onboarding_release.py -q
```

Expected: collection fails because the onboarding release module does not exist.

**Step 3: Implement the minimal release profile and CLI**

Use `MigrationReleaseSpec` and the existing guarded backup/apply functions. Load migration bytes from Git `HEAD`, require a clean exact commit for preflight, and never accept a migration directory, glob, or caller-selected migration name.

**Step 4: Run focused tests and verify GREEN**

Run the focused test file and `git diff --check`.

**Step 5: Commit**

```bash
git add apps/api/hxy_release/onboarding_release.py \
  scripts/hxy-governed-onboarding-release.py \
  tests/test_hxy_governed_onboarding_release.py
git commit -m "feat: add guarded onboarding release profile"
```

### Task 2: Validate The Complete PostgreSQL Onboarding Contract

**Files:**
- Modify: `tests/test_hxy_governed_onboarding_release.py`
- Modify: `apps/api/hxy_release/onboarding_release.py`

**Step 1: Write failing postflight contract tests**

Require read-only inspection of both onboarding tables, every required column, primary/unique/check/foreign-key scope, token-hash uniqueness, status/expiry indexes, append-only row and truncate triggers, and the supporting assignment identity index. Prove that missing, malformed, disabled, unvalidated, wrong-schema, or wrong-delete-behavior objects fail closed.

**Step 2: Run focused tests and verify RED**

Expected: postflight status is failed until the inspector implements all contracts.

**Step 3: Implement preflight and postflight inspection**

Preflight must prove PostgreSQL 16, HXY repository/database boundaries, current schema `public`, prerequisite activation/role-journey structures, clean Git state, and exact `017` checksum. Postflight adds the complete onboarding schema checks and returns bounded JSON without rows, display names, tokens, cookies, or DSNs.

**Step 4: Run focused and guarded migration regressions**

```bash
.venv/bin/pytest tests/test_hxy_governed_onboarding_release.py \
  tests/test_hxy_guarded_migration.py \
  tests/test_hxy_role_journeys_release.py -q
```

**Step 5: Commit**

```bash
git add apps/api/hxy_release/onboarding_release.py \
  tests/test_hxy_governed_onboarding_release.py
git commit -m "test: enforce onboarding release contract"
```

### Task 3: Add Edge Throttling And The Production Runbook

**Files:**
- Create: `ops/nginx/hxyos-public-edge.conf.example`
- Create: `docs/operations/hxy-governed-onboarding-release.md`
- Modify: `tests/test_hxy_governed_onboarding_release.py`

**Step 1: Write failing deployment contract tests**

Require an HTTP-scope `limit_req_zone` keyed by binary remote address, an exact invite-redemption location with a small body limit and a strict burst, no token-bearing query parameters, and the existing API proxy behavior. Require ordered runbook gates for immutable source, tests/build/seal, read-only preflight, verified restore backup, exact-confirmation apply, postflight, environment validation, canary, atomic API/Web activation, log-redaction checks, session cleanup, and rollback.

**Step 2: Run tests and verify RED**

Expected: missing Nginx example and runbook fail the deployment contract.

**Step 3: Add the Nginx example and release runbook**

Use `HXY_PUBLIC_APP_URL=https://hxyos.hexiaoyue.com`, preserve URL-fragment invite delivery, and document that the public edge file must be installed on `115.190.245.14` only after `nginx -t`. Do not include credentials, private data, invitation tokens, or production DSNs.

**Step 4: Run focused tests and verify GREEN**

Run focused tests, secret scan, public release scan, and `git diff --check`.

**Step 5: Commit**

```bash
git add ops/nginx/hxyos-public-edge.conf.example \
  docs/operations/hxy-governed-onboarding-release.md \
  tests/test_hxy_governed_onboarding_release.py
git commit -m "docs: define onboarding production release"
```

### Task 4: Verify The Release Candidate

**Files:**
- Modify only files needed to fix failures found by verification.

**Step 1: Run the focused release suite**

```bash
.venv/bin/pytest tests/test_hxy_governed_onboarding_release.py -q
```

**Step 2: Run the complete project verification**

```bash
npm test
npm run build:web
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check
```

**Step 3: Verify repository boundaries and branch state**

Confirm no `/root/htops` access or changes, no private knowledge or environment file is tracked, and only the release branch contains the new work.

**Step 4: Commit any verification-only fixes**

Use a narrowly scoped commit only if verification reveals a real defect.

**Step 5: Push the release branch**

```bash
git push -u origin feature/hxyos-governed-onboarding-release-v1
```

Do not apply migration `017`, alter public Nginx, switch `releases/current`, or start production onboarding canaries as part of implementation. Those are explicit runbook gates against the approved exact commit.
