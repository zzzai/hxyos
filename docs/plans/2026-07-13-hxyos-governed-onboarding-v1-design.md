# HXYOS Governed Onboarding V1 Design

## Status

Approved on 2026-07-13.

## Goal

让 HXYOS 从“只有 Founder 能登录”变成可由组织自行开通的多岗位系统，同时保持极简产品体验和严格的数据权限：

```text
Founder 创建门店 -> 邀请店长 -> 店长邀请本店员工 -> 一次性链接登录
```

该能力只管理 HXY 自有门店、账号、岗位和 session，不读取或写入 `/root/htops`，不修改核心知识。

## Product Principles

1. 不设默认密码，不在聊天、日志或数据库保存原始邀请 token。
2. 邀请不是正式身份。只有成功兑换后才创建账号和岗位 assignment。
3. Founder 只能邀请店长；店长只能邀请自己门店的员工。
4. 普通员工不能邀请成员、切换角色或访问其他门店。
5. 组织与门店边界由服务端从当前 session 推导，不能相信客户端提交的 organization。
6. 邀请可以撤销，成员可以停用，所有状态变化必须可审计。
7. 前台只提供极简成员入口，审核、审计和运行记录不堆到普通用户页面。

## Chosen Approach

采用 HXYOS 自有的受治理邀请机制。

不采用 Founder 包办所有账号的集中模式，因为扩店后会形成组织瓶颈。第一版也不直接接企业 IAM、飞书通讯录或复杂密码系统，因为它们会扩大身份面和运维复杂度。当前方案保留后续接飞书安全分发一次性链接的接口，但身份和授权仍由 HXYOS 控制。

## Roles And Authority

### Founder

- 查看本组织门店和成员。
- 创建 HXY 门店。
- 为指定门店邀请一名或多名店长。
- 撤销未兑换的店长邀请。
- 停用店长 assignment。
- 不通过该流程直接邀请普通员工。

### Store Manager

- 只查看自己的门店和本店成员。
- 只邀请 `store_employee`。
- 撤销自己门店的未兑换员工邀请。
- 停用本店员工 assignment。
- 不能停用自己、创建门店、邀请店长或访问其他门店。

### Store Employee

- 查看自己的身份和门店。
- 无成员管理能力。
- 通过现有问答、训练、问题上报和待办能力工作。

## User Experience

### Computer And Mobile

现有主对话框继续是第一入口。“我的”页面不做管理后台，只增加一个安静的组织入口：

```text
当前身份 / 当前门店
门店与成员（Founder / 店长可见）
退出登录
```

Founder 的“门店与成员”流程：

```text
门店列表 -> 新建门店 -> 选择门店 -> 邀请店长 -> 复制一次性链接
```

店长的流程：

```text
本店成员 -> 邀请员工 -> 复制一次性链接
```

邀请链接只在创建成功后显示一次。成员列表不返回 token，也不重复展示原链接。邀请人在链接丢失时撤销旧邀请并创建新邀请。

移动端保持单列布局。表单最多包含门店名称、城市、地址或成员显示名，不要求用户理解 organization id、store id、assignment id、token、权限表等技术概念。

## Data Model

新增 migration `017_hxy_governed_onboarding.sql`。

### `hxy_member_invites`

```text
invite_id UUID primary key
organization_id UUID not null
store_id TEXT not null
role TEXT: store_manager | store_employee
display_name TEXT not null
token_hash TEXT unique not null
created_by_assignment_id UUID not null
status TEXT: pending | redeemed | revoked
expires_at TIMESTAMPTZ not null
redeemed_account_id UUID nullable
redeemed_assignment_id UUID nullable
redeemed_at TIMESTAMPTZ nullable
revoked_at TIMESTAMPTZ nullable
created_at TIMESTAMPTZ not null
updated_at TIMESTAMPTZ not null
```

约束必须保证 organization、store、creator assignment 和 redeemed assignment 属于同一 HXY 边界。原始 token 永远不入库。

### `hxy_member_invite_events`

append-only 记录：

```text
created
redeemed
revoked
member_deactivated
```

禁止 update、delete 和 truncate。事件 payload 只保存非敏感标识和状态，不保存原始 token、资料内容或个人敏感信息。

### Existing Tables

兑换邀请时复用：

```text
stores
hxy_organization_stores
staff_accounts
hxy_role_assignments
staff_sessions
```

`staff_accounts.username` 由服务端生成，不作为用户登录凭据。`password_hash` 使用不可登录的 invite-only marker。岗位映射：

```text
store_manager -> staff_accounts.role = store_manager
store_employee -> staff_accounts.role = frontdesk
```

