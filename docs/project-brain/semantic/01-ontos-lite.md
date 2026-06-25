# HXY Ontos-lite 轻量本体

## 为什么需要本体

HXY 资料里存在多种定位：

- 社区泡脚按摩小店
- 社区健康生活方式入口
- 银发健康科技平台
- 草本养生连锁

如果只用 RAG，模型容易把这些混成一句空话。轻量本体用于定义概念层级、关系、版本和冲突。

## 不做重型 ontology

当前不引入 OWL/RDF/知识图谱平台。采用：

```text
PostgreSQL + JSON schema + claim/evidence/version/relation
```

## 核心实体

```text
Project
BrandPositioning
CustomerSegment
PainPoint
ProductService
StoreModel
FinancialAssumption
BrandAsset
SuperSymbol
PurchaseReason
Competitor
ExternalTheory
OperatingMetric
ActionRecipe
ValidationMetric
Evidence
Version
```

## 核心关系

```text
BrandPositioning -> targets -> CustomerSegment
CustomerSegment -> has_pain -> PainPoint
PainPoint -> solved_by -> ProductService
ProductService -> belongs_to -> StoreModel
StoreModel -> depends_on -> FinancialAssumption
BrandAsset -> expresses -> BrandPositioning
SuperSymbol -> amplifies -> PurchaseReason
ExternalTheory -> supports/challenges -> Claim
OperatingMetric -> validates -> FinancialAssumption
ActionRecipe -> improves -> OperatingMetric
Evidence -> supports -> Claim
Claim -> conflicts_with -> Claim
Version -> supersedes -> Version
```

## 阶段语义

```text
preparation      筹备期
pilot_store      样板店期
replication      10-50 店复制期
regional_scale   100-1000 店区域规模期
national_scale   万店规模期
```

所有 claim、recipe、metric 都必须绑定阶段。

## 状态语义

```text
draft              草稿
current_candidate  当前候选
confirmed          人工确认
validated          数据验证
deprecated         已废弃
conflicted         存在冲突
```

