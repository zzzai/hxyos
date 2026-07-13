from __future__ import annotations

import hashlib
import secrets
from collections.abc import Mapping
from typing import Any, Callable
from urllib.parse import quote, urlsplit, urlunsplit

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from .auth import Principal, ProductAuthSettings, build_principal_resolver
from .onboarding_policy import (
    ResolvedAssignment,
    ResolvedStore,
    can_deactivate_member,
    can_invite_member,
)
from .onboarding_repository import (
    OnboardingConflict,
    OnboardingRepositoryError,
    OnboardingScopeError,
    OnboardingValidationError,
)
from .onboarding_schemas import (
    AssignmentRole,
    AuthenticatedResponse,
    CreateInviteRequest,
    CreateInviteResponse,
    CreateStoreRequest,
    InviteResponse,
    InviteRole,
    MemberResponse,
    RedeemInviteRequest,
    StoreResponse,
)
from .routes import assignment_for_principal


RepositoryFactory = Callable[[], Any]
_MANAGEMENT_ROLES = frozenset(
    {AssignmentRole.FOUNDER, AssignmentRole.STORE_MANAGER}
)


def _forbidden() -> HTTPException:
    return HTTPException(status_code=403, detail="Forbidden")


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Not Found")


def _store_response(record: Mapping[str, Any]) -> StoreResponse:
    return StoreResponse(
        id=record["id"],
        name=record["name"],
        city=record["city"],
        address=record["address"],
        status=record["status"],
    )


def _member_response(record: Mapping[str, Any]) -> MemberResponse:
    return MemberResponse(
        assignment_id=record["assignment_id"],
        store_id=record["store_id"],
        display_name=record["display_name"],
        role=record["role"],
        status=record["status"],
    )


def _invite_response(record: Mapping[str, Any]) -> InviteResponse:
    return InviteResponse(
        id=record["id"],
        store_id=record["store_id"],
        role=record["role"],
        display_name=record["display_name"],
        status=record["status"],
        expires_at=record["expires_at"],
    )


def _invite_link(public_app_url: str, raw_token: str) -> str:
    parsed = urlsplit(public_app_url.strip())
    local_hosts = {"127.0.0.1", "localhost", "::1"}
    try:
        port_is_valid = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        port_is_valid = False
    if (
        not parsed.netloc
        or not parsed.hostname
        or parsed.scheme not in {"http", "https"}
        or (parsed.scheme != "https" and parsed.hostname not in local_hosts)
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not port_is_valid
    ):
        raise HTTPException(status_code=503, detail="Service Unavailable")
    fragment = f"invite={quote(raw_token, safe='-._~')}"
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path or "/", "", fragment))


def _management_repository_error(exc: OnboardingRepositoryError) -> HTTPException:
    if isinstance(exc, OnboardingScopeError):
        return _forbidden()
    if isinstance(exc, OnboardingConflict):
        return HTTPException(status_code=409, detail="Conflict")
    if isinstance(exc, OnboardingValidationError):
        return HTTPException(status_code=422, detail="Unprocessable Entity")
    return HTTPException(status_code=503, detail="Service Unavailable")


