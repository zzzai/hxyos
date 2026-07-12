# HXY Role Journeys Internal Release

## Scope

本手册只用于 HXY Role Journeys `015-016` 的内部发布。GitHub 仅用于代码协作，
不需要项目描述，本手册也不增加项目说明。visibility/description 属于仓库管理外部前置，
不作为本次 DB/app release 的自动 Gate。当前未登录 HTTP 可达不等于本 runbook 要修改 visibility。

本次发布不得修改核心知识，不得批准或发布知识内容，不得向 `/root/htops` 写入。
所有代码、备份、运行记录和服务路径必须由 HXY 自有目录承载。

边界规范：不得向 /root/htops 写入；release source 必须是位于 exact target commit 的
clean immutable release worktree。

`/root/hxy` 当前是脏工作树，不得作为 release source。它只能作为 Git 管理入口、
本地环境文件和 HXY 持久数据的宿主。生产进程必须从 clean immutable release
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
`/root/hxy` 来伪造 clean 状态。Gate 2 封存前，release worktree 只能增加忽略的依赖和构建产物。

## Gate 2: Code And Public Preflight

只在 versioned release path 中运行代码测试、构建和 secret/public preflight：

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
不得写时间、分支、路径、凭据或其他内容。上述命令全部成功后，删除 Web 静态运行
不需要的 Node 依赖，再生成外部持久 release seal：

```bash
rm -rf "$HXY_RELEASE_PATH/node_modules"
rm -rf "$HXY_RELEASE_PATH/apps/hxy-web/node_modules"
export HXY_RELEASE_SEAL_DIR=/root/hxy/data/releases/role-journeys
export HXY_RELEASE_SEAL="${HXY_RELEASE_SEAL_DIR}/${HXY_RELEASE_COMMIT}.sha256"
export HXY_RELEASE_SEAL_TMP="${HXY_RELEASE_SEAL_DIR}/.${HXY_RELEASE_COMMIT}.sha256.tmp"
mkdir -p "$HXY_RELEASE_SEAL_DIR"
test ! -e "$HXY_RELEASE_SEAL"
test ! -e "$HXY_RELEASE_SEAL_TMP"
(
  cd "$HXY_RELEASE_PATH"
  find -L . -xdev -type f -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 -r sha256sum
) > "$HXY_RELEASE_SEAL_TMP"
test -s "$HXY_RELEASE_SEAL_TMP"
mv -T "$HXY_RELEASE_SEAL_TMP" "$HXY_RELEASE_SEAL"
chmod 0444 "$HXY_RELEASE_SEAL"
chmod -R a-w "$HXY_RELEASE_PATH"
cd "$HXY_RELEASE_PATH"
sha256sum -c "$HXY_RELEASE_SEAL"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -type f -perm /222 -print -quit)"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -type d -perm /222 -print -quit)"
```

seal 对 release 中全部运行文件和符号链接按路径排序后做 SHA-256，明确包含
source、`dist/` 和 `.venv/`。seal 不能放在 release 内，必须持久保存在
`/root/hxy/data/releases/role-journeys/<commit>.sha256`。`chmod -R a-w` 后不得在 release
内运行会生成文件的命令。

通过标准：测试、Web 构建、secret 检查、public release 检查、whitespace 检查、
seal 校验和无可写文件/目录检查全部成功。public release 检查用于证明代码不包含
私有业务数据，不代表要改动仓库 visibility 或添加 description。

## Gate 3: Read-Only Role Release Preflight

先重新验证 seal 和只读状态，再执行数据库只读 preflight：

```bash
cd "$HXY_RELEASE_PATH"
sha256sum -c "$HXY_RELEASE_SEAL"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -type f -perm /222 -print -quit)"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -type d -perm /222 -print -quit)"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/hxy-role-journeys-release.py preflight
```

通过标准：输出为有界 JSON，`status` 为 `passed`，Git commit 与
`$HXY_RELEASE_COMMIT` 一致，并确认 `009-014` 激活前置结构、assignment session scope、
HXY 仓库/数据库边界和 PostgreSQL 主版本。该 Gate 只能读数据库，不创建、更新、删除
任何数据。出现 HXY 边界不匹配或任何 htops 标识立即停止。

