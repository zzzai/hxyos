from __future__ import annotations

import hashlib
import mimetypes
import os
import re
import shutil
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote
from uuid import UUID, uuid4

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    Header,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse

from .auth import Principal, build_principal_resolver
from .material_schemas import (
    ListMaterialsResponse,
    MaterialDetailResponse,
    UploadMaterialResponse,
)
from .material_repository import MaterialStorageQuotaExceeded
from .routes import ROLE_CAPABILITIES, assignment_for_principal


RepositoryFactory = Callable[[], Any]
UnderstandingBuilder = Callable[..., dict[str, Any]]

PREVIEW_EXTENSIONS = frozenset({".jpeg", ".jpg", ".md", ".pdf", ".png", ".txt", ".webp"})
TEXT_EXTENSIONS = frozenset({".csv", ".json", ".md", ".txt"})
OOXML_EXTENSIONS = frozenset({".docx", ".pptx", ".xlsx"})
OLE_EXTENSIONS = frozenset({".doc", ".ppt", ".xls"})
SAFE_FILE_NAME = re.compile(r"^[^/\\\x00-\x1f\x7f]{1,180}$")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not Found")


def _validate_file_name(file_name: str) -> tuple[str, str]:
    if not SAFE_FILE_NAME.fullmatch(file_name) or file_name in {".", ".."}:
        raise HTTPException(status_code=400, detail="Invalid file name")
    extension = Path(file_name).suffix.lower()
    return file_name, extension


def _derived_media_type(file_name: str) -> str:
    extension = Path(file_name).suffix.lower()
    overrides = {
        ".md": "text/markdown",
        ".json": "application/json",
        ".csv": "text/csv",
    }
    return overrides.get(extension) or mimetypes.guess_type(file_name)[0] or "application/octet-stream"


def _matches_signature(extension: str, first_bytes: bytes) -> bool:
    if extension in TEXT_EXTENSIONS:
        return b"\x00" not in first_bytes
    if extension == ".pdf":
        return first_bytes.startswith(b"%PDF-")
    if extension == ".png":
        return first_bytes.startswith(b"\x89PNG\r\n\x1a\n")
    if extension in {".jpg", ".jpeg"}:
        return first_bytes.startswith(b"\xff\xd8\xff")
    if extension == ".webp":
        return len(first_bytes) >= 12 and first_bytes[:4] == b"RIFF" and first_bytes[8:12] == b"WEBP"
    if extension in OOXML_EXTENSIONS:
        return first_bytes.startswith(b"PK\x03\x04")
    if extension in OLE_EXTENSIONS:
        return first_bytes.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    return False


def _storage_path(material_root: Path, storage_key: str) -> Path | None:
    root = material_root.resolve()
    candidate = (root / storage_key).resolve()
    return candidate if candidate.is_relative_to(root) else None


def _existing_storage_parent(path: Path) -> Path:
    candidate = path
    while not candidate.exists() and candidate != candidate.parent:
        candidate = candidate.parent
    return candidate


def _safe_understanding(payload: Any) -> dict[str, Any]:
    source = payload if isinstance(payload, dict) else {}
    allowed_origins = {"internal", "external", "unknown"}
    allowed_authority = {"working_material", "claimed_official", "reference", "fragment"}
    allowed_scales = {"macro", "meso", "micro", "unknown"}
    allowed_domains = {
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
    }
    allowed_parse_status = {"extracted", "metadata_only", "needs_multimodal", "needs_deep_parse"}
    allowed_confidence = {"high", "medium", "low"}

    def choice(key: str, allowed: set[str], default: str) -> str:
        value = str(source.get(key) or "").strip()
        return value if value in allowed else default

    warnings = [str(item).strip()[:240] for item in source.get("warnings") or [] if str(item).strip()]
    return {
        "summary": str(source.get("summary") or "已收到资料，等待进一步理解。").strip()[:600],
        "document_type": str(source.get("document_type") or "文档资料").strip()[:80],
        "source_origin": choice("source_origin", allowed_origins, "unknown"),
        "authority_level": choice("authority_level", allowed_authority, "working_material"),
        "knowledge_scale": choice("knowledge_scale", allowed_scales, "unknown"),
        "domain": choice("domain", allowed_domains, "general"),
        "parse_status": choice("parse_status", allowed_parse_status, "metadata_only"),
        "confidence": choice("confidence", allowed_confidence, "low"),
        "warnings": warnings[:5],
        "official_use_allowed": False,
        "use_boundary": str(
            source.get("use_boundary")
            or "可用于整理候选知识，未经核定不能作为荷小悦正式口径。"
        ).strip()[:300],
    }


