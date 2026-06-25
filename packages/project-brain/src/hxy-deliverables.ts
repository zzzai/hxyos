import fs from "node:fs/promises";
import path from "node:path";
import type { HxyBrandMasterPlan } from "./hxy-brand-master-plan.js";
import type { HxyExecutionPlaybook, HxyExecutionSurface } from "./hxy-execution-playbook.js";
import type { HxyPilotValidationMatrix, HxyStoreModel } from "./hxy-store-model-calculator.js";

export type HxyDeliverableInputs = {
  masterPlan: HxyBrandMasterPlan;
  playbook: HxyExecutionPlaybook;
  storeModel: HxyStoreModel;
  validationMatrix: HxyPilotValidationMatrix;
};

export function buildHxyFormalBrandPlanMarkdown(inputs: HxyDeliverableInputs): string {
  const positioning = findSection(inputs.masterPlan, "positioning_strategy");
  const purchaseReasons = findSection(inputs.masterPlan, "purchase_reason_system");
  const brandAssetItems = normalizeBrandAssetItems(findSection(inputs.masterPlan, "brand_asset_system")?.content ?? []);
  const terminal = findSection(inputs.masterPlan, "terminal_execution");
  return lines(
    "# 荷小悦品牌策划全案 v1",
    "",
    "## 1. 核心判断",
    inputs.masterPlan.executive_summary,
    "",
    "当前经营定位：社区泡脚按摩小店。",
    "融资叙事：社区健康服务入口。",
    "远期愿景：银发健康科技平台 / 社区健康数字基础设施。",
    "",
    "## 2. 定位策略",
    bulletList(positioning?.content ?? []),
    "",
    "## 3. 购买理由",
    bulletList(purchaseReasons?.content ?? []),
    "",
    "## 4. 品牌资产",
    bulletList(brandAssetItems),
    "",
    "## 5. 终端执行",
    bulletList(terminal?.content ?? inputs.playbook.surfaces.map((surface) => `${surface.label}：${surface.objective}`)),
    "",
    "## 6. 样板店经营模型",
    `- 月总营收：${inputs.storeModel.monthly_revenue}`,
    `- 月净现金流：${inputs.storeModel.monthly_net_cashflow}`,
    `- 回本周期：${inputs.storeModel.payback_months ?? "待验证"} 个月`,
    bulletList(inputs.storeModel.caveats),
    "",
    "## 7. 样板店验证",
    bulletList(
      inputs.validationMatrix.items.map(
        (item) =>
          `${item.label}：${item.hypothesis} 证据：${item.evidence_source}${
            item.baseline_value === undefined ? "" : ` 当前基线：${item.baseline_value}`
          }`,
      ),
    ),
    "",
    "## 8. 风险边界",
    bulletList(inputs.masterPlan.risks),
  );
}

export function buildHxyPilotExecutionPackMarkdown(inputs: HxyDeliverableInputs): string {
  return lines(
    "# 荷小悦样板店执行包 v1",
    "",
    "## 定位护栏",
    inputs.playbook.positioning_guardrail,
    "",
    "## 四个执行面",
    inputs.playbook.surfaces.map(renderSurface).join("\n\n"),
    "",
    "## 每日检查表",
    "- 门头、海报、菜单是否统一出现核心购买理由。",
    "- 前台是否优先推荐招牌款，并记录套餐选择。",
    "- 技师是否完成服务前说明、服务中解释、服务后护理建议。",
    "- 服务结束当天是否发送护理建议，而不是只群发优惠。",
    "- 当天是否记录复购标签和健康档案字段。",
    "",
    "## 样板店验证指标",
    bulletList(inputs.validationMatrix.items.map((item) => `${item.label}：${item.evidence_source}`)),
  );
}

