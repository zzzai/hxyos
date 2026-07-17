from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import defaultdict
from pathlib import Path, PurePosixPath
from typing import Any

from .source_card import build_source_use_policy


_COMPLIANCE_CANDIDATES = {
    "索引_风险与合规.md",
    "荷小悦项目红线卡.md",
    "荷小悦员工功效问题标准话术.md",
    "荷小悦禁用表达库.md",
}
_AI_APPLICATION_SIGNALS = ("应用笔记", "应用稿", "荷小悦应用", "实践草稿")
_AI_SUMMARY_SIGNALS = (
    "核心总结",
    "总结",
    "阅读笔记",
    "精读",
    "ai摘要",
    "ai_摘要",
    "ai总结",
)
_FOUNDER_ONLY_SIGNALS = (
    "股东",
    "合作协议",
    "投资人",
    "商业计划书",
    "天使轮",
    "估值",
    "收购方",
)
_RESTRICTED_SIGNALS = ("报价", "合同", "协议", "法务", "融资", "分账", "支付")


def _normalized_path(value: str) -> str:
    return PurePosixPath(str(value).replace("\\", "/")).as_posix().lstrip("./")


def _contains_any(value: str, signals: tuple[str, ...]) -> bool:
    return any(signal in value for signal in signals)


def _scopes(path: str) -> list[str]:
    scopes: list[str] = []
    rules = (
        (("02_战略方向", "品牌", "定位"), ("brand", "strategy")),
        (("03_门店模型", "首店", "小店", "单店", "门店"), ("first_store",)),
        (("04_产品系统", "产品", "菜单", "服务", "泡脚"), ("product",)),
        (("05_运营方法", "运营", "接待", "员工", "培训"), ("operations",)),
        (("客户", "消费者", "会员", "用户"), ("customer",)),
        (("06_融资商务", "融资", "股东", "财务", "报价"), ("finance",)),
        (("协议", "合同", "法务", "合规"), ("legal",)),
        (("系统", "技术", "ai", "小程序", "o2o", "iot"), ("technology",)),
        (("07_演示素材", "08_原始素材", "设计", "视觉", "vi", "si"), ("design",)),
        (("风险与合规", "禁用表达", "红线", "功效问题"), ("compliance",)),
    )
    lowered = path.lower()
    for signals, values in rules:
        if any(signal.lower() in lowered for signal in signals):
            scopes.extend(values)
    if "09_知识库与参考资料" in path or not scopes:
        scopes.append("external_method")
    return list(dict.fromkeys(scopes))


def _business_stage(path: str, material_class: str) -> str:
    if _contains_any(path, ("万店", "未来", "全国扩张")):
        return "future_vision"
    if "06_融资商务" in path or _contains_any(path, ("融资", "投资人", "股东")):
        return "financing"
    if _contains_any(path, ("连锁", "多门店", "总部", "督导")):
        return "chain"
    if "03_门店模型" in path or _contains_any(path, ("首店", "小店", "单店")):
        return "first_store"
    if _contains_any(path, ("试点", "验证", "样板店")):
        return "pilot"
    if material_class in {"external_primary", "external_secondary", "ai_derived"}:
        return "evergreen"
    return "pilot"