def _public_material(record: dict[str, Any]) -> dict[str, Any]:
    material_id = str(record.get("id") or record.get("material_id"))
    extension = str(record.get("extension") or Path(str(record.get("file_name") or "")).suffix).lower()
    return {
        "id": material_id,
        "file_name": str(record.get("file_name") or "未命名资料")[:180],
        "media_type": str(record.get("media_type") or "application/octet-stream")[:120],
        "size_bytes": int(record.get("size_bytes") or 0),
        "status": str(record.get("status") or "received"),
        "receipt": {
            "status": "已收到",
            "message": "资料已安全保存，当前不会自动变成正式知识。",
        },
        "original": {
            "url": f"/api/v1/materials/{material_id}/content",
            "can_preview": extension in PREVIEW_EXTENSIONS,
        },
        "understanding": _safe_understanding(record.get("understanding")),
        "created_at": record["created_at"],
        "updated_at": record["updated_at"],
    }


def create_material_router(
    identity_repository_factory: RepositoryFactory,
    material_repository_factory: RepositoryFactory,
    *,
    material_root: Path,
    max_upload_bytes: int,
    max_assignment_storage_bytes: int,
    min_material_free_bytes: int,
    allowed_extensions: set[str],
    understanding_builder: UnderstandingBuilder,
) -> APIRouter:
    router = APIRouter()
    material_root = material_root.resolve()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_material_repository() -> Any:
        return material_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def assignment_with(capability: str):
        def resolve_assignment(
            principal: Principal = Depends(resolve_principal),
            identity_repository: Any = Depends(get_identity_repository),
        ) -> Any:
            assignment = assignment_for_principal(principal, identity_repository)
            if capability not in ROLE_CAPABILITIES.get(assignment.role, ()):
                raise HTTPException(status_code=403, detail="Forbidden")
            return assignment

        return resolve_assignment

    resolve_material_creator = assignment_with("materials:create")
    resolve_material_reader = assignment_with("materials:read")

    @router.post(
        "/api/v1/materials",
        status_code=status.HTTP_201_CREATED,
        response_model=UploadMaterialResponse,
    )
    async def upload_material(
        file: UploadFile = File(...),
        note: str = Form(default="", max_length=1000),
        client_upload_id: UUID = Form(...),
        content_length: int | None = Header(default=None, alias="Content-Length"),
        assignment: Any = Depends(resolve_material_creator),
        repository: Any = Depends(get_material_repository),
    ) -> dict[str, Any]:
        if content_length is not None and content_length > max_upload_bytes + 64 * 1024:
            raise HTTPException(status_code=413, detail="Upload request is too large")
        file_name, extension = _validate_file_name(file.filename or "")
        if extension not in allowed_extensions:
            raise HTTPException(status_code=415, detail="Unsupported file type")

        existing = repository.get_by_client_upload_id(
            assignment.assignment_id,
            str(client_upload_id),
        )
        if existing is not None:
            if existing.get("file_name") != file_name:
                raise HTTPException(status_code=409, detail="Upload id already used")
            return {"material": _public_material(existing)}

        storage_usage = shutil.disk_usage(_existing_storage_parent(material_root))
        if storage_usage.free < min_material_free_bytes + max_upload_bytes:
            raise HTTPException(status_code=507, detail="Material storage is temporarily unavailable")

        material_id = str(uuid4())
        storage_key = f"{assignment.assignment_id}/{material_id}/{file_name}"
        destination = _storage_path(material_root, storage_key)
        if destination is None:
            raise HTTPException(status_code=400, detail="Invalid upload path")
        destination.parent.mkdir(parents=True, exist_ok=False)
        temporary = destination.with_name(f".{destination.name}.upload")
        digest = hashlib.sha256()
        size = 0
        first_bytes = b""
        try:
            with temporary.open("xb") as output:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    if not first_bytes:
                        first_bytes = chunk[:32]
                    size += len(chunk)
                    if size > max_upload_bytes:
                        raise HTTPException(status_code=413, detail="Upload file is too large")
                    digest.update(chunk)
                    output.write(chunk)
            if size == 0:
                raise HTTPException(status_code=400, detail="Upload file is empty")
            if not _matches_signature(extension, first_bytes):
                raise HTTPException(status_code=415, detail="File content does not match its type")
            os.replace(temporary, destination)
        except Exception:
            temporary.unlink(missing_ok=True)
            destination.unlink(missing_ok=True)
            try:
                destination.parent.rmdir()
            except OSError:
                pass
            raise

        media_type = _derived_media_type(file_name)
        material_status = "understood"
        try:
            understanding = _safe_understanding(
                understanding_builder(
                    path=destination,
                    file_name=file_name,
                    media_type=media_type,
                    note=note.strip(),
                    role=assignment.role,
                )
            )
        except Exception:
            material_status = "understanding_failed"
            understanding = _safe_understanding(
                {
                    "summary": f"已安全保存《{Path(file_name).stem}》，但本次系统理解没有完成。",
                    "parse_status": "metadata_only",
                    "warnings": ["系统理解暂时失败，原文件已保留，可稍后重试。"],
                    "official_use_allowed": False,
                }
            )

        try:
            record = repository.create_material(
                {
                    "material_id": material_id,
                    "assignment_id": assignment.assignment_id,
                    "client_upload_id": str(client_upload_id),
                    "file_name": file_name,
                    "extension": extension,
                    "media_type": media_type,
                    "size_bytes": size,
                    "sha256": digest.hexdigest(),
                    "storage_key": storage_key,
                    "note": note.strip(),
                    "status": material_status,
                    "understanding": understanding,
                    "official_use_allowed": False,
                    "max_assignment_storage_bytes": max_assignment_storage_bytes,
                }
            )
        except MaterialStorageQuotaExceeded:
            destination.unlink(missing_ok=True)
            try:
                destination.parent.rmdir()
            except OSError:
                pass
            raise HTTPException(
                status_code=507,
                detail="Assignment material storage quota exceeded",
            ) from None
        except Exception:
            destination.unlink(missing_ok=True)
            try:
                destination.parent.rmdir()
            except OSError:
                pass
            raise

        if str(record.get("id") or record.get("material_id")) != material_id:
            destination.unlink(missing_ok=True)
            try:
                destination.parent.rmdir()
            except OSError:
                pass

        return {"material": _public_material(record)}

    @router.post(
        "/api/v1/materials/{material_id}/understanding",
        response_model=MaterialDetailResponse,
    )
    def retry_material_understanding(
        material_id: UUID,
        assignment: Any = Depends(resolve_material_creator),
        repository: Any = Depends(get_material_repository),
    ) -> dict[str, Any]:
        record = repository.get_material(assignment.assignment_id, str(material_id))
        if record is None:
            raise _not_found()
        path = _storage_path(material_root, str(record.get("storage_key") or ""))
        if path is None or not path.is_file():
            raise _not_found()

        material_status = "understood"
        try:
            understanding = _safe_understanding(
                understanding_builder(
                    path=path,
                    file_name=str(record.get("file_name") or ""),
                    media_type=str(record.get("media_type") or "application/octet-stream"),
                    note=str(record.get("note") or ""),
                    role=assignment.role,
                )
            )
        except Exception:
            material_status = "understanding_failed"
            understanding = _safe_understanding(
                {
                    "summary": (
                        f"已安全保存《{Path(str(record.get('file_name') or '')).stem}》，"
                        "但本次系统理解没有完成。"
                    ),
                    "parse_status": "metadata_only",
                    "warnings": ["系统理解暂时失败，原文件已保留，可稍后重试。"],
                    "official_use_allowed": False,
                }
            )

        updated = repository.update_understanding(
            assignment.assignment_id,
            str(material_id),
            status=material_status,
            understanding=understanding,
        )
        if updated is None:
            raise _not_found()
        return {"material": _public_material(updated)}

    @router.get("/api/v1/materials", response_model=ListMaterialsResponse)
    def list_materials(
        limit: int = Query(default=50, ge=1, le=100),
        assignment: Any = Depends(resolve_material_reader),
        repository: Any = Depends(get_material_repository),
    ) -> dict[str, Any]:
        items = [
            _public_material(record)
            for record in repository.list_materials(assignment.assignment_id, limit=limit)
        ]
        return {"items": items, "count": len(items)}

    @router.get("/api/v1/materials/{material_id}", response_model=MaterialDetailResponse)
    def material_detail(
        material_id: UUID,
        assignment: Any = Depends(resolve_material_reader),
        repository: Any = Depends(get_material_repository),
    ) -> dict[str, Any]:
        record = repository.get_material(assignment.assignment_id, str(material_id))
        if record is None:
            raise _not_found()
        return {"material": _public_material(record)}

    @router.get("/api/v1/materials/{material_id}/content")
    def material_content(
        material_id: UUID,
        range_header: str | None = Header(default=None, alias="Range"),
        assignment: Any = Depends(resolve_material_reader),
        repository: Any = Depends(get_material_repository),
    ) -> FileResponse:
        if range_header and (len(range_header) > 128 or "," in range_header):
            raise HTTPException(status_code=416, detail="Range Not Satisfiable")
        record = repository.get_material(assignment.assignment_id, str(material_id))
        if record is None:
            raise _not_found()
        path = _storage_path(material_root, str(record.get("storage_key") or ""))
        if path is None or not path.is_file():
            raise _not_found()
        extension = str(record.get("extension") or "").lower()
        disposition = "inline" if extension in PREVIEW_EXTENSIONS else "attachment"
        encoded_name = quote(str(record.get("file_name") or "material"), safe="")
        response = FileResponse(
            path,
            media_type=str(record.get("media_type") or "application/octet-stream"),
            content_disposition_type=disposition,
            filename=str(record.get("file_name") or "material"),
        )
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "sandbox; default-src 'none'"
        response.headers["Content-Disposition"] = (
            f"{disposition}; filename*=utf-8''{encoded_name}"
        )
        return response

    return router
