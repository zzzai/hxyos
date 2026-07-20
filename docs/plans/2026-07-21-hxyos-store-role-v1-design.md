# HXYOS Store Role V1 Design

## Status

Approved on 2026-07-21. This document is the product baseline for the
2026-08-20 store-role release. It supersedes the ask/record mode switch and any
V1 design that depends on the third-party transaction API being available.

## Product Definition

HXYOS is the AI operating execution and organization-learning layer above
HXY's third-party transaction systems.

It does not replace cashiering, membership, scheduling, commissions,
settlement, or the consumer mini-program. It connects organization input,
governed HXY knowledge, operating actions, evidence, and outcomes so useful
methods can be improved and copied across stores.

## Release Outcome

By 2026-08-20, a store manager and a technician must be able to use HXYOS on a
phone for seven consecutive days without developer assistance.

The release is useful only when it supports real work:

```text
capture what happened
-> understand it under role and data permissions
-> return relevant guidance or a next action
-> preserve the source and result
-> make the context available in later work
```

The release is not accepted because pages render, tests pass, or the model can
produce a plausible answer.

## Frontstage Contract

### Shared shell

The ordinary-user frontstage has four destinations:

```text
Today | Ask | Learn | Me
```

`Today` contains at most three role-relevant items. `Ask` is a continuous
conversation with one universal composer. `Learn` contains the next useful
learning action and personal progress. `Me` contains identity, active store,
role, upload history, and session controls.

There is no ordinary-user navigation for claims, review queues, model traces,
knowledge governance, project boards, or workflow configuration.

### Universal composer

The composer supports:

- text;
- press-and-hold voice submission on mobile;
- photo, audio, video, and file upload;
- links and pasted conversation text.

The product has no ask versus record mode. The user never chooses a category,
tag, source authority, or workflow type before submission.

Every submission follows this order:

```text
persist the original input
-> return an immediate receipt
-> classify intent, domain, risk, and required tools
-> execute the selected answer or record workflow asynchronously
-> update the conversation and authorized Today projection
```

The immediate receipt is concise: `已收到，正在处理`.

## Role Experience

### Technician

The technician sees:

- no more than three current reminders;
- the universal conversation;
- one next learning action;
- service-feedback prompts when a service context exists;
- only customer and store information permitted by the active assignment.

The technician product combines three jobs:

```text
work assistant + learning coach + service-feedback entrance
```

### Store manager

The manager sees:

- material store exceptions and unresolved follow-ups;
- concise service-feedback signals that require management attention;
- a pre-shift focus and closing-review action;
- authorized store records and source evidence;
- the same universal conversation.

HXYOS does not require the manager to maintain a duplicate project board.

## Answer Routing

The user experiences one conversation. The server selects the answer path
before generation:

```text
identity and assignment scope
-> intent and domain classification
-> risk policy
-> route selection
-> model, governed retrieval, or skill execution
-> evidence and output-policy checks
-> answer
```

Routes are:

1. `general`: use the configured model within general safety policy.
2. `hxy_official`: retrieve approved HXY knowledge and cite it.
3. `mixed`: combine general reasoning with governed HXY facts; HXY facts win.
4. `service_scenario`: use a role-specific communication or service skill.
5. `high_risk`: apply health, medical-claim, pricing, privacy, or escalation
   policy before answering.

When HXY has no approved answer, the product says so. It may provide clearly
separated general reference information, but it must not invent an HXY policy.

The UI does not expose routing internals. It uses a small source disclosure
only when the answer depends on HXY material.

## Learning Contract

Learning is action-driven, not a course catalog.

V1 supports:

- role onboarding for brand core, service awareness, basic process, and
  compliance boundaries;
- one short recommended learning action at a time;
- AI customer-scenario practice using text or voice;
- feedback on communication, service awareness, brand consistency, and risky
  expressions;
- a private capability record showing mastered, practicing, and needs-attention
  areas.

AI does not certify physical massage technique. Practical technique remains a
trainer or manager assessment with evidence.

There is no public leaderboard in V1.

## Service Context Without The Third-Party API

