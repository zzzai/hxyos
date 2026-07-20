# HXYOS Organization Record Frontstage V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build one production-ready vertical slice in which an authorized HXYOS user can capture text or files as an organization record, receive an immediate receipt, see evidence-backed AI understanding in a role-specific Today briefing, inspect the original record, and continue the work in a sourced conversation.

**Architecture:** Reuse `hxy_inbound_envelopes`, `hxy_product_materials`, `hxy_asset_bindings`, `hxy_ai_proposals`, and the durable outbox instead of creating a parallel knowledge or project-management subsystem. Add a public `OrganizationRecord` read projection, a dedicated generic record-understanding worker, and a role briefing projection. Replace the current feature-tab frontend with a responsive shell centered on Today, Conversation, Records, and a universal ask/record composer.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic v2, PostgreSQL/psycopg, existing HXY outbox worker and model router, React 19, TypeScript, Vite, Vitest, Testing Library, Playwright, lucide-react.

---

## Product And Engineering Constraints

- Work only in `/root/hxy`; never read from or write to `/root/htops`.
- Do not modify the Brand Constitution, VI, SI, or approved business knowledge.
- Keep private business material under local data/knowledge paths and out of Git.
- Ordinary users never classify, tag, approve, or review claims during capture.
- Original input is persisted before model execution and remains available if AI fails.
- AI interpretations stay derived and versioned; they never become official knowledge automatically.
- Every brief risk, decision, or progress statement links to an accessible source record and evidence excerpt.
- Today returns no more than three attention items by default.
- Store employees see their own records; store managers see records in their store; founder and headquarters roles see authorized organization records. `system_admin` receives no implicit access to business records.
- Routine project tasks remain in Feishu. HXYOS only projects critical context, decisions, risks, and changes.

### Task 1: Freeze The Public Organization Record Contract

**Files:**
- Create: `apps/api/hxy_product/record_schemas.py`
- Create: `apps/api/hxy_product/record_repository.py`
- Create: `tests/test_hxy_organization_records.py`
- Modify: `apps/api/hxy_product/routes.py`

**Step 1: Write failing schema and repository tests**

Add tests for these externally visible objects:

```python
def test_record_projection_keeps_original_and_interpretation_separate():
    record = public_record(RECORD_ROW)
    assert record["original"]["text"] == "施工群原始记录"
    assert record["interpretation"]["summary"] == "水电图仍缺最终确认"
    assert record["interpretation"]["official_knowledge"] is False


def test_store_employee_query_is_limited_to_own_submission():
    repository.list_records(
        organization_id=ORG_ID,
        assignment_id=EMPLOYEE_ID,
        role="store_employee",
        store_id="store-1",
        limit=20,
    )
    assert "sender_assignment_id = %s::uuid" in normalized_sql


def test_founder_query_is_organization_scoped_without_store_leakage():
    repository.list_records(
        organization_id=ORG_ID,
        assignment_id=FOUNDER_ID,
        role="founder",
        store_id=None,
        limit=20,
    )
    assert params[0] == ORG_ID
    assert "organization_id = %s::uuid" in normalized_sql
```

The contract must include:

```text
OrganizationRecord
  id, source_types, preview, submitted_by, store_id,
  captured_at, occurred_at, processing_status,
  original { text, assets[] },
  interpretation { version, summary, facts[], decisions[], progress[], risks[],
                   missing_information[], confidence, official_knowledge=false } | null
```

Each extracted item uses a common evidence reference:

```text
statement, evidence[] { source_record_id, source_asset_id?, quote, locator? }
```

**Step 2: Run the tests and verify RED**

Run:

```bash
pytest -q tests/test_hxy_organization_records.py
```

Expected: failure because `record_schemas` and `record_repository` do not exist.

**Step 3: Implement the minimal projection and scoped repository**

Implement `RecordRepository.list_records(...)` and `get_record(...)` by joining:

```text
hxy_inbound_envelopes
LEFT JOIN latest hxy_ai_proposals where proposal_type='organization_record_understanding'
LEFT JOIN hxy_asset_bindings
LEFT JOIN hxy_product_materials
```

Use one SQL visibility predicate selected from a fixed role map. Do not interpolate user input into SQL. Map internal states to:

```text
received -> received
queued -> processing
processed -> ready
needs_attention -> needs_attention
rejected -> needs_attention
```

Add `records:create` and `records:read` capabilities to founder, HQ operations, store manager, and store employee. Do not add them to `system_admin`.

**Step 4: Run focused and identity regression tests**