def classify_source_path(source_path: str) -> dict[str, Any]:
    path = _normalized_path(source_path)
    lowered = path.lower()
    name = PurePosixPath(path).name
    reasons: list[str] = []

    lifecycle = "undetermined"
    authority_state = "unclassified"
    sensitivity = "internal"
    derivation = "original"
    confidence = "medium"

    if path.startswith("extracted-reference/"):
        material_class = "processing_artifact"
        derivation = "extracted_copy"
        confidence = "high"
        reasons.append("material_class:extracted-reference")
    elif "/scripts/" in f"/{path}" or (
        path.startswith("荷小悦资料/scripts/")
        and PurePosixPath(path).suffix.lower() in {".py", ".html", ".json"}
    ):
        material_class = "tool_artifact"
        confidence = "high"
        reasons.append("material_class:tool-directory")
    elif name in _COMPLIANCE_CANDIDATES and "09_风险与合规" in path:
        material_class = "internal_project"
        lifecycle = "current_candidate"
        authority_state = "candidate"
        confidence = "high"
        reasons.append("material_class:explicit-compliance-candidate")
    elif "06_融资商务" in path or _contains_any(path, _RESTRICTED_SIGNALS):
        material_class = "internal_record"
        if _contains_any(path, _FOUNDER_ONLY_SIGNALS):
            sensitivity = "founder_only"
            reasons.append("sensitivity:founder-financing-or-agreement")
        else:
            sensitivity = "restricted"
            reasons.append("sensitivity:restricted-finance-or-legal")
        confidence = "high"
        reasons.append("material_class:internal-finance-record")
    elif "09_知识库与参考资料" in path:
        sensitivity = "public"
        if _contains_any(lowered, tuple(signal.lower() for signal in _AI_APPLICATION_SIGNALS)):
            material_class = "ai_derived"
            derivation = "application_draft"
            reasons.append("material_class:application-note-signal")
        elif _contains_any(lowered, tuple(signal.lower() for signal in _AI_SUMMARY_SIGNALS)):
            material_class = "ai_derived"
            derivation = "ai_summary"
            reasons.append("material_class:summary-or-reading-note-signal")
        elif _contains_any(path, ("原版书籍", "原文", "原始报告")):
            material_class = "external_primary"
            reasons.append("material_class:external-original-directory")
        else:
            material_class = "external_secondary"
            reasons.append("material_class:external-reference-directory")
        confidence = "high"
    elif any(f"/{prefix}_" in f"/{path}" for prefix in ("00", "01", "02", "03", "04", "05", "07", "08")):
        material_class = "internal_project"
        reasons.append("material_class:hxy-project-working-set")
    else:
        material_class = "external_secondary"
        confidence = "low"
        reasons.append("material_class:conservative-unmatched-default")

    if _contains_any(path, ("归档", "旧版", "_旧", "历史参考")):
        lifecycle = "historical"
        reasons.append("lifecycle:explicit-archive-or-old-marker")
    elif _contains_any(path, ("已废止", "废止", "superseded")):
        lifecycle = "superseded"
        reasons.append("lifecycle:explicit-superseded-marker")

    policy = build_source_use_policy(material_class)
    return {
        "material_class": material_class,
        "lifecycle": lifecycle,
        "authority_state": authority_state,
        "scope": _scopes(path),
        "sensitivity": sensitivity,
        "business_stage": _business_stage(path, material_class),
        "derivation": derivation,
        "classification_confidence": confidence,
        "classification_reasons": reasons,
        **policy,
    }


def _sha256(path: Path) -> tuple[str, int]:
    before = path.stat()
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    after = path.stat()
    if before.st_size != after.st_size or before.st_mtime_ns != after.st_mtime_ns:
        raise OSError("source changed while hashing")
    return digest.hexdigest(), after.st_size


def _source_id(source_path: str) -> str:
    digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest()
    return f"path:{digest}"


def _error_record(
    source_path: str,
    classification: dict[str, Any],
    *,
    code: str,
    message: str,
    as_of: str | None,
) -> dict[str, Any]:
    blocked = list(
        dict.fromkeys(
            [
                *classification["blocked_use"],
                "retrieval",
                "generation_context",
            ]
        )
    )
    return {
        "version": "hxy-source-card.v2",
        "source_id": _source_id(source_path),
        "source_path": source_path,
        "content_id": None,
        "source_hash": None,
        "size_bytes": None,
        "file_extension": PurePosixPath(source_path).suffix.lower(),
        **classification,
        "allowed_use": ["audit_only"],
        "blocked_use": blocked,
        "retrieval_state": "excluded",
        "canonical_source_path": None,
        "duplicate_paths": [],
        "error": {"code": code, "message": message},
        "created_at": as_of,
    }


def _effective_group_policy(records: list[dict[str, Any]]) -> dict[str, Any]:
    non_artifacts = [
        record
        for record in records
        if record["material_class"] not in {"processing_artifact", "tool_artifact"}
    ]
    effective = non_artifacts or records
    sensitivity_rank = {"public": 0, "internal": 1, "restricted": 2, "founder_only": 3}
    retrieval_rank = {
        "eligible_reference": 0,
        "pending_source_decision": 1,
        "excluded": 2,
    }
    sensitivity = max(
        (record["sensitivity"] for record in effective),
        key=sensitivity_rank.__getitem__,
    )
    retrieval_state = max(
        (record["retrieval_state"] for record in effective),
        key=retrieval_rank.__getitem__,
    )
    blocked_use = sorted(
        {
            blocked
            for record in effective
            for blocked in record["blocked_use"]
        }
    )
    return {
        "effective_sensitivity": sensitivity,
        "effective_retrieval_state": retrieval_state,
        "blocked_use": blocked_use,
    }


