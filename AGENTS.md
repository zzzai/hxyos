# AGENTS

Project scope: `/root/hxy`

## Mission

HXY is the independent operating system for 荷小悦.

It is not htops.
It is not 荷塘悦色.
It must not share business data with 荷塘悦色.

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
