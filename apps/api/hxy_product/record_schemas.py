from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


RecordSourceType = Literal["text", "link", "image", "audio", "video", "document", "file"]
RecordProcessingStatus = Literal["received", "processing", "ready", "needs_attention"]


class StrictRecordModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecordEvidence(StrictRecordModel):
    source_record_id: str = Field(min_length=1, max_length=80)
    source_asset_id: str | None = Field(default=None, min_length=1, max_length=80)
    quote: str = Field(min_length=1, max_length=1000)
    locator: str | None = Field(default=None, min_length=1, max_length=300)


class RecordInterpretationItem(StrictRecordModel):
    statement: str = Field(min_length=1, max_length=1000)
    evidence: list[RecordEvidence] = Field(default_factory=list, max_length=50)


class RecordInterpretation(StrictRecordModel):
    version: str = Field(min_length=1, max_length=100)
    summary: str = Field(max_length=2000)
    facts: list[RecordInterpretationItem] = Field(default_factory=list, max_length=100)
    decisions: list[RecordInterpretationItem] = Field(default_factory=list, max_length=100)
    progress: list[RecordInterpretationItem] = Field(default_factory=list, max_length=100)
    risks: list[RecordInterpretationItem] = Field(default_factory=list, max_length=100)
    missing_information: list[str] = Field(default_factory=list, max_length=100)
    confidence: float = Field(ge=0, le=1)
    official_knowledge: Literal[False] = False


class OrganizationRecordAsset(StrictRecordModel):
    id: str = Field(min_length=1, max_length=80)
    file_name: str = Field(min_length=1, max_length=180)
    media_type: str = Field(min_length=1, max_length=160)
    size_bytes: int = Field(ge=0)
    status: RecordProcessingStatus


class OrganizationRecordOriginal(StrictRecordModel):
    text: str = Field(max_length=20000)
    assets: list[OrganizationRecordAsset] = Field(default_factory=list, max_length=100)


class OrganizationRecord(StrictRecordModel):
    id: str = Field(min_length=1, max_length=80)
    source_types: list[RecordSourceType] = Field(default_factory=list, max_length=20)
    preview: str = Field(max_length=240)
    submitted_by: str = Field(max_length=160)
    store_id: str | None = Field(default=None, max_length=160)
    captured_at: datetime
    occurred_at: datetime | None = None
    processing_status: RecordProcessingStatus
    original: OrganizationRecordOriginal
    interpretation: RecordInterpretation | None = None