def build_source_registry(inbox: Path, *, as_of: str | None = None) -> dict[str, Any]:
    root = inbox.resolve()
    if not root.is_dir():
        raise ValueError("inbox must be an existing directory")

    records: list[dict[str, Any]] = []
    by_hash: dict[str, list[dict[str, Any]]] = defaultdict(list)
    paths = sorted(
        (
            path
            for path in root.rglob("*")
            if path.is_file() or path.is_symlink()
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )

    for path in paths:
        source_path = path.relative_to(root).as_posix()
        classification = classify_source_path(source_path)
        try:
            resolved = path.resolve(strict=True)
            resolved.relative_to(root)
        except (FileNotFoundError, ValueError):
            records.append(
                _error_record(
                    source_path,
                    classification,
                    code="source_outside_inbox",
                    message="source resolves outside inbox",
                    as_of=as_of,
                )
            )
            continue

        try:
            source_hash, size_bytes = _sha256(resolved)
        except OSError:
            records.append(
                _error_record(
                    source_path,
                    classification,
                    code="source_unreadable_or_changed",
                    message="source could not be read consistently",
                    as_of=as_of,
                )
            )
            continue

        record = {
            "version": "hxy-source-card.v2",
            "source_id": _source_id(source_path),
            "source_path": source_path,
            "content_id": f"sha256:{source_hash}",
            "source_hash": source_hash,
            "size_bytes": size_bytes,
            "file_extension": PurePosixPath(source_path).suffix.lower(),
            **classification,
            "canonical_source_path": None,
            "duplicate_paths": [],
            "error": None,
            "created_at": as_of,
        }
        records.append(record)
        by_hash[source_hash].append(record)

    content_groups: list[dict[str, Any]] = []
    for source_hash, group_records in by_hash.items():
        ordered = sorted(group_records, key=lambda record: record["source_path"])
        non_artifacts = [
            record
            for record in ordered
            if record["material_class"] not in {"processing_artifact", "tool_artifact"}
        ]
        canonical = (non_artifacts or ordered)[0]
        duplicate_paths = [
            record["source_path"]
            for record in ordered
            if record is not canonical
        ]
        for record in ordered:
            record["canonical_source_path"] = canonical["source_path"]
            record["duplicate_paths"] = list(duplicate_paths)
            if record is not canonical:
                record["derivation"] = "duplicate_copy"

        content_groups.append(
            {
                "content_id": f"sha256:{source_hash}",
                "source_hash": source_hash,
                "canonical_source_path": canonical["source_path"],
                "all_source_paths": [record["source_path"] for record in ordered],
                "path_count": len(ordered),
                **_effective_group_policy(ordered),
            }
        )

    records.sort(key=lambda record: record["source_path"])
    content_groups.sort(key=lambda group: group["content_id"])
    return {
        "version": "hxy-source-registry.v2",
        "as_of": as_of,
        "counts": {
            "path_records": len(records),
            "content_groups": len(content_groups),
            "duplicate_paths": sum(max(0, group["path_count"] - 1) for group in content_groups),
            "error_records": sum(record["error"] is not None for record in records),
            "approved_sources": sum(
                record["authority_state"] == "approved" for record in records
            ),
        },
        "path_records": records,
        "content_groups": content_groups,
    }


def _atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
            temporary_path = Path(temporary.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def _summary_markdown(registry: dict[str, Any]) -> str:
    records = registry["path_records"]
    material_counts: dict[str, int] = defaultdict(int)
    sensitivity_counts: dict[str, int] = defaultdict(int)
    for record in records:
        material_counts[record["material_class"]] += 1
        sensitivity_counts[record["sensitivity"]] += 1
    lines = [
        "# HXY Source Registry V2",
        "",
        "> Private, read-only source inventory. It does not approve or publish knowledge.",
        "",
        f"- As of: `{registry.get('as_of') or 'unspecified'}`",
        f"- Path records: `{registry['counts']['path_records']}`",
        f"- Content groups: `{registry['counts']['content_groups']}`",
        f"- Duplicate paths: `{registry['counts']['duplicate_paths']}`",
        f"- Error records: `{registry['counts']['error_records']}`",
        f"- Approved sources: `{registry['counts']['approved_sources']}`",
        "",
        "## Material Classes",
        "",
    ]
    for key in sorted(material_counts):
        lines.append(f"- `{key}`: `{material_counts[key]}`")
    lines.extend(["", "## Sensitivity", ""])
    for key in sorted(sensitivity_counts):
        lines.append(f"- `{key}`: `{sensitivity_counts[key]}`")
    restricted_paths = [
        record["source_path"]
        for record in records
        if record["sensitivity"] in {"restricted", "founder_only"}
    ]
    if restricted_paths:
        lines.extend(["", "## Restricted Source Paths", ""])
        lines.extend(f"- `{path}`" for path in restricted_paths)
    return "\n".join(lines) + "\n"


def write_registry_reports(
    registry: dict[str, Any],
    output_dir: Path,
    *,
    report_date: str,
) -> dict[str, Path]:
    json_path = output_dir / f"{report_date}-source-registry.json"
    markdown_path = output_dir / f"{report_date}-source-registry.md"
    json_content = json.dumps(
        registry,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"
    _atomic_write(json_path, json_content)
    _atomic_write(markdown_path, _summary_markdown(registry))
    return {"json": json_path, "markdown": markdown_path}
