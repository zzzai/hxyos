export type HxyKnowledgeDomainKey =
  | "brand"
  | "product"
  | "store_model"
  | "operations"
  | "marketing"
  | "management"
  | "franchise"
  | "finance"
  | "competitor"
  | "technology"
  | "legal"
  | "external";

export type HxyProjectStageKey =
  | "preparation"
  | "pilot"
  | "scale"
  | "chain"
  | "10000_stores"
  | "evergreen";

export type HxyKnowledgeTaxonomyItem<T extends string> = {
  key: T;
  label: string;
  keywords: string[];
};

export type HxyKnowledgeClassification = {
  domain: HxyKnowledgeDomainKey;
  secondaryDomains: HxyKnowledgeDomainKey[];
  stage: HxyProjectStageKey;
  confidence: number;
  reasons: string[];
};

export type HxyKnowledgeTaxonomyOverride = {
  match: {
    pathIncludes?: string;
    fileNameIncludes?: string;
    extension?: string;
  };
  knowledgeDomain: HxyKnowledgeDomainKey;
  projectStage: HxyProjectStageKey;
  confidence?: number;
  reason: string;
};

export const HXY_KNOWLEDGE_DOMAINS: Array<HxyKnowledgeTaxonomyItem<HxyKnowledgeDomainKey>> = [
  { key: "brand", label: "品牌", keywords: ["品牌", "定位", "超级符号", "购买理由", "门头", "视觉", "vi"] },
  { key: "product", label: "产品/服务", keywords: ["产品", "服务", "套餐", "项目", "泡脚", "按摩", "理疗"] },
  {
    key: "store_model",
    label: "门店模型",
    keywords: ["小店模型", "店型", "坪效", "人员配置", "房间", "面积", "选址", "单店模型"],
  },
  { key: "operations", label: "运营", keywords: ["运营", "流程", "排班", "复购", "服务流程", "到店", "会员"] },
  { key: "marketing", label: "营销", keywords: ["营销", "获客", "活动", "投放", "私域", "团购", "转化"] },
  { key: "management", label: "管理", keywords: ["管理", "组织", "店长", "培训", "绩效", "督导"] },
  { key: "franchise", label: "加盟", keywords: ["加盟", "招商", "加盟商", "复制", "连锁"] },
  { key: "finance", label: "财务/模型", keywords: ["财务", "成本", "毛利", "利润", "现金流", "回本"] },
  { key: "competitor", label: "竞品", keywords: ["竞品", "对手", "美团", "大众点评", "同行"] },
  { key: "technology", label: "技术/系统", keywords: ["技术", "系统", "小程序", "ai", "数据", "agent"] },
  { key: "legal", label: "法务/合同", keywords: ["合同", "法务", "协议", "授权", "商标"] },
  { key: "external", label: "外部行业/政策/市场", keywords: ["行业", "政策", "市场", "人口", "商圈", "趋势"] },
];

export const HXY_PROJECT_STAGES: Array<HxyKnowledgeTaxonomyItem<HxyProjectStageKey>> = [
  { key: "preparation", label: "筹备期", keywords: ["preparation", "筹备", "开业前", "启动", "立项", "准备"] },
  { key: "pilot", label: "试点期", keywords: ["pilot", "试点", "样板店", "验证", "测试", "首店"] },
  { key: "scale", label: "扩张期", keywords: ["scale", "扩张", "拓店", "规模化", "增长"] },
  { key: "chain", label: "连锁化", keywords: ["chain", "连锁", "标准化", "督导", "区域", "多店"] },
  { key: "10000_stores", label: "万店规模", keywords: ["10000", "万店", "全国", "平台化", "生态"] },
  { key: "evergreen", label: "长期通用", keywords: ["evergreen", "长期", "通用", "方法论", "原则"] },
];

type ScoreResult<T extends string> = {
  key: T;
  score: number;
  reasons: string[];
};

function normalize(value: string): string {
  return value.toLowerCase();
}

