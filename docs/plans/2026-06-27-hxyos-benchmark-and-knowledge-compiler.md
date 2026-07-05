# HXYOS Benchmark And Knowledge Compiler Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a falsifiable HXYOS foundation by creating a benchmark harness first, then implementing an LLM Wiki / OKF-style knowledge compiler that turns HXY materials into governed claims, evidence, wiki pages, and graph relations.

**Architecture:** The implementation keeps HXY business semantics inside `/root/hxy`. It adds deterministic compiler and benchmark modules under `apps/api/hxy_knowledge/`, CLI scripts under `scripts/`, generated knowledge artifacts under `knowledge/`, and tests under `tests/`. The first release must compare HXYOS against simpler baselines before claiming product value.

**Tech Stack:** Python standard library, pytest, existing HXY FastAPI modules, Markdown + YAML-like frontmatter, JSON artifacts, existing governance lint and answer pipeline.

---

## Constraints

- Do not read or write `/root/htops` business data.
- Do not use `HETANG_*` environment fallback.
- Generated HXY artifacts must stay under `knowledge/`, `docs/`, `data/`, or `tests/`.
- Raw uploaded materials are not approved knowledge.
- Process memory can only be context hint.
- All behavior changes require tests first.

## Target Files

- Create: `apps/api/hxy_knowledge/brain_benchmark.py`
- Create: `apps/api/hxy_knowledge/knowledge_compiler.py`
- Create: `scripts/run-hxy-brain-benchmark.py`
- Create: `scripts/compile-hxy-knowledge.py`
- Create: `tests/test_hxy_brain_benchmark.py`
- Create: `tests/test_hxy_knowledge_compiler.py`
- Create: `knowledge/benchmarks/hxy-brain-benchmark-v1.json`
- Create: `knowledge/wiki/README.md`
- Create: `knowledge/schema/hxy-wiki-page.schema.json`
- Modify: `apps/api/hxy_knowledge/enterprise_governance.py`
- Modify: `apps/api/hxy_knowledge_api.py`

## Phase 1: Benchmark First

### Task 1: Seed Golden Question Benchmark

**Files:**

- Create: `knowledge/benchmarks/hxy-brain-benchmark-v1.json`
- Test: `tests/test_hxy_brain_benchmark.py`

**Step 1: Write the failing test**

Test that the benchmark file loads and contains at least these fields for each case:

```python
def test_benchmark_cases_have_required_fields():
    from apps.api.hxy_knowledge.brain_benchmark import load_benchmark

    benchmark = load_benchmark("knowledge/benchmarks/hxy-brain-benchmark-v1.json")

    assert benchmark["version"] == "hxy-brain-benchmark.v1"
    assert len(benchmark["cases"]) >= 30
    for case in benchmark["cases"]:
        assert case["case_id"]
        assert case["question"]
        assert case["domain"]
        assert case["expected_capabilities"]
        assert case["risk_checks"]
        assert case["success_criteria"]
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_hxy_brain_benchmark.py::test_benchmark_cases_have_required_fields -v
```

Expected: FAIL because `brain_benchmark.py` does not exist.

**Step 3: Add benchmark loader**

Create `apps/api/hxy_knowledge/brain_benchmark.py` with:

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def load_benchmark(path: str | Path) -> dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if data.get("version") != "hxy-brain-benchmark.v1":
        raise ValueError("unsupported HXY benchmark version")
    if not isinstance(data.get("cases"), list):
        raise ValueError("benchmark cases must be a list")
    return data
```

**Step 4: Add seed benchmark file**

Create `knowledge/benchmarks/hxy-brain-benchmark-v1.json` with 30 cases across:

- Week 1 对外话术风险：禁用表达、员工推荐话术、客户高频问题、宣传审核标准
- Week 2 融资材料口径：投后估值 2000 万支撑逻辑、单店模型、门店进度、股权结构、品牌授权关系
- Week 3 经营判断：荷小悦是什么、核爆点定位、清泡调补养、当前战略判断
- 生命周期治理：参考资料、候选判断、核定知识、过程记忆边界
- 经营议题推进：阶段判断、动作闭环、证伪标准

Every case must include expected ability tags:

```json
["distinguish_reference_candidate_approved", "cite_evidence", "block_overclaim"]
```

as applicable.

Benchmark must explicitly include three compliance interception metrics:

```json
{
  "medicalized_expression_interception_rate": {"target": 1.0},
  "guaranteed_effect_interception_rate": {"target": 1.0},
  "exaggerated_marketing_interception_rate": {"target": 1.0}
}
```

**Step 5: Run test to verify it passes**

Run:

```bash
pytest tests/test_hxy_brain_benchmark.py::test_benchmark_cases_have_required_fields -v
```

Expected: PASS.

### Task 2: Add Scoring Rubric

**Files:**

- Modify: `apps/api/hxy_knowledge/brain_benchmark.py`
- Test: `tests/test_hxy_brain_benchmark.py`

**Step 1: Write the failing test**

```python
def test_score_answer_penalizes_unapproved_authority_and_overclaim():
    from apps.api.hxy_knowledge.brain_benchmark import score_answer

    case = {
        "case_id": "risk-001",
        "risk_checks": ["no_medical_claim", "must_distinguish_lifecycle"],
        "success_criteria": ["states_insufficient_if_unapproved"],
    }
    result = score_answer(
        case,
        {
            "answer": "荷小悦可以治疗失眠，资料里这么写所以可以对外说。",
            "evidence_statuses": ["reference"],
            "flags": [],
        },
    )

    assert result["passed"] is False
    assert "overclaim_risk" in result["failed_checks"]
    assert "unapproved_authority" in result["failed_checks"]
