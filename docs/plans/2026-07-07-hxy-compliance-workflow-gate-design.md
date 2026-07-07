# HXY Compliance Workflow Gate Design

## Context

HXY already has a deterministic compliance language check. It can inspect a piece of external-facing text and return `allow`, `revise`, or `block` with risk reasons and rewrite suggestions.

That is useful as a tool, but it is not yet a workflow gate. Real operations need the same check embedded into common work surfaces:

- 内容发布：朋友圈、团购页、海报、小红书、抖音、社群文案
- 员工话术：接待、推荐、功效问题、复训材料
- 项目菜单：项目名、项目介绍、套餐说明、居家产品说明

The product requirement is not to build a publishing system. The requirement is to stop risky wording before it becomes published content, training material, or menu copy.

## Decision

Add one HXY-owned compliance workflow gate endpoint:

```text
POST /api/operating-brain/workflow-gates/compliance/run
```

Input:

```text
workflow_type: content_publish | staff_script | project_menu
text
channel
audience
```

Output:

```text
decision: allow | revise | block
workflow_status: can_continue | revise_before_continue | blocked
next_step
human_owner
risk_reason
rewrite_suggestion
can_continue
can_publish: false
official_use_allowed: false
review_required
```

The existing skill endpoint remains available. The new workflow gate wraps the same deterministic rule engine and translates the result into business action.

## Why Single Endpoint

### Option A: Three separate endpoints

Example:

- `/content-publish/compliance-check`
- `/staff-script/compliance-check`
- `/project-menu/compliance-check`

This is explicit, but it duplicates logic and makes future Hermes/Feishu integration noisier.

### Option B: One endpoint with `workflow_type`

This is the selected approach. It keeps one compliance engine, one auth policy, one test surface, and one front-end integration. The business meaning still differs by `workflow_type`.

### Option C: Put everything in the existing skill endpoint

This would be fast, but it keeps the product at "tool" level. A workflow gate needs fields such as `workflow_status`, `next_step`, and `human_owner`.

## Workflow Semantics

### Content Publish

For external content, `block` and `revise` must stop release. `allow` only means it may enter human publication review.

```text
allow  -> can_continue, next_step=进入发布前人工确认
revise -> revise_before_continue, next_step=先按建议改写，再复检
block  -> blocked, next_step=停止发布，重写表达
```

### Staff Script

For staff scripts, risky content must not enter training material. `allow` means it can become a training draft, not an approved SOP.

```text
allow  -> can_continue, next_step=进入店长/运营复核
revise -> revise_before_continue, next_step=改成标准话术后复训
block  -> blocked, next_step=禁止进入员工培训
```

### Project Menu

For menu copy, medicalized project wording is highest risk. Even an allowed result still requires menu owner review.

```text
allow  -> can_continue, next_step=进入菜单负责人复核
revise -> revise_before_continue, next_step=改项目名或项目介绍
block  -> blocked, next_step=停止上架该表达
```

## Governance

The workflow gate must not:

- publish content
- write approved answer cards
- write menu data
- approve training scripts
- use htops services or data

It may:

- return risk decisions
- return rewrite suggestions
- tell the user the next workflow step
- be used by admin UI, Hermes, Feishu, or future menu systems

## Frontend Shape

Keep the existing minimal panel. Add one select:

```text
用途：内容发布 / 员工话术 / 项目菜单
```

The result should answer:

```text
能不能继续
为什么
怎么改
下一步找谁确认
```

It should not expose raw rule internals, claim IDs, file paths, or review queue details.

## Tests

Backend tests:

- content publish blocks medical claims and cannot publish
- staff script blocks risky employee answers from training
- project menu blocks medicalized project copy
- low-risk copy can continue but still cannot publish automatically
- unknown workflow type is rejected
- endpoint requires token and fails closed through existing auth

Frontend tests:

- page contains workflow select
- page calls workflow gate endpoint
- page renders business labels, not technical schema names
