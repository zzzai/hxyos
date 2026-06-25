import fs from "node:fs/promises";
import path from "node:path";
import type { HxyBrandMasterPlan } from "./hxy-brand-master-plan.js";

export type HxyExecutionSurfaceKey = "storefront" | "menu" | "technician_script" | "private_domain";

export type HxyExecutionSurface = {
  key: HxyExecutionSurfaceKey;
  label: string;
  objective: string;
  copy_blocks: string[];
  action_steps: string[];
  do_not_say: string[];
};

export type HxyExecutionPlaybook = {
  version: "hxy-execution-playbook.v1";
  generated_at: string;
  source_master_plan_generated_at: string;
  positioning_guardrail: string;
  surfaces: HxyExecutionSurface[];
  validation_metrics: HxyBrandMasterPlan["validation_plan"];
  risks: string[];
};

export function buildHxyExecutionPlaybook(plan: HxyBrandMasterPlan): HxyExecutionPlaybook {
  return {
    version: "hxy-execution-playbook.v1",
    generated_at: new Date().toISOString(),
    source_master_plan_generated_at: plan.generated_at,
    positioning_guardrail: "当前经营只讲社区泡脚按摩小店；融资讲社区健康服务入口；远期再讲银发健康科技平台。",
    surfaces: [
      buildStorefrontSurface(),
      buildMenuSurface(),
      buildTechnicianScriptSurface(),
      buildPrivateDomainSurface(),
    ],
    validation_metrics: plan.validation_plan.filter((metric) =>
      ["brand_asset_consistency", "take_rate_by_package", "repeat_visit_rate"].includes(metric.metric_key),
    ),
    risks: plan.risks,
  };
}

function buildStorefrontSurface(): HxyExecutionSurface {
  return {
    key: "storefront",
    label: "门头/门店",
    objective: "让路过的人立刻知道荷小悦卖什么、为什么值得进店。",
    copy_blocks: [
      "荷小悦",
      "草本真现煮，按出真功夫",
      "社区泡脚按摩小店",
      "家门口，按得真舒服",
    ],
    action_steps: [
      "门头只保留品牌名、品类和一句购买理由，不放平台愿景。",
      "现煮草本、护理包和技师手法要在顾客视线内可见。",
      "收银台和等候区重复同一句购买理由，降低理解成本。",
    ],
    do_not_say: ["银发健康科技平台已经落地。", "我们是大健康生态平台。"],
  };
}

function buildMenuSurface(): HxyExecutionSurface {
  return {
    key: "menu",
    label: "菜单/套餐",
    objective: "把产品价格变成清楚的选择结构，而不是一堆项目。",
    copy_blocks: [
      "基础款：解乏放松，适合第一次体验。",
      "招牌款：草本现煮 + 手法按摩 + 护理建议。",
      "尊享款：更长时长 + 居家护理包 + 下次护理建议。",
    ],
    action_steps: [
      "菜单按基础款、招牌款、尊享款三层呈现。",
      "每个套餐必须写清时长、价格、包含内容和适合人群。",
      "收银和技师都优先推荐招牌款，用套餐选择率验证。",
    ],
    do_not_say: ["随便选一个都一样。", "价格以后再说。"],
  };
}

function buildTechnicianScriptSurface(): HxyExecutionSurface {
  return {
    key: "technician_script",
    label: "技师话术",
    objective: "把真实有效转成服务过程中的可感知解释和下次护理理由。",
    copy_blocks: [
      "今天先帮你把这里放松开，结束后我会告诉你回去怎么护理。",
      "这个草本包是现煮的，配合手法会更容易有体感。",
      "下次建议按这个部位继续做，不要拖到特别难受再来。",
    ],
    action_steps: [
      "服务前说清今天解决什么体感问题。",
      "服务中解释草本现煮和手法重点。",
      "服务后给出下次护理建议和居家护理动作。",
    ],
    do_not_say: ["这是医疗诊断。", "保证治好。", "不办卡就没效果。"],
  };
}

function buildPrivateDomainSurface(): HxyExecutionSurface {
  return {
    key: "private_domain",
    label: "私域/复购",
    objective: "把一次到店变成连续护理关系。",
    copy_blocks: [
      "今天护理建议已记录，下次可以继续按这个方向做。",
      "这周如果肩颈又紧，优先做热敷和泡脚，不要硬扛。",
      "下次到店可以直接按上次方案接着做。",
    ],
    action_steps: [
      "服务结束当天发送护理建议，不先推销。",
      "第 7 天用体感问题提醒复购，第 30 天用健康档案复盘。",
      "沉淀复购标签：肩颈、睡眠、疲劳、腿部、寒湿等。",
    ],
    do_not_say: ["群发优惠券即可。", "不回消息就放弃。"],
  };
}

export async function readHxyBrandMasterPlan(planPath: string): Promise<HxyBrandMasterPlan> {
  return JSON.parse(await fs.readFile(planPath, "utf8")) as HxyBrandMasterPlan;
}

export async function writeHxyExecutionPlaybook(playbook: HxyExecutionPlaybook, outputDir: string): Promise<void> {
  await fs.mkdir(outputDir, { recursive: true });
  await fs.writeFile(path.join(outputDir, "execution-playbook.json"), `${JSON.stringify(playbook, null, 2)}\n`, "utf8");
}
