# HXYOS Store Issue Vertical Slice V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the direct-operated pilot store Feishu/PWA issue loop on a unified HXY data catalog so a verified user can report a real operating problem, receive asynchronous AI-assisted classification, complete corrective work with evidence, pass governed acceptance, and produce auditable metrics without blocking future mixed operating modes.

**Architecture:** First establish organization-level `SourceAsset`, structured-data snapshots, store operating relationships, governance profiles, metric definitions, and asset lineage. Feishu and PWA then write an immutable `InboundEnvelope` and transactional `OutboxMessage` before any model call. A PostgreSQL worker creates an `AIProposal`; deterministic policy converts accepted proposals into governed operating records. Feishu is the default collaboration channel, while HXYOS PWA remains a first-class conversation, upload, task, evidence, and training surface.

**Tech Stack:** Python 3, FastAPI, Pydantic 2, psycopg 3, PostgreSQL 16, pgvector only for governed knowledge, httpx, React 19, TypeScript, Vite, Vitest, Playwright, systemd, Nginx.

---

## Delivery Rules

1. Work only in `/root/hxy/.worktrees/hxyos-authority-answer-v1`.
2. Do not read from or write to htops business databases or `/root/htops` business data.
3. Use TDD for every behavior change: failing test, minimal implementation, passing test, commit.
4. Do not call an LLM inside the transaction that stores channel input.
5. Do not let AI act as a state-transition actor or write `MetricFact` values.
6. Do not ingest all Feishu communication. Only designated groups, `@HXYOS`, explicit actions, and authorized workflows enter HXYOS.
7. Keep ordinary user surfaces limited to `对话 / 上传 / 今日 / 我的`; admin and dead-letter operations use separate routes.
8. Use existing PostgreSQL lease/retry semantics from `material_repository.py`; do not add Celery, Redis, Temporal, or another queue in V1.
9. Use Chinese package mirrors for any dependency installation.
10. Commit after every task. Never combine schema, worker, Feishu, UI, and deployment into one commit.
11. V1 operates only the 直营首店 path. Preserve `StoreOperatingRelationship` and `GovernanceProfile` boundaries, but do not build 加盟管理功能、招商、区域代理 or mixed-mode settlement.
12. Evolve `hxy_product_materials` into the V1 `SourceAsset` implementation; do not create a second competing upload table.
13. Treat external POS/member/payment/groupbuy systems as the initial system of record for transactions. HXYOS stores immutable snapshots, normalized facts, and lineage only.

## Phase A: Freeze The Business Facts

### Task 1: Add the unified data catalog and operating relationship migration

**Files:**
- Create: `data/migrations/020_hxy_data_catalog.sql`
- Create: `tests/test_hxy_data_catalog_migration.py`

**Step 1: Write the failing migration contract test**

The test must require the organization-level source asset evolution and the new catalog objects:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "020_hxy_data_catalog.sql"


def test_data_catalog_separates_assets_datasets_facts_metrics_and_lineage():
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())
    for table in (
        "hxy_legal_entities",
        "hxy_operating_mode_catalog",
        "hxy_governance_profiles",
        "hxy_store_operating_relationships",
        "hxy_data_sources",
        "hxy_data_connectors",
        "hxy_dataset_snapshots",
        "hxy_business_facts",
        "hxy_metric_definitions",
        "hxy_asset_bindings",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in normalized
    assert "ALTER TABLE hxy_product_materials" in normalized
    assert "ADD COLUMN IF NOT EXISTS organization_id" in normalized
    assert "ADD COLUMN IF NOT EXISTS store_id" in normalized
    assert "CREATE TABLE IF NOT EXISTS hxy_source_assets" not in normalized
    assert "htops" not in sql.lower()


def test_catalog_keeps_relationships_and_snapshots_versioned():
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())
    assert "relationship_version" in normalized
    assert "profile_version" in normalized
    assert "schema_version" in normalized
    assert "normalization_version" in normalized
    assert "metric_key" in normalized
    assert "formula" in normalized
    assert "configuration_ref" in normalized
    assert "api_key" not in sql.lower()
    assert "DROP TABLE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()
```

**Step 2: Run the test to verify it fails**

```bash
.venv/bin/pytest tests/test_hxy_data_catalog_migration.py -q
```

Expected: FAIL because `020_hxy_data_catalog.sql` does not exist.

**Step 3: Write the migration**

Evolve `hxy_product_materials` into the V1 physical implementation of `SourceAsset` by adding and backfilling:

```text
organization_id
store_id
asset_kind
visibility_scope
retention_policy
scan_status
```

Derive organization and store from the existing uploader assignment. Preserve `assignment_id` for compatibility; treat it as `uploaded_by_assignment_id` in domain code. Do not create a second upload table and do not delete existing material history.

Create:

```text
hxy_legal_entities
  organization-scoped owner/operator identity; no payment credentials

hxy_operating_mode_catalog
  versioned mode codes; direct_operated is the only V1 active mode

hxy_governance_profiles
  decision rights, approval policy refs, data access policy,
  required metric definitions, audit policy, effective period

hxy_store_operating_relationships
  store, owner entity, operator entity, mode code, relationship version,
  governance profile, agreement SourceAsset, effective period

hxy_data_sources
  source type, name, system-of-record flag, data classification, owner

hxy_data_connectors
  api|webhook|scheduled_sync|file_import, configuration_ref, cursor, status;
  never store provider secrets in configuration JSON

hxy_dataset_snapshots
  immutable import/sync version, source, connector, period, hash,
  schema version, record count, object key and ingestion status

