from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Cookie, Depends, Header, HTTPException


@dataclass(frozen=True)
class Principal:
    account_id: str
    display_name: str


@dataclass(frozen=True)
class ProductAuthSettings:
    gateway_secret: str = ""
    assertion_max_age_seconds: int = 60
    session_ttl_seconds: int = 3600
    secure_cookie: bool = True

    def __post_init__(self) -> None:
        if not 1 <= self.assertion_max_age_seconds <= 300:
            raise ValueError("assertion_max_age_seconds must be between 1 and 300")
        if not 60 <= self.session_ttl_seconds <= 86400:
            raise ValueError("session_ttl_seconds must be between 60 and 86400")

    @classmethod
    def from_environment(cls) -> ProductAuthSettings:
        secure_value = os.environ.get("HXY_AUTH_SECURE_COOKIE", "true").strip().lower()
        return cls(
            gateway_secret=os.environ.get("HXY_AUTH_PROXY_SECRET", ""),
            secure_cookie=secure_value not in {"0", "false", "no", "off"},
        )


def require_session_token(
    authorization: str | None = Header(default=None),
    hxy_session: str | None = Cookie(default=None, alias="hxy_session"),
) -> str:
    if authorization is not None:
        parts = authorization.split(" ")
        if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return parts[1]
    if hxy_session:
        return hxy_session
    raise HTTPException(status_code=401, detail="Unauthorized")


def build_principal_resolver(
    repository_dependency: Callable[[], Any],
) -> Callable[..., Principal]:
    def resolve_principal(
        raw_token: str = Depends(require_session_token),
        repository: Any = Depends(repository_dependency),
    ) -> Principal:
        principal = repository.resolve_session(raw_token)
        if principal is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return principal

    return resolve_principal
