"""Build a private parser-routing audit from the governed source registry."""

from __future__ import annotations

import json
import os
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from .document_router import build_parser_plan


_ARTIFACT_CLASSES = {"processing_artifact", "tool_artifact"}


def _safe_source(root: Path, source_path: str) -> Path | None:
    try:
        candidate = (root / source_path).resolve(strict=True)
        candidate.relative_to(root)
    except (FileNotFoundError, ValueError):
        return None
    return candidate if candidate.is_file() else None


def build_source_routing_report(
    inbox: Path,
    registry: dict[str, Any],
    *,
    as_of: str | None = None,
) -> dict[str, Any]:
    root = inbox.resolve()
    if not root.is_dir():
        raise ValueError("inbox must be an existing directory")

    items: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    excluded_duplicates = 0
    excluded_artifacts = 0
    by_primary: Counter[str] = Counter()
    by_complexity: Counter[str] = Counter()
    by_extension: Counter[str] = Counter()
    needs_attention = 0
    pending_adapters = 0

    for record in registry.get("path_records") or []:
        source_path = str(record.get("source_path") or "")
        if record.get("material_class") in _ARTIFACT_CLASSES:
            excluded_artifacts += 1
            continue
        canonical = str(record.get("canonical_source_path") or source_path)
        if canonical != source_path:
            excluded_duplicates += 1
            continue
        if record.get("error"):
            errors.append({"source_path": source_path, "code": "registry_error"})
            continue
        source = _safe_source(root, source_path)
        if source is None:
            errors.append({"source_path": source_path, "code": "source_unavailable"})
            continue

        plan = build_parser_plan(source)
        primary = str(plan["primary"])
        complexity = str(plan["complexity"])
        extension = source.suffix.lower() or "[no_extension]"
        by_primary[primary] += 1
        by_complexity[complexity] += 1
        by_extension[extension] += 1
        requires_human_review = bool(plan.get("requires_human_review"))
        automation_state = str(plan.get("automation_state") or "manual_attention")
        needs_attention += int(requires_human_review)
        pending_adapters += int(automation_state == "pending_adapter")
        items.append(
            {
                "source_path": source_path,
                "content_id": record.get("content_id"),
                "file_extension": extension,
                "material_class": record.get("material_class"),
                "authority_state": record.get("authority_state"),
                "sensitivity": record.get("sensitivity"),
                "scope": list(record.get("scope") or []),
                "parser_plan": plan,
                "automation_state": automation_state,
                "official_use_allowed": False,
                "requires_human_review": requires_human_review,
            }
        )

    items.sort(key=lambda item: item["source_path"])
    return {
        "version": "hxy-source-routing-report.v1",
        "as_of": as_of,
        "source_registry_version": registry.get("version"),
        "counts": {
            "routed_sources": len(items),
            "excluded_duplicates": excluded_duplicates,
            "excluded_artifacts": excluded_artifacts,
            "error_sources": len(errors),
            "needs_attention": needs_attention + len(errors),
            "pending_adapters": pending_adapters,
            "by_primary": dict(sorted(by_primary.items())),
            "by_complexity": dict(sorted(by_complexity.items())),
            "by_extension": dict(sorted(by_extension.items())),
        },
        "items": items,
        "errors": errors,
        "official_use_allowed": False,
        "requires_human_review": bool(needs_attention or errors),
        "authority_rule": "routing_reports_select_tools_but_do_not_interpret_or_approve_sources",
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


def _summary_markdown(report: dict[str, Any]) -> str:
    counts = report.get("counts") or {}
    lines = [
        "# HXY Source Routing Report",
        "",
        "> Private parser-routing audit. It does not parse, interpret, approve, or publish source content.",
        "",
        f"- As of: `{report.get('as_of') or 'unspecified'}`",
        f"- Routed unique sources: `{counts.get('routed_sources', 0)}`",
        f"- Excluded duplicate paths: `{counts.get('excluded_duplicates', 0)}`",
        f"- Excluded processing/tool artifacts: `{counts.get('excluded_artifacts', 0)}`",
        f"- Routing errors: `{counts.get('error_sources', 0)}`",
        f"- Need human attention: `{counts.get('needs_attention', 0)}`",
        f"- Pending adapters: `{counts.get('pending_adapters', 0)}`",
        "",
        "## Parser Load",
        "",
    ]
    for name, count in sorted((counts.get("by_primary") or {}).items()):
        lines.append(f"- `{name}`: `{count}`")
    lines.extend(["", "## Complexity", ""])
    for name, count in sorted((counts.get("by_complexity") or {}).items()):
        lines.append(f"- `{name}`: `{count}`")
    return "\n".join(lines) + "\n"


def write_source_routing_report(
    report: dict[str, Any],
    output_dir: Path,
    *,
    report_date: str,
) -> dict[str, Path]:
    json_path = output_dir / f"{report_date}-source-routing.json"
    markdown_path = output_dir / f"{report_date}-source-routing.md"
    _atomic_write(
        json_path,
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    )
    _atomic_write(markdown_path, _summary_markdown(report))
    return {"json": json_path, "markdown": markdown_path}
