from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Iterator

try:
    import psycopg
    from psycopg.rows import dict_row
except Exception:  # pragma: no cover - deployment dependency may be installed later
    psycopg = None
    dict_row = None


class OperatingWriteConflict(RuntimeError):
    pass


def _dict_row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row is not None else None


class OperatingTransaction:
    def __init__(self, connection: Any) -> None:
        self.connection = connection

    def lock_proposal_context(
        self, organization_id: str, proposal_id: str
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT proposal.proposal_id::text,
                   proposal.organization_id::text,
                   proposal.source_envelope_id::text,
                   proposal.status,
                   proposal.target_id::text,
                   proposal.payload,
                   proposal.risk_level,
                   proposal.decision_policy_version,
                   proposal.decided_at,
                   proposal.decided_by_assignment_id::text,
                   envelope.store_id,
                   envelope.sender_assignment_id::text AS reporter_assignment_id,
                   envelope.received_at
            FROM hxy_ai_proposals AS proposal
            JOIN hxy_inbound_envelopes AS envelope
              ON envelope.organization_id = proposal.organization_id
             AND envelope.envelope_id = proposal.source_envelope_id
            WHERE proposal.organization_id = %s::uuid
              AND proposal.proposal_id = %s::uuid
              AND proposal.target_type = 'operating_event'
            FOR UPDATE OF proposal
            """,
            (organization_id, proposal_id),
        ).fetchone()
        return _dict_row(row)

    def load_current_governance_snapshot(
        self, organization_id: str, store_id: str, effective_at: datetime
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT relationship.relationship_id::text
                     AS store_operating_relationship_id,
                   relationship.relationship_version
                     AS store_operating_relationship_version,
                   governance.profile_id::text AS governance_profile_id,
                   governance.profile_version AS governance_profile_version,
                   governance.decision_rights
            FROM hxy_store_operating_relationships AS relationship
            JOIN hxy_governance_profiles AS governance
              ON governance.organization_id = relationship.organization_id
             AND governance.profile_id = relationship.governance_profile_id
            WHERE relationship.organization_id = %s::uuid
              AND relationship.store_id = %s
              AND relationship.status = 'active'
              AND relationship.effective_from <= %s
              AND (relationship.effective_to IS NULL OR relationship.effective_to > %s)
              AND governance.status = 'published'
              AND governance.effective_from <= %s
              AND (governance.effective_to IS NULL OR governance.effective_to > %s)
            ORDER BY relationship.relationship_version DESC
            LIMIT 1
            FOR SHARE OF relationship, governance
            """,
            (
                organization_id,
                store_id,
                effective_at,
                effective_at,
                effective_at,
                effective_at,
            ),
        ).fetchone()
        return _dict_row(row)

    def load_assignment(
        self, organization_id: str, assignment_id: str
    ) -> dict[str, Any] | None:
        row = self.connection.execute(
            """
            SELECT assignment_id::text,
                   organization_id::text,
                   store_id,
                   role,
                   status
            FROM hxy_role_assignments
            WHERE organization_id = %s::uuid
              AND assignment_id = %s::uuid
            FOR SHARE
            """,
            (organization_id, assignment_id),
        ).fetchone()
        return _dict_row(row)

    def insert_operating_event(self, values: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO hxy_operating_events (
              organization_id,
              store_id,
              event_type,
              title,
              description,
              location,
              impact,
              acceptance_criteria,
              source_envelope_id,
              source_proposal_id,
              reporter_assignment_id,
              owner_assignment_id,
              severity,
              status,
              occurred_at,
              detected_at,
              due_at,
              policy_version,
              store_operating_relationship_id,
              store_operating_relationship_version,
              governance_profile_id,
              governance_profile_version
            )
            VALUES (
              %s::uuid, %s, %s, %s, %s, %s, %s, %s,
              %s::uuid, %s::uuid, %s::uuid, %s::uuid,
              %s, %s, %s, %s, %s, %s,
              %s::uuid, %s, %s::uuid, %s
            )
            RETURNING operating_event_id::text,
                      organization_id::text,
                      store_id,
                      event_type,
                      title,
                      owner_assignment_id::text,
                      severity,
                      status,
                      policy_version,
                      store_operating_relationship_id::text,
                      store_operating_relationship_version,
                      governance_profile_id::text,
                      governance_profile_version,
                      occurred_at,
                      due_at,
                      closed_at,
                      created_at,
                      updated_at
            """,
            (
                values["organization_id"],
                values["store_id"],
                values["event_type"],
                values["title"],
                values.get("description") or "",
                values.get("location") or "",
                values.get("impact") or "",
                values.get("acceptance_criteria") or "",
                values["source_envelope_id"],
                values["source_proposal_id"],
                values["reporter_assignment_id"],
                values.get("owner_assignment_id"),
                values["severity"],
                values["status"],
                values["occurred_at"],
                values["detected_at"],
                values.get("due_at"),
                values["policy_version"],
                values["store_operating_relationship_id"],
                values["store_operating_relationship_version"],
                values["governance_profile_id"],
                values["governance_profile_version"],
            ),
        ).fetchone()
        assert row is not None
        return dict(row)

    def insert_workflow_instance(self, values: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO hxy_workflow_instances (
              organization_id,
              store_id,
              operating_event_id,
              workflow_type,
              workflow_version,
              status,
              current_state,
              started_at
            )
            VALUES (%s::uuid, %s, %s::uuid, %s, %s, %s, %s, %s)
            RETURNING workflow_instance_id::text,
                      organization_id::text,
                      store_id,
                      operating_event_id::text,
                      workflow_type,
                      workflow_version,
                      status,
                      current_state,
                      started_at,
                      completed_at,
                      created_at,
                      updated_at
            """,
            (
                values["organization_id"],
                values["store_id"],
                values["operating_event_id"],
                values["workflow_type"],
                values["workflow_version"],
                values["status"],
                values["current_state"],
                values.get("started_at"),
            ),
        ).fetchone()
        assert row is not None
        return dict(row)

    def insert_task(self, values: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO hxy_product_tasks (
              organization_id,
              store_id,
              creator_assignment_id,
              assignee_assignment_id,
              title,
              details,
              priority,
              visibility,
              status,
              due_at,
              operating_event_id,
              workflow_instance_id,
              task_type,
              external_responsible_name
            )
            VALUES (
              %s::uuid, %s, %s::uuid, %s::uuid, %s, %s, %s, %s,
              %s, %s, %s::uuid, %s::uuid, %s, %s
            )
            RETURNING task_id::text,
                      organization_id::text,
                      store_id,
                      creator_assignment_id::text,
                      assignee_assignment_id::text,
                      title,
                      details,
                      priority,
                      visibility,
                      status,
                      result,
                      due_at,
                      submitted_at,
                      accepted_at,
                      acceptance_assignment_id::text,
                      operating_event_id::text,
                      workflow_instance_id::text,
                      task_type,
                      external_responsible_name,
                      created_at,
                      updated_at
            """,
            (
                values["organization_id"],
                values["store_id"],
                values["creator_assignment_id"],
                values.get("assignee_assignment_id"),
                values["title"],
                values.get("details") or "",
                values["priority"],
                values["visibility"],
                values["status"],
                values.get("due_at"),
                values["operating_event_id"],
                values["workflow_instance_id"],
                values["task_type"],
                values.get("external_responsible_name"),
            ),
        ).fetchone()
        assert row is not None
        return dict(row)

    def link_proposal_to_event(
        self,
        *,
        organization_id: str,
        proposal_id: str,
        event_id: str,
        accepted_by_assignment_id: str | None,
        decision_policy_version: str | None,
    ) -> dict[str, Any]:
        row = self.connection.execute(
            """
            UPDATE hxy_ai_proposals
            SET target_id = %s::uuid,
                status = CASE WHEN status = 'proposed' THEN 'accepted' ELSE status END,
                decided_at = CASE WHEN status = 'proposed' THEN NOW() ELSE decided_at END,
                decided_by_assignment_id = CASE
                  WHEN status = 'proposed' THEN %s::uuid
                  ELSE decided_by_assignment_id
                END,
                decision_policy_version = CASE
                  WHEN status = 'proposed' THEN %s
                  ELSE decision_policy_version
                END
            WHERE organization_id = %s::uuid
              AND proposal_id = %s::uuid
              AND target_id IS NULL
              AND status IN ('proposed', 'auto_accepted', 'accepted')
            RETURNING proposal_id::text,
                      status,
                      target_id::text,
                      decided_at,
                      decided_by_assignment_id::text,
                      decision_policy_version
            """,
            (
                event_id,
                accepted_by_assignment_id,
                decision_policy_version,
                organization_id,
                proposal_id,
            ),
        ).fetchone()
        if row is None:
            raise OperatingWriteConflict("proposal was changed by another command")
        return dict(row)

    def append_transition(self, values: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO hxy_state_transitions (
              organization_id,
              store_id,
              aggregate_type,
              aggregate_id,
              from_state,
              to_state,
              command_type,
              actor_type,
              actor_assignment_id,
              actor_reference,
              reason,
              policy_version,
              occurred_at,
              correlation_id
            )
            VALUES (
              %s::uuid, %s, %s, %s::uuid, %s, %s, %s, %s,
              %s::uuid, %s, %s, %s, %s, %s::uuid
            )
            RETURNING transition_id::text,
                      aggregate_type,
                      aggregate_id::text,
                      from_state,
                      to_state,
                      command_type,
                      actor_type,
                      occurred_at,
                      correlation_id::text
            """,
            (
                values["organization_id"],
                values.get("store_id"),
                values["aggregate_type"],
                values["aggregate_id"],
                values.get("from_state"),
                values["to_state"],
                values["command_type"],
                values["actor_type"],
                values.get("actor_assignment_id"),
                values.get("actor_reference"),
                values.get("reason") or "",
                values.get("policy_version"),
                values["occurred_at"],
                values["correlation_id"],
            ),
        ).fetchone()
        assert row is not None
        return dict(row)

    def load_command_receipt(
        self, organization_id: str, correlation_id: str
    ) -> dict[str, Any] | None:
        lock_key = f"{organization_id}:{correlation_id}"
        self.connection.execute(
            "SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
            (lock_key,),
        )
        row = self.connection.execute(
            """
            SELECT command_receipt_id::text,
                   organization_id::text,
                   correlation_id::text,
                   actor_assignment_id::text,
                   command_type,
                   aggregate_type,
                   aggregate_id::text,
                   request_fingerprint,
                   receipt_json,
                   created_at
            FROM hxy_operating_command_receipts
            WHERE organization_id = %s::uuid
              AND correlation_id = %s::uuid
            """,
            (organization_id, correlation_id),
        ).fetchone()
        return _dict_row(row)

    def insert_command_receipt(self, values: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            """
            INSERT INTO hxy_operating_command_receipts (
              organization_id,
              correlation_id,
              actor_assignment_id,
              command_type,
              aggregate_type,
              aggregate_id,
              request_fingerprint,
              receipt_json
            )
            VALUES (
              %s::uuid, %s::uuid, %s::uuid, %s, %s, %s::uuid, %s, %s::jsonb
            )
            RETURNING command_receipt_id::text,
                      organization_id::text,
                      correlation_id::text,
                      actor_assignment_id::text,
                      command_type,
                      aggregate_type,
                      aggregate_id::text,
                      request_fingerprint,
                      receipt_json,
                      created_at
            """,
            (
                values["organization_id"],
                values["correlation_id"],
                values["actor_assignment_id"],
                values["command_type"],
                values["aggregate_type"],
                values["aggregate_id"],
                values["request_fingerprint"],
                json.dumps(values["receipt_json"], ensure_ascii=False),
            ),
        ).fetchone()
        assert row is not None
        return dict(row)

    def lock_task_aggregate(
        self, organization_id: str, task_id: str
    ) -> dict[str, Any] | None:
        locator = self.connection.execute(
            """
            SELECT operating_event_id::text
            FROM hxy_product_tasks
            WHERE organization_id = %s::uuid
              AND task_id = %s::uuid
            """,
            (organization_id, task_id),
        ).fetchone()
        if locator is None or locator.get("operating_event_id") is None:
            return None
        event_id = str(locator["operating_event_id"])
        event = self.connection.execute(
            """
            SELECT event.*,
                   event.operating_event_id::text,
                   event.organization_id::text,
                   event.source_envelope_id::text,
                   event.source_proposal_id::text,
                   event.reporter_assignment_id::text,
                   event.owner_assignment_id::text,
                   event.store_operating_relationship_id::text,
                   event.governance_profile_id::text
            FROM hxy_operating_events AS event
            WHERE event.organization_id = %s::uuid
              AND event.operating_event_id = %s::uuid
            FOR UPDATE OF event
            """,
            (organization_id, event_id),
        ).fetchone()
        if event is None:
            return None
        workflows = self.connection.execute(
            """
            SELECT workflow_instance_id::text,
                   organization_id::text,
                   store_id,
                   operating_event_id::text,
                   workflow_type,
                   workflow_version,
                   status,
                   current_state,
                   started_at,
                   completed_at,
                   created_at,
                   updated_at
            FROM hxy_workflow_instances
            WHERE organization_id = %s::uuid
              AND operating_event_id = %s::uuid
            ORDER BY workflow_instance_id
            FOR UPDATE
            """,
            (organization_id, event_id),
        ).fetchall()
        task = self.connection.execute(
            """
            SELECT task.*,
                   task.task_id::text,
                   task.organization_id::text,
                   task.creator_assignment_id::text,
                   task.assignee_assignment_id::text,
                   task.acceptance_assignment_id::text,
                   task.operating_event_id::text,
                   task.workflow_instance_id::text
            FROM hxy_product_tasks AS task
            WHERE task.organization_id = %s::uuid
              AND task.task_id = %s::uuid
              AND task.operating_event_id = %s::uuid
            FOR UPDATE OF task
            """,
            (organization_id, task_id, event_id),
        ).fetchone()
        if task is None:
            return None
        workflow_id = str(task.get("workflow_instance_id") or "")
        workflow = next(
            (
                row
                for row in workflows
                if str(row.get("workflow_instance_id") or "") == workflow_id
            ),
            None,
        )
        tasks = self.connection.execute(
            """
            SELECT *,
                   task_id::text,
                   organization_id::text,
                   assignee_assignment_id::text,
                   operating_event_id::text,
                   workflow_instance_id::text
            FROM hxy_product_tasks
            WHERE organization_id = %s::uuid
              AND operating_event_id = %s::uuid
            ORDER BY hxy_product_tasks.task_id
            FOR UPDATE
            """,
            (organization_id, event_id),
        ).fetchall()
        governance = self._load_snapshotted_governance(dict(event))
        return {
            "event": dict(event),
            "workflow": _dict_row(workflow),
            "workflows": [dict(row) for row in workflows],
            "task": dict(task),
            "tasks": [dict(row) for row in tasks],
            "governance": governance,
        }

    def lock_event_aggregate(
        self, organization_id: str, event_id: str
    ) -> dict[str, Any] | None:
        event = self.connection.execute(
            """
            SELECT event.*,
                   event.operating_event_id::text,
                   event.organization_id::text,
                   event.source_envelope_id::text,
                   event.source_proposal_id::text,
                   event.reporter_assignment_id::text,
                   event.owner_assignment_id::text,
                   event.store_operating_relationship_id::text,
                   event.governance_profile_id::text
            FROM hxy_operating_events AS event
            WHERE event.organization_id = %s::uuid
              AND event.operating_event_id = %s::uuid
            FOR UPDATE OF event
            """,
            (organization_id, event_id),
        ).fetchone()
        if event is None:
            return None
        workflows = self.connection.execute(
            """
            SELECT workflow_instance_id::text,
                   organization_id::text,
                   store_id,
                   operating_event_id::text,
                   workflow_type,
                   workflow_version,
                   status,
                   current_state,
                   started_at,
                   completed_at,
                   created_at,
                   updated_at
            FROM hxy_workflow_instances
            WHERE organization_id = %s::uuid
              AND operating_event_id = %s::uuid
            ORDER BY workflow_instance_id
            FOR UPDATE
            """,
            (organization_id, event_id),
        ).fetchall()
        tasks = self.connection.execute(
            """
            SELECT *,
                   task_id::text,
                   organization_id::text,
                   assignee_assignment_id::text,
                   operating_event_id::text,
                   workflow_instance_id::text
            FROM hxy_product_tasks
            WHERE organization_id = %s::uuid
              AND operating_event_id = %s::uuid
            ORDER BY hxy_product_tasks.task_id
            FOR UPDATE
            """,
            (organization_id, event_id),
        ).fetchall()
        governance = self._load_snapshotted_governance(dict(event))
        return {
            "event": dict(event),
            "workflow": _dict_row(workflows[0]) if len(workflows) == 1 else None,
            "workflows": [dict(row) for row in workflows],
            "tasks": [dict(row) for row in tasks],
            "governance": governance,
        }

    def _load_snapshotted_governance(self, event: dict[str, Any]) -> dict[str, Any]:
        row = self.connection.execute(
            """
            SELECT profile_id::text AS governance_profile_id,
                   profile_version AS governance_profile_version,
                   decision_rights,
                   approval_policy_refs,
                   audit_policy
            FROM hxy_governance_profiles
            WHERE organization_id = %s::uuid
              AND profile_id = %s::uuid
              AND profile_version = %s
              AND status IN ('published', 'superseded')
            FOR SHARE
            """,
            (
                str(event["organization_id"]),
                str(event["governance_profile_id"]),
                int(event["governance_profile_version"]),
            ),
        ).fetchone()
        if row is None:
            raise OperatingWriteConflict("snapshotted governance profile was not found")
        return dict(row)

    def evidence_ids_are_valid_for_task(
        self,
        *,
        organization_id: str,
        store_id: str,
        event_id: str,
        task_id: str,
        evidence_ids: list[str],
    ) -> bool:
        unique_ids = sorted(set(evidence_ids))
        if not unique_ids:
            return False
        row = self.connection.execute(
            """
            SELECT COUNT(DISTINCT evidence.evidence_id) AS valid_count
            FROM hxy_operating_evidence AS evidence
            JOIN hxy_product_materials AS material
              ON material.organization_id = evidence.organization_id
             AND material.material_id = evidence.source_asset_id
            WHERE evidence.organization_id = %s::uuid
              AND evidence.store_id = %s
              AND evidence.operating_event_id = %s::uuid
              AND evidence.task_id = %s::uuid
              AND evidence.evidence_id = ANY(%s::uuid[])
              AND (material.store_id IS NULL OR material.store_id = %s)
              AND material.status <> 'archived'
              AND material.scan_status = 'clean'
            """,
            (organization_id, store_id, event_id, task_id, unique_ids, store_id),
        ).fetchone()
        return row is not None and int(row["valid_count"]) == len(unique_ids)

    def task_has_valid_evidence(
        self, *, organization_id: str, store_id: str, event_id: str, task_id: str
    ) -> bool:
        row = self.connection.execute(
            """
            SELECT EXISTS (
              SELECT 1
              FROM hxy_operating_evidence AS evidence
              JOIN hxy_product_materials AS material
                ON material.organization_id = evidence.organization_id
               AND material.material_id = evidence.source_asset_id
              WHERE evidence.organization_id = %s::uuid
                AND evidence.store_id = %s
                AND evidence.operating_event_id = %s::uuid
                AND evidence.task_id = %s::uuid
                AND (material.store_id IS NULL OR material.store_id = %s)
                AND material.status <> 'archived'
                AND material.scan_status = 'clean'
            ) AS has_evidence
            """,
            (organization_id, store_id, event_id, task_id, store_id),
        ).fetchone()
        return bool(row and row["has_evidence"])

    def update_task(
        self,
        *,
        organization_id: str,
        task_id: str,
        locked_updated_at: datetime,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        return self._update_row(
            table="hxy_product_tasks",
            id_column="task_id",
            row_id=task_id,
            organization_id=organization_id,
            locked_updated_at=locked_updated_at,
            changes=changes,
            allowed_columns={
                "status",
                "assignee_assignment_id",
                "external_responsible_name",
                "visibility",
                "submitted_at",
                "accepted_at",
                "acceptance_assignment_id",
                "result",
            },
        )

    def update_event(
        self,
        *,
        organization_id: str,
        event_id: str,
        locked_updated_at: datetime,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        return self._update_row(
            table="hxy_operating_events",
            id_column="operating_event_id",
            row_id=event_id,
            organization_id=organization_id,
            locked_updated_at=locked_updated_at,
            changes=changes,
            allowed_columns={"status", "owner_assignment_id", "severity", "closed_at"},
        )

    def update_workflow(
        self,
        *,
        organization_id: str,
        workflow_id: str,
        locked_updated_at: datetime,
        changes: dict[str, Any],
    ) -> dict[str, Any]:
        return self._update_row(
            table="hxy_workflow_instances",
            id_column="workflow_instance_id",
            row_id=workflow_id,
            organization_id=organization_id,
            locked_updated_at=locked_updated_at,
            changes=changes,
            allowed_columns={"status", "current_state", "started_at", "completed_at"},
        )

    def _update_row(
        self,
        *,
        table: str,
        id_column: str,
        row_id: str,
        organization_id: str,
        locked_updated_at: datetime,
        changes: dict[str, Any],
        allowed_columns: set[str],
    ) -> dict[str, Any]:
        if not changes or not set(changes).issubset(allowed_columns):
            raise ValueError("unsupported operating workflow update")
        assignments = [f"{column} = %s" for column in changes]
        params = [changes[column] for column in changes]
        params.extend((organization_id, row_id, locked_updated_at))
        sql = f"""
            UPDATE {table}
            SET {', '.join(assignments)},
                updated_at = GREATEST(
                  clock_timestamp(),
                  updated_at + INTERVAL '1 microsecond'
                )
            WHERE organization_id = %s::uuid
              AND {id_column} = %s::uuid
              AND updated_at = %s
            RETURNING *,
                      {id_column}::text,
                      organization_id::text
        """
        row = self.connection.execute(sql, tuple(params)).fetchone()
        if row is None:
            raise OperatingWriteConflict(f"{table} was changed by another command")
        return dict(row)


class OperatingRepository:
    def __init__(self, database_url: str):
        if not database_url:
            raise ValueError("database_url is required")
        if psycopg is None:
            raise RuntimeError("psycopg is not installed")
        self.database_url = database_url

    def connect(self):
        return psycopg.connect(self.database_url, row_factory=dict_row)

    @staticmethod
    def _read_scope(
        role: str,
        store_id: str | None,
        assignment_id: str,
    ) -> tuple[str, tuple[Any, ...]] | None:
        if role in {"founder", "hq_operations"}:
            return "", ()
        if role == "store_manager" and store_id:
            return " AND event.store_id = %s", (store_id,)
        if role == "store_employee" and store_id and assignment_id:
            return (
                """
                AND event.store_id = %s
                AND (
                  event.reporter_assignment_id = %s::uuid
                  OR event.owner_assignment_id = %s::uuid
                  OR EXISTS (
                    SELECT 1
                    FROM hxy_product_tasks AS visible_task
                    WHERE visible_task.organization_id = event.organization_id
                      AND visible_task.store_id = event.store_id
                      AND visible_task.operating_event_id = event.operating_event_id
                      AND (
                        visible_task.assignee_assignment_id = %s::uuid
                        OR visible_task.visibility = 'store'
                      )
                  )
                )
                """,
                (store_id, assignment_id, assignment_id, assignment_id),
            )
        return None

    def list_events(
        self,
        *,
        organization_id: str,
        store_id: str | None,
        assignment_id: str,
        role: str,
        limit: int,
    ) -> list[dict[str, Any]]:
        scope = self._read_scope(role, store_id, assignment_id)
        if scope is None:
            return []
        scope_sql, scope_params = scope
        sql = (
            """
            SELECT event.operating_event_id::text,
                   event.store_id,
                   event.event_type,
                   event.title,
                   event.description,
                   event.location,
                   event.impact,
                   event.acceptance_criteria,
                   event.reporter_assignment_id::text,
                   event.owner_assignment_id::text,
                   event.severity,
                   event.status,
                   event.occurred_at,
                   event.due_at,
                   event.closed_at,
                   event.created_at,
                   event.updated_at
            FROM hxy_operating_events AS event
            WHERE event.organization_id = %s::uuid
            """
            + scope_sql
            + " ORDER BY event.updated_at DESC, event.operating_event_id DESC LIMIT %s"
        )
        with self.connect() as connection:
            rows = connection.execute(
                sql,
                (organization_id, *scope_params, max(1, min(int(limit), 100))),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_event(
        self,
        *,
        organization_id: str,
        event_id: str,
        store_id: str | None,
        assignment_id: str,
        role: str,
    ) -> dict[str, Any] | None:
        scope = self._read_scope(role, store_id, assignment_id)
        if scope is None:
            return None
        scope_sql, scope_params = scope
        task_scope_sql = ""
        task_scope_params: tuple[Any, ...] = ()
        evidence_scope_sql = ""
        evidence_scope_params: tuple[Any, ...] = ()
        if role == "store_employee":
            task_scope_sql = """
                AND (
                  task.assignee_assignment_id = %s::uuid
                  OR task.visibility = 'store'
                )
            """
            task_scope_params = (assignment_id,)
            evidence_scope_sql = """
                AND (
                  evidence.created_by_assignment_id = %s::uuid
                  OR (
                    evidence.visibility_scope @> '{"task_assignee": true}'::jsonb
                    AND EXISTS (
                      SELECT 1
                      FROM hxy_product_tasks AS evidence_task
                      WHERE evidence_task.organization_id = evidence.organization_id
                        AND evidence_task.store_id = evidence.store_id
                        AND evidence_task.task_id = evidence.task_id
                        AND evidence_task.assignee_assignment_id = %s::uuid
                    )
                  )
                  OR (
                    evidence.visibility_scope @> '{"store_employee": true}'::jsonb
                    AND EXISTS (
                      SELECT 1
                      FROM hxy_product_tasks AS evidence_task
                      WHERE evidence_task.organization_id = evidence.organization_id
                        AND evidence_task.store_id = evidence.store_id
                        AND evidence_task.task_id = evidence.task_id
                        AND evidence_task.visibility = 'store'
                    )
                  )
                )
            """
            evidence_scope_params = (assignment_id, assignment_id)
        with self.connect() as connection:
            event = connection.execute(
                """
                SELECT event.operating_event_id::text,
                       event.store_id,
                       event.event_type,
                       event.title,
                       event.description,
                       event.location,
                       event.impact,
                       event.acceptance_criteria,
                       event.reporter_assignment_id::text,
                       event.owner_assignment_id::text,
                       event.severity,
                       event.status,
                       event.occurred_at,
                       event.due_at,
                       event.closed_at,
                       event.created_at,
                       event.updated_at
                FROM hxy_operating_events AS event
                WHERE event.organization_id = %s::uuid
                  AND event.operating_event_id = %s::uuid
                """
                + scope_sql,
                (organization_id, event_id, *scope_params),
            ).fetchone()
            if event is None:
                return None
            workflows = connection.execute(
                """
                SELECT workflow_instance_id::text,
                       status,
                       current_state,
                       created_at,
                       updated_at
                FROM hxy_workflow_instances
                WHERE organization_id = %s::uuid
                  AND operating_event_id = %s::uuid
                ORDER BY created_at, workflow_instance_id
                """,
                (organization_id, event_id),
            ).fetchall()
            tasks = connection.execute(
                """
                SELECT task.task_id::text,
                       task.operating_event_id::text,
                       task.workflow_instance_id::text,
                       task.title,
                       task.details,
                       task.priority,
                       task.status,
                       task.assignee_assignment_id::text,
                       task.result,
                       task.due_at,
                       task.submitted_at,
                       task.accepted_at,
                       task.created_at,
                       task.updated_at
                FROM hxy_product_tasks AS task
                WHERE task.organization_id = %s::uuid
                  AND task.operating_event_id = %s::uuid
                """
                + task_scope_sql
                + " ORDER BY task.created_at, task.task_id",
                (organization_id, event_id, *task_scope_params),
            ).fetchall()
            evidence = connection.execute(
                """
                SELECT evidence.evidence_id::text,
                       evidence.evidence_type,
                       evidence.statement,
                       evidence.source_asset_id::text,
                       evidence.created_by_assignment_id::text,
                       evidence.created_at
                FROM hxy_operating_evidence AS evidence
                WHERE evidence.organization_id = %s::uuid
                  AND evidence.operating_event_id = %s::uuid
                """
                + evidence_scope_sql
                + " ORDER BY evidence.created_at, evidence.evidence_id",
                (organization_id, event_id, *evidence_scope_params),
            ).fetchall()
        return {
            "event": dict(event),
            "workflow": dict(workflows[0]) if len(workflows) == 1 else None,
            "tasks": [dict(row) for row in tasks],
            "evidence": [dict(row) for row in evidence],
        }

    @contextmanager
    def transaction(self) -> Iterator[OperatingTransaction]:
        with self.connect() as connection:
            yield OperatingTransaction(connection)
