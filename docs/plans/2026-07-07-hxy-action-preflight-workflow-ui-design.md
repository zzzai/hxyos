# HXY Action Preflight Workflow UI Design

## Design Read

This is an internal operating workflow for store staff and operators, not a marketing page. The visual language should be extremely minimal, task-first, and calm: one input, one purpose choice, one decision, one next step.

## Problem

HXY already has a compliance workflow gate, but the useful capability is still buried in the knowledge governance page. The front-stage `brand-check.html` reads like a local forbidden-word checker. That makes the product feel like a rule sheet, not a daily workflow.

## Options Considered

1. Keep `brand-check.html` as a local checker and add a separate preflight page.
   - Pro: avoids touching existing UI.
   - Con: adds another entry and fragments the user journey.

2. Upgrade `brand-check.html` into the action preflight surface.
   - Pro: matches the existing index entry, keeps one obvious place for "这句话能不能发", and uses the real workflow gate.
   - Con: requires replacing some existing local-check copy and tests.

3. Move the compliance panel from `knowledge.html` to the home page.
   - Pro: fastest access.
   - Con: mixes governance and daily task entry, making the home page heavier.

Recommendation: option 2. The user's mental model is already "这句话能不能发". That page should become the front-stage workflow surface.

## Product Shape

The page should answer exactly four questions:

- 能不能继续
- 为什么
- 怎么改
- 下一步

The page keeps a single text area for the draft phrase and adds a small purpose selector:

- 发出去
- 给员工说
- 放进项目菜单

The result maps the backend workflow gate to business language:

- `can_continue` -> 可以继续
- `revise_before_continue` -> 先改再继续
- `blocked` -> 不要继续

It must not show raw governance internals such as claims, chunks, review queues, file paths, cluster fields, or approval controls.

## Data Flow

`brand-check.html`
-> `POST /api/operating-brain/workflow-gates/compliance/run`
-> render a human-readable workflow result
-> fallback to the current deterministic local checker when the API is offline.

Fallback is only for front-stage usability. It must not claim official approval.

## UI Constraints

- One page, no dashboard.
- Keep the existing home entry and URL.
- Keep the question/input box.
- Do not expose review queues or raw compliance packs.
- No decorative icons, fake metrics, raw JSON, or technical field names.
- No em dashes in visible copy.
- Mobile collapses to one column.

## Testing

Frontend tests must assert:

- `brand-check.html` uses the compliance workflow gate endpoint.
- The page contains the four workflow outputs.
- The page keeps `brandTextInput` and `brandCheckResult`.
- The page does not expose admin-only words or raw internals.
- Offline boundary-language behavior still returns `可以继续` and does not block negated forbidden terms.
