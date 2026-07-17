# HXYOS Core-10 Knowledge Activation Packet Design

## Product Decision

HXYOS will close the remaining Core-10 knowledge-readiness gaps through one
compact founder decision packet. The packet groups decisions by business
object, not by extracted claim.

```text
Core-10 report
+ current Brand Constitution state
+ database-backed source authority
+ source evidence
+ answer-card inventory
-> read-only activation packet
-> one bounded founder review
-> separate, explicit activation step
```

The packet may propose exact writes. Generating or previewing it must not write,
approve, publish, or activate knowledge.

## Problem

Core-10 currently passes routing, safety interception, action usefulness and
token-cost gates. Five cases remain blocked because their required authority is
not active:

- brand identity has no active owner-approved Brand Constitution;
- product-system evidence remains external reference;
- first-store operating decisions have no classified internal source;
- reception standard has no exact approved answer card;
- operating issue handling has no classified internal source.

These are governance gaps. Treating them as retrieval or prompting defects
would either preserve the failures or manufacture authority.

The existing claim and topic review flows are too granular for this decision.
HXYOS needs one source-level packet with no claim-by-claim review.

## Approaches Considered

### One Core-10 activation packet

Selected. It minimizes founder work while preserving independent decisions and
exact evidence boundaries.

### Separate domain packets

Rejected for V1. Separate brand, product and operations packets provide similar
control but require repeated review and make the benchmark gate harder to
understand as one release decision.

### Automatically promote likely internal sources

Rejected. File paths, quality scores and model classifications may nominate a
source but cannot grant authority. Old plans, external references and generated
drafts must not become internal authority without an explicit decision.

## Scope

V1 includes:

- deterministic analysis of a captured Core-10 report;
- current-state checks for Brand Constitution, sources and answer cards;
- exactly four grouped activation items;
- source-level evidence summaries with bounded excerpts;
- proposed authority and exact write intents;
- approve, reject and request-correction decision options per group;
- packet and upstream fingerprints;
- JSON and Markdown artifacts under a local private data directory;
- a read-only API projection suitable for a later internal review surface;
- validation of a founder decision payload without applying it.

V1 excludes:

- applying source authority changes;
- publishing or activating a Brand Constitution;
- creating an approved answer card;
- production migration 019;
- claim-level review;
- bulk governance of the full corpus;
- a new frontstage module;
- embedding real HXY brand wording or private evidence in Git.

## Grouped Decisions

The packet contains at most four items with stable keys.

### `brand_constitution`

Contains an exact local draft of the core statements, role variants, forbidden
interpretations and source references. It reports whether an active valid
constitution exists.

An approved decision may later authorize these write intents:

```text
create immutable version file
append publication event
replace active pointer atomically
```

### `product_system_sources`

Contains only explicitly selected source assets proposed as HXY internal working
material for the product system. V1 recommends `internal_material`, not
`official_internal`, unless the packet input explicitly requests otherwise and
the policy permits it.

Approval classifies the parent source, not its chunks or extracted claims. It
does not create a formal answer card.

### `first_store_operations_sources`

Contains selected internal working sources for first-store opening decisions and
operating issue handling. The item is blocked when no credible source is
selected. External plans, competitors and generic generated reports cannot be
used to fill the gap.

### `reception_standard_answer_card`

Contains one exact answer-card draft for the reception standard, its intended
audience, intent, evidence and compliance preflight. Approval only authorizes a
later publication operation; the packet itself does not create the card.

## Data Contract

Top-level packet shape:

```json
{
  "version": "hxyos-core10-activation-packet.v1",
  "packet_id": "core10-activation:<digest-prefix>",
  "generated_at": "<UTC timestamp>",
  "benchmark": {
    "version": "hxyos-core-10.v1",
    "pass_rate": 0.5,
    "failed_case_ids": []
  },
  "upstream_fingerprints": {},
  "items": [],
  "item_count": 4,
  "official_use_allowed": false,
  "publish_allowed": false,
  "write_to_database": false,
  "requires_founder_decision": true,
  "authority_rule": "activation_packet_is_a_proposal_not_authority"
}
```

Each item contains:

```text
item_key
title
status
current_state
proposed_authority
source_evidence
why_needed
affected_core10_cases
risk_if_approved
risk_if_rejected
exact_write_intents
decision_options
blockers
official_use_allowed=false
write_allowed=false
```

Source evidence contains public-safe identifiers, source title, source path,
authority version and a bounded excerpt. It never contains storage credentials,
raw local absolute paths, hidden reasoning or unrestricted document content.

