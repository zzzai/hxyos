# HXY 业务智能体地图

## Agent 总览

```text
Brand Agent          品牌策划
Product Agent        产品体系
Store Model Agent    单店模型
Site Agent           选址
Operation Agent      门店运营
Customer Agent       用户增长
Franchise Agent      加盟复制
Finance Agent        财务融资
Organization Agent   组织管理
Review Agent         复盘进化
```

## Brand Agent

输入：

- HXY 项目资料
- 华与华理论
- 竞品资料
- 门店真实反馈

输出：

- 一句话定位
- 品牌承诺
- 购买理由
- 超级符号
- slogan
- 门头与终端动作
- 验证指标

## Store Model Agent

输入：

- 面积
- 房租
- 投资
- 技师
- 客流
- 客单
- 产品结构
- 零售占比

输出：

- 月营收
- 毛利
- 净利
- 回本周期
- 敏感变量
- 风险点

## Operation Agent

输入：

- 每日经营数据
- 会员数据
- 技师数据
- 用户评价

输出：

- 今日异常
- 归因
- 店长动作
- 客户名单
- 话术
- 结果追踪

## Franchise Agent

输入：

- 加盟商画像
- 选址报告
- 资金能力
- 经营参与度
- 区域密度

输出：

- 加盟商评分
- 风险预警
- 开店建议
- 区域保护判断
- 第二店资格判断

## Review Agent

输入：

- 经营结果
- 任务执行
- 人工反馈
- 错误问答

输出：

- 更新 claim
- 更新 recipe
- 更新 SOP
- 生成复盘报告
- 标记废弃假设

## Claude Code Workflow

This is not a business Agent. It is the execution harness for the whole project.

Inputs:

- HXY project contract
- Loop Engineering rules
- Repo structure
- Tests and verification commands

Outputs:

- handoff summary
- loop result
- verification status
- next action

Core roles:

- Product
- Design
- Engineer
- QA
- Release
- Reviewer

Its job is to keep Claude Code on the stage, inside the loop, and out of drift.

## Execution Loop

Execution Loop 不是单独业务 Agent，而是所有 Agent 的运行约束：

- 目标必须可验证
- 上下文必须可压缩
- 工具调用必须可反馈
- 结果必须可评估
- 循环必须可停止

它负责把任务从“持续说”变成“按标准完成”。
