from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fastapi import Depends, Header, HTTPException


@dataclass(frozen=True)
class Principal:
    account_id: str
    display_name: str


def require_bearer_token(
    authorization: str | None = Header(default=None),
) -> str:
    parts = authorization.split(" ") if authorization else []
    if len(parts) != 2 or parts[0].lower() != "bearer" or not parts[1]:
        raise HTTPException(status_code=401, detail="Unauthorized")
    return parts[1]


def build_principal_resolver(
    repository_dependency: Callable[[], Any],
) -> Callable[..., Principal]:
    def resolve_principal(
        raw_token: str = Depends(require_bearer_token),
        repository: Any = Depends(repository_dependency),
    ) -> Principal:
        principal = repository.resolve_session(raw_token)
        if principal is None:
            raise HTTPException(status_code=401, detail="Unauthorized")
        return principal

    return resolve_principal
