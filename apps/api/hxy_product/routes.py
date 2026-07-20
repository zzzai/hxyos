from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from types import MappingProxyType
from typing import Any, Callable
from uuid import UUID

from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .auth import (
    ProductAuthSettings,
    Principal,
    build_principal_resolver,
    gateway_secret_is_strong,
    select_session_token,
)
from .schemas import (
    AssignmentContext,
    MeResponse,
    OrganizationContext,
    SessionGrantRequest,
    StoreContext,
    UserContext,
)


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
            "materials:create",
            "materials:classify",
            "materials:read",
            "operating:accept",
            "operating:escalate",
            "operating:execute",
            "operating:read",
            "operating:report",
            "organization:read",
            "records:create",
            "records:read",
            "stores:read",
            "tasks:manage",
            "tasks:read",
        ),
        "hq_operations": (
            "conversation:use",
            "materials:create",
            "materials:classify",
            "materials:read",
            "operating:accept",
            "operating:escalate",
            "operating:execute",
            "operating:read",
            "operating:report",
            "operations:manage",
            "organization:read",
            "records:create",
            "records:read",
            "stores:read",
            "tasks:manage",
            "tasks:read",
        ),
        "store_manager": (
            "conversation:use",
            "issues:create",
            "materials:create",
            "materials:read",
            "operating:accept",
            "operating:escalate",
            "operating:execute",
            "operating:read",
            "operating:report",
            "records:create",
            "records:read",
            "services:create",
            "services:feedback",
            "services:read",
            "services:reconcile",
            "store:operate",
            "store:read",
            "tasks:manage",
            "tasks:read",
        ),
        "store_employee": (
            "conversation:use",
            "issues:create",
            "materials:create",
            "materials:read",
            "operating:execute",
            "operating:read",
            "operating:report",
            "records:create",
            "records:read",
            "services:create",
            "services:feedback",
            "services:read",
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


def assignment_for_principal(principal: Principal, repository: Any) -> Any:
    assignment = next(
        (
            item
            for item in repository.list_assignments(principal.account_id)
            if item.assignment_id == principal.assignment_id
        ),
        None,
    )
    if assignment is None:
        raise HTTPException(status_code=403, detail="Forbidden")
    return assignment


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


def _verified_gateway_assertion(
    payload: Any,
    settings: ProductAuthSettings,
) -> tuple[str, str, int]:
    if not isinstance(payload, dict) or set(payload) != {
        "account_id",
        "timestamp",
        "assertion_id",
        "signature",
    }:
        raise _unauthorized()
    account_id = payload.get("account_id")
    timestamp = payload.get("timestamp")
    assertion_id = payload.get("assertion_id")
    signature = payload.get("signature")
    if (
        not isinstance(account_id, str)
        or not isinstance(timestamp, int)
        or isinstance(timestamp, bool)
        or not isinstance(assertion_id, str)
        or not isinstance(signature, str)
    ):
        raise _unauthorized()

    message = f"{account_id}:{timestamp}:{assertion_id}".encode("utf-8")
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
        return str(UUID(account_id)), str(UUID(assertion_id)), timestamp
    except (ValueError, AttributeError):
        raise _unauthorized() from None


def _expire_session_cookie(
    response: JSONResponse,
    settings: ProductAuthSettings,
) -> None:
    response.delete_cookie(
        key="hxy_session",
        path="/api/v1",
        secure=settings.secure_cookie,
        httponly=True,
        samesite="lax",
    )


def _authenticated_session_response(
    raw_token: str,
    settings: ProductAuthSettings,
) -> JSONResponse:
    response = JSONResponse({"status": "authenticated"})
    response.set_cookie(
        key="hxy_session",
        value=raw_token,
        max_age=settings.session_ttl_seconds,
        path="/api/v1",
        secure=settings.secure_cookie,
        httponly=True,
        samesite="lax",
    )
    return response


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
        if not gateway_secret_is_strong(auth_settings.gateway_secret):
            raise HTTPException(status_code=503, detail="Service Unavailable")
        try:
            payload = await request.json()
        except ValueError:
            raise _unauthorized() from None
        account_id, assertion_id, assertion_timestamp = _verified_gateway_assertion(
            payload,
            auth_settings,
        )
        repository = get_repository()
        raw_token = secrets.token_urlsafe(32)
        principal = repository.exchange_gateway_assertion(
            account_id,
            assertion_id,
            assertion_timestamp + auth_settings.assertion_max_age_seconds,
            raw_token,
            auth_settings.session_ttl_seconds,
        )
        if principal is None:
            raise _unauthorized()
        return _authenticated_session_response(raw_token, auth_settings)

    @router.post("/api/v1/auth/session-grant")
    def one_time_session_grant_exchange(request: SessionGrantRequest) -> JSONResponse:
        repository = get_repository()
        raw_token = secrets.token_urlsafe(32)
        principal = repository.exchange_session_grant(
            request.grant,
            raw_token,
            auth_settings.session_ttl_seconds,
        )
        if principal is None:
            raise _unauthorized()
        return _authenticated_session_response(raw_token, auth_settings)

    @router.post("/api/v1/auth/logout")
    def logout(
        authorization: str | None = Header(default=None),
        hxy_session: str | None = Cookie(default=None, alias="hxy_session"),
        repository: Any = Depends(get_repository),
    ) -> JSONResponse:
        try:
            raw_token = select_session_token(
                authorization,
                hxy_session,
                required=False,
            )
        except HTTPException:
            response = JSONResponse({"detail": "Unauthorized"}, status_code=401)
            _expire_session_cookie(response, auth_settings)
            return response
        if raw_token is not None:
            repository.delete_session(raw_token)
        response = JSONResponse({"status": "ok"})
        _expire_session_cookie(response, auth_settings)
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

        active_assignment = next(
            (
                assignment
                for assignment in assignments
                if assignment.assignment_id == principal.assignment_id
            ),
            None,
        )
        if active_assignment is None:
            raise HTTPException(status_code=403, detail="Forbidden")
        if assignment_id is not None and assignment_id != active_assignment.assignment_id:
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
