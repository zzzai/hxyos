# HXY Material Intake Runtime

## Boundary

The material worker processes private HXY uploads only.

```text
original
-> durable parser job
-> normalized Markdown
-> Source Card
-> assignment-private chunks
-> governed conversation reference
-> bounded answer Trace
```

所有上传资料和衍生产物都保持 `working_context/reference` 与
`official_use_allowed=false`。它们可以在所属岗位身份的对话中作为上下文提醒并附带可授权访问的
资料引用，但不得自动进入正式知识、返回 `已批准`、写入长期记忆或替代 approved answer card。

## Prerequisites

1. Install API dependencies in `/root/hxy/.venv`.
2. Configure `HXY_DATABASE_URL` in `/root/hxy/ops/env/hxy-knowledge-api.env`.
3. Apply migrations through `014_hxy_knowledge_activation.sql`.
4. Ensure `/root/hxy/data/product-materials` exists and is owned by the service account.

Apply migrations:

```bash
cd /root/hxy
HXY_ENV_FILE=/root/hxy/ops/env/hxy-knowledge-api.env \
  bash scripts/apply-db-migrations.sh
```

该命令仅用于开发/全新数据库初始化。生产启用 Knowledge Activation Loop V1 必须使用
`docs/operations/hxy-knowledge-activation-release.md` 中的预检、备份、限定迁移与灰度 Gate。

## One-Shot Check

Run one claim cycle without installing systemd:

```bash
cd /root/hxy
bash ops/hxy-material-worker.sh --once
```

Expected output is one JSON line with `idle`, `succeeded`, `retryable_failed`, or `permanent_failed`. It must not include source paths or stack traces.

成功完成后，normalized Markdown 的分块与解析产物在同一数据库事务中落库。资料只有在状态为
`ready` 时才可检索；检索必须始终携带服务端解析出的 `assignment_id`，不得接受客户端传入的
岗位身份作为授权依据。

## Conversation Boundary

资料检索结果只通过以下受权路由暴露原文件，不返回服务器路径或 `storage_key`：

```text
/api/v1/materials/<material_id>/content
```

包含私有资料的回答必须保持 `AI 草稿` 与 `needs_review=true`。approved answer card 仍具有正式知识
优先级；聊天、上传资料和过程记忆都不能修改或晋升正式知识。

每次助手完成回答时最多写入一条 `hxy_product_answer_traces` 记录。Trace 只记录岗位、意图、
召回计数、是否命中正式答案卡、模型/token/延迟等有界运行元数据，不复制原文、回答正文、
本地路径、密钥或完整 Prompt。

## Systemd

Install and start only after the one-shot check succeeds:

```bash
install -m 0644 ops/systemd/hxy-material-worker.service \
  /etc/systemd/system/hxy-material-worker.service
systemctl daemon-reload
systemctl enable --now hxy-material-worker
systemctl status hxy-material-worker
```

Inspect recent structured output:

```bash
journalctl -u hxy-material-worker -n 100 --no-pager
```

## Recovery

The worker claims work with a lease. If the process exits, the next worker cycle reclaims the expired lease and retries within the stored attempt budget.

For repeated failures:

1. keep the original file unchanged;
2. inspect `last_error_code`, not raw parser output;
3. verify MarkItDown in the project virtual environment;
4. run one `--once` cycle;
5. use the existing product retry action only after the dependency or file issue is fixed.

Do not edit queue rows manually to mark them `succeeded`. Do not copy any HXY material into `/root/htops`.

## Isolated PostgreSQL Verification

迁移或检索 SQL 变更必须先在独立 PostgreSQL 16 测试库中应用 `001-014`，再运行：

```bash
HXY_TEST_DATABASE_URL="<isolated-test-database-url>" \
  .venv/bin/pytest tests/test_hxy_material_jobs_postgres.py -q
```

测试覆盖租约回收、解析完成、私有分块、关键词检索、最新资料检索、跨岗位隔离与 Trace 幂等。
不要将 `HXY_TEST_DATABASE_URL` 指向生产数据库。
