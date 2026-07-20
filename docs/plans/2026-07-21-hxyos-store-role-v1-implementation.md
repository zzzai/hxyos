# HXYOS Store Role V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Deliver a mobile-first HXYOS V1 by 2026-08-20 in which technicians and store managers can ask questions, submit text/voice/files, learn, and capture service feedback without depending on the third-party transaction API.

**Architecture:** Extend the existing FastAPI modular monolith, durable PostgreSQL outbox, organization-record projection, answer pipeline, and React PWA. Keep original intake durable and asynchronous; route answers before generation; represent pre-API services and customer links with provisional, reconcilable domain records.

**Tech Stack:** Python, FastAPI, PostgreSQL, React, TypeScript, Vite, Vitest, Playwright, browser MediaRecorder, existing HXY model router, pgvector, S3-compatible asset storage.

---

## Delivery Rules

- Use test-driven development for every behavior change.
- Keep HXY data isolated from `/root/htops`.
- Do not commit private knowledge, customer data, secrets, or generated local artifacts.
- Do not implement an invented third-party API. Define connector ports and test fixtures only.
- Commit each completed task separately.
- Ordinary users never choose ask versus record or see governance internals.

### Task 1: Freeze The Store-Role Release Contract

**Files:**
- Create: `docs/plans/2026-07-21-hxyos-store-role-v1-design.md`
- Create: `docs/plans/2026-07-21-hxyos-store-role-v1-implementation.md`
- Modify: `docs/project-brain/roadmap/01-stage-roadmap.md`
- Test: `tests/test_hxyos_v1_architecture_docs.py`

**Steps:**

1. Add a failing documentation-contract test requiring the store-role V1 design, deadline, unified composer, answer routes, provisional service context, and zero unauthorized sensitive-data exposure.
2. Run `pytest -q tests/test_hxyos_v1_architecture_docs.py` and confirm the new assertions fail.
3. Add the approved design and implementation references to the stage roadmap.
4. Run the focused test and confirm it passes.
5. Commit with `docs: freeze HXYOS store role V1`.

### Task 2: Harden Frontend API Response Validation

**Files:**
- Modify: `apps/hxy-web/src/api/records.test.ts`
- Modify: `apps/hxy-web/src/api/records.ts`
- Modify: `apps/hxy-web/src/api/today.test.ts`
- Modify: `apps/hxy-web/src/api/today.ts`

**Steps:**

1. Add failing tests for `{record:{}}`, `{records:[null]}`, `{items:[{}]}`, malformed nested assets, and malformed next actions.
2. Run `npm test -- src/api/records.test.ts src/api/today.test.ts` from `apps/hxy-web` and confirm contract failures.
3. Add complete structural type guards for records, interpretations, assets, brief items, and next actions.
4. Normalize FastAPI string and array-form validation details without exposing server internals.
5. Run the focused tests and commit with `fix: validate organization record responses`.

### Task 3: Replace Ask/Record Modes With One Composer

**Files:**
- Modify: `apps/hxy-web/src/features/composer/UniversalComposer.tsx`
- Modify: `apps/hxy-web/src/features/shell/ProductShell.tsx`
- Modify: `apps/hxy-web/src/features/shell/ProductShell.test.tsx`
- Modify: `apps/hxy-web/src/App.test.tsx`
- Modify: `apps/hxy-web/src/styles/shell.css`

**Steps:**

1. Rewrite tests to assert there is no ask/record switch and every text submission receives one immediate receipt.
2. Add tests proving files can accompany text and a retry preserves the same client submission ID.
3. Run focused shell tests and confirm they fail for the obsolete mode switch.
4. Replace `ComposerMode` with a single submission contract.
5. Persist through the organization intake endpoint first; render `已收到，正在处理` before derived handling completes.
6. Keep conversation follow-up contextual without exposing routing internals.
7. Run focused tests and commit with `feat: unify HXYOS intake composer`.

### Task 4: Add Browser Voice Capture

**Files:**
- Create: `apps/hxy-web/src/features/composer/useVoiceCapture.ts`
- Create: `apps/hxy-web/src/features/composer/useVoiceCapture.test.ts`
- Modify: `apps/hxy-web/src/features/composer/UniversalComposer.tsx`
- Modify: `apps/hxy-web/src/features/shell/ProductShell.test.tsx`
- Modify: `apps/hxy-web/src/styles/shell.css`

**Steps:**

1. Add failing tests for unsupported browsers, denied permission, recording start, recording stop, upload, cancellation, and retry.
2. Run the focused tests and verify expected failures.
3. Implement MediaRecorder capability detection and explicit lifecycle cleanup.
4. Expose a microphone button with recording duration, stop, cancel, and upload states.
5. Upload the audio through the existing protected material client and submit the resulting asset ID through unified intake.
6. Run focused tests and commit with `feat: add voice intake`.

### Task 5: Add Unified Server-Side Intent And Answer Routing

**Files:**
- Create: `apps/api/hxy_product/intake_schemas.py`
- Create: `apps/api/hxy_product/intake_routes.py`
- Create: `apps/api/hxy_product/intake_router.py`
- Modify: `apps/api/hxy_product/routes.py`
- Modify: `apps/api/hxy_product/conversation_routes.py`
- Modify: `apps/api/hxy_knowledge/answer_pipeline.py`
- Test: `tests/test_hxy_unified_intake.py`
- Test: `tests/test_hxy_answer_authority.py`

