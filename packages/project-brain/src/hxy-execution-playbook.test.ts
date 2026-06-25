import { describe, expect, test } from "vitest";
import { buildHxyExecutionPlaybook } from "./hxy-execution-playbook.js";
import type { HxyBrandMasterPlan } from "./hxy-brand-master-plan.js";

function masterPlan(): HxyBrandMasterPlan {
  return {
    version: "hxy-brand-master-plan.v1",
    generated_at: "2026-05-14T00:00:00.000Z",
    source_draft_generated_at: "2026-05-14T00:00:00.000Z",
    executive_summary: "荷小悦是社区泡脚按摩小店，核心是家门口、真实有效、价格不心疼、能复购。",
    methodology_principles: [
      { key: "purchase_reason", label: "购买理由", application: "真实有效、价格不心疼、离家近可信。" },
      { key: "super_symbol", label: "超级符号", application: "草本现煮、按出真功夫。" },
      { key: "cultural_context", label: "文化母体", application: "社区日常健康和邻里信任。" },
      { key: "shelf_thinking", label: "货架思维", application: "门头、菜单、话术、私域都是货架。" },
    ],
    sections: [
      {
        key: "terminal_execution",
        title: "终端执行",
        content: [
          "门头/门店：突出荷小悦、草本现煮、按出真功夫。",
          "菜单/套餐：用基础款、招牌款、尊享款三层菜单承接不同频次和客单。",
          "技师话术：统一表达真实有效、按后体感、下次护理建议，不做医疗诊断。",
          "私域/复购：围绕健康档案、复购标签和居家护理建议做持续触达。",
        ],
      },
    ],
    validation_plan: [
      { metric_key: "brand_asset_consistency", label: "品牌资产一致率", source_domain: "brand_positioning", why: "统一表达。" },
      { metric_key: "take_rate_by_package", label: "套餐选择率", source_domain: "product_price_model", why: "验证套餐。" },
      { metric_key: "repeat_visit_rate", label: "复购率", source_domain: "customer_segment", why: "验证复购。" },
    ],
    risks: ["社区小店定位与银发健康科技平台不能同时作为当前主定位。"],
    citations: [],
  };
}

describe("hxy execution playbook", () => {
  test("builds four execution surfaces from the master plan", () => {
    const playbook = buildHxyExecutionPlaybook(masterPlan());
    expect(playbook.version).toBe("hxy-execution-playbook.v1");
    expect(playbook.surfaces.map((surface) => surface.key)).toEqual([
      "storefront",
      "menu",
      "technician_script",
      "private_domain",
    ]);
  });

  test("keeps concrete copy, action steps and validation metrics", () => {
    const playbook = buildHxyExecutionPlaybook(masterPlan());
    const storefront = playbook.surfaces.find((surface) => surface.key === "storefront");
    const menu = playbook.surfaces.find((surface) => surface.key === "menu");
    const script = playbook.surfaces.find((surface) => surface.key === "technician_script");

    expect(storefront?.copy_blocks).toContain("草本真现煮，按出真功夫");
    expect(menu?.action_steps[0]).toContain("基础款、招牌款、尊享款");
    expect(script?.do_not_say).toContain("这是医疗诊断。");
    expect(playbook.validation_metrics.map((metric) => metric.metric_key)).toEqual([
      "brand_asset_consistency",
      "take_rate_by_package",
      "repeat_visit_rate",
    ]);
  });
});
