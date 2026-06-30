# HXY Public AI Workspace V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a governed public AI workspace event stream so HXYOS AI work becomes visible, replayable, redacted when sensitive, and routable into review tasks or process-memory drafts without mutating approved knowledge.

**Architecture:** Add a pure JSONL-backed workspace event module, expose it through HXY-owned FastAPI endpoints, and extend the existing `brain.html` operating brain page with a public workspace stream. The workspace stores episodic memory only; review-task and process-memory routes reuse existing governance builders and never publish approved knowledge.

**Tech Stack:** Python standard library, FastAPI, existing HXY repository abstraction, JSONL under `knowledge/workspace/events.jsonl`, static HTML/JS, pytest/unittest.

---

## Product Constraints

- Do not touch `/root/htops` data or services.
- Do not create `htops-*` service names or routes.
- Workspace events are `episodic_memory`, not formal knowledge.
- No workspace route can create or mutate `approved` knowledge.
- Process memory created from a workspace event is context-only.
- Sensitive events must redact public payloads.
- `private_draft` events cannot be routed into formal promotion paths directly.

## Task 1: Add Workspace Event Policy Tests

**Files:**

- Create: `tests/test_hxy_workspace_events.py`
- Create later: `apps/api/hxy_knowledge/workspace_events.py`

**Step 1: Write failing tests**

Create tests for:

```python
def test_create_workspace_event_defaults_to_public_org_and_not_authority(tmp_path):
    event = create_workspace_event(
        {
            "topic": "员工话术风险",
            "actor": "founder",
            "role": "创始人内部决策",
            "input": "泡脚能不能说治疗失眠？",
            "ai_output": {"summary": "不能承诺治疗。"},
            "risk_flags": ["medical_claim_risk"],
        },
        store_path=tmp_path / "events.jsonl",
        now=lambda: "2026-07-01T00:00:00+00:00",
    )

    assert event["version"] == "hxy-workspace-event.v1"
    assert event["visibility"] == "public_org"
    assert event["memory_layer"] == "episodic"
    assert event["official_use_allowed"] is False
    assert event["authority_rule"] == "workspace_events_are_episodic_memory_not_approved_knowledge"
```

```python
def test_sensitive_event_is_restricted_and_public_copy_is_redacted(tmp_path):
    event = create_workspace_event(
        {
            "topic": "API key pasted by mistake",
            "actor": "founder",
            "role": "创始人内部决策",
            "input": "HXY_API_TOKEN=secret-value",
            "ai_output": {"summary": "请轮换密钥。"},
        },
        store_path=tmp_path / "events.jsonl",
        now=lambda: "2026-07-01T00:00:00+00:00",
    )

    public_event = redact_workspace_event(event)
    assert event["visibility"] == "restricted_role"
    assert public_event["visibility"] == "redacted_public"
    assert "secret-value" not in json.dumps(public_event, ensure_ascii=False)
    assert public_event["input"] == "[redacted]"
```

```python
def test_list_workspace_events_returns_newest_first_and_filters_query(tmp_path):
    store = tmp_path / "events.jsonl"
    create_workspace_event({"topic": "品牌口径", "input": "A"}, store_path=store, now=lambda: "2026-07-01T00:00:00+00:00")
    create_workspace_event({"topic": "员工训练", "input": "B"}, store_path=store, now=lambda: "2026-07-01T00:01:00+00:00")

    result = list_workspace_events(store, limit=10, query="员工", visibility=None)
    assert [item["topic"] for item in result["items"]] == ["员工训练"]
```

**Step 2: Run test to verify failure**

Run:

```bash
PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_workspace_events.py -q
```

Expected: FAIL because `hxy_knowledge.workspace_events` does not exist.

## Task 2: Implement Pure Workspace Event Module

**Files:**

- Create: `apps/api/hxy_knowledge/workspace_events.py`
- Test: `tests/test_hxy_workspace_events.py`

**Step 1: Implement minimal module**

Implement:

```python
SENSITIVE_PATTERNS = [
    ("secret", re.compile(r"(api[_-]?key|token|password|secret|database_url|HXY_API_TOKEN|HXY_DATABASE_URL)", re.I)),
    ("phone", re.compile(r"(?<!\\d)1[3-9]\\d{9}(?!\\d)")),
    ("financing", re.compile(r"(估值|股权|融资|投资协议|对赌|承诺函)")),
]
```

