# HXYOS AI Native Dev Harness

## 来源与定位

参考文章：

- URL: `https://mp.weixin.qq.com/s/t04ysxZN2qEc3986r2gyTA`
- 标题：`Code is cheap. Don't write any.——AI Native，程序员如何提升五倍coding效率`
- 作者：无岳
- 本地原文：`knowledge/raw/inbox/wechat/data-miniprogram-nickname/19700101_Code_is_cheap._Don't_write_any.——AI_Native，程序员如何提升/article.md`

这篇文章对 HXYOS 的价值在开发方法，不在品牌、运营、功效、融资或门店知识。

它只能作为：

```text
外部参考资料
-> HXYOS Dev Harness 方法输入
-> 开发 Loop 纪律
-> 自动化执行与验证规范
```

它不能作为：

```text
HXY 权威业务知识
HXY 品牌口径
门店员工话术
对外宣传依据
自动批准知识的依据
```

## 对 HXYOS 当前问题的直接帮助

HXYOS 当前开发卡点不是缺想法，而是：

```text
1. 对话式开发太慢，用户需要一句一句推动。
2. 每轮目标容易漂移，页面和产品方向一会儿一变。
3. 资料、文档、测试、页面、Loop Engine 没有统一开发节奏。
4. AI 很容易产出看似完整但不贴 HXY 地形的 slop。
5. 完成声明必须靠证据，不靠模型自信。
```

文章可以帮助 HXYOS 把开发方式改成：

```text
spec 定方向
task package 控范围
minimum chaos unit 控粒度
checkpoint 控偏航
safety net 控质量
handoff 控跨会话
```

一句话：

```text
HXYOS 不应该靠连续聊天推进开发，
而应该靠可复用的 Dev Harness 自动推进，人在 checkpoint 上控方向。
```

## HXYOS 采纳的核心概念

### 1. Harness: 人定方向，模型推进

HXYOS 的开发 Harness 定义为：

```text
人负责：
- 目标
- 边界
- 业务判断
- checkpoint 放行
- 最终验收

AI 负责：
- 读代码地形
- 拟定实现方案
- 写代码
- 跑测试
- 修失败
- 生成证据报告
```

这和当前 `scripts/run-hxy-loop.py` 的思路一致：

```text
loop 只执行 allowlisted workflow
loop 必须有 max_iterations
loop 必须写 state/report
loop 不能自动批准业务知识
```

### 2. 反 slop: 先 spec，后代码

文章强调大模型是概率生成器，自由空间越大越容易跑偏。

HXYOS 的开发规则：

```text
No Spec, No Code
No Boundary, No Loop
No Evidence, No Done
```

任何较大改动前必须先形成短 spec，至少包含：

```text
goal
current_state
allowed_scope
forbidden_scope
acceptance_tests
stop_condition
risk_notes
```

当前适用场景：

- 重做 `startup.html`
- 继续改前端执行面
- 新增资料入库 Loop
- 扩展 benchmark improvement loop
- 接 Hermes / 飞书开发任务入口

### 3. Minimum Chaos Unit: 最小混沌单元

HXYOS 不把“做成熟企业级系统”这种大目标一次性交给 AI。

每个开发任务必须小到：

```text
目标清楚
范围可见
结果可验
失败能回炉
```

同时大到：

```text
AI 可以自主读代码、写实现、跑验证、修测试
```

HXYOS 的推荐任务包粒度：

```text
好任务：
- 重做 index.html 成任务工作台，并保留问答框
- 新增 brand-check.html，拦截医疗、保证、夸大表达
- knowledge.html 第一屏改成资料入口，高级治理折叠
- startup.html 改成首店今日动作台

坏任务：
- 做完整企业级智能大脑
- 把所有资料都理解
- 把前端做好看
- 自动开发整个项目
```

### 4. Codemap: 先读地形

HXYOS 现在代码和文档已经很多。

每轮 Dev Harness 开始前，要先形成本轮 codemap：

```text
相关页面
相关测试
相关 API
相关脚本
相关文档
已有约束
不能碰的区域
```

例子：

```text
任务：重做 startup.html

codemap:
- apps/admin-web/startup.html
- tests/test_hxy_brain_frontend.py
- docs/project-brain/2026-07-03-current-status.md
- docs/product/hxyos-prd.md
- AGENTS.md

不能碰：
- htops
- 招商主线
- VI/SI 设计结论
- 自动批准知识
```

