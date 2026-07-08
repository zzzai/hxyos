# HXYOS DataAgent Console V1

## Goal

Turn the HXYOS default entry from a loose set of pages into a DataAgent-style operating console:

```text
Front stage: one question box + scenario workflows
Middle platform: knowledge engine, retrieval apps, Skill, Agent, memory
Back office: review, permissions, versions, run records, evaluation, monitoring
```

`brand-check.html` is no longer treated as the product. It is one front-stage workflow: external expression preflight.

## Product Shape

### Front Stage

The front stage is for daily business use. It should stay minimal and action-first.

It contains:

- one question box;
- front desk reception;
- external publishing preflight;
- first-store opening workflow;
- material intake;
- employee training;
- operating review.

It must not expose governance internals such as raw claims, chunk ids, review queues, benchmark correction fields, or permission models.

### Middle Platform

The middle platform explains what capabilities power the workflows.

It contains:

- knowledge engine;
- retrieval applications;
- Skill registry;
- Agent routing;
- governed memory.

These are product objects, not raw files. They can link to existing `knowledge.html` and `brain.html` V1 surfaces until dedicated pages exist.

### Back Office

The back office is for control and traceability.

It contains:

- review;
- permissions;
- versions;
- run records;
- evaluation;
- monitoring.

Back-office controls should be reachable, but not mixed into the front-stage workflow copy.

## Current Implementation

- Main entry: `apps/admin-web/index.html`
- Front-stage workflow pages:
  - `frontdesk.html`
  - `brand-check.html`
  - `startup.html`
  - `knowledge.html`
  - `../employee-web/training.html`
  - `brain.html`
- Guard tests: `tests/test_hxy_brain_frontend.py`

## Non-Negotiable Rules

1. The homepage must not collapse back to a single `brand-check.html`-style page.
2. The front stage must keep one question box.
3. Governance terms belong in the back office, not inside front-stage workflow cards.
4. Process memory can remind, but cannot become authority.
5. Chat, Agent, Loop, Skill, and memory cannot publish approved knowledge.
6. HXY must stay independent from htops data and service names.