Run:

```bash
pytest -q tests/test_hxy_organization_records.py tests/test_hxy_product_identity.py
```

Expected: all pass.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/record_schemas.py apps/api/hxy_product/record_repository.py apps/api/hxy_product/routes.py tests/test_hxy_organization_records.py
git commit -m "feat: add organization record projection"
```

### Task 2: Add Generic Organization Record Intake

**Files:**
- Create: `apps/api/hxy_product/record_routes.py`
- Modify: `apps/api/hxy_product/channel_repository.py`
- Modify: `apps/api/hxy_product/material_repository.py`
- Modify: `apps/api/hxy_product/outbox_repository.py`
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_organization_records.py`
- Modify: `tests/test_hxy_material_jobs_postgres.py`
- Modify: `tests/test_hxy_outbox_runtime.py`

**Step 1: Write failing route tests for capture and read**

Cover:

```python
def test_record_capture_returns_before_understanding_finishes():
    response = client.post(
        "/api/v1/organization-records",
        json={"client_record_id": CLIENT_ID, "text": "水电图今天确认", "source_asset_ids": []},
        headers=SESSION_HEADERS,
    )
    assert response.status_code == 202
    assert response.json()["record"]["processing_status"] in {"received", "processing"}


def test_capture_does_not_require_a_store_for_founder():
    assert client.post("/api/v1/organization-records", json=PAYLOAD).status_code == 202


def test_record_detail_returns_404_outside_role_scope():
    assert client.get(f"/api/v1/organization-records/{OTHER_RECORD}").status_code == 404
```

Also verify the repository writes:

```text
intent_hint = organization_record
topic = understand.organization_record
aggregate_type = inbound_envelope
```

**Step 2: Run and verify RED**

Run:

```bash
pytest -q tests/test_hxy_organization_records.py
```

Expected: 404 for the missing routes and missing repository method.

**Step 3: Implement capture using the existing envelope ledger**

Add `ChannelRepository.accept_authenticated_record(...)` that:

1. validates the server-resolved assignment and organization;
2. permits founder/HQ records without a store and preserves a store when present;
3. checks all referenced materials belong to the organization and are visible to the submitting assignment;
4. persists `hxy_inbound_envelopes` first with `intent_hint='organization_record'`;
5. binds attachments through `hxy_asset_bindings`;
6. inserts one `understand.organization_record` outbox message;
7. returns the persisted envelope without waiting for a model.

Expose:

```text
POST /api/v1/organization-records
GET  /api/v1/organization-records?limit=50
GET  /api/v1/organization-records/{record_id}
```

Update material-release and outbox-dead-letter handling to cover both understanding topics using an explicit allowlist:

```sql
message.topic IN ('understand.inbound.issue', 'understand.organization_record')
```

Do not use a broad prefix match.

**Step 4: Run focused backend tests**

Run:

```bash
pytest -q \
  tests/test_hxy_organization_records.py \
  tests/test_hxy_channel_intake.py \
  tests/test_hxy_material_jobs_postgres.py \
  tests/test_hxy_outbox_runtime.py
```

Expected: all pass.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/record_routes.py apps/api/hxy_product/channel_repository.py apps/api/hxy_product/material_repository.py apps/api/hxy_product/outbox_repository.py apps/api/hxy_knowledge_api.py tests/test_hxy_organization_records.py tests/test_hxy_material_jobs_postgres.py tests/test_hxy_outbox_runtime.py
git commit -m "feat: accept organization records asynchronously"
```

### Task 3: Understand Records As Facts, Decisions, Progress, Risks, And Evidence

**Files:**
- Create: `apps/api/hxy_product/record_understanding.py`
- Create: `tests/test_hxy_record_understanding.py`
- Modify: `apps/api/hxy_product/channel_repository.py`
- Modify: `apps/api/hxy_knowledge/model_router.py`
- Modify: `scripts/run-hxy-outbox-worker.py`
- Modify: `tests/test_hxy_outbox_runtime.py`

**Step 1: Write failing model-output and persistence tests**

The Pydantic draft must reject unsupported fields, overlong evidence, invalid severity, and confidence outside `[0, 1]`.

```python
def test_understanding_preserves_evidence_and_never_approves_knowledge():
    result = handler(scoped_outbox_payload())
    saved = proposal_repository.saved
    assert saved["proposal_type"] == "organization_record_understanding"
    assert saved["status"] == "proposed"
    assert saved["payload"]["risks"][0]["evidence"][0]["quote"] == "施工方尚未收到最终水电图"
    assert "official_knowledge" not in saved["payload"]
    assert result["status"] == "processed"


