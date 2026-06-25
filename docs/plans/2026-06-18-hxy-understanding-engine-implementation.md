# HXY Understanding Engine Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build the first tested Understanding Engine contract for HXY: intent recognition, D1-D5 understanding, A1-A5 application outputs, conflict priority, executability gates, and evolution signals.

**Architecture:** Add deterministic Python modules first so behavior is testable without external model keys. Expose the understanding contract through the HXY FastAPI service and enrich chat/intake responses with hidden Inspector-ready details. Later model routing can replace deterministic extractors behind the same contract.

**Tech Stack:** Python, FastAPI, Pydantic, PostgreSQL migration SQL, unittest, static HTML.

---

### Task 1: Pure Understanding Engine Contract

**Files:**
- Create: `apps/api/hxy_knowledge/understanding_engine.py`
- Modify: `tests/test_hxy_knowledge_service.py`

**Step 1: Write failing tests**

Add tests that import `understanding_engine.py` and assert:

- `recognize_intent("清泡调补养怎么给门店员工培训？")` returns action `question`, need `training`, mode `deep_understanding`;
- `recognize_intent("这份资料上传后请入库")` returns action `ingest`;
- `understand_text(...)` returns `depth` keys `D1_perception` through `D5_judgment`;
- the result includes `applications` keys `A1_role_output` through `A5_memory_evolution`;
- `D5_judgment["priority_matrix"]` includes `impact`, `urgency`, `controllability`, `strategic_relevance`, and `priority`;
- the result includes an `executability_gate` with `resources`, `capability`, `permission`, `risk`, and `acceptance`.

**Step 2: Run focused service tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_service.py -v`

Expected: fail because module does not exist.

**Step 3: Implement minimal deterministic module**

Implement:

```python
def recognize_intent(text: str, attachments: list[dict] | None = None) -> dict
def understand_text(text: str, scenario: str = "创始人内部决策", role: str = "founder") -> dict
def priority_matrix_for(conflict_or_need: str, *, domain: str, scenario: str) -> dict
def executability_gate_for(action: str, *, scenario: str, role: str) -> dict
```

Keep heuristics simple, explicit, and HXY-specific. Do not call external model APIs yet.

**Step 4: Run focused service tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_service.py -v`

Expected: pass.

---

### Task 2: API Endpoint For Understanding

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing API test**

Add `POST /api/operating-brain/understand` test with JSON:

```json
{
  "input": "清泡调补养怎么给门店员工培训？",
  "scenario": "门店员工培训",
  "role": "store_staff"
}
```

Assert:

- HTTP 200;
- response has `intent`, `depth`, `applications`, `executability_gate`;
- `intent["mode"] == "deep_understanding"`;
- `depth["D5_judgment"]` contains `main_conflict`;
- `applications["A1_role_output"]` contains `store_staff`.

**Step 2: Run focused API tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_api.py -v`

Expected: fail because route does not exist.

**Step 3: Implement endpoint**

Add request model:

```python
class UnderstandRequest(BaseModel):
    input: str
    scenario: str = "创始人内部决策"
    role: str = "founder"
    attachments: list[dict[str, Any]] = Field(default_factory=list)
```

Return `understand_text(...)`.

**Step 4: Run focused API tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_api.py -v`

Expected: pass.

---

### Task 3: Enrich Chat With Inspector-Ready Understanding

**Files:**
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing test**

Add a chat test asserting `POST /api/knowledge/chat` returns:

- `understanding.intent`;
- `understanding.depth.D5_judgment.main_conflict`;
- `understanding.applications.A2_risk_boundary`;
- `understanding.executability_gate`;

The test should also assert the main `answer` remains concise and does not expose `D1_perception`, `chunk`, or file paths.

**Step 2: Run focused API tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_api.py -v`

Expected: fail because chat does not include understanding.

**Step 3: Implement enrichment**

In `knowledge_chat`, call `understand_text(question, scenario=scenario, role=...)` after question validation. Add it to the saved answer payload and response under `understanding`.

Keep main chat display behavior unchanged: detailed understanding is for Inspector, not the default answer.

**Step 4: Run focused API tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_api.py -v`

Expected: pass.

---

### Task 4: Intake Request Contract

**Files:**
- Create: `apps/api/hxy_knowledge/intake.py`
- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing tests**

Add tests for `POST /api/operating-brain/intake`:

- text-only input with `input`;
- file metadata input with `attachments`;
- mixed input where question plus image metadata returns action `analyze_multimodal`.

Assert intake response includes:

- `intake_id`;
- `intent`;
- `recommended_path`: `quick_answer`, `deep_understanding`, `ingest_memory`, `correction_review`, or `execute_skill`;
- `memory_action`: `none`, `stage_raw`, `create_understanding_record`, `create_review_task`, or `suggest_answer_card`;
- `quality_flags`.

