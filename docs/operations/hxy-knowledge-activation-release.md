# HXY Knowledge Activation Release

## Scope

本手册用于 Knowledge Activation Loop V1 的生产启用准备和人工灰度执行。它覆盖：

```text
只读预检
-> 已验证备份
-> 受控迁移 009-014
-> 只读后检
-> API canary
-> worker canary
-> 岗位隔离验收
```

本手册不执行生产部署。执行生产 Gate 必须由负责人另行确认维护窗口、目标 Git 提交和操作人。

整个过程不批准答案卡、不修改核心知识，也不把上传资料晋升为正式知识。

## Stop Rule

**任一 Gate 失败立即停止。** 不得带着 warning 进入下一步，不得手工改数据库状态伪造通过。

停止后保留以下非敏感证据：

- Git commit；
- Gate 名称和退出码；
- release CLI 输出的有界 JSON；
- systemd 状态和时间；
- 备份 manifest 路径与 SHA-256。

不得把数据库密码、API token、模型 Key、完整 DSN、资料原文或 Prompt 写入发布记录。

## Prerequisites

1. 当前目录是 HXY 仓库根目录。
2. `ops/env/hxy-knowledge-api.env` 只存在于服务器本地，权限正确。
3. `pg_dump`、`pg_restore`、`psql` 主版本为 16。
4. `data/backups/knowledge-activation` 位于 HXY 本地数据目录且不进入 Git。
5. API 和 worker 在迁移前保持停止状态。

加载本地环境：

```bash
cd /root/hxy
set -a
source ops/env/hxy-knowledge-api.env
set +a
```

`scripts/apply-db-migrations.sh` 仅用于开发/全新数据库初始化，不是本次生产启用路径。

## Gate 1: Code

在待发布提交上运行：

```bash
npm test
npm run build:web
.venv/bin/python scripts/check-hxy-secrets.py
.venv/bin/python scripts/check-hxy-public-release.py
git status --short --branch
```

通过标准：测试、构建、扫描全部成功，工作树无未提交变更，提交已推送到远端。

## Gate 2: Read-Only Preflight

```bash
.venv/bin/python scripts/hxy-activation-release.py preflight
```

允许 `pending_tables` 列出尚未创建的产品表。以下任一情况必须停止：

- PostgreSQL 不是 16；
- 缺少 `staff_accounts` 或 `stores` 基线表；
- 目标数据库不是 HXY-owned；
- 迁移文件不是精确的 `009-014`；
- 输出状态不是 `passed`。

该命令只执行只读查询，不创建表、不更新数据、不启停服务。

## Gate 3: Verified Backup

```bash
.venv/bin/python scripts/hxy-activation-release.py backup
```

记录输出中的 `manifest_path`，例如：

```bash
export HXY_ACTIVATION_BACKUP_MANIFEST=/root/hxy/data/backups/knowledge-activation/<UTC>/manifest.json
```

确认同目录包含：

```text
hxy-before-activation.dump
manifest.json
```

CLI 已执行 custom-format `pg_dump`、`pg_restore --list`、SHA-256 和文件权限检查。不得修改 dump 或 manifest。

## Gate 4: Apply 009-014

先再次确认 API 和 worker 未运行。然后使用精确确认词：

```bash
.venv/bin/python scripts/hxy-activation-release.py apply \
  --backup-manifest "$HXY_ACTIVATION_BACKUP_MANIFEST" \
  --confirm APPLY-HXY-009-014
```

通过标准：

- manifest 不超过 24 小时；
- 数据库身份、dump 校验和、迁移校验和全部匹配；
- `psql` 在一个 transaction 中持有 advisory lock；
- 只执行 `009-014`；
- SQL 错误时整个 transaction 回滚；
- 自动 postflight 返回 `passed`。

## Gate 5: Read-Only Postflight

即使 apply 已自动执行后检，也要单独保存一次结果：

```bash
.venv/bin/python scripts/hxy-activation-release.py postflight
```

必须确认：

- product identity、conversation、material、parser job、artifact、private chunk 和 Trace 表存在；
- material、artifact、private chunk 都有 `official_use_allowed=false` 约束；
- private chunk 受 assignment/material 外键约束；
- 每个 assistant message 最多一条 Trace；
- 私有资料 trigram 索引存在。

## Gate 6: API Canary

只启动 API：

```bash
systemctl start hxy-knowledge-api
systemctl status hxy-knowledge-api --no-pager
curl --fail --silent http://127.0.0.1:18081/health
```

随后用一个已授权测试账号完成登录和当前 assignment 查询。API 健康但身份解析失败，也必须停止，不得启动 worker。

检查日志只看错误码和结构化状态，不在发布记录中粘贴请求 token：

```bash
journalctl -u hxy-knowledge-api -n 100 --no-pager
```

## Gate 7: Worker Canary

API Gate 通过后才启动 worker：

```bash
systemctl start hxy-material-worker
systemctl status hxy-material-worker --no-pager
journalctl -u hxy-material-worker -n 100 --no-pager
```

worker 空闲时应返回或记录 `idle`，不得因没有任务而持续报错。

## Gate 8: Assignment-Isolation Acceptance

使用无敏感内容的测试 Markdown 完成一次受控验收：

1. 在测试账号的当前 assignment 上传文件。
2. 等待资料状态变为 `ready`。
3. 用文件中的唯一关键词提问。
4. 回答必须标记为 `AI 草稿`，必须有受权 source link，不能显示 `已批准`。
5. 使用另一个 assignment 提问相同关键词，必须不能召回前一个 assignment 的资料。
6. 检查只产生一条 bounded answer Trace。
7. 验收结束后将测试资料执行 archive，不批准答案卡、不修改核心知识。

任何本地文件路径、`storage_key` 或其他岗位资料出现在响应中，都视为发布失败。

## Rollback Boundary

出现 API 或 worker 代码回归时：

```text
先停 worker，再回滚 API 代码
```

迁移 `009-014` 以新增结构和兼容性变更为主，优先保留数据库结构并回滚应用代码。不要在服务仍写入时删除新表或恢复旧 dump。

本流程不自动执行数据库恢复。数据库恢复会丢弃备份时间之后的写入，只能在单独维护窗口中进行，并要求：

1. API 与 worker 全部停止；
2. 负责人二次确认数据损失范围；
3. 再次验证 manifest、dump SHA-256 和 `pg_restore --list`；
4. 恢复到新的隔离数据库先验收；
5. 通过后另行决定是否切换生产数据库。

不得把 restore 作为普通代码回滚步骤。

## Completion Record

发布完成记录只包含：

```text
release commit
operator
maintenance window
backup manifest path and checksum
preflight/postflight status
API and worker activation time
assignment-isolation result
rollback decision
```

上传资料仍然是 `working_context/reference`；本次启用不改变知识权威边界。

首次 identity canary 使用 `docs/operations/hxy-founder-bootstrap.md`。在 founder assignment 和
`/api/v1/me` 验证通过前，不得启动 material worker。
