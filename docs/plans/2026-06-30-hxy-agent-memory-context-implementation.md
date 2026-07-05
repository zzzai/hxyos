# HXY Agent Memory Context Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build HXYOS memory context orchestration so every Agent receives the right working state, short-term context, formal knowledge, and process-memory hints without mixing process memory into authority answers.

**Architecture:** The first layer is a deterministic memory context policy in `apps/api/hxy_knowledge/memory_context.py`. It will later be wired into `hxy_knowledge_api.py`, `answer_pipeline.py`, and `KnowledgeRepository` so runtime answers assemble context through the same budget, retrieval, decay, and authority rules. Process memory remains context-only until a promotion workflow creates reviewed candidate claims and approved answer cards.

**Tech Stack:** Python standard library, FastAPI modules, PostgreSQL via existing repository, JSON payloads, existing answer pipeline and governance tests.

---

## Constraints

- Do not read or write `/root/htops` business data.
- Do not let `process_memory` become approved evidence.
- Do not store raw chat history as authoritative knowledge.
- Do not pass unlimited history or unlimited retrieval items into model prompts.
- Every runtime integration must keep answer cards and approved knowledge above process memory.

## Current Baseline

- `apps/api/hxy_knowledge/process_memory.py` creates governed process-memory records and promotion drafts.
- `apps/api/hxy_knowledge/answer_pipeline.py` already treats process memory as `context_draft`, not authority.
- `apps/api/hxy_knowledge/memory_context.py` now provides deterministic context assembly:
  - `Working Memory`
  - `Short-Term Memory`
  - `formal_knowledge`
  - `retrieval_evidence`
  - `process_memory_hints`
  - `blocked_memories`
  - `decay_score`
  - `hot / warm / cold`

## Task 1: Keep Policy Module Pure And Tested

**Files:**

- Modify: `apps/api/hxy_knowledge/memory_context.py`
- Test: `tests/test_hxy_memory_context.py`

**Steps:**

1. Add tests for each memory category:
   - approved answer card
   - reviewed SOP
   - process memory
   - reference material
   - conflicted memory
2. Verify `process_memory_hints[*].official_use_allowed` is always `False`.
3. Verify conflicted or superseded memories only appear in `blocked_memories`.
4. Verify `context_budget.context_overflow` is true when inputs exceed limits.
5. Run:

```bash
python3 -m unittest tests.test_hxy_memory_context -v
```

Expected: all tests pass.

## Task 2: Add Repository Retrieval Shape

**Files:**

- Modify: `apps/api/hxy_knowledge/repository.py`
- Test: `tests/test_hxy_knowledge_service.py`

**Steps:**

1. Add a repository method `memory_candidates(query, role, scenario, limit=20)`.
2. First implementation can combine:
   - approved answer cards from existing answer-card storage
   - process-memory records from review task payloads or future memory table
   - reference chunks from `hxy_knowledge_chunks`
3. Normalize every candidate into:

```python
{
    "memory_id": "...",
    "content": "...",
    "layer": "formal_knowledge | long_term_memory | reference",
    "status": "approved | process | reference | conflicted",
    "source_type": "...",
    "semantic_relevance": 0.0,
    "recency": 0.0,
    "importance": 0.0,
    "risk_level": "low | medium | high",
    "official_use_allowed": false
}
```

4. Test that candidates without status/source metadata are rejected or downgraded to reference.

## Task 3: Wire Memory Context Into Chat Runtime

**Files:**

- Modify: `apps/api/hxy_knowledge_api.py`
- Modify: `apps/api/hxy_knowledge/answer_pipeline.py`
- Test: `tests/test_hxy_knowledge_api.py`

**Steps:**

1. In `/api/knowledge/chat`, build `working_memory` from role, scenario, intent, remaining actions, and model route.
2. Retrieve memory candidates after intent classification and before answer generation.
3. Call `build_memory_context(...)`.
4. Add `memory_context` to saved answer payload and response inspector.
5. Ensure user-facing answer does not expose memory internals.
6. Verify answer pipeline still blocks process memory as authority.

## Task 4: Add Short-Term Summary Contract

**Files:**

- Create: `apps/api/hxy_knowledge/short_term_memory.py`
- Test: `tests/test_hxy_memory_context.py`

**Steps:**

1. Implement deterministic `summarize_short_term_messages(messages, max_chars=1200)`.
2. The summary should preserve:
   - current user goal
   - explicit constraints
   - decisions made in this session
   - unresolved questions
3. It must drop:
   - repeated frustration text
   - old implementation details not needed for current answer
   - raw chain-of-thought
4. This summary can enter Short-Term Memory; it is not formal knowledge.

## Task 5: Add Decay And Promotion Reporting

**Files:**

- Modify: `apps/api/hxy_knowledge/memory_context.py`
- Modify: `apps/api/hxy_knowledge/process_memory.py`
- Test: `tests/test_hxy_memory_context.py`

**Steps:**

1. Emit `promotion_candidates` when process memories are high-importance, high-reuse, and stable.
2. Emit `decay_actions`:
   - `cooldown`
   - `archive`
   - `conflict_review`
   - `promotion_review`
3. Never auto-promote to `approved`.
4. Promotion still routes through `build_memory_promotion_draft`.

## Task 6: Add Benchmark Cases

**Files:**

- Modify: `knowledge/benchmarks/hxy-brain-benchmark-v1.json`
- Modify: `apps/api/hxy_knowledge/brain_benchmark.py`
- Test: `tests/test_hxy_brain_benchmark.py`

**Steps:**

1. Add cases where:
   - process memory says one thing
   - approved answer card says another thing
   - correct answer follows approved answer card and mentions conflict/review
2. Add scoring checks:
   - `process_memory_not_authority`
   - `context_budget_present`
   - `conflict_goes_to_review`
3. Run:

```bash
python3 -m unittest tests.test_hxy_memory_context tests.test_hxy_brain_benchmark -v
```

Expected: all tests pass.

## Acceptance Criteria

- Runtime context always separates Working Memory, Short-Term Memory, Long-Term Memory, and Formal Knowledge.
- Process memory can influence style and reminders but cannot authorize factual/business claims.
- Context budget is visible in saved answer payloads.
- Conflict and stale memory produce review actions, not silent answers.
- Benchmark includes cases that would fail if process memory is treated as approved evidence.
