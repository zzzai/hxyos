import fs from "node:fs/promises";
import path from "node:path";

export type HxyPackageMixInput = {
  package_key: string;
  label: string;
  price: number;
  monthly_orders: number;
};

export type HxyStoreModelInput = {
  initial_investment: number;
  monthly_fixed_cost: number;
  variable_cost_rate: number;
  package_mix: HxyPackageMixInput[];
  other_monthly_revenue?: number;
};

export type HxyPackageModelRow = HxyPackageMixInput & {
  monthly_revenue: number;
  revenue_share: number;
};

export type HxyStoreModel = {
  version: "hxy-store-model.v1";
  generated_at: string;
  input: HxyStoreModelInput;
  package_rows: HxyPackageModelRow[];
  package_monthly_revenue: number;
  other_monthly_revenue: number;
  monthly_revenue: number;
  monthly_variable_cost: number;
  monthly_fixed_cost: number;
  monthly_net_cashflow: number;
  payback_months: number | null;
  caveats: string[];
};

export type HxyPilotValidationItem = {
  key: string;
  label: string;
  stage: "brand" | "menu" | "finance" | "retention" | "data";
  hypothesis: string;
  evidence_source: string;
  baseline_value?: number | string | null;
  target_direction: "increase" | "decrease" | "validate";
};

export type HxyPilotValidationMatrix = {
  version: "hxy-pilot-validation-matrix.v1";
  generated_at: string;
  source_store_model_generated_at: string;
  items: HxyPilotValidationItem[];
};

export function calculateHxyStoreModel(input: HxyStoreModelInput): HxyStoreModel {
  validateStoreModelInput(input);

  const packageRowsWithoutShare = input.package_mix.map((item) => ({
    ...item,
    monthly_revenue: roundMoney(item.price * item.monthly_orders),
  }));
  const packageMonthlyRevenue = roundMoney(
    packageRowsWithoutShare.reduce((sum, item) => sum + item.monthly_revenue, 0),
  );
  const otherMonthlyRevenue = roundMoney(input.other_monthly_revenue ?? 0);
  const monthlyRevenue = roundMoney(packageMonthlyRevenue + otherMonthlyRevenue);
  const packageRows = packageRowsWithoutShare.map((item) => ({
    ...item,
    revenue_share: monthlyRevenue > 0 ? roundRatio(item.monthly_revenue / monthlyRevenue) : 0,
  }));
  const monthlyVariableCost = roundMoney(packageMonthlyRevenue * input.variable_cost_rate);
  const monthlyFixedCost = roundMoney(input.monthly_fixed_cost);
  const monthlyNetCashflow = roundMoney(monthlyRevenue - monthlyVariableCost - monthlyFixedCost);
  const paybackMonths =
    monthlyNetCashflow > 0 ? Math.ceil(roundMoney(input.initial_investment) / monthlyNetCashflow) : null;

  return {
    version: "hxy-store-model.v1",
    generated_at: new Date().toISOString(),
    input,
    package_rows: packageRows,
    package_monthly_revenue: packageMonthlyRevenue,
    other_monthly_revenue: otherMonthlyRevenue,
    monthly_revenue: monthlyRevenue,
    monthly_variable_cost: monthlyVariableCost,
    monthly_fixed_cost: monthlyFixedCost,
    monthly_net_cashflow: monthlyNetCashflow,
    payback_months: paybackMonths,
    caveats: [
      "这是样板店假设模型，不是已审计财务报表。",
      "回本周期必须用真实房租、人工、耗材、客流、套餐结构和现金到账数据复核。",
      "医疗诊断、长期健康结果和平台化收入不进入当前小店模型。",
    ],
  };
}

