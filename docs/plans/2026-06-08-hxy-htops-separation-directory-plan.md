# HXY 与 htops 完全分离目录规划

## 结论

荷小悦 HXY 与荷塘悦色是两个独立主体，不是同一家公司，也不是同一业务项目。

边界必须改成：

```text
/root/htops/       # 荷塘悦色项目。只保存荷塘悦色门店经营、团购、同步、报表、经营大脑。
/root/hxy/         # 荷小悦项目。只保存荷小悦菜单、品牌、产品、知识库、Memory Service、门店系统。
/root/shared/      # 可选。只保存无业务数据的通用能力包，不保存任何门店、会员、订单、技师、项目知识。
```

当前 `/root/htops` 中的 HXY 文件、接口、数据库表和 nginx 路由只视为迁移源或历史污染面，不再作为 HXY 的长期运行位置。

## 不可违反的边界

1. `htops` 只属于荷塘悦色。
2. `hxy` 只属于荷小悦。
3. 功能可以复用，数据不能复用。
4. HXY 菜单、订单、会员、技师、门店、知识库、Memory Service 不允许继续落在 htops 数据库或 htops API 中。
5. 荷塘悦色迎宾店、美团团购、五店经营同步、门店经营报表属于 htops，不自动归入 HXY。
6. HXY 百店菜单系统中的门店只能是荷小悦门店，不允许默认混入荷塘悦色门店。
7. 迁移采用复制优先，不先删除。验证完成后再做清理。

## 目标目录结构

### `/root/htops`：荷塘悦色项目根

```text
/root/htops/
├── api/                         # 荷塘悦色 API；后续移除 HXY/wellness API
├── src/
│   ├── query-intent.ts           # 荷塘悦色语义意图
│   ├── query-plan.ts             # 荷塘悦色查询计划
│   ├── capability-graph.ts       # htops Capability Graph
│   ├── sql-compiler.ts           # 安全 SQL 编译
│   ├── query-engine.ts           # 荷塘悦色查询执行
│   ├── platform-groupbuy/        # 荷塘悦色团购/平台数据诊断
│   └── proactive-insight/        # 荷塘悦色经营洞察
├── docs/
│   ├── plans/                    # htops 规划；保留本分离规划
│   ├── prompts/
│   └── reviews/
├── knowledge/                    # 荷塘悦色或通用知识；不再放 knowledge/hxy
├── ops/
│   ├── nginx/                    # htops nginx 配置；不再承载 HXY 菜单
│   └── systemd/                  # htops 服务
├── scripts/                      # htops 脚本；不再放 build-hxy-* / import-hxy-*
└── tests/
```

htops 清理后的目标状态：

```text
不得存在：
- docs/wellness-menu/
- docs/wellness-order.html
- docs/wellness-admin.html
- docs/wellness-staff.html
- docs/wellness-technician.html
- projects/hxy/
- knowledge/hxy/
- src/hxy-*
- src/hxy-memory/
- scripts/build-hxy-*
- scripts/import-hxy-memory.ts
- scripts/rebuild-hxy-memory-search.ts
- /api/v1/hxy/*
- /api/v1/wellness/* 作为 HXY 菜单运行接口
```

注意：清理不是第一步。第一步是迁出、验证、切流。

### `/root/hxy`：荷小悦项目根

