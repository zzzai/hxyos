# ADR-001：HXY 从 htops 中拆出独立项目文件体系

## 状态

Accepted

## 背景

htops 是荷塘悦色门店经营系统。HXY 是荷小悦新项目，包含品牌、产品、小店模型、融资、O2O、AI、加盟等独立工作流。

继续把 HXY 方案散落在 `docs/plans`、`knowledge/hxy` 和 htops 运行代码中，会造成边界混乱。

## 决策

创建：

```text
projects/hxy/
```

用于承载 HXY 超智大脑项目体系。

`knowledge/hxy/` 继续保存原始资料和索引。  
`projects/hxy/` 保存架构、语义、数据、智能体、治理和路线图。

## 后果

- HXY 可以独立演进。
- 不污染 htops 核心运行时代码。
- 后续可以拆成独立仓库。
- HXY 原始资料继续不进入 Git 和 Docker 镜像。

