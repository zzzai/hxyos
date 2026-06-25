import { describe, expect, test } from "vitest";
import fs from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import {
  buildHxyKnowledgeDoctorReport,
  buildHxyKnowledgeFactory,
  writeHxyKnowledgeFactoryOutputs,
} from "./hxy-knowledge-factory.js";

describe("hxy knowledge factory", () => {
  test("builds manifest, normalized text and doctor report", async () => {
    const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "hxy-factory-"));
    const rawDir = path.join(rootDir, "knowledge", "hxy", "raw");
    const outputDir = path.join(rootDir, "knowledge", "hxy");
    await fs.mkdir(path.join(rawDir, "brand", "preparation"), { recursive: true });
    await fs.mkdir(path.join(rawDir, "misc"), { recursive: true });
    await fs.writeFile(
      path.join(rawDir, "brand", "preparation", "荷小悦品牌策划.md"),
      "荷小悦品牌定位、购买理由、超级符号和门头物料需要在筹备期完成。",
      "utf8",
    );
    await fs.writeFile(
      path.join(rawDir, "brand", "preparation", "荷小悦品牌策划副本.md"),
      "荷小悦品牌定位、购买理由、超级符号和门头物料需要在筹备期完成。",
      "utf8",
    );
    await fs.writeFile(path.join(rawDir, "misc", "门店照片.png"), "not image bytes", "utf8");

    const output = await buildHxyKnowledgeFactory({
      rootDir,
      rawDir,
      outputDir,
      readSourceText: async (filePath) => await fs.readFile(filePath, "utf8"),
      now: () => new Date("2026-05-17T00:00:00.000Z"),
    });

    expect(output.manifest.version).toBe("hxy-knowledge-manifest.v1");
    expect(output.manifest.assets).toHaveLength(3);
    const indexed = output.manifest.assets.find((asset) => asset.fileName === "荷小悦品牌策划.md");
    expect(indexed?.status).toBe("indexed");
    expect(indexed?.knowledgeDomain).toBe("brand");
    expect(indexed?.projectStage).toBe("preparation");
    expect(indexed?.normalizedPath).toContain("knowledge/hxy/normalized/brand/preparation/");
    expect(output.normalizedFiles[0]?.text).toContain("# 荷小悦品牌策划");
    const skipped = output.manifest.assets.find((asset) => asset.fileName === "门店照片.png");
    expect(skipped?.status).toBe("skipped");
    expect(skipped?.warnings).toContain("markitdown_required");
    const duplicate = output.manifest.assets.find((asset) => asset.fileName === "荷小悦品牌策划副本.md");
    expect(duplicate?.warnings).toContain("duplicate_content");

    const doctor = buildHxyKnowledgeDoctorReport(output.manifest);
    expect(doctor.summary.total_asset_count).toBe(3);
    expect(doctor.summary.indexed_asset_count).toBe(2);
    expect(doctor.summary.skipped_asset_count).toBe(1);
    expect(doctor.summary.duplicate_asset_count).toBe(1);
    expect(doctor.coverage.brand.preparation).toBe(2);
    expect(doctor.impacts.some((impact) => impact.includes("product"))).toBe(true);

    await writeHxyKnowledgeFactoryOutputs(output, { outputDir });
    await expect(fs.stat(path.join(outputDir, "manifest.json"))).resolves.toBeTruthy();
    await expect(fs.stat(path.join(outputDir, "taxonomy.json"))).resolves.toBeTruthy();
    await expect(fs.stat(path.join(outputDir, "reports", "knowledge-doctor.json"))).resolves.toBeTruthy();
    await expect(fs.stat(path.join(outputDir, "index.json"))).resolves.toBeTruthy();
    await expect(fs.stat(path.join(rootDir, indexed?.normalizedPath ?? ""))).resolves.toBeTruthy();

    await fs.rm(rootDir, { recursive: true, force: true });
  });

  test("uses taxonomy overrides for unsupported image assets", async () => {
    const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "hxy-overrides-"));
    const rawDir = path.join(rootDir, "knowledge", "hxy", "raw");
    const outputDir = path.join(rootDir, "knowledge", "hxy");
    await fs.mkdir(path.join(rawDir, "荷小悦资料", "长风拨筋"), { recursive: true });
    await fs.writeFile(path.join(rawDir, "荷小悦资料", "长风拨筋", "竞品门头.jpg"), "image", "utf8");

    const output = await buildHxyKnowledgeFactory({
      rootDir,
      rawDir,
      outputDir,
      taxonomyOverrides: [
        {
          match: { pathIncludes: "长风拨筋" },
          knowledgeDomain: "competitor",
          projectStage: "preparation",
          confidence: 0.9,
          reason: "长风拨筋竞品图片目录",
        },
      ],
      readSourceText: async (filePath) => await fs.readFile(filePath, "utf8"),
      now: () => new Date("2026-05-17T00:00:00.000Z"),
    });

    expect(output.manifest.assets).toHaveLength(1);
    expect(output.manifest.assets[0]?.status).toBe("skipped");
    expect(output.manifest.assets[0]?.knowledgeDomain).toBe("competitor");
    expect(output.manifest.assets[0]?.projectStage).toBe("preparation");
    expect(output.manifest.assets[0]?.classificationReasons).toContain("override:长风拨筋竞品图片目录");
    expect(output.doctor.coverage.competitor.preparation).toBe(0);

    await fs.rm(rootDir, { recursive: true, force: true });
  });

  test("indexes image assets when a vision sidecar extraction exists", async () => {
    const rootDir = await fs.mkdtemp(path.join(os.tmpdir(), "hxy-vision-"));
    const rawDir = path.join(rootDir, "knowledge", "hxy", "raw");
    const outputDir = path.join(rootDir, "knowledge", "hxy");
    await fs.mkdir(path.join(rawDir, "荷小悦资料", "长风拨筋"), { recursive: true });
    const imagePath = path.join(rawDir, "荷小悦资料", "长风拨筋", "竞品门头.jpg");
    await fs.writeFile(imagePath, "image", "utf8");
    await fs.writeFile(
      `${imagePath}.vision.json`,
      JSON.stringify({
        asset_type: "competitor_store_photo",
        knowledge_domain: "competitor",
        project_stage: "preparation",
        observations: ["门头主色突出", "门口展示服务项目"],
        brand_elements: ["长风拨筋"],
        price_signals: ["未识别价格"],
        service_signals: ["拨筋", "推拿"],
        evidence_text: ["长风拨筋"],
        confidence: 0.86,
      }),
      "utf8",
    );

    const output = await buildHxyKnowledgeFactory({
      rootDir,
      rawDir,
      outputDir,
      taxonomyOverrides: [
        {
          match: { pathIncludes: "长风拨筋" },
          knowledgeDomain: "competitor",
          projectStage: "preparation",
          confidence: 0.9,
          reason: "长风拨筋竞品图片目录",
        },
      ],
      readSourceText: async (filePath) => await fs.readFile(filePath, "utf8"),
      now: () => new Date("2026-05-17T00:00:00.000Z"),
    });

    const imageAsset = output.manifest.assets.find((asset) => asset.fileName === "竞品门头.jpg");
    expect(imageAsset?.status).toBe("indexed");
    expect(imageAsset?.warnings).toContain("vision_sidecar_indexed");
    expect(imageAsset?.knowledgeDomain).toBe("competitor");
    expect(imageAsset?.normalizedPath).toContain("knowledge/hxy/normalized/competitor/preparation/");
    expect(output.normalizedFiles.some((file) => file.text.includes("门头主色突出"))).toBe(true);
    expect(output.index.chunks.some((chunk) => chunk.text.includes("长风拨筋"))).toBe(true);

    await fs.rm(rootDir, { recursive: true, force: true });
  });
});