## Gate 4: Verified Restorable Backup

创建迁移前的完整、可恢复验证备份：

```bash
cd "$HXY_RELEASE_PATH"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/hxy-role-journeys-release.py backup
```

命令必须在 `/root/hxy/data/backups/role-journeys/<UTC>/` 生成：

```text
hxy-before-role-journeys.dump
manifest.json
```

该 backup Gate 必须完成 custom-format 全库 dump、`pg_restore --list`、临时隔离数据库
的完整恢复验证、临时库清理、dump 大小与 SHA-256 记录，并将数据库身份、exact target
commit、`015-016` 文件清单及校验和写入 `manifest.json`。目录权限必须为 `0700`，
dump 和 manifest 权限必须为 `0600`。备份只写持久数据根，不得写入 release。

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

在任何数据库写入前再次验证 seal 和 release 只读状态，然后使用精确确认词：

```bash
cd "$HXY_RELEASE_PATH"
sha256sum -c "$HXY_RELEASE_SEAL"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -type f -perm /222 -print -quit)"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -type d -perm /222 -print -quit)"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/hxy-role-journeys-release.py apply \
  --backup-manifest "$HXY_ROLE_BACKUP_MANIFEST" \
  --confirm APPLY-HXY-015-016
```

apply 为精确 migration bytes 创建的 snapshot temp 只能位于持久数据根
`/root/hxy/data/release-tmp`，权限为 `0700`，并在执行后清理。sealed release 内不写入
snapshot temp，也不得为了 apply 临时恢复任何可写权限。

通过标准：工具在执行任何 SQL 前重新检查 clean worktree、commit、manifest、数据库身份、
恢复验证和 migration checksum；随后只执行 `015_hxy_product_tasks.sql` 与
`016_hxy_product_training.sql`。两份 migration 必须通过 `--single-transaction`、
`ON_ERROR_STOP=1` 和同一个 transaction-scoped advisory lock 执行。任一 SQL 失败时两份
migration 一起回滚。不得分开执行，不得手工重放单个文件。

## Gate 6: Read-Only Postflight

即使 apply 已执行自动后检，也必须单独保存一次只读结果：

```bash
cd "$HXY_RELEASE_PATH"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python scripts/hxy-role-journeys-release.py postflight
```

必须确认 task、task event、training session 表，`parent_task_id`，同门店 parent 外键，
organization/store/assignment 外键，task event 与 training append-only triggers，以及
active-task/training indexes 全部存在且定义正确。该 Gate 不修数据、不改 schema。

postflight 不是 `passed` 时不得进入维护切换。

## Gate 7: Maintenance And Atomic Activation

目标 release 先重新通过 seal 与无可写文件/目录检查：

```bash
cd "$HXY_RELEASE_PATH"
sha256sum -c "$HXY_RELEASE_SEAL"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -type f -perm /222 -print -quit)"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -type d -perm /222 -print -quit)"
```

API 与 Web 必须使用已安装的 `hxy-knowledge-api.service` 和 `hxy-product-web.service`。
systemd 服务契约必须与以下架构一致：

```ini
# hxy-knowledge-api.service
[Service]
WorkingDirectory=/root/hxy/releases/current
Environment=HOME=/root
Environment=HXY_ROOT_DIR=/root/hxy
Environment=HXY_ENV_FILE=/root/hxy/ops/env/hxy-knowledge-api.env
Environment=PYTHONPATH=/root/hxy/releases/current/apps/api
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=
ExecStart=/bin/bash -c 'set -a; source /root/hxy/ops/env/hxy-knowledge-api.env; set +a; export HXY_ROOT_DIR=/root/hxy PYTHONPATH=/root/hxy/releases/current/apps/api PYTHONDONTWRITEBYTECODE=1; exec /root/hxy/releases/current/.venv/bin/python -m uvicorn apps.api.hxy_knowledge_api:app --host 127.0.0.1 --port 18081'

# hxy-product-web.service
[Service]
WorkingDirectory=/root/hxy/releases/current/apps/hxy-web/dist
ExecStart=
ExecStart=/usr/bin/python3 -m http.server 18084 --bind 127.0.0.1 --directory /root/hxy/releases/current/apps/hxy-web/dist
```

