# HXYOS Organization Record Frontstage V1 Design

## Status

Approved product direction on 2026-07-20.

This document replaces the current ordinary-user interaction model of:

```text
generic chat + feature tabs + embedded business forms
```

with:

```text
continuous organization information intake
-> governed AI understanding
-> role-relevant briefing and assistance
-> outcomes returned as organization records
```

## Product Definition

HXYOS Frontstage V1 is the organization information entrance and intelligence surface for 荷小悦.

It lets organization members submit what happened with minimal effort, lets AI understand and connect those records under explicit permissions, and lets each role use the resulting context in daily work.

It is not:

- a replacement for Feishu task and project management;
- a generic file knowledge base;
- a dashboard made of feature modules;
- a chatbot that waits for users to invent the right question;
- an ordinary-user interface for knowledge review, model operations, or system governance.

## First Principles

### 1. Organization records are the primary input

The primary frontstage object is `OrganizationRecord`, not a file, claim, task, or chat message.

An organization record may originate from:

- typed text;
- voice;
- a photo or video;
- a file or link;
- imported WeChat or Feishu conversation history;
- a meeting record or management action;
- future business-system, revenue, customer, order, or platform data.

### 2. Capture must be easier than classification

Ordinary users do not select knowledge categories, source-authority levels, tags, or workflow types before submitting information.

HXYOS records the original source first, then derives candidate structure asynchronously. If required context cannot be inferred, the system asks one necessary question after capture; it never discards the original record.

### 3. Minimal does not mean empty

The product uses a restrained interface, but it proactively shows the few items that matter to the current role.

The ordinary home surface may show:

- up to three items requiring attention;
- material risks with evidence;
- a small number of key progress changes;
- the universal ask-and-record composer.

### 4. Progress is a projection, not a second project system

HXYOS may derive milestones, progress, blockers, and reminders from organization records and connected systems. It does not require users to maintain a parallel project board.

Routine tasks remain in Feishu or another designated execution tool. HXYOS surfaces only role-relevant critical reminders, decisions, and risks.

### 5. AI interpretation is not official knowledge

The system separates:

```text
raw organization record
AI interpretation
verified business fact
approved organization knowledge
```

An AI extraction can update a briefing as a clearly attributed working interpretation. It cannot silently change the Brand Constitution, prices, formal policies, compliance boundaries, or other approved core knowledge.

### 6. Permissions are implicit in the experience

Role and organization scope change what a user can submit, retrieve, and see. Ordinary users should not need to understand the permission model, but every retrieval, briefing item, source link, and AI answer must enforce it.

## Information Architecture

### Desktop navigation

```text
+ New record

Today
Organization records

Recent conversations
--------------------
Identity and scope
```

The rail may show small counts for items needing attention. It must not contain a long module catalog.

### Mobile navigation

The mobile product preserves the same mental model:

```text
Today | Conversation | Records | Me
```

Capture remains available from the composer and a clear add action. Camera, voice, file, and link input require no detour through a management page.

### Frontstage surfaces

V1 has four ordinary-user surfaces.

#### 1. Today

`Today` is a role-specific briefing, not a dashboard.

Content order:

1. items requiring the user's attention;
2. evidence-backed risk notices;
3. key changes since the last visit;
4. the universal composer.

Each row states:

- what changed or requires attention;
- why it matters to this role;
- its source and freshness;
- the next meaningful interaction.

Selecting a row opens a contextual conversation or record detail. It does not navigate to a project-management form.

#### 2. Conversation

The conversation surface supports questions, record submission, decision assistance, generation, and follow-up in one thread.

The composer supports:

- text;
- voice;
- camera;
- file upload;
- chat-history upload;
- pasted links.

AI responses distinguish formal answers, working interpretations, and reference information. Source details remain available through progressive disclosure.

#### 3. Organization records

This surface lets a user view records they submitted or are authorized to access.

The default list shows only:

- source preview;
- who or what submitted it;
- capture time and event time when known;
- processing state;
- a one-line understanding summary.

It does not expose internal tags, chunk lists, claims, embeddings, review queues, or model traces.

#### 4. Record detail

The detail surface preserves the evidence chain:

- original content or artifact;
- source and access scope;
- processing status;
- extracted facts, decisions, progress, and risks;
- confidence and evidence spans;
- related records and conversations;
- corrections or a retry action when permitted.

Desktop uses a secondary work pane when space permits. Mobile uses a full-screen detail surface with a clear return path.

## Role Projection

The shell remains consistent. Content and permitted actions change by role.

### Founder

- critical decisions and unresolved risks;
- major progress changes across authorized scopes;
- evidence behind a status or recommendation;
- decision and research assistance.

### HQ and online operations

- content and channel risks;
- campaign inputs and outcome records;
- operational handoffs and missing information;
- authorized organization and platform data.

### Store manager

