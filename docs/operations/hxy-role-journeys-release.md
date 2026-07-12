# HXY Role Journeys Internal Release

## Scope

本手册只用于 HXY Role Journeys `015-016` 的内部发布。GitHub 仅用于内部代码仓，
不创建公开项目描述、营销 README 或公开 roadmap。

本次发布不得修改核心知识，不得批准或发布知识内容，不得向 `/root/htops` 写入。
所有代码、备份、运行记录和服务路径必须由 HXY 自有目录承载。

边界规范：不得向 /root/htops 写入；release source 必须是位于 exact target commit 的
clean immutable release worktree。

`/root/hxy` 当前是脏工作树，不得作为 release source。它只能作为 Git 管理入口、
本地环境文件和 HXY 私有备份的宿主。生产进程必须从 clean immutable release
worktree 对应的 versioned release path 启动。

## Stop Rule

以下 Gate 必须依次执行。任一命令失败、状态不是 `passed`、证据不完整或目标 commit
发生变化，立即停止；不得跳过、补写结果或带 warning 进入下一 Gate。

发布记录不得记录密码、token、完整 DSN 或私有资料，也不得粘贴请求头、资料原文、
用户资料、员工资料、门店经营数据或数据库行内容。只记录 commit、时间、退出码、
有界状态和校验和。

## Gate 1: Immutable Release Source

负责人先批准 exact target commit。使用完整 40 位 commit，不使用分支名、tag、短 SHA
或会移动的远端引用作为最终发布标识。

```bash
export HXY_RELEASE_COMMIT='<approved-40-character-commit>'
export HXY_RELEASE_PATH="/root/hxy/releases/role-journeys/${HXY_RELEASE_COMMIT}"

git -C /root/hxy rev-parse --verify "${HXY_RELEASE_COMMIT}^{commit}"
git -C /root/hxy worktree add --detach "$HXY_RELEASE_PATH" "$HXY_RELEASE_COMMIT"
git -C "$HXY_RELEASE_PATH" status --porcelain=v1 --untracked-files=all
test "$(git -C "$HXY_RELEASE_PATH" rev-parse HEAD)" = "$HXY_RELEASE_COMMIT"
```

通过标准：最后两个命令分别输出空状态和精确 commit。不得清理、stash、reset 或覆盖
`/root/hxy` 来伪造 clean 状态。release worktree 创建后不再改源文件；依赖目录和构建
产物必须属于 Git 忽略的运行产物。

## Gate 2: Code And Public Preflight

只在 versioned release path 中运行代码测试和 secret/public preflight：

```bash
cd "$HXY_RELEASE_PATH"
python3 -m venv .venv
.venv/bin/pip install --requirement apps/api/requirements.txt
npm ci
npm --prefix apps/hxy-web ci
.venv/bin/pytest tests/test_hxy_role_journeys_release.py -q
npm test
npm run build:web
printf '%s\n' "$HXY_RELEASE_COMMIT" \
  > "$HXY_RELEASE_PATH/apps/hxy-web/dist/release-commit.txt"
test "$(wc -l < "$HXY_RELEASE_PATH/apps/hxy-web/dist/release-commit.txt")" -eq 1
test "$(cat "$HXY_RELEASE_PATH/apps/hxy-web/dist/release-commit.txt")" = "$HXY_RELEASE_COMMIT"
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check
git status --porcelain=v1 --untracked-files=all
```

`release-commit.txt` 必须在 build 后生成，只写 `$HXY_RELEASE_COMMIT` 和一个结尾换行，
不得写时间、分支、路径、凭据或其他内容。

通过标准：测试、Web 构建、secret 检查、public release 检查和 whitespace 检查全部
成功；Git 状态仅允许 release 工具显式放行的本地依赖 symlink。public release 检查
用于证明内部代码仓不包含私有业务数据，不代表要创建公开仓库或项目介绍。