HXY_ROOT_DIR 是 `/root/hxy` 持久数据根，不是代码发布目录。Python 必须是
`current/.venv/bin/python`，`PYTHONPATH` 必须是 `current/apps/api`；Web 必须直接服务
`current/apps/hxy-web/dist`。环境文件、backup、release seal、日志和其他业务数据均位于
`/root/hxy` 持久路径，不得写入 release。

```bash
systemctl cat hxy-knowledge-api.service
systemctl cat hxy-product-web.service
systemctl show --property WorkingDirectory --property Environment --property ExecStart hxy-knowledge-api.service
systemctl show --property WorkingDirectory --property ExecStart hxy-product-web.service
```

任一配置不符合上述精确路径时立即停止。不得通过调用 release 内会把代码根重定向
`HXY_ROOT_DIR` 的旧启动包装脚本来绕过该契约。

输入已批准的维护窗口或变更单标识，不记录凭据或业务数据：

```bash
read -r -p 'Approved maintenance window/change id: ' HXY_MAINTENANCE_WINDOW
test -n "$HXY_MAINTENANCE_WINDOW"
export HXY_MAINTENANCE_WINDOW
export HXY_WEB_RELEASE_MARKER_URL='https://hxyos.hexiaoyue.com/release-commit.txt'
```

切换前必须把当前 `current` 解析为 previous，并在服务仍运行时验证它是可回滚的完整 release：

```bash
export HXY_PREVIOUS_RELEASE_PATH="$(readlink -f /root/hxy/releases/current)"
test -d "$HXY_PREVIOUS_RELEASE_PATH"
test "$HXY_PREVIOUS_RELEASE_PATH" != "$HXY_RELEASE_PATH"
export HXY_PREVIOUS_GIT_TOPLEVEL="$(git -C "$HXY_PREVIOUS_RELEASE_PATH" rev-parse --show-toplevel)"
export HXY_PREVIOUS_GIT_TOPLEVEL="$(readlink -f "$HXY_PREVIOUS_GIT_TOPLEVEL")"
test "$HXY_PREVIOUS_GIT_TOPLEVEL" = "$HXY_PREVIOUS_RELEASE_PATH"
test -f "$HXY_PREVIOUS_RELEASE_PATH/.git"
test ! -L "$HXY_PREVIOUS_RELEASE_PATH/.git"
export HXY_PREVIOUS_GIT_DIR="$(git -C "$HXY_PREVIOUS_RELEASE_PATH" rev-parse --absolute-git-dir)"
export HXY_PREVIOUS_GIT_DIR="$(readlink -f "$HXY_PREVIOUS_GIT_DIR")"
case "$HXY_PREVIOUS_GIT_DIR" in
  /root/hxy/.git/worktrees/*) ;;
  *) false ;;
esac
test "$(cat "$HXY_PREVIOUS_RELEASE_PATH/.git")" = "gitdir: $HXY_PREVIOUS_GIT_DIR"
export HXY_PREVIOUS_GIT_COMMON_DIR="$(git -C "$HXY_PREVIOUS_RELEASE_PATH" rev-parse --path-format=absolute --git-common-dir)"
test "$(readlink -f "$HXY_PREVIOUS_GIT_COMMON_DIR")" = "$(readlink -f /root/hxy/.git)"
test -z "$(git -C "$HXY_PREVIOUS_RELEASE_PATH" symbolic-ref -q HEAD || true)"
```

上述身份检查必须先于任何 `rev-parse HEAD`。它们证明 resolved top-level 精确是
previous path，`.git` 是指向 `/root/hxy/.git/worktrees/*` 的常规文件，common dir 是
HXY 仓库，且 HEAD 处于 detached 状态。身份检查失败必须立即停止当前发布，不得继续读取
commit、生成 seal 或设置 `previous` 指针。