hxy_business_facts
  source snapshot, source record key, fact type, dimensions, measures,
  occurred_at and normalization version

hxy_metric_definitions
  governed metric key/version, allow-listed formula DSL or tested calculation_ref,
  required fact types and effective period; arbitrary SQL/code execution forbidden

hxy_asset_bindings
  generic source/target/relation lineage with organization scope
```

Use append-only guards for dataset snapshots, business facts, relationship history, metric definitions after publication, and asset bindings. Use `btree_gist` plus an exclusion constraint on `(organization_id, store_id, tstzrange(effective_from, effective_to))` for active relationships so effective periods cannot overlap; a normal unique index is insufficient.

Do not seed fictional franchise contracts, legal entities, stores, orders, members, or financial facts. Store bootstrap data is a separate authorized command.

**Step 4: Run the migration tests**

```bash
.venv/bin/pytest tests/test_hxy_data_catalog_migration.py tests/test_hxy_product_materials.py tests/test_hxy_product_identity.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add data/migrations/020_hxy_data_catalog.sql tests/test_hxy_data_catalog_migration.py
git commit -m "feat: add HXY unified data catalog"
```

### Task 2: Add the V1 operating schema migration

**Files:**
- Create: `data/migrations/021_hxy_operating_loop.sql`
- Create: `tests/test_hxy_operating_loop_migration.py`

**Step 1: Write the failing migration contract test**

The test must assert the presence of these tables:

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "data" / "migrations" / "021_hxy_operating_loop.sql"


def test_operating_loop_migration_defines_channel_ai_work_and_evidence_objects():
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())
    for table in (
        "hxy_channel_identity_bindings",
        "hxy_inbound_envelopes",
        "hxy_ai_proposals",
        "hxy_outbox_messages",
        "hxy_outbox_attempts",
        "hxy_operating_events",
        "hxy_workflow_instances",
        "hxy_operating_evidence",
        "hxy_state_transitions",
        "hxy_metric_facts",
    ):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in normalized
    assert "organization_id UUID NOT NULL" in normalized
    assert "UNIQUE (organization_id, channel, idempotency_key)" in normalized
    assert "status IN ('pending', 'leased', 'retryable_failed', 'succeeded', 'dead_letter')" in normalized
    assert "actor_type IN ('user', 'policy', 'system')" in normalized
    assert "actor_type" not in normalized.split("CREATE TABLE IF NOT EXISTS hxy_ai_proposals", 1)[0]
    assert "htops" not in sql.lower()


def test_operating_loop_migration_extends_tasks_without_destroying_existing_history():
    sql = MIGRATION.read_text(encoding="utf-8")
    normalized = " ".join(sql.split())
    assert "ALTER TABLE hxy_product_tasks ADD COLUMN IF NOT EXISTS operating_event_id" in normalized
    assert "ALTER TABLE hxy_product_tasks ADD COLUMN IF NOT EXISTS workflow_instance_id" in normalized
    assert "ALTER TABLE hxy_product_tasks ADD COLUMN IF NOT EXISTS submitted_at" in normalized
    assert "ALTER TABLE hxy_product_tasks ADD COLUMN IF NOT EXISTS accepted_at" in normalized
    assert "DROP TABLE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()
```

**Step 2: Run the test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_hxy_operating_loop_migration.py -q
```

Expected: FAIL because migration `021_hxy_operating_loop.sql` does not exist.

**Step 3: Write the migration**

Implement the exact contracts from:

- `docs/project-brain/contracts/hxyos-core-data-contract-v1.md`
- `docs/plans/2026-07-18-store-issue-vertical-slice-design.md`

Required database constraints:

```text
hxy_channel_identity_bindings
  unique organization/channel/channel_tenant_id/channel_user_id
  assignment must belong to the same organization
  status active|revoked

hxy_inbound_envelopes
  channel feishu|pwa|admin|api
  status received|queued|processed|needs_attention|rejected
  unique organization/channel/idempotency_key
  raw_payload JSONB, raw_text TEXT, visibility_scope JSONB

hxy_ai_proposals
  status proposed|auto_accepted|accepted|rejected|superseded
  risk low|medium|high|critical
  confidence NUMERIC constrained to 0..1
  source envelope foreign key scoped by organization

hxy_outbox_messages / hxy_outbox_attempts
  lease owner, lease expiry, attempts, retry time, dead letter
  unique organization/topic/idempotency_key
  append-only attempts

hxy_operating_events
  severity low|medium|high|critical
  status open|active|resolved|closed|cancelled
  source envelope and reporter assignment scoped by organization/store
  store operating relationship and governance profile snapshots are required

hxy_workflow_instances
  pending|running|waiting|completed|cancelled|failed
  one active workflow type/version per operating event

hxy_product_tasks extensions
  operating_event_id, workflow_instance_id, task_type
  submitted_at, accepted_at, acceptance_assignment_id
  expand statuses to open|assigned|in_progress|submitted|accepted|rework|cancelled

hxy_operating_evidence
  immutable evidence with supersedes_evidence_id and SourceAsset reference
  evidence meaning is separate from file storage metadata

hxy_state_transitions
  append-only, AI forbidden as actor by enum

hxy_metric_facts
  MetricDefinition reference, derived transition/snapshot IDs,
  calculation version, no overwrite