## Gate 3: Read-Only Role Release Preflight

由授权操作人通过服务器本地环境加载数据库连接，但不显示、不复制连接值。随后执行
只读 role release preflight：

```bash
cd "$HXY_RELEASE_PATH"
.venv/bin/python scripts/hxy-role-journeys-release.py preflight
```

通过标准：输出为有界 JSON，`status` 为 `passed`，Git commit 与
`$HXY_RELEASE_COMMIT` 一致，并确认 `009-014` 激活前置结构、assignment session scope、
HXY 仓库/数据库边界和 PostgreSQL 主版本。该 Gate 只能读数据库，不创建、更新、删除
任何数据。出现 HXY 边界不匹配或任何 htops 标识立即停止。

## Gate 4: Verified Restorable Backup

创建迁移前的完整、可恢复验证备份：

```bash
cd "$HXY_RELEASE_PATH"
.venv/bin/python scripts/hxy-role-journeys-release.py backup
```

命令必须在 `/root/hxy/data/backups/role-journeys/<UTC>/` 生成：

```text
hxy-before-role-journeys.dump
manifest.json
```

该 backup Gate 必须完成 custom-format 全库 dump、`pg_restore --list`、临时隔离数据库
的完整恢复验证、临时库清理、dump 大小与 SHA-256 记录，并将数据库身份、exact target
commit、`015-016` 文件清单及校验和写入 `manifest.json`。目录权限必须为 `0700`，
dump 和 manifest 权限必须为 `0600`。

不得只以 `pg_restore --list` 成功代替完整恢复验证；临时隔离数据库的创建、restore 和
清理任一步失败都必须停止。

保存 CLI 返回的 `manifest_path` 到当前维护会话的环境变量，不写入 shell history 或
发布文档：

```bash
read -r HXY_ROLE_BACKUP_MANIFEST
export HXY_ROLE_BACKUP_MANIFEST
test -f "$HXY_ROLE_BACKUP_MANIFEST"
pg_restore --list "$(dirname "$HXY_ROLE_BACKUP_MANIFEST")/hxy-before-role-journeys.dump" >/dev/null
```

通过标准：manifest 未超过 24 小时，恢复验证成功，dump 与 manifest 均未被修改，且
它们绑定当前数据库、当前 commit 和精确的 `015-016` migration inventory。没有 verified
backup 和 manifest 时不得 apply。

## Gate 5: Transactional Apply 015-016

再次确认 API、worker 和 Web 写路径未切到新 release。使用精确确认词：

```bash
cd "$HXY_RELEASE_PATH"
.venv/bin/python scripts/hxy-role-journeys-release.py apply \
  --backup-manifest "$HXY_ROLE_BACKUP_MANIFEST" \
  --confirm APPLY-HXY-015-016
```

通过标准：工具在执行任何 SQL 前重新检查 clean worktree、commit、manifest、数据库身份、
恢复验证和 migration checksum；随后只执行 `015_hxy_product_tasks.sql` 与
`016_hxy_product_training.sql`。两份 migration 必须通过 `--single-transaction`、
`ON_ERROR_STOP=1` 和同一个 transaction-scoped advisory lock 执行。任一 SQL 失败时两份
migration 一起回滚。不得分开执行，不得手工重放单个文件。

## Gate 6: Read-Only Postflight

即使 apply 已执行自动后检，也必须单独保存一次只读结果：

```bash
cd "$HXY_RELEASE_PATH"
.venv/bin/python scripts/hxy-role-journeys-release.py postflight
```

必须确认 task、task event、training session 表，`parent_task_id`，同门店 parent 外键，
organization/store/assignment 外键，task event 与 training append-only triggers，以及
active-task/training indexes 全部存在且定义正确。该 Gate 不修数据、不改 schema。

postflight 不是 `passed` 时不得启动新 API 或 Web。

## Gate 7: API Activation From Versioned Release