Functions:

```python
def create_workspace_event(payload: dict[str, Any], *, store_path: Path, now: Callable[[], str] | None = None) -> dict[str, Any]
def list_workspace_events(store_path: Path, *, limit: int = 20, query: str = "", visibility: str | None = None) -> dict[str, Any]
def get_workspace_event(store_path: Path, event_id: str) -> dict[str, Any] | None
def redact_workspace_event(event: dict[str, Any]) -> dict[str, Any]
def classify_workspace_visibility(payload: dict[str, Any]) -> str
```

Required event defaults:

```python
{
    "version": "hxy-workspace-event.v1",
    "event_id": "workspace-event-<short-token>",
    "topic": "...",
    "actor": "unknown",
    "role": "team",
    "visibility": "public_org | restricted_role | private_draft | redacted_public",
    "input": "...",
    "ai_output": {},
    "evidence": [],
    "risk_flags": [],
    "corrections": [],
    "generated_tasks": [],
    "memory_action": {"type": "process_memory_context_only", "allowed_as_authority": False},
    "review_action": {"type": "none", "required": False},
    "memory_layer": "episodic",
    "official_use_allowed": False,
    "authority_rule": "workspace_events_are_episodic_memory_not_approved_knowledge",
    "created_at": "..."
}
```

**Step 2: Run tests**

Run:

```bash
PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_workspace_events.py -q
```

Expected: PASS.

**Step 3: Commit**

```bash
git add apps/api/hxy_knowledge/workspace_events.py tests/test_hxy_workspace_events.py
git commit -m "feat: add hxy workspace event store"
```

## Task 3: Add Workspace API Tests

**Files:**

- Modify: `tests/test_hxy_knowledge_api.py`
- Modify later: `apps/api/hxy_knowledge_api.py`

**Step 1: Add API tests**

Add tests near operating brain tests:

```python
def test_operating_brain_workspace_event_create_and_list(self):
    response = self.client.post(
        "/api/operating-brain/workspace/events",
        json={
            "topic": "员工话术风险",
            "actor": "founder",
            "role": "创始人内部决策",
            "input": "泡脚能不能说治疗失眠？",
            "ai_output": {"summary": "不能承诺治疗。"},
            "risk_flags": ["medical_claim_risk"],
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == "hxy-workspace-event-created.v1"
    assert body["event"]["official_use_allowed"] is False

    listing = self.client.get("/api/operating-brain/workspace/events?limit=10")
    assert listing.status_code == 200
    assert listing.json()["items"][0]["topic"] == "员工话术风险"
```

```python
def test_operating_brain_workspace_event_list_redacts_restricted_payload(self):
    self.client.post(
        "/api/operating-brain/workspace/events",
        json={
            "topic": "密钥误发",
            "input": "HXY_API_TOKEN=secret-value",
            "ai_output": {"summary": "请轮换密钥。"},
        },
    )

    body = self.client.get("/api/operating-brain/workspace/events").json()
    serialized = json.dumps(body, ensure_ascii=False)
    assert "secret-value" not in serialized
    assert body["items"][0]["visibility"] == "redacted_public"
```

```python
def test_operating_brain_workspace_event_review_task_does_not_approve_knowledge(self):
    created = self.client.post(
        "/api/operating-brain/workspace/events",
        json={
            "topic": "话术纠偏",
            "input": "员工说一周见效",
            "ai_output": {"summary": "需要复核禁用表达。"},
            "risk_flags": ["efficacy_claim_risk"],
        },
    ).json()

    response = self.client.post(
        f"/api/operating-brain/workspace/events/{created['event']['event_id']}/review-task",
        json={"reviewer": "founder", "note": "进入话术复核"},
    )
    body = response.json()
    assert body["status"] == "review_task_created"
    assert body["official_use_allowed"] is False
    assert self.repo.saved_review_task["reason"] == "workspace_event_review"
```

```python
def test_operating_brain_workspace_private_draft_cannot_create_process_memory(self):
    created = self.client.post(
        "/api/operating-brain/workspace/events",
        json={
            "topic": "个人草稿",
            "visibility": "private_draft",
            "input": "还没确认的想法",
        },
    ).json()

    response = self.client.post(
        f"/api/operating-brain/workspace/events/{created['event']['event_id']}/process-memory",
        json={"actor": "founder", "target_domain": "brand"},
    )
    assert response.status_code == 400
```

