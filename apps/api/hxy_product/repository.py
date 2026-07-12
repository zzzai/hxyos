from __future__ import annotations

import hashlib
from dataclasses import dataclass

try:
    import psycopg
    from psycopg.errors import UniqueViolation
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    UniqueViolation = Exception
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
                SELECT account.id::text AS account_id,
                       account.display_name,
                       assignment.assignment_id::text AS assignment_id
                FROM staff_sessions AS session
                JOIN staff_accounts AS account ON account.id = session.account_id
                JOIN hxy_role_assignments AS assignment
                  ON assignment.assignment_id = session.assignment_id
                 AND assignment.account_id = session.account_id
                JOIN hxy_organizations AS organization
                  ON organization.organization_id = assignment.organization_id
                WHERE session.token_hash = %s
                  AND session.expires_at > NOW()
                  AND account.status = 'active'
                  AND assignment.status = 'active'
                  AND organization.status = 'active'
                LIMIT 1
                """,
                (token_hash,),
            ).fetchone()
        if row is None:
            return None
        return Principal(
            account_id=str(row["account_id"]),
            display_name=str(row["display_name"]),
            assignment_id=str(row["assignment_id"]),
        )

    def find_active_principal(self, account_id: str) -> Principal | None:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT account.id::text AS account_id,
                       account.display_name,
                       assignment.assignment_id::text AS assignment_id
                FROM staff_accounts AS account
                JOIN LATERAL (
                  SELECT role_assignment.assignment_id
                  FROM hxy_role_assignments AS role_assignment
                  JOIN hxy_organizations AS organization
                    ON organization.organization_id = role_assignment.organization_id
                  WHERE role_assignment.account_id = account.id
                    AND role_assignment.status = 'active'
                    AND organization.status = 'active'
                  ORDER BY role_assignment.created_at, role_assignment.assignment_id
                  LIMIT 1
                ) AS assignment ON TRUE
                WHERE account.id = %s::uuid
                  AND account.status = 'active'
                LIMIT 1
                """,
                (account_id,),
            ).fetchone()
        if row is None:
            return None
        return Principal(
            account_id=str(row["account_id"]),
            display_name=str(row["display_name"]),
            assignment_id=str(row["assignment_id"]),
        )

    def exchange_gateway_assertion(
        self,
        account_id: str,
        assertion_id: str,
        assertion_expires_at: int,
        raw_token: str,
        ttl_seconds: int,
    ) -> Principal | None:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        try:
            with self.connect() as connection:
                row = connection.execute(
                    """
                    SELECT account.id::text AS account_id,
                           account.display_name,
                           assignment.assignment_id::text AS assignment_id
                    FROM staff_accounts AS account
                    JOIN LATERAL (
                      SELECT role_assignment.assignment_id
                      FROM hxy_role_assignments AS role_assignment
                      JOIN hxy_organizations AS organization
                        ON organization.organization_id = role_assignment.organization_id
                      WHERE role_assignment.account_id = account.id
                        AND role_assignment.status = 'active'
                        AND organization.status = 'active'
                      ORDER BY role_assignment.created_at, role_assignment.assignment_id
                      LIMIT 1
                    ) AS assignment ON TRUE
                    WHERE account.id = %s::uuid
                      AND account.status = 'active'
                    LIMIT 1
                    """,
                    (account_id,),
                ).fetchone()
                if row is None:
                    return None
                connection.execute(
                    """
                    INSERT INTO hxy_consumed_gateway_assertions (assertion_id, expires_at)
                    VALUES (%s::uuid, to_timestamp(%s))
                    """,
                    (assertion_id, assertion_expires_at),
                )
                connection.execute(
                    """
                    INSERT INTO staff_sessions (
                      token_hash,
                      account_id,
                      assignment_id,
                      expires_at
                    )
                    VALUES (
                      %s,
                      %s::uuid,
                      %s::uuid,
                      NOW() + (%s * INTERVAL '1 second')
                    )
                    """,
                    (token_hash, account_id, row["assignment_id"], ttl_seconds),
                )
        except UniqueViolation:
            return None
        return Principal(
            account_id=str(row["account_id"]),
            display_name=str(row["display_name"]),
            assignment_id=str(row["assignment_id"]),
        )

    def exchange_session_grant(
        self,
        session_grant: str,
        raw_token: str,
        ttl_seconds: int,
    ) -> Principal | None:
        grant_hash = hashlib.sha256(session_grant.encode("utf-8")).hexdigest()
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        try:
            with self.connect() as connection:
                row = connection.execute(
                    """
                    SELECT account.id::text AS account_id,
                           account.display_name,
                           assignment.assignment_id::text AS assignment_id
                    FROM staff_sessions AS session_grant
                    JOIN staff_accounts AS account ON account.id = session_grant.account_id
                    JOIN hxy_role_assignments AS assignment
                      ON assignment.assignment_id = session_grant.assignment_id
                     AND assignment.account_id = session_grant.account_id
                    JOIN hxy_organizations AS organization
                      ON organization.organization_id = assignment.organization_id
                    WHERE session_grant.token_hash = %s
                      AND session_grant.expires_at > NOW()
                      AND account.status = 'active'
                      AND assignment.status = 'active'
                      AND organization.status = 'active'
                    FOR UPDATE OF session_grant
                    """,
                    (grant_hash,),
                ).fetchone()
                if row is None:
                    return None
                connection.execute(
                    "DELETE FROM staff_sessions WHERE token_hash = %s",
                    (grant_hash,),
                )
                connection.execute(
                    """
                    INSERT INTO staff_sessions (
                      token_hash,
                      account_id,
                      assignment_id,
                      expires_at
                    )
                    VALUES (
                      %s,
                      %s::uuid,
                      %s::uuid,
                      NOW() + (%s * INTERVAL '1 second')
                    )
                    """,
                    (
                        token_hash,
                        row["account_id"],
                        row["assignment_id"],
                        ttl_seconds,
                    ),
                )
        except UniqueViolation:
            return None
        return Principal(
            account_id=str(row["account_id"]),
            display_name=str(row["display_name"]),
            assignment_id=str(row["assignment_id"]),
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

    def get_assignment(self, assignment_id: str) -> AssignmentRecord | None:
        with self.connect() as connection:
            row = connection.execute(
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
                WHERE ra.assignment_id = %s::uuid
                  AND ra.status = 'active'
                  AND organization.status = 'active'
                LIMIT 1
                """,
                (assignment_id,),
            ).fetchone()
        if row is None:
            return None
        return AssignmentRecord(
            assignment_id=str(row["assignment_id"]),
            organization_id=str(row["organization_id"]),
            organization_name=str(row["organization_name"]),
            store_id=str(row["store_id"]) if row["store_id"] is not None else None,
            store_name=str(row["store_name"]) if row["store_name"] is not None else None,
            role=str(row["role"]),
        )

    def organization_has_store(self, organization_id: str, store_id: str) -> bool:
        with self.connect() as connection:
            row = connection.execute(
                """
                SELECT 1
                FROM hxy_organization_stores
                WHERE organization_id = %s::uuid
                  AND store_id = %s
                LIMIT 1
                """,
                (organization_id, store_id),
            ).fetchone()
        return row is not None
