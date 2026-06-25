import { describe, expect, test } from "vitest";
import {
  buildHxyStructuredKnowledge,
  extractHxyClaimsFromChunk,
} from "./hxy-knowledge-extractor.js";

describe("hxy knowledge extractor", () => {
  test("extracts typed claims with evidence from project chunks", () => {
    const claims = extractHxyClaimsFromChunk({
      sourceId: "source-1",
      domain: "hxy",
      title: "荷小悦 品牌战略汇总",
      relativePath: "knowledge/hxy/raw/荷小悦_品牌战略汇总.docx",
      chunkIndex: 2,
      text: [
        "荷小悦定位社区泡脚按摩小店，面向悦己的年轻女性和社区家庭用户。",
        "主推款60分钟泡脚+按摩+离店护理包，价格128元。",
        "店面面积约100㎡，投资规模约50万元，目标回本周期8个月。",
        "品牌口号：草本真现煮，按出真功夫。",
      ].join(" "),
      keywords: [],
    });

    expect(claims.map((claim) => claim.claim_type)).toEqual(
      expect.arrayContaining([
        "brand_positioning",
        "customer_segment",
        "product_service",
        "store_model",
        "financial_assumption",
        "brand_asset",
      ]),
    );
    expect(claims[0]?.evidence_ids[0]).toContain("source-1:2");
    expect(claims.every((claim) => claim.stage === "preparation")).toBe(true);
  });

  test("builds structured knowledge with entities relations and evidence", () => {
    const output = buildHxyStructuredKnowledge({
      version: "personal-knowledge-index.v1",
      generatedAt: "2026-05-14T00:00:00.000Z",
      rootDir: "/root/hxy",
      rawDir: "/root/hxy/knowledge/raw",
      domains: ["hxy"],
      sources: [
        {
          sourceId: "source-1",
          domain: "hxy",
          title: "荷小悦 品牌战略汇总",
          relativePath: "knowledge/hxy/raw/荷小悦_品牌战略汇总.docx",
          fileName: "荷小悦_品牌战略汇总.docx",
          fileSize: 100,
          updatedAt: "2026-05-14T00:00:00.000Z",
        },
      ],
      chunks: [
        {
          chunkId: "chunk-1",
          sourceId: "source-1",
          domain: "hxy",
          title: "荷小悦 品牌战略汇总",
          relativePath: "knowledge/hxy/raw/荷小悦_品牌战略汇总.docx",
          chunkIndex: 2,
          text: "荷小悦定位社区泡脚按摩小店，主推草本泡脚和按摩。投资规模约50万元，目标回本周期8个月。",
          keywords: [],
        },
      ],
      skippedFiles: [],
    });

    expect(output.assets).toHaveLength(1);
    expect(output.claims.length).toBeGreaterThanOrEqual(3);
    expect(output.evidence.length).toBeGreaterThan(0);
    expect(output.entities.some((entity) => entity.entity_type === "BrandPositioning")).toBe(true);
    expect(output.relations.some((relation) => relation.relation_type === "supports")).toBe(true);
  });

  test("does not treat competitor research rows as HXY project claims", () => {
    const claims = extractHxyClaimsFromChunk({
      sourceId: "source-competitor",
      domain: "hxy",
      title: "荷小悦 小店模型",
      relativePath: "knowledge/hxy/raw/荷小悦 小店模型.pdf",
      chunkIndex: 4,
      text: "排名 品牌名称 奈晚推拿 头部竞争 全区域适配 线上获客能力 签约1300家，已开业500家。长风拨筋 专项技术壁垒，区域深耕，客群精准。",
      keywords: [],
    });

    expect(claims).toHaveLength(0);
  });

  test("does not treat competitor scoring table headers as HXY project claims", () => {
    const claims = extractHxyClaimsFromChunk({
      sourceId: "source-table",
      domain: "hxy",
      title: "荷小悦 小店模型",
      relativePath: "knowledge/hxy/raw/荷小悦 小店模型.pdf",
      chunkIndex: 0,
      text: "荷小悦 小店模型 市场其他品牌调研 一、模板核心模块 1. 指标体系表：含22项核心指标，按品牌实力、运营能力、盈利能力、成长潜力、竞争壁垒5大维度分类。品牌数据填报页已填充奈晚推拿、谷小推、郑远元、长风拨筋。",
      keywords: [],
    });

    expect(claims).toHaveLength(0);
  });
});