- store exceptions and material changes;
- staff, customer, service, and facility records;
- reminders that require manager attention;
- quick voice, photo, and document submission.

### Store employee or technician

- service and communication guidance;
- assigned training or important reminders;
- low-friction customer and现场 feedback;
- only the knowledge and records allowed for the active store assignment.

## Capture And Understanding Flow

```text
user or channel submits input
-> persist immutable source metadata and artifact
-> return receipt immediately
-> enqueue multimodal parsing and understanding
-> extract candidate entities, facts, decisions, progress, and risks
-> attach evidence spans and confidence
-> apply permission and governance policies
-> update authorized role brief projections
-> notify only when attention is justified
```

The immediate receipt shows:

```text
received
processing
ready
needs attention
```

When ready, it summarizes what was recognized without asking the user to approve every extraction.

## Core Data Contract

### OrganizationRecord

Required fields:

- `record_id`;
- `organization_id`;
- `store_id` when scoped to a store;
- `submitted_by` or channel identity;
- `source_type` and source locator;
- `source_hash` and idempotency key;
- `occurred_at` when known;
- `captured_at`;
- `access_scope`;
- `processing_status`;
- immutable original-artifact reference.

### RecordInterpretation

Versioned derived fields:

- summary;
- entities and relationships;
- candidate facts;
- decisions;
- progress changes;
- risks;
- evidence spans;
- confidence;
- parser and model provenance;
- interpretation version and timestamp.

### RoleBriefItem

A brief item is a projection, not source truth.

Required fields:

- target role or assignment;
- severity and reason;
- concise statement;
- source record references;
- freshness;
- permitted next interaction;
- lifecycle state such as active, acknowledged, resolved, or expired.

Metric facts, official knowledge, and formal tasks remain separate objects and may reference organization records as evidence.

## Initial Vertical Slice

The first production slice uses current store-preparation information because it is real, time-sensitive, and multimodal.

```text
upload renovation chat history, plan, or现场 photo
-> create organization record
-> return immediate receipt
-> extract decisions, progress, missing information, and evidence-backed risk
-> update the founder briefing
-> open a contextual question from the briefing item
-> answer with links to the originating record
```

The same contract must also accept purchasing records and online-operations onboarding material without adding separate feature modules.

## Error And Recovery Behavior

- Source capture succeeds or fails independently of AI processing.
- A model timeout never loses the submitted artifact.
- Duplicate submissions are detected by source hash and idempotency key.
- Processing retries are bounded and audited.
- `needs_attention` explains whether the issue is unreadable content, missing permission, unsupported format, or failed interpretation.
- Users can retry understanding without uploading the source again.
- A corrected interpretation creates a new version; it does not overwrite the original source or prior interpretation.
- Brief items disappear when their source becomes inaccessible or their lifecycle expires.

## Security And Governance

- Every record is scoped to an HXY-owned organization and optional store.
- Retrieval and role briefs apply server-side assignment permissions.
- Original artifacts use controlled access URLs.
- Sensitive data is not exposed in previews or model traces.
- Ordinary users never see review queues, internal paths, secrets, model credentials, or cross-role data.
- HXY records and business data remain isolated from `/root/htops` and htops services.

## Interaction Acceptance Criteria

- Any supported input can be submitted in no more than two user actions.
- Submission does not require a title, category, tag, or authority selection.
- The receipt appears before AI processing completes.
- Processing state remains visible and recoverable.
- `Today` shows no more than three items requiring attention by default.
- Every risk or progress claim links to accessible evidence.
- The main composer remains available on the Today and Conversation surfaces.
- Desktop works at 1280px and 1440px without large empty dead zones.
- Mobile works at 360px and 390px without text overlap or hidden primary actions.
- Camera, voice, and file actions are reachable with one hand on mobile.
- Role changes alter data and actions without changing the core navigation model.
- No ordinary-user path exposes governance or review terminology.

## Verification

V1 verification includes:

- component tests for navigation, capture, receipts, role brief limits, and permission-driven rendering;
- API contract tests for organization records, interpretations, and brief projections;
- idempotency, timeout, retry, and inaccessible-source tests;
- Playwright desktop and mobile end-to-end flows;
- visual screenshots for empty, populated, processing, error, and detail states;
- real-role smoke tests for founder, HQ operations, store manager, and store employee;
- evidence checks confirming every displayed risk and progress item has an accessible source.

## Explicit Non-Goals

- project boards, Gantt charts, or a complete task manager;
- a full Feishu replacement;
- ordinary-user knowledge approval;
- automatic mutation of approved core knowledge;
- investor dashboards;
- broad analytics before reliable organization-record capture exists;
- separate frontends for each role.

## Design Decision

HXYOS Frontstage V1 will use a stable, minimal shell with role-specific content. The universal capture and question composer is the primary interaction. Organization records are the durable input. Briefings, progress, risk, conversation context, and future organizational learning are governed projections derived from those records.