API systemd unit 必须预先使用 `/root/hxy/releases/current`，并保留服务器本地环境文件：

```ini
[Service]
WorkingDirectory=/root/hxy/releases/current
Environment=HXY_ROOT_DIR=/root/hxy/releases/current
Environment=HXY_ENV_FILE=/root/hxy/ops/env/hxy-knowledge-api.env
Environment=HXY_API_PYTHON=/root/hxy/releases/current/.venv/bin/python
ExecStart=
ExecStart=/usr/bin/env bash /root/hxy/releases/current/ops/hxy-knowledge-api.sh
```

若 `systemctl cat hxy-knowledge-api` 仍把 `WorkingDirectory`、`HXY_ROOT_DIR`、
`HXY_API_PYTHON` 或 `ExecStart` 指向非 release 路径，立即停止。API 必须从 versioned
release path 启动，不能从脏工作树启动。

API 与 Web 共用一个 release 指针。先保留旧 release，再用一次 rename 完成 atomic
service switch：

该 symlink rename 是唯一的 atomic service switch；任何逐目录复制或分别切换 API/Web
路径的做法都必须停止。

```bash
mkdir -p /root/hxy/releases
export HXY_PREVIOUS_RELEASE_PATH="$(readlink -f /root/hxy/releases/current)"
test -d "$HXY_PREVIOUS_RELEASE_PATH"
ln -sfn "$HXY_PREVIOUS_RELEASE_PATH" /root/hxy/releases/previous.next
mv -Tf /root/hxy/releases/previous.next /root/hxy/releases/previous
ln -sfn "$HXY_RELEASE_PATH" /root/hxy/releases/current.next
mv -Tf /root/hxy/releases/current.next /root/hxy/releases/current
```

不得删除、覆盖或改写 `$HXY_PREVIOUS_RELEASE_PATH`；必须保留旧 release，直到 completion
record 完成且维护负责人批准清理。切换后：

```bash
systemctl daemon-reload
systemctl restart hxy-knowledge-api
systemctl status hxy-knowledge-api --no-pager
curl --fail --silent http://127.0.0.1:18081/health
HXY_API_MAIN_PID="$(systemctl show --property MainPID --value hxy-knowledge-api)"
test "$HXY_API_MAIN_PID" -gt 0
test "$(readlink -f "/proc/${HXY_API_MAIN_PID}/cwd")" = "$HXY_RELEASE_PATH"
test "$(readlink -f /root/hxy/releases/current)" = "$HXY_RELEASE_PATH"
```

## Gate 8: Web Activation From Same Commit

本次发布要求 API and web from one commit。Web 构建产物必须是 Gate 2 在
`$HXY_RELEASE_PATH/apps/hxy-web/dist` 生成的产物，Web server 必须从
`/root/hxy/releases/current/apps/hxy-web/dist` 提供文件，不得复制到另一个未绑定 commit
的目录。

```bash
test "$(git -C /root/hxy/releases/current rev-parse HEAD)" = "$HXY_RELEASE_COMMIT"
test -d /root/hxy/releases/current/apps/hxy-web/dist
nginx -t
systemctl reload nginx
export HXY_WEB_RELEASE_MARKER_URL='https://hxyos.hexiaoyue.com/release-commit.txt'
HXY_WEB_RELEASE_COMMIT="$(
  curl --fail --silent --show-error \
    --header 'Cache-Control: no-cache' \
    "$HXY_WEB_RELEASE_MARKER_URL"
)"
test "$HXY_WEB_RELEASE_COMMIT" = "$HXY_RELEASE_COMMIT"
```

验证 API 进程 cwd 和 Web root 最终都解析到 `$HXY_RELEASE_PATH`。HTTP marker 是最终证据；
本地文件、nginx config/root 检查或 `nginx -t` 不能替代线上 marker。Web reload、API
health、marker curl 或 commit 精确比对失败立即执行 Rollback Boundary 的应用回滚，
不得继续角色 canary。

