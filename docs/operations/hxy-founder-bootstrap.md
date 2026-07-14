# HXY Founder Bootstrap

## Scope

本手册用于创建 HXYOS 第一个受治理的 founder 身份，并生成一个 10 分钟有效的一次性移动端/电脑端启动链接。

本手册不自动执行 founder 初始化，不启动服务，不创建默认密码，也不批准任何正式知识。

## Preconditions

执行前必须满足：

1. `009-014` 已迁移且 postflight 为 `passed`。
2. 生产备份已通过 `pg_restore --list` 和 SHA-256 验证。
3. founder bootstrap 代码已经过测试并部署到 API release。
4. `staff_accounts`、`hxy_organizations`、`hxy_role_assignments` 均为空。
5. 应用入口使用 HTTPS；只有 `127.0.0.1` 或 `localhost` canary 允许 HTTP。
6. API 与 worker 保持停止，先确认 founder 元数据和应用 URL。

需要负责人确认的元数据：

```text
username              内部稳定标识，例如 founder
display name          产品中显示的姓名
organization slug     建议 hxy
organization name     荷小悦
app URL               实际 HTTPS 访问地址
```

## Bootstrap Gate

加载本地数据库环境：

```bash
cd /root/hxy
set -a
source ops/env/hxy-knowledge-api.env
set +a
```

在已验证的 release 目录执行：

```bash
.venv/bin/python scripts/bootstrap-hxy-founder.py \
  --username "<founder-username>" \
  --display-name "<founder-display-name>" \
  --organization-slug "hxy" \
  --organization-name "荷小悦" \
  --app-url "https://<hxy-app-host>/" \
  --confirm BOOTSTRAP-HXY-FOUNDER
```

CLI 在一个 transaction 中创建：

```text
staff account
HXY organization
founder assignment
10 分钟 bootstrap session grant
```

`password_hash` 是不可用于登录的 gateway-only marker，不创建默认密码。

命令只在 stdout 返回一次 `one_time_link`。不要把链接写入工单、日志、截图、群聊或仓库。URL fragment 不会进入 HTTP access log，但持有链接的人在有效期内可以登录。

## Activation Order

严格保持 API 先于 worker：

1. 启动 API canary。
2. 检查 `/health`。
3. 在目标手机或电脑打开一次性链接。
4. 前端立即清除 URL fragment，并调用 `/api/v1/auth/session-grant`。
5. `/api/v1/me` 必须返回 `founder` 和正确 organization。
6. 创建一条测试 conversation。
7. 上传无敏感内容的测试 Markdown。
8. API、身份、assignment 和资料状态均正常后再启动 worker。
9. 验收完成后 archive 测试资料。

不得在身份 canary 失败时启动 worker。

## Failure Boundary

- 任一步失败立即停止。
- 链接只能交换一次，未知、过期或重复使用统一返回 `401`。
- 链接过期后不要重新执行 bootstrap；该命令要求身份表为空。
- 不要手工把原始 grant 写入 `staff_sessions`，数据库只能保存 SHA-256。
- 不要通过 URL query 传递 grant。
- 不要为了通过验收修改 assignment、cookie 或正式知识状态。

如果初始化 transaction 失败，不应留下部分身份数据。若 transaction 成功但后续 canary 失败，保留 founder 身份并停止服务，先修复代码；删除 founder 身份属于单独的数据治理操作。

## Completion

完成标准：

```text
/health passed
session grant exchanged exactly once
/api/v1/me returns founder assignment
conversation works
test material remains working_context/reference
worker starts after identity acceptance
no default password exists
```

之后 Hermes/飞书只需要安全签发或传递同类一次性入口，不需要在移动端增加登录表单。

## Reissue An Expired Founder Link

Founder 已存在后不得重新运行 bootstrap。首次链接丢失、过期或已消费时，使用独立重签发命令：

```bash
cd /root/hxy/releases/current
set -a
source /root/hxy/ops/env/hxy-knowledge-api.env
set +a

python3 scripts/reissue-hxy-session-link.py \
  --username founder \
  --app-url "https://hxyos.hexiaoyue.com/" \
  --confirm REISSUE-HXY-SESSION-LINK
```

该命令只解析已有的 active Founder assignment，并新增一个单次 grant。有效期由
`HXY_FOUNDER_GRANT_TTL_SECONDS` 独立配置，范围为 60 秒至 24 小时；它不复用
`HXY_AUTH_SESSION_TTL_SECONDS`，也不影响员工邀请有效期。生产环境默认配置为 24 小时，
链接一旦成功交换仍立即失效。

它不创建或修改身份，不创建密码，也不清除已登录设备。数据库只保存 grant 的
SHA-256；原始链接仍然只在 stdout 返回一次，不得写入日志、截图、仓库或群聊。
自动化验收必须使用单独签发的 canary grant 并在验收后退出，禁止消费准备交付给真实
用户的链接。