export function buildHxyTerminalMaterialPackMarkdown(inputs: HxyDeliverableInputs): string {
  const storefront = findSurface(inputs.playbook, "storefront");
  const menu = findSurface(inputs.playbook, "menu");
  const technicianScript = findSurface(inputs.playbook, "technician_script");
  const privateDomain = findSurface(inputs.playbook, "private_domain");
  const brandAssetItems = normalizeBrandAssetItems(findSection(inputs.masterPlan, "brand_asset_system")?.content ?? []);
  const validationMetrics = mergeValidationMetrics(inputs);

  return lines(
    "# 荷小悦终端物料包 v1",
    "",
    "## 使用原则",
    "- 所有物料只讲当前能被顾客感知和验证的承诺。",
    "- 门头、菜单、话术、私域必须使用同一套购买理由，不各说各话。",
    "- 不把远期平台愿景当成当前门店宣传承诺。",
    "",
    "## 1. 门头与海报",
    "",
    "主信息：",
    bulletList(brandAssetItems),
    "",
    "门店可直接使用：",
    bulletList(storefront?.copy_blocks ?? ["荷小悦", "草本真现煮，按出真功夫", "社区泡脚按摩小店"]),
    "",
    "落地动作：",
    bulletList(storefront?.action_steps ?? ["门头只保留品牌名、品类和一句购买理由。"]),
    "",
    "## 2. 价格菜单",
    "",
    "菜单结构：",
    bulletList(menu?.copy_blocks ?? ["基础款", "招牌款", "尊享款"]),
    "",
    "推荐规则：",
    bulletList(menu?.action_steps ?? ["菜单按基础款、招牌款、尊享款三层呈现。"]),
    "",
    "## 3. 技师服务话术卡",
    "",
    "服务中可说：",
    bulletList(technicianScript?.copy_blocks ?? ["今天先帮你把这里放松开。"]),
    "",
    "服务动作：",
    bulletList(technicianScript?.action_steps ?? ["服务后给出下次护理建议。"]),
    "",
    "不能说：",
    bulletList(technicianScript?.do_not_say ?? ["这是医疗诊断。"]),
    "",
    "## 4. 私域跟进模板",
    "",
    "可直接发送：",
    bulletList(privateDomain?.copy_blocks ?? ["今天护理建议已记录。"]),
    "",
    "跟进节奏：",
    bulletList(privateDomain?.action_steps ?? ["第 7 天用体感问题提醒复购。"]),
    "",
    "不能做：",
    bulletList(privateDomain?.do_not_say ?? ["群发优惠券即可。"]),
    "",
    "## 5. 样板店验收指标",
    bulletList(validationMetrics),
  );
}

export function buildHxyPilotPrintablePackMarkdown(inputs: HxyDeliverableInputs): string {
  const menu = findSurface(inputs.playbook, "menu");
  const technicianScript = findSurface(inputs.playbook, "technician_script");
  const privateDomain = findSurface(inputs.playbook, "private_domain");
  const menuItems = menu?.copy_blocks ?? ["基础款", "招牌款", "尊享款"];
  const technicianLines = technicianScript?.copy_blocks ?? ["今天先帮你把这里放松开。"];
  const privateDomainLines = privateDomain?.copy_blocks ?? ["今天护理建议已记录。"];

  return lines(
    "# 荷小悦样板店可打印执行卡 v1",
    "",
    "## 使用方式",
    "- 打印后分别放在店长台账、前台收银、技师休息区和私域客服工作台。",
    "- 每天闭店前由店长检查一次，不通过的项第二天班前会纠偏。",
    "",
    "## 1. 店长日检表",
    "- [ ] 门头、菜单、话术、私域是否统一出现同一购买理由",
    "- [ ] 今日是否优先推荐招牌款，并记录套餐选择",
    "- [ ] 技师是否完成服务前说明、服务中解释、服务后护理建议",
    "- [ ] 服务结束当天是否发送护理建议，而不是只发优惠",
    "- [ ] 今日是否记录复购标签和健康档案字段",
    "",
    "## 2. 前台推荐卡",
    "一句话原则：优先推荐招牌款，用清楚选择降低顾客决策成本。",
    "",
    "套餐结构：",
    bulletList(menuItems),
    "",
    "推荐动作：",
    bulletList(menu?.action_steps ?? ["菜单按基础款、招牌款、尊享款三层呈现。"]),
    "",
    "## 3. 技师话术卡",
    "服务前：先说今天解决什么体感问题。",
    "",
    "可直接说：",
    bulletList(technicianLines),
    "",
    "服务后：给出下次护理建议，不做医疗诊断。",
    "",
    "禁用表达：",
    bulletList(technicianScript?.do_not_say ?? ["这是医疗诊断。"]),
    "",
    "## 4. 私域跟进卡",
    "当天跟进：先发护理建议，不先推销。",
    "",
    "可直接发：",
    bulletList(privateDomainLines),
    "",
    "跟进动作：",
    bulletList(privateDomain?.action_steps ?? ["第 7 天用体感问题提醒复购。"]),
    "",
    "## 5. 每日记录字段",
    "- 日期",
    "- 到店来源",
    "- 套餐选择",
    "- 是否选择招牌款",
    "- 主要体感问题",
    "- 服务技师",
    "- 护理建议是否发送",
    "- 复购标签",
    "- 7 天跟进结果",
    "- 30 天复购结果",
  );
}

