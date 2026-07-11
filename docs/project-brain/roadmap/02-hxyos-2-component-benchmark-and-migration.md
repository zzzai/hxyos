# HXYOS 2.0 Component Benchmark And Migration

## Purpose

This roadmap prevents architecture changes driven by feature lists, stars, or a
single impressive demo. Every external engine competes against the current HXY
baseline through the same adapter contract and role-scoped task set.

## Decision Funnel

```text
paper fit
-> isolated spike
-> offline benchmark
-> security and governance gate
-> shadow traffic
-> role canary
-> promoted adapter
-> monitored rollback window
```

No candidate skips a stage because it is from a major vendor or has a mature UI.

## Hard Gates

A candidate is rejected immediately when any condition occurs:

- cross-assignment or cross-store evidence leakage;
- reference/process memory presented as approved authority;
- chat or upload mutates core knowledge;
- raw credentials or private paths reach the client;
- production data requires write credentials for analysis;
- engine failure blocks HXYOS without fallback;
- license or export terms prevent the intended deployment;
- employees must configure models, prompts, indexes, or providers.

## Benchmark Corpus

The first benchmark contains 50 bounded tasks:

| Role | Tasks | Primary value |
|---|---:|---|
| founder | 10 | project status, strategic evidence, decision trace |
| brand/operations | 10 | approved expression, content risk, opening execution |
| store manager | 10 | tasks, SOP, exception handling, daily review |
| employee | 10 | customer response, service practice, upload/feedback |
| knowledge/data admin | 10 | source quality, conflicts, metrics, engine diagnostics |

Each task includes:

- identity and assignment;
- allowed and forbidden evidence;
- expected authority status;
- risk expectations;
- minimum useful action;
- latency and cost budget;
- deterministic leakage assertions.

## Metrics

### Hard metrics

- unauthorized evidence exposure: `0`;
- authority-state violations: `0`;
- prohibited medical/guaranteed-outcome misses: `0`;
- destructive or unapproved writes: `0`;
- source links outside authorized scope: `0`.

### Comparative metrics

- end-to-end task success;
- evidence recall and citation correctness;
- user steps and time to useful result;
- p50/p95 latency;
- model tokens and total variable cost;
- operator effort per 100 sources/tasks;
- failure recovery and rollback time;
- deployment and upgrade burden.

A candidate must pass every hard metric and either improve task success
materially or reduce cost/operating effort materially without degrading quality.

## Component Order

### P0: Contract And Current Baseline

1. Freeze canonical identity, knowledge authority, material, conversation, and
   trace contracts.
2. Record the current product result for all benchmark tasks.
3. Add engine name/version, policy version, latency, and cost to trace output.

### P1: ModelGateway Spike

Compare current routing with LiteLLM or an equivalent gateway for:

- provider fallback;
- per-role/model budget;
- usage accounting;
- key isolation;
- compatible streaming and structured output.

### P1: Parser And Retrieval Spike

Compare the current parser/retrieval path with RAGFlow and selected parser
adapters using difficult HXY PDFs, Office files, tables, scans, and Chinese text.

Do not import RAGFlow knowledge status or user model into HXYOS.

### P2: AgentRuntime Boundary

Move one bounded workflow behind an `AgentRuntime` contract. Use LangGraph only
where stateful reasoning, tool use, or interruption adds measured value.

Introduce Temporal only when a workflow must survive process restarts, wait for
humans, retry over long periods, or run on schedules.

### P2: Observability

Emit OpenTelemetry traces and evaluate Langfuse for model/prompt/evaluation
views. HXYOS remains the canonical audit owner.

### P3: AnalyticsEngine Spike

Start only after stable operating data and metric definitions exist.

DataAgent receives:

- a read-only replica or analytics database;
- explicit table/row/column scope;
- HXY metric contracts and semantic definitions;
- SELECT-only AST policy, timeout, row limit, and PII masking.

Its output returns to HXYOS as an analysis artifact. Employees do not use a
second DataAgent front end.

### Optional: Expert Client

Cherry Studio may call governed HXYOS APIs/MCP for founder or specialist use.
It never receives direct database, model-provider, or canonical knowledge
credentials and is not required for mobile/store workflows.

## Rollout And Rollback

Each promoted adapter keeps:

- the previous adapter available during a bounded rollback window;
- versioned configuration outside canonical business data;
- a rebuild/export procedure;
- health, timeout, and circuit-breaker behavior;
- benchmark evidence attached to the architecture decision.

## Immediate Next Deliverable

Create the HXYOS Engine Port V1 package containing typed contracts for:

