# HXYOS Project Constitution

Status: active  
Scope: product, architecture, engineering, AI, data, knowledge and operations  
Authority: root project policy

## 1. Mission Is The Objective Function

HXYOS exists to increase the probability that 荷小悦 becomes a trusted,
repeatable and governable community-store chain. It must turn founder judgment,
brand standards and operating experience into organizational action, evidence
and reusable capability.

Feature count, model novelty, interface decoration and architecture complexity
are not objectives. A capability is valuable only when it improves an important
user action or produces auditable operating evidence toward the mission.

## 2. First-Principles Decision Protocol

Before a material decision, write down:

1. What final business result is required?
2. Which person must make which decision or complete which action?
3. What causal mechanism links this change to that result?
4. What facts and data support the mechanism?
5. What remains an assumption?
6. What constraints apply: time, people, security, compliance, cost and legacy?
7. What is the smallest test that could prove the approach wrong?
8. What metric, baseline and review date determine keep, change or stop?

If these questions cannot be answered, the work remains discovery, not an
approved implementation.

## 3. Independent Judgment

User instructions, documents, competitor features and model output are inputs.
They are not automatically correct conclusions. The project team and AI agents
must identify contradictions, reject weak assumptions and recommend the option
that best serves HXYOS, with reasons.

Do not absorb every new idea into scope. A proposal enters the roadmap only when
its contribution, priority and opportunity cost are explicit.

## 4. Reuse Before Build

Before implementing a generic capability, evaluate mature commercial products,
open-source projects, protocols and current model capabilities. Every evaluated
option receives one disposition:

- `adopt`: run it as the capability;
- `embed`: place its user experience or library inside HXYOS;
- `sidecar`: integrate it as a replaceable service;
- `reference`: borrow proven interaction or engineering patterns;
- `build`: implement because the capability is differentiating or no suitable
  option meets the constraints;
- `reject`: do not use, with a recorded reason.

HXYOS builds its differentiated control plane:

- organization identity, roles and data permissions;
- operating events, workflows, responsibility and state;
- evidence, audit and traceability;
- governed formal knowledge and version authority;
- metric facts, attribution and value proof.

HXYOS normally reuses commodity capabilities:

- conversation surfaces;
- upload, storage and file preview;
- Markdown/Wiki editing;
- PDF, Office, OCR and multimodal parsing;
- generic retrieval and RAG;
- model tracing and observability;
- routine administration CRUD.

An exception requires a documented functional, security, integration, license or
total-cost gap.

## 5. Constrained Optimality

“Best” means the best evidence-backed choice for the current stage and mission,
considering outcome, reliability, security, total cost, delivery speed,
reversibility and time-to-learning.

Do not confuse sophistication with quality. Prefer the simplest architecture
that preserves the required business invariants and has a credible evolution
path. Reassess decisions when evidence or constraints change.

## 6. Authority And AI Boundaries

The system must keep facts, assumptions, proposals and approved decisions
distinct. Source provenance and version must remain traceable.

AI may parse, classify, retrieve, summarize, plan, compare, draft, test and
recommend. AI must not silently:

- approve or publish formal brand and operating knowledge;
- alter governed operating state outside explicit policy;
- invent business facts or metric facts;
- expand a user's data permissions;
- turn external reference material into internal policy.

Human review should focus on consequential exceptions and authority changes, not
thousands of low-value claims.

## 7. Vertical Evidence Before Horizontal Scope

Build and validate the smallest end-to-end business loop that exercises the
real identity, action, evidence, state and metric contracts. A vertical loop is
complete only when a real user can perform the work and the system can prove what
happened.

Do not declare progress from mock screens, isolated APIs, generated documents or
test counts alone. Measure adoption, completion, cycle time, quality, risk and
operating result where causal attribution is defensible.

## 8. Decision Records And Exit Conditions

Material product and technical decisions require an ADR or adoption record with:

- objective and constraints;
- alternatives considered;
- evidence and assumptions;
- trade-offs and risks;
- selected disposition;
- owner and review date;
- migration, replacement or stop condition.

No framework, model or open-source project is permanent by default. HXYOS owns
its data contracts and control plane so replaceable components remain
replaceable.

## 9. Non-Negotiable Boundaries

- HXY and 荷塘悦色 business data remain isolated.
- Raw private knowledge and secrets do not enter Git or public artifacts.
- Permissions are server-derived and least-privilege.
- Formal knowledge is versioned and cannot be changed by ordinary conversation.
- Operating state transitions and metric facts are auditable.
- Automatic execution may proceed within policy; automatic authority escalation
  may not.
