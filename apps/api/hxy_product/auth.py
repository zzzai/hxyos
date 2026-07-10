from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Cookie, Depends, Header, HTTPException


@dataclass(frozen=True)
class Principal:
    account_id: str
    display_name: str


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