def test_invalid_model_json_is_retryable_and_does_not_complete_envelope():
    with pytest.raises(OutboxHandlerError) as error:
        handler(scoped_outbox_payload())
    assert error.value.code == "invalid_record_json"
    assert channel_repository.completed is False
```

**Step 2: Run and verify RED**

Run:

```bash
pytest -q tests/test_hxy_record_understanding.py
```

Expected: import failure because the handler is missing.

**Step 3: Implement the generic understanding handler**

Reuse the bounded attachment adapter behavior from `issue_understanding.py`; extract shared parsing helpers only after tests protect current issue behavior.

The model must return strict JSON with:

```json
{
  "summary": "",
  "record_type": "progress_update",
  "occurred_at": null,
  "facts": [],
  "decisions": [],
  "progress": [],
  "risks": [],
  "missing_information": [],
  "confidence": 0.0
}
```

Rules embedded in the prompt and enforced in validation:

- never infer an approved policy or formal brand position;
- never invent completion percentages, dates, owners, prices, or results;
- every decision, progress item, and risk must include at least one quote and source reference;
- absence of evidence means omission, not a low-confidence claim;
- keep no more than five items in each section;
- interpretation status is always `proposed` and is only a derived view.

Add a `organization_record_understanding` route to `ModelRouter`. Register the handler in `run-hxy-outbox-worker.py` under `understand.organization_record`.

**Step 4: Run worker and existing issue-understanding regressions**

Run:

```bash
pytest -q \
  tests/test_hxy_record_understanding.py \
  tests/test_hxy_issue_understanding.py \
  tests/test_hxy_outbox_runtime.py
```

Expected: all pass.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/record_understanding.py apps/api/hxy_product/channel_repository.py apps/api/hxy_knowledge/model_router.py scripts/run-hxy-outbox-worker.py tests/test_hxy_record_understanding.py tests/test_hxy_outbox_runtime.py
git commit -m "feat: understand organization records with evidence"
```

### Task 4: Build The Evidence-Backed Today Briefing

**Files:**
- Create: `apps/api/hxy_product/briefing_schemas.py`
- Create: `apps/api/hxy_product/briefing_repository.py`
- Create: `apps/api/hxy_product/briefing_routes.py`
- Create: `tests/test_hxy_today_briefing.py`
- Modify: `apps/api/hxy_knowledge_api.py`

**Step 1: Write failing role and evidence tests**

```python
def test_today_returns_at_most_three_items():
    response = client.get("/api/v1/today")
    assert response.status_code == 200
    assert len(response.json()["items"]) <= 3


def test_brief_item_without_evidence_is_omitted():
    assert project_brief_items(INTERPRETATION_WITH_UNSOURCED_RISK) == []


def test_founder_sees_critical_decision_before_recent_progress():
    items = project_brief_items(FOUNDER_RECORDS)
    assert [item["kind"] for item in items[:2]] == ["risk", "decision"]


def test_store_employee_briefing_cannot_include_another_submitter_record():
    response = employee_client.get("/api/v1/today")
    assert OTHER_RECORD_ID not in response.text
```

**Step 2: Run and verify RED**

Run:

```bash
pytest -q tests/test_hxy_today_briefing.py
```

Expected: missing route/module failure.

**Step 3: Implement a deterministic projection, not a second AI call**

Expose:

```text
GET /api/v1/today?limit=3
```

Build items only from already stored, authorized record interpretations. Rank deterministically:

```text
critical/high evidenced risk
unresolved evidenced decision or missing information
material recent progress change
freshness
```

Return:

```text
id, kind, severity, statement, why_it_matters,
source_record_id, evidence[], captured_at,
next_action { type: open_record|ask_about_record, label, prompt? }
```

No item may be generated directly by the language model at request time. No dashboard metric is inferred from text.

**Step 4: Run focused API tests**

Run:

```bash
pytest -q tests/test_hxy_today_briefing.py tests/test_hxy_organization_records.py
```

