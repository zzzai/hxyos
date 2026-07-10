from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from types import MappingProxyType
from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .auth import ProductAuthSettings, Principal, build_principal_resolver, require_session_token
from .schemas import AssignmentContext, MeResponse, OrganizationContext, StoreContext, UserContext


ROLE_LABELS = MappingProxyType(
    {
        "founder": "创始人",
        "hq_operations": "总部运营",
        "store_manager": "店长",
        "store_employee": "门店员工",
        "system_admin": "系统管理员",
    }
)

ROLE_CAPABILITIES = MappingProxyType(
    {
        "founder": (
            "conversation:use",
            "organization:read",
            "stores:read",
            "tasks:manage",
            "tasks:read",
        ),
        "hq_operations": (
            "conversation:use",
            "operations:manage",
            "organization:read",
            "stores:read",
            "tasks:manage",
            "tasks:read",
        ),
        "store_manager": (
            "conversation:use",
            "issues:create",
            "store:operate",
            "store:read",
            "tasks:manage",
            "tasks:read",
        ),
        "store_employee": (
            "conversation:use",
            "issues:create",
            "store:read",
            "tasks:read",
            "training:practice",
        ),
        "system_admin": (
            "conversation:use",
            "identity:admin",
            "system:admin",
        ),
    }
)


def _assignment_context(record: Any) -> AssignmentContext:
    if record.role not in ROLE_CAPABILITIES:
        raise HTTPException(status_code=403, detail="Forbidden")
    store = None
    if record.store_id is not None:
        store = StoreContext(id=record.store_id, name=record.store_name or "")
    return AssignmentContext(
        assignment_id=record.assignment_id,
        organization=OrganizationContext(
            id=record.organization_id,
            name=record.organization_name,
        ),
        store=store,
        role=record.role,
        role_label=ROLE_LABELS[record.role],
        capabilities=list(ROLE_CAPABILITIES[record.role]),
    )


def _unauthorized() -> HTTPException:
    return HTTPException(status_code=401, detail="Unauthorized")


def _verified_gateway_account_id(
    payload: Any,
    settings: ProductAuthSettings,
) -> str:
    if not isinstance(payload, dict) or set(payload) != {
        "account_id",
        "timestamp",
        "signature",
    }:
        raise _unauthorized()
    account_id = payload.get("account_id")
    timestamp = payload.get("timestamp")
    signature = payload.get("signature")
    if (
        not isinstance(account_id, str)
        or not isinstance(timestamp, int)
        or isinstance(timestamp, bool)
        or not isinstance(signature, str)
    ):
        raise _unauthorized()

    message = f"{account_id}:{timestamp}".encode("utf-8")
    expected_signature = hmac.new(
        settings.gateway_secret.encode("utf-8"),
        message,
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(signature, expected_signature):
        raise _unauthorized()
    if abs(int(time.time()) - timestamp) > settings.assertion_max_age_seconds:
        raise _unauthorized()
    try:
        return str(UUID(account_id))
    except (ValueError, AttributeError):
        raise _unauthorized() from None


def create_identity_router(
    repository_factory: Callable[[], Any],
    auth_settings: ProductAuthSettings,
) -> APIRouter:
    router = APIRouter()

    def get_repository() -> Any:
        return repository_factory()

    resolve_principal = build_principal_resolver(get_repository)

    @router.post("/api/v1/auth/session")
    async def trusted_gateway_session_exchange(request: Request) -> JSONResponse:
        if not auth_settings.gateway_secret:
            raise HTTPException(status_code=503, detail="Service Unavailable")
        try:
            payload = await request.json()
        except ValueError:
            raise _unauthorized() from None
        account_id = _verified_gateway_account_id(payload, auth_settings)
        repository = get_repository()
        principal = repository.find_active_principal(account_id)
        if principal is None:
            raise _unauthorized()

        raw_token = secrets.token_urlsafe(32)
        repository.create_session(
            principal.account_id,
            raw_token,
            auth_settings.session_ttl_seconds,
        )
        response = JSONResponse({"status": "authenticated"})
        response.set_cookie(
            key="hxy_session",
            value=raw_token,
            max_age=auth_settings.session_ttl_seconds,
            path="/api/v1",
            secure=auth_settings.secure_cookie,
            httponly=True,
            samesite="lax",
        )
        return response

    @router.post("/api/v1/auth/logout")
    def logout(
        raw_token: str = Depends(require_session_token),
        principal: Principal = Depends(resolve_principal),
        repository: Any = Depends(get_repository),
    ) -> JSONResponse:
        del principal
        repository.delete_session(raw_token)
        response = JSONResponse({"status": "ok"})
        response.delete_cookie(
            key="hxy_session",
            path="/api/v1",
            secure=auth_settings.secure_cookie,
            httponly=True,
            samesite="lax",
        )
        return response

    @router.get("/api/v1/me", response_model=MeResponse)
    def me(
        principal: Principal = Depends(resolve_principal),
        repository: Any = Depends(get_repository),
        assignment_id: str | None = Query(default=None),
    ) -> MeResponse:
        assignments = [
            _assignment_context(record)
            for record in repository.list_assignments(principal.account_id)
        ]
        if not assignments:
            raise HTTPException(status_code=403, detail="Forbidden")

        active_assignment = assignments[0]
        if assignment_id is not None:
            active_assignment = next(
                (
                    assignment
                    for assignment in assignments
                    if assignment.assignment_id == assignment_id
                ),
                None,
            )
            if active_assignment is None:
                raise HTTPException(status_code=403, detail="Forbidden")

        return MeResponse(
            user=UserContext(
                account_id=principal.account_id,
                display_name=principal.display_name,
            ),
            active_assignment=active_assignment,
            available_assignments=assignments,
        )

    return router