`exact_write_intents` are declarative previews. Each intent identifies the
target, operation, expected prior version or fingerprint, and proposed payload
digest. It never contains an executable command or database credential.

## Inputs

The builder accepts explicit, typed inputs:

- captured Core-10 report;
- active Brand Constitution status;
- a local private constitution draft, when present;
- source candidates selected by asset id for product and operations;
- database source records and bounded evidence for those ids;
- existing approved answer-card inventory;
- a local private reception-standard draft.

Source candidates may be recommended by automation, but the activation packet
builder does not infer authority from file name, directory, score, model output
or metadata. Missing or stale inputs fail closed.

## Decision Contract

Each group allows exactly one action:

```text
approve
reject
request_correction
```

An approval requires:

- an authorized founder decision identity;
- packet id and full packet fingerprint;
- item key and item fingerprint;
- a non-empty reason;
- no unresolved blocker;
- all proposed prior versions still matching current state.

Decision validation is preview-only in V1. A valid decision does not apply any
write intent.

The four items remain independent. Rejecting one item must not make the other
three appear approved or block their review.

## Fingerprints And Staleness

Canonical JSON SHA-256 fingerprints cover:

- Core-10 report;
- constitution draft and current active pointer;
- selected source records, authority versions and evidence;
- reception card draft and answer-card inventory;
- every packet item;
- the complete packet excluding generated timestamp fields.

Any upstream change invalidates the prior packet or affected item decision. A
stale decision returns a validation error and never degrades into a warning.

## Generation Flow

```text
load and validate Core-10 report
-> identify supported knowledge-readiness failures
-> load current authority state
-> resolve only explicitly selected source ids
-> build four grouped proposals
-> run compliance and conflict preflights
-> compute item and packet fingerprints
-> write local private JSON and Markdown atomically
-> expose sanitized read-only projection
```

The generator is idempotent for unchanged inputs except for `generated_at`.
Packet identity and decision fingerprints are based on canonical content, not
the generation timestamp.

## Failure Handling

- Missing Core-10 report: do not create a packet.
- Invalid or non-captured benchmark: block the packet.
- Missing constitution draft: create a blocked brand item.
- Unknown source id: create a blocked source group and report the id.
- External source proposed for internal authority: block the item.
- Source authority version mismatch: mark the packet stale.
- Unsafe reception wording: block the answer-card item.
- Existing conflicting approved answer card: block the answer-card item.
- Artifact write failure: leave the prior complete packet unchanged.

The builder never substitutes another source to make a blocked item pass.

## Storage And API

Artifacts live under an ignored local path:

```text
data/private/core10-activation/<packet-id>/packet.json
data/private/core10-activation/<packet-id>/packet.md
data/private/core10-activation/<packet-id>/decisions.sample.json
```

The read-only API returns a sanitized packet projection. It must not expose
absolute paths or unrestricted source text. The decision-preview API validates
payloads and returns `write_to_database=false`.

No approval buttons or new review dashboard are added in this slice.

## Security And Governance

- Private activation artifacts remain outside Git.
- Only HXY-owned sources are eligible for internal authority proposals.
- No HXY business data is written to or read from `/root/htops`.
- Source authority comes only from database records, never chunk metadata.
- Process memory and conversation history cannot be source evidence.
- The model cannot add, replace or approve packet items.
- A packet is evidence for a later human decision, not enterprise authority.

## Test Strategy

Unit tests cover:

- four-group deterministic construction;
- failure-to-group mapping for the five remaining Core-10 cases;
- missing and unsafe input blockers;
- source-level grouping without claim ids;
- bounded and sanitized evidence;
- exact declarative write intents;
- canonical fingerprint stability;
- stale decision rejection;
- preview-only decision validation.

API tests cover:

- missing packet behavior;
- sanitized read-only projection;
- decision preview with no repository mutation;
- absolute-path and private-content redaction.

Regression verification covers the full Python and web test suites plus a fresh
Core-10 capture. Packet generation must not change the current benchmark result,
because V1 performs no activation.

## Acceptance Criteria

1. One packet contains no more than four grouped decisions.
2. No claim id, chunk review task or claim-level decision is exposed.
3. The five current Core-10 failures map to exactly one of the four groups.
4. Every item shows current state, proposal, evidence, impact, risks and exact
   write intents.
5. Missing, external, stale or unsafe evidence blocks the affected item.
6. Packet and item fingerprints are deterministic and stale decisions fail.
7. Generation and decision preview perform zero database or authority writes.
8. Private HXY wording and evidence remain local and out of Git.
9. Full regression stays green and authority leakage remains zero.
10. Production migration 019 is not applied.

