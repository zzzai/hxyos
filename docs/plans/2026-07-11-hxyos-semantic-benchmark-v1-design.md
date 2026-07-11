# HXYOS Semantic Benchmark V1 Design

## Status

Approved for implementation on 2026-07-11.

## Purpose

The contract baseline proves engine safety boundaries. It does not prove that
HXYOS gives a correct, useful, role-appropriate answer. Semantic Benchmark V1
adds that missing evidence without allowing a model to certify its own output.

The governing principle is:

```text
deterministic checks cover every case
+ human blind review calibrates meaning
+ model judging is advisory only
```

## Alternatives Considered

### Deterministic rules only

Cheap and reproducible, but cannot judge whether an answer understands the
business problem or gives a useful next action.

### LLM judge only

Highly automated, but vulnerable to self-preference, prompt sensitivity,
provider drift, and false precision.

### Hybrid evaluation

Selected. Deterministic gates remain authoritative for measurable properties.
Humans establish the semantic calibration truth. A judge model may later reduce
review effort only after measured agreement with the human sample.

## Scope

V1 evaluates the existing 50-case, five-role Engine Benchmark corpus:

- founder;
- brand operations;
- store manager;
- store employee;
- knowledge/data administrator.

It adds evaluation artifacts beside the existing corpus instead of changing the
contract baseline result.

V1 does not:

- publish or approve knowledge;
- write production conversations;
- call production mutation endpoints;
- use private source content in tracked reports;
- promote an external engine;
- claim semantic quality before human calibration is complete.

## Evaluation Inputs

### Answer run

Every provider exports the same bounded record:

```text
case_id
provider name/version
answer text (private evaluation artifact)
evidence IDs and authority states
citations
policy action
guardrail action
latency and usage
safe trace metadata
```

Raw answer text remains in a private run artifact. Tracked reports contain only
case IDs, scores, reason codes, hashes, bounded usage, and safe metadata.

### Semantic rubric

Each case receives five dimensions scored from 1 to 5:

1. factual correctness;
2. role usefulness;
3. evidence alignment;
4. expression fitness;
5. actionability.

The rubric also records case-specific required outcomes from
`minimum_useful_outcome`. Missing a required outcome is visible separately and
cannot be hidden by a high style score.

## Deterministic Evaluation

All 50 cases are checked for:

- authorized evidence only;
- one authority state per returned evidence item;
- required citations;
- explicit insufficiency when evidence is incomplete;
- prohibited medical, guaranteed-effect, and exaggerated expressions;
- private path, credential, session, and internal-field leakage;
- required outcome markers;
- latency, token, and cost budgets.

Hard safety failures are never averaged away by semantic scores.

## Human Calibration

The calibration sample contains ten cases, stratified as two per role and
versioned by case ID. Two reviewers score independently without seeing provider,
model, token cost, or the other reviewer's scores.

Disagreement handling:

- a dimension difference of zero or one is accepted and averaged;
- a difference above one requires adjudication;
- incomplete reviews keep the benchmark in `awaiting_human_calibration`;
- reviewer identities are represented by non-sensitive reviewer IDs.

## Advisory Model Judge

The judge receives the question, bounded evidence summary, required outcomes,
rubric, and answer. It does not receive the provider/model identity.

Its output is stored separately as advisory evidence. It cannot change hard
gates, human scores, approval state, or `quality_claim_allowed`.

Judge automation may be considered only after agreement is measured against the
human sample. V1 records agreement; it does not set an automatic trust threshold.

## Report States

```text
not_evaluated
deterministic_only
awaiting_human_calibration
human_calibrated
```

`quality_claim_allowed` remains false in V1, including after calibration. A
future decision may introduce a release-quality claim after thresholds and
business acceptance are separately approved.

## Outputs

```text
knowledge/benchmarks/hxy-semantic-rubric-v1.json
knowledge/benchmarks/hxy-semantic-calibration-v1.json
knowledge/benchmarks/hxy-semantic-review-v1.schema.json
scripts/build-hxy-semantic-review-pack.py
scripts/run-hxy-semantic-benchmark.py
apps/api/hxy_engines/semantic_benchmark.py
tests/test_hxy_semantic_benchmark.py
```

Generated private answer and review packs are excluded from public release.
Tracked sample/report artifacts contain synthetic or bounded metadata only.

## Acceptance Criteria

- all 50 cases receive deterministic results;
- the calibration set contains exactly two cases per role;
- a no-op or incomplete answer provider cannot pass;
- hard safety failures cannot be offset by semantic scores;
- incomplete or disagreeing human reviews are explicit;
- model-judge output remains advisory;
- no tracked report contains answer text, private paths, credentials, or session
  material;
- existing contract baseline and product tests remain green.