### 5. Checkpoint: 人只在关键节点控方向

HXYOS Dev Harness 的 checkpoint 不看“AI 是否很努力”，只看：

```text
目标有没有跑偏
边界有没有越界
测试有没有变绿
页面是否真实可用
风险是否进入安全通道
是否需要回炉
```

checkpoint 可采取 6 种动作：

```text
continue     继续
stop         停止
redirect     转向
rollback     回炉
ask          追问
add_context  加料
```

### 6. New Chat / Handoff: 对抗上下文腐烂

长对话会腐烂。自动总结只能延缓，不能解决。

HXYOS 要把长期状态放在文件里：

```text
docs/project-brain/2026-07-03-current-status.md
docs/plans/*.md
knowledge/runs/{run_id}/loop-state.json
knowledge/reports/*.json
tests/*.py
```

换会话时，不靠“你记得刚才吗”，而靠：

```text
current status
spec
codemap
last checkpoint report
test output
next task package
```

## HXYOS Dev Harness v1 流程

标准流程：

```text
1. Read Terrain
   读取 AGENTS.md、相关页面、测试、文档、状态文件。

2. Write Micro Spec
   写清目标、范围、禁止项、验收标准、停止条件。

3. Build Codemap
   列出本轮必须读的文件和不能碰的文件。

4. Execute Minimum Chaos Unit
   AI 自主实现、跑测试、修失败。

5. Checkpoint Report
   输出改了什么、测试结果、截图/交互证据、剩余风险。

6. Safety Net
   按风险层级跑单测、前端截图、交互验证、benchmark 或安全检查。

7. Handoff
   更新状态文件或计划文档，给下一轮一个干净入口。
```

## 与现有 HXYOS Loop Engine 的融合

当前已有：

```text
apps/api/hxy_knowledge/loop_engine.py
scripts/run-hxy-loop.py
tests/test_hxy_loop_engine.py
knowledge/runs/
knowledge/reports/
```

文章方法可以融合为三层：

### L1: Human-Codex Dev Loop

适合当前 UI 和文档开发。

```text
输入：用户目标 + repo codemap
输出：代码改动 + 测试 + 截图 + final report
停止：测试通过或达到 max_iterations
```

### L2: Scripted HXY Loop Engine

适合知识编译、benchmark、治理状态。

```text
compile_knowledge
benchmark_improvement
review_queue_triage
frontend_regression
```

### L3: Hermes / 飞书 Task Loop

适合后续把开发任务从对话框搬到工作流。

```text
飞书指令
-> 创建 task package
-> 跑 allowlisted loop
-> 回传 checkpoint report
-> 人点继续 / 停止 / 转向
```

## Codex 五类能力在 HXYOS 的落地

用户补充的视频把 Codex 能力分成五类。HXYOS 不直接照搬外部工具名，而是吸收它们背后的工程能力：

| 能力 | HXYOS 对应机制 | 当前落点 | 禁区 |
|---|---|---|---|
| 工程方法 | Dev Harness + Loop Engine + TDD + 验证报告 | `docs/project-brain/agents/04-ai-native-dev-harness.md`、`scripts/run-hxy-loop.py`、测试集 | 不用“AI 会写代码”代替测试和验收 |
| 长期记忆 | 文件化 handoff + process memory + run state | `knowledge/runs/`、`knowledge/reports/`、`process_memory` | 过程记忆不能修改 approved 核心知识 |
| 全网洞察 | 外部资料只进 raw/reference/candidate | `knowledge/raw/inbox/`、资料入库 Loop | 外部文章、视频、社区观点不能直接变企业权威结论 |
| 代码图谱 | 每轮先做 Codemap，识别边界和不能碰区域 | `AGENTS.md`、相关测试、相关 API、相关页面 | 不能跨到 `/root/htops` 写 HXY 业务数据 |
| 中文表达 | 对外文档、员工话术、页面文案做自然化和合规化 | 前台页、品牌检查、员工话术、PRD | 不用润色掩盖证据不足或合规风险 |

对当前项目最有用的是前三个：

```text
1. 工程方法：让“继续”变成可执行 Dev Loop，而不是一轮轮聊天。
2. 长期记忆：把进度、决策、测试和产物写进文件，跨会话不丢。
3. 全网洞察：外部资料可以扩展视野，但必须经过候选、评审、发布闸门。
```

这次新上传的风险与合规资料应走同一规则：

