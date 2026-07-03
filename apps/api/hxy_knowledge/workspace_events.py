from __future__ import annotations

import copy
import json
import re
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable


VERSION = "hxy-workspace-event.v1"
DEFAULT_TOPIC = "AI 工作记录"
AUTHORITY_RULE = "workspace_events_are_episodic_memory_not_approved_knowledge"
VALID_VISIBILITIES = {
    "public_org",
    "private_draft",
    "restricted_role",
    "redacted_public",
}

SENSITIVE_PATTERNS = [
    re.compile(
        r"\b(?:api[_-]?key|token|password|secret|database_url|"
        r"HXY_API_TOKEN|HXY_DATABASE_URL)\b",
        re.IGNORECASE,
    ),
    re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    re.compile(
        r"\b(?:financing|fundraising|equity|valuation|cap\s*table|"
        r"term\s*sheet)\b|(?:投资|融资|股权|估值|股份|期权|股东)",
        re.IGNORECASE,
    ),
]

def create_workspace_event(
    payload: dict,
    *,
    store_path: Path,
    now: Callable[[], str] | None = None,
) -> dict:
    visibility = _resolve_visibility(payload)
    event = {
        "version": VERSION,
        "event_id": f"workspace-event-{secrets.token_urlsafe(8)}",
        "topic": payload.get("topic") or DEFAULT_TOPIC,
        "actor": payload.get("actor") or "unknown",
        "role": payload.get("role") or "team",
        "visibility": visibility,
        "input": payload.get("input") or "",
        "ai_output": payload.get("ai_output") or {},
        "evidence": _list_or_empty(payload.get("evidence")),
        "risk_flags": _list_or_empty(payload.get("risk_flags")),
        "corrections": _list_or_empty(payload.get("corrections")),
        "generated_tasks": _list_or_empty(payload.get("generated_tasks")),
        "memory_action": payload.get("memory_action")
        or {"type": "process_memory_context_only", "allowed_as_authority": False},
        "review_action": payload.get("review_action")
        or {"type": "none", "required": False},
        "memory_layer": "episodic",
        "official_use_allowed": False,
        "authority_rule": AUTHORITY_RULE,
        "created_at": now() if now else _utc_now(),
    }

    store_path.parent.mkdir(parents=True, exist_ok=True)
    with store_path.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")

    return event


def list_workspace_events(
    store_path: Path,
    *,
    limit: int = 20,
    query: str = "",
    visibility: str | None = None,
) -> dict:
    events = _read_events(store_path)
    events.sort(key=lambda item: item.get("created_at", ""), reverse=True)

    normalized_query = query.casefold().strip()
    filtered = []
    for event in events:
        if event.get("visibility") == "private_draft":
            continue
        if visibility and event.get("visibility") != visibility:
            continue
        public_event = redact_workspace_event(event)
        if normalized_query and normalized_query not in _search_text(public_event):
            continue
        filtered.append(public_event)
        if len(filtered) >= limit:
            break

    return {"items": filtered, "count": len(filtered)}


def get_workspace_event(store_path: Path, event_id: str) -> dict | None:
    for event in _read_events(store_path):
        if event.get("event_id") == event_id:
            return event
    return None


def redact_workspace_event(event: dict) -> dict:
    redacted = copy.deepcopy(event)
    if redacted.get("visibility") in {"restricted_role", "redacted_public"}:
        if redacted.get("visibility") == "restricted_role":
            redacted["visibility"] = "redacted_public"
        for key in (
            "topic",
            "actor",
            "role",
            "risk_flags",
            "memory_action",
            "review_action",
        ):
            if key in redacted:
                redacted[key] = _redact_sensitive_value(redacted[key])
        for key in ("input", "ai_output", "evidence", "corrections", "generated_tasks"):
            redacted[key] = "[redacted]"
    return redacted


def classify_workspace_visibility(payload: dict) -> str:
    explicit = payload.get("visibility")
    if explicit == "private_draft":
        return "private_draft"
    if explicit == "redacted_public":
        return "redacted_public"
    if _is_sensitive(payload):
        return "restricted_role"
    if explicit in VALID_VISIBILITIES:
        return explicit
    return "public_org"


def _resolve_visibility(payload: dict) -> str:
    return classify_workspace_visibility(payload)


def _is_sensitive(payload: dict) -> bool:
    rendered = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return any(pattern.search(rendered) for pattern in SENSITIVE_PATTERNS)


def _redact_sensitive_value(value):
    if isinstance(value, str):
        if any(pattern.search(value) for pattern in SENSITIVE_PATTERNS):
            return "[redacted]"
        return value
    if isinstance(value, list):
        return [_redact_sensitive_value(item) for item in value]
    if isinstance(value, dict):
        return {
            _redact_sensitive_value(key): _redact_sensitive_value(item)
            for key, item in value.items()
        }
    return value


def _search_text(event: dict) -> str:
    parts = [
        str(event.get("topic", "")),
        str(event.get("input", "")),
    ]
    ai_output = event.get("ai_output")
    if isinstance(ai_output, dict):
        parts.append(str(ai_output.get("summary", "")))
    else:
        parts.append(str(ai_output or ""))
    return "\n".join(parts).casefold()


def _read_events(store_path: Path) -> list[dict]:
    if not store_path.exists():
        return []

    events = []
    with store_path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                events.append(item)
    return events


def _list_or_empty(value) -> list:
    if isinstance(value, list):
        return value
    return []


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