首次受控发布如果当前 `current` 是 legacy release，而不是上述独立 detached worktree，
该 legacy 目录不能作为 previous。立即结束当前尝试，使用负责人批准的 last-known-good 40 位 commit，
在独立准备会话中按 Gate 1 和 Gate 2 流程重建一个
可回滚 previous 候选。候选必须完成测试、build、release-commit.txt、seal 和只读检查，
然后在备用端口 canary 通过后才能回到本 Gate：

```bash
export HXY_PREVIOUS_CANDIDATE_COMMIT='<approved-last-known-good-40-character-commit>'
test "${#HXY_PREVIOUS_CANDIDATE_COMMIT}" -eq 40
git -C /root/hxy rev-parse --verify "${HXY_PREVIOUS_CANDIDATE_COMMIT}^{commit}"
export HXY_PREVIOUS_CANDIDATE_PATH="/root/hxy/releases/role-journeys/${HXY_PREVIOUS_CANDIDATE_COMMIT}"
```

在独立准备会话中，临时将 Gate 1/2 的 `HXY_RELEASE_COMMIT` 与 `HXY_RELEASE_PATH` 分别设为
`$HXY_PREVIOUS_CANDIDATE_COMMIT` 与 `$HXY_PREVIOUS_CANDIDATE_PATH`，原样执行 Gate 1 和 Gate 2，
不得省略测试、构建、marker、排序 SHA-256 seal 和 `chmod -R a-w`。然后在原发布会话中：

```bash
export HXY_PREVIOUS_RELEASE_PATH="$HXY_PREVIOUS_CANDIDATE_PATH"
export HXY_PREVIOUS_RELEASE_COMMIT="$HXY_PREVIOUS_CANDIDATE_COMMIT"
export HXY_PREVIOUS_SEAL="/root/hxy/data/releases/role-journeys/${HXY_PREVIOUS_RELEASE_COMMIT}.sha256"
cd "$HXY_PREVIOUS_RELEASE_PATH"
sha256sum -c "$HXY_PREVIOUS_SEAL"
test -z "$(find "$HXY_PREVIOUS_RELEASE_PATH" -xdev -type f -perm /222 -print -quit)"
test -z "$(find "$HXY_PREVIOUS_RELEASE_PATH" -xdev -type d -perm /222 -print -quit)"
export HXY_PREVIOUS_CANARY_API_PORT=28081
export HXY_PREVIOUS_CANARY_WEB_PORT=28084
HXY_PREVIOUS_CANARY_API_PID=''
HXY_PREVIOUS_CANARY_WEB_PID=''
cleanup_previous_canary() {
  test -z "${HXY_PREVIOUS_CANARY_WEB_PID:-}" || kill "$HXY_PREVIOUS_CANARY_WEB_PID" 2>/dev/null || true
  test -z "${HXY_PREVIOUS_CANARY_API_PID:-}" || kill "$HXY_PREVIOUS_CANARY_API_PID" 2>/dev/null || true
  test -z "${HXY_PREVIOUS_CANARY_WEB_PID:-}" || wait "$HXY_PREVIOUS_CANARY_WEB_PID" 2>/dev/null || true
  test -z "${HXY_PREVIOUS_CANARY_API_PID:-}" || wait "$HXY_PREVIOUS_CANARY_API_PID" 2>/dev/null || true
}
trap cleanup_previous_canary EXIT
(
  cd "$HXY_PREVIOUS_RELEASE_PATH"
  set -a
  source /root/hxy/ops/env/hxy-knowledge-api.env
  set +a
  export HXY_ROOT_DIR=/root/hxy
  export PYTHONPATH="$HXY_PREVIOUS_RELEASE_PATH/apps/api"
  export PYTHONDONTWRITEBYTECODE=1
  exec "$HXY_PREVIOUS_RELEASE_PATH/.venv/bin/python" -m uvicorn \
    apps.api.hxy_knowledge_api:app --host 127.0.0.1 --port "$HXY_PREVIOUS_CANARY_API_PORT"
) &
HXY_PREVIOUS_CANARY_API_PID="$!"
(
  cd "$HXY_PREVIOUS_RELEASE_PATH/apps/hxy-web/dist"
  exec /usr/bin/python3 -m http.server "$HXY_PREVIOUS_CANARY_WEB_PORT" \
    --bind 127.0.0.1 --directory "$HXY_PREVIOUS_RELEASE_PATH/apps/hxy-web/dist"
) &
HXY_PREVIOUS_CANARY_WEB_PID="$!"
for _attempt in $(seq 1 30); do
  curl --fail --silent "http://127.0.0.1:${HXY_PREVIOUS_CANARY_API_PORT}/health" && break
  sleep 1
done
curl --fail --silent "http://127.0.0.1:${HXY_PREVIOUS_CANARY_API_PORT}/health"
test "$(readlink -f "/proc/${HXY_PREVIOUS_CANARY_API_PID}/cwd")" = "$HXY_PREVIOUS_RELEASE_PATH"
test "$(readlink -f "/proc/${HXY_PREVIOUS_CANARY_WEB_PID}/cwd")" = "$HXY_PREVIOUS_RELEASE_PATH/apps/hxy-web/dist"
HXY_PREVIOUS_CANARY_WEB_COMMIT="$(
  curl --fail --silent --show-error \
    "http://127.0.0.1:${HXY_PREVIOUS_CANARY_WEB_PORT}/release-commit.txt"
)"
test "$HXY_PREVIOUS_CANARY_WEB_COMMIT" = "$HXY_PREVIOUS_RELEASE_COMMIT"
cleanup_previous_canary
trap - EXIT
cd "$HXY_PREVIOUS_RELEASE_PATH"
sha256sum -c "$HXY_PREVIOUS_SEAL"
test -z "$(find "$HXY_PREVIOUS_RELEASE_PATH" -xdev -type f -perm /222 -print -quit)"
test -z "$(find "$HXY_PREVIOUS_RELEASE_PATH" -xdev -type d -perm /222 -print -quit)"
```

