# 2026-06-10 htops -> HXY 安全迁移摘要

## 本次迁移目标

把已经混入 `/root/htops` 的荷小悦 HXY 资产复制到独立项目根 `/root/hxy`。

本次只做安全迁移：

- 创建 HXY 独立目录。
- 复制 HXY 文件资产。
- 写入 HXY 项目边界说明。
- 导出 htops 中 HXY/wellness 临时表清单和本地 SQL 备份。
- 不删除 htops 源文件。
- 不 DROP htops 数据库表。
- 不切换线上路由。

## 已创建目录

```text
/root/hxy/
├── apps/
├── packages/
├── knowledge/
├── data/
├── docs/
├── ops/
├── scripts/
└── tests/
```

## 已迁移文件资产

| 类型 | 来源 | 目标 |
|---|---|---|
| 菜单 H5 | `/root/htops/docs/wellness-menu/` | `/root/hxy/apps/menu-h5/` |
| 散落菜单 HTML | `/root/htops/docs/wellness-*.html` | `/root/hxy/apps/menu-h5/legacy-root-pages/` |
| 菜单图片资产 | `/root/htops/docs/assets/hxy-wellness/` | `/root/hxy/apps/menu-h5/public/assets/hxy-wellness/` |
| HXY 项目资料 | `/root/htops/projects/hxy/` | `/root/hxy/docs/project-brain/` |
| HXY 知识资产 | `/root/htops/knowledge/hxy/` | `/root/hxy/knowledge/` |
| HXY Memory Service | `/root/htops/src/hxy-memory/` | `/root/hxy/packages/memory-service/src/` |
| HXY 项目大脑 TS 模块 | `/root/htops/src/hxy-*.ts` | `/root/hxy/packages/project-brain/src/` |
| HXY 构建/导入脚本 | `/root/htops/scripts/*hxy*.ts` | `/root/hxy/scripts/` |
| wellness 校验脚本 | `/root/htops/scripts/verify-wellness-*.cjs` | `/root/hxy/scripts/` |
| HXY 历史规划 | `/root/htops/docs/plans/*hxy*/*wellness*/*markitdown*` | `/root/hxy/docs/plans/` |
| 旧 ops 配置 | `/root/htops/ops/*wellness*` | `/root/hxy/ops/` |

## 新增 HXY 边界文件

```text
/root/hxy/README.md
/root/hxy/AGENTS.md
/root/hxy/docs/decisions/ADR-001-separate-from-htops.md
/root/hxy/data/exports/2026-06-10-from-htops-migration-map.json
```

## 迁移清单

```text
/root/hxy/data/exports/2026-06-10-file-list.txt
/root/hxy/data/exports/2026-06-10-file-manifest.sha256
```

当前 `/root/hxy` 文件数：

```text
278
```

## htops 临时表盘点

来源数据库：`hetang-ops-postgres / hetang_ops`

导出文件：

```text
/root/hxy/data/exports/2026-06-10-htops-hxy-table-list.txt
/root/hxy/data/exports/2026-06-10-htops-hxy-table-inventory.tsv
/root/hxy/data/exports/2026-06-10-htops-wellness-store-distribution.tsv
/root/hxy/data/exports/2026-06-10-htops-hxy-wellness-tables.sensitive.sql
```

SQL 备份文件包含敏感数据，权限已设置为 `600`。

表盘点：

| 表 | 行数 |
|---|---:|
| `hxy_memory_evidence_links` | 1287 |
| `hxy_memory_import_runs` | 1 |
| `hxy_memory_items` | 1353 |
| `hxy_memory_search_documents` | 1353 |
| `hxy_memory_transitions` | 0 |
| `wellness_catalog_drafts` | 0 |
| `wellness_catalog_versions` | 4 |
| `wellness_catalogs` | 1 |
| `wellness_order_status_events` | 7 |
| `wellness_orders` | 9 |
| `wellness_staff_accounts` | 1 |
| `wellness_staff_sessions` | 8 |
| `wellness_stores` | 6 |
| `wellness_users` | 1 |

订单门店分布：

| store_id | store_name | order_count |
|---|---|---:|
| `ay-wuyue` | 安阳吾悦广场店 | 7 |
| 空 | 安阳吾悦广场店 | 2 |

## 风险记录

1. htops 里仍有 HXY/wellness API 和临时表，尚未清理。
2. HXY 菜单 legacy 代码里仍可能有 `wellness`、`htops`、`荷塘悦色` 命名，需要后续净化。
3. htops 的 `wellness_stores` 中历史上混入了荷塘悦色门店，不能直接作为 HXY 门店主数据导入。
4. `wellness_staff_sessions` 是运行态 session，原则上不应迁入 HXY 新库，应重新登录生成。
5. HXY API 还没有从 htops `api/main.py` 拆出。