export async function readHxyDeliverableInputs(structuredDir: string): Promise<HxyDeliverableInputs> {
  const readJson = async <T>(fileName: string): Promise<T> =>
    JSON.parse(await fs.readFile(path.join(structuredDir, fileName), "utf8")) as T;
  return {
    masterPlan: await readJson<HxyBrandMasterPlan>("brand-master-plan.json"),
    playbook: await readJson<HxyExecutionPlaybook>("execution-playbook.json"),
    storeModel: await readJson<HxyStoreModel>("store-model.json"),
    validationMatrix: await readJson<HxyPilotValidationMatrix>("pilot-validation-matrix.json"),
  };
}

export async function writeHxyDeliverables(params: {
  inputs: HxyDeliverableInputs;
  outputDir: string;
}): Promise<void> {
  await fs.mkdir(params.outputDir, { recursive: true });
  await fs.writeFile(
    path.join(params.outputDir, "hxy-brand-plan-v1.md"),
    `${buildHxyFormalBrandPlanMarkdown(params.inputs)}\n`,
    "utf8",
  );
  await fs.writeFile(
    path.join(params.outputDir, "hxy-pilot-execution-pack-v1.md"),
    `${buildHxyPilotExecutionPackMarkdown(params.inputs)}\n`,
    "utf8",
  );
  await fs.writeFile(
    path.join(params.outputDir, "hxy-terminal-material-pack-v1.md"),
    `${buildHxyTerminalMaterialPackMarkdown(params.inputs)}\n`,
    "utf8",
  );
  await fs.writeFile(
    path.join(params.outputDir, "hxy-pilot-printable-cards-v1.md"),
    `${buildHxyPilotPrintablePackMarkdown(params.inputs)}\n`,
    "utf8",
  );
}

function renderSurface(surface: HxyExecutionSurface): string {
  return lines(
    `### ${surface.label}`,
    "",
    `目标：${surface.objective}`,
    "",
    "核心文案：",
    bulletList(surface.copy_blocks),
    "",
    "执行动作：",
    bulletList(surface.action_steps),
    "",
    "禁用表达：",
    bulletList(surface.do_not_say),
  );
}

function findSection(plan: HxyBrandMasterPlan, key: HxyBrandMasterPlan["sections"][number]["key"]) {
  return plan.sections.find((section) => section.key === key);
}

function findSurface(playbook: HxyExecutionPlaybook, key: HxyExecutionSurface["key"]) {
  return playbook.surfaces.find((surface) => surface.key === key);
}

function normalizeBrandAssetItems(items: string[]): string[] {
  const brandName = items.find((item) => item.startsWith("品牌名：")) ?? "品牌名：荷小悦";
  const slogan = items.find((item) => item.startsWith("口号候选：")) ?? "口号候选：草本真现煮，按出真功夫";
  return [
    brandName,
    slogan,
    "核心表达：真实有效、社区信任、草本现煮、按出真功夫。",
    "终端主文案：草本真现煮，按出真功夫。",
  ];
}

function dedupeLines(items: string[]): string[] {
  return Array.from(new Set(items.filter((item) => item.trim().length > 0)));
}

function mergeValidationMetrics(inputs: HxyDeliverableInputs): string[] {
  const merged = new Map<string, { why?: string; evidence?: string }>();
  for (const item of inputs.masterPlan.validation_plan) {
    const current = merged.get(item.label) ?? {};
    current.why = item.why;
    merged.set(item.label, current);
  }
  for (const item of inputs.validationMatrix.items) {
    const current = merged.get(item.label) ?? {};
    current.evidence = item.evidence_source;
    merged.set(item.label, current);
  }
  return Array.from(merged.entries()).map(([label, item]) => {
    if (item.why && item.evidence) {
      return `${label}：${item.why} 验收证据：${item.evidence}`;
    }
    return `${label}：${item.why ?? item.evidence ?? "待补充验收口径"}`;
  });
}

function bulletList(items: string[]): string {
  if (items.length === 0) {
    return "- 待补充。";
  }
  return items.map((item) => `- ${item}`).join("\n");
}

function lines(...items: Array<string | false | null | undefined>): string {
  return items.filter((item): item is string => typeof item === "string").join("\n");
}
