import { describe, expect, test } from "vitest";
import {
  buildHxyFormalBrandPlanMarkdown,
  buildHxyPilotPrintablePackMarkdown,
  buildHxyTerminalMaterialPackMarkdown,
  buildHxyPilotExecutionPackMarkdown,
  type HxyDeliverableInputs,
} from "./hxy-deliverables.js";
import type { HxyBrandMasterPlan } from "./hxy-brand-master-plan.js";
import type { HxyExecutionPlaybook } from "./hxy-execution-playbook.js";
import type { HxyPilotValidationMatrix, HxyStoreModel } from "./hxy-store-model-calculator.js";

function inputs(): HxyDeliverableInputs {
  const masterPlan: HxyBrandMasterPlan = {
    version: "hxy-brand-master-plan.v1",
    generated_at: "2026-05-14T00:00:00.000Z",
    source_draft_generated_at: "2026-05-14T00:00:00.000Z",
    executive_summary: "荷小悦是社区泡脚按摩小店，核心是家门口、真实有效、价格不心疼、能复购。",
    methodology_principles: [
      { key: "cultural_context", label: "文化母体", application: "社区日常健康、邻里信任。" },
      { key: "purchase_reason", label: "购买理由", application: "真实有效、价格不心疼、离家近可信。" },
      { key: "super_symbol", label: "超级符号", application: "荷小悦、草本现煮、按出真功夫。" },
      { key: "shelf_thinking", label: "货架思维", application: "门头、菜单、话术、私域都是货架。" },
    ],
    sections: [
      {
        key: "positioning_strategy",
        title: "定位策略",
        content: [
          "当前定位：荷小悦是社区泡脚按摩小店，核心是家门口、真实有效、价格不心疼、能复购。",
          "融资叙事：社区健康服务入口。",
          "远期愿景：银发健康科技平台。",
        ],
      },
      {
        key: "purchase_reason_system",
        title: "购买理由系统",
        content: ["真实有效", "价格不心疼", "离家近可信", "服务可延伸"],
      },
    ],
    validation_plan: [
      { metric_key: "brand_asset_consistency", label: "品牌资产一致率", source_domain: "brand_positioning", why: "统一表达。" },
      { metric_key: "take_rate_by_package", label: "套餐选择率", source_domain: "product_price_model", why: "验证菜单。" },
    ],
    risks: ["社区小店定位与银发健康科技平台不能同时作为当前主定位。"],
    citations: [],
  };
  const playbook: HxyExecutionPlaybook = {
    version: "hxy-execution-playbook.v1",
    generated_at: "2026-05-14T00:00:00.000Z",
    source_master_plan_generated_at: "2026-05-14T00:00:00.000Z",
    positioning_guardrail: "当前经营只讲社区泡脚按摩小店；融资讲社区健康服务入口；远期再讲银发健康科技平台。",
    surfaces: [
      {
        key: "storefront",
        label: "门头/门店",
        objective: "让路过的人立刻知道荷小悦卖什么。",
        copy_blocks: ["荷小悦", "草本真现煮，按出真功夫", "社区泡脚按摩小店"],
        action_steps: ["门头只保留品牌名、品类和一句购买理由。"],
        do_not_say: ["银发健康科技平台已经落地。"],
      },
      {
        key: "menu",
        label: "菜单/套餐",
        objective: "把产品价格变成清楚的选择结构。",
        copy_blocks: ["基础款", "招牌款", "尊享款"],
        action_steps: ["菜单按基础款、招牌款、尊享款三层呈现。"],
        do_not_say: ["随便选一个都一样。"],
      },
      {
        key: "technician_script",
        label: "技师话术",
        objective: "把真实有效转成服务过程解释。",
        copy_blocks: ["今天先帮你把这里放松开。"],
        action_steps: ["服务后给出下次护理建议。"],
        do_not_say: ["这是医疗诊断。"],
      },
      {
        key: "private_domain",
        label: "私域/复购",
        objective: "把一次到店变成连续护理关系。",
        copy_blocks: ["今天护理建议已记录。"],
        action_steps: ["第 7 天用体感问题提醒复购。"],
        do_not_say: ["群发优惠券即可。"],
      },
    ],
    validation_metrics: [],
    risks: ["不要把远期平台愿景当前置主定位。"],
  };
  const storeModel: HxyStoreModel = {
    version: "hxy-store-model.v1",
    generated_at: "2026-05-14T00:00:00.000Z",
    input: {
      initial_investment: 180000,
      monthly_fixed_cost: 68000,
      variable_cost_rate: 0.28,
      package_mix: [],
      other_monthly_revenue: 6000,
    },
    package_rows: [],
    package_monthly_revenue: 136760,
    other_monthly_revenue: 6000,
    monthly_revenue: 142760,
    monthly_variable_cost: 38292.8,
    monthly_fixed_cost: 68000,
    monthly_net_cashflow: 36467.2,
    payback_months: 5,
    caveats: ["这是样板店假设模型，不是已审计财务报表。"],
  };
  const validationMatrix: HxyPilotValidationMatrix = {
    version: "hxy-pilot-validation-matrix.v1",
    generated_at: "2026-05-14T00:00:00.000Z",
    source_store_model_generated_at: "2026-05-14T00:00:00.000Z",
    items: [
      {
        key: "take_rate_by_package",
        label: "套餐选择率",
        stage: "menu",
        hypothesis: "三层菜单能让招牌款成为主销套餐。",
        evidence_source: "收银流水、套餐订单明细",
        baseline_value: 0.5559,
        target_direction: "increase",
      },
    ],
  };
  return { masterPlan, playbook, storeModel, validationMatrix };
}

