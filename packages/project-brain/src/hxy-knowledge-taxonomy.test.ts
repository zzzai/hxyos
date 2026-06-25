import { describe, expect, test } from "vitest";
import { classifyHxyKnowledgeAsset } from "./hxy-knowledge-taxonomy.js";

describe("hxy knowledge taxonomy", () => {
  test("classifies brand preparation assets from path and title", () => {
    const result = classifyHxyKnowledgeAsset({
      relativePath: "knowledge/hxy/raw/品牌/筹备期/荷小悦品牌策划全案.md",
      fileName: "荷小悦品牌策划全案.md",
      title: "荷小悦品牌策划全案",
      textPreview: "品牌定位、购买理由、超级符号和门头话术需要在筹备期先确定。",
    });

    expect(result.domain).toBe("brand");
    expect(result.stage).toBe("preparation");
    expect(result.confidence).toBeGreaterThanOrEqual(0.7);
    expect(result.reasons.some((reason) => reason.includes("品牌"))).toBe(true);
    expect(result.reasons.some((reason) => reason.includes("筹备"))).toBe(true);
  });

  test("classifies store model pilot assets from content", () => {
    const result = classifyHxyKnowledgeAsset({
      relativePath: "knowledge/hxy/raw/资料/模型草案.md",
      fileName: "模型草案.md",
      title: "模型草案",
      textPreview: "小店模型需要在试点门店验证，重点看坪效、人员配置、服务流程和复购。",
    });

    expect(result.domain).toBe("store_model");
    expect(result.stage).toBe("pilot");
    expect(result.confidence).toBeGreaterThan(0.5);
    expect(result.reasons).toContain("domain:小店模型");
    expect(result.reasons).toContain("stage:试点");
  });

  test("falls back to external evergreen when no signal is present", () => {
    const result = classifyHxyKnowledgeAsset({
      relativePath: "knowledge/hxy/raw/misc/unknown.md",
      fileName: "unknown.md",
      title: "unknown",
      textPreview: "no clear business signal",
    });

    expect(result.domain).toBe("external");
    expect(result.stage).toBe("evergreen");
    expect(result.confidence).toBeLessThan(0.5);
    expect(result.reasons).toContain("domain:fallback_external");
    expect(result.reasons).toContain("stage:fallback_evergreen");
  });

  test("applies taxonomy overrides before deterministic keyword scoring", () => {
    const result = classifyHxyKnowledgeAsset({
      relativePath: "knowledge/hxy/raw/荷小悦资料/长风拨筋/微信图片_20260501133501_11081_13.jpg",
      fileName: "微信图片_20260501133501_11081_13.jpg",
      title: "微信图片_20260501133501_11081_13",
      textPreview: "",
      overrides: [
        {
          match: { pathIncludes: "长风拨筋" },
          knowledgeDomain: "competitor",
          projectStage: "preparation",
          confidence: 0.9,
          reason: "长风拨筋竞品图片目录",
        },
      ],
    });

    expect(result.domain).toBe("competitor");
    expect(result.stage).toBe("preparation");
    expect(result.confidence).toBe(0.9);
    expect(result.reasons).toContain("override:长风拨筋竞品图片目录");
  });
});
