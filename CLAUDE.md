# HXY Claude Execution Contract

## Mission

HXY is the independent operating system for 荷小悦.
It is not htops.
It must not share business data with 荷塘悦色.

## Working Rules

1. Keep HXY business data inside `/root/hxy`.
2. Never import htops store, member, order, technician, or operating data into HXY.
3. Use HXY-owned paths for HXY work:
   - `apps/`
   - `packages/`
   - `knowledge/`
   - `data/`
   - `docs/`
   - `ops/`
   - `scripts/`
   - `tests/`
4. Copy-first for migration work. Do not delete source material until backup, manifest, verification, and explicit cleanup exist.
5. Generic reusable code must not carry brand, store, member, order, technician, or knowledge payloads.
6. HXY service names should use `hxy-*`.
7. HXY APIs must live in HXY-owned services, not htops service entrypoints.

## Loop Engineering

Every non-trivial HXY task should behave like a closed loop:

- define a measurable target
- bound the context
- call the right tool or workflow
- evaluate the output
- stop on success, failure, or hard limit

Do not keep looping after the output is good enough.
Do not let the loop continue without a stop condition.
Do not let the goal drift while the loop runs.

## Default Loop Checklist

Before acting, ask:

- What is the measurable target?
- What context is required?
- Which tool or workflow should run?
- How will I judge success?
- What is the stop condition?

## Output Discipline

- Show the result, not the chain of thought.
- Prefer concise, actionable outputs.
- If a task changes behavior, verify it with tests or a direct check.

