# HXY Loop Engine Runner Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a bounded local loop runner that can repeatedly execute HXY knowledge workflows, evaluate measurable results, stop deterministically, and persist run state.

**Architecture:** The runner is a small Python module under `apps/api/hxy_knowledge/` plus a CLI wrapper under `scripts/`. It starts with one supported loop, `compile_knowledge`, which calls the existing knowledge compiler, reads its report, evaluates thresholds, and writes a durable loop state file under `knowledge/runs/<run-id>/loop-state.json`.

**Tech Stack:** Python standard library, existing HXY knowledge compiler, pytest.

---

## Product Boundary

This runner is an automation harness for repeatable project work. It is not an autonomous business decision maker.

It may:

- run approved local workflows
- evaluate measurable outputs
- retry within hard limits
- write run state and reports
- propose next actions

It must not:

- approve answer cards
- promote candidate claims to official knowledge
- change brand, price, medical, investment, or franchise口径 without human review
- call arbitrary shell commands
- write HXY data into `/root/htops`

## Loop Contract

Each run persists:

```json
{
  "version": "hxy-loop-runner-state.v1",
  "loop_name": "compile_knowledge",
  "run_id": "knowledge-loop-latest",
  "goal": {
    "text": "Compile HXY reference materials into governed review artifacts.",
    "measurable_target": "review_queue_count >= 20 and answer_card_draft_count >= 10"
  },
  "context_budget": {
    "raw_dir": "knowledge/raw/inbox",
    "wiki_dir": "knowledge/wiki",
    "max_iterations": 2
  },
  "iterations": [],
  "status": "passed | failed | stopped",
  "stop_reason": "target_met | max_iterations_reached | evidence_insufficient | command_failed"
}
```

## Task 1: Add Failing Tests

**Files:**

- Create: `tests/test_hxy_loop_engine.py`
- Create later: `apps/api/hxy_knowledge/loop_engine.py`
- Create later: `scripts/run-hxy-loop.py`

**Step 1: Test target-met behavior**

Create a temporary raw directory with a minimal reference file that the existing compiler can process. Run the loop with low thresholds and assert:

- state version is `hxy-loop-runner-state.v1`
- status is `passed`
- stop reason is `target_met`
- iteration count is at least 1
- a loop-state file is written

**Step 2: Test hard stop behavior**

Run the loop with impossible thresholds and `max_iterations=1`. Assert:

- status is `failed`
- stop reason is `max_iterations_reached`
- exactly 1 iteration is recorded

**Step 3: Test CLI behavior**

Invoke `scripts/run-hxy-loop.py compile_knowledge` with temp paths. Assert stdout returns JSON with:

- version `hxy-loop-runner-cli.v1`
- loop state path
- final status

Run:

```bash
PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_loop_engine.py -q
```

Expected before implementation: failing import or missing script.

## Task 2: Implement Loop Engine

**Files:**

- Create: `apps/api/hxy_knowledge/loop_engine.py`

Implement:

- `LoopGoal`
- `LoopThresholds`
- `CompileKnowledgeLoopConfig`
- `run_compile_knowledge_loop(config)`

Behavior:

- call `compile_directory(raw_dir, wiki_dir)`
- write compiler public report to `report_path`
- call `write_harness_run` for per-phase artifacts
- evaluate `review_queue_count`, `answer_card_draft_count`, and `claim_count`
- repeat until target is met or `max_iterations` is reached
- write `loop-state.json`

## Task 3: Add CLI

**Files:**

- Create: `scripts/run-hxy-loop.py`

Supported first command:

```bash
python3 scripts/run-hxy-loop.py compile_knowledge \
  --raw-dir knowledge/raw/inbox \
  --wiki-dir knowledge/wiki \
  --report knowledge/reports/compiler-latest.json \
  --run-id knowledge-loop-latest \
  --runs-dir knowledge/runs \
  --min-review-queue 20 \
  --min-answer-card-drafts 10 \
  --max-iterations 2
```

The CLI only exposes allowlisted loop types. It does not accept arbitrary shell commands.

## Task 4: Verify

Run focused tests:

```bash
PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_loop_engine.py -q
```

Run broader Python tests touched by the workflow:

```bash
PYTHONPATH=/root/hxy/apps/api pytest tests/test_hxy_loop_engine.py tests/test_hxy_knowledge_compiler.py -q
```

Run the real loop:

```bash
python3 scripts/run-hxy-loop.py compile_knowledge \
  --raw-dir knowledge/raw/inbox \
  --wiki-dir knowledge/wiki \
  --report knowledge/reports/compiler-latest.json \
  --run-id knowledge-loop-latest \
  --runs-dir knowledge/runs \
  --min-review-queue 20 \
  --min-answer-card-drafts 10 \
  --max-iterations 2
```

Expected current result:

- final status `passed`
- stop reason `target_met`
- no approved knowledge is created automatically

## Later Loops

After the first runner is stable, add separate loop types:

- `benchmark_improvement`: run benchmark, identify failed cases, create correction tasks
- `review_queue_triage`: batch classify review queue, never approve
- `answer_card_quality`: score draft cards for evidence, compliance, and clarity
- `frontend_regression`: run UI tests and screenshot checks