```

Add append-only triggers for `hxy_outbox_attempts`, `hxy_operating_evidence`, `hxy_state_transitions`, and `hxy_metric_facts`, following the trigger pattern in `015_hxy_product_tasks.sql`.

**Step 4: Run the migration tests**

Run:

```bash
.venv/bin/pytest tests/test_hxy_operating_loop_migration.py tests/test_hxy_product_tasks.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add data/migrations/021_hxy_operating_loop.sql tests/test_hxy_operating_loop_migration.py
git commit -m "feat: add HXY operating loop schema"
```

### Task 3: Implement deterministic risk and auto-advance policy

**Files:**
- Create: `apps/api/hxy_product/operating_policy.py`
- Create: `tests/test_hxy_operating_policy.py`

**Step 1: Write failing policy tests**

Cover at least:

```python
from apps.api.hxy_product.operating_policy import evaluate_issue_proposal


def test_low_risk_high_confidence_issue_auto_advances():
    decision = evaluate_issue_proposal(
        proposal={
            "event_type": "facility_defect",
            "confidence": 0.92,
            "risk_flags": [],
            "location": "前台",
            "acceptance_criteria": "更换后灯光稳定",
            "suggested_owner_assignment_id": "manager-id",
        },
        published_event_types={"facility_defect"},
        assignment_is_active=True,
    )
    assert decision.action == "auto_accept"
    assert decision.severity == "low"


def test_safety_or_injury_never_auto_advances():
    decision = evaluate_issue_proposal(
        proposal={
            "event_type": "safety",
            "confidence": 0.99,
            "risk_flags": ["person_injury"],
            "location": "施工区",
            "acceptance_criteria": "完成安全处理",
            "suggested_owner_assignment_id": "manager-id",
        },
        published_event_types={"safety"},
        assignment_is_active=True,
    )
    assert decision.action == "escalate"
    assert decision.severity == "critical"


def test_only_blocking_missing_fields_are_requested():
    decision = evaluate_issue_proposal(
        proposal={
            "event_type": "facility_defect",
            "confidence": 0.81,
            "risk_flags": [],
            "location": "",
            "acceptance_criteria": "",
            "suggested_owner_assignment_id": None,
        },
        published_event_types={"facility_defect"},
        assignment_is_active=True,
    )
    assert decision.action == "request_missing"
    assert decision.missing_fields == (
        "location",
        "acceptance_criteria",
        "owner_assignment_id",
    )
```

**Step 2: Verify failure**

Run:

```bash
.venv/bin/pytest tests/test_hxy_operating_policy.py -q
```

Expected: FAIL because `operating_policy.py` does not exist.

**Step 3: Implement the policy as pure code**

Use a frozen dataclass:

```python
@dataclass(frozen=True)
class PolicyDecision:
    action: Literal["auto_accept", "request_missing", "require_confirmation", "escalate"]
    severity: Literal["low", "medium", "high", "critical"]
    missing_fields: tuple[str, ...]
    policy_version: str = "issue-intake.v1"
```

Policy ordering must be deterministic:

```text
1. safety/injury/permit/major_budget/major_complaint => escalate
2. inactive or unmapped assignment => require_confirmation
3. blocking fields missing => request_missing
4. unpublished type or confidence < 0.75 => require_confirmation
5. risk-free and confidence >= 0.85 => auto_accept
6. otherwise => require_confirmation
```

Do not call a model or database from this module.

**Step 4: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_operating_policy.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/operating_policy.py tests/test_hxy_operating_policy.py
git commit -m "feat: add deterministic operating risk policy"
```

## Phase B: Reliable Intake And AI Understanding

### Task 4: Add atomic channel intake and identity bindings

**Files:**
- Create: `apps/api/hxy_product/channel_schemas.py`
- Create: `apps/api/hxy_product/channel_repository.py`
- Create: `tests/test_hxy_channel_intake.py`

**Step 1: Write failing repository tests**

Test that one transaction:

1. Resolves an active `ChannelIdentityBinding`.
2. Inserts one `InboundEnvelope`.
3. Inserts one `OutboxMessage` with topic `understand.inbound.issue`.
4. Returns the existing envelope for an identical idempotency key.
5. Does not enqueue work when identity is unmapped; it records a restricted `needs_attention` envelope.

The primary repository method must be:

```python
def accept_inbound(self, payload: dict[str, Any]) -> dict[str, Any]:
    """Persist raw input and enqueue understanding atomically."""
```

Required payload fields:

```python
{
    "organization_id": "...",
    "channel": "feishu",
    "channel_tenant_id": "tenant-key",
    "channel_message_id": "om_xxx",
    "channel_thread_id": "oc_xxx",
    "channel_user_id": "ou_xxx",
    "idempotency_key": "feishu:event-id",
    "raw_text": "前台灯闪烁",
    "raw_payload": {...},
    "source_asset_ids": [...],
}
```

**Step 2: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_channel_intake.py -q
```

Expected: FAIL because the channel repository does not exist.

**Step 3: Implement Pydantic schemas and repository**

Schemas must use `extra="forbid"`, bounded strings, and explicit channel literals. Never accept `organization_id`, `assignment_id`, or `store_id` from an ordinary browser body when they can be derived from an authenticated assignment.

Repository SQL order for mapped identities:

```text
SELECT binding + active assignment FOR SHARE
SELECT current StoreOperatingRelationship + GovernanceProfile FOR SHARE
authorize linked SourceAssets in organization/store/visibility scope
SELECT existing envelope by idempotency key
INSERT hxy_inbound_envelopes
INSERT hxy_asset_bindings for envelope/source assets
INSERT hxy_outbox_messages
UPDATE envelope status = queued
COMMIT
```

For unmapped Feishu users, store only minimum callback metadata and sanitized text under `visibility_scope={"system_admin": true}`; do not create an OperatingEvent.

**Step 4: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_channel_intake.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/channel_schemas.py apps/api/hxy_product/channel_repository.py tests/test_hxy_channel_intake.py
git commit -m "feat: add atomic HXY channel intake"
```

