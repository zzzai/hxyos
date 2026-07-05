# 荷小悦 HXY

荷小悦是独立项目，不属于荷塘悦色，也不属于 htops。

本目录是荷小悦项目根目录，用于承载：

- 荷小悦菜单系统
- 荷小悦管理后台
- 荷小悦技师/员工前端
- 荷小悦产品体系：清、泡、调、补、养
- 荷小悦知识库与项目大脑
- 荷小悦 Memory Service
- 荷小悦独立数据库、部署、运维脚本

## 边界

```text
/root/htops/  = 荷塘悦色
/root/hxy/    = 荷小悦
```

功能模式可以复用，业务数据必须完全分开。

禁止把以下 HXY 数据写入 htops：

- 菜单项目
- 用户订单
- 会员
- 技师
- 门店
- 项目知识
- Memory Service
- 检索索引

禁止把以下荷塘悦色数据写入 HXY：

- 荷塘悦色门店
- 美团团购数据
- 荷塘悦色会员/订单/技师数据
- 荷塘悦色经营指标
- 荷塘悦色项目知识

## 当前迁移状态

本目录当前是从 `/root/htops` 复制迁出的第一版 HXY 项目根。

迁移采用复制优先：

1. 先复制文件。
2. 生成 manifest。
3. 建独立数据库。
4. 切换 HXY 服务。
5. 验证完成后，才清理 htops 中的历史污染面。

当前不代表 htops 已清理完成。

## 目录

```text
apps/
  menu-h5/             HXY 用户菜单和 legacy HTML
  admin-web/           HXY 管理后台
  staff-web/           HXY 员工端
  technician-web/      HXY 技师端
  api/                 HXY API
packages/
  menu-core/           菜单、订单、发布、状态模型
  memory-service/      HXY Memory Service
  knowledge-factory/   HXY 知识清洗、分类、结构化
  project-brain/       HXY 项目大脑生成逻辑
knowledge/             HXY 原始/清洗/结构化知识资产
data/                  迁移、种子、导出、备份
docs/                  HXY 文档、规划、ADR、产品、UI
ops/                   HXY nginx/systemd/docker/env
scripts/               HXY 构建、导入、校验脚本
tests/                 HXY 测试
```

## 当前阶段主入口

当前阶段主入口是 `apps/admin-web/index.html`，它默认进入 `apps/admin-web/startup.html`。

`apps/admin-web/startup.html` 是荷小悦 `0-1 项目推进器`，只推进三件事：

- 核爆点定位是否成立。
- 清泡调补养口径是否能被团队和外部用户听懂、复述、执行。
- 品牌资料沉淀是否能变成答案卡、话术卡和验证任务。

`apps/admin-web/brain.html` 保留经营大脑的通用能力和后台复核能力，但开店前不把招商、门店日报、客户消费数据作为主入口。当前产品先验证定位和表达，再扩展门店经营数据。

## 知识核定规则

当前所有历史资料、上传资料和内置黄金问题都只按参考素材处理，不能直接作为荷小悦的最终标准口径。

HXY 的知识流转规则是：

```text
reference -> ai_structured -> needs_review -> approved -> superseded
```

大模型负责分类、提炼、找冲突、生成黄金问题和答案卡草稿；人工复核通过前，系统只能输出未核定梳理稿并生成复核/答案卡草稿动作。只有数据库中 `status=approved` 的 HXY 答案卡可以直接作为权威答案返回。

## 下一步

优先级：

1. 建 HXY 独立数据库和迁移脚本。
2. 把 HXY API 从 htops `api/main.py` 拆入 `apps/api/`。
3. 把菜单 H5 从 legacy HTML 整理成 HXY 独立前端。
4. 切换 nginx/systemd 到 HXY 命名。
5. 验证 HXY 服务读写 HXY 数据库。
6. 再提交 htops 清理清单。