候选还必须重新执行上文 `show-toplevel`/`.git`/detached 身份检查。任一构建、seal、只读或
canary 验证失败都立即停止。禁止给 legacy 目录伪造 commit/marker，也不得把父仓库
`HEAD` 或 `.git` 元数据复制进 legacy 目录。

只有标准 current 通过身份检查，或首次受控发布的候选完成重建与 canary 后，才能读取
previous commit 并继续完整性验证：

```bash
export HXY_PREVIOUS_RELEASE_COMMIT="$(git -C "$HXY_PREVIOUS_RELEASE_PATH" rev-parse HEAD)"
test "${#HXY_PREVIOUS_RELEASE_COMMIT}" -eq 40
test "$(git -C "$HXY_PREVIOUS_RELEASE_PATH" rev-parse HEAD)" = "$HXY_PREVIOUS_RELEASE_COMMIT"
test -d "$HXY_PREVIOUS_RELEASE_PATH/apps/hxy-web/dist"
test -f "$HXY_PREVIOUS_RELEASE_PATH/apps/hxy-web/dist/index.html"
test -f "$HXY_PREVIOUS_RELEASE_PATH/apps/hxy-web/dist/release-commit.txt"
test "$(wc -l < "$HXY_PREVIOUS_RELEASE_PATH/apps/hxy-web/dist/release-commit.txt")" -eq 1
test "$(cat "$HXY_PREVIOUS_RELEASE_PATH/apps/hxy-web/dist/release-commit.txt")" = "$HXY_PREVIOUS_RELEASE_COMMIT"
test -x "$HXY_PREVIOUS_RELEASE_PATH/.venv/bin/python"
test -f "$HXY_PREVIOUS_RELEASE_PATH/apps/api/requirements.txt"
"$HXY_PREVIOUS_RELEASE_PATH/.venv/bin/python" -m pip install --dry-run --no-index --requirement "$HXY_PREVIOUS_RELEASE_PATH/apps/api/requirements.txt"
"$HXY_PREVIOUS_RELEASE_PATH/.venv/bin/python" -m pip check
curl --fail --silent http://127.0.0.1:18081/health
HXY_PREVIOUS_API_MAIN_PID="$(systemctl show --property MainPID --value hxy-knowledge-api)"
test "$HXY_PREVIOUS_API_MAIN_PID" -gt 0
test "$(readlink -f "/proc/${HXY_PREVIOUS_API_MAIN_PID}/cwd")" = "$HXY_PREVIOUS_RELEASE_PATH"
HXY_PREVIOUS_WEB_MAIN_PID="$(systemctl show --property MainPID --value hxy-product-web)"
test "$HXY_PREVIOUS_WEB_MAIN_PID" -gt 0
test "$(readlink -f "/proc/${HXY_PREVIOUS_WEB_MAIN_PID}/cwd")" = "$HXY_PREVIOUS_RELEASE_PATH/apps/hxy-web/dist"
HXY_PREVIOUS_WEB_COMMIT="$(
  curl --fail --silent --show-error \
    --header 'Cache-Control: no-cache' \
    "$HXY_WEB_RELEASE_MARKER_URL"
)"
test "$HXY_PREVIOUS_WEB_COMMIT" = "$HXY_PREVIOUS_RELEASE_COMMIT"
```

