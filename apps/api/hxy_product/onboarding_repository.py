from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

try:
    import psycopg
    from psycopg.errors import UniqueViolation
    from psycopg.rows import dict_row
except ImportError:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    UniqueViolation = Exception
    dict_row = None


SESSION_TTL_MIN_SECONDS = 60
SESSION_TTL_MAX_SECONDS = 2_592_000
PASSWORDLESS_PASSWORD_MARKER = "!hxy-gateway-only$onboarding-passwordless-v1"
ACCOUNT_ROLE_BY_INVITE_ROLE = {
    "store_manager": "store_manager",
    "store_employee": "frontdesk",
}
_SHA256_HEX = re.compile(r"[0-9a-f]{64}\Z")


class OnboardingRepositoryError(RuntimeError):
    pass


class OnboardingScopeError(OnboardingRepositoryError):
    pass


class OnboardingValidationError(OnboardingRepositoryError):
    pass


class OnboardingConflict(OnboardingRepositoryError):
    pass


class InviteRedemptionError(OnboardingRepositoryError):
    pass


def _store_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "name": str(row["name"]),
        "city": str(row["city"]),
        "address": str(row["address"]),
        "status": str(row["status"]),
    }


def _member_from_row(
    row: Mapping[str, Any],
    *,
    status: str | None = None,
) -> dict[str, Any]:
    return {
        "assignment_id": str(row["assignment_id"]),
        "store_id": str(row["store_id"]),
        "display_name": str(row["display_name"]),
        "role": str(row["role"]),
        "status": status or str(row["status"]),
    }


def _invite_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "id": str(row["id"]),
        "store_id": str(row["store_id"]),
        "role": str(row["role"]),
        "display_name": str(row["display_name"]),
        "status": str(row["status"]),
        "expires_at": row["expires_at"],
    }


def _payload_field(payload: Mapping[str, Any] | object, field: str) -> Any:
    if isinstance(payload, Mapping):
        return payload[field]
    return getattr(payload, field)


class OnboardingRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    def list_stores(self, organization_id: str) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute(
                """
                SELECT store.store_id AS id,
                       store.name,
                       store.city,
                       store.address,
                       store.status
                FROM hxy_organization_stores AS organization_store
                JOIN stores AS store
                  ON store.store_id = organization_store.store_id
                WHERE organization_store.organization_id = %s::uuid
                ORDER BY store.name, store.store_id
                """,
                (organization_id,),
            ).fetchall()
        return [_store_from_row(row) for row in rows]

    def create_store(
        self,
        organization_id: str,
        creator_assignment_id: str,
        payload: Mapping[str, Any] | object,
    ) -> dict[str, Any]:
        store_id = f"hxy-{uuid4().hex}"
        with self.connect() as connection:
            creator = connection.execute(
                """
                SELECT creator.assignment_id::text AS assignment_id
                FROM hxy_role_assignments AS creator
                JOIN staff_accounts AS creator_account
                  ON creator_account.id = creator.account_id
                JOIN hxy_organizations AS organization
                  ON organization.organization_id = creator.organization_id
                WHERE creator.assignment_id = %s::uuid
                  AND creator.organization_id = %s::uuid
                  AND creator.status = 'active'
                  AND creator.role = 'founder'
                  AND creator_account.status = 'active'
                  AND organization.status = 'active'
                LIMIT 1
                FOR UPDATE OF creator, creator_account, organization
                """,
                (creator_assignment_id, organization_id),
            ).fetchone()
            if creator is None:
                raise OnboardingScopeError("onboarding operation is not available")
            row = connection.execute(
                """
                INSERT INTO stores (store_id, name, city, address)
                VALUES (%s, %s, %s, %s)
                RETURNING store_id AS id, name, city, address, status
                """,
                (
                    store_id,
                    _payload_field(payload, "name"),
                    _payload_field(payload, "city"),
                    _payload_field(payload, "address"),
                ),
            ).fetchone()
            connection.execute(
                """
                INSERT INTO hxy_organization_stores (organization_id, store_id)
                VALUES (%s::uuid, %s)
                """,
                (organization_id, store_id),
            )
        return _store_from_row(row)

    def list_members(
        self,
        organization_id: str,
        store_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if store_id is None:
            statement = """
                SELECT assignment.assignment_id::text AS assignment_id,
                       assignment.store_id,
                       account.display_name,
                       assignment.role,
                       assignment.status
                FROM hxy_role_assignments AS assignment
                JOIN staff_accounts AS account ON account.id = assignment.account_id
                WHERE assignment.organization_id = %s::uuid
                  AND assignment.store_id IS NOT NULL
                ORDER BY account.display_name, assignment.assignment_id
            """
            params: tuple[object, ...] = (organization_id,)
        else:
            statement = """
                SELECT assignment.assignment_id::text AS assignment_id,
                       assignment.store_id,
                       account.display_name,
                       assignment.role,
                       assignment.status
                FROM hxy_role_assignments AS assignment
                JOIN staff_accounts AS account ON account.id = assignment.account_id
                WHERE assignment.organization_id = %s::uuid
                  AND assignment.store_id = %s
                ORDER BY account.display_name, assignment.assignment_id
            """
            params = (organization_id, store_id)
        with self.connect() as connection:
            rows = connection.execute(statement, params).fetchall()
        return [_member_from_row(row) for row in rows]

    def list_invites(
        self,
        organization_id: str,
        store_id: str | None = None,
    ) -> list[dict[str, Any]]:
        if store_id is None:
            statement = """
                SELECT invite.invite_id::text AS id,
                       invite.store_id,
                       invite.role,
                       invite.display_name,
                       invite.status,
                       invite.expires_at
                FROM hxy_member_invites AS invite
                WHERE invite.organization_id = %s::uuid
                ORDER BY invite.created_at DESC, invite.invite_id
            """
            params: tuple[object, ...] = (organization_id,)
        else:
            statement = """
                SELECT invite.invite_id::text AS id,
                       invite.store_id,
                       invite.role,
                       invite.display_name,
                       invite.status,
                       invite.expires_at
                FROM hxy_member_invites AS invite
                WHERE invite.organization_id = %s::uuid
                  AND invite.store_id = %s
                ORDER BY invite.created_at DESC, invite.invite_id
            """
            params = (organization_id, store_id)
        with self.connect() as connection:
            rows = connection.execute(statement, params).fetchall()
        return [_invite_from_row(row) for row in rows]

    def create_invite(
        self,
        organization_id: str,
        store_id: str,
        creator_assignment_id: str,
        role: str,
        display_name: str,
        token_hash: str,
    ) -> dict[str, Any]:
        normalized_role = str(getattr(role, "value", role))
        if normalized_role not in ACCOUNT_ROLE_BY_INVITE_ROLE or not _SHA256_HEX.fullmatch(
            token_hash
        ):
            raise OnboardingValidationError("onboarding input is invalid")
        try:
            with self.connect() as connection:
                row = connection.execute(
                    """
                    INSERT INTO hxy_member_invites (
                      organization_id,
                      store_id,
                      role,
                      display_name,
                      token_hash,
                      created_by_assignment_id,
                      expires_at
                    )
                    SELECT creator.organization_id,
                           organization_store.store_id,
                           %s,
                           %s,
                           %s,
                           creator.assignment_id,
                           NOW() + INTERVAL '24 hours'
                    FROM hxy_role_assignments AS creator
                    JOIN staff_accounts AS creator_account
                      ON creator_account.id = creator.account_id
                    JOIN hxy_organizations AS organization
                      ON organization.organization_id = creator.organization_id
                    JOIN hxy_organization_stores AS organization_store
                      ON organization_store.organization_id = creator.organization_id
                     AND organization_store.store_id = %s
                    JOIN stores AS store
                      ON store.store_id = organization_store.store_id
                    WHERE creator.assignment_id = %s::uuid
                      AND creator.organization_id = %s::uuid
                      AND creator.status = 'active'
                      AND creator_account.status = 'active'
                      AND organization.status = 'active'
                      AND store.status = 'active'
                      AND (
                        (creator.role = 'founder' AND %s = 'store_manager')
                        OR (
                          creator.role = 'store_manager'
                          AND creator.store_id = organization_store.store_id
                          AND %s = 'store_employee'
                        )
                      )
                    FOR UPDATE OF creator, creator_account, organization,
                                  organization_store, store
                    RETURNING invite_id::text AS id,
                              store_id,
                              role,
                              display_name,
                              status,
                              expires_at
                    """,
                    (
                        normalized_role,
                        display_name,
                        token_hash,
                        store_id,
                        creator_assignment_id,
                        organization_id,
                        normalized_role,
                        normalized_role,
                    ),
                ).fetchone()
                if row is None:
                    raise OnboardingScopeError("onboarding operation is not available")
                connection.execute(
                    """
                    INSERT INTO hxy_member_invite_events (
                      organization_id,
                      store_id,
                      invite_id,
                      actor_assignment_id,
                      event_type
                    )
                    VALUES (%s::uuid, %s, %s::uuid, %s::uuid, 'created')
                    """,
                    (
                        organization_id,
                        store_id,
                        row["id"],
                        creator_assignment_id,
                    ),
                )
        except UniqueViolation:
            raise OnboardingConflict("onboarding operation conflicts") from None
        return _invite_from_row(row)

    def revoke_invite(
        self,
        organization_id: str,
        store_id: str,
        actor_assignment_id: str,
        invite_id: str,
    ) -> dict[str, Any] | None:
        scope = (organization_id, store_id, invite_id)
        with self.connect() as connection:
            current = connection.execute(
                """
                SELECT invite.invite_id::text AS id
                FROM hxy_member_invites AS invite
                JOIN hxy_role_assignments AS actor
                  ON actor.assignment_id = %s::uuid
                 AND actor.organization_id = invite.organization_id
                JOIN staff_accounts AS actor_account
                  ON actor_account.id = actor.account_id
                JOIN hxy_organizations AS organization
                  ON organization.organization_id = invite.organization_id
                JOIN hxy_organization_stores AS organization_store
                  ON organization_store.organization_id = invite.organization_id
                 AND organization_store.store_id = invite.store_id
                JOIN stores AS store
                  ON store.store_id = organization_store.store_id
                WHERE invite.organization_id = %s::uuid
                  AND invite.store_id = %s
                  AND invite.invite_id = %s::uuid
                  AND invite.status = 'pending'
                  AND actor.status = 'active'
                  AND actor_account.status = 'active'
                  AND organization.status = 'active'
                  AND store.status = 'active'
                  AND (
                    (actor.role = 'founder' AND invite.role = 'store_manager')
                    OR (
                      actor.role = 'store_manager'
                      AND actor.store_id = invite.store_id
                      AND invite.role = 'store_employee'
                    )
                  )
                FOR UPDATE OF invite, actor, actor_account, organization,
                              organization_store, store
                """,
                (actor_assignment_id, *scope),
            ).fetchone()
            if current is None:
                return None
            row = connection.execute(
                """
                UPDATE hxy_member_invites
                SET status = 'revoked',
                    revoked_at = NOW(),
                    updated_at = NOW()
                WHERE organization_id = %s::uuid
                  AND store_id = %s
                  AND invite_id = %s::uuid
                  AND status = 'pending'
                RETURNING invite_id::text AS id,
                          store_id,
                          role,
                          display_name,
                          status,
                          expires_at
                """,
                scope,
            ).fetchone()
            connection.execute(
                """
                INSERT INTO hxy_member_invite_events (
                  organization_id,
                  store_id,
                  invite_id,
                  actor_assignment_id,
                  event_type
                )
                VALUES (%s::uuid, %s, %s::uuid, %s::uuid, 'revoked')
                """,
                (*scope, actor_assignment_id),
            )
        return _invite_from_row(row)

    def redeem_invite(
        self,
        token_hash: str,
        raw_session_token: str,
        session_ttl_seconds: int,
    ) -> dict[str, Any]:
        if (
            not _SHA256_HEX.fullmatch(token_hash)
            or not SESSION_TTL_MIN_SECONDS
            <= session_ttl_seconds
            <= SESSION_TTL_MAX_SECONDS
        ):
            raise OnboardingValidationError("onboarding input is invalid")
        session_hash = hashlib.sha256(raw_session_token.encode("utf-8")).hexdigest()
        account_id = str(uuid4())
        assignment_id = str(uuid4())
        username = f"hxy-onboard-{account_id.replace('-', '')}"
        try:
            with self.connect() as connection:
                invite = connection.execute(
                    """
                    SELECT invite.invite_id::text AS id,
                           invite.organization_id::text AS organization_id,
                           invite.store_id,
                           invite.role,
                           invite.display_name
                    FROM hxy_member_invites AS invite
                    JOIN hxy_role_assignments AS creator
                      ON creator.organization_id = invite.organization_id
                     AND creator.assignment_id = invite.created_by_assignment_id
                    JOIN staff_accounts AS creator_account
                      ON creator_account.id = creator.account_id
                    JOIN hxy_organizations AS organization
                      ON organization.organization_id = invite.organization_id
                    JOIN hxy_organization_stores AS organization_store
                      ON organization_store.organization_id = invite.organization_id
                     AND organization_store.store_id = invite.store_id
                    JOIN stores AS store ON store.store_id = organization_store.store_id
                    WHERE invite.token_hash = %s
                      AND invite.status = 'pending'
                      AND invite.expires_at > NOW()
                      AND creator.status = 'active'
                      AND creator_account.status = 'active'
                      AND organization.status = 'active'
                      AND store.status = 'active'
                      AND (
                        (
                          creator.role = 'founder'
                          AND invite.role = 'store_manager'
                        )
                        OR (
                          creator.role = 'store_manager'
                          AND creator.store_id = invite.store_id
                          AND invite.role = 'store_employee'
                        )
                      )
                    FOR UPDATE OF invite, creator, creator_account, organization,
                                  organization_store, store
                    """,
                    (token_hash,),
                ).fetchone()
                if invite is None:
                    raise InviteRedemptionError("invitation is not available")
                role = str(invite["role"])
                account_role = ACCOUNT_ROLE_BY_INVITE_ROLE.get(role)
                if account_role is None:
                    raise InviteRedemptionError("invitation is not available")
                connection.execute(
                    """
                    INSERT INTO staff_accounts (
                      id,
                      username,
                      display_name,
                      password_hash,
                      role,
                      store_id,
                      status
                    )
                    VALUES (%s::uuid, %s, %s, %s, %s, %s, 'active')
                    """,
                    (
                        account_id,
                        username,
                        invite["display_name"],
                        PASSWORDLESS_PASSWORD_MARKER,
                        account_role,
                        invite["store_id"],
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO hxy_role_assignments (
                      assignment_id,
                      account_id,
                      organization_id,
                      store_id,
                      role,
                      status
                    )
                    VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, 'active')
                    """,
                    (
                        assignment_id,
                        account_id,
                        invite["organization_id"],
                        invite["store_id"],
                        role,
                    ),
                )
                connection.execute(
                    """
                    UPDATE hxy_member_invites
                    SET status = 'redeemed',
                        redeemed_account_id = %s::uuid,
                        redeemed_assignment_id = %s::uuid,
                        redeemed_at = NOW(),
                        updated_at = NOW()
                    WHERE organization_id = %s::uuid
                      AND store_id = %s
                      AND invite_id = %s::uuid
                      AND status = 'pending'
                    """,
                    (
                        account_id,
                        assignment_id,
                        invite["organization_id"],
                        invite["store_id"],
                        invite["id"],
                    ),
                )
                connection.execute(
                    """
                    INSERT INTO hxy_member_invite_events (
                      organization_id,
                      store_id,
                      invite_id,
                      actor_assignment_id,
                      subject_assignment_id,
                      event_type
                    )
                    VALUES (
                      %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid, 'redeemed'
                    )
                    """,
                    (
                        invite["organization_id"],
                        invite["store_id"],
                        invite["id"],
                        assignment_id,
                        assignment_id,
                    ),
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
                        session_hash,
                        account_id,
                        assignment_id,
                        session_ttl_seconds,
                    ),
                )
        except InviteRedemptionError:
            raise
        except UniqueViolation:
            raise InviteRedemptionError("invitation is not available") from None
        return {
            "assignment_id": assignment_id,
            "store_id": str(invite["store_id"]),
            "display_name": str(invite["display_name"]),
            "role": role,
            "status": "active",
        }

    def deactivate_member(
        self,
        organization_id: str,
        store_id: str,
        actor_assignment_id: str,
        target_assignment_id: str,
    ) -> dict[str, Any] | None:
        scope = (organization_id, store_id, target_assignment_id)
        with self.connect() as connection:
            target = connection.execute(
                """
                SELECT assignment.assignment_id::text AS assignment_id,
                       assignment.store_id,
                       account.display_name,
                       assignment.role,
                       assignment.status
                FROM hxy_role_assignments AS assignment
                JOIN staff_accounts AS account ON account.id = assignment.account_id
                JOIN hxy_role_assignments AS actor
                  ON actor.assignment_id = %s::uuid
                 AND actor.organization_id = assignment.organization_id
                JOIN staff_accounts AS actor_account
                  ON actor_account.id = actor.account_id
                JOIN hxy_organizations AS organization
                  ON organization.organization_id = assignment.organization_id
                JOIN hxy_organization_stores AS organization_store
                  ON organization_store.organization_id = assignment.organization_id
                 AND organization_store.store_id = assignment.store_id
                JOIN stores AS store
                  ON store.store_id = organization_store.store_id
                WHERE assignment.organization_id = %s::uuid
                  AND assignment.store_id = %s
                  AND assignment.assignment_id = %s::uuid
                  AND assignment.status = 'active'
                  AND actor.status = 'active'
                  AND actor_account.status = 'active'
                  AND organization.status = 'active'
                  AND store.status = 'active'
                  AND actor.assignment_id <> assignment.assignment_id
                  AND (
                    (actor.role = 'founder' AND assignment.role = 'store_manager')
                    OR (
                      actor.role = 'store_manager'
                      AND actor.store_id = assignment.store_id
                      AND assignment.role = 'store_employee'
                    )
                  )
                FOR UPDATE OF assignment, actor, actor_account, organization,
                              organization_store, store
                """,
                (actor_assignment_id, *scope),
            ).fetchone()
            if target is None:
                return None
            connection.execute(
                """
                UPDATE hxy_role_assignments
                SET status = 'inactive',
                    updated_at = NOW()
                WHERE organization_id = %s::uuid
                  AND store_id = %s
                  AND assignment_id = %s::uuid
                  AND status = 'active'
                """,
                scope,
            )
            connection.execute(
                "DELETE FROM staff_sessions WHERE assignment_id = %s::uuid",
                (target_assignment_id,),
            )
            connection.execute(
                """
                INSERT INTO hxy_member_invite_events (
                  organization_id,
                  store_id,
                  actor_assignment_id,
                  subject_assignment_id,
                  event_type
                )
                VALUES (%s::uuid, %s, %s::uuid, %s::uuid, 'member_deactivated')
                """,
                (
                    organization_id,
                    store_id,
                    actor_assignment_id,
                    target_assignment_id,
                ),
            )
        return _member_from_row(target, status="inactive")
