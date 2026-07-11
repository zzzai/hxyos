# HXY Founder Bootstrap And Session Link Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Create the first governed founder identity and a one-time URL-fragment session exchange that opens the existing HXYOS conversation UI on desktop or mobile without a password form.

**Architecture:** A dedicated bootstrap module atomically creates the first account, organization, founder assignment and short-lived hashed session grant. The existing identity repository rotates that grant into a normal session through a same-origin API. The React session provider consumes and clears the URL fragment before loading `/api/v1/me`.

**Tech Stack:** Python 3.12, FastAPI, psycopg 3, PostgreSQL 16, React/TypeScript, pytest, Vitest, Playwright.

---

### Task 1: Atomic Founder Bootstrap CLI

**Files:**
- Create: `apps/api/hxy_product/founder_bootstrap.py`
- Create: `scripts/bootstrap-hxy-founder.py`
- Create: `tests/test_hxy_founder_bootstrap.py`

**Steps:**

1. Write failing tests for exact confirmation, bounded metadata, gateway-only password marker, 256-bit token entropy, SHA-256-only persistence, fragment URL construction and refusal when any identity row exists.
2. Run `.venv/bin/pytest tests/test_hxy_founder_bootstrap.py -q` and verify RED.
3. Implement one transaction that locks identity bootstrap state, checks all identity tables are empty and inserts account, organization, founder assignment and ten-minute session grant.
4. Add a CLI requiring `--username`, `--display-name`, `--organization-slug`, `--organization-name`, `--app-url` and `--confirm BOOTSTRAP-HXY-FOUNDER`.
5. Ensure structured output excludes password markers, token hashes and complete DSNs; print the one-time link once on stdout.
6. Run focused tests and verify GREEN.
7. Commit as `feat: bootstrap first governed founder`.

### Task 2: One-Time Session Rotation API

**Files:**
- Modify: `apps/api/hxy_product/repository.py`
- Modify: `apps/api/hxy_product/routes.py`
- Modify: `apps/api/hxy_product/schemas.py`
- Modify: `tests/test_hxy_product_identity.py`

**Steps:**

1. Write failing repository tests for row locking, expiry, active identity checks, assignment preservation, old-grant deletion and new-session insertion in one transaction.
2. Write failing route tests for `POST /api/v1/auth/session-grant`, exact request shape, bounded grant length, constant `401`, HttpOnly cookie and token-free JSON.
3. Run focused tests and verify RED.
4. Implement `IdentityRepository.exchange_session_grant` and the API route.
5. Reuse existing cookie security settings and normal session TTL.
6. Run focused tests and verify GREEN.
7. Commit as `feat: rotate one-time founder session grants`.

### Task 3: Invisible Frontend Session Link

**Files:**
- Modify: `apps/hxy-web/src/api/client.ts`
- Modify: `apps/hxy-web/src/features/session/SessionProvider.tsx`
- Modify: `apps/hxy-web/src/features/session/SessionProvider.test.tsx`
- Modify: `apps/hxy-web/tests/product-shell.spec.ts`

**Steps:**

1. Write failing tests proving the fragment is removed before the exchange request, exchange precedes `/api/v1/me`, invalid links enter unauthorized state and no grant appears in rendered UI.
2. Add a mobile Playwright case that opens with a fragment grant and reaches the existing conversation shell without a login form.
3. Run Web tests and verify RED.
4. Implement fragment parsing for exactly one `hxy_session_grant`, immediate `history.replaceState`, same-origin POST and normal session loading.
5. Do not add cards, forms, onboarding copy or navigation.
6. Run Web and Playwright tests and verify GREEN.
7. Commit as `feat: open HXYOS from one-time session links`.

### Task 4: PostgreSQL Integration And Release Gate

**Files:**
- Modify: `tests/test_hxy_material_jobs_postgres.py` or create `tests/test_hxy_founder_bootstrap_postgres.py`
- Create: `docs/operations/hxy-founder-bootstrap.md`
- Modify: `docs/operations/hxy-knowledge-activation-release.md`

**Steps:**

1. Add an optional PostgreSQL test that bootstraps a random founder, exchanges the grant once, rejects reuse, resolves `/me` principal data and cleans all test rows.
2. Document backup prerequisite, exact bootstrap confirmation, required metadata, one-time link handling, HTTPS requirement and rollback/cleanup boundary.
3. Apply migrations `001-014` to an isolated PostgreSQL 16 database.
4. Run bootstrap and session rotation integration tests against the isolated database.
5. Run `npm test`, `npm run build:web`, secret scan, public-release scan and `git diff --check`.
6. Commit and push the feature branch.
7. Stop before production bootstrap. Production metadata and public application URL require a separate explicit confirmation.
