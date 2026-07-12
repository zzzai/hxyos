# HXYOS Role Task Loop V1

## Decision

HXYOS Task Loop turns governed answers into organization work:

```text
question or operating issue
-> actionable answer
-> role-scoped task
-> execution result
-> immutable audit event
```

It extends Product Shell V1 without adding another dashboard. Users keep the same three primary surfaces:

```text
对话 | 待办 | 我的
```

## V1 Scope

- Founder and HQ operations can manage organization-scoped tasks.
- Store managers can manage tasks they created, received, or published to their store.
- Store employees can read assigned and store-visible tasks and record execution results.
- An authorized user can turn an assistant answer action into a self-assigned task without copying text.
- Every create or status transition writes an immutable task event.

V1 does not include recurring tasks, approval workflows, task comments, project boards, or automated task completion.

## Authorization

Authorization is derived from the authenticated assignment. The API does not trust browser-submitted role or organization context.

- All task reads are restricted to the active organization.
- Store visibility is valid only for a store owned by that organization.
- Store managers cannot access private tasks assigned to another employee unless the manager created the task.
- Assignees must belong to the task organization and, for store tasks, the same store.
- A task's answer source must be an assistant message in the submitted conversation and owned by the active assignment.
- Missing and unauthorized task reads return the same `404` response.

The database repeats the critical boundaries with composite organization, store, assignment, task and event foreign keys.

## State Model

```text
open -> in_progress -> completed
  |          |
  +----------+-> cancelled
```

Closed tasks cannot be reopened or overwritten. The repository locks the task row and rechecks its state inside the transaction before writing a transition.

Completion requires a non-empty execution result. The event stores actor, transition, result and timestamp.

## Audit Model

`hxy_product_task_events` is append-only:

- task deletion is restricted;
- event `UPDATE` and `DELETE` are rejected by a trigger;
- event `TRUNCATE` is rejected by a statement trigger;
- actor and task must belong to the event organization.

## Product Interaction

- `待办` loads only the current assignment's visible work.
- Active tasks are ordered by priority and status.
- Completion happens inline and records the result before changing state.
- A manager can use `转为待办` on an answer with a next action.
- The main conversation composer remains available across views.
- Task list requests use version guards so older responses cannot overwrite newer state.

## Implementation

Backend:

- `data/migrations/015_hxy_product_tasks.sql`
- `apps/api/hxy_product/task_schemas.py`
- `apps/api/hxy_product/task_routes.py`
- `apps/api/hxy_product/task_repository.py`

Frontend:

- `apps/hxy-web/src/api/tasks.ts`
- `apps/hxy-web/src/App.tsx`
- `apps/hxy-web/src/styles/shell.css`

Tests:

- `tests/test_hxy_product_tasks.py`
- `apps/hxy-web/src/App.test.tsx`

## Verification Evidence

Completed before release:

- Python: `716 passed, 2 skipped`.
- Web component tests: `36 passed`.
- Playwright: `6 passed`.
- TypeScript and Vite production build: passed.
- Public release preflight: passed.
- Disposable PostgreSQL database: migrations `001-015` passed.
- Database rejected cross-organization task and event relationships.
- Database rejected task-event `UPDATE`, `DELETE`, and `TRUNCATE`.

## Release Gate

Do not deploy migration `015` by running the broad migration script directly against production.

Release requires:

1. database backup and verification;
2. migration `015` preflight against the current schema;
3. migration application in a controlled transaction;
4. API and web release from the same commit;
5. founder, store manager and store employee acceptance journeys;
6. rollback procedure that preserves task audit events.
