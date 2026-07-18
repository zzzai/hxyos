# AGENTS

Project scope: `/root/hxy`

## Mission

HXY is the independent operating system for 荷小悦.

It is not htops.
It is not 荷塘悦色.
It must not share business data with 荷塘悦色.

## Project Constitution

The canonical constitution is
`docs/project-brain/governance/00-project-constitution.md`. Every product,
architecture, engineering, data, AI, and operating decision must follow it.

In particular:

1. Start from the business outcome, user action, causal mechanism, evidence,
   constraints, and falsifiable success metric. Do not start from a requested
   feature, framework, model, or fashionable architecture.
2. A user request is important evidence and a constraint, not automatically the
   product conclusion. Challenge weak assumptions and choose the best option for
   HXY's mission.
3. Before building a capability, investigate mature products, open-source
   projects, standards, and current AI capabilities. Record the decision as
   `adopt`, `embed`, `sidecar`, `reference`, `build`, or `reject`.
4. Build HXY's differentiated control plane: organization and permissions,
   operating events and state, responsibility, evidence, audit, governed formal
   knowledge, metric facts, and value proof. Reuse commodity capabilities such
   as chat surfaces, upload preview, Wiki editing, OCR/parsing, generic RAG,
   observability, and admin CRUD unless a documented gap requires otherwise.
5. “Optimal” means the best evidence-backed choice under current stage,
   constraints, total cost, risk, reversibility, and time-to-learning. More
   technology and more abstraction are not inherently better.
6. Separate facts, assumptions, proposals, and approved decisions. AI may draft,
   analyze, compare, test, and recommend, but it must not silently approve formal
   knowledge, change governed operating state, or manufacture metric facts.
7. Validate with the smallest end-to-end business loop that can disprove the
   thesis. Prefer measured user and operating outcomes over feature count.
8. Major choices require an ADR or adoption record containing alternatives,
   evidence, trade-offs, exit conditions, and a review date.

## Core Boundary

```text
/root/htops/  # 荷塘悦色 only
/root/hxy/    # 荷小悦 only
```

Reusable engineering patterns are allowed.
Shared business data is not allowed.

## Rules

1. Do not write HXY menu, order, member, technician, store, or memory data into htops databases.
2. Do not import 荷塘悦色 store, groupbuy, member, order, technician, or operating data into HXY.
3. Use HXY-owned directories for HXY work:
   - `apps/`
   - `packages/`
   - `knowledge/`
   - `data/`
   - `docs/`
   - `ops/`
   - `scripts/`
   - `tests/`
4. Migration from htops must be copy-first. Do not delete source files until a backup, manifest, verification report, and explicit cleanup step exist.
5. Any generic code extracted for reuse must be free of brand, store, member, order, technician, and knowledge data.
6. HXY service names should use `hxy-*`, not `htops-*`.
7. HXY API routes should use HXY-owned API services, not htops `api/main.py`.

## Product Scope

HXY owns:

- 菜单系统
- 用户前端
- 管理后台
- 员工/技师端
- 清泡调补养产品体系
- HXY 知识库
- HXY Memory Service
- HXY 项目大脑
- HXY 门店经营系统

## Migration Status

This directory currently contains assets copied from `/root/htops`.

Until final cleanup is completed:

- htops remains the source copy for some historical files.
- HXY should become the new owner of copied assets.
- Deletion from htops requires a separate cleanup plan.
