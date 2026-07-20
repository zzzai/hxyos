from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


BriefKind = Literal["risk", "decision", "progress"]
BriefSeverity = Literal["low", "medium", "high", "critical"]

_SEVERITY_RANK = {"critical": 0, "high": 1, "medium": 2, "low": 3}
_WHY_IT_MATTERS = {
    "risk": "这项风险可能影响后续工作，需要查看原始依据。",
    "decision": "这是已经记录的关键决定，需要保持执行一致。",
    "progress": "这是近期发生的重要变化，需要了解上下文。",
}


class StrictBriefModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class BriefEvidence(StrictBriefModel):
    source_record_id: str = Field(min_length=1, max_length=80)
    source_asset_id: str | None = Field(default=None, min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=1000)
    locator: str | None = Field(default=None, min_length=1, max_length=300)


class BriefNextAction(StrictBriefModel):
    type: Literal["open_record", "ask_about_record"]
    label: str = Field(min_length=1, max_length=80)
    prompt: str | None = Field(default=None, max_length=1000)


class TodayBriefItem(StrictBriefModel):
    id: str = Field(min_length=1, max_length=80)
    kind: BriefKind
    severity: BriefSeverity | None = None
    statement: str = Field(min_length=1, max_length=1000)
    why_it_matters: str = Field(min_length=1, max_length=500)
    source_record_id: str = Field(min_length=1, max_length=80)
    evidence: list[BriefEvidence] = Field(min_length=1, max_length=5)
    captured_at: datetime
    next_action: BriefNextAction


class TodayResponse(StrictBriefModel):
    items: list[TodayBriefItem] = Field(default_factory=list, max_length=3)


def _object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (TypeError, ValueError):
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _captured_at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def _evidence(value: Any, record_id: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    result: list[dict[str, Any]] = []
    for candidate in value[:5]:
        if not isinstance(candidate, dict):
            continue
        source_record_id = str(candidate.get("source_record_id") or "").strip()
        quote = str(candidate.get("quote") or "").strip()[:1000]
        if source_record_id != record_id or not quote:
            continue
        item: dict[str, Any] = {
            "source_record_id": record_id,
            "quote": quote,
        }
        source_asset_id = str(candidate.get("source_asset_id") or "").strip()[:80]
        locator = str(candidate.get("locator") or "").strip()[:300]
        if source_asset_id:
            item["source_asset_id"] = source_asset_id
        if locator:
            item["locator"] = locator
        result.append(item)
    return result


def _stable_id(record_id: str, kind: str, index: int, statement: str) -> str:
    digest = hashlib.sha256(
        f"{record_id}\x00{kind}\x00{index}\x00{statement}".encode("utf-8")
    ).hexdigest()[:20]
    return f"brief-{digest}"


def project_brief_items(
    records: list[dict[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    candidates: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
    for record in records:
        record_id = str(record.get("id") or record.get("record_id") or "").strip()
        captured_at = _captured_at(record.get("captured_at"))
        interpretation = _object(
            record.get("interpretation") or record.get("interpretation_payload")
        )
        if not record_id or captured_at is None or not interpretation:
            continue

        for kind, section in (
            ("risk", "risks"),
            ("decision", "decisions"),
            ("progress", "progress"),
        ):
            values = interpretation.get(section)
            if not isinstance(values, list):
                continue
            for index, value in enumerate(values[:5]):
                if not isinstance(value, dict):
                    continue
                statement = str(value.get("statement") or "").strip()[:1000]
                item_evidence = _evidence(value.get("evidence"), record_id)
                if not statement or not item_evidence:
                    continue

                severity: str | None = None
                if kind == "risk":
                    candidate_severity = str(value.get("severity") or "").strip()
                    if candidate_severity not in _SEVERITY_RANK:
                        continue
                    severity = candidate_severity
                    category = 0 if severity in {"critical", "high"} else 3
                    within_category = _SEVERITY_RANK[severity]
                else:
                    category = 1 if kind == "decision" else 2
                    within_category = 0

                item = {
                    "id": _stable_id(record_id, kind, index, statement),
                    "kind": kind,
                    "severity": severity,
                    "statement": statement,
                    "why_it_matters": _WHY_IT_MATTERS[kind],
                    "source_record_id": record_id,
                    "evidence": item_evidence,
                    "captured_at": captured_at,
                    "next_action": {
                        "type": "open_record",
                        "label": "查看记录",
                    },
                }
                rank = (
                    category,
                    within_category,
                    -captured_at.timestamp(),
                    record_id,
                    index,
                )
                candidates.append((rank, item))

    bounded_limit = max(1, min(int(limit), 3))
    return [item for _rank, item in sorted(candidates, key=lambda pair: pair[0])][
        :bounded_limit
    ]