**Step 2: Run tests to verify failure**

Run:

```bash
PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_api.py -k "workspace_event" -q
```

Expected: FAIL because endpoints do not exist.

## Task 4: Add Workspace API Endpoints

**Files:**

- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Step 1: Add imports and request models**

Import workspace module:

```python
from hxy_knowledge.workspace_events import (
    create_workspace_event,
    get_workspace_event,
    list_workspace_events,
    redact_workspace_event,
)
```

Add Pydantic models:

```python
class WorkspaceEventRequest(BaseModel):
    topic: str = ""
    actor: str = "unknown"
    role: str = "team"
    visibility: str = "public_org"
    input: str = ""
    ai_output: dict[str, Any] = Field(default_factory=dict)
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    risk_flags: list[str] = Field(default_factory=list)
    corrections: list[dict[str, Any]] = Field(default_factory=list)
    generated_tasks: list[dict[str, Any]] = Field(default_factory=list)
    memory_action: dict[str, Any] = Field(default_factory=dict)
    review_action: dict[str, Any] = Field(default_factory=dict)

class WorkspaceEventReviewTaskRequest(BaseModel):
    reviewer: str = "unknown"
    note: str = ""

class WorkspaceEventProcessMemoryRequest(BaseModel):
    actor: str = "unknown"
    target_domain: str = "general"
    confidence: float = Field(default=0.5, ge=0, le=1)
```

**Step 2: Add store path helper**

Inside `create_app`, set:

```python
workspace_event_store = resolved_root / "knowledge" / "workspace" / "events.jsonl"
```

**Step 3: Add endpoints**

Add:

```python
@app.post("/api/operating-brain/workspace/events", dependencies=[Depends(require_api_token)])
async def operating_brain_workspace_event_create_endpoint(request: WorkspaceEventRequest) -> dict[str, Any]:
    event = create_workspace_event(request.model_dump(), store_path=workspace_event_store)
    return {
        "version": "hxy-workspace-event-created.v1",
        "event": event,
        "public_event": redact_workspace_event(event),
        "authority_rule": "workspace_events_are_episodic_memory_not_approved_knowledge",
    }
```

Add:

```python
@app.get("/api/operating-brain/workspace/events")
async def operating_brain_workspace_event_list_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    q: str = "",
    visibility: str | None = None,
) -> dict[str, Any]:
    return list_workspace_events(workspace_event_store, limit=limit, query=q, visibility=visibility)
```

Add:

```python
@app.get("/api/operating-brain/workspace/events/{event_id}")
async def operating_brain_workspace_event_get_endpoint(event_id: str) -> dict[str, Any]:
    event = get_workspace_event(workspace_event_store, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="workspace event not found")
    return {
        "version": "hxy-workspace-event-detail.v1",
        "event": redact_workspace_event(event),
        "authority_rule": "workspace_events_are_episodic_memory_not_approved_knowledge",
    }
```

Add review task endpoint:

```python
@app.post("/api/operating-brain/workspace/events/{event_id}/review-task", dependencies=[Depends(require_api_token)])
async def operating_brain_workspace_event_review_task_endpoint(
    event_id: str,
    request: WorkspaceEventReviewTaskRequest,
) -> dict[str, Any]:
    event = get_workspace_event(workspace_event_store, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="workspace event not found")
    task_id = make_repository().create_review_task(
        {
            "question": event.get("topic") or "公共 AI 工作间复核任务",
            "intent": "workspace_event_review",
            "reason": "workspace_event_review",
            "priority": "high" if event.get("risk_flags") else "medium",
            "correction_package": {
                "source": "workspace_event",
                "event_id": event_id,
                "risk_flags": event.get("risk_flags") or [],
                "reviewer": request.reviewer,
                "note": request.note,
            },
            "payload_json": {"source": "workspace_event", "event": event},
        }
    )
    return {
        "version": "hxy-workspace-event-review-task-result.v1",
        "status": "review_task_created",
        "review_task_id": task_id,
        "official_use_allowed": False,
        "authority_rule": "review_task_is_not_approved_knowledge",
    }
```

Add process-memory endpoint:

