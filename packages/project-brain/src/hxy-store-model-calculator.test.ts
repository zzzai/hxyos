import { describe, expect, test } from "vitest";
import {
  buildHxyPilotValidationMatrix,
  calculateHxyStoreModel,
  type HxyStoreModelInput,
} from "./hxy-store-model-calculator.js";

function input(): HxyStoreModelInput {
  return {
    initial_investment: 180000,
    monthly_fixed_cost: 68000,
    variable_cost_rate: 0.28,
    package_mix: [
      { package_key: "basic", label: "基础款", price: 68, monthly_orders: 320 },
      { package_key: "signature", label: "招牌款", price: 128, monthly_orders: 620 },
      { package_key: "premium", label: "尊享款", price: 198, monthly_orders: 180 },
    ],
    other_monthly_revenue: 6000,
  };
}

describe("hxy store model calculator", () => {
  test("calculates monthly revenue, net cashflow and payback months", () => {
    const model = calculateHxyStoreModel(input());

    expect(model.version).toBe("hxy-store-model.v1");
    expect(model.monthly_revenue).toBe(142760);
    expect(model.monthly_variable_cost).toBe(38292.8);
    expect(model.monthly_net_cashflow).toBe(36467.2);
    expect(model.payback_months).toBe(5);
    expect(model.package_rows.find((row) => row.package_key === "signature")).toMatchObject({
      monthly_revenue: 79360,
      revenue_share: 0.5559,
    });
  });

  test("builds a validation matrix from brand, menu, store model and private domain assumptions", () => {
    const matrix = buildHxyPilotValidationMatrix(calculateHxyStoreModel(input()));

    expect(matrix.version).toBe("hxy-pilot-validation-matrix.v1");
    expect(matrix.items.map((item) => item.key)).toEqual([
      "brand_asset_consistency",
      "unaided_positioning_recall",
      "take_rate_by_package",
      "monthly_net_cashflow",
      "payback_months",
      "repeat_visit_rate",
      "profile_completion_rate",
    ]);
    expect(matrix.items.find((item) => item.key === "payback_months")?.baseline_value).toBe(5);
    expect(matrix.items.find((item) => item.key === "take_rate_by_package")?.evidence_source).toContain("收银");
  });
});
