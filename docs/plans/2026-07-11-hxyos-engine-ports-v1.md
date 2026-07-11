# HXYOS Engine Ports V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Put current model, parser, and retrieval behavior behind governed HXYOS engine contracts without changing product behavior or introducing an external platform.

**Architecture:** Add a small `hxy_engines` package containing an immutable execution context, bounded artifact envelopes, and Python `Protocol` ports. Wrap the existing `ModelRouter`, parser adapter, and product knowledge context first; add the remaining engine ports only when their first real caller is implemented.

**Tech Stack:** Python 3.12, dataclasses, typing.Protocol, FastAPI, PostgreSQL, pytest.

---

### Task 1: Governed Engine Context And Result Envelope

**Files:**
- Create: `apps/api/hxy_engines/__init__.py`
- Create: `apps/api/hxy_engines/contracts.py`
- Test: `tests/test_hxy_engine_contracts.py`

**Step 1: Write the failing contract tests**

Test that `EngineContext` requires a request id, account id, assignment id,
organization id, purpose, authority policy, and bounded budget. Test that it
normalizes optional store scope without accepting raw credentials or source
content.

Test that `EngineResult` records engine name/version, status, artifacts,
latency, usage, and policy decisions while rejecting an engine attempt to mark
an artifact as `approved`.

**Step 2: Verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_engine_contracts.py -q
```

Expected: collection fails because `hxy_engines.contracts` does not exist.

**Step 3: Implement the minimal immutable types**

Use frozen dataclasses and bounded validation in `__post_init__`. Keep content
payloads opaque and require canonical ids/provenance instead of filesystem
paths in public results.

**Step 4: Verify GREEN**

Run the focused test and existing product permission tests.

**Step 5: Commit**

```bash
git add apps/api/hxy_engines tests/test_hxy_engine_contracts.py
git commit -m "feat: add governed engine contracts"
```

### Task 2: ModelGateway Port And Current Adapter

**Files:**
- Create: `apps/api/hxy_engines/model_gateway.py`
- Create: `apps/api/hxy_engines/adapters/current_model.py`
- Modify: `apps/api/hxy_knowledge/model_router.py`
- Test: `tests/test_hxy_model_gateway.py`

**Step 1: Write failing tests**

Require the port to accept only a governed context plus a typed model request.
Assert the current adapter preserves authority-card no-model behavior, never
returns an API key, and maps provider/model/usage metadata into `EngineResult`.

**Step 2: Verify RED**

Run:

```bash
.venv/bin/pytest tests/test_hxy_model_gateway.py -q
```

**Step 3: Implement a wrapper, not a rewrite**

Delegate execution to the existing `ModelRouter`. Add only the metadata needed
for the stable port. Do not add LiteLLM yet.

**Step 4: Verify GREEN and regression**

Run model-router, answer-pipeline, and API tests.

**Step 5: Commit**

```bash
git commit -am "refactor: place model routing behind engine port"
```

### Task 3: DocumentParser Port And Current Adapter

**Files:**
- Create: `apps/api/hxy_engines/document_parser.py`
- Create: `apps/api/hxy_engines/adapters/current_parser.py`
- Modify: `apps/api/hxy_knowledge/parser_adapter.py`
- Test: `tests/test_hxy_document_parser_port.py`

**Step 1: Write failing tests**

Require immutable source ids, media type, parser policy, and authorized storage
reference. Assert every parser artifact remains `reference`, includes parser
provenance and quality state, and cannot expose a server path through the
product envelope.

**Step 2: Verify RED**

Run the focused parser-port test.

**Step 3: Implement the adapter**

Wrap current MarkItDown/MinerU behavior. Keep filesystem paths inside the
private adapter result and convert them to canonical artifact ids before they
cross the port.

**Step 4: Verify GREEN and regression**

Run parser, material worker, upload, and assignment-isolation tests.

**Step 5: Commit**

```bash
git commit -am "refactor: place parsing behind engine port"
```

### Task 4: RetrievalEngine Port And Permission-First Adapter

**Files:**
- Create: `apps/api/hxy_engines/retrieval.py`
- Create: `apps/api/hxy_engines/adapters/current_retrieval.py`
- Modify: `apps/api/hxy_product/knowledge_context.py`
- Modify: `apps/api/hxy_product/conversation_routes.py`
- Test: `tests/test_hxy_retrieval_engine.py`
- Test: `tests/test_hxy_product_postgres.py`

**Step 1: Write failing tests**

Assert assignment/store filters are mandatory inputs, unauthorized material is
never returned, private chunks can never report `approved`, source links remain
bounded, and an adapter cannot retrieve before the scope is resolved.

**Step 2: Verify RED**

Run focused unit and isolated PostgreSQL tests.

**Step 3: Implement current retrieval adapter**

Move no SQL initially. Wrap the current repository/knowledge-context call and
return ranked canonical evidence records. Preserve exact existing behavior.

**Step 4: Verify GREEN and regression**

Run all conversation, material, citation, and PostgreSQL isolation tests.

**Step 5: Commit**

```bash
git commit -am "refactor: enforce retrieval engine boundary"
```

### Task 5: Engine Descriptor And Benchmark Schema

**Files:**
- Create: `apps/api/hxy_engines/descriptor.py`
- Create: `knowledge/benchmarks/hxy-engine-benchmark-v1.schema.json`
- Create: `knowledge/benchmarks/hxy-engine-benchmark-v1.sample.json`
- Create: `scripts/validate-hxy-engine-benchmark.py`
- Test: `tests/test_hxy_engine_benchmark_schema.py`

**Step 1: Write failing schema tests**

Require role, assignment scope, allowed/forbidden evidence ids, authority
expectation, risk expectation, useful outcome, latency/cost budget, and engine
descriptor. Reject private content and local paths in benchmark fixtures.

**Step 2: Verify RED**

Run the focused test.

**Step 3: Implement schema and validator**

Create a representative sample for founder, operations, store manager,
employee, and knowledge/data admin. Do not invent business facts; use synthetic
ids and behavior contracts.

**Step 4: Verify GREEN**

Run schema tests, secret scan, and public-release scan.

**Step 5: Commit**

```bash
git commit -am "test: add engine benchmark contract"
```

### Task 6: Full Verification And Release Decision

**Files:**
- Modify: `docs/project-brain/roadmap/02-hxyos-2-component-benchmark-and-migration.md`

**Step 1: Run complete verification**

```bash
npm test
npm run build:web
.venv/bin/python scripts/check-hxy-secrets.py
.venv/bin/python scripts/check-hxy-public-release.py
```

**Step 2: Record actual baseline**

Record test counts, adapter versions, known gaps, and whether any product output
changed. Do not claim an external-engine improvement before running the corpus.

**Step 3: Choose first isolated spike**

Select ModelGateway or parser/retrieval based on measured current failures. Do
not start DataAgent until operating data and metric contracts exist.

**Step 4: Commit and push**

```bash
git add docs/project-brain/roadmap/02-hxyos-2-component-benchmark-and-migration.md
git commit -m "docs: record engine port baseline"
git push origin feature/hxyos-engine-ports-v1
```