function scoreTaxonomy<T extends string>(
  items: Array<HxyKnowledgeTaxonomyItem<T>>,
  params: {
    pathAndTitle: string;
    textPreview: string;
    reasonPrefix: string;
  },
): ScoreResult<T>[] {
  const pathAndTitle = normalize(params.pathAndTitle);
  const textPreview = normalize(params.textPreview);
  return items
    .map((item) => {
      let score = 0;
      const reasons: string[] = [];
      for (const keyword of item.keywords) {
        const normalizedKeyword = normalize(keyword);
        if (pathAndTitle.includes(normalizedKeyword)) {
          score += 3;
          reasons.push(`${params.reasonPrefix}:${keyword}`);
          continue;
        }
        if (textPreview.includes(normalizedKeyword)) {
          score += 1;
          reasons.push(`${params.reasonPrefix}:${keyword}`);
        }
      }
      return { key: item.key, score, reasons };
    })
    .filter((item) => item.score > 0)
    .sort(
      (left, right) =>
        right.score - left.score ||
        items.findIndex((item) => item.key === left.key) - items.findIndex((item) => item.key === right.key),
    );
}

export function classifyHxyKnowledgeAsset(params: {
  relativePath: string;
  fileName: string;
  title: string;
  textPreview?: string;
  overrides?: HxyKnowledgeTaxonomyOverride[];
}): HxyKnowledgeClassification {
  const pathAndTitle = [params.relativePath, params.fileName, params.title].join(" ");
  const textPreview = params.textPreview ?? "";
  const matchedOverride = findMatchingOverride(params);
  if (matchedOverride) {
    return {
      domain: matchedOverride.knowledgeDomain,
      secondaryDomains: [],
      stage: matchedOverride.projectStage,
      confidence: matchedOverride.confidence ?? 0.95,
      reasons: [`override:${matchedOverride.reason}`],
    };
  }
  const domainScores = scoreTaxonomy(HXY_KNOWLEDGE_DOMAINS, {
    pathAndTitle,
    textPreview,
    reasonPrefix: "domain",
  });
  const stageScores = scoreTaxonomy(HXY_PROJECT_STAGES, {
    pathAndTitle,
    textPreview,
    reasonPrefix: "stage",
  });
  const primaryDomain = domainScores[0];
  const primaryStage = stageScores[0];
  const domain = primaryDomain?.key ?? "external";
  const stage = primaryStage?.key ?? "evergreen";
  const reasons = [
    ...(primaryDomain?.reasons ?? ["domain:fallback_external"]),
    ...(primaryStage?.reasons ?? ["stage:fallback_evergreen"]),
  ];
  const secondaryDomains = domainScores
    .slice(1, 4)
    .map((item) => item.key)
    .filter((item) => item !== domain);
  const rawConfidence = ((primaryDomain?.score ?? 0) + (primaryStage?.score ?? 0)) / 8;
  const confidence = Math.max(0.2, Math.min(0.95, rawConfidence));
  return {
    domain,
    secondaryDomains,
    stage,
    confidence,
    reasons,
  };
}

function findMatchingOverride(params: {
  relativePath: string;
  fileName: string;
  overrides?: HxyKnowledgeTaxonomyOverride[];
}): HxyKnowledgeTaxonomyOverride | undefined {
  const relativePath = normalize(params.relativePath);
  const fileName = normalize(params.fileName);
  const extension = params.fileName.split(".").pop()?.toLowerCase() ?? "";
  return params.overrides?.find((override) => {
    const pathIncludes = override.match.pathIncludes;
    if (pathIncludes && !relativePath.includes(normalize(pathIncludes))) {
      return false;
    }
    const fileNameIncludes = override.match.fileNameIncludes;
    if (fileNameIncludes && !fileName.includes(normalize(fileNameIncludes))) {
      return false;
    }
    const expectedExtension = override.match.extension?.replace(/^\./u, "").toLowerCase();
    if (expectedExtension && extension !== expectedExtension) {
      return false;
    }
    return true;
  });
}