```text
/root/hxy/
├── AGENTS.md
├── README.md
├── apps/
│   ├── menu-h5/                  # 用户前端菜单：扫码选择、确认、历史订单
│   │   ├── public/
│   │   │   └── assets/
│   │   ├── src/
│   │   └── tests/
│   ├── admin-web/                # 总部/门店管理后台
│   ├── staff-web/                # 前台/员工看单
│   ├── technician-web/           # 技师看单与 SOP
│   └── api/                      # HXY API，独立服务，不挂 htops api/main.py
├── packages/
│   ├── menu-core/                # 菜单品类、项目、选项、发布版本、订单状态模型
│   ├── memory-service/           # HXY Memory Service
│   ├── knowledge-factory/         # HXY 知识清洗、分类、索引、manifest
│   ├── ingestion/                # MarkItDown/OCR/多模态解析适配
│   ├── design-system/            # HXY 浅翠绿色视觉系统、组件规范
│   └── auth-core/                # HXY 角色权限模型
├── knowledge/
│   ├── raw/                      # HXY 原始资料
│   ├── normalized/               # 清洗后的文本
│   ├── structured/               # 决策、假设、模型、证据 JSON
│   ├── index/                    # 文件索引、检索索引
│   ├── manifests/                # 上传、解析、构建 manifest
│   └── reports/                  # doctor、质量报告、低置信清单
├── data/
│   ├── migrations/               # HXY 自己的数据库迁移
│   ├── seeds/                    # HXY 样例门店、菜单、账号种子
│   ├── exports/                  # 从 htops 临时表导出的迁移包
│   └── backups/                  # 迁移前后备份记录
├── docs/
│   ├── plans/                    # HXY 规划
│   ├── decisions/                # HXY ADR / 决策日志
│   ├── product/
│   │   └── menu/                 # 清泡调补养、五行产品体系、菜单设计
│   ├── brand/
│   ├── architecture/
│   ├── project-brain/
│   ├── ui/
│   └── operations/
├── ops/
│   ├── docker/
│   ├── nginx/
│   ├── systemd/
│   └── env/
├── scripts/
│   ├── build-knowledge.ts
│   ├── import-memory.ts
│   ├── rebuild-memory-search.ts
│   └── verify-menu.cjs
└── tests/
```

### `/root/shared`：可选复用能力根

```text
/root/shared/
├── packages/
│   ├── document-ingestion/        # 通用 MarkItDown/OCR 包装，不含业务资料
│   ├── catalog-versioning/        # 通用 catalog 草稿/发布/回滚模型
│   ├── role-auth-patterns/        # 通用 RBAC 帮助逻辑
│   ├── memory-schema-patterns/    # 通用 Memory Service schema 模板
│   └── ui-patterns/               # 通用 UI 交互模式，不含 HXY/荷塘品牌资产
└── README.md
```

共享层只允许放无业务数据、无品牌数据、无门店数据的通用代码。任何 `荷小悦`、`荷塘悦色`、门店名、会员、订单、技师、团购、评价内容都不能进入 `/root/shared`。

## 当前混入 htops 的 HXY 资产迁移表

| 当前位置 | 目标位置 | 动作 | 说明 |
|---|---|---|---|
| `docs/wellness-menu/` | `/root/hxy/apps/menu-h5/` | 复制后改造 | 用户菜单、后台、员工端、技师端都属于 HXY |
| `docs/wellness-order.html` 等散落 HTML | `/root/hxy/apps/menu-h5/legacy/` | 复制归档 | 与 `docs/wellness-menu/` 去重后再决定保留版本 |
| `docs/assets/hxy-wellness/` | `/root/hxy/apps/menu-h5/public/assets/` | 复制 | HXY 菜单视觉资产 |
| `projects/hxy/` | `/root/hxy/docs/project-brain/` 或拆入 `/root/hxy/docs/*` | 复制后重整 | HXY 项目大脑资料，不属于 htops |
| `knowledge/hxy/` | `/root/hxy/knowledge/` | 复制 | raw/normalized/structured/index/reports 整体迁出 |
| `src/hxy-memory/` | `/root/hxy/packages/memory-service/` | 复制后改路径 | HXY Memory Service 所有权迁给 HXY |
| `src/hxy-*.ts` | `/root/hxy/packages/knowledge-factory/` 或 `/root/hxy/packages/project-brain/` | 分类复制 | HXY 品牌、知识、模型脚本迁出 |
| `scripts/build-hxy-*.ts` | `/root/hxy/scripts/` | 复制后改命名 | 去掉在 htops 中的构建入口 |
| `scripts/import-hxy-memory.ts` | `/root/hxy/scripts/import-memory.ts` | 复制后改命名 | 指向 HXY 数据库 |
| `scripts/rebuild-hxy-memory-search.ts` | `/root/hxy/scripts/rebuild-memory-search.ts` | 复制后改命名 | 指向 HXY 数据库 |
| `api/main.py` 中 `/api/v1/hxy/*` | `/root/hxy/apps/api/` | 迁出 | HXY memory API 不允许挂在 htops API |
| `api/main.py` 中 HXY 菜单 `/api/v1/wellness/*` | `/root/hxy/apps/api/` | 迁出并重命名 | 建议改为 `/api/v1/menu/*` 或 `/api/v1/hxy/menu/*` |
| `ops/nginx/htops-wellness-h5.conf` | `/root/hxy/ops/nginx/hxy-menu-h5.conf` | 复制后改服务名 | 当前 nginx 只是临时承载 |
| `ops/systemd/htops-wellness-api.service` | `/root/hxy/ops/systemd/hxy-api.service` | 复制后改服务名 | 服务名不再使用 htops |

