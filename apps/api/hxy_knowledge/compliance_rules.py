from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any


RULE_VERSION = "hxy-brand-risk-rules.v1"
RISK_MATERIAL = Path("knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/09_风险与合规/荷小悦禁用表达库.md")

DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "type": "医疗",
        "level": "bad",
        "words": ["治疗", "治愈", "治好", "根治", "诊断", "处方", "治疗失眠", "改善睡眠", "治疗颈椎病"],
        "advice": "不要把生活放松服务说成医疗、诊疗或疾病处理。",
    },
    {
        "type": "保证",
        "level": "bad",
        "words": ["疗效", "见效", "一次见效", "立刻见效", "包好", "保证有效", "祛湿排毒"],
        "advice": "不要承诺确定结果，也不要把草本、泡脚、按摩包装成功效保证。",
    },
    {
        "type": "夸大",
        "level": "warn",
        "words": ["最好", "第一", "唯一", "顶级", "神奇", "年轻十岁", "医美级"],
        "advice": "不要使用无法证明的绝对化、医美化或制造焦虑的表达。",
    },
]

SECTION_RULE_MAP = {
    "医疗诊疗类": "医疗",
    "疾病与症状承诺类": "医疗",
    "夸大功效类": "保证",
    "排毒祛湿类": "保证",
    "医美与容貌焦虑类": "夸大",
}

REFERENCE_MARKERS = [
    "不能",
    "不要",
    "不得",
    "禁止",
    "禁用",
    "避免",
    "不做",
    "不说",
    "不承诺",
    "不替代",
    "不能替代",
    "不是",
]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _rule_by_type(rules: list[dict[str, Any]], rule_type: str) -> dict[str, Any]:
    for rule in rules:
        if rule["type"] == rule_type:
            return rule
    rule = {
        "type": rule_type,
        "level": "warn",
        "words": [],
        "advice": "保持克制表达，正式发布前需要负责人确认。",
    }
    rules.append(rule)
    return rule


def _codeblock_terms(markdown: str) -> list[str]:
    terms: list[str] = []
    for block in re.findall(r"```(?:text)?\s*(.*?)```", markdown, flags=re.S):
        for line in block.splitlines():
            item = line.strip(" \t-•")
            if item and not item.startswith("#") and item not in terms:
                terms.append(item)
    return terms


def _merge_terms(target: dict[str, Any], terms: list[str]) -> None:
    existing = list(target.get("words") or [])
    for term in terms:
        if term not in existing:
            existing.append(term)
    target["words"] = existing


def _terms_by_section(markdown: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    headings = list(re.finditer(r"^###\s+\d+\.\d+\s+(.+)$", markdown, flags=re.M))
    for index, heading in enumerate(headings):
        section_title = heading.group(1).strip()
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        mapped_type = next((rule_type for marker, rule_type in SECTION_RULE_MAP.items() if marker in section_title), "")
        if not mapped_type:
            continue
        result.setdefault(mapped_type, []).extend(_codeblock_terms(markdown[start:end]))
    return result


def load_brand_risk_rules(*, root_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(root_dir).resolve() if root_dir else _project_root()
    rules = deepcopy(DEFAULT_RULES)
    source_paths: list[str] = []
    material_path = root / RISK_MATERIAL
    if not material_path.exists() and root != _project_root():
        material_path = _project_root() / RISK_MATERIAL
    if material_path.exists():
        markdown = material_path.read_text(encoding="utf-8")
        source_paths.append(RISK_MATERIAL.as_posix())
        for rule_type, terms in _terms_by_section(markdown).items():
            _merge_terms(_rule_by_type(rules, rule_type), terms)

    return {
        "version": RULE_VERSION,
        "status": "candidate_rules",
        "official_use_allowed": False,
        "requires_human_review": True,
        "source_paths": source_paths,
        "rules": rules,
    }


def _sentence_window(text: str, word: str, index: int) -> str:
    left = max(text.rfind("。", 0, index), text.rfind("！", 0, index), text.rfind("？", 0, index), text.rfind("\n", 0, index))
    right_candidates = [pos for pos in [text.find("。", index), text.find("！", index), text.find("？", index), text.find("\n", index)] if pos != -1]
    right = min(right_candidates) if right_candidates else len(text)
    return text[left + 1 : right + len(word)].strip()


def _is_reference_or_boundary(sentence: str) -> bool:
    return any(marker in sentence for marker in REFERENCE_MARKERS)


def _word_hits(text: str, words: list[str]) -> list[str]:
    hits: list[str] = []
    for word in sorted(set(words), key=len, reverse=True):
        start = 0
        while True:
            index = text.find(word, start)
            if index == -1:
                break
            sentence = _sentence_window(text, word, index)
            if not _is_reference_or_boundary(sentence):
                hits.append(word)
                break
            start = index + len(word)
    return hits


def check_brand_risk_text(text: str, *, root_dir: str | Path | None = None) -> dict[str, Any]:
    normalized = " ".join((text or "").split())
    rules = load_brand_risk_rules(root_dir=root_dir)
    hits: list[dict[str, Any]] = []
    for rule in rules["rules"]:
        words = _word_hits(normalized, list(rule.get("words") or []))
        if words:
            hits.append(
                {
                    "type": rule["type"],
                    "level": rule["level"],
                    "words": words,
                    "advice": rule["advice"],
                }
            )
    has_bad = any(hit["level"] == "bad" for hit in hits)
    return {
        "version": "hxy-brand-risk-check.v1",
        "rules_version": rules["version"],
        "rules_status": rules["status"],
        "official_use_allowed": False,
        "requires_human_review": True,
        "status": "bad" if has_bad else "warn" if hits else "ok",
        "hits": hits,
    }