```

**Step 2: Run test to verify it fails**

Run:

```bash
pytest tests/test_hxy_brain_benchmark.py::test_score_answer_penalizes_unapproved_authority_and_overclaim -v
```

Expected: FAIL because `score_answer` is missing.

**Step 3: Implement minimal scoring**

Add deterministic scoring for:

- overclaim terms.
- evidence status not in `approved` / `action_asset`.
- missing insufficient-data flag when evidence is weak.
- missing citations.

Return:

```python
{
    "score": 0.0,
    "passed": False,
    "failed_checks": [...],
    "warnings": [...],
}
```

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_hxy_brain_benchmark.py -v
```

Expected: PASS.

### Task 3: CLI Benchmark Report

**Files:**

- Create: `scripts/run-hxy-brain-benchmark.py`
- Test: `tests/test_hxy_brain_benchmark.py`

**Step 1: Write failing CLI test**

Use `subprocess.run` to execute:

```bash
python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output knowledge/reports/benchmark-latest.json
```

Assert:

- exit code is 0.
- output JSON exists.
- report contains `case_count`, `pass_rate`, `failure_thresholds`.

**Step 2: Run test to verify it fails**

Expected: FAIL because script is missing.

**Step 3: Implement CLI**

The first CLI may score empty placeholder answers as failures. It is still valuable because it verifies the harness and failure reporting.

**Step 4: Run test to verify it passes**

Run:

```bash
pytest tests/test_hxy_brain_benchmark.py -v
```

Expected: PASS.

## Phase 2: Knowledge Compiler

### Task 4: Define HXY Wiki Page Schema

**Files:**

- Create: `knowledge/schema/hxy-wiki-page.schema.json`
- Create: `knowledge/wiki/README.md`
- Test: `tests/test_hxy_knowledge_compiler.py`

**Step 1: Write failing test**

Test that schema requires:

```text
id
type
title
domain
status
sources
confidence
owner
last_confirmed
used_by
risk_level
```

**Step 2: Run failing test**

Expected: FAIL because schema is missing.

**Step 3: Add schema and README**

Keep schema small and deterministic. It is a contract for compiler output, not a full product schema.

**Step 4: Run test**

Expected: PASS.

### Task 5: Compile Raw Material Into Structured Extract

**Files:**

- Create: `apps/api/hxy_knowledge/knowledge_compiler.py`
- Test: `tests/test_hxy_knowledge_compiler.py`

**Step 1: Write failing test**

```python
def test_compile_material_creates_reference_extract_not_approved():
    from apps.api.hxy_knowledge.knowledge_compiler import compile_material

    result = compile_material(
        {
            "asset_id": "asset-001",
            "title": "荷小悦定位讨论稿",
            "content": "荷小悦是社区轻养生品牌，主打泡脚和按摩。",
            "source_path": "knowledge/raw/inbox/positioning.md",
        }
    )

    assert result["status"] == "reference"
    assert result["memory_layer"] == "L1_structured_extract"
    assert result["sources"] == ["knowledge/raw/inbox/positioning.md"]
    assert result["official_use_allowed"] is False
```

**Step 2: Run failing test**

Expected: FAIL because compiler is missing.

**Step 3: Implement minimal compiler**

Implement deterministic extraction:

- stable id.
- title.
- domain inferred by conservative keywords.
- status `reference`.
- confidence default `0.5`.
- source path.
- official use blocked.

No LLM call in v1.

**Step 4: Run test**

Expected: PASS.

### Task 6: Generate Candidate Claims

**Files:**

- Modify: `apps/api/hxy_knowledge/knowledge_compiler.py`
- Test: `tests/test_hxy_knowledge_compiler.py`

**Step 1: Write failing test**

```python
def test_extract_claims_marks_them_current_candidate_and_requires_review():
    from apps.api.hxy_knowledge.knowledge_compiler import extract_candidate_claims

    claims = extract_candidate_claims(
        {
            "extract_id": "extract-001",
            "content": "荷小悦不是传统足疗店。清泡调补养用于表达产品体系。",
            "sources": ["source.md"],
        }
    )

    assert len(claims) == 2
    assert all(claim["status"] == "current_candidate" for claim in claims)
    assert all(claim["requires_human_review"] is True for claim in claims)
```

**Step 2: Run failing test**

Expected: FAIL.

**Step 3: Implement simple sentence-based claim extraction**

Use conservative Chinese sentence splitting. Do not create claims shorter than 8 characters.

**Step 4: Run test**

