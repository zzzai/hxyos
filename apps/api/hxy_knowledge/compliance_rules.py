from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any


RULE_VERSION = "hxy-brand-risk-rules.v1"
RISK_MATERIAL = Path("knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/09_风险与合规/荷小悦禁用表达库.md")
EMPLOYEE_SCRIPT_MATERIAL = Path(
    "knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/09_风险与合规/荷小悦员工功效问题标准话术.md"
)
PROJECT_RED_LINE_MATERIAL = Path("knowledge/raw/inbox/荷小悦资料/09_知识库与参考资料/09_风险与合规/荷小悦项目红线卡.md")
RISK_MATERIALS = [RISK_MATERIAL, EMPLOYEE_SCRIPT_MATERIAL, PROJECT_RED_LINE_MATERIAL]

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
    "不讲",
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


def _split_terms(value: str) -> list[str]:
    terms: list[str] = []
    for item in re.split(r"[、,，；;]\s*", value):
        term = item.strip(" \t\r\n。.")
        if term and term not in terms:
            terms.append(term)
    return terms


def _markdown_table_rows(markdown: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in markdown.splitlines():
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not cells or all(re.fullmatch(r":?-{3,}:?", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows


def _section_between(markdown: str, start_pattern: str, end_pattern: str = r"^##\s+") -> str:
    start = re.search(start_pattern, markdown, flags=re.M)
    if not start:
        return ""
    end = re.search(end_pattern, markdown[start.end() :], flags=re.M)
    return markdown[start.end() : start.end() + end.start()] if end else markdown[start.end() :]


def _codeblock_terms_in_section(markdown: str, start_pattern: str) -> list[str]:
    section = _section_between(markdown, start_pattern)
    return _codeblock_terms(section)


def _risk_type_for_term(term: str) -> str:
    if any(marker in term for marker in ["治疗", "治病", "诊疗", "疾病", "慢病", "医院", "药", "颈椎", "腰椎", "肩周"]):
        return "医疗"
    if any(marker in term for marker in ["疗效", "见效", "包好", "保证", "祛湿", "排毒", "调理", "体质", "经络", "气血"]):
        return "保证"
    if any(marker in term for marker in ["医美", "抗衰", "瘦", "美白", "皮肤", "年轻", "无创"]):
        return "夸大"
    return "保证"


def _terms_by_risk_type(terms: list[str]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for term in terms:
        result.setdefault(_risk_type_for_term(term), []).append(term)
    return result


def _merge_terms(target: dict[str, Any], terms: list[str]) -> None:
    existing = list(target.get("words") or [])
    for term in terms:
        if term not in existing:
            existing.append(term)
    target["words"] = existing


def _terms_by_section(markdown: str) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    headings = list(re.finditer(r"^(?:##\s+\d+\.\s+|###\s+\d+\.\d+\s+)(.+)$", markdown, flags=re.M))
    for index, heading in enumerate(headings):
        section_title = heading.group(1).strip()
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(markdown)
        mapped_type = next((rule_type for marker, rule_type in SECTION_RULE_MAP.items() if marker in section_title), "")
        if not mapped_type:
            continue
        result.setdefault(mapped_type, []).extend(_codeblock_terms(markdown[start:end]))
    return result


def _safe_replacements_from_forbidden_material(markdown: str) -> list[dict[str, str]]:
    section = _section_between(markdown, r"^##\s+6\.\s+常见错误与替换\s*$")
    replacements: list[dict[str, str]] = []
    for cells in _markdown_table_rows(section):
        if len(cells) < 2 or cells[0] == "不要这样说":
            continue
        unsafe, safe = cells[0], cells[1]
        if unsafe and safe:
            replacements.append({"unsafe": unsafe, "safe": safe})
    return replacements


def _employee_forbidden_terms(markdown: str) -> list[str]:
    terms = _codeblock_terms_in_section(markdown, r"^##\s+2\.\s+员工绝对不能说\s*$")
    for match in re.finditer(r"不能说：\s*```(?:text)?\s*(.*?)```", markdown, flags=re.S):
        for term in _codeblock_terms(match.group(0)):
            if term not in terms:
                terms.append(term)
    return terms


def _employee_safe_answers(markdown: str) -> list[dict[str, str]]:
    answers: list[dict[str, str]] = []
    pattern = re.compile(
        r"^##\s+\d+\.\s+顾客问：(.+?)\n.*?标准回答：\s*```(?:text)?\s*(.*?)```",
        flags=re.M | re.S,
    )
    for match in pattern.finditer(markdown):
        question = match.group(1).strip()
        answer = " ".join(match.group(2).split())
        if question and answer:
            answers.append({"question": question, "answer": answer})
    return answers


def _project_red_line_terms(markdown: str) -> list[str]:
    terms: list[str] = []
    for cells in _markdown_table_rows(markdown):
        if len(cells) < 2 or cells[0] != "不能怎么说":
            continue
        for term in _split_terms(cells[1]):
            if term not in terms:
                terms.append(term)
    return terms


def _material_markdown(root: Path, material: Path) -> str:
    material_path = root / material
    if not material_path.exists() and root != _project_root():
        material_path = _project_root() / material
    if not material_path.exists():
        return ""
    return material_path.read_text(encoding="utf-8")


def load_brand_risk_rules(*, root_dir: str | Path | None = None) -> dict[str, Any]:
    root = Path(root_dir).resolve() if root_dir else _project_root()
    rules = deepcopy(DEFAULT_RULES)
    source_paths: list[str] = []
    safe_replacements: list[dict[str, str]] = []
    safe_answer_snippets: list[dict[str, str]] = []
    for material in RISK_MATERIALS:
        markdown = _material_markdown(root, material)
        if not markdown:
            continue
        source_paths.append(material.as_posix())
        if material == RISK_MATERIAL:
            for rule_type, terms in _terms_by_section(markdown).items():
                _merge_terms(_rule_by_type(rules, rule_type), terms)
            safe_replacements.extend(_safe_replacements_from_forbidden_material(markdown))
        elif material == EMPLOYEE_SCRIPT_MATERIAL:
            for rule_type, terms in _terms_by_risk_type(_employee_forbidden_terms(markdown)).items():
                _merge_terms(_rule_by_type(rules, rule_type), terms)
            safe_answer_snippets.extend(_employee_safe_answers(markdown))
        elif material == PROJECT_RED_LINE_MATERIAL:
            for rule_type, terms in _terms_by_risk_type(_project_red_line_terms(markdown)).items():
                _merge_terms(_rule_by_type(rules, rule_type), terms)

    return {
        "version": RULE_VERSION,
        "status": "candidate_rules",
        "official_use_allowed": False,
        "requires_human_review": True,
        "source_paths": source_paths,
        "safe_replacements": safe_replacements,
        "safe_answer_snippets": safe_answer_snippets,
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
