# HXYOS Role Journeys V1

## Status

Implemented on `feature/hxyos-role-journeys-v1`. Not deployed.

This increment turns Product Shell V1 from a shared chat surface into three small, role-specific work loops without adding another dashboard:

```text
Founder: question -> evidence -> task
Store manager: visible task -> linked issue -> follow-up task
Store employee: frontdesk answer -> practice -> correction -> issue report
```

The ordinary product surface remains:

```text
对话 | 待办 | 我的
```

## Product Contract

### Founder

- Ask from the main conversation.
- Inspect answer status and evidence in the existing details drawer.
- Convert a server-provided task action into a self-assigned follow-up.
- Task creation still works when the answer has no generated `next_actions`; the fallback title is `跟进本次回答`.

### Store Manager

- Open current role- and store-visible tasks.
- Start `反馈问题` from a specific task.
- The issue creates a new store-visible task with an immutable parent-task relationship.
- A task from another organization, store, or invisible assignment cannot be used as the parent.

### Store Employee

- Receive a frontdesk answer with approved evidence where available.
- Open a short practice flow from the answer or role suggestion.
- See score, concrete correction points, a reference script, the next practice action and the usage boundary.
- Report a live store issue; it becomes visible store work without granting task-management authority.

## Unified API

```text
GET  /api/v1/journeys/suggestions
POST /api/v1/journeys/training/evaluate
POST /api/v1/issues
```

Role, organization, store and assignment always come from the authenticated session. Browser-submitted identity or store scope is rejected.

Journey suggestions are server-derived, limited to three and capability-filtered again in the client. An intentionally empty server result remains empty; it does not revive local fallback actions.

## Training Boundary

Product training must not write to legacy global training sessions or knowledge review tasks.

`/api/v1/journeys/training/evaluate`:

1. evaluates the employee answer;
2. applies the existing compliance checks;
3. stores only the product training record;
4. returns a redacted result envelope.

The product record is stored in `hxy_product_training_sessions` with mandatory:

```text
organization_id + store_id + assignment_id
```

The table is append-only. It has organization/store/assignment foreign keys and no public list endpoint in V1.

## Safety Rules

- Core knowledge is not approved, published or mutated by these journeys.
- Ordinary practice does not create human review queue items.
- Internal absolute and HXY-relative paths are redacted from conversation and journey output.
- Issue responses expose only the task fields required by the ordinary product.
- Late training or issue responses are discarded after assignment or journey changes.
- Source-task links are accepted only when the task is visible to the active assignment and belongs to the active store.
- Formal knowledge, review, permissions and monitoring remain backstage concerns.

## Database Changes

- `015_hxy_product_tasks.sql`
  - remains unchanged so environments that already applied it keep a valid migration history.
- `016_hxy_product_training.sql`
  - adds optional `parent_task_id` as an idempotent upgrade;
  - enforces same-organization and same-store parent tasks;
  - adds scoped, append-only product training sessions;
  - does not reference legacy training or review tables.

Neither migration has been applied to production.

## Release Gate

Release requires:

1. verified database backup;
2. controlled migration of `015` and `016` in one reviewed release;
3. API and web release from the same commit;
4. founder, manager and employee smoke tests using real session assignments;
5. confirmation that no legacy training/review reader can access product training records;
6. rollback that preserves task events and training audit records.

## Verification

Required before commit and push:

```text
pytest full suite
web component tests
TypeScript + Vite production build
Playwright role journeys and mobile viewport checks
public release preflight
git diff --check
disposable PostgreSQL migrations 001-016
independent backend and frontend review
```