export function buildHxyPilotValidationMatrix(model: HxyStoreModel): HxyPilotValidationMatrix {
  return {
    version: "hxy-pilot-validation-matrix.v1",
    generated_at: new Date().toISOString(),
    source_store_model_generated_at: model.generated_at,
    items: [
      {
        key: "brand_asset_consistency",
        label: "品牌资产一致率",
        stage: "brand",
        hypothesis: "门头、菜单、物料、技师话术都能统一表达“草本真现煮，按出真功夫”。",
        evidence_source: "门店巡检照片、物料清单、话术抽检记录",
        target_direction: "increase",
      },
      {
        key: "unaided_positioning_recall",
        label: "无提示定位复述率",
        stage: "brand",
        hypothesis: "顾客能在不提示的情况下说出荷小悦是家门口的社区泡脚按摩小店。",
        evidence_source: "首访顾客离店访谈、社群问卷",
        target_direction: "increase",
      },
      {
        key: "take_rate_by_package",
        label: "套餐选择率",
        stage: "menu",
        hypothesis: "三层菜单能让招牌款成为主销套餐，并提升客单稳定性。",
        evidence_source: "收银流水、套餐订单明细、前台推荐记录",
        baseline_value: topPackageShare(model),
        target_direction: "increase",
      },
      {
        key: "monthly_net_cashflow",
        label: "月净现金流",
        stage: "finance",
        hypothesis: "样板店能在真实成本下形成正向月净现金流。",
        evidence_source: "现金到账、房租、人工、耗材、水电、平台费和总部费用",
        baseline_value: model.monthly_net_cashflow,
        target_direction: "increase",
      },
      {
        key: "payback_months",
        label: "回本周期",
        stage: "finance",
        hypothesis: "真实累计净现金流能覆盖初始投资。",
        evidence_source: "初始投资台账、月度净现金流、累计现金流表",
        baseline_value: model.payback_months,
        target_direction: "decrease",
      },
      {
        key: "repeat_visit_rate",
        label: "复购率",
        stage: "retention",
        hypothesis: "体感改善、护理建议和私域跟进能带来 30/60/90 天复购。",
        evidence_source: "会员到店记录、服务后跟进记录、复购标签",
        target_direction: "increase",
      },
      {
        key: "profile_completion_rate",
        label: "健康档案完整率",
        stage: "data",
        hypothesis: "每次服务都能沉淀体感问题、护理部位、禁忌和下次建议。",
        evidence_source: "健康档案字段覆盖、技师服务记录、私域跟进记录",
        target_direction: "increase",
      },
    ],
  };
}

export async function readHxyStoreModelInput(inputPath: string): Promise<HxyStoreModelInput> {
  return JSON.parse(await fs.readFile(inputPath, "utf8")) as HxyStoreModelInput;
}

export async function writeHxyStoreModelOutputs(params: {
  model: HxyStoreModel;
  matrix: HxyPilotValidationMatrix;
  outputDir: string;
}): Promise<void> {
  await fs.mkdir(params.outputDir, { recursive: true });
  await fs.writeFile(
    path.join(params.outputDir, "store-model.json"),
    `${JSON.stringify(params.model, null, 2)}\n`,
    "utf8",
  );
  await fs.writeFile(
    path.join(params.outputDir, "pilot-validation-matrix.json"),
    `${JSON.stringify(params.matrix, null, 2)}\n`,
    "utf8",
  );
}

function validateStoreModelInput(input: HxyStoreModelInput): void {
  const numericFields: Array<[string, number]> = [
    ["initial_investment", input.initial_investment],
    ["monthly_fixed_cost", input.monthly_fixed_cost],
    ["variable_cost_rate", input.variable_cost_rate],
  ];
  for (const [key, value] of numericFields) {
    if (!Number.isFinite(value) || value < 0) {
      throw new Error(`${key} must be a non-negative finite number`);
    }
  }
  if (input.variable_cost_rate > 1) {
    throw new Error("variable_cost_rate must be between 0 and 1");
  }
  if (input.package_mix.length === 0) {
    throw new Error("package_mix cannot be empty");
  }
  for (const item of input.package_mix) {
    if (!item.package_key.trim()) {
      throw new Error("package_key cannot be empty");
    }
    if (!Number.isFinite(item.price) || item.price < 0) {
      throw new Error(`price must be non-negative for package ${item.package_key}`);
    }
    if (!Number.isFinite(item.monthly_orders) || item.monthly_orders < 0) {
      throw new Error(`monthly_orders must be non-negative for package ${item.package_key}`);
    }
  }
}

function topPackageShare(model: HxyStoreModel): number | null {
  const top = [...model.package_rows].sort((left, right) => right.monthly_revenue - left.monthly_revenue)[0];
  return top?.revenue_share ?? null;
}

function roundMoney(value: number): number {
  return Math.round(value * 100) / 100;
}

function roundRatio(value: number): number {
  return Math.round(value * 10_000) / 10_000;
}
