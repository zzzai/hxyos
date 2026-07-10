from __future__ import annotations

import hashlib
from dataclasses import dataclass

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None

from .auth import Principal


@dataclass(frozen=True)
class AssignmentRecord:
    assignment_id: str
    organization_id: str
    organization_name: str
    store_id: str | None
    store_name: str | None
    role: str


class IdentityRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def resolve_session(self, raw_token: str) -> Principal | None:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT account.id::text AS account_id, account.display_name
                FROM staff_sessions AS session
                JOIN staff_accounts AS account ON account.id = session.account_id
                WHERE session.token_hash = %s
                  AND session.expires_at > NOW()
                  AND account.status = 'active'
                LIMIT 1
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return Principal(
            account_id=str(row["account_id"]),
            display_name=str(row["display_name"]),
        )

    def find_active_principal(self, account_id: str) -> Principal | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT id::text AS account_id, display_name
                FROM staff_accounts
                WHERE id = %s::uuid
                  AND status = 'active'
                LIMIT 1
                """,
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        return Principal(
            account_id=str(row["account_id"]),
            display_name=str(row["display_name"]),
        )

    def create_session(
        self,
        account_id: str,
        raw_token: str,
        ttl_seconds: int,
    ) -> None:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO staff_sessions (token_hash, account_id, expires_at)
                VALUES (%s, %s::uuid, NOW() + (%s * INTERVAL '1 second'))
                """,
                (token_hash, account_id, ttl_seconds),
            )

    def delete_session(self, raw_token: str) -> None:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        with self.connect() as connection:
            connection.execute(
                "DELETE FROM staff_sessions WHERE token_hash = %s",
                (token_hash,),
            )

    def list_assignments(self, account_id: str) -> list[AssignmentRecord]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT ra.assignment_id::text AS assignment_id,
                       ra.organization_id::text AS organization_id,
                       organization.name AS organization_name,
                       ra.store_id,
                       store.name AS store_name,
                       ra.role
                FROM hxy_role_assignments AS ra
                JOIN hxy_organizations AS organization
                  ON organization.organization_id = ra.organization_id
                LEFT JOIN stores AS store ON store.store_id = ra.store_id
                WHERE ra.account_id = %s::uuid
                  AND ra.status = 'active'
                  AND organization.status = 'active'
                ORDER BY ra.created_at, ra.assignment_id
                """,
                (account_id,),
            ).fetchall()
        return [
            AssignmentRecord(
                assignment_id=str(row["assignment_id"]),
                organization_id=str(row["organization_id"]),
                organization_name=str(row["organization_name"]),
                store_id=str(row["store_id"]) if row["store_id"] is not None else None,
                store_name=str(row["store_name"]) if row["store_name"] is not None else None,
                role=str(row["role"]),
            )
            for row in rows
        ]
