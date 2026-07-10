from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class KnowledgeSettings:
    root_dir: Path
    database_url: str
    run_name: str = "inbox-2026-06-11"
    api_token: str = ""
    cors_origins: tuple[str, ...] = ()
    max_upload_bytes: int = 10 * 1024 * 1024
    max_material_storage_bytes: int = 1024 * 1024 * 1024
    min_material_free_bytes: int = 512 * 1024 * 1024
    allowed_upload_extensions: tuple[str, ...] = (
        ".csv",
        ".doc",
        ".docx",
        ".jpeg",
        ".jpg",
        ".json",
        ".md",
        ".pdf",
        ".png",
        ".ppt",
        ".pptx",
        ".txt",
        ".webp",
        ".xls",
        ".xlsx",
    )


def _csv_env(name: str, default: str = "") -> tuple[str, ...]:
    value = os.environ.get(name, default)
    return tuple(item.strip() for item in value.split(",") if item.strip())


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    if not value:
        return default
    try:
        parsed = int(value)
    except ValueError:
        return default
    return parsed if parsed > 0 else default


def get_settings() -> KnowledgeSettings:
    root_dir = Path(os.environ.get("HXY_ROOT_DIR", "/root/hxy")).resolve()
    return KnowledgeSettings(
        root_dir=root_dir,
        database_url=os.environ.get("HXY_DATABASE_URL", ""),
        run_name=os.environ.get("HXY_KNOWLEDGE_RUN", "inbox-2026-06-11"),
        api_token=os.environ.get("HXY_API_TOKEN", "").strip(),
        cors_origins=_csv_env(
            "HXY_CORS_ORIGINS",
            "http://127.0.0.1:8088,http://localhost:8088,http://127.0.0.1:18084,http://localhost:18084",
        ),
        max_upload_bytes=_int_env("HXY_MAX_UPLOAD_BYTES", 10 * 1024 * 1024),
        max_material_storage_bytes=_int_env(
            "HXY_MAX_MATERIAL_STORAGE_BYTES",
            1024 * 1024 * 1024,
        ),
        min_material_free_bytes=_int_env(
            "HXY_MIN_MATERIAL_FREE_BYTES",
            512 * 1024 * 1024,
        ),
        allowed_upload_extensions=tuple(
            extension.lower()
            for extension in _csv_env(
                "HXY_ALLOWED_UPLOAD_EXTENSIONS",
                ".csv,.doc,.docx,.jpeg,.jpg,.json,.md,.pdf,.png,.ppt,.pptx,.txt,.webp,.xls,.xlsx",
            )
        ),
    )