```text
raw/reference
-> compiler 提取 candidate claim
-> review queue
-> 人工复核
-> approved 合规规则
-> brand-check / 员工话术 / 内容发布闸门调用
```

任何 AI 回答只能把未复核合规资料当作候选上下文，不能当作权威依据。

## 多层 Safety Net

HXYOS 不接受“AI 说完成了”。

每轮根据风险启用不同验证层：

| 风险 | 场景 | 必跑验证 |
|---|---|---|
| 低 | 文档、静态页面微调 | targeted test + diff check |
| 中 | 前端工作流、API 小改 | full touched tests + browser interaction |
| 高 | 知识批准、合规话术、模型回答 | benchmark + governance gate +人工复核 |
| 极高 | 数据写入、权限、安全、发布 | full tests + security review + dry-run + rollback plan |

当前前端执行面最低标准：

```text
pytest tests/test_hxy_brain_frontend.py -q
git diff --check
Playwright 390px mobile scrollWidth check
关键按钮真实点击
```

知识底座最低标准：

```text
compile report
loop-state.json
benchmark report
governance blocker report
manual review remains required
```

## 不能吸收的部分

### 不吸收“代码不看也行”的极端说法

HXYOS 可以在低风险 UI、文档、原型任务中少看实现、多看证据。

但以下场景必须看代码和边界：

```text
鉴权
权限
数据库写入
客户数据
健康/医疗表达
支付
部署脚本
Nginx / systemd
frpc / ssh
知识批准
```

### 不吸收“代码是卫生纸”的无边界表达

对 HXYOS 来说：

```text
代码可以便宜
事故不便宜
用户信任不便宜
品牌合规不便宜
组织知识污染不便宜
```

因此代码可以快速生成，但必须通过边界、测试、灰度和回滚。

### 不做任意自动 shell agent

HXYOS Dev Harness 只能调用 allowlisted workflow。

禁止：

```text
自动跑任意 shell
自动批准知识
自动写生产数据
自动改 htops
自动发布高风险内容
```

## 对当下项目的下一步动作

### P0: 把 `startup.html` 改成首店今日动作台

当前首页、前台、说法检查和资料台已经开始从后台化转为任务化。

下一步最应该处理：

```text
apps/admin-web/startup.html
```

目标：

```text
不是“0-1 大后台”
而是“今天首店开业还差哪件事”
```

Micro Spec：

```text
goal:
  首屏只显示当前主线、今日动作、证据缺口、一个输入框。

allowed_scope:
  apps/admin-web/startup.html
  tests/test_hxy_brain_frontend.py

forbidden_scope:
  htops
  招商主线
  多店经营看板
  VI/SI 最终结论
  自动批准知识

acceptance:
  前端测试通过
  手机端无横向溢出
  首屏不出现后台治理术语
  关键按钮可点击
```

### P1: 新增 frontend_regression loop

把刚刚手工做的前端验证变成脚本：

```text
scripts/run-hxy-frontend-regression.py
```

验证：

```text
index.html
frontdesk.html
brand-check.html
knowledge.html
startup.html
```

输出：

```text
knowledge/reports/frontend-regression-latest.json
screenshots under knowledge/runs/{run_id}/screenshots/
```

### P2: 新增 task package 模板

让用户以后不用一句一句说“继续”。

模板：

```text
HXYOS Dev Loop:
goal:
scope:
forbidden:
acceptance:
max_iterations:
checkpoint:
```

### P3: Hermes / 飞书触发 Dev Loop

后续把任务放到飞书：

```text
/hxy-dev-loop startup-frontstage
```

系统创建 task package，跑允许的本地验证，回传 checkpoint report。

## 推荐使用方式

用户以后可以直接发：

```text
执行 HXYOS Dev Harness：
目标：重做 startup.html 成首店今日动作台
范围：只改 startup.html 和前端测试
禁止：htops、招商、多店看板、自动批准知识
验收：前端测试通过，390px 无横向溢出，按钮可点击
停止：最多 3 轮
```

Codex 应按本文执行，不再停在泛泛建议。

## 结论

这篇文章对 HXYOS 的真正价值是：

```text
把 AI 从“聊天式写代码”
升级成“有 spec、有边界、有 checkpoint、有证据的开发流水线”。
```

它直接支持当下最关键的工程目标：

```text
减少一句一句推进
降低目标漂移
提高前端产品迭代速度
让每次完成都有证据
让 HXYOS 的开发能力本身变成可复用系统
```