### Task 5: Extract a generic PostgreSQL outbox runtime

**Files:**
- Create: `apps/api/hxy_product/outbox_repository.py`
- Create: `apps/api/hxy_product/outbox_worker.py`
- Create: `tests/test_hxy_outbox_runtime.py`
- Create: `scripts/run-hxy-outbox-worker.py`

**Step 1: Write failing queue tests**

Mirror the proven tests in `tests/test_hxy_material_intake_jobs.py` and require:

```text
claim_next uses FOR UPDATE SKIP LOCKED
claim opens an attempt record
only lease owner can complete/fail
retry delay is exponential and capped at 3600 seconds
stale leases become retryable_failed or dead_letter
dead-letter history is retained
same topic/idempotency key cannot be processed twice
```

Worker handler interface:

```python
OutboxHandler = Callable[[dict[str, Any]], dict[str, Any]]


def process_one_outbox_message(
    repository: OutboxRepository,
    handlers: Mapping[str, OutboxHandler],
    *,
    worker_id: str,
    lease_seconds: int,
    base_retry_seconds: int,
) -> dict[str, str]:
    ...
```

**Step 2: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_outbox_runtime.py -q
```

Expected: FAIL because outbox modules do not exist.

**Step 3: Implement by extracting semantics, not copying brand data**

Reuse the algorithm from:

- `apps/api/hxy_product/material_repository.py:349`
- `apps/api/hxy_product/material_worker.py:120`

The generic worker knows nothing about materials, stores, Feishu, or models. Topic handlers own business behavior.

CLI requirements:

```bash
scripts/run-hxy-outbox-worker.py --once
scripts/run-hxy-outbox-worker.py --poll-seconds 2 --lease-seconds 120 --base-retry-seconds 15
```

The CLI must fail closed with JSON error output if `HXY_DATABASE_URL` is absent.

**Step 4: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_outbox_runtime.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/outbox_repository.py apps/api/hxy_product/outbox_worker.py tests/test_hxy_outbox_runtime.py scripts/run-hxy-outbox-worker.py
git commit -m "feat: add durable HXY outbox runtime"
```

### Task 6: Add asynchronous multimodal issue-understanding proposals

**Files:**
- Create: `apps/api/hxy_product/issue_understanding.py`
- Create: `tests/test_hxy_issue_understanding.py`
- Modify: `apps/api/hxy_knowledge/model_router.py`

**Step 1: Write failing tests around a fake model adapter**

The handler must accept text plus attachment descriptors and return a bounded proposal:

```python
{
    "event_type": "facility_defect",
    "title": "前台灯光持续闪烁",
    "description": "前台左侧灯带在通电后持续闪烁。",
    "location": "前台左侧",
    "impact": "影响现场观感",
    "acceptance_criteria": "灯带连续运行30分钟无闪烁",
    "suggested_owner_assignment_id": None,
    "suggested_due_at": None,
    "risk_flags": [],
    "confidence": 0.91,
}
```

Tests must verify:

- invalid JSON is retryable;
- a valid but incomplete response becomes a stored proposal, not a fabricated fact;
- model response cannot inject `organization_id`, `store_id`, actor, status, or metric values;
- image/audio parse failures preserve the original envelope and produce `needs_attention` after retries;
- prompt contains the current event taxonomy and risk vocabulary, not the formal knowledge corpus wholesale.

