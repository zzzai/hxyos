# HXYOS Store Role V1 Seven-Day Pilot

## Purpose

Validate that a store manager and technicians can use HXYOS independently in
real daily work. This pilot verifies usability, reliable capture, role scope,
and operating-loop completion. It does not yet prove store performance gains,
cross-store replication, or investment value.

## Pilot Users

- Store manager: records the closing review, checks current information, and
  reports store issues.
- Technicians: ask questions, submit service feedback, upload materials, and
  complete assigned learning practice.
- Founder or administrator: creates role-scoped access and handles technical
  exceptions. Governance review stays outside the ordinary-user interface.

## Available Scope

- General and governed HXY questions through one conversation box.
- Text, file, and browser voice intake through the same input surface.
- Technician learning and service-scenario practice.
- Recent provisional service selection and post-service feedback.
- Manager closing review through the same input surface.
- Today briefing feedback: useful or inaccurate.
- Role-scoped identity, store assignment, and logout.

The third-party store, cashier, member, order, and mini-program APIs are not
connected in this pilot. Service and customer links are provisional and must
remain reconcilable; the UI must not imply that transaction data is live.

## Seven-Day Rule

1. Before day 1, create named accounts and confirm the correct store and role
   for every participant.
2. Give one short access demonstration. Do not train users to follow a hidden
   test script.
3. For seven consecutive operating days, participants use HXYOS during normal
   work for the available scenarios.
4. Do not remind a participant to complete an individual action merely to
   improve the metric. Record assistance as a pilot exception.
5. A failed submission is retried in the product. Do not move the record to a
   private chat as the normal workaround.
6. The administrator reviews technical failures daily, but does not approve
   knowledge or edit employee records in the ordinary-user interface.
7. At the end of day 7, conduct a short role interview and reconcile reported
   experience with the event ledger and operating records.

## Data Boundaries

Business records preserve the text, audio, or files intentionally submitted by
an authorized user. Access follows organization, store, role, and assignment
scope.

The product-event ledger never stores:

- raw conversation or record text;
- phone numbers or phone suffixes;
- customer aliases or external customer identifiers;
- attachment content or file names;
- arbitrary JSON payloads or model prompts.

Participants must not enter a full phone number, diagnosis, guaranteed effect,
payment credential, identity document, or unrelated private information.
HXYOS does not certify massage technique or provide medical diagnosis.

## Product Events

| Event | Meaning | Optional field |
|---|---|---|
| `intake_succeeded` | A unified intake was durably accepted | None |
| `service_feedback_completed` | A technician completed service feedback | `duration_ms` |
| `briefing_feedback` | A user judged a briefing item | `useful` |
| `learning_completed` | A user completed one learning attempt | None |
| `closing_review_completed` | A manager submitted a closing review | None |

Completion events are generated atomically from authoritative business rows:

- accepted organization records produce `intake_succeeded`;
- structured closing-review records produce `closing_review_completed`;
- training sessions produce `learning_completed`;
- service-feedback rows produce `service_feedback_completed`.

The browser may submit only `briefing_feedback`, after the API verifies that
the source record is visible to the active organization, store, role, and
assignment. Every event may include organization ID, store ID, assignment ID,
internal subject ID, client event ID, and server time. The ledger is
append-only and idempotent. Metrics must be calculated from these auditable
fields and their source business rows, not from model-generated estimates.

The event ledger records accepted completions, not failed HTTP attempts. During
this V1 pilot, submission failures, retries, and workarounds are recorded in a
separate privacy-safe pilot exception log with time, workflow, symptom,
resolution, and owner. Do not calculate a success rate from the completion
ledger alone.

## Success Criteria

- Every pilot user can sign in, see only the assigned role/store scope, and
  sign out without administrator intervention.
- At least 80% of intended real work inputs are submitted successfully through
  HXYOS, using the operating record as the numerator and the pilot exception
  log plus observed intended inputs as the denominator.
- At least 80% of actual services selected for pilot feedback have one
  completed feedback record without requiring a private-chat workaround.
- The manager completes a closing review on at least 6 of 7 operating days.
- Each participating technician completes at least one assigned practice and
  can ask both a general and an HXY-specific question.
- No cross-store or cross-assignment data exposure is observed.
- No product event contains raw content or customer-identifying data.
- All pilot exceptions have an owner, time, symptom, and resolution status.

These criteria establish a usable baseline. Changes in onboarding time,
service quality, issue closure time, revenue, retention, or store replication
require later baseline comparison and cannot be inferred from V1 event counts.

## Evidence And Decision

At pilot close, produce one internal report containing:

- participant roles and operating days, without customer identity data;
- completion counts from authoritative business rows and the product-event
  projection;
- failure and retry counts from the pilot exception log;
- unresolved technical and workflow exceptions;
- role interview findings;
- a ship, revise, or stop decision for each tested workflow.

Automated test results are release evidence only. Real-role validation remains
pending until seven consecutive operating days have been observed and the
pilot report has been reviewed.