## 数据库分离规划

### htops 数据库

用途：

```text
荷塘悦色门店、团购、经营指标、同步任务、语义查询、经营报表。
```

禁止长期保存：

```text
HXY 菜单订单
HXY 用户
HXY 技师
HXY 门店
HXY 会员
HXY Memory Service
HXY 知识检索索引
```

当前已存在的 `hxy_memory_*`、`wellness_*` 表只能作为迁移源。不得继续作为 HXY 生产数据表。

### HXY 数据库

建议独立数据库与独立账号：

```text
database: hxy
user: hxy_app
schema: public 或 hxy_app
service: hxy-postgres / hxy-mysql，按 HXY 技术栈决定
```

HXY 表建议：

```text
stores
staff_accounts
staff_sessions
users
orders
order_status_events
catalogs
catalog_drafts
catalog_versions
memory_items
memory_evidence_links
memory_transitions
memory_import_runs
memory_search_documents
source_assets
knowledge_manifests
```

如果仍使用 `hxy_memory_items` 这类前缀，也必须在 HXY 独立数据库中使用，不能放在 htops 数据库中。

## 服务与路由命名

### htops 保留

```text
htops-query-api.service
htops-bridge.service
htops-scheduled-worker.service
htops-analysis-worker.service
```

### HXY 新建

```text
hxy-api.service
hxy-menu-h5.service       # 如未来改为独立前端服务
hxy-worker.service
hxy-memory-worker.service
```

### nginx

htops nginx 只服务荷塘悦色。

HXY nginx 独立配置：

```text
/root/hxy/ops/nginx/hxy-menu-h5.conf
```

建议 HXY 路由：

```text
/menu/                    # 用户扫码菜单
/admin/                   # HXY 管理后台
/staff/                   # HXY 前台/员工端
/technician/              # HXY 技师端
/api/v1/menu/*            # HXY 菜单 API
/api/v1/memory/*          # HXY Memory API
```

不要继续使用 `htops-wellness-*` 命名。

## 现有 `/root/crmeb-java/hxy` 的处理

当前机器已有：

```text
/root/crmeb-java/hxy/
```

它应被视为 HXY 现有资料/工程资产来源之一，而不是 htops 的一部分。

目录规划上有两个选择：

1. 推荐：建立 `/root/hxy` 作为 HXY 总根目录，将 `/root/crmeb-java/hxy` 按迁移清单并入或作为外部集成引用。
2. 临时：继续让 `/root/crmeb-java/hxy` 保存部分 HXY 资料，但 HXY 菜单和 Memory Service 不再进入 htops。

为了避免 HXY 被 `crmeb-java` 这个工程名限制，长期推荐 `/root/hxy` 为总根。

## 迁移阶段

### Phase 0：冻结边界

立即生效：

```text
不再向 /root/htops 新增 HXY 菜单、HXY Memory、HXY 知识库功能。
不再把 HXY 数据写入 htops PostgreSQL。
不再在 htops api/main.py 扩展 HXY API。
```

### Phase 1：创建 HXY 独立根目录

创建：

```text
/root/hxy/
/root/hxy/apps/
/root/hxy/packages/
/root/hxy/knowledge/
/root/hxy/data/
/root/hxy/docs/
/root/hxy/ops/
/root/hxy/scripts/
/root/hxy/tests/
```

写入：

```text
/root/hxy/README.md
/root/hxy/AGENTS.md
/root/hxy/docs/plans/2026-06-08-hxy-htops-separation-directory-plan.md
```

### Phase 2：复制 HXY 文件资产

只复制，不删除：

```text
docs/wellness-menu/        -> /root/hxy/apps/menu-h5/
projects/hxy/              -> /root/hxy/docs/project-brain/
knowledge/hxy/             -> /root/hxy/knowledge/
src/hxy-memory/            -> /root/hxy/packages/memory-service/
src/hxy-*.ts               -> /root/hxy/packages/knowledge-factory/ 或 project-brain/
scripts/*hxy*.ts           -> /root/hxy/scripts/
ops/*wellness*             -> /root/hxy/ops/
```

