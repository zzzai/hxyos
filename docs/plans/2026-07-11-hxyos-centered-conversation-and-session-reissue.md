# HXYOS Centered Conversation And Session Reissue Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Center the empty HXYOS conversation like DataAgent and restore product access through a governed Founder session-link reissue command.

**Architecture:** Add one explicit empty-conversation class to the React shell and implement the visual transition in existing CSS. Add a host-only Python CLI that resolves the existing founder assignment and inserts a hashed, short-lived one-time grant without modifying identity records.

**Tech Stack:** React 19, TypeScript, CSS Grid, Vitest, Playwright, Python 3.12, psycopg 3, PostgreSQL 16.

---

### Task 1: Lock The Adaptive Layout Contract

**Files:**
- Modify: `apps/hxy-web/src/App.test.tsx`
- Modify: `apps/hxy-web/tests/product-shell.spec.ts`

1. Add a unit test requiring `is-conversation-empty` before the first message
   and requiring its removal after sending.
2. Add a desktop browser assertion that the empty composer is horizontally
   centered in the stage and starts near the stage's vertical center.
3. Assert that after sending, the composer moves below the central empty
   position and remains visible.
4. Run the focused tests and confirm they fail for the missing state.

### Task 2: Implement The Adaptive Layout

**Files:**
- Modify: `apps/hxy-web/src/App.tsx`
- Modify: `apps/hxy-web/src/styles/shell.css`

1. Derive the empty-conversation state from the active view and message count.
2. Add the state class to the conversation stage.
3. Place empty content and composer in one central grid area on desktop and
   mobile.
4. Preserve the current bottom composer after messages exist.
5. Run unit and browser tests until green.

### Task 3: Lock The Session Reissue Contract

**Files:**
- Create: `tests/test_hxy_session_link_reissue.py`

1. Test exact operator confirmation before database access.
2. Test HXY-owned database validation and active-founder resolution.
3. Test that only SHA-256 of the grant is inserted.
4. Test bounded TTL, fragment URL, and sanitized CLI failures.
5. Run the focused tests and confirm they fail because the module is absent.

### Task 4: Implement Session Reissue

**Files:**
- Create: `apps/api/hxy_product/session_link_reissue.py`
- Create: `scripts/reissue-hxy-session-link.py`
- Modify: `docs/operations/hxy-founder-bootstrap.md`

1. Implement the locked, founder-scoped grant insertion.
2. Add the exact-confirmation CLI and one-time fragment output.
3. Document expiry, non-destructive behavior, and safe handling.
4. Run focused and full Python tests.

### Task 5: Release And Verify

**Files:**
- Build artifact: `apps/hxy-web/dist/`

1. Run complete TypeScript, web, Python, Playwright, secret, and public-release
   verification.
2. Commit and push the verified branch.
3. Build an immutable release directory and atomically update
   `/root/hxy/releases/current`.
4. Restart API and web services, then verify local, FRP, and strict HTTPS.
5. Issue one ten-minute Founder link and deliver it without storing the raw
   grant in a file or log.