## 下一步

建议下一批迁移：

```text
1. 在 /root/hxy/ops/docker/ 下定义 HXY 独立数据库服务。
2. 在 /root/hxy/apps/api/ 下拆出 HXY API 最小服务。
3. 编写 HXY DB migration：只导入干净 HXY 表，不导入 htops/荷塘悦色门店。
4. 把 menu-h5 的接口地址改为 HXY API。
5. 启动 hxy-api.service。
6. 验证 HXY 菜单读写 HXY 数据库。
7. 另开 htops cleanup 计划，移除 htops 中 HXY 污染面。
```

## 当前结论

HXY 已从 htops 中彻底切分。

当前状态：

```text
文件资产：已复制到 /root/hxy
数据库：已建立 hxy-postgres，clean 库已建表，legacy 导入库已承接 htops 历史表
API：htops 中 HXY/wellness API 已移除
nginx/systemd：htops-wellness 运行入口已停用并移除
htops 源文件：HXY/wellness 文件资产已删除
htops 临时表：HXY/wellness 表已 DROP
```

## HXY 独立数据库

容器：

```text
hxy-postgres
```

监听：

```text
127.0.0.1:55433
```

配置文件：

```text
/root/hxy/ops/docker/docker-compose.yml
/root/hxy/ops/env/hxy-postgres.env
/root/hxy/ops/env/hxy-postgres.env.example
```

本机 env 文件权限为 `600`。

数据库：

```text
hxy                 # HXY clean 业务库
hxy_legacy_import   # 从 htops 导入的历史隔离库
```

clean 库迁移：

```text
/root/hxy/data/migrations/001_hxy_core.sql
/root/hxy/scripts/apply-db-migrations.sh
```

clean 库当前为空表，等待 HXY API 和净化后的种子数据写入。

legacy 导入库已经导入：

| 表 | 行数 |
|---|---:|
| `hxy_memory_evidence_links` | 1287 |
| `hxy_memory_import_runs` | 1 |
| `hxy_memory_items` | 1353 |
| `hxy_memory_transitions` | 0 |
| `wellness_catalog_drafts` | 0 |
| `wellness_catalog_versions` | 4 |
| `wellness_catalogs` | 1 |
| `wellness_order_status_events` | 7 |
| `wellness_orders` | 9 |
| `wellness_staff_accounts` | 1 |
| `wellness_staff_sessions` | 8 |
| `wellness_stores` | 6 |
| `wellness_users` | 1 |

未导入 `hxy_memory_search_documents`，因为它依赖 htops Postgres 中的 `pgvector` 扩展，且本质是可重建搜索索引。HXY 后续应在 clean 库中重新构建 `memory_search_documents`。

## 最终切分记录

完成时间：

```text
2026-06-10
```

htops 中已删除：

```text
projects/hxy/
knowledge/hxy/
docs/wellness-menu/
docs/assets/hxy-wellness/
docs/wellness-*.html
docs/wellness-qrcode.png
src/hxy-memory/
src/hxy-*.ts
scripts/build-hxy-*.ts
scripts/import-hxy-memory.ts
scripts/rebuild-hxy-memory-search.ts
scripts/verify-wellness-*.cjs
ops/htops-wellness-api.sh
ops/nginx/htops-wellness-h5.conf
ops/systemd/htops-wellness-api.service
```

htops API 已移除：

```text
/api/v1/hxy/*
/api/v1/wellness/*
HXY project brain
HXY memory search
HXY wellness menu/order/admin/staff APIs
```

htops 数据库已删除：

```text
hxy_memory_*
wellness_*
```

运行入口已移除：

```text
/etc/systemd/system/htops-wellness-api.service
/etc/nginx/sites-enabled/htops-wellness-h5
/etc/nginx/sites-available/htops-wellness-h5
```

备份：

```text
/root/hxy/data/backups/2026-06-10-htops-hxy-final-split.tar.gz
/root/hxy/data/backups/2026-06-10-htops-hxy-final-split.tar.gz.sha256
/root/hxy/data/backups/2026-06-10-htops-wellness-runtime-etc/
```

验证：

```text
htops 文件/代码扫描：无 HXY/wellness 运行引用
htops DB HXY/wellness 表计数：0
api/main.py py_compile：通过
npx tsc --noEmit：通过
npx vitest run src/personal-knowledge.test.ts：8 tests passed
nginx -t：通过
hxy-postgres：running healthy
hxy_legacy_import：hxy_memory_items=1353, wellness_orders=9
```
