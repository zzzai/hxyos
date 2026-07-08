# HXY Harness Runner V1 Design

## Goal

Turn HXYOS development and knowledge-quality improvement from repeated chat commands into a governed autonomous loop.

The runner should let a human define:

- target;
- scope;
- constraints;
- verification commands;
- benchmark thresholds;
- stop conditions;
- forbidden actions.

The system then executes bounded development or knowledge-governance iterations and reports evidence after each round.

## Source Inspiration

This design is based on the Harness engineering pattern described in the WeChat article:

`https://mp.weixin.qq.com/s/c8BymWxcopweHr11u7zY-Q`

Key ideas adapted for HXYOS:

- humans define problems and acceptance;
- Agent executes, tests, analyzes failures, and iterates;
- all human-facing tools must have CLI/API equivalents;
- long-running tasks need anti-early-stop, anti-spin, context-budget, and retry-analysis rules;
- evaluation must defend against reward hacking;
- champion-challenger prevents strategy regression.

The article is treated as external engineering reference, not HXY official business knowledge.

## Product Definition

```text
HXY Harness Runner = a bounded autonomous execution loop for HXYOS engineering and AI-quality improvement.
```

It is not a general chat agent. It is a control surface for repeatable work:

- improve benchmark pass rate;
- improve Source Quality Gate classification;
- reduce compliance false negatives;
- improve answer pipeline citation quality;
- improve frontend workflow usability;
- run parser/ingest loops and summarize blockers.

## Non-Negotiable Boundaries

1. The runner must not approve official knowledge.
2. The runner must not import `topic-reviewed-assets.json` into formal stores.
3. The runner must not write HXY data into htops systems.
4. The runner must not modify `/root/htops`.
5. The runner must not publish private knowledge to GitHub.
6. The runner must not change VI/SI decisions owned by external designers.
7. The runner must stop at hard iteration limits.
8. The runner must report repeated failures instead of mechanical retry loops.

## V1 Use Cases

### 1. HXYOS Dev Loop

Input:

```text
target: benchmark pass_rate >= 0.85
scope: approved answer cards, citation, answer pipeline
stop: npm test green + benchmark threshold, or max 3 rounds
forbidden: auto approval, htops edits,招商主线, VI/SI changes
```

Output:

- per-round summary;
- changed files;
- test results;
- benchmark delta;
- unresolved blockers;
- final recommendation.

### 2. Source Quality Gate Loop

Input:

```text
target: source classification accuracy >= 0.85
scope: source identity cards, classification tests, source benchmark
stop: tests green + source benchmark threshold, or max 3 rounds
```

Output:

- classification confusion table;
- missed source classes;
- false authority promotions;
- next data needed.

### 3. Compliance Guardrail Loop

Input:

```text
target: medical/guaranteed-effect/overclaim blocking = 100%
scope: compliance rules and workflow gate
stop: tests green + compliance benchmark pass, or max 3 rounds
```

Output:

- blocked risky copy;
- safe rewrite coverage;
- false positives;
- unresolved review cases.

## Architecture

```text
Harness spec
-> run initialization
-> baseline capture
-> round loop
   -> plan round
   -> execute command set
   -> inspect test/benchmark output
   -> decide continue/stop
   -> persist round report
-> final report
```

V1 should be file-based and deterministic. It does not need a queue or distributed workflow engine yet.

## Core Objects

### Harness Spec

Path:

```text
knowledge/harness/specs/<run_name>.json
```

Fields:

```json
{
  "version": "hxy-harness-spec.v1",
  "run_name": "source-quality-gate-v1",
  "target": "source classification accuracy >= 0.85",
  "scope": ["apps/api/hxy_knowledge/ingest_loop.py", "tests/test_hxy_ingest_loop.py"],
  "max_rounds": 3,
  "verification_commands": [
    "npm test",
    ".venv/bin/python scripts/run-hxy-brain-benchmark.py --benchmark knowledge/benchmarks/hxy-brain-benchmark-v1.json --output knowledge/reports/harness-source-quality.json"
  ],
  "forbidden_paths": ["/root/htops"],
  "forbidden_actions": [
    "auto_approve_knowledge",
    "write_formal_knowledge_store",
    "commit_private_knowledge"
  ],
  "success_thresholds": {
    "npm_test": "pass",
    "benchmark_pass_rate": 0.85
  }
}
```

