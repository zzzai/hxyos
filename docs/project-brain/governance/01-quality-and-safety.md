# HXY 大脑质量与安全治理

## 核心要求

1. 不把模型推理当事实。
2. 不把历史草稿当当前版本。
3. 不把外部理论当项目结论。
4. 不在数据缺口时硬答。
5. 不输出没有验证指标的经营动作。

## 回答前自检

```text
问题类型是什么？
需要哪些证据？
项目资料是否足够？
是否需要外部理论？
是否需要真实经营数据？
是否存在版本冲突？
结论属于事实、假设、建议还是推理？
能否给验证指标？
```

## 审计字段

每次回答记录：

- question
- intent
- capability
- evidence_ids
- model
- answer_source
- confidence
- unresolved_conflicts
- missing_data
- generated_actions
- validation_metrics

## 安全边界

- 原始资料不进 Git
- 原始资料不进 Docker 镜像
- 商业计划和融资资料默认内部可见
- 门店经营数据按角色授权
- 用户健康数据必须单独授权和脱敏

