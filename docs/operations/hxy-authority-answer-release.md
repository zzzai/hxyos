# HXYOS Authority Answer V1 Release

本手册发布第一条可用的权威回答闭环。它只处理回答权威边界、来源分类、意图路由、
本地品牌宪法、Core-10 和模型 canary，不批量治理 697 份资料，不修改 `/root/htops`。

## Stop Rule

任一 Gate 失败立即停止。后台可以自动测试、构建、调用 canary 和生成报告，但不得自动创建、批准或激活品牌宪法，
不得批准候选知识，不得保存回答正文、资料原文、凭据或私有路径。

`deterministic_contract` 仅证明评分器契约正确，必须保持
`business_readiness_claimed=false`。真实发布必须使用 `captured_product_answers`。

## Gate 1: Immutable Source

使用负责人批准的完整 40 位 commit 创建 detached、clean、只读候选 release。不得从脏工作树、
分支名或移动 tag 启动服务。候选路径使用：

```bash
export HXY_RELEASE_COMMIT='<approved-40-character-commit>'
export HXY_RELEASE_PATH="/root/hxy/releases/authority-answer/${HXY_RELEASE_COMMIT}"
git -C /root/hxy worktree add --detach "$HXY_RELEASE_PATH" "$HXY_RELEASE_COMMIT"
test -z "$(git -C "$HXY_RELEASE_PATH" status --porcelain=v1 --untracked-files=all)"
test "$(git -C "$HXY_RELEASE_PATH" rev-parse HEAD)" = "$HXY_RELEASE_COMMIT"
```

## Gate 2: Full Verification

在候选 release 内安装依赖并执行完整验证：

```bash
cd "$HXY_RELEASE_PATH"
python3 -m venv .venv
.venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r apps/api/requirements.txt
npm ci --registry=https://registry.npmmirror.com
npm --prefix apps/hxy-web ci --registry=https://registry.npmmirror.com
npm test
npm run build:web
.venv/bin/python scripts/check-hxy-secrets.py
.venv/bin/python scripts/check-hxy-public-release.py
git diff --check
```

要求 Python、TypeScript、Web、Playwright、构建、secret 和 public-release 全部通过。

## Gate 3: Private Readiness

私有配置只从 `/root/hxy` 持久目录读取，不复制进 Git 或 release：

```text
/root/hxy/ops/env/hxy-knowledge-api.env
/root/hxy/ops/env/hxy-model-router.toml
/root/hxy/data/private/brand-constitution/
```

必须确认 API token、`HXY_MODEL_API_KEY`、模型执行开关和模型配置存在。Brand Constitution
必须按 `docs/operations/hxy-brand-constitution.md` 由负责人核定并激活；如果缺失，品牌问题只能
返回 `working + review_required`，本 Gate 不得为了通过测试自动生成正式口径。

## Gate 4: Source Authority Schema

迁移 `018_hxy_source_authority.sql` 只为产品资料入口建立来源分类、版本和追加式事件记录。
它不修改旧知识资产的业务结论；旧知识资产不得自动升格，缺少明确来源分类时继续按
`external_reference` 使用。

必须从候选 release 运行受控发布器。先做只读预检；预检必须显示 `state=pending`，且
009-014 前置契约、PostgreSQL 16、HXY 数据库边界和 migration checksum 全部通过：

```bash
set -a
source /root/hxy/ops/env/hxy-knowledge-api.env
set +a
cd "$HXY_RELEASE_PATH"
.venv/bin/python scripts/hxy-source-authority-release.py preflight
```

在维护窗口停止两个数据库写入服务，Web 和 FRP 不需要停止。停止后重新执行 preflight，
然后创建并实际恢复验证一份备份：

```bash
systemctl stop hxy-material-worker.service hxy-knowledge-api.service
.venv/bin/python scripts/hxy-source-authority-release.py preflight
.venv/bin/python scripts/hxy-source-authority-release.py backup
```

从 backup JSON 读取 `manifest_path`，核对路径位于
`/root/hxy/data/backups/source-authority/`。迁移必须使用准确确认串、同一 40 位 commit、
同一数据库实例、同一连接指纹和同一 migration checksum：

```bash
export HXY_SOURCE_AUTHORITY_BACKUP_MANIFEST='<manifest_path>'
.venv/bin/python scripts/hxy-source-authority-release.py apply \
  --backup-manifest "$HXY_SOURCE_AUTHORITY_BACKUP_MANIFEST" \
  --confirm APPLY-HXY-018
.venv/bin/python scripts/hxy-source-authority-release.py postflight
systemctl start hxy-knowledge-api.service hxy-material-worker.service
```

`postflight` 必须证明三列、事件表、约束、五个触发器、四个函数、索引和每条既有资料的
迁移默认基线完整。不得借迁移把任何资料设为 `official_internal` 或生成 approved answer card。
如果 `apply` 报告 `applied=true`，不得盲目重试；按报告和备份判断修复或回滚。

## Gate 5: Three-Model Canary

只使用无业务内容的专用健康检查，不记录模型正文：

```bash
set -a
source /root/hxy/ops/env/hxy-knowledge-api.env
set +a
PYTHONPATH=apps/api .venv/bin/python scripts/run-hxy-authority-canary.py models \
  --output /root/hxy/data/releases/authority-answer/model-canary.json
```

`qwen-flash`、`qwen-plus-latest`、`qwen3.7-max` 必须分别命中指定路线，三项均为 `passed`。

## Gate 6: Core-10 Captured Answers

先在备用端口启动同一 commit 的 API，再运行真实十题。报告只保留 case、模式、权威来源、
引用存在性、风险拦截、动作类型和 token 计数，不得保存回答正文。

```bash
set -a
source /root/hxy/ops/env/hxy-knowledge-api.env
set +a
export HXY_ROOT_DIR=/root/hxy
export PYTHONPATH="$HXY_RELEASE_PATH/apps/api"
"$HXY_RELEASE_PATH/.venv/bin/python" -m uvicorn apps.api.hxy_knowledge_api:app \
  --host 127.0.0.1 --port 28081

"$HXY_RELEASE_PATH/.venv/bin/python" scripts/run-hxy-authority-canary.py core-10 \
  --base-url http://127.0.0.1:28081 \
  --runs-output /root/hxy/data/releases/authority-answer/core-10-runs.json \
  --report-output /root/hxy/data/releases/authority-answer/core-10-report.json
```

必须满足：`pass_rate>=0.85`、`authority_leakage_failures=0`、
`high_risk_interception_rate=1.0`、`target_met=true`。权威组合、遥测、十题完整性都是额外硬门槛。

## Gate 7: Atomic Activation

保存当前 `/root/hxy/releases/current` 为 previous，验证 previous 可回滚；随后在同一维护窗口内
原子切换 `current` 到候选 commit，并统一重启 `hxy-knowledge-api.service`、
`hxy-product-web.service` 和 `hxy-material-worker.service`。三个服务必须指向同一 release commit。

## Gate 8: Public Smoke

验证 `https://hxyos.hexiaoyue.com/` 的桌面与移动入口、登录会话、问答、资料上传、任务和退出。
只使用 canary 身份和无私有内容，不在截图、日志或报告中保留真实资料与回答正文。

## Rollback Boundary

API、Web、worker、Core-10 或公网 smoke 任一回归时，把统一 `current` 指针原子切回 verified
previous commit 并重启三个服务。不要回滚或删除已经合法写入的回答运行记录；不得借回滚修改
品牌宪法。697 份资料的批量治理保持排队状态，直到本发布稳定并单独批准后再开始。