### Harness State

Path:

```text
knowledge/runs/<run_id>/harness-state.json
```

Fields:

```json
{
  "version": "hxy-harness-state.v1",
  "run_id": "harness-source-quality-20260708",
  "status": "running | succeeded | failed | blocked",
  "current_round": 1,
  "max_rounds": 3,
  "champion_commit": "ad666ef",
  "challenger_commit": "",
  "rounds": [],
  "stop_reason": ""
}
```

### Round Report

Path:

```text
knowledge/runs/<run_id>/round-<n>.json
```

Fields:

```json
{
  "version": "hxy-harness-round-report.v1",
  "round": 1,
  "goal": "improve source quality gate",
  "changed_files": [],
  "test_results": [],
  "benchmark_results": {},
  "failure_patterns": [],
  "decision": "continue | promote_challenger | stop_blocked | stop_failed",
  "next_action": ""
}
```

## Champion-Challenger Rule

The runner must not replace the current stable baseline just because one metric improved.

Promotion requires:

- full tests pass;
- benchmark threshold passes;
- no regression in protected metrics;
- no forbidden file/path changes;
- no private knowledge staged for commit;
- review report explains why improvement is general, not a case-specific hack.

If evidence is weak, challenger stays unpromoted.

## Anti Reward-Hacking Rule

HXY benchmarks should split into:

```text
training set: Agent can see question, expected checks, failure reasons.
validation set: Agent can see case id and score summary only.
hidden set: only humans or CI can run before promotion.
```

V1 can start with explicit benchmark metadata:

```json
{
  "visibility": "training | validation | hidden",
  "protected": true
}
```

The runner should fail promotion when changes add hard-coded answers for specific case ids, raw benchmark strings, or brittle one-case rules.

## Tooling Requirements

The following capabilities must be available as CLI/API, not only UI:

- run tests;
- run HXY brain benchmark;
- run source quality benchmark;
- run ingest loop;
- run parser jobs;
- run topic publication preflight/dry-run/import gate;
- run secret check;
- run public release check;
- inspect changed files;
- generate final report.

## Integration With HXY DataAgent

HXY DataAgent manages enterprise knowledge workflows.

Harness Runner improves the DataAgent itself:

```text
DataAgent = knowledge product runtime
Harness Runner = controlled self-improvement loop
```

Examples:

- DataAgent misclassifies reference material as candidate authority.
- Benchmark captures this as a failure.
- Harness Runner iterates on Source Quality Gate rules.
- Champion-challenger decides whether to promote the improvement.

## V1 Implementation Strategy

Do not build a full orchestrator first.

Start with:

- file-based specs;
- Python runner;
- round reports;
- strict shell command allowlist;
- test and benchmark parsing;
- no automatic code generation inside the runner.

The first version coordinates existing commands and reports evidence. Agent-driven code changes can be performed by Codex outside the runner, using the runner as the verification harness.

## Acceptance Criteria

1. A harness spec can describe target, scope, commands, forbidden paths/actions, max rounds, and thresholds.
2. A dry-run command validates the spec and refuses unsafe configuration.
3. A runner command executes allowed verification commands and writes a state/report file.
4. The runner enforces max rounds and repeated-failure stop conditions.
5. The runner never approves official knowledge or writes formal knowledge stores.
6. Tests cover safe spec validation, unsafe path rejection, command allowlist enforcement, and report output.
7. `npm test` passes.
8. HXY benchmark pass rate remains `>= 0.85`.

## Open Questions

1. Should V1 execute code-editing commands, or only verify changes made by Codex?

   Recommendation: only verify/report in V1. Let Codex perform edits through the existing development workflow.

2. Should hidden benchmark cases exist in the local repo?

   Recommendation: keep hidden cases local only, excluded from public release.

3. Should Harness Runner run inside the API service?

   Recommendation: no for V1. Use CLI first; expose read-only status to the web console later.
