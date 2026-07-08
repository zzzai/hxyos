# HXY Core Knowledge Topic Layer

## Problem

The ingest loop can produce a very large number of candidate claims. That is acceptable as a machine intermediate, but it is not a useful human review object for HXY.

HXY is still in the first-store, 0-1 validation stage. The highest-value knowledge is not a broad claim queue. It is a small set of business-critical judgments:

- brand strategy;
- nuclear positioning;
- customer evidence;
- product and service system;
- employee executable scripts;
- compliance risk boundaries;
- first-store opening actions.

## Product Rule

Candidate claim extraction remains internal infrastructure.

Humans should review `core_decision_topics`, not raw claims.

```text
raw material
-> machine extracts
-> candidate claims
-> claim triage
-> core decision topics
-> human review
-> decision card / positioning card / script card / SOP card / risk card
```

## Implementation

The compiler now writes:

- `knowledge/wiki/core-decision-topics.json`
- `core_decision_topic_count`
- `human_review_object: core_decision_topics`

The review topics API now prefers `core-decision-topics.json` when present:

```text
GET /api/operating-brain/knowledge-compiler/review-topics
```

If no core topic artifact exists, the endpoint falls back to the older claim-triage aggregation.

## Boundary

Core decision topics are still not approved knowledge.

They are review objects. They cannot be cited as authority until manually converted into approved positioning cards, script cards, SOP cards, or risk boundary cards.
