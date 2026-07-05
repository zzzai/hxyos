# HXY Reference Material Governance Design

## Decision

Current HXY materials are reference materials, not approved brand truth.

The operating brain must use large models to organize, compare, extract, and draft, but it must not treat uploaded or historical documents as final answers until a human owner approves them.

## Knowledge Lifecycle

```text
reference
  Raw or historical material. Useful for extraction and comparison only.

ai_structured
  Model-extracted candidate knowledge, questions, conflicts, answer-card drafts, or training-card drafts.

needs_review
  Candidate knowledge with conflicts, weak evidence, risky language, unclear ownership, or business-critical impact.

approved
  Human-approved answer card, training card, policy, or brand statement. This is the only status that can answer as authority.

superseded
  Previously useful knowledge replaced by a newer approved version.
```

## Product Rule

If the system only has reference material, it must not present the output as a final standard answer.

It should instead return a structured draft:

- current draft conclusion
- evidence used
- uncertainty and conflict notes
- questions for human review
- suggested answer-card draft
- recommended reviewer

## Model Role

Large models are used for:

- classifying documents
- extracting candidate claims
- finding contradictions
- generating golden questions
- drafting answer cards
- drafting training cards
- checking risky language
- proposing review tasks

Large models are not used to override approved HXY answer cards.

## Answer Rule

```text
approved answer card hit
  -> answer directly, no model override

reference-only evidence
  -> return "未核定梳理稿", mark needs_review, create draft/review actions

conflicting evidence
  -> do not answer as fact, create conflict review task

risky domains: positioning, price, efficacy, revenue, policy
  -> require review unless an approved card exists
```

## Immediate Implementation Scope

This iteration changes the answer pipeline and repository semantics only.

It does not build a full document ingestion UI, does not migrate quarantined raw data back into git, and does not create customer consumption data flows.