**Step 2: Run focused API tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_api.py -v`

Expected: fail.

**Step 3: Implement deterministic intake**

Implement `build_intake_plan(input_text, attachments, scenario, role)` in `intake.py`. Add FastAPI endpoint using it. This does not yet write DB records; it defines the routing contract.

**Step 4: Run focused API tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_api.py -v`

Expected: pass.

---

### Task 5: Database Migration For Understanding Records

**Files:**
- Create: `data/migrations/006_hxy_understanding_engine.sql`
- Modify: `tests/test_hxy_knowledge_service.py`

**Step 1: Write failing migration test**

Assert migration contains:

- `hxy_understanding_runs`;
- `intent_json`;
- `depth_json`;
- `applications_json`;
- `priority_json`;
- `executability_json`;
- `confidence_json`;
- `hxy_knowledge_evolution_events`;
- `event_type`;
- `answer_card_id`;

**Step 2: Run focused service tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_service.py -v`

Expected: fail until migration exists.

**Step 3: Add migration**

Create tables:

- `hxy_understanding_runs`: stores input hash, scenario, role, intent, depth, applications, priority, executability, confidence, linked answer run, linked asset.
- `hxy_knowledge_evolution_events`: stores hot knowledge, unstable knowledge, blind spot, correction, low quality source, answer card upgrade suggestions.

Use JSONB for structured fields and HXY-owned names.

**Step 4: Run focused service tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_service.py -v`

Expected: pass.

---

### Task 6: Repository Persistence Methods

**Files:**
- Modify: `apps/api/hxy_knowledge/repository.py`
- Modify: `tests/test_hxy_knowledge_service.py`

**Step 1: Write failing tests**

Assert `KnowledgeRepository` exposes:

- `save_understanding_run`;
- `save_evolution_event`;
- `understanding_runs`;
- `evolution_events`.

Add SQL-builder tests if direct DB integration is unavailable.

**Step 2: Run focused service tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_service.py -v`

Expected: fail.

**Step 3: Implement methods**

Use parameterized SQL only. Store JSON with `json.dumps(..., ensure_ascii=False)`.

**Step 4: Run focused service tests**

Run: `python3 -m unittest tests/test_hxy_knowledge_service.py -v`

Expected: pass.

---

### Task 7: Frontend Inspector Integration

**Files:**
- Modify: `apps/admin-web/brain.html`
- Modify: `tests/test_hxy_brain_frontend.py`

**Step 1: Write failing frontend tests**

Assert `brain.html` contains:

- an Inspector section for `理解详情`;
- labels for `主要矛盾`, `风险边界`, `可执行性`, `知识进化`;
- no default rendering of `chunk_id`, `source_path`, or OCR text in the main chat template.

**Step 2: Run frontend tests**

Run: `python3 -m unittest tests/test_hxy_brain_frontend.py -v`

Expected: fail.

**Step 3: Implement UI behavior**

Keep middle chat as the main focus. Add a Details/Inspector rendering path that shows Understanding Engine details only after the user clicks details.

**Step 4: Run frontend tests and JS syntax**

Run:

```bash
python3 -m unittest tests/test_hxy_brain_frontend.py -v
node - <<'NODE'
const fs = require('fs');
const html = fs.readFileSync('apps/admin-web/brain.html', 'utf8');
const match = html.match(/<script>([\s\S]*)<\/script>/);
if (!match) throw new Error('script block not found');
new Function(match[1]);
console.log('brain.html script syntax OK');
NODE
```

Expected: pass.

---

### Task 8: Full Verification

Run:

```bash
python3 -m unittest tests/test_hxy_knowledge_api.py tests/test_hxy_knowledge_service.py tests/test_hxy_brain_frontend.py tests/test_hxy_operating_brain_docs.py -v
node - <<'NODE'
const fs = require('fs');
const html = fs.readFileSync('apps/admin-web/brain.html', 'utf8');
const match = html.match(/<script>([\s\S]*)<\/script>/);
if (!match) throw new Error('script block not found');
new Function(match[1]);
console.log('brain.html script syntax OK');
NODE
curl -sS -o /tmp/hxy-understanding-capabilities.json -w '%{http_code}\n' http://127.0.0.1:18081/api/operating-brain/capabilities
```

Expected:

- all tests pass;
- JavaScript parses;
- capabilities endpoint returns 200.

If the service is running, restart it after code changes and smoke test:

```bash
curl -sS -X POST http://127.0.0.1:18081/api/operating-brain/understand \
  -H 'content-type: application/json' \
  -d '{"input":"清泡调补养怎么给门店员工培训？","scenario":"门店员工培训","role":"store_staff"}'
```

Expected: response contains `intent`, `depth`, `applications`, and `executability_gate`.