def create_onboarding_router(
    identity_repository_factory: RepositoryFactory,
    onboarding_repository_factory: RepositoryFactory,
    auth_settings: ProductAuthSettings,
    public_app_url: str,
) -> APIRouter:
    router = APIRouter()

    def get_identity_repository() -> Any:
        return identity_repository_factory()

    def get_onboarding_repository() -> Any:
        return onboarding_repository_factory()

    resolve_principal = build_principal_resolver(get_identity_repository)

    def resolve_actor(
        principal: Principal = Depends(resolve_principal),
        identity_repository: Any = Depends(get_identity_repository),
    ) -> ResolvedAssignment:
        record = assignment_for_principal(principal, identity_repository)
        try:
            actor = ResolvedAssignment(
                assignment_id=record.assignment_id,
                organization_id=record.organization_id,
                store_id=record.store_id,
                role=record.role,
            )
        except ValueError:
            raise _forbidden() from None
        if actor.role not in _MANAGEMENT_ROLES:
            raise _forbidden()
        return actor

    def confirmed_store(
        actor: ResolvedAssignment,
        repository: Any,
        store_id: str,
        *,
        require_active: bool = False,
    ) -> tuple[ResolvedStore, Mapping[str, Any]]:
        record = next(
            (
                item
                for item in repository.list_stores(actor.organization_id)
                if item.get("id") == store_id
            ),
            None,
        )
        if record is None or (require_active and record.get("status") != "active"):
            raise _not_found()
        return (
            ResolvedStore(
                organization_id=actor.organization_id,
                store_id=str(record["id"]),
            ),
            record,
        )

    @router.get(
        "/api/v1/organization/stores",
        response_model=list[StoreResponse],
    )
    def list_stores(
        actor: ResolvedAssignment = Depends(resolve_actor),
        repository: Any = Depends(get_onboarding_repository),
    ) -> list[StoreResponse]:
        records = repository.list_stores(actor.organization_id)
        if actor.role is AssignmentRole.FOUNDER:
            return [_store_response(record) for record in records]
        if actor.store_id is None:
            raise _forbidden()
        record = next(
            (item for item in records if item.get("id") == actor.store_id),
            None,
        )
        if record is None:
            raise _forbidden()
        return [_store_response(record)]

    @router.post(
        "/api/v1/organization/stores",
        response_model=StoreResponse,
        status_code=201,
    )
    def create_store(
        request: CreateStoreRequest,
        actor: ResolvedAssignment = Depends(resolve_actor),
        repository: Any = Depends(get_onboarding_repository),
    ) -> StoreResponse:
        if actor.role is not AssignmentRole.FOUNDER:
            raise _forbidden()
        try:
            record = repository.create_store(
                actor.organization_id,
                actor.assignment_id,
                request,
            )
        except OnboardingRepositoryError as exc:
            raise _management_repository_error(exc) from None
        return _store_response(record)

    @router.get(
        "/api/v1/organization/members",
        response_model=list[MemberResponse],
    )
    def list_members(
        actor: ResolvedAssignment = Depends(resolve_actor),
        repository: Any = Depends(get_onboarding_repository),
    ) -> list[MemberResponse]:
        store_id = None
        if actor.role is AssignmentRole.STORE_MANAGER:
            if actor.store_id is None:
                raise _forbidden()
            confirmed_store(actor, repository, actor.store_id)
            store_id = actor.store_id
        return [
            _member_response(record)
            for record in repository.list_members(actor.organization_id, store_id)
        ]

    @router.get(
        "/api/v1/organization/invites",
        response_model=list[InviteResponse],
    )
    def list_invites(
        actor: ResolvedAssignment = Depends(resolve_actor),
        repository: Any = Depends(get_onboarding_repository),
    ) -> list[InviteResponse]:
        store_id = None
        if actor.role is AssignmentRole.STORE_MANAGER:
            if actor.store_id is None:
                raise _forbidden()
            confirmed_store(actor, repository, actor.store_id)
            store_id = actor.store_id
        return [
            _invite_response(record)
            for record in repository.list_invites(actor.organization_id, store_id)
        ]

    @router.post(
        "/api/v1/organization/invites",
        response_model=CreateInviteResponse,
        status_code=201,
    )
    def create_invite(
        request: CreateInviteRequest,
        actor: ResolvedAssignment = Depends(resolve_actor),
        repository: Any = Depends(get_onboarding_repository),
    ) -> CreateInviteResponse:
        if actor.role is AssignmentRole.FOUNDER:
            if request.store_id is None:
                raise HTTPException(status_code=422, detail="Unprocessable Entity")
            store_id = request.store_id
        else:
            if actor.store_id is None:
                raise _forbidden()
            if request.store_id is not None and request.store_id != actor.store_id:
                raise _forbidden()
            store_id = actor.store_id

        target_store, _ = confirmed_store(
            actor,
            repository,
            store_id,
            require_active=True,
        )
        if not can_invite_member(actor, target_store, request.role):
            raise _forbidden()

        raw_token = secrets.token_urlsafe(32)
        one_time_link = _invite_link(public_app_url, raw_token)
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        try:
            record = repository.create_invite(
                actor.organization_id,
                target_store.store_id,
                actor.assignment_id,
                request.role.value,
                request.display_name,
                token_hash,
            )
        except OnboardingRepositoryError as exc:
            raise _management_repository_error(exc) from None
        return CreateInviteResponse(
            invite=_invite_response(record),
            one_time_link=one_time_link,
        )

    @router.post(
        "/api/v1/organization/invites/{invite_id}/revoke",
        response_model=InviteResponse,
    )
    def revoke_invite(
        invite_id: str,
        actor: ResolvedAssignment = Depends(resolve_actor),
        repository: Any = Depends(get_onboarding_repository),
    ) -> InviteResponse:
        store_scope = actor.store_id if actor.role is AssignmentRole.STORE_MANAGER else None
        if actor.role is AssignmentRole.STORE_MANAGER and store_scope is None:
            raise _forbidden()
        record = next(
            (
                item
                for item in repository.list_invites(actor.organization_id, store_scope)
                if item.get("id") == invite_id
            ),
            None,
        )
        if record is None:
            raise _not_found()
        try:
            invite_role = InviteRole(record["role"])
            target_store, _ = confirmed_store(
                actor,
                repository,
                str(record["store_id"]),
            )
        except (KeyError, TypeError, ValueError):
            raise _not_found() from None
        if not can_invite_member(actor, target_store, invite_role):
            raise _forbidden()
        try:
            revoked = repository.revoke_invite(
                actor.organization_id,
                target_store.store_id,
                actor.assignment_id,
                invite_id,
            )
        except OnboardingRepositoryError as exc:
            raise _management_repository_error(exc) from None
        if revoked is None:
            raise _not_found()
        return _invite_response(revoked)

    @router.post(
        "/api/v1/organization/members/{assignment_id}/deactivate",
        response_model=MemberResponse,
    )
    def deactivate_member(
        assignment_id: str,
        actor: ResolvedAssignment = Depends(resolve_actor),
        repository: Any = Depends(get_onboarding_repository),
    ) -> MemberResponse:
        store_scope = actor.store_id if actor.role is AssignmentRole.STORE_MANAGER else None
        if actor.role is AssignmentRole.STORE_MANAGER and store_scope is None:
            raise _forbidden()
        record = next(
            (
                item
                for item in repository.list_members(actor.organization_id, store_scope)
                if item.get("assignment_id") == assignment_id
            ),
            None,
        )
        if record is None:
            raise _not_found()
        try:
            target_store, _ = confirmed_store(
                actor,
                repository,
                str(record["store_id"]),
            )
            target = ResolvedAssignment(
                assignment_id=str(record["assignment_id"]),
                organization_id=target_store.organization_id,
                store_id=target_store.store_id,
                role=record["role"],
            )
        except (KeyError, TypeError, ValueError):
            raise _not_found() from None
        if not can_deactivate_member(actor, target):
            raise _forbidden()
        try:
            deactivated = repository.deactivate_member(
                actor.organization_id,
                target_store.store_id,
                actor.assignment_id,
                target.assignment_id,
            )
        except OnboardingRepositoryError as exc:
            raise _management_repository_error(exc) from None
        if deactivated is None:
            raise _not_found()
        return _member_response(deactivated)

    @router.post(
        "/api/v1/onboarding/invites/redeem",
        response_model=AuthenticatedResponse,
    )
    def redeem_invite(
        request: RedeemInviteRequest,
        repository: Any = Depends(get_onboarding_repository),
    ) -> JSONResponse:
        token_hash = hashlib.sha256(request.token.encode("utf-8")).hexdigest()
        raw_session_token = secrets.token_urlsafe(32)
        try:
            repository.redeem_invite(
                token_hash,
                raw_session_token,
                auth_settings.session_ttl_seconds,
            )
        except OnboardingRepositoryError:
            raise HTTPException(status_code=401, detail="Unauthorized") from None
        response = JSONResponse({"status": "authenticated"})
        response.set_cookie(
            key="hxy_session",
            value=raw_session_token,
            max_age=auth_settings.session_ttl_seconds,
            path="/api/v1",
            secure=auth_settings.secure_cookie,
            httponly=True,
            samesite="lax",
        )
        return response

    return router
