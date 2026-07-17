# HXY Source Registry V2 Design

## Product Decision

HXYOS must understand a source before it extracts claims or makes the source
retrievable. The current inbox is a mixed evidence store, not one knowledge
base. Source Registry V2 creates a conservative, file-level control plane for
the inbox without changing source files, PostgreSQL, or formal knowledge.

```text
inbox file
-> path and content identity
-> deterministic source classification
-> use and access policy
-> duplicate linkage
-> private registry artifact
```

The registry describes what a file is and how it may be used. It never decides
that a file is official HXY knowledge.

## Alternatives Considered

### Re-run the existing bulk knowledge ingestion

Rejected. The existing script relies mainly on keyword classification and has
already produced a stale, competitor-heavy database projection. Re-running it
would amplify the current authority problem.

### Create a second authority database and workflow

Rejected. HXYOS already has Source Card V1. A parallel authority model would
create conflicting concepts, migrations, and review paths before the source set
is understood.

### Extend Source Card and build a read-only registry

Selected. Source Card V2 becomes the shared source contract. A deterministic
registry builder applies it to the existing inbox and writes private JSON and
Markdown reports. Database projection comes later, after the registry has been
inspected and the four small business bundles have been decided.

## Scope

V2 includes:

- inventory of every file below `knowledge/raw/inbox`;
- SHA-256 content identity and exact-duplicate groups;
- deterministic path/name/type classification;
- lifecycle, authority, scope, sensitivity, stage, and derivation dimensions;
- explicit exclusion of parser copies, crawler code, debug files, and tools;
- conservative allowed/blocked-use policy;
- machine-readable private JSON and a human-readable private summary;
- compatibility fields in Source Card V2 for newly uploaded materials;
- tests for precedence, safety defaults, duplicate handling, and determinism.

V2 excludes:

- claim extraction or review;
- LLM classification;
- content approval or automatic publication;
- database writes or migration `019`;
- creation of `selection.json`;
- parsing/OCR upgrades;
- frontend or review queue changes;
- moving, renaming, deleting, or editing inbox files.

## Source Card V2 Contract

Each path record contains:

```text
version: hxy-source-card.v2
source_id
source_path
content_id
source_hash
size_bytes
file_extension

material_class:
  internal_project | internal_record | external_primary |
  external_secondary | ai_derived | processing_artifact | tool_artifact

lifecycle:
  current_candidate | historical | superseded | undetermined

authority_state:
  unclassified | candidate | approved | rejected

scope:
  brand | strategy | product | first_store | operations | customer |
  finance | legal | technology | design | compliance | external_method

sensitivity:
  public | internal | restricted | founder_only

business_stage:
  first_store | pilot | chain | financing | future_vision | evergreen

derivation:
  original | extracted_copy | ai_summary | application_draft | duplicate_copy

retrieval_state:
  eligible_reference | excluded | pending_source_decision

allowed_use
blocked_use
classification_confidence
classification_reasons
canonical_source_path
duplicate_paths
created_at
```

`scope` may contain multiple values because one source can concern both brand
and first-store operations. The other governance dimensions remain independent;
they must not be collapsed into a quality score.

## Classification Precedence

Rules execute in this order so a broad keyword cannot override a safety rule:

1. `extracted-reference/**` is `processing_artifact`, `extracted_copy`, and
   excluded from retrieval.
2. `**/scripts/**`, executable source files in tool directories, crawler debug
   pages, and temporary search/download files are `tool_artifact` and excluded.
3. Financing agreements, shareholder records, quotations, investor materials,
   and legal documents are `restricted` or `founder_only` before any other
   business classification.
4. Files under the external knowledge directory are external or AI-derived.
   Summaries, reading notes, staged analyses, and HXY application notes are
   `ai_derived`, not independent evidence.
5. The four explicit compliance files remain `candidate`; they are not
   approved by the registry.
6. Explicit archive/old/superseded markers set lifecycle. Version numbers and
   modification time alone do not establish current authority.
7. HXY working directories `00` through `08` default to `internal_project`,
   `undetermined`, and `unclassified` unless a stronger rule applies.
8. Unmatched files receive conservative defaults and low confidence.

No deterministic rule emits `authority_state=approved`.

## Use Policy

```text
external_primary / external_secondary:
  allowed: reference, research
  blocked: official_answer, formal_hxy_fact, automatic_publication

ai_derived:
  allowed: reference, ideation, draft
  blocked: official_answer, evidence_citation, automatic_publication

internal_project / internal_record:
  allowed: internal_context, draft
  blocked: official_answer, automatic_publication

processing_artifact / tool_artifact:
  allowed: audit_only
  blocked: retrieval, generation_context, official_answer, publication
```

All source classes also block unsupported medical, efficacy, financing, and
franchise commitments. A later governed knowledge version may grant narrower
permissions; the registry cannot.

## Duplicate Model

The registry stores one path record per file and one content group per unique
SHA-256 hash. The lexicographically first non-artifact path is canonical. Other
members use `derivation=duplicate_copy` and point to that canonical path. A
duplicate never inherits greater authority from another path; the most
restrictive sensitivity and use policy wins when a content group is projected.

## Output Contract

Default outputs are private and date-versioned:

```text
data/private/source-registry/YYYY-MM-DD-source-registry.json
data/private/source-registry/YYYY-MM-DD-source-registry.md
```

JSON contains run metadata, counts, path records, content groups, unresolved
classifications, and rule-version information. Records are sorted by relative
path and JSON keys are stable. The Markdown report contains aggregate counts,
exclusion reasons, sensitivity counts, duplicate counts, and the four candidate
business bundles; it does not reproduce restricted document contents.

## Four Bundle Decisions

After the source registry is inspected, human decisions happen at four small
business bundles rather than per claim:

1. brand core;
2. product boundary;
3. first-store operating assumptions;
4. reception and compliance.

The registry only identifies candidate sources for those bundles. It does not
write the decisions.

## Error Handling

- unreadable files remain in the registry with an error code and are excluded;
- symlinks that resolve outside the inbox are rejected;
- changing files are detected by size/hash mismatch and reported, not retried
  indefinitely;
- unsupported file formats are still inventoried with conservative defaults;
- a failed run writes no final artifact; temporary files are replaced
  atomically only after complete serialization.

## Acceptance Criteria

1. all 697 current inbox files are inventoried or have an explicit error record;
2. tool and processing artifacts cannot enter retrieval;
3. exact duplicate paths share one content identity;
4. external and AI-derived material cannot become formal HXY facts;
5. financing/legal sensitivity is set before general classification;
6. no record is automatically approved;
7. repeated runs over unchanged input produce identical records except run time;
8. outputs remain private and no PostgreSQL write occurs;
9. Source Card V1 consumers continue to work with the V2 superset;
10. focused tests and the existing project test suite pass.
