# HXYOS Semantic Benchmark V1 Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add governed semantic evaluation for the 50 role cases using deterministic structural preflight, a ten-case identity-masked review pack, and strictly advisory model-judge results.

**Architecture:** Keep the contract runner unchanged and add a separate semantic evaluator. Private answer text and completed reviews live under ignored `knowledge/runs/`; tracked artifacts contain only bounded IDs, hashes, scores, reason codes, and safe metadata. Hard gates and human reviews are authoritative; model-judge output cannot change benchmark state or quality claims.

**Tech Stack:** Python 3.12 dataclasses and standard library, JSON/JSON Schema, pytest, existing HXY benchmark and compliance rules.

---

### Task 1: Build Versioned Rubric And Calibration Catalogs

**Files:**
- Create: `scripts/build-hxy-semantic-benchmark-v1.py`
- Create: `knowledge/benchmarks/hxy-semantic-rubric-v1.json`
- Create: `knowledge/benchmarks/hxy-semantic-calibration-v1.json`
- Test: `tests/test_hxy_semantic_benchmark_catalog.py`

**Step 1: Write the failing catalog test**

Assert that the rubric contains all 50 case IDs and five dimensions, while the
calibration catalog contains exactly two deterministic cases per role. Rebuilding
must return byte-equivalent payloads. Neither catalog may contain private paths,
credentials, answers, or session material.

```python
assert rubric["version"] == "hxy-semantic-rubric.v1"
assert len(rubric["cases"]) == 50
assert calibration["version"] == "hxy-semantic-calibration.v1"
assert len(calibration["case_ids"]) == 10
```

**Step 2: Run to verify RED**

```bash
.venv/bin/pytest tests/test_hxy_semantic_benchmark_catalog.py -q
```

Expected: FAIL because builder and catalogs do not exist.

**Step 3: Implement the builder**

Load `hxy-engine-benchmark-v1.json`. For every case emit only `case_id`, `role`,
`required_outcomes`, `risk_expectations`, and these dimensions:

```text
factual_correctness
role_usefulness
evidence_alignment
expression_fitness
actionability
```

Select the first and last case in each role group for calibration. Record the
source benchmark SHA-256 in both outputs.

**Step 4: Generate and verify GREEN**

```bash
.venv/bin/python scripts/build-hxy-semantic-benchmark-v1.py
.venv/bin/pytest tests/test_hxy_semantic_benchmark_catalog.py -q
```

**Step 5: Commit**

```bash
git add scripts/build-hxy-semantic-benchmark-v1.py knowledge/benchmarks/hxy-semantic-*.json tests/test_hxy_semantic_benchmark_catalog.py
git commit -m "test: add semantic benchmark catalogs"
```

### Task 2: Add Answer-Run Contract And Deterministic Evaluator

**Files:**
- Create: `apps/api/hxy_engines/semantic_benchmark.py`
- Create: `knowledge/benchmarks/hxy-semantic-answer-run-v1.schema.json`
- Test: `tests/test_hxy_semantic_benchmark.py`

**Step 1: Write failing evaluator tests**

Cover:

```python
def test_noop_answer_run_fails_all_cases(): ...
def test_hard_safety_failure_cannot_be_averaged_away(): ...
def test_authorized_citations_and_authorities_pass(): ...
def test_unknown_evidence_and_private_trace_are_redacted(): ...
def test_required_outcome_declarations_are_complete(): ...
def test_report_never_contains_answer_text(): ...
```

The no-op provider must produce `deterministic_pass_count == 0`. A record with a
perfect advisory score but a medical claim must still fail.

**Step 2: Run to verify RED**

```bash
.venv/bin/pytest tests/test_hxy_semantic_benchmark.py -q
```

Expected: missing `hxy_engines.semantic_benchmark`.

**Step 3: Implement bounded contracts**

Create frozen `SemanticAnswerRun` with case/provider IDs, private answer text,
evidence IDs and authorities, citations, declared outcomes, policy and guardrail
actions, bounded usage, and safe trace metadata. Reject unknown authorities and
negative usage. Never serialize answer text.

**Step 4: Implement deterministic scoring**

Derive requirements from each benchmark case, never from provider claims:

- non-empty answer hash;
- only case evidence IDs;
- one authority per evidence item;
- citations for returned evidence;
- complete, case-bounded outcome declaration coverage;
- current compliance-rule detection;
- no private or technical markers;
- latency/token/cost budgets.

Hard failures cannot be averaged away. Always return
`quality_claim_allowed=False`.

**Step 5: Run and commit**

```bash
.venv/bin/pytest tests/test_hxy_semantic_benchmark.py -q
git add apps/api/hxy_engines/semantic_benchmark.py knowledge/benchmarks/hxy-semantic-answer-run-v1.schema.json tests/test_hxy_semantic_benchmark.py
git commit -m "feat: add deterministic semantic evaluator"
```