Expected: PASS.

### Task 7: Build Graph Relations

**Files:**

- Modify: `apps/api/hxy_knowledge/knowledge_compiler.py`
- Test: `tests/test_hxy_knowledge_compiler.py`

**Step 1: Write failing test**

Test that:

- claim has `supported_by` edge to evidence/source.
- wiki page has `belongs_to` edge to domain.
- risk claim can have `blocked_by` edge to risk rule.

**Step 2: Run failing test**

Expected: FAIL.

**Step 3: Implement `build_knowledge_graph`**

Return:

```python
{
    "version": "hxy-knowledge-graph.v1",
    "nodes": [...],
    "edges": [...],
}
```

Keep graph JSON file-friendly. Do not add Neo4j dependency.

**Step 4: Run test**

Expected: PASS.

### Task 8: Compiler CLI

**Files:**

- Create: `scripts/compile-hxy-knowledge.py`
- Test: `tests/test_hxy_knowledge_compiler.py`

**Step 1: Write failing test**

Run CLI against a temporary raw folder and assert outputs:

- `knowledge/wiki/index.md`
- `knowledge/wiki/graph.json`
- `knowledge/reports/compiler-latest.json`

**Step 2: Run failing test**

Expected: FAIL.

**Step 3: Implement CLI**

Inputs:

```bash
python scripts/compile-hxy-knowledge.py --raw-dir knowledge/raw/inbox --wiki-dir knowledge/wiki --report knowledge/reports/compiler-latest.json
```

Behavior:

- scan `.md` and `.txt` only in v1.
- create extracts and candidate claims.
- write graph.
- write report.
- never mark outputs approved.

**Step 4: Run test**

Expected: PASS.

## Phase 3: Governance Integration

### Task 9: Lint Compiler Outputs

**Files:**

- Modify: `apps/api/hxy_knowledge/enterprise_governance.py`
- Test: `tests/test_hxy_knowledge_compiler.py`

**Step 1: Write failing test**

Create a compiled wiki page missing sources and assert governance lint returns issue:

```text
wiki_missing_sources
```

Create an approved compiled page missing owner and assert release is blocked.

**Step 2: Run failing test**

Expected: FAIL.

**Step 3: Implement lint hooks**

Reuse existing issue format in `enterprise_governance.py`.

**Step 4: Run tests**

Expected: PASS.

### Task 10: Expose Benchmark And Compiler Status API

**Files:**

- Modify: `apps/api/hxy_knowledge_api.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Step 1: Write failing tests**

Add API tests for:

- `GET /api/v1/hxy/brain/benchmark`
- `GET /api/v1/hxy/knowledge/compiler/status`

Expected shape:

```json
{
  "version": "...",
  "summary": {...},
  "next_actions": [...]
}
```

**Step 2: Run failing tests**

Expected: FAIL.

**Step 3: Implement endpoints**

Endpoints read latest report JSON if present. If missing, return an empty state with recommended command.

**Step 4: Run tests**

Expected: PASS.

## Phase 4: Verification

### Task 11: Targeted Python Tests

Run:

```bash
pytest tests/test_hxy_brain_benchmark.py tests/test_hxy_knowledge_compiler.py tests/test_hxy_knowledge_api.py -v
```

Expected:

- all new tests pass.
- existing API tests still pass.

### Task 12: Full Test Suite

Run:

```bash
npm test
```

Expected:

- Python suite passes.
- Vitest suite passes.

### Task 13: Runtime Smoke

Run:

```bash
HXY_ENV_FILE=quarantine/env/hxy-postgres.env scripts/start-hxy-knowledge-api.sh --restart
curl -fsS http://127.0.0.1:18081/health
curl -fsS http://127.0.0.1:18081/api/v1/hxy/brain/benchmark
curl -fsS http://127.0.0.1:18081/api/v1/hxy/knowledge/compiler/status
```

Expected:

- health returns OK.
- benchmark and compiler endpoints return JSON.

## Acceptance Criteria

### Internal Criteria

- HXY has a benchmark file with at least 30 golden questions.
- HXY can generate a benchmark report with pass rate and failed checks.
- HXY can compile raw text/Markdown materials into reference extracts and candidate claims.
- Compiler output never becomes approved automatically.
- HXY can write `knowledge/wiki/graph.json`.
- Governance lint can block invalid approved wiki pages.
- API exposes benchmark and compiler status.
- Full tests pass.
- Benchmark pass rate is at least `0.85`.
- Medicalized expression interception rate is `100%`.
- Guaranteed effect expression interception rate is `100%`.
- Exaggerated marketing expression interception rate is `100%`.

### External Value Criteria

- At least 10 employee FAQ items have standard answers.
- At least 5 investor FAQ items have standard financing口径.
- At least 1 external marketing copy can be risk-checked automatically.
- At least 3 real users, covering employee / founder / operations owner, confirm the system is useful.

## Non-Goals

- No direct LLM calls in compiler v1.
- No Neo4j or external graph database.
- No production UI redesign in this plan.
- No automatic approval of HXY knowledge.
- No use of htops data.