The third-party API is expected after the V1 release window. V1 therefore owns
a stable `ServiceContext` contract whose source can later change without
rewriting product behavior.

Required semantics:

```text
service_context_id
organization_id
store_id
technician_assignment_id
occurred_at
service_name when known
customer_ref_id when known
source_kind: manual | import | api
external_order_id when available
link_status: provisional | linked | ambiguous | rejected
created_at
```

Before the API is available, a context may be created from:

- a minimal technician entry;
- an authorized spreadsheet export;
- an uploaded schedule or order screenshot;
- a manager-created service prompt.

The minimum fallback identity is a masked alias or phone suffix combined with
store, technician, service, and time. A phone suffix is never treated as a
unique identity.

When the API becomes available, a reconciliation job links provisional service
contexts to external customer and order IDs. It creates mapping history and
does not overwrite original feedback.

## Customer Identity And Privacy

HXYOS uses an internal customer ID and source-specific external identities:

```text
Customer
<- ExternalCustomerIdentity
<- ServiceContext
<- CustomerObservation
```

Plain phone numbers are encrypted when retention is necessary. Deterministic
matching uses a keyed HMAC, not an unsalted hash. Model prompts, vector indexes,
analytics events, and ordinary logs use internal or masked references.

Technicians can access only customer context necessary for their recent or
assigned services. Managers are limited to their authorized store. HQ analysis
uses aggregated or pseudonymized data unless an authorized purpose requires
identifiable records.

Service observations must remain service-relevant. They must not become
medical diagnoses, unsupported health profiles, or unrestricted employee
surveillance.

## Automated Intake

All supported input enters the organization intake contract:

```text
persist source
-> scan and parse
-> ASR/OCR/vision/document extraction
-> identify role, store, time, and context
-> classify intent and extract evidence-backed facts
-> link service/customer/order when possible
-> apply privacy, compliance, and permission policy
-> update conversation, Today, learning, or an operating workflow
```

Routine classification and extraction do not require item-by-item approval.
Only consequential authority changes, external publication, medical claims,
pricing/settlement rules, and unresolved identity conflicts enter a protected
exception flow.

## Value Evidence

The primary V1 measure is useful operating-loop coverage, not uploads, messages,
tokens, or generated claims.

Release evidence includes:

- original-input persistence success;
- median time to submit service feedback;
- eligible-service feedback completion rate;
- service/customer context link quality;
- manager-rated useful briefing ratio;
- learning and scenario completion;
- evidence-backed answer rate for HXY questions;
- permission or sensitive-data incidents;
- seven-day independent usage by real roles.

Initial release thresholds:

```text
original input loss                         0
unauthorized sensitive-data exposure       0
median service-feedback time                <= 45 seconds
eligible feedback completion                >= 70 percent
useful manager briefing items               >= 80 percent
real service feedback records               >= 20
manager closing reviews                     >= 5
independent pilot duration                  >= 7 consecutive days
```

Revenue, satisfaction, complaints, and repeat visits become outcome measures
after a reliable baseline and external data connection exist. Correlation must
not be presented as causal impact.

## Delivery Sequence

1. Harden current API response contracts.
2. Remove ask/record mode selection.
3. Ship the unified composer with voice and file intake.
4. Add pre-generation answer routing and governed source disclosure.
5. Add the technician learning surface and scenario practice.
6. Add provisional service context and customer linkage.
7. Add manager closing review and role-specific Today projections.
8. Complete mobile, desktop, privacy, failure, and real-role acceptance.

## Non-Goals Before 2026-08-20

- full customer 360;
- a native mobile app;
- a POS, CRM, scheduling, settlement, or project-management replacement;
- broad operating analytics before reliable facts exist;
- online-content autopublishing;
- a workflow builder;
- a claim-review frontstage;
- an investor dashboard;
- third-party API behavior invented without a real contract.

## Acceptance Decision

The V1 release is kept only if store roles can use it independently and the
system produces useful, permission-safe operating context. Features that do not
improve a real role action or produce auditable operating evidence are removed
or deferred.