随后为 previous 生成或复用不可改写的 seal，以只读方式封存并保留旧 release，验证成功后才允许设置
`previous` 指针：

```bash
export HXY_PREVIOUS_SEAL="${HXY_RELEASE_SEAL_DIR}/${HXY_PREVIOUS_RELEASE_COMMIT}.sha256"
export HXY_PREVIOUS_SEAL_TMP="${HXY_RELEASE_SEAL_DIR}/.${HXY_PREVIOUS_RELEASE_COMMIT}.sha256.tmp"
if ! test -f "$HXY_PREVIOUS_SEAL"; then
  test ! -e "$HXY_PREVIOUS_SEAL_TMP"
  (
    cd "$HXY_PREVIOUS_RELEASE_PATH"
    find -L . -xdev -type f -print0 \
      | LC_ALL=C sort -z \
      | xargs -0 -r sha256sum
  ) > "$HXY_PREVIOUS_SEAL_TMP"
  test -s "$HXY_PREVIOUS_SEAL_TMP"
  mv -T "$HXY_PREVIOUS_SEAL_TMP" "$HXY_PREVIOUS_SEAL"
fi
chmod 0444 "$HXY_PREVIOUS_SEAL"
chmod -R a-w "$HXY_PREVIOUS_RELEASE_PATH"
cd "$HXY_PREVIOUS_RELEASE_PATH"
sha256sum -c "$HXY_PREVIOUS_SEAL"
test -z "$(find "$HXY_PREVIOUS_RELEASE_PATH" -xdev -type f -perm /222 -print -quit)"
test -z "$(find "$HXY_PREVIOUS_RELEASE_PATH" -xdev -type d -perm /222 -print -quit)"
ln -sfn "$HXY_PREVIOUS_RELEASE_PATH" /root/hxy/releases/previous.next
mv -Tf /root/hxy/releases/previous.next /root/hxy/releases/previous
```

旧 release 无法满足任一前置验证时禁止发布，不得先切换再尝试修复 previous。
完成 previous 证据后，在原子切换 `current` 前先停止两个服务并确认都为 inactive：

```bash
systemctl stop hxy-product-web hxy-knowledge-api
test "$(systemctl is-active hxy-product-web || true)" = inactive
test "$(systemctl is-active hxy-knowledge-api || true)" = inactive
ln -sfn "$HXY_RELEASE_PATH" /root/hxy/releases/current.next
mv -Tf /root/hxy/releases/current.next /root/hxy/releases/current
test "$(readlink -f /root/hxy/releases/current)" = "$HXY_RELEASE_PATH"
systemctl start hxy-knowledge-api
systemctl start hxy-product-web
```

