# HXYOS Governed Onboarding V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a governed store and member onboarding loop so Founder can create stores and invite managers, managers can invite employees in their own store, and recipients can enter HXYOS through single-use links without passwords.

**Architecture:** Add one HXY-owned migration for invite state and append-only audit events, then expose a FastAPI router backed by a PostgreSQL repository and strict role policy. Extend the existing React session bootstrap to redeem `#invite=` links and replace the empty profile view with one minimal role-aware organization panel. Raw tokens only exist in process memory and the one-time response; persistence stores SHA-256 only.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, psycopg 3, PostgreSQL 16, React 19, TypeScript, Vitest, Playwright.

---

### Task 1: Define The Governed Onboarding Migration

**Files:**
- Create: `data/migrations/017_hxy_governed_onboarding.sql`
- Create: `tests/test_hxy_governed_onboarding.py`

**Step 1: Write the failing migration contract tests**

Add tests that parse the SQL and require:

```python
def test_onboarding_migration_scopes_invites_and_events() -> None:
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())
    assert "CREATE TABLE IF NOT EXISTS hxy_member_invites" in normalized
    assert "CREATE TABLE IF NOT EXISTS hxy_member_invite_events" in normalized
    assert "CHECK (role IN ('store_manager', 'store_employee'))" in normalized
    assert "REFERENCES hxy_organization_stores(organization_id, store_id)" in normalized
    assert "REFERENCES hxy_role_assignments(organization_id, assignment_id)" in normalized
    assert "hxy_member_invite_events is append-only" in normalized
```

Also require unique `token_hash`, status/expiry indexes, state-shape checks for pending/redeemed/revoked, and update/delete/truncate rejection for event rows.

**Step 2: Run the tests and verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_governed_onboarding.py -q
```

Expected: FAIL because migration `017` does not exist.

**Step 3: Implement the migration**

Create the two tables, composite HXY boundary foreign keys, state checks, indexes and append-only triggers. Do not seed a store, account, invite or business row.

**Step 4: Run the tests and verify GREEN**

Run the same focused pytest command. Expected: PASS.

**Step 5: Commit**

```bash
git add data/migrations/017_hxy_governed_onboarding.sql tests/test_hxy_governed_onboarding.py
git commit -m "feat: define governed onboarding storage"
```

### Task 2: Implement Pure Authorization And Validation Rules

**Files:**
- Create: `apps/api/hxy_product/onboarding_policy.py`
- Create: `apps/api/hxy_product/onboarding_schemas.py`
- Modify: `tests/test_hxy_governed_onboarding.py`

**Step 1: Write failing policy tests**

Cover this exact matrix:

```text
founder + store_manager + organization store = allow
founder + store_employee = deny
store_manager + store_employee + same store = allow
store_manager + store_manager = deny
store_manager + another store = deny
store_employee + any invite = deny
manager deactivates self = deny
manager deactivates same-store employee = allow
founder deactivates organization manager = allow
```

Add schema tests for bounded display name, store name/city/address, forbidden extra fields and a fixed 24-hour invite lifetime controlled by the server.

**Step 2: Verify RED**

Run the focused test file and confirm missing modules/functions fail.

**Step 3: Implement minimal policy helpers and Pydantic models**

Use explicit enums and immutable mappings. Policy functions receive resolved assignment/store records; they must not accept organization authority from request data.

**Step 4: Verify GREEN**

Run focused tests and `git diff --check`.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/onboarding_policy.py apps/api/hxy_product/onboarding_schemas.py tests/test_hxy_governed_onboarding.py
git commit -m "feat: enforce onboarding role policy"
```

### Task 3: Build The PostgreSQL Onboarding Repository

**Files:**
- Create: `apps/api/hxy_product/onboarding_repository.py`
- Modify: `tests/test_hxy_governed_onboarding.py`

**Step 1: Write failing repository tests with a recording fake connection**

Require repository methods:

```python
list_stores(organization_id)
create_store(organization_id, creator_assignment_id, payload)
list_members(organization_id, store_id=None)
list_invites(organization_id, store_id=None)
create_invite(..., token_hash, expires_at)
revoke_invite(...)
redeem_invite(token_hash, raw_session_token, session_ttl_seconds)
deactivate_member(...)
```

Tests must inspect SQL and prove:

- reads are organization/store scoped;
- raw token is never passed to SQL;
- redemption uses `FOR UPDATE` and one transaction;
- account, assignment, invite state, event and session are created atomically;
- deactivation revokes all sessions for the assignment;
- list results never expose `token_hash`.