**Step 2: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_issue_understanding.py -q
```

Expected: FAIL.

**Step 3: Implement the handler**

Expose:

```python
def build_issue_understanding_handler(
    channel_repository,
    operating_repository,
    model_router,
    policy,
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    ...
```

Handler flow:

```text
load envelope in tenant scope
load authorized attachments
OCR / vision / speech only when needed
call replaceable model route
validate structured proposal
insert AIProposal with model/prompt/input hash
evaluate deterministic policy
auto-accept, request missing fields, or escalate
mark envelope processed or needs_attention
```

Do not add a new model SDK. Route through the existing `ModelRouter` and existing image/parser adapters.

**Step 4: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_issue_understanding.py tests/test_hxy_image_adapter.py tests/test_hxy_parser_adapter.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/issue_understanding.py apps/api/hxy_knowledge/model_router.py tests/test_hxy_issue_understanding.py
git commit -m "feat: add asynchronous issue understanding"
```

## Phase C: Deterministic Operating Workflow

### Task 7: Implement operating event commands and state transitions

**Files:**
- Create: `apps/api/hxy_product/operating_schemas.py`
- Create: `apps/api/hxy_product/operating_repository.py`
- Create: `apps/api/hxy_product/operating_service.py`
- Create: `tests/test_hxy_operating_workflow.py`

**Step 1: Write failing state-machine tests**

Freeze these transitions:

```python
ALLOWED_TASK_TRANSITIONS = {
    "open": {"assigned", "in_progress", "cancelled"},
    "assigned": {"in_progress", "cancelled"},
    "in_progress": {"submitted", "cancelled"},
    "submitted": {"accepted", "rework"},
    "rework": {"in_progress", "submitted", "cancelled"},
    "accepted": set(),
    "cancelled": set(),
}
```

Required tests:

```text
accepted requires an acceptance actor and valid evidence
event creation snapshots the current StoreOperatingRelationship and GovernanceProfile
submitted moves the operating event to resolved only when all active tasks are submitted/accepted
low/medium event may be accepted by store manager
high event requires founder or HQ operations
critical event cannot be closed without HQ acceptance
rework creates a StateTransition and increments no metric directly
AI proposal acceptance records actor_type=policy or user, never AI
concurrent stale command returns 409-style conflict
```

**Step 2: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_operating_workflow.py -q
```

Expected: FAIL.

**Step 3: Implement repository and service**

Public service commands:

```python
create_event_from_proposal(...)
assign_task(...)
start_task(...)
submit_task(...)
accept_task(...)
return_for_rework(...)
escalate_event(...)
cancel_event(...)
```

Every command must:

```text
lock the aggregate FOR UPDATE
validate tenant/store/role scope
evaluate the snapshotted GovernanceProfile, not a browser-supplied mode
validate current state
write new business state
append StateTransition with correlation_id
optionally write OutboxMessage for notification/metric calculation
commit once
```

Do not overload `hxy_product_task_events` with the new workflow. Preserve it for existing task compatibility while `hxy_state_transitions` becomes the canonical cross-aggregate audit stream.

**Step 4: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_operating_workflow.py tests/test_hxy_product_tasks.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/operating_schemas.py apps/api/hxy_product/operating_repository.py apps/api/hxy_product/operating_service.py tests/test_hxy_operating_workflow.py
git commit -m "feat: add governed operating workflow"
```

### Task 8: Add authenticated PWA issue and evidence APIs

**Files:**
- Create: `apps/api/hxy_product/operating_routes.py`
- Create: `apps/api/hxy_product/evidence_repository.py`
- Create: `apps/api/hxy_product/evidence_routes.py`
- Create: `tests/test_hxy_operating_routes.py`
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `apps/api/hxy_product/routes.py`

**Step 1: Write failing API tests**

Required routes:

```text
POST /api/v1/operating/intake
GET  /api/v1/operating/events
GET  /api/v1/operating/events/{event_id}
POST /api/v1/operating/tasks/{task_id}/start
POST /api/v1/operating/tasks/{task_id}/evidence
POST /api/v1/operating/tasks/{task_id}/submit
POST /api/v1/operating/tasks/{task_id}/accept
POST /api/v1/operating/tasks/{task_id}/rework
POST /api/v1/operating/events/{event_id}/escalate
```

Test that:

- the browser cannot choose another organization/store/reporter;
- duplicate `client_intake_id` returns the existing receipt;
- intake responds `202` with `received` or `understanding` without waiting for AI;
- ordinary HXYOS upload can create a SourceAsset without creating an OperatingEvent;
- a user may bind an authorized SourceAsset to an intake, task, training item, or evidence;
- evidence upload validates size, extension, MIME, file hash, store scope, and task state;
- employee cannot accept high-risk work;
- returned payload never exposes internal storage paths, model prompts, or raw callback bodies.

Add capabilities:

```text
operating:report
operating:read
operating:execute
operating:accept
operating:escalate
```

Map them minimally by existing roles.

**Step 2: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_operating_routes.py -q
```

Expected: FAIL.

**Step 3: Implement routes and evidence binding**

Reuse the organization-level `SourceAsset` upload path from `material_routes.py` and `material_worker.py`. An evidence submission creates an immutable `Evidence` record that references the authorized SourceAsset and adds an `AssetBinding`; do not write the same binary into a second evidence directory.

```text
SourceAsset
→ AssetBinding(relation_type=evidence_for)
→ Evidence
→ Task / OperatingEvent
```

Only opaque signed URLs or authenticated streaming routes are public. Never return `object_key` or local paths to ordinary clients.

Wire repository factories and routers into `create_app` without broad refactoring of `hxy_knowledge_api.py`.

**Step 4: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_operating_routes.py tests/test_public_governance.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/operating_routes.py apps/api/hxy_product/evidence_repository.py apps/api/hxy_product/evidence_routes.py apps/api/hxy_product/routes.py apps/api/hxy_knowledge_api.py tests/test_hxy_operating_routes.py
git commit -m "feat: expose governed operating APIs"
```

### Task 9: Compute metric facts from transitions

**Files:**
- Create: `apps/api/hxy_product/operating_metrics.py`
- Create: `tests/test_hxy_operating_metrics.py`

**Step 1: Write failing deterministic metric tests**

Cover:

```text
issue_closure_duration_seconds = event created/open -> closed
issue_overdue_duration_seconds = max(0, closed_at - due_at)
issue_rework_count = number of submitted -> rework transitions
issue_acceptance_count = number of submitted -> accepted transitions
```

The calculator input is records and timestamps, never free text or a model answer. Each output must reference a published `MetricDefinition` version.

**Step 2: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_operating_metrics.py -q
```

Expected: FAIL.

**Step 3: Implement versioned calculation**

Expose:

```python
CALCULATION_VERSION = "operating-metrics.v1"


def calculate_closed_event_facts(event, transitions, metric_definitions) -> list[MetricFactDraft]:
    ...
```

Insert facts only from the `metrics.operating_event.closed` outbox handler. Re-running the same calculation version must be idempotent.

**Step 4: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_operating_metrics.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/operating_metrics.py tests/test_hxy_operating_metrics.py
git commit -m "feat: derive operating metrics from audit facts"
```

## Phase D: Feishu As The Default Channel

### Task 10: Implement Feishu callback verification and identity mapping

**Files:**
- Create: `apps/api/hxy_product/feishu_gateway.py`
- Create: `apps/api/hxy_product/feishu_schemas.py`
- Create: `tests/test_hxy_feishu_gateway.py`
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `ops/env/hxy-knowledge-api.env.example`

**Step 1: Record and verify the current official Feishu contract**

Before writing implementation code, verify the current official Feishu Open Platform documentation for:

```text
event subscription callback challenge
request signature headers and signature algorithm
encrypted callback payload, if enabled
im.message.receive_v1 payload
interactive card callback payload
tenant access token endpoint
message/card send endpoint
```

Add the official documentation URLs as comments in `tests/test_hxy_feishu_gateway.py`. Do not implement from memory or a third-party blog.

**Step 2: Write failing gateway tests**

Test fixtures must cover:

```text
valid URL challenge
invalid verification token
valid signed event
invalid signature
timestamp outside replay window
duplicate event_id
message from non-allowlisted chat
message without @HXYOS or explicit action
mapped user in mapped tenant/store
unmapped user routed to identity attention queue
callback returns quickly before model work
```

Core function contract:

```python
def verify_and_normalize_feishu_callback(
    *,
    headers: Mapping[str, str],
    body: bytes,
    settings: FeishuSettings,
    now: datetime,
) -> FeishuCallback:
    ...
```

**Step 3: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_feishu_gateway.py -q
```

Expected: FAIL.

**Step 4: Implement gateway routes**

Routes:

```text
POST /api/v1/channels/feishu/events
POST /api/v1/channels/feishu/cards
```

Environment:

```text
HXY_FEISHU_APP_ID
HXY_FEISHU_APP_SECRET
HXY_FEISHU_VERIFICATION_TOKEN
HXY_FEISHU_ENCRYPT_KEY
HXY_FEISHU_ALLOWED_TENANT_KEYS
HXY_FEISHU_ALLOWED_CHAT_IDS
HXY_FEISHU_CALLBACK_MAX_AGE_SECONDS=300
```

Do not log secrets, full callback bodies, personal contact data, or attachment download tokens.

**Step 5: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_feishu_gateway.py tests/test_hxy_channel_intake.py -q
```

Expected: PASS.

**Step 6: Commit**

```bash
git add apps/api/hxy_product/feishu_gateway.py apps/api/hxy_product/feishu_schemas.py apps/api/hxy_knowledge_api.py ops/env/hxy-knowledge-api.env.example tests/test_hxy_feishu_gateway.py
git commit -m "feat: add verified Feishu channel gateway"
```

### Task 11: Add Feishu notifications, action cards, and authenticated deep links

**Files:**
- Create: `apps/api/hxy_product/feishu_client.py`
- Create: `apps/api/hxy_product/feishu_cards.py`
- Create: `tests/test_hxy_feishu_cards.py`
- Modify: `apps/api/hxy_product/repository.py`
- Modify: `tests/test_hxy_product_identity.py`

**Step 1: Write failing card and deep-link tests**

Required cards:

```text
issue_created       summary, severity, owner, due time, PWA link
missing_information only missing fields, not the whole classification form
task_assigned       task and completion standard
task_submitted      before/after evidence and acceptance actions
issue_escalated     reason and authorized decision target
daily_digest        new, closed, overdue, rework, founder decisions
```

Card actions must carry only opaque command IDs, not trusted status/role/store values.

Add an identity repository method:

```python
def issue_one_time_session_grant(
    self,
    assignment_id: str,
    *,
    ttl_seconds: int,
    token_factory: Callable[[], str] | None = None,
) -> str:
    ...
```

Store only a hash in `staff_sessions`. The raw grant appears only in the generated fragment link and expires in no more than 10 minutes.

**Step 2: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_feishu_cards.py tests/test_hxy_product_identity.py -q
```

Expected: FAIL for the new behavior.

**Step 3: Implement outbound client and card builders**

Use `httpx` with:

```text
bounded connect/read timeouts
tenant-token cache with early expiry
idempotent message key where supported
sanitized error summaries
retryable vs permanent error classification
```

Card callbacks invoke deterministic service commands and re-check current state. A double-click returns the current state rather than applying the command twice.

**Step 4: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_feishu_cards.py tests/test_hxy_product_identity.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/feishu_client.py apps/api/hxy_product/feishu_cards.py apps/api/hxy_product/repository.py tests/test_hxy_feishu_cards.py tests/test_hxy_product_identity.py
git commit -m "feat: add Feishu operating cards and deep links"
```

## Phase E: Minimal PWA Work Surface

### Task 12: Replace the current issue form with conversation-first capture

**Files:**
- Create: `apps/hxy-web/src/api/operating.ts`
- Create: `apps/hxy-web/src/features/operating/IssueCapture.tsx`
- Create: `apps/hxy-web/src/features/operating/IssueCapture.test.tsx`
- Create: `apps/hxy-web/src/features/operating/IssueDetail.tsx`
- Create: `apps/hxy-web/src/features/operating/IssueDetail.test.tsx`
- Create: `apps/hxy-web/src/features/materials/UploadSourceAsset.tsx`
- Create: `apps/hxy-web/src/features/materials/UploadSourceAsset.test.tsx`
- Modify: `apps/hxy-web/src/App.tsx`
- Modify: `apps/hxy-web/src/styles/shell.css`
- Modify: `apps/hxy-web/src/App.test.tsx`

**Step 1: Write failing component tests**

Capture must support:

```text
one primary text box
camera/image attachment
audio attachment where browser permits
file attachment
optional task context
immediate received state
understanding state without blocking navigation
retry using the same client_intake_id
```

Test user-visible behavior, not internal state:

```tsx
expect(screen.getByRole("textbox", { name: "描述现场情况" })).toBeVisible();
expect(screen.getByRole("button", { name: "拍照或添加图片" })).toBeEnabled();
expect(screen.getByRole("button", { name: "发送" })).toBeDisabled();
```

The upload view must also prove:

```tsx
expect(screen.getByRole("heading", { name: "上传资料" })).toBeVisible();
expect(screen.getByLabelText("选择资料")).toBeEnabled();
expect(screen.getByText("进入组织资料待处理区")).toBeVisible();
```

There must not be a required separate “问题标题” field. AI may propose a title after receipt.

**Step 2: Verify failure**

```bash
npm --prefix apps/hxy-web test -- --run src/features/operating/IssueCapture.test.tsx src/features/operating/IssueDetail.test.tsx src/features/materials/UploadSourceAsset.test.tsx
```

Expected: FAIL because components do not exist.

**Step 3: Implement minimal components and API client**

`IssueCapture` states:

```text
idle -> uploading -> received -> understanding -> ready
                                -> needs_attention
         -> retryable_error
```

`IssueDetail` shows only:

```text
what happened
current owner/status/due time
completion standard
evidence timeline
one valid next action for the current user
```

Do not add dashboards, nested cards, claim review, AI trace, model names, or knowledge compiler internals.

**Step 4: Wire into the existing four-view shell**

Keep:

```text
对话
上传
今日
我的
```

Preserve the main conversation box. `上传` opens a minimal source-asset surface with file selection, optional note, current visibility, processing state, preview, and optional binding to a task/problem/training context. It must not expose review queues, claims, model traces, parser configuration, or governance internals.

**Step 5: Verify pass and build**

```bash
npm --prefix apps/hxy-web test -- --run
npm --prefix apps/hxy-web run build
```

Expected: all Vitest tests PASS and Vite build succeeds.

**Step 6: Commit**

```bash
git add apps/hxy-web/src/api/operating.ts apps/hxy-web/src/features/operating apps/hxy-web/src/features/materials apps/hxy-web/src/App.tsx apps/hxy-web/src/styles/shell.css apps/hxy-web/src/App.test.tsx
git commit -m "feat: add minimal operating capture experience"
```

### Task 13: Add mobile and desktop Playwright coverage

**Files:**
- Create: `apps/hxy-web/tests/operating-loop.spec.ts`
- Modify: `apps/hxy-web/playwright.config.test.ts`

**Step 1: Write failing end-to-end tests**

Required viewports:

```text
390x844 mobile
768x1024 tablet
1440x900 desktop
```

Required journeys:

```text
report text-only issue in <= 30 seconds of user interaction
report issue with photo
upload and preview a SourceAsset without creating an OperatingEvent
bind an uploaded SourceAsset to an existing task as evidence
leave page after received and later find it under 今日
open task from Feishu-style deep link
submit evidence
manager accepts low-risk issue
manager cannot accept high-risk issue without HQ
return for rework and resubmit
```

Also assert:

```text
no horizontal overflow
no overlapping primary controls
primary conversation box visible on first load
tap targets at least 44x44 CSS pixels
no admin/review/compiler text in ordinary user UI
```

**Step 2: Verify failure**

```bash
npm --prefix apps/hxy-web run test:e2e -- operating-loop.spec.ts
```

Expected: FAIL until API mocks and components are wired.

**Step 3: Complete fixtures and responsive fixes**

Use route-level API mocks for component flow, then run one real-stack smoke test after backend tasks are complete. Do not use screenshot-only tests; assert actual state changes and generated requests.

**Step 4: Verify pass**

```bash
npm --prefix apps/hxy-web run test:e2e -- operating-loop.spec.ts
```

Expected: PASS on all three viewports.

**Step 5: Commit**

```bash
git add apps/hxy-web/tests/operating-loop.spec.ts apps/hxy-web/playwright.config.test.ts apps/hxy-web/src/styles/shell.css
git commit -m "test: cover operating loop across viewports"
```

## Phase F: Operations And Production Safety

### Task 14: Add a separate admin dead-letter and retry surface

**Files:**
- Create: `apps/api/hxy_product/job_routes.py`
- Create: `tests/test_hxy_job_admin.py`
- Modify: `apps/api/hxy_knowledge_api.py`

**Step 1: Write failing tests**

Routes:

```text
GET  /api/v1/admin/jobs/dead-letter
POST /api/v1/admin/jobs/{message_id}/retry
GET  /api/v1/admin/channels/identity-attention
```

Only `system_admin` can use them. Responses expose bounded error codes and summaries, not secrets, prompt bodies, raw callbacks, personal contact data, or local paths.

**Step 2: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_job_admin.py -q
```

Expected: FAIL.

**Step 3: Implement routes and manual retry audit**

Manual retry must:

```text
lock dead-letter message
increase max_attempts by one or create a new versioned retry message
append an admin StateTransition/audit record
clear lease fields
set available_at=NOW()
never delete prior attempts
```

**Step 4: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_job_admin.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_product/job_routes.py apps/api/hxy_knowledge_api.py tests/test_hxy_job_admin.py
git commit -m "feat: add governed outbox recovery controls"
```

### Task 15: Add systemd, environment, Nginx, and runbook configuration

**Files:**
- Create: `ops/systemd/hxy-outbox-worker.service`
- Create: `ops/nginx/hxy-feishu-channel.conf.example`
- Create: `docs/runbooks/hxy-feishu-operating-loop.md`
- Modify: `ops/env/hxy-knowledge-api.env.example`
- Modify: `ops/nginx/hxyos-public-edge.conf.example`
- Create: `tests/test_hxy_operating_deployment.py`

**Step 1: Write failing deployment contract tests**

Assert:

```text
service name starts hxy-
WorkingDirectory uses /root/hxy/releases/current
environment uses HXY_DATABASE_URL and HXY_FEISHU_*
ReadWritePaths includes only HXY evidence/artifact directories
callback routes have bounded body size and rate limiting
callback route is HTTPS-only at public edge
no htops path, service, database, or upstream appears
runbook includes secret rotation and callback disable procedure
```

**Step 2: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_operating_deployment.py -q
```

Expected: FAIL.

**Step 3: Add deployment files**

The worker service should follow `ops/systemd/hxy-material-worker.service`, with:

```text
ExecStart=... scripts/run-hxy-outbox-worker.py
Restart=always
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ReadWritePaths=/root/hxy/data/operating-evidence
```

Runbook must cover:

```text
create Feishu internal app
configure event subscriptions and card callbacks
set allowlisted tenant and chat IDs
bind Feishu users to HXY assignments
apply migration 020
start/restart worker and API
verify challenge, signed callback, and outbound card
simulate model outage
inspect/retry dead letters
rotate app secret, verification token, and encrypt key
disable callbacks without losing PWA intake
```

**Step 4: Verify pass**

```bash
.venv/bin/pytest tests/test_hxy_operating_deployment.py tests/test_hxy_secret_scanner.py -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add ops/systemd/hxy-outbox-worker.service ops/nginx/hxy-feishu-channel.conf.example ops/env/hxy-knowledge-api.env.example ops/nginx/hxyos-public-edge.conf.example docs/runbooks/hxy-feishu-operating-loop.md tests/test_hxy_operating_deployment.py
git commit -m "ops: add Feishu operating loop deployment"
```

## Phase G: End-To-End Acceptance

### Task 16: Prove ten real-style operating scenarios

**Files:**
- Create: `tests/fixtures/operating-loop/store-issue-scenarios.json`
- Create: `tests/test_hxy_operating_loop_e2e.py`
- Create: `docs/reports/hxyos-store-issue-v1-acceptance.md`

**Step 1: Define ten scenarios before implementing the test runner**

Include:

```text
1. 装修灯带闪烁，低风险，自动分派
2. 墙面施工与效果图不一致，品牌/SI高风险，升级
3. 施工现场人员受伤，critical，立即通知总部
4. 空调漏水，图片上报，责任方明确
5. 员工发现顾客须知物料缺失，普通门店问题
6. 顾客投诉技师承诺治疗效果，高风险合规事件
7. 同一问题被飞书重复回调，不重复创建
8. 模型超时后重试成功，原始输入只保存一次
9. 整改证据不充分，被退回并重新提交
10. 事件关闭后生成确定性闭环和返工指标
```

Each fixture must include expected severity, auto-advance decision, required role, terminal state, and expected metric keys.

**Step 2: Write the failing end-to-end test**

The test must exercise repository/service/worker boundaries with fake Feishu and fake model HTTP transports, not bypass them by inserting final rows directly.

**Step 3: Verify failure**

```bash
.venv/bin/pytest tests/test_hxy_operating_loop_e2e.py -q
```

Expected: FAIL until all earlier tasks are connected.

**Step 4: Connect topic handlers and complete only missing integration work**

Expected topic registry:

```python
{
    "understand.inbound.issue": issue_understanding_handler,
    "notify.feishu.issue_created": feishu_issue_created_handler,
    "notify.feishu.task_submitted": feishu_task_submitted_handler,
    "notify.feishu.issue_escalated": feishu_issue_escalated_handler,
    "metrics.operating_event.closed": closed_event_metrics_handler,
}
```

Do not add new product scope during this step.

**Step 5: Run focused and full verification**

```bash
.venv/bin/pytest tests/test_hxy_operating_loop_e2e.py -q
.venv/bin/pytest -q
npm --prefix apps/hxy-web test -- --run
npm --prefix apps/hxy-web run build
npm --prefix apps/hxy-web run test:e2e -- operating-loop.spec.ts
```

Expected: all commands PASS.

**Step 6: Write the acceptance report**

Report only measured facts:

```text
scenario pass count
duplicate suppression result
model outage result
authorization boundary result
evidence completeness result
metric derivation result
mobile/desktop result
remaining operational dependencies such as real Feishu credentials
```

Do not claim business improvement before real store baseline data exists.

**Step 7: Commit**

```bash
git add tests/fixtures/operating-loop/store-issue-scenarios.json tests/test_hxy_operating_loop_e2e.py docs/reports/hxyos-store-issue-v1-acceptance.md
git commit -m "test: prove HXY store issue vertical slice"
```

## Final Release Gate

The vertical slice is complete only when all conditions are true:

```text
Feishu callback verification is based on current official documentation
Feishu and PWA intake are idempotent
020 data catalog precedes 021 operating-loop migration
HXYOS upload creates organization-scoped SourceAssets without automatic publication
raw input survives model outage
AI output remains an AIProposal until policy/user acceptance
10 scenarios pass end to end
closed events have owner, state history, and evidence
events retain StoreOperatingRelationship and GovernanceProfile versions
high/critical events require authorized human acceptance
metrics reference published MetricDefinitions and are derived from transitions/facts
ordinary UI contains no governance/compiler internals
mobile and desktop Playwright tests pass
HXY and htops remain fully isolated
```

Final verification command:

```bash
npm test
```

Expected: all Python, TypeScript, web unit, and Playwright suites PASS.