## API Design

### Authenticated Organization APIs

```text
GET  /api/v1/organization/stores
POST /api/v1/organization/stores
GET  /api/v1/organization/members
GET  /api/v1/organization/invites
POST /api/v1/organization/invites
POST /api/v1/organization/invites/{invite_id}/revoke
POST /api/v1/organization/members/{assignment_id}/deactivate
```

邀请创建接口返回一次：

```json
{
  "invite": {
    "id": "uuid",
    "role": "store_employee",
    "display_name": "成员显示名",
    "expires_at": "timestamp"
  },
  "one_time_link": "https://hxyos.hexiaoyue.com/#invite=..."
}
```

列表接口永不返回 `token_hash` 或 `one_time_link`。

### Public Redemption API

```text
POST /api/v1/onboarding/invites/redeem
```

请求体只包含原始 invite token。服务端在一个 transaction 中完成：

```text
SHA-256 token
-> SELECT pending invite FOR UPDATE
-> 检查未过期/未撤销/未兑换
-> 创建 staff account
-> 创建 HXY role assignment
-> 标记 invite redeemed
-> 写 append-only event
-> 创建随机正常 session
-> 设置 Secure HttpOnly SameSite=Lax cookie
```

无效、过期、撤销、重复兑换统一返回 `401`，不泄露邀请是否存在。兑换成功后前端立即清除 URL fragment。

## Security And Governance

- 原始 token 至少 256 bits entropy，数据库只保存 SHA-256。
- 默认有效期 24 小时，服务端拒绝超过上限的 TTL。
- token 只能通过 URL fragment 传递，不进入 query string、access log 或 Git。
- 兑换使用 row lock 和 transaction，两个并发请求只能成功一个。
- 创建邀请、撤销、兑换、停用全部写审计事件。
- Founder 和店长不能通过客户端参数扩大权限。
- 停用 assignment 时撤销该 assignment 的全部 session。
- 不自动删除历史 task、training 或 append-only evidence。
- 不创建密码登录、短信验证码或公开注册。

## Error Handling

- 门店重名不作为身份键冲突；`store_id` 由服务端生成。
- 邀请已撤销或兑换：统一不可再次使用。
- 邀请者已停用：未兑换邀请不可继续兑换。
- 门店已关闭：新邀请和兑换均拒绝。
- 店长跨店操作：返回 `404` 或 `403`，不暴露目标是否存在。
- 数据库 transaction 失败：不得留下部分 account、assignment、session 或 event。
- 前端只显示可行动错误，例如“链接已失效，请联系邀请人重新发送”。

## Testing

### Backend

- migration 结构、外键、检查约束、索引和 append-only trigger。
- Founder 创建门店与邀请店长。
- 店长只邀请本店员工。
- 员工无管理权限。
- 跨 organization、跨 store、角色升级和停用自己全部拒绝。
- token 只保存 hash，列表不泄露 token。
- 过期、撤销、重复和并发兑换。
- 兑换 transaction 原子创建 account、assignment、session 和 event。
- 停用成员撤销所有 session。
- PostgreSQL 16 从 `001-016` 升级到 `017` 的真实集成测试。

### Frontend

- Founder 门店与成员流程。
- 店长本店员工邀请流程。
- 员工看不到成员管理入口。
- `#invite=` 兑换成功、失败、fragment 清除和 session 恢复。
- 390x844 与桌面 viewport 无横向溢出、遮挡或不可点击控件。
- 现有主对话框、待办、训练和问题上报不回归。

## Observability

记录受限运行指标：

```text
invite_created
invite_redeemed
invite_revoked
invite_expired
member_deactivated
authorization_denied
```

日志不得记录原始 token、完整请求体、cookie、显示名或内部资料。

## Non-Goals

- 不接飞书通讯录自动同步。
- 不做手机号、邮箱、短信或密码登录。
- 不做批量导入和复杂组织架构。
- 不做员工审批流或把审核工作放到普通用户前台。
- 不修改核心知识、品牌口径、知识审核状态或 `/root/htops`。
- 不在本功能内执行生产 migration 或自动发布。

## Acceptance Criteria

1. Founder 可在电脑和手机上创建门店并生成一次性店长邀请。
2. 店长兑换后只看到自己的门店，并可邀请本店员工。
3. 员工兑换后可直接进入现有问答和训练工作流。
4. 任意越权、跨店、重复兑换和原始 token 泄露测试均失败关闭。
5. 所有邀请与停用动作可审计，核心知识和 htops 零变更。
6. 完整 Python、TypeScript、Web、Playwright、secret scan 和 public code-only preflight 全绿。