上述 stop/inactive 检查是本手册的最低维护保护；若站点还有独立的公网维护态，可在 stop 前另行验证。
API 和 Web 共用一个 atomic service switch，不得逐目录复制、分别切换或依赖本机
nginx 动作完成 Web 切换。

## Gate 8: Joint Runtime Verification

两个服务都启动后，必须依次验证 API cwd、Web cwd、API health、本地 marker 和公网 marker：

```bash
test "$(readlink -f /root/hxy/releases/current)" = "$HXY_RELEASE_PATH"
test "$(git -C /root/hxy/releases/current rev-parse HEAD)" = "$HXY_RELEASE_COMMIT"
HXY_API_MAIN_PID="$(systemctl show --property MainPID --value hxy-knowledge-api)"
test "$HXY_API_MAIN_PID" -gt 0
test "$(readlink -f "/proc/${HXY_API_MAIN_PID}/cwd")" = "$HXY_RELEASE_PATH"
HXY_WEB_MAIN_PID="$(systemctl show --property MainPID --value hxy-product-web)"
test "$HXY_WEB_MAIN_PID" -gt 0
test "$(readlink -f "/proc/${HXY_WEB_MAIN_PID}/cwd")" = "$HXY_RELEASE_PATH/apps/hxy-web/dist"
curl --fail --silent http://127.0.0.1:18081/health
HXY_LOCAL_WEB_COMMIT="$(cat /root/hxy/releases/current/apps/hxy-web/dist/release-commit.txt)"
test "$HXY_LOCAL_WEB_COMMIT" = "$HXY_RELEASE_COMMIT"
HXY_WEB_RELEASE_COMMIT="$(
  curl --fail --silent --show-error \
    --header 'Cache-Control: no-cache' \
    "$HXY_WEB_RELEASE_MARKER_URL"
)"
test "$HXY_WEB_RELEASE_COMMIT" = "$HXY_RELEASE_COMMIT"
cd "$HXY_RELEASE_PATH"
sha256sum -c "$HXY_RELEASE_SEAL"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -type f -perm /222 -print -quit)"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -type d -perm /222 -print -quit)"
```