**Step 2: Verify RED**

Run focused tests.

**Step 3: Implement repository and domain exceptions**

Generate server store IDs and usernames with UUID-derived identifiers. Map product roles to legacy account roles in one constant. Return bounded dictionaries only.

**Step 4: Verify GREEN**

Run focused tests and static import checks.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/onboarding_repository.py tests/test_hxy_governed_onboarding.py
git commit -m "feat: add governed onboarding repository"
```

### Task 4: Add Authenticated Management And Public Redemption APIs

**Files:**
- Create: `apps/api/hxy_product/onboarding_routes.py`
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_governed_onboarding.py`

**Step 1: Write failing FastAPI tests**

Build clients with Founder, manager and employee fake assignments. Test:

- Founder creates/list stores and invites managers.
- Manager lists only own store and invites employees.
- Employee receives `403` on every management route.
- Manager cross-store IDs return `404` or `403` without target details.
- invite create returns a single `one_time_link` with `#invite=`.
- list APIs omit token and link.
- revoke and deactivate apply the policy matrix.
- redeem endpoint returns a session cookie and generic `401` for every invalid state.
- application router is wired only when HXY database/auth settings are present.

**Step 2: Verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_governed_onboarding.py -q
```

**Step 3: Implement router and app wiring**

Use `build_principal_resolver`, `assignment_for_principal`, existing secure cookie settings and `secrets.token_urlsafe`. Hash invite tokens before repository calls. Redact database errors and never log request bodies.

**Step 4: Verify GREEN**

Run focused tests plus existing identity tests:

```bash
.venv/bin/pytest tests/test_hxy_governed_onboarding.py tests/test_hxy_product_identity.py -q
```

**Step 5: Commit**

```bash
git add apps/api/hxy_product/onboarding_routes.py apps/api/hxy_knowledge_api.py tests/test_hxy_governed_onboarding.py
git commit -m "feat: expose governed onboarding api"
```

### Task 5: Prove Real PostgreSQL Atomicity And Tenant Isolation

**Files:**
- Create: `tests/test_hxy_governed_onboarding_postgres.py`

**Step 1: Write opt-in PostgreSQL integration tests**

Use `HXY_TEST_DATABASE_URL` and isolated random IDs. Apply `001-017` to a test database. Verify:

- one invite redeems once under concurrent attempts;
- only a SHA-256 token exists in storage;
- created account/assignment/session share one HXY organization/store;
- revoked and expired invites cannot redeem;
- cross-store creator/target foreign keys fail;
- deactivation removes active sessions;
- event update/delete/truncate fail;
- cleanup removes only random test data and never connects to database `hxy` production.

**Step 2: Verify the test refuses production**

Run without `HXY_TEST_DATABASE_URL`; expected: SKIP. Set an isolated `hxy_*_test` URL and confirm test setup rejects a non-test database name.

**Step 3: Implement any repository fixes revealed by PostgreSQL**

Keep changes minimal and do not weaken migration constraints.

**Step 4: Run integration tests GREEN**

Expected: all PostgreSQL onboarding tests pass with no residual rows.

**Step 5: Commit**

```bash
git add tests/test_hxy_governed_onboarding_postgres.py apps/api/hxy_product/onboarding_repository.py
git commit -m "test: verify onboarding against postgres"
```

### Task 6: Extend The Typed Frontend API Client

**Files:**
- Modify: `apps/hxy-web/src/api/client.ts`
- Modify: `apps/hxy-web/src/api/client.test.ts`

**Step 1: Write failing client tests**

Test typed calls for stores, members, invites, create/revoke/deactivate and invite redemption. Require `credentials: "include"`, bounded response mapping and no token field in list types.

**Step 2: Verify RED**

Run:

```bash
npm --prefix apps/hxy-web test -- --run src/api/client.test.ts
```

**Step 3: Implement the minimal client methods and types**

Keep organization/store identifiers out of requests when the server can infer them. Only invite creation accepts a selected store ID for Founder.

**Step 4: Verify GREEN**

Run focused Web tests.

**Step 5: Commit**

```bash
git add apps/hxy-web/src/api/client.ts apps/hxy-web/src/api/client.test.ts
git commit -m "feat: add onboarding web client"
```

### Task 7: Redeem Invite Fragments In SessionProvider

**Files:**
- Modify: `apps/hxy-web/src/features/session/SessionProvider.tsx`
- Modify: `apps/hxy-web/src/features/session/SessionProvider.test.tsx`

**Step 1: Write failing session tests**

Require:

- `#invite=` is read once and immediately removed with `history.replaceState`;
- invite exchanger runs before `/api/v1/me` load;
- success loads the new active assignment;
- invalid invite renders the existing unauthorized state with a bounded message;
- `#grant=` founder bootstrap behavior remains unchanged;
- raw invite never enters localStorage, sessionStorage, query string or rendered text.

