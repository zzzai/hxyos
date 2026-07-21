from __future__ import annotations

import os
from uuid import uuid4

import pytest

psycopg = pytest.importorskip("psycopg")


DATABASE_URL = os.getenv("HXY_TEST_DATABASE_URL", "").strip()


@pytest.mark.skipif(not DATABASE_URL, reason="HXY_TEST_DATABASE_URL is not configured")
def test_authoritative_records_project_append_only_product_events() -> None:
    organization_id = str(uuid4())
    assignment_id = str(uuid4())
    account_id = str(uuid4())
    store_id = f"event-test-{uuid4().hex}"
    general_record_id = str(uuid4())
    closing_record_id = str(uuid4())
    training_id = str(uuid4())
    context_id = str(uuid4())
    feedback_id = str(uuid4())

    connection = psycopg.connect(DATABASE_URL)
    try:
        connection.execute(
            "INSERT INTO stores (store_id, name) VALUES (%s, %s)",
            (store_id, "Event test store"),
        )
        connection.execute(
            """
            INSERT INTO staff_accounts (id, username, display_name, password_hash, role, store_id)
            VALUES (%s::uuid, %s, %s, %s, 'technician', %s)
            """,
            (account_id, f"event-{account_id}", "Event tester", "not-a-real-secret", store_id),
        )
        connection.execute(
            "INSERT INTO hxy_organizations (organization_id, slug, name) VALUES (%s::uuid, %s, %s)",
            (organization_id, f"event-{organization_id}", "Event test organization"),
        )
        connection.execute(
            "INSERT INTO hxy_organization_stores (organization_id, store_id) VALUES (%s::uuid, %s)",
            (organization_id, store_id),
        )
        connection.execute(
            """
            INSERT INTO hxy_role_assignments (
              assignment_id, account_id, organization_id, store_id, role
            ) VALUES (%s::uuid, %s::uuid, %s::uuid, %s, 'store_employee')
            """,
            (assignment_id, account_id, organization_id, store_id),
        )

        for record_id, purpose in (
            (general_record_id, "general"),
            (closing_record_id, "closing_review"),
        ):
            connection.execute(
                """
                INSERT INTO hxy_inbound_envelopes (
                  envelope_id, organization_id, channel, channel_tenant_id,
                  sender_assignment_id, store_id, intent_hint, raw_payload,
                  raw_text, idempotency_key, request_fingerprint, visibility_scope
                ) VALUES (
                  %s::uuid, %s::uuid, 'pwa', %s, %s::uuid, %s,
                  'organization_record', jsonb_build_object('purpose', %s::text),
                  'test record', %s, %s, '{}'::jsonb
                )
                """,
                (
                    record_id,
                    organization_id,
                    organization_id,
                    assignment_id,
                    store_id,
                    purpose,
                    record_id,
                    uuid4().hex * 2,
                ),
            )

        connection.execute(
            """
            INSERT INTO hxy_product_training_sessions (
              training_session_id, organization_id, store_id, assignment_id,
              customer_question, employee_answer, score, level, needs_retrain
            ) VALUES (
              %s::uuid, %s::uuid, %s, %s::uuid,
              'question', 'answer', 80, 'pass', FALSE
            )
            """,
            (training_id, organization_id, store_id, assignment_id),
        )
        connection.execute(
            """
            INSERT INTO hxy_service_contexts (
              service_context_id, organization_id, store_id,
              created_by_assignment_id, client_context_id, occurred_at,
              service_label, request_fingerprint
            ) VALUES (
              %s::uuid, %s::uuid, %s, %s::uuid, %s::uuid, NOW(),
              'service', %s
            )
            """,
            (context_id, organization_id, store_id, assignment_id, str(uuid4()), uuid4().hex * 2),
        )
        connection.execute(
            """
            INSERT INTO hxy_service_feedback (
              service_feedback_id, organization_id, store_id, service_context_id,
              created_by_assignment_id, client_feedback_id, feedback_text,
              request_fingerprint, duration_ms
            ) VALUES (
              %s::uuid, %s::uuid, %s, %s::uuid, %s::uuid, %s::uuid,
              'feedback', %s, 42000
            )
            """,
            (
                feedback_id,
                organization_id,
                store_id,
                context_id,
                assignment_id,
                str(uuid4()),
                uuid4().hex * 2,
            ),
        )

        rows = connection.execute(
            """
            SELECT event_name, subject_id::text, duration_ms
            FROM hxy_product_events
            WHERE organization_id = %s::uuid
            ORDER BY event_name
            """,
            (organization_id,),
        ).fetchall()
        assert rows == [
            ("closing_review_completed", closing_record_id, None),
            ("intake_succeeded", general_record_id, None),
            ("learning_completed", training_id, None),
            ("service_feedback_completed", feedback_id, 42_000),
        ]

        event_id = connection.execute(
            """
            SELECT product_event_id::text
            FROM hxy_product_events
            WHERE organization_id = %s::uuid AND subject_id = %s::uuid
            """,
            (organization_id, general_record_id),
        ).fetchone()[0]
        with pytest.raises(psycopg.errors.RaiseException):
            with connection.transaction():
                connection.execute(
                    "UPDATE hxy_product_events SET useful = TRUE WHERE product_event_id = %s::uuid",
                    (event_id,),
                )
        with pytest.raises(psycopg.errors.RaiseException):
            with connection.transaction():
                connection.execute("TRUNCATE hxy_product_events")
    finally:
        connection.rollback()
        connection.close()
