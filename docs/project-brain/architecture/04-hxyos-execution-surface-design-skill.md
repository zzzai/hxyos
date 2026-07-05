# HXYOS Execution Surface Design Skill

## 结论

来源文章：`https://mp.weixin.qq.com/s/ulZkAEvrAt09-Aw6p5bh9Q`

文章主题：`Huashu Design：Agent 的 原生 HTML 设计 Skill`

在 HXYOS 中，这篇文章只进入 `Execution Surface` 层，作为外部参考资料和原型生产方法论。

它不能作为 HXY 权威知识，不能直接影响品牌定位、产品功效、融资口径、门店 SOP 或员工标准话术。

```text
Huashu Design article
  -> 外部参考资料
  -> Execution Surface 方法
  -> HXY UI Prototype Skill
  -> 前端原型、设计评审、交互验证、演示物料
```

当前原始资料保存位置：

```text
knowledge/raw/external-references/wechat-2026-06-28-ulZkAEvrAt09-Aw6p5bh9Q/
```

该资料不放入 `knowledge/raw/inbox`，避免被 Knowledge Compiler 当成 Week 1 权威知识候选输入。

## 为什么不能进入知识底座权威层

HXY 当前 Week 1 的最高优先级是对外话术风险：

- 禁用表达库。
- 员工推荐话术。
- 客户常见问题标准答案。
- 对外宣传审核标准。

Huashu Design 讲的是 AI 设计 Skill 和 HTML 原型交付，不解决医疗化表达、保证疗效表达、夸大宣传表达这些最紧急风险。

因此它不改变 Week 1 对外话术风险优先级。

## 可以吸收的能力

### 1. 品牌资产协议

HXY 前端、H5、飞书卡片和演示物料不能凭模型记忆猜颜色、Logo、字体和门店视觉。

执行面生成前必须先读取 HXY 自有资产：

- Logo。
- 门头图。
- 菜单图。
- 空间参考图。
- 品牌色。
- 字体和物料规范。

输出要固化为：

```text
apps/*/DESIGN.md
docs/ui/hxy-operating-brain-design-contract.md
```

### 2. 反 AI Slop

HXY 内部系统不能做成通用 AI 后台模板。

必须避免：

- 紫色渐变。
- 大圆角堆卡片。
- emoji 代替专业图标。
- 空洞大屏感。
- 聊天框占据第一屏。
- 把工具入口堆成产品价值。

HXY 的执行面应优先呈现：

- 当前最大经营议题。
- 待复核知识。
- 风险与冲突。
- 今日动作。
- 训练与验收结果。

### 3. 设计方向顾问

当 HXY 的界面方向不清晰时，不应直接开做完整页面。

应先并行生成三个方向：

```text
A. 经营战情室：适合创始人、运营负责人。
B. 员工训练台：适合门店员工和店长。
C. 资料治理台：适合知识管理员和复核人。
```

每个方向都必须说明：

- 面向角色。
- 主要任务。
- 首屏信息。
- 不适合承载什么。
- 验证方式。

### 4. 五维设计评审

HXY UI Prototype Skill 的评审维度固定为：

```text
1. 业务任务清晰度
2. 信息层级
3. 操作成本
4. 品牌一致性
5. 可验证性
```

文章里的五维设计评审可以作为形式参考，但 HXY 必须换成业务导向维度。

### 5. Playwright 验证

任何 HXY 原型或前端页面不能只靠截图主观判断。

最小验收：

- 桌面端打开不白屏。
- 手机端首屏不超长、不遮挡。
- 关键按钮可点击。
- 文本不溢出容器。
- 首屏能说清当前任务。

Playwright 验证是 HXY 执行面进入下一轮评审的最低门槛。

## 暂不吸收的能力

### 不把 HTML 动画导出作为当前重点

MP4、GIF、PPTX 导出对 HXY 当前知识底座不是核心能力。

除非要做融资演示或门店培训视频，否则不进入 P0。

### 不把设计 Skill 当产品战略

设计 Skill 只能提高表达质量，不能替代产品判断。

HXY 的产品判断仍然来自：

- 当前阶段。
- 最大经营风险。
- 已核定知识。
- 真实用户和员工反馈。
- Benchmark 和门禁。

### 不把外部设计原则直接写成 HXY 标准

外部文章中的设计哲学、工具链、数据和口号只作为参考。

任何进入 HXY 正式规范的内容，必须经过：

```text
外部参考 -> HXY 适配判断 -> 原型验证 -> 人工复核 -> action_asset
```

## HXY UI Prototype Skill 契约

当需要做 HXY 前端或原型时，Agent 必须按这个顺序执行：

```text
1. 读 HXY 当前阶段和角色任务
2. 读 docs/ui/hxy-operating-brain-design-contract.md
3. 读可用品牌资产，不猜品牌视觉
4. 先输出首屏任务结构
5. 再做 HTML / H5 / Web 原型
6. 用 Playwright 验证桌面和手机视口
7. 输出五维设计评审和修复清单
```

硬边界：

- 不能新增 htops 入口。
- 不能使用 htops 数据。
- 不能把 external reference 当 approved knowledge。
- 不能跳过合规话术风险。

## 对当前项目的实际帮助

这篇文章对 HXY 当下有价值，但价值在执行面，不在知识底座。

最该用的三个场景：

1. 员工训练 H5：降低学习成本，手机端优先。
2. 知识复核台：让复核人快速判断 claim、来源、风险和发布状态。
3. 创始人经营台：只展示当前最大假设、证据状态、风险和下一步动作。

当前不该用的场景：

1. 替代 Knowledge Compiler。
2. 替代合规 Benchmark。
3. 生成品牌最终口径。
4. 自动批准答案卡。
5. 自动生成融资材料定稿。

## 验收标准

HXY 使用该参考资料时，必须满足：

- 资料仍在 `knowledge/raw/external-references`。
- 文档明确标记为外部参考资料。
- 不出现在 approved answer card 来源里。
- 不影响 Week 1 对外话术风险优先级。
- 生成的原型必须经过 Playwright 验证。
- 设计输出必须附五维设计评审。
