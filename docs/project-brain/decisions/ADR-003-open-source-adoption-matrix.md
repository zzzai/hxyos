# ADR-003: HXYOS Open-Source Adoption Matrix

## Status

Accepted

## Date

2026-07-19

## Objective

HXYOS must reach useful operating loops quickly without rebuilding commodity
infrastructure. Reuse is valid only when HXYOS keeps ownership of organization
identity, permissions, operating state, evidence, formal knowledge authority and
metric facts.

## Decision Criteria

Every candidate is evaluated against:

1. contribution to a real HXYOS user action;
2. data isolation and permission enforcement;
3. reliability, security and auditability;
4. integration and operating cost;
5. license and deployment constraints;
6. replaceability and ownership of resulting data;
7. time to verified learning.

Feature count and project popularity are not adoption criteria.

## Adoption Matrix

| Capability | Candidate | Disposition | HXYOS use | Boundary |
|---|---|---|---|---|
| Malware scanning | ClamAV | `sidecar` | Scan every uploaded file before any parser, OCR or model can read it | ClamAV returns scan facts only; HXYOS owns jobs, policy, audit, retries and state |
| Common document conversion | MarkItDown | `embed` | Convert supported Office, PDF and text formats into private normalized Markdown | It cannot assign authority, publish knowledge or change business state |
| Complex document extraction | MinerU | `sidecar` | High-fidelity fallback for scanned or layout-heavy documents selected by the document router | It is not run over all files and cannot become a second knowledge store |
| Local knowledge authoring | Obsidian | `adopt` | Founder and authorized specialists edit local Markdown, links and research notes | It is an authoring workspace, not the multi-user permission, approval or operating system |
| Knowledge compilation | LLM Wiki / OKF patterns | `reference` | Borrow source-to-claim-to-page compilation, provenance and graph-linking patterns | HXYOS does not import claim volume as formal knowledge; authority remains source- and version-governed |
| Enterprise data-agent UX | Volcengine Data Agent patterns | `reference` | Borrow the minimal conversation surface, plan/execution visibility, skills and governed data access | HXYOS does not clone a generic BI agent or surrender its operating control plane |
| Generic RAG platforms | WeKnora / RAGFlow / FastGPT / Dify | `reference` | Reuse retrieval, evaluation and workflow patterns when a measured gap exists | None becomes HXYOS's product shell or source of truth by default |
| Long-running orchestration | Temporal | `reject` for V1 | Reassess after PostgreSQL jobs show multi-day compensation or cross-service timer pressure | Current operating loops remain in the HXYOS durable PostgreSQL job runtime |
| Organization and operating control plane | HXYOS domain modules | `build` | Identity, roles, data scope, events, workflows, evidence, authority, metrics and audit | These contracts remain HXYOS-owned and vendor-neutral |

## Current Integration Contract

The first enforced composition is:

```text
HXYOS upload metadata transaction
-> durable scan job
-> ClamAV sidecar
-> clean result recorded by HXYOS
-> document router
-> MarkItDown / MinerU / OCR / vision adapter
-> private derived artifacts
-> governed knowledge or operating workflow
```

`blocked`, `failed` and unscanned files cannot reach any parser or model. AI and
parsers may produce drafts and evidence, but cannot raise source authority or
approve formal knowledge.

## Why Not Deploy Obsidian Or LLM Wiki As HXYOS

Obsidian is effective for local Markdown thinking but does not provide HXYOS's
server-derived organization permissions, operating workflows, evidence chain or
metric facts. LLM Wiki is useful as a knowledge compiler pattern but optimizes
knowledge production rather than store execution and can amplify low-value
claims. Both are reused within their strongest boundary instead of being made
the product shell.

## Ownership And Review

- Owner: HXYOS architecture owner
- Review date: 2026-10-01, or earlier when a component creates a production
  security, license, reliability or operating-cost issue
- Required evidence: task success rate, latency, failure modes, operator effort,
  security findings and replacement cost

## Replacement And Stop Conditions

A reused component is replaced or removed when it violates data isolation,
cannot enforce the integration contract, has unacceptable license/security
risk, or a measured alternative improves the target workflow enough to justify
migration. HXYOS-owned IDs, files, provenance and state contracts must make the
replacement possible without rewriting the business control plane.