```python
@app.post("/api/operating-brain/workspace/events/{event_id}/process-memory", dependencies=[Depends(require_api_token)])
async def operating_brain_workspace_event_process_memory_endpoint(
    event_id: str,
    request: WorkspaceEventProcessMemoryRequest,
) -> dict[str, Any]:
    event = get_workspace_event(workspace_event_store, event_id)
    if not event:
        raise HTTPException(status_code=404, detail="workspace event not found")
    if event.get("visibility") == "private_draft":
        raise HTTPException(status_code=400, detail="private_draft cannot be converted to process memory directly")
    text = "\\n".join(
        part for part in [
            str(event.get("topic") or ""),
            str(event.get("input") or ""),
            str((event.get("ai_output") or {}).get("summary") or ""),
        ] if part
    )
    preview_request = ProcessMemoryRequest(
        text=text,
        source=f"workspace_event:{event_id}",
        actor=request.actor,
        confidence=request.confidence,
        target_domain=request.target_domain,
    )
    preview = _build_process_memory_preview(preview_request)
    preview["source_event_id"] = event_id
    preview["status"] = "process_memory_preview_created"
    preview["authority_rule"] = "process_memory_is_context_only_not_approved_knowledge"
    return preview
```

**Step 4: Run focused API tests**

Run:

```bash
PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_knowledge_api.py -k "workspace_event" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/api/hxy_knowledge_api.py tests/test_hxy_knowledge_api.py
git commit -m "feat: expose hxy public workspace events api"
```

## Task 5: Add Frontend Contract Tests

**Files:**

- Modify: `tests/test_hxy_brain_frontend.py`
- Modify later: `apps/admin-web/brain.html`

**Step 1: Add failing static tests**

Add:

```python
def test_brain_page_exposes_public_ai_workspace_event_stream(self):
    html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")

    for label in [
        "公共 AI 工作间",
        "最新 AI 工作",
        "组织可见",
        "风险标签",
        "复核动作",
        "记忆动作",
        "不是正式知识",
    ]:
        self.assertIn(label, html)

    for item in [
        'id="workspaceEvents"',
        'id="refreshWorkspaceEvents"',
        "/api/operating-brain/workspace/events",
        "refreshWorkspaceEvents",
        "renderWorkspaceEvents",
        "createWorkspaceEvent",
        "data-workspace-review",
        "data-workspace-memory",
    ]:
        self.assertIn(item, html)
```

```python
def test_brain_page_workspace_copy_does_not_claim_authority(self):
    html = (ROOT / "apps" / "admin-web" / "brain.html").read_text(encoding="utf-8")
    workspace_start = html.index("公共 AI 工作间")
    workspace_block = html[workspace_start:workspace_start + 3000]

    self.assertIn("不是正式知识", workspace_block)
    self.assertNotIn("权威知识发布", workspace_block)
    self.assertNotIn("已批准口径", workspace_block)
```

**Step 2: Run tests to verify failure**

Run:

```bash
pytest tests/test_hxy_brain_frontend.py -k "workspace" -q
```

Expected: FAIL until HTML is updated.

## Task 6: Add Public Workspace Stream To `brain.html`

**Files:**

- Modify: `apps/admin-web/brain.html`
- Test: `tests/test_hxy_brain_frontend.py`

**Step 1: Add markup**

Add a panel near the operating issue queue:

```html
<section class="public-workspace-panel">
  <div class="panel-heading">
    <div>
      <h2>公共 AI 工作间</h2>
      <p>最新 AI 工作会沉淀为组织可见事件；它不是正式知识。</p>
    </div>
    <button class="secondary" id="refreshWorkspaceEvents" type="button">刷新</button>
  </div>
  <div class="workspace-event-meta">
    <span>组织可见</span>
    <span>风险标签</span>
    <span>复核动作</span>
    <span>记忆动作</span>
  </div>
  <div id="workspaceEvents" class="workspace-events">
    <div class="empty-state">暂无公共 AI 工作记录。</div>
  </div>
</section>
```

**Step 2: Add JS helpers**

Add functions:

```javascript
async function refreshWorkspaceEvents() {
  const container = document.getElementById("workspaceEvents");
  if (!container) return;
  container.innerHTML = '<div class="empty-state">加载最新 AI 工作...</div>';
  try {
    const data = await apiGet("/api/operating-brain/workspace/events?limit=20");
    renderWorkspaceEvents(data.items || []);
  } catch (error) {
    container.innerHTML = `<div class="empty-state error">${escapeHtml(error.message || "加载失败")}</div>`;
  }
}

function renderWorkspaceEvents(items) {
  const container = document.getElementById("workspaceEvents");
  if (!container) return;
  if (!items.length) {
    container.innerHTML = '<div class="empty-state">暂无公共 AI 工作记录。</div>';
    return;
  }
  container.innerHTML = items.map((event) => {
    const output = event.ai_output || {};
    const summary = output.summary || output.answer || "等待复核";
    const risks = (event.risk_flags || []).join(" · ") || "无";
    const review = (event.review_action || {}).type || "none";
    const memory = (event.memory_action || {}).type || "context_only";
    return `
      <article class="workspace-event">
        <div class="workspace-event-main">
          <strong>${escapeHtml(event.topic || "未命名工作")}</strong>
          <p>${escapeHtml(summary)}</p>
          <small>${escapeHtml(event.role || "team")} · ${escapeHtml(event.visibility || "public_org")}</small>
        </div>
        <div class="workspace-event-tags">
          <span>风险标签：${escapeHtml(risks)}</span>
          <span>复核动作：${escapeHtml(review)}</span>
          <span>记忆动作：${escapeHtml(memory)}</span>
        </div>
        <div class="workspace-event-actions">
          <button class="secondary" data-workspace-review="${escapeHtml(event.event_id)}" type="button">转复核</button>
          <button class="secondary" data-workspace-memory="${escapeHtml(event.event_id)}" type="button">记为过程记忆</button>
        </div>
      </article>
    `;
  }).join("");
}
```

Add:

```javascript
async function createWorkspaceEvent(payload) {
  return apiPost("/api/operating-brain/workspace/events", payload);
}
```

Wire refresh button and document click handlers for `data-workspace-review` and `data-workspace-memory`.

**Step 3: Hook event creation after existing workflow result**

After the main answer/training/intake result is rendered, call `createWorkspaceEvent(...)` with:

```javascript
{
  topic: currentInput.slice(0, 80) || "AI 工作记录",
  actor: "web",
  role: selectedScenario || "team",
  visibility: "public_org",
  input: currentInput,
  ai_output: {
    summary: result.result_card?.answer || result.summary || result.answer || "",
    answer_status: result.answer_status?.status || result.review_status || ""
  },
  evidence: result.evidence || result.citations || [],
  risk_flags: result.risk_flags || result.policy_review?.risk_flags || [],
  memory_action: {
    type: result.workbench_intake?.memory_action ? "process_memory_context_only" : "none",
    allowed_as_authority: false
  },
  review_action: {
    type: result.needs_review ? "create_review_task" : "none",
    required: Boolean(result.needs_review)
  }
}
```

If event creation fails, do not block the user-facing answer. Show a small status message.

**Step 4: Run frontend static tests**

Run:

```bash
pytest tests/test_hxy_brain_frontend.py -k "workspace" -q
```

Expected: PASS.

**Step 5: Commit**

```bash
git add apps/admin-web/brain.html tests/test_hxy_brain_frontend.py
git commit -m "feat: show public ai workspace events"
```

## Task 7: Add End-To-End Verification

**Files:**

- Existing tests only unless failures require updates.

**Step 1: Run focused backend tests**

Run:

```bash
PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_workspace_events.py tests/test_hxy_knowledge_api.py -k "workspace_event" -q
```

Expected: PASS.

**Step 2: Run frontend tests**

Run:

```bash
pytest tests/test_hxy_brain_frontend.py -q
```

Expected: PASS.

**Step 3: Run full test suite**

Run:

```bash
npm test
```

Expected: all existing Python and TS tests pass.

**Step 4: Inspect git diff**

Run:

```bash
git status --short
git diff --stat HEAD
```

Expected:

- only intended workspace event/API/frontend files changed after the task commits
- no `/root/htops` path introduced
- no approved answer-card mutation path introduced

## Acceptance Criteria

- `POST /api/operating-brain/workspace/events` creates governed events.
- `GET /api/operating-brain/workspace/events` lists public/redacted events newest first.
- Sensitive content is not leaked through list/detail endpoints.
- Review task routing creates review tasks and keeps `official_use_allowed=false`.
- Process-memory routing creates context-only previews and blocks `private_draft`.
- `brain.html` shows a public workspace stream and explicitly says events are not official knowledge.
- Tests cover event creation, redaction, listing, review routing, process-memory boundary, and frontend contract.
