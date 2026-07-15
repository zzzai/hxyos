from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StrictMaterialModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceAuthorityUpdate(StrictMaterialModel):
    source_origin: Literal["internal", "external", "unknown"]
    source_authority: Literal[
        "official_internal",
        "internal_material",
        "external_reference",
    ]
    reason: str = Field(min_length=4, max_length=500)


class MaterialReceipt(StrictMaterialModel):
    status: Literal["已收到"]
    message: str


class MaterialOriginal(StrictMaterialModel):
    url: str
    can_preview: bool


class MaterialUnderstanding(StrictMaterialModel):
    summary: str
    document_type: str
    source_origin: Literal["internal", "external", "unknown"]
    authority_level: Literal[
        "working_material",
        "claimed_official",
        "reference",
        "fragment",
    ]
    knowledge_scale: Literal["macro", "meso", "micro", "unknown"]
    domain: Literal[
        "brand",
        "product",
        "operations",
        "store",
        "customer",
        "finance",
        "organization",
        "compliance",
        "external",
        "general",
    ]
    parse_status: Literal[
        "extracted",
        "metadata_only",
        "needs_multimodal",
        "needs_deep_parse",
    ]
    confidence: Literal["high", "medium", "low"]
    warnings: list[str] = Field(max_length=5)
    official_use_allowed: Literal[False]
    use_boundary: str


class ProductMaterial(StrictMaterialModel):
    id: UUID
    file_name: str
    media_type: str
    size_bytes: int = Field(gt=0)
    status: Literal["processing", "ready", "needs_attention"]
    receipt: MaterialReceipt
    original: MaterialOriginal
    understanding: MaterialUnderstanding
    source_origin: Literal["internal", "external", "unknown"]
    source_authority: Literal[
        "official_internal",
        "internal_material",
        "external_reference",
    ]
    authority_version: int = Field(ge=1)
    created_at: datetime
    updated_at: datetime


class UploadMaterialResponse(StrictMaterialModel):
    material: ProductMaterial


class MaterialDetailResponse(StrictMaterialModel):
    material: ProductMaterial


class ListMaterialsResponse(StrictMaterialModel):
    items: list[ProductMaterial]
    count: int = Field(ge=0)