```text
ModelGateway
DocumentParser
RetrievalEngine
AgentRuntime
AnalyticsEngine
MemoryAdapter
ChannelAdapter
```

The first implementation wraps current behavior. External engines are not
introduced until the baseline adapter passes existing tests and the 50-task
benchmark schema exists.

## Engine Ports V1 Baseline Record

Recorded on 2026-07-11 from branch `feature/hxyos-engine-ports-v1`.

Implemented:

- immutable `EngineContext`, budget, artifact, usage, policy, and result contracts;
- current `ModelRouter` behind `ModelGateway` without changing model execution;
- current MarkItDown/MinerU runner behind `DocumentParser`;
- permission-first current retrieval adapter with account/assignment/
  organization/store context;
- bounded engine descriptor, benchmark JSON Schema, five-role sample, and
  dependency-free validator;
- complete mode requires exactly 50 cases and 10 cases per role.

Verification evidence:

```text
Python: 774 passed, 2 skipped
TypeScript: 52 passed
Web: 33 passed
Playwright: 6 passed
Web production build: passed
secret scan: passed
public-release scan: passed
complete 50-case benchmark validation: passed
current contract baseline: 50 passed, 0 failed
```

Interpretation:

- Product behavior has a tested baseline behind replaceable ports.
- No external engine has been promoted.
- The sample proves contract validation, not engine quality.
- The 50-case, five-role corpus and complete-mode structural validation are now
  present.

## Executable Contract Baseline

The deterministic current-engine contract baseline is recorded at:

```text
knowledge/benchmarks/results/hxy-current-contract-baseline.json
```

Result on 2026-07-11:

```text
cases: 50
contract passed: 50
contract failed: 0
contract pass rate: 1.0
semantic status: not_evaluated
quality claim allowed: false
```

The runner executes the current permission-first retrieval adapter and the
current compliance rules. It verifies assignment/store scope and aggregate-read
permission denial before a repository containing forbidden probe IDs can be
accessed, engine authority boundaries, prohibited-expression pattern detection,
absence of writes in the tested retrieval path, trace privacy, and case budgets.
The report records the benchmark digest, checker/rules versions, and the loaded
rules digest. It does not call a model, verify the full external-publication
blocking path, or score the usefulness, correctness, or citation quality of
generated role answers.

Interpretation:

- the current adapters have a reproducible governance-contract baseline;
- the loaded compliance rules still report `candidate_rules`, which is visible
  in the baseline report and is not promoted by this run;
- semantic product quality remains unmeasured by this result;
- this result cannot be presented as a product-quality pass rate;
- no external engine may be promoted from this result alone;
- the next benchmark increment must independently score real role answers
  before LiteLLM, RAGFlow, DataAgent, or another candidate is compared.

## Semantic Benchmark V1 Framework

Recorded on 2026-07-11 from branch `feature/hxyos-engine-ports-v1`.

Implemented:

- a 50-case semantic rubric derived from the versioned role corpus;
- a ten-case calibration set with two cases per role;
- a private answer-run contract whose answer text is never emitted in tracked
  reports;
- structural preflight checks for evidence scope, rubric-owned authority,
  citations, lifecycle-aware delivery policy, required outcome declarations,
  compliance patterns, trace privacy, and budgets;
- two-review-file identity-masked calibration with answer/review-text hashes,
  explicit disagreement/adjudication state, unverified identity redaction, and
  unverified reviewer provenance;
- advisory judge isolation: judge scores cannot change hard gates, human state,
  or `quality_claim_allowed`;
- a private identity-masked review-pack builder and complete-corpus semantic CLI.

The public-safe framework report is:

```text
knowledge/benchmarks/results/hxy-semantic-framework-baseline.json
```

Framework no-op result:

```text
cases: 50
answer runs: 0
structural preflight passed: 0
structural preflight failed: 50
semantic status: awaiting_human_calibration
verified human calibrated cases: 0 / 10
quality claim allowed: false
```

Interpretation:

- this proves that an empty provider cannot obtain a semantic pass;
- structural preflight is explicitly not a semantic-quality metric; generic or
  weak answers can only be judged by the bound human review stage;
- this is a framework verification result, not current HXYOS answer quality;
- the current product semantic baseline remains pending until a governed,
  read-only export of 50 real role answers exists;
- review-file completion requires two submissions for all ten selected cases;
- `human_calibrated` remains reserved until reviewer identities and assignments
  come from an authenticated organization boundary;
- no external engine may be compared or promoted on semantic quality yet.