### Task 3: Add Human Masked-Review Calibration

**Files:**
- Create: `knowledge/benchmarks/hxy-semantic-review-v1.schema.json`
- Modify: `apps/api/hxy_engines/semantic_benchmark.py`
- Test: `tests/test_hxy_semantic_review.py`

**Step 1: Write failing review tests**

```python
def test_incomplete_reviews_keep_awaiting_state(): ...
def test_two_reviews_per_case_complete_calibration(): ...
def test_dimension_gap_above_one_requires_adjudication(): ...
def test_blind_pack_exposes_no_provider_identity(): ...
def test_advisory_judge_cannot_change_human_or_hard_gates(): ...
```

**Step 2: Run to verify RED**

```bash
.venv/bin/pytest tests/test_hxy_semantic_review.py -q
```

**Step 3: Implement validation and agreement**

Each review has bounded reviewer/case IDs, answer and displayed-text hashes,
five integer scores from 1 to 5, and optional reason codes. Two distinct review
files are mandatory. A dimension difference above one requires adjudication;
offline reviewer IDs do not prove identity independence.

```text
missing or disagreeing reviews -> awaiting_human_calibration
two accepted files for all ten cases -> review_files_complete_unverified
```

Judge scores remain a separate advisory section.

**Step 4: Run and commit**

```bash
.venv/bin/pytest tests/test_hxy_semantic_review.py -q
git add knowledge/benchmarks/hxy-semantic-review-v1.schema.json apps/api/hxy_engines/semantic_benchmark.py tests/test_hxy_semantic_review.py
git commit -m "feat: add blind review calibration"
```

### Task 4: Add Private Masked Review Pack And Semantic CLI

**Files:**
- Create: `scripts/build-hxy-semantic-review-pack.py`
- Create: `scripts/run-hxy-semantic-benchmark.py`
- Test: `tests/test_hxy_semantic_benchmark_cli.py`

**Step 1: Write failing CLI tests**

Assert that the private review pack includes question, answer, bounded evidence
summary and rubric, but no provider/model identity. Reports must contain no
answer text or private paths. Missing cases must fail rather than disappear.
Incomplete reviews produce `awaiting_human_calibration`. Incomplete 50-case
corpora are rejected.

**Step 2: Run to verify RED**

```bash
.venv/bin/pytest tests/test_hxy_semantic_benchmark_cli.py -q
```

**Step 3: Implement review-pack builder**

Default output is ignored
`knowledge/runs/semantic-benchmark/<run-id>/review-pack.json`. Refuse output
inside tracked `knowledge/benchmarks/`. Use a recorded deterministic shuffle
seed and omit provider/model identity.

**Step 4: Implement benchmark CLI**

Support `--benchmark`, `--rubric`, `--answers`, optional `--reviews`, optional
`--judge-results`, and `--output`. Invoke the complete existing corpus validator,
write atomically, and print only a report basename/ID rather than an absolute
path. A measured low score is a successful measurement; malformed input exits
non-zero.

**Step 5: Run and commit**

```bash
.venv/bin/pytest tests/test_hxy_semantic_benchmark_cli.py -q
git add scripts/build-hxy-semantic-review-pack.py scripts/run-hxy-semantic-benchmark.py tests/test_hxy_semantic_benchmark_cli.py
git commit -m "feat: add semantic benchmark cli"
```

### Task 5: Record Framework State And Verify

**Files:**
- Modify: `docs/project-brain/roadmap/02-hxyos-2-component-benchmark-and-migration.md`
- Create: `knowledge/benchmarks/results/hxy-current-semantic-baseline.json` only when it contains no answer text or private metadata

**Step 1: Generate a bounded framework result**

Use synthetic answer fixtures only to verify mechanics. State must remain
`deterministic_only` or `awaiting_human_calibration`, with
`quality_claim_allowed=false`. Do not call it current product quality. If there
is no real read-only answer export, record the product baseline as pending.

**Step 2: Update roadmap truthfully**

Record executable capabilities, uncalibrated work, rules version/digest, and
that no external engine is promoted.

**Step 3: Run full verification**

```bash
npm test
npm run build:web
.venv/bin/python scripts/check-hxy-secrets.py
.venv/bin/python scripts/check-hxy-public-release.py
.venv/bin/python scripts/validate-hxy-engine-benchmark.py --require-complete knowledge/benchmarks/hxy-engine-benchmark-v1.json
git diff --check
```

**Step 4: Request review and fix Critical/High findings**

Review privacy, false quality claims, case-derived gates, human-state logic, and
judge isolation.

**Step 5: Commit and push**

```bash
git add docs/project-brain/roadmap/02-hxyos-2-component-benchmark-and-migration.md knowledge/benchmarks/results/hxy-current-semantic-baseline.json
git commit -m "docs: record semantic benchmark framework baseline"
git push origin feature/hxyos-engine-ports-v1
```
