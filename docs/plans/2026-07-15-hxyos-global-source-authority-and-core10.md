# HXYOS Global Source Authority And Core-10 Plan

## Goal

Close the gap between product-material authority and the global knowledge corpus so
Core-10 answers can trust database-backed source classification without promoting
legacy content or creating claim-by-claim review work.

## Non-Negotiable Boundaries

- Existing `hxy_knowledge_assets` default to `external_reference`.
- No migration, importer, model, chat or metadata field can promote an asset.
- Classification happens once per source or source batch and is versioned.
- A chunk inherits authority from its parent asset at retrieval time.
- Approved answer cards remain the only team-standard authority.
- Private knowledge stays under `/root/hxy` and never enters the public repository.
- Migration 018 and later migrations require separate guarded production authorization.

## Task 1: Database-Backed Global Source Authority

Add migration 019 with additive asset authority columns and append-only authority
events. Legacy rows receive the safe baseline only. Authority changes require an
active founder or HQ operations assignment in the same HXY organization and advance
the version by exactly one.

Acceptance:

- 141 existing assets remain `unknown + external_reference + version 1`.
- no answer card or official knowledge is created;
- event history cannot be updated, deleted or truncated;
- unauthorized and cross-organization changes fail.

## Task 2: Import And Retrieval Contract

Strip governance keys from parser/model metadata. New imports rely on database
defaults. Repository upserts never overwrite authority columns. Search joins the
parent asset and returns only its database-backed origin, authority and version.

Acceptance:

- arbitrary chunk metadata cannot grant authority;
- re-importing a source preserves its authority version;
- every returned chunk exposes its parent asset identity and authority;
- assets without migration 019 fail closed as external reference during rollout.

## Task 3: Source-Level Classification Service

Add a repository transaction that writes an event first and updates the source in the
same transaction. Support single-source and bounded source-batch operations. Do not
create a claim review queue.

Acceptance:

- exact actor, organization, reason and previous version are required;
- duplicate or stale updates fail;
- batch results are auditable per source;
- classification never approves answer cards.

## Task 4: Core-10 Code Defects

Fix with separate red-green cycles:

- founder reception practice returns a typed training action;
- synthesized operating answers return typed actions;
- medical efficacy questions route to `risk_boundary`;
- missing internal evidence returns `working + review_required`;
- missing Brand Constitution fails before retrieval/model generation;
- deterministic compliance answers avoid unnecessary model calls;
- explicit database authority outranks legacy lifecycle metadata;
- source-classification benchmark carries real attachment/source context.

## Task 5: Candidate Verification

Run focused tests, PostgreSQL disposable-copy migration tests, candidate API and the
captured Core-10 suite. Separate remaining failures into owner-approved knowledge gaps
and code defects. Do not manufacture brand, product, reception or operating facts to
raise the score.

## Stop Conditions

- Stop production migration unless the exact migration authorization is supplied.
- Stop release if authority leakage is nonzero or high-risk interception is below 1.0.
- Stop bulk governance of the 697-file corpus until parent-asset authority is visible
  in retrieval and Core-10 reaches the release threshold.