describe("hxy deliverables", () => {
  test("builds a formal brand plan with positioning, execution and validation", () => {
    const markdown = buildHxyFormalBrandPlanMarkdown(inputs());

    expect(markdown).toContain("# 荷小悦品牌策划全案 v1");
    expect(markdown).toContain("当前经营定位：社区泡脚按摩小店");
    expect(markdown).toContain("草本真现煮，按出真功夫");
    expect(markdown).toContain("回本周期：5 个月");
    expect(markdown).toContain("样板店验证");
    expect(markdown).toContain("社区小店定位与银发健康科技平台不能同时作为当前主定位");
  });

  test("builds a pilot execution pack with SOP surfaces and forbidden wording", () => {
    const markdown = buildHxyPilotExecutionPackMarkdown(inputs());

    expect(markdown).toContain("# 荷小悦样板店执行包 v1");
    expect(markdown).toContain("门头/门店");
    expect(markdown).toContain("菜单按基础款、招牌款、尊享款三层呈现。");
    expect(markdown).toContain("禁用表达");
    expect(markdown).toContain("这是医疗诊断。");
    expect(markdown).toContain("每日检查表");
  });

  test("builds a terminal material pack for storefront, menu, technician and private-domain execution", () => {
    const markdown = buildHxyTerminalMaterialPackMarkdown(inputs());

    expect(markdown).toContain("# 荷小悦终端物料包 v1");
    expect(markdown).toContain("## 1. 门头与海报");
    expect(markdown).toContain("草本真现煮，按出真功夫");
    expect(markdown).toContain("## 2. 价格菜单");
    expect(markdown).toContain("基础款");
    expect(markdown).toContain("招牌款");
    expect(markdown).toContain("尊享款");
    expect(markdown).toContain("## 3. 技师服务话术卡");
    expect(markdown).toContain("今天先帮你把这里放松开。");
    expect(markdown).toContain("## 4. 私域跟进模板");
    expect(markdown).toContain("今天护理建议已记录。");
    expect(markdown).toContain("## 5. 样板店验收指标");
    expect(markdown).toContain("品牌资产一致率");
    expect(markdown.match(/套餐选择率/gu)).toHaveLength(1);
  });

  test("builds printable pilot cards for store manager, front desk, technician and private domain", () => {
    const markdown = buildHxyPilotPrintablePackMarkdown(inputs());

    expect(markdown).toContain("# 荷小悦样板店可打印执行卡 v1");
    expect(markdown).toContain("## 1. 店长日检表");
    expect(markdown).toContain("[ ] 门头、菜单、话术、私域是否统一出现同一购买理由");
    expect(markdown).toContain("## 2. 前台推荐卡");
    expect(markdown).toContain("优先推荐招牌款");
    expect(markdown).toContain("基础款");
    expect(markdown).toContain("招牌款");
    expect(markdown).toContain("尊享款");
    expect(markdown).toContain("## 3. 技师话术卡");
    expect(markdown).toContain("今天先帮你把这里放松开。");
    expect(markdown).toContain("## 4. 私域跟进卡");
    expect(markdown).toContain("今天护理建议已记录。");
    expect(markdown).toContain("## 5. 每日记录字段");
    expect(markdown).toContain("套餐选择");
    expect(markdown).toContain("复购标签");
  });
});