**Steps:**

1. Add failing tests for durable original persistence before routing.
2. Add failing route tests for `general`, `hxy_official`, `mixed`, `service_scenario`, and `high_risk`.
3. Add tests proving HXY-specific unknowns are not answered as approved facts and high-risk health prompts cannot produce diagnoses or guarantees.
4. Implement a deterministic policy shell around model-assisted classification.
5. Route general questions to the model and governed HXY questions through approved answer assets with citations.
6. Preserve asynchronous record understanding independently of answer generation.
7. Run focused backend tests and commit with `feat: route unified HXYOS intake`.

### Task 6: Add Technician Learning And Scenario Practice

**Files:**
- Create: `apps/api/hxy_product/learning_schemas.py`
- Create: `apps/api/hxy_product/learning_routes.py`
- Create: `apps/api/hxy_product/learning_service.py`
- Modify: `apps/api/hxy_product/training_repository.py`
- Create: `apps/hxy-web/src/api/learning.ts`
- Create: `apps/hxy-web/src/features/learning/LearningView.tsx`
- Modify: `apps/hxy-web/src/features/shell/Navigation.tsx`
- Modify: `apps/hxy-web/src/features/shell/ProductShell.tsx`
- Test: `tests/test_hxy_role_learning.py`
- Test: `apps/hxy-web/src/features/learning/LearningView.test.tsx`

**Steps:**

1. Add failing tests for assignment-scoped learning, one next action, scenario attempts, and private capability progress.
2. Add tests proving AI cannot certify physical technique and ordinary users cannot see another employee's progress.
3. Implement the minimum learning and scenario contracts using governed role material.
4. Add a restrained Learn view with one next action, practice entry, and progress disclosure.
5. Run focused backend and frontend tests and commit with `feat: add technician learning loop`.

### Task 7: Add Provisional Service Context And Customer Identity

**Files:**
- Create: `data/migrations/024_hxy_service_context.sql`
- Create: `apps/api/hxy_product/service_schemas.py`
- Create: `apps/api/hxy_product/service_repository.py`
- Create: `apps/api/hxy_product/service_routes.py`
- Modify: `apps/api/hxy_product/routes.py`
- Test: `tests/test_hxy_service_context.py`

**Steps:**

1. Add failing schema and repository tests for organization/store scope, provisional links, idempotency, immutable original identity hints, and reconciliation history.
2. Add tests proving phone suffixes are ambiguous hints and plain phone numbers do not enter model payloads or logs.
3. Add the migration and repository using internal UUIDs and source-specific external identity mappings.
4. Add minimal endpoints to create, list recent authorized contexts, attach feedback, and reconcile a context later.
5. Run focused tests and commit with `feat: add provisional service context`.

### Task 8: Connect Technician Feedback And Manager Closing Review

**Files:**
- Create: `apps/hxy-web/src/api/services.ts`
- Create: `apps/hxy-web/src/features/service/ServiceFeedbackPrompt.tsx`
- Create: `apps/hxy-web/src/features/service/ServiceFeedbackPrompt.test.tsx`
- Modify: `apps/hxy-web/src/features/today/TodayView.tsx`
- Modify: `apps/hxy-web/src/features/shell/ProductShell.tsx`
- Modify: `apps/api/hxy_product/briefing_repository.py`
- Test: `tests/test_hxy_today_briefing.py`

**Steps:**

1. Add failing tests for recent-service selection, masked identity display, voice feedback attachment, and assignment boundaries.
2. Add failing tests for a manager closing-review prompt and no more than three Today items.
3. Implement the technician prompt and manager projection without a duplicate task board.
4. Record feedback outcome and closing review as organization records linked to service or store context.
5. Run focused tests and commit with `feat: connect store role operating loops`.

### Task 9: Complete Release Acceptance And Production Pilot Instrumentation

**Files:**
- Modify: `apps/hxy-web/tests/product-shell.spec.ts`
- Create: `apps/hxy-web/tests/store-role-v1.spec.ts`
- Modify: `apps/hxy-web/playwright.config.ts`
- Modify: `tests/test_hxy_product_smoke.py`
- Create: `docs/plans/2026-08-13-hxyos-store-role-pilot.md`

**Steps:**

1. Add Playwright journeys for 360x800, 390x844, 1280x800, and 1440x900.
2. Cover login, text intake, file intake, voice states, general question, HXY question, learning, service feedback, manager review, retry, and logout.
3. Assert every visible button is actionable, no horizontal scroll exists, and primary controls do not overlap.
4. Add smoke checks for API routes, worker registration, data isolation, and forbidden ordinary-user labels.
5. Add privacy-safe events for intake success, feedback duration, completion, useful brief feedback, and learning completion.
6. Run backend tests, frontend tests, build, Playwright, static release checks, and `git diff --check`.
7. Deploy only HXY-owned services and perform role-based production smoke tests at `https://hxyos.hexiaoyue.com/`.
8. Commit with `test: verify HXYOS store role V1`.

## Final Verification

Run:

```bash
pytest -q
cd apps/hxy-web && npm test -- --run
cd apps/hxy-web && npm run build
cd apps/hxy-web && npx playwright test
git diff --check
```

Record real-role pilot evidence separately from automated test output. The
release is not complete until the seven-day independent-use criterion has been
observed or explicitly marked as pending field validation.