Expected: all pass.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/briefing_schemas.py apps/api/hxy_product/briefing_repository.py apps/api/hxy_product/briefing_routes.py apps/api/hxy_knowledge_api.py tests/test_hxy_today_briefing.py
git commit -m "feat: add role-aware today briefing"
```

### Task 5: Add Frontend API Clients And Test Fixtures

**Files:**
- Create: `apps/hxy-web/src/api/records.ts`
- Create: `apps/hxy-web/src/api/records.test.ts`
- Create: `apps/hxy-web/src/api/today.ts`
- Create: `apps/hxy-web/src/api/today.test.ts`
- Modify: `apps/hxy-web/src/api/materials.ts`

**Step 1: Write failing client tests**

Cover credentials, URL encoding, JSON body shape, source upload followed by record capture, and error status preservation.

```typescript
it("captures a file as one organization record", async () => {
  const material = await materialClient.uploadMaterial(file, "", uploadId);
  await recordClient.createRecord({
    clientRecordId: recordId,
    text: "装修群记录",
    sourceAssetIds: [material.material.id],
  });
  expect(fetch).toHaveBeenLastCalledWith(
    "/api/v1/organization-records",
    expect.objectContaining({ method: "POST", credentials: "include" }),
  );
});
```

**Step 2: Run and verify RED**

Run:

```bash
npm test -- --run src/api/records.test.ts src/api/today.test.ts
```

Expected: missing modules.

**Step 3: Implement typed clients**

Implement:

```text
recordClient.listRecords
recordClient.getRecord
recordClient.createRecord
todayClient.getToday
```

Keep upload and record capture as two explicit API calls so an uploaded artifact survives record-understanding failure. Do not add a dependency.

**Step 4: Run all frontend client tests**

Run:

```bash
npm test -- --run src/api/client.test.ts src/api/records.test.ts src/api/today.test.ts
```

Expected: all pass.

**Step 5: Commit**

```bash
git add apps/hxy-web/src/api/records.ts apps/hxy-web/src/api/records.test.ts apps/hxy-web/src/api/today.ts apps/hxy-web/src/api/today.test.ts apps/hxy-web/src/api/materials.ts
git commit -m "feat: add organization record web clients"
```

### Task 6: Replace The Feature Dashboard With The Minimal Frontstage Shell

**Files:**
- Create: `apps/hxy-web/src/features/shell/ProductShell.tsx`
- Create: `apps/hxy-web/src/features/shell/Navigation.tsx`
- Create: `apps/hxy-web/src/features/today/TodayView.tsx`
- Create: `apps/hxy-web/src/features/conversation/ConversationView.tsx`
- Create: `apps/hxy-web/src/features/records/RecordsView.tsx`
- Create: `apps/hxy-web/src/features/records/RecordDetail.tsx`
- Create: `apps/hxy-web/src/features/composer/UniversalComposer.tsx`
- Create: `apps/hxy-web/src/features/shell/ProductShell.test.tsx`
- Modify: `apps/hxy-web/src/App.tsx`
- Modify: `apps/hxy-web/src/App.test.tsx`
- Modify: `apps/hxy-web/src/styles/tokens.css`
- Modify: `apps/hxy-web/src/styles/shell.css`

**Step 1: Write failing interaction tests**

Test behavior rather than class names:

```typescript
it("opens Today with no more than three attention items", async () => {});
it("captures text without asking for a category or tag", async () => {});
it("uploads a file and shows its immediate receipt", async () => {});
it("opens evidence-backed record detail from a briefing row", async () => {});
it("starts a sourced contextual question from a record", async () => {});
it("shows employee-safe content for the employee role", async () => {});
it("all rendered navigation and composer buttons perform an action", async () => {});
```

**Step 2: Run and verify RED**

Run:

```bash
npm test -- --run src/features/shell/ProductShell.test.tsx
```

Expected: missing component failure.

**Step 3: Implement the shell and four user surfaces**

Desktop rail:

```text
+ New record

Today
Organization records

