# HXY Operating Brain Foundation Design

## Product Definition

荷小悦运营大脑不是项目资料问答页。它是面向经营现场的判断系统：把项目知识、门店数据、行业竞品、经营方法论、组织记忆和角色权限融合起来，输出可执行判断、风险边界、复核任务和权威答案。

## Knowledge Fusion

第一版按 6 类知识组织：

- `project_knowledge`: 品牌、产品、泡脚方、菜单、招商、门店模型、培训 SOP。
- `operating_data`: 营收、客流、客单、复购、套餐转化、技师效率、库存、排班、差评。
- `market_intelligence`: 足浴、养生、社区健康、银发健康、轻养生、连锁加盟、团购趋势和竞品。
- `operating_methodology`: 单店模型、选址模型、会员模型、复购模型、招商模型、培训模型、SOP 管理。
- `organizational_memory`: 已问问题、纠偏记录、批准答案、验证结论、被推翻假设。
- `role_context`: 创始人、运营、店长、员工、招商、产品、培训负责人。

## AI Model Strategy

短期不做预训练。荷小悦的价值不在训练一个通用模型，而在准确调用荷小悦事实、数据、方法论和组织记忆。

模型层采用路由：

- reasoning: 高质量经营判断、跨域推理、策略问题。
- classification: 意图识别、资料分类、标签、质检。
- embedding: 文本、图片理解文本、答案卡向量检索。
- vision: 图片、PPT、流程图、菜单图、现场图理解。
- speech: 后续企微和门店培训语音输入输出。

只有积累大量高质量“问题 - 标准答案 - 纠偏记录”后，才考虑微调。微调目标是固定话术、培训问答和成本优化，不做从头预训练。

## System Contract

第一版新增 `/api/operating-brain/capabilities`。它返回：

- capability domains;
- knowledge sources;
- model routing policy;
- training strategy;
- next implementation stages.

这个接口让前端、企微 Agent、培训端和后台共享同一张运营大脑蓝图。
