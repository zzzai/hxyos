# ADR-002: HXYOS Control Plane And Pluggable Engines

## Status

Accepted on 2026-07-11.

## Context

HXYOS can obtain generic capabilities from mature products such as Cherry
Studio, Spring AI Alibaba DataAgent, RAGFlow, Dify, model gateways, and cloud
platforms. Making any one of them the parent application appears fast, but
would transfer product authority and data semantics to a system optimized for a
different problem.

HXYOS must remain simple for employees while enforcing organization identity,
role scope, knowledge authority, brand policy, and store workflow.

## Decision

HXYOS is the organization control plane and canonical product. Generic products
are integrated only behind versioned adapters.

```text
build and own:
identity scope, knowledge governance, brand policy, task/workflow state,
product experience, audit and benchmark decisions

integrate when proven:
models, parsing, OCR, vector retrieval, agent runtime, analytics, channels,
observability
```

The default implementation shape is a modular monolith with external engine
adapters. Service extraction requires measured scaling, isolation, ownership,
or release-cadence evidence.

## Rejected Alternatives

### Fork Cherry Studio As HXYOS

Rejected as the primary product. It optimizes personal desktop model use, adds
employee-facing configuration, does not own HXY organization governance, and
introduces AGPL/commercial-license and upstream-merge considerations.

It remains eligible as an optional expert client through governed API/MCP.

### Fork DataAgent As HXYOS

Rejected as the primary product. It is strong in semantic models, NL2SQL, and
analysis workflows, but it does not provide HXY knowledge authority, role data
boundaries, or the minimal organization experience. Its current release line is
also pre-1.0 stable and documents an incomplete API-key enforcement path.

It remains eligible behind `AnalyticsEngine` after production data exists.

### Assemble Dify And RAGFlow As The Product

Rejected as the control plane. This would create two administration models and
duplicate knowledge/application lifecycles. Both remain eligible as replaceable
workflow or retrieval engines when benchmarked.

### Build Every Capability In HXYOS

Rejected. Parsing, model gateway, vector search, workflow runtime, and telemetry
are commodity capabilities with mature implementations. HXYOS owns adapters,
policy, and canonical data rather than rebuilding infrastructure by default.

## Consequences

Positive:

- HXY assets remain portable and governed;
- engines can evolve with AI technology;
- the employee product remains minimal;
- component selection becomes evidence based;
- cloud and open-source services can coexist.

Costs:

- adapter contracts require deliberate design;
- HXYOS must operate integration tests and traces;
- some generic admin features cannot be adopted unchanged;
- a stable canonical data model is mandatory.

## Review Trigger

Revisit this decision only if a candidate platform demonstrates all of the
following on the HXY benchmark:

1. complete role and store isolation;
2. explicit approved/reference lifecycle enforcement;
3. canonical data export and rollback;
4. equal or better task completion and usability;
5. lower total operating cost without vendor lock-in;
6. no employee-facing infrastructure configuration.
