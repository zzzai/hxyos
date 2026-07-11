# HXYOS 2.0 Reference Architecture

## Status

```text
status: accepted baseline
accepted_at: 2026-07-11
scope: target architecture and component boundaries
```

This document refines, rather than replaces, the authority and falsifiability
rules in `01-target-architecture.md` and
`02-hxyos-falsifiable-architecture.md`.

## First-Principles Objective

HXYOS exists to turn AI capability into repeatable organization capability for
荷小悦:

```text
stable brand core
+ governed organization knowledge
+ role-specific execution
+ repeatable store operations
+ measurable operating improvement
= lower replication risk and higher brand value
```

The product is not optimized for the number of models, agents, documents, or
features. It is optimized for verified task completion by real roles without
leaking data or weakening the authority boundary.

## Architectural Decision

No generic product becomes the HXYOS parent application.

```text
Cherry Studio is an optional expert client.
DataAgent is a candidate analytics engine.
RAGFlow is a candidate parsing and retrieval engine.
Dify is an optional experiment environment.
Models, vector stores, and cloud services are replaceable infrastructure.

HXYOS remains the only organization control plane and product authority.
```

Clients and engines never own canonical HXY identity, knowledge status,
permissions, brand policy, task state, or decision history.

## Five Planes

### 1. Experience Plane

Owned surfaces:

- minimal HXYOS Web/PWA for desktop and mobile;
- 飞书/Hermes channel adapter;
- future mini program when distribution requires it;
- optional expert desktop clients through governed APIs or MCP.

Rules:

- one primary conversation and task surface;
- no model, provider, vector database, or prompt configuration for employees;
- the same role scope and authority labels on every channel;
- no channel may bypass HXYOS identity or evidence policy.

### 2. HXYOS Control Plane

This is the product core and the principal source of enterprise value.

It owns:

- account, organization, role assignment, store, and data scope;
- brand constitution and approved knowledge versions;
- source, material, evidence, claim, answer card, and decision lifecycles;
- task, training, workflow, feedback, and operating issue state;
- policy evaluation, model budget, audit, trace, and benchmark decisions;
- capability routing to replaceable engines.

The control plane is a modular monolith until measured scale or failure
isolation requires a service boundary. Microservices are not a maturity goal.

### 3. AI Execution Plane

Candidate engines are mounted behind stable ports:

```text
ModelGateway
DocumentParser
RetrievalEngine
AgentRuntime
AnalyticsEngine
MemoryAdapter
ChannelAdapter
```

An engine receives only the minimum authorized task context. Its output is an
artifact or proposal; the control plane assigns authority, visibility, and
publication state.

### 4. Data Plane

Canonical ownership:

| Data | Canonical owner |
|---|---|
| identity, role, store scope | HXYOS relational database |
| approved knowledge and versions | HXYOS relational database |
| raw files and parser artifacts | HXYOS object storage |
| workflow, task, trace, audit | HXYOS relational database |
| process memory | governed HXYOS memory store |
| retrieval index | replaceable derived index |
| model cache | replaceable derived cache |
| operating facts | HXY-owned operational database/warehouse |

Derived indexes can always be rebuilt from canonical HXY data. No vector store,
LLM platform, or client is a system of record.

### 5. Governance And Observability Plane

Every request carries:

```text
request identity
active assignment
organization/store scope
task purpose
knowledge authority policy
model/tool budget
trace id
```

Every result records:

```text
engine and version
model and prompt/policy version
authorized evidence ids
answer authority status
cost and latency
risk and policy decisions
user feedback and downstream outcome
```

Hard gates are deterministic code. Model self-evaluation is supporting evidence,
not authorization.

## Stable Adapter Contracts

### ModelGateway

Input: governed model request, capability requirement, privacy class, budget.

Output: model response, usage, latency, provider trace, fallback history.

Candidates: LiteLLM, cloud gateway, HXY adapter. API keys never reach clients.

### DocumentParser

Input: immutable source reference, media type, parser policy.

Output: bounded text/structure artifacts, page anchors, tables, images, quality
report, parser provenance.

Candidates: MinerU, Docling, MarkItDown, RAGFlow parser.

### RetrievalEngine

Input: authorized corpus filter, query, task type, authority policy.

Output: ranked evidence ids with scores and source anchors.

The engine cannot convert `reference` into `approved`. Permission filtering must
occur before content leaves the engine.

Candidates: PostgreSQL/pgvector, Qdrant, OpenSearch, RAGFlow.

### AgentRuntime

Input: typed task state, allowed tools, policy, stop conditions, budget.

Output: state transitions and artifacts, never implicit knowledge mutation.

Candidates: LangGraph for reasoning state; Temporal for durable outer workflow
when tasks require long waits, retries, schedules, or operator intervention.

### AnalyticsEngine

Input: authorized metric contract, semantic model, read-only data scope, query.

Output: query plan, guarded SQL, bounded result, analysis artifact, report.

Candidates: Spring AI Alibaba DataAgent or a HXY-owned implementation. It must
use read-only credentials, query limits, AST policy, PII masking, and audit.

### MemoryAdapter

Input: process event or governed retrieval query.

Output: context hints with provenance, confidence, recency, and expiry.

Process memory never becomes authority without explicit promotion through the
knowledge lifecycle.

### ChannelAdapter

Input: authenticated channel event.

Output: normalized HXYOS request and channel-safe response.

All channels resolve an HXY assignment before accessing data or tools.

## Target Technology Profile

Technology follows layer fitness, not language ideology:

```text
experience: TypeScript + React/Next.js PWA
control and AI orchestration: Python + FastAPI + LangGraph
durable workflow when justified: Temporal
canonical data: PostgreSQL
object storage: MinIO/S3-compatible storage
default retrieval: PostgreSQL full text + pgvector
scale-out retrieval when benchmarked: Qdrant/OpenSearch/RAGFlow
model gateway candidate: LiteLLM
analytics candidate: DataAgent behind AnalyticsEngine
observability: OpenTelemetry + Langfuse
identity federation: OIDC/飞书, mapped to HXY assignments
```

This is a target profile, not a mandate to rewrite working modules. A component
changes only when benchmark evidence justifies migration.

## Evolution Stages

### Stage A: Governed Vertical Slice

- one founder and one employee role;
- conversation, upload, source view, and one real workflow;
- approved knowledge and private working context remain separated;
- complete trace and permission tests.

### Stage B: Replaceable Intelligence

- introduce ModelGateway and parser/retrieval adapters;
- compare baseline retrieval with RAGFlow or another candidate;
- add Langfuse/OpenTelemetry traces;
- retain one product surface and canonical data model.

### Stage C: Operating Intelligence

- establish metric contracts and a read-only operating warehouse;
- evaluate DataAgent through AnalyticsEngine;
- return analysis inside HXYOS, not through a second employee-facing product;
- connect recommendations to tasks and measured outcomes.

### Stage D: Multi-Store Replication

- store-scoped policy and analytics;
- training and quality loops;
- durable scheduled workflows;
- cross-store comparison only under explicit aggregate permissions.

## Non-Negotiable Boundaries

1. Chat, uploads, memory, or engine output cannot modify core knowledge.
2. Permission filtering occurs before retrieval content is returned.
3. Only HXYOS assigns `approved` or `action_asset` status.
4. Business data access is read-only by default and store scoped.
5. Every replaceable engine has an export, rollback, and failure-isolation path.
6. Employees never configure models or infrastructure.
7. No HXY data is written to `/root/htops` or htops databases.
