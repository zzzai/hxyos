# HXY Knowledge Factory Design

## Goal

把 `knowledge/hxy` 从“资料目录 + 简单索引”升级成可长期扩展的项目级知识工厂，支持后续持续上传资料，并稳定完成分类、清洗、存储、检索、结构化抽取、质量检查和问答调用。

## Scope

本设计只覆盖 HXY 项目知识库。它复用现有个人知识助手和 HXY 结构化知识脚本，不新建第二套知识运行时，不改 `src/runtime.ts` 业务职责。

本轮交付优先做本地文件和 API 能直接使用的 MVP：

- 分类体系：一级知识域，二级项目阶段。
- 资料资产台账：记录 hash、来源、分类、状态、处理结果。
- 标准化文本：把可解析资料落成 normalized markdown，便于审计和重建。
- 检索索引：沿用 `knowledge/hxy/index.json`，但补充分类元数据。
- 质量报告：输出跳过、解析失败、分类低置信、空文本、重复文件。
- 调用能力：问答可按知识域和项目阶段过滤；HXY 项目大脑优先项目结构化证据，再合并品牌理论。

## Taxonomy

一级知识域：

```text
brand          品牌
product        产品/服务
store_model    门店模型
operations     运营
marketing      营销
management     管理
franchise      加盟
finance        财务/模型
competitor     竞品
technology     技术/系统
legal          法务/合同
external       外部行业/政策/市场
```

二级项目阶段：

```text
preparation    筹备期
pilot          试点期
scale          扩张期
chain          连锁化
10000_stores   万店规模
evergreen      长期通用
```

默认分类规则：

- 文件路径优先于文件名，文件名优先于正文关键词。
- 多域资料允许记录 `secondary_domains`，但 `domain` 必须唯一。
- 阶段不明确时使用 `evergreen`，不能瞎猜成具体阶段。
- 低置信分类进入 doctor 报告，允许人工在 manifest 中覆盖。

## Directory Layout

```text
knowledge/hxy/
  raw/                 原始资料，只增不改
  staging/             新上传待处理区
  normalized/          清洗后的 markdown/json
  index.json           检索索引
  manifest.json        资料资产台账
  taxonomy.json        分类体系
  structured/          claim/entity/relation/evidence/method contract
  reports/             跳过、失败、冲突、待确认报告
```

## Data Model

`manifest.json`：

```json
{
  "version": "hxy-knowledge-manifest.v1",
  "generatedAt": "2026-05-17T00:00:00.000Z",
  "assets": [
    {
      "assetId": "sha1",
      "sourceId": "personal knowledge source id",
      "fileName": "example.pdf",
      "relativePath": "knowledge/hxy/raw/example.pdf",
      "normalizedPath": "knowledge/hxy/normalized/brand/preparation/example.md",
      "sha1": "...",
      "fileSize": 123,
      "updatedAt": "...",
      "contentType": "pdf",
      "domain": "brand",
      "secondaryDomains": ["marketing"],
      "stage": "preparation",
      "classificationConfidence": 0.82,
      "classificationReasons": ["filename:品牌", "text:定位"],
      "status": "indexed",
      "chunkCount": 12,
      "warnings": []
    }
  ]
}
```

允许的 `status`：

```text
staged       已上传待处理
normalized   已完成文本清洗
indexed      已进入检索索引
structured   已进入结构化知识抽取
skipped      不支持或暂不处理
failed       解析失败
needs_review 分类低置信或证据冲突
```

`taxonomy.json`：固定分类定义、关键词、路径别名和人工覆盖入口。

`reports/knowledge-doctor.json`：

- 总资料数、已索引数、失败数、跳过数、低置信数、重复数。
- 按知识域/阶段的覆盖矩阵。
- 失败文件明细和处理建议。
- 对问答/策划案的影响说明。

## Pipeline

1. 上传或放入资料
   - API 上传先进入 `staging/`。
   - 手工放入 `raw/` 的历史资料也可直接被扫描。

2. 解析与清洗
   - PDF 使用 `pdftotext`。
   - EPUB/DOCX 使用 `pandoc`。
   - PPTX 使用 unzip 提取 slide XML。
   - TXT/MD/HTML 直接清洗。
   - 本轮不做 OCR；图片、扫描件进入 skipped/needs_ocr。

3. 分类与台账
   - 对每个 asset 计算 sha1。
   - 根据路径、文件名、正文片段做 deterministic 分类。
   - 生成 normalized markdown 和 manifest。

4. 检索索引
   - 在现有 `PersonalKnowledgeIndex` 中给 source/chunk 增加 `knowledgeDomain`、`projectStage`、`assetId`。
   - 保持向后兼容：现有字段不删除。

5. 结构化抽取
   - 继续使用当前 `build-hxy-structured-knowledge.ts`。
   - 后续把 claim/entity/relation 绑定到 `assetId`、`knowledgeDomain`、`projectStage`。

6. 问答调用
   - `/api/v1/personal-knowledge/chat` 增加可选过滤字段：`knowledge_domain`、`project_stage`。
   - HXY 领域问题默认先检索 HXY 项目资料；涉及品牌策划时再合并 `brand` 理论。
   - 回答必须带引用；如果检索不足，输出缺资料提示而不是编造。

## Error Handling

- 解析失败不阻断全量构建，单文件进入 `failed`。
- 不支持类型进入 `skipped`，记录原因。
- sha1 重复进入 doctor 报告，不重复归档。
- 分类置信度低于阈值时仍可索引，但标记 `needs_review`。
- normalized 写入失败时不能更新 manifest 为 indexed。

## Testing

优先新增单测覆盖：

- taxonomy 分类：文件名、路径、正文关键词、低置信 fallback。
- manifest 构建：hash、路径、状态、分类、重复检测。
- index 元数据：source/chunk 携带知识域和阶段，旧检索不受影响。
- doctor 报告：失败、跳过、低置信、覆盖矩阵。
- API 过滤：HXY chat 按知识域/阶段过滤结果。

目标命令：

```bash
npx vitest run src/personal-knowledge.test.ts src/hxy-knowledge-factory.test.ts
python -m unittest api.test_main.MainTests
npx tsc --noEmit
```

## Rollout

阶段 1：本地 Knowledge Factory MVP。
阶段 2：API 上传与重建流程接入 manifest/doctor。
阶段 3：结构化知识绑定 taxonomy 元数据。
阶段 4：引入 pgvector 和 OCR/多模态解析。
阶段 5：把方法论沉淀为 method contract，并服务品牌策划、营销、管理 Agent。
