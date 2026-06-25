from __future__ import annotations

from copy import deepcopy
from typing import Any


_CAPABILITIES: dict[str, Any] = {
    "version": "hxy-operating-brain.v1",
    "positioning": "HXY Operating Brain delivers stable business results, not a document search interface.",
    "knowledge_fusion": [
        {
            "key": "project_knowledge",
            "name": "项目知识",
            "purpose": "品牌、产品、菜单、泡脚方、招商、SOP and approved answer cards.",
        },
        {
            "key": "operating_data",
            "name": "经营数据",
            "purpose": "门店、订单、转化、复购、客诉、培训 and execution signals owned by HXY.",
        },
        {
            "key": "market_intelligence",
            "name": "市场情报",
            "purpose": "行业趋势、竞品、渠道、用户需求 and public market signals.",
        },
        {
            "key": "operating_methodology",
            "name": "经营方法论",
            "purpose": "定位、增长、门店管理、培训、招商 and quality-control playbooks.",
        },
        {
            "key": "organizational_memory",
            "name": "组织记忆",
            "purpose": "approved answers, correction records, review history and reusable team experience.",
        },
        {
            "key": "role_context",
            "name": "角色上下文",
            "purpose": "创始人、产品、运营、招商、门店员工 and future Hermes/企微 role routing.",
        },
    ],
    "model_routes": [
        {
            "key": "reasoning",
            "use_for": ["经营判断", "冲突分析", "纠偏建议", "多场景答案改写"],
            "default_model_family": "strong reasoning model",
        },
        {
            "key": "classification",
            "use_for": ["资料分类", "意图识别", "角色识别", "质检分级"],
            "default_model_family": "fast small model",
        },
        {
            "key": "embedding",
            "use_for": ["文本召回", "答案卡召回", "组织记忆召回"],
            "default_model_family": "text embedding model",
        },
        {
            "key": "vision",
            "use_for": ["图片理解", "菜单图解析", "流程图解析", "报表截图解析"],
            "default_model_family": "vision-language model",
        },
        {
            "key": "speech",
            "use_for": ["培训语音转写", "门店复盘转写", "企微语音入口"],
            "default_model_family": "speech-to-text model",
        },
    ],
    "training_strategy": {
        "pretraining_required": False,
        "pretraining_reason": (
            "HXY should first use RAG, answer cards, review tasks and memory weighting; "
            "pretraining is unnecessary before stable proprietary datasets exist."
        ),
        "fine_tuning_gate": (
            "Consider fine-tuning only after enough approved answers and correction records "
            "prove repeated high-value tasks and stable labels."
        ),
        "recommended_order": [
            "PostgreSQL + pgvector retrieval",
            "role-aware answer cards",
            "correction and review loop",
            "memory profiles and conflict records",
            "fine-tuning after reviewed datasets mature",
        ],
    },
    "implementation_stages": [
        {
            "key": "foundation",
            "goal": "Define capability contract and keep the current HXY API as the only entry point.",
        },
        {
            "key": "result_cards",
            "goal": "Turn frequent questions into reviewed operating answer cards.",
        },
        {
            "key": "memory_layer",
            "goal": "Add role profiles, conflict handling and correction-driven memory weighting.",
        },
        {
            "key": "agent_channels",
            "goal": "Expose the same controlled capabilities to Hermes Agent and 企微 after the web workflow is stable.",
        },
    ],
}


def operating_brain_capabilities() -> dict[str, Any]:
    return deepcopy(_CAPABILITIES)