## Gate 9: Role Canaries

只使用无私有内容的专用 canary 账号和测试文本，按以下顺序完成完整闭环：

1. `founder question -> evidence -> task`：问题产生可核对 evidence，并可创建 founder
   可见 task；证据不得暴露内部路径或私有原文。
2. `manager task -> issue -> follow-up`：manager 可看到授权 task，创建关联 issue，并在
   follow-up 中保持 task/issue 关系和门店边界。
3. `employee answer -> practice -> correction -> issue`：employee 从 answer 进入 practice，
   收到 correction，并把需要处理的结果形成 issue；不得获得越权角色或门店数据。

任何一步出现越权、断链、重复写入、错误角色视图或敏感内容泄露，立即停止并应用回滚。

## Gate 10: Mobile Smoke

在至少一个窄屏移动 viewport 完成 mobile smoke：登录、角色首页、问题/任务入口、manager
issue follow-up、employee practice/correction、返回导航和退出登录。检查无横向溢出、
遮挡、不可点击控件、错误角色内容或 API 错误。

移动 smoke 只复用 Gate 9 的无私有 canary 数据，不截图或导出真实用户、员工、门店、
订单、技师或知识资料。

## Gate 11: Completion Record

只有 Gate 1-10 全部通过后才写 completion record。记录：

```text
release commit
previous release commit and retained path
operator and approver
maintenance window
code/secret/public preflight status
read-only preflight and postflight status
backup manifest path, dump SHA-256 and restore-verification status
APPLY-HXY-015-016 result
API and Web activation time and resolved release path
founder/manager/employee canary status
mobile smoke status
rollback decision
```

记录只保存非敏感证据，不包含连接信息、请求凭据、私有资料或业务数据。

## Rollback Boundary

固定原则是 application rollback before database restore。`015-016` 为新增结构，API、Web
或 canary 回归时，优先保留数据库结构并把统一 release 指针原子切回旧版本：

```bash
export HXY_ROLLBACK_PATH="$(readlink -f /root/hxy/releases/previous)"
test -d "$HXY_ROLLBACK_PATH"
export HXY_ROLLBACK_COMMIT="$(git -C "$HXY_ROLLBACK_PATH" rev-parse HEAD)"
ln -sfn "$HXY_ROLLBACK_PATH" /root/hxy/releases/current.next
mv -Tf /root/hxy/releases/current.next /root/hxy/releases/current
test "$(readlink -f /root/hxy/releases/current)" = "$HXY_ROLLBACK_PATH"
systemctl restart hxy-knowledge-api
nginx -t
systemctl reload nginx
curl --fail --silent http://127.0.0.1:18081/health
export HXY_WEB_RELEASE_MARKER_URL='https://hxyos.hexiaoyue.com/release-commit.txt'
HXY_ROLLBACK_WEB_COMMIT="$(
  curl --fail --silent --show-error \
    --header 'Cache-Control: no-cache' \
    "$HXY_WEB_RELEASE_MARKER_URL"
)"
test "$HXY_ROLLBACK_WEB_COMMIT" = "$HXY_ROLLBACK_COMMIT"
```

原子 current 回切、API restart、nginx reload、API health 和旧 commit HTTP marker 任一
验证失败都必须停止并升级处理；不得因此直接进入数据库 restore。

数据库 restore 不是普通 rollback，也不得由本手册自动执行。它可能丢弃 backup 之后的
合法写入，必须在 API、worker 和 Web 写入全部停止后，由数据库维护负责人完成
independent maintenance confirmation，明确数据损失范围，并在新的隔离数据库再次验证
manifest、SHA-256、`pg_restore --list` 和完整恢复后，才可另开维护窗口决定是否切换。

任何 rollback 或 restore 操作都不得读取或写入 `/root/htops`，不得修改核心知识。