Recent conversations
--------------------
Identity and scope
```

Mobile navigation:

```text
Today | Conversation | Records | Me
```

Design constraints:

- main work area is centered and calm, with a reading width near 760px;
- no nested cards, large hero, feature grid, gradient, decorative orb, or admin vocabulary;
- use borders and whitespace for hierarchy; card radius is at most 8px;
- display at most three Today items before a deliberate “view records” action;
- one-line briefing rows expand into evidence or open record detail;
- composer placeholder is `问问题，或记录刚刚发生的事`;
- use a two-option segmented mode control `Ask | Record` because the same text has different persistence semantics;
- paperclip opens file selection; send submits; New record switches to Record and focuses the composer;
- no inert controls: every visible button must work, be disabled with a reason, or be omitted;
- keep onboarding/profile administration behind `Me`, not in the working surface;
- retain existing AccessGate and SessionProvider behavior.

On desktop, record detail may occupy a secondary pane. On mobile, it becomes a full-screen surface with a back action.

**Step 4: Run component tests and build**

Run:

```bash
npm test -- --run
npm run build
```

Expected: all Vitest tests pass; TypeScript and Vite build succeed.

**Step 5: Commit**

```bash
git add apps/hxy-web/src/App.tsx apps/hxy-web/src/App.test.tsx apps/hxy-web/src/features apps/hxy-web/src/styles/tokens.css apps/hxy-web/src/styles/shell.css
git commit -m "feat: redesign hxyos around organization records"
```

### Task 7: Verify Desktop, Mobile, Permissions, And The Renovation Vertical Slice

**Files:**
- Rewrite: `apps/hxy-web/tests/product-shell.spec.ts`
- Create: `tests/test_hxy_record_frontstage_release.py`
- Modify: `docs/runbooks/HXYOS-PRODUCT-RELEASE.md` if the existing runbook requires new endpoints

**Step 1: Write failing Playwright acceptance tests**

Mock or seed these real V1 cases:

```text
1. Founder uploads a renovation chat export and sees an immediate receipt.
2. After background understanding, Today shows an evidenced missing water/electrical confirmation.
3. Selecting the item opens the source record and original attachment.
4. “Ask about this record” opens Conversation with record context.
5. Purchasing and online-operations records appear in the same Records surface.
6. A store employee cannot retrieve a founder-only record.
7. Mobile 390x844 has no overlap, hidden action, or horizontal overflow.
8. Desktop 1440x900 keeps the composer and primary content centered.
```

**Step 2: Run and verify RED**

Run:

```bash
npm run test:e2e -- product-shell.spec.ts
```

Expected: old shell assertions fail.

**Step 3: Update fixtures and release contract**

Add a static release test that asserts the API includes record and Today routers, the worker registers `understand.organization_record`, and the built frontend does not contain ordinary-user labels such as `claim`, `review queue`, `模型轨迹`, or `审核中心`.

**Step 4: Run full verification**

From repository root:

```bash
pytest -q \
  tests/test_hxy_organization_records.py \
  tests/test_hxy_record_understanding.py \
  tests/test_hxy_today_briefing.py \
  tests/test_hxy_operating_routes.py \
  tests/test_hxy_outbox_runtime.py \
  tests/test_hxy_record_frontstage_release.py
```

From `apps/hxy-web`:

```bash
npm test -- --run
npm run build
npm run test:e2e -- product-shell.spec.ts
```

Expected: all tests and build pass.

**Step 5: Run local visual verification**

Start the Vite server on an unused port and inspect with Playwright at `1440x900`, `1024x768`, and `390x844`. Verify:

- all buttons accept pointer input;
- no overlay blocks the page;
- no text or navigation overlap;
- no horizontal overflow;
- source detail is reachable;
- capture success and failure states are visible;
- the interface remains useful with zero Today items and with three long Chinese items.

**Step 6: Commit**

```bash
git add apps/hxy-web/tests/product-shell.spec.ts tests/test_hxy_record_frontstage_release.py docs/runbooks/HXYOS-PRODUCT-RELEASE.md
git commit -m "test: verify organization record frontstage"
```

### Task 8: Release Without Replacing The Known-Good Deployment Prematurely

**Files:**
- Modify only the existing HXY deployment manifests or scripts found during release preflight.
- Do not modify any `htops` service, path, database, or Nginx configuration.

**Step 1: Run release preflight**

Run the repository’s existing HXY deployment and secret checks. Confirm:

```text
HXY_DATABASE_URL points to the HXY database
HXY_ROOT_DIR points to /root/hxy
material storage remains local/private
worker service includes the new topic handler
frontend and API are built from the same commit
```

**Step 2: Apply any required HXY-only migration/index**

Only if query plans show it is needed, add the next numbered migration for:

```sql
CREATE INDEX ... ON hxy_inbound_envelopes (organization_id, received_at DESC);
```

Do not create a new source ledger or duplicate material table.

**Step 3: Deploy to the HXY service and run smoke checks**

Verify authenticated production responses for:

```text
GET  /api/v1/me
GET  /api/v1/today
GET  /api/v1/organization-records
POST /api/v1/organization-records
GET  /api/v1/conversations
```

Then verify `https://hxyos.hexiaoyue.com/` at desktop and mobile dimensions.

**Step 4: Record release evidence and commit only public-safe artifacts**

Do not commit uploaded records, screenshots containing private material, API keys, cookies, database URLs, or model traces containing business data.