复制后生成迁移 manifest：

```text
/root/hxy/data/exports/2026-06-08-from-htops-file-manifest.json
```

### Phase 3：创建 HXY 独立数据库

动作：

```text
创建 HXY 数据库/容器/账号。
把 htops 中临时 HXY 表导出到 /root/hxy/data/exports/。
导入 HXY 独立数据库。
运行 HXY API 指向新数据库。
```

明确禁止：

```text
直接让 HXY API 继续连 hetang-ops-postgres。
```

### Phase 4：切换 HXY 服务

动作：

```text
启动 hxy-api.service。
部署 hxy nginx 配置。
把菜单入口从 htops 静态页切到 /root/hxy/apps/menu-h5。
验证用户端、后台、员工端、技师端都读写 HXY 数据库。
```

### Phase 5：清理 htops 污染面

只有 Phase 1-4 验证完成后才能清理。

清理顺序：

```text
1. 从 htops nginx 移除 HXY 路由。
2. 从 htops systemd 移除 HXY 服务。
3. 从 api/main.py 移除 HXY 菜单和 memory API。
4. 从 htops scripts/src/docs/knowledge 中移除已迁出的 HXY 文件。
5. 备份确认后，再处理 htops PostgreSQL 中 hxy_memory_* 和 wellness_* 临时表。
```

清理前必须有：

```text
/root/hxy/data/backups/
/root/hxy/data/exports/
迁移校验报告
可回滚说明
```

## 复用策略

允许复用：

```text
目录规划方法
角色权限模型
菜单草稿/发布/回滚机制
订单状态机模式
Memory Service schema 模式
MarkItDown/OCR 解析适配方式
前端交互模式
测试脚本模式
```

禁止复用：

```text
htops 数据库
荷塘悦色门店数据
荷塘悦色会员/订单/技师数据
美团团购数据
荷塘悦色经营指标
荷塘悦色项目知识
任何真实顾客隐私数据
```

## 验收标准

目录级验收：

```text
/root/htops 下不再有 HXY 运行代码和 HXY 数据目录。
/root/hxy 下具备 HXY 菜单、知识库、Memory Service、API、ops 的完整目录。
```

运行级验收：

```text
htops 服务正常回答荷塘悦色问题。
HXY 菜单服务正常提交和查看 HXY 订单。
HXY 后台正常管理 HXY 项目与门店。
HXY Memory API 正常查询 HXY 知识。
两边数据库连接串、表、账号完全不同。
```

数据级验收：

```text
HXY 数据库不包含荷塘悦色门店/订单/会员/技师数据。
htops 数据库不再新增 HXY 菜单/Memory 数据。
迁移前后 HXY 文件数、structured JSON 数、memory item 数有校验报告。
```

安全级验收：

```text
迁移过程没有直接删除源文件。
迁移过程有 manifest。
清理前有备份。
所有 DROP/删除动作单独列清单，确认后执行。
```

## 近期执行顺序

推荐接下来按这个顺序做：

```text
1. 创建 /root/hxy 目录骨架。
2. 复制 HXY 菜单、知识、项目资料、Memory Service 到 /root/hxy。
3. 为 HXY 写独立 AGENTS.md 和 README.md。
4. 建 HXY 独立数据库配置与迁移脚本。
5. 把 HXY API 从 htops api/main.py 拆到 /root/hxy/apps/api。
6. 启动 hxy-api.service 和 HXY nginx。
7. 验证 HXY 菜单和 Memory API 使用 HXY 数据库。
8. 再提交 htops 清理计划，最后处理删除和 DROP。
```

## 当前状态判断

当前不是“已分离”，而是：

```text
HXY 文件资产散落在 htops。
HXY 菜单运行面挂在 htops。
HXY Memory 表临时进入 htops PostgreSQL。
HXY 规划文档进入 htops docs/plans。
部分 HXY 菜单默认门店混入了荷塘悦色门店。
```

所以当前第一优先级不是继续优化菜单 UI，也不是继续完善 htops API，而是先完成 HXY 独立根目录和数据边界迁移。