本地 marker 只证明构建产物，HTTP marker 是最终公网证据。双进程 cwd、health、marker、seal
或只读状态任一失败立即执行 Rollback Boundary 的应用回滚，不得继续角色 canary。
本 Gate 不依赖本机 nginx 重载作为 Web 切换或验证证据。本次发布要求
API and web from one commit。

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
release commit, retained path and seal path
previous release commit, retained path and seal path
operator, approver and maintenance window
code/secret/public preflight status
read-only preflight and postflight status
backup manifest path, dump SHA-256 and restore-verification status
APPLY-HXY-015-016 result
API and Web activation time, service names and resolved cwd
local and public release marker status
founder/manager/employee canary status
mobile smoke status
rollback decision
```

记录只保存非敏感证据，不包含连接信息、请求凭据、私有资料或业务数据。

## Rollback Boundary

固定原则是 application rollback before database restore。`015-016` 为新增结构，API、Web
或 canary 回归时，优先保留数据库结构并把统一 release 指针原子切回旧版本。

回滚前必须验证 previous 指针、旧 marker、seal 和只读状态：

```bash
export HXY_ROLLBACK_PATH="$(readlink -f /root/hxy/releases/previous)"
test -d "$HXY_ROLLBACK_PATH"
export HXY_ROLLBACK_COMMIT="$(git -C "$HXY_ROLLBACK_PATH" rev-parse HEAD)"
test "${#HXY_ROLLBACK_COMMIT}" -eq 40
test -f "$HXY_ROLLBACK_PATH/apps/hxy-web/dist/index.html"
test "$(cat "$HXY_ROLLBACK_PATH/apps/hxy-web/dist/release-commit.txt")" = "$HXY_ROLLBACK_COMMIT"
export HXY_ROLLBACK_SEAL="/root/hxy/data/releases/role-journeys/${HXY_ROLLBACK_COMMIT}.sha256"
test -f "$HXY_ROLLBACK_SEAL"
cd "$HXY_ROLLBACK_PATH"
sha256sum -c "$HXY_ROLLBACK_SEAL"
test -z "$(find "$HXY_ROLLBACK_PATH" -xdev -type f -perm /222 -print -quit)"
test -z "$(find "$HXY_ROLLBACK_PATH" -xdev -type d -perm /222 -print -quit)"
export HXY_WEB_RELEASE_MARKER_URL='https://hxyos.hexiaoyue.com/release-commit.txt'
read -r -p 'Approved rollback maintenance window/change id: ' HXY_ROLLBACK_WINDOW
test -n "$HXY_ROLLBACK_WINDOW"
systemctl stop hxy-product-web hxy-knowledge-api
test "$(systemctl is-active hxy-product-web || true)" = inactive
test "$(systemctl is-active hxy-knowledge-api || true)" = inactive
ln -sfn "$HXY_ROLLBACK_PATH" /root/hxy/releases/current.next
mv -Tf /root/hxy/releases/current.next /root/hxy/releases/current
systemctl start hxy-knowledge-api
systemctl start hxy-product-web
test "$(readlink -f /root/hxy/releases/current)" = "$HXY_ROLLBACK_PATH"
HXY_ROLLBACK_API_MAIN_PID="$(systemctl show --property MainPID --value hxy-knowledge-api)"
test "$HXY_ROLLBACK_API_MAIN_PID" -gt 0
test "$(readlink -f "/proc/${HXY_ROLLBACK_API_MAIN_PID}/cwd")" = "$HXY_ROLLBACK_PATH"
HXY_ROLLBACK_WEB_MAIN_PID="$(systemctl show --property MainPID --value hxy-product-web)"
test "$HXY_ROLLBACK_WEB_MAIN_PID" -gt 0
test "$(readlink -f "/proc/${HXY_ROLLBACK_WEB_MAIN_PID}/cwd")" = "$HXY_ROLLBACK_PATH/apps/hxy-web/dist"
curl --fail --silent http://127.0.0.1:18081/health
HXY_ROLLBACK_LOCAL_WEB_COMMIT="$(cat /root/hxy/releases/current/apps/hxy-web/dist/release-commit.txt)"
test "$HXY_ROLLBACK_LOCAL_WEB_COMMIT" = "$HXY_ROLLBACK_COMMIT"
HXY_ROLLBACK_WEB_COMMIT="$(
  curl --fail --silent --show-error \
    --header 'Cache-Control: no-cache' \
    "$HXY_WEB_RELEASE_MARKER_URL"
)"
test "$HXY_ROLLBACK_WEB_COMMIT" = "$HXY_ROLLBACK_COMMIT"
cd "$HXY_ROLLBACK_PATH"
sha256sum -c "$HXY_ROLLBACK_SEAL"
test -z "$(find "$HXY_ROLLBACK_PATH" -xdev -type f -perm /222 -print -quit)"
test -z "$(find "$HXY_ROLLBACK_PATH" -xdev -type d -perm /222 -print -quit)"
```

回滚也必须严格使用“预验证 -> 停两服务 -> 确认 inactive -> 原子切换 -> 启动 API ->
启动 Web -> 双 cwd -> health -> 本地/公网旧 marker -> seal”顺序。任一验证失败都必须
停止并升级处理，不得因此直接进入数据库 restore。

数据库 restore 不是普通 rollback，也不得由本手册自动执行。它可能丢弃 backup 之后的
合法写入，必须在 API、worker 和 Web 写入全部停止后，由数据库维护负责人完成
independent maintenance confirmation，明确数据损失范围，并在新的隔离数据库再次验证
manifest、SHA-256、`pg_restore --list` 和完整恢复后，才可另开维护窗口决定是否切换。

任何 rollback 或 restore 操作都不得读取或写入 `/root/htops`，不得修改核心知识。