**Step 2: Verify RED**

Run the SessionProvider test file.

**Step 3: Implement invite exchange**

Add an injectable invite exchanger for tests and a default call to `/api/v1/onboarding/invites/redeem`. Preserve one bootstrap promise and ensure fragment cleanup happens before network work.

**Step 4: Verify GREEN**

Run SessionProvider and App tests.

**Step 5: Commit**

```bash
git add apps/hxy-web/src/features/session/SessionProvider.tsx apps/hxy-web/src/features/session/SessionProvider.test.tsx
git commit -m "feat: redeem member invite links"
```

### Task 8: Replace The Empty Profile With A Minimal Organization Panel

**Files:**
- Create: `apps/hxy-web/src/features/onboarding/OrganizationPanel.tsx`
- Create: `apps/hxy-web/src/features/onboarding/OrganizationPanel.test.tsx`
- Modify: `apps/hxy-web/src/App.tsx`
- Modify: `apps/hxy-web/src/App.css`
- Modify: `apps/hxy-web/src/App.test.tsx`

**Step 1: Write failing component tests**

Require:

- Founder sees store list, create store and invite manager actions.
- Manager sees only current-store members and invite employee action.
- Employee sees identity and logout only; no management controls.
- one-time link appears once after invite creation with an icon copy button and accessible label.
- revoke/deactivate require a compact confirmation dialog.
- no review queue, governance jargon, token hash or organization IDs appear.

**Step 2: Verify RED**

Run focused component/App tests.

**Step 3: Implement the component**

Keep the main conversation unchanged. Use existing lucide icons and visual tokens, no nested cards, no desktop-only table and no explanatory marketing copy. Stable mobile controls must fit 390px.

**Step 4: Verify GREEN**

Run Web unit tests and `npm run build:web`.

**Step 5: Commit**

```bash
git add apps/hxy-web/src/features/onboarding apps/hxy-web/src/App.tsx apps/hxy-web/src/App.css apps/hxy-web/src/App.test.tsx
git commit -m "feat: add minimal organization onboarding ui"
```

### Task 9: Add End-To-End Role And Mobile Coverage

**Files:**
- Modify: `apps/hxy-web/tests/product-shell.spec.ts`

**Step 1: Write failing Playwright tests**

Add mocked network journeys for:

```text
Founder: 我的 -> 新建门店 -> 邀请店长 -> one-time link
Manager: 我的 -> 邀请员工 -> revoke pending invite
Employee: 我的 -> no management action
Recipient: /#invite=... -> redeem -> fragment removed -> role home
```

For 390x844 and desktop, assert no horizontal overflow, fixed navigation does not cover forms, dialog buttons are clickable, long display names wrap, and no token remains in URL after exchange.

**Step 2: Verify RED**

Run only the new Playwright cases and confirm missing UI behavior fails.

**Step 3: Apply minimal UI fixes**

Do not redesign the product shell or add another dashboard.

**Step 4: Verify GREEN**

Run:

```bash
npm --prefix apps/hxy-web run test:e2e
```

**Step 5: Commit**

```bash
git add apps/hxy-web/tests/product-shell.spec.ts apps/hxy-web/src
git commit -m "test: cover governed onboarding journeys"
```

### Task 10: Full Verification And Branch Handoff

**Files:**
- Modify only files required by verified failures.

**Step 1: Run all code tests**

```bash
npm test
```

Expected: Python, TypeScript, Web and Playwright all pass.

**Step 2: Run build and release hygiene**

```bash
npm run build:web
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check
git status --short
```

Expected: build and scans pass; worktree is clean after commits.

**Step 3: Review requirement-by-requirement**

Confirm no raw token storage/logging, no employee management capability, no cross-store access, no core knowledge changes, no private materials in Git and no `/root/htops` access.

**Step 4: Push the feature branch**

```bash
git push -u origin feature/hxyos-governed-onboarding-v1
```

Do not merge `main`, apply migration `017` to production or switch services in this task.

**Step 5: Record candidate status**

Report exact commit, tests, build, branch and remaining production release gates.
