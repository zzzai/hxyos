from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest

from apps.api.hxy_product.conversation_repository import ConversationRepository
from apps.api.hxy_product.material_repository import MaterialRepository
from apps.api.hxy_release.activation_release import run_postflight


DATABASE_URL = os.getenv("HXY_TEST_DATABASE_URL", "").strip()


@pytest.mark.skipif(not DATABASE_URL, reason="HXY_TEST_DATABASE_URL is not configured")
def test_postgres_source_authority_rejects_unauthorized_or_cross_org_events() -> None:
    organization_id = str(uuid4())
    foreign_organization_id = str(uuid4())
    owner_account_id = str(uuid4())
    unauthorized_account_id = str(uuid4())
    foreign_account_id = str(uuid4())
    owner_assignment_id = str(uuid4())
    unauthorized_assignment_id = str(uuid4())
    foreign_assignment_id = str(uuid4())
    material_id = str(uuid4())

    with psycopg.connect(DATABASE_URL) as connection:
        authority_events_table = connection.execute(
            "SELECT to_regclass('hxy_material_authority_events')"
        ).fetchone()[0]
        assert authority_events_table is not None, "source authority migration is not applied"
        connection.execute(
            "INSERT INTO hxy_organizations (organization_id, slug, name) VALUES (%s, %s, %s)",
            (organization_id, f"authority-{uuid4().hex}", "权威边界测试组织"),
        )
        connection.execute(
            "INSERT INTO hxy_organizations (organization_id, slug, name) VALUES (%s, %s, %s)",
            (foreign_organization_id, f"authority-foreign-{uuid4().hex}", "外部测试组织"),
        )
        for account_id, username in (
            (owner_account_id, f"authority-owner-{uuid4().hex}"),
            (unauthorized_account_id, f"authority-admin-{uuid4().hex}"),
            (foreign_account_id, f"authority-foreign-{uuid4().hex}"),
        ):
            connection.execute(
                """
                INSERT INTO staff_accounts (id, username, password_hash, role)
                VALUES (%s, %s, 'not-a-login-credential', 'hq_admin')
                """,
                (account_id, username),
            )
        connection.execute(
            """
            INSERT INTO hxy_role_assignments (
              assignment_id, account_id, organization_id, role
            ) VALUES
              (%s, %s, %s, 'founder'),
              (%s, %s, %s, 'system_admin'),
              (%s, %s, %s, 'founder')
            """,
            (
                owner_assignment_id,
                owner_account_id,
                organization_id,
                unauthorized_assignment_id,
                unauthorized_account_id,
                organization_id,
                foreign_assignment_id,
                foreign_account_id,
                foreign_organization_id,
            ),
        )
        connection.execute(
            """
            INSERT INTO hxy_product_materials (
              material_id, assignment_id, client_upload_id, original_file_name,
              extension, media_type, size_bytes, sha256, storage_key, status,
              source_origin, source_authority
            ) VALUES (
              %s, %s, %s, '权威边界.md', '.md', 'text/markdown', 64,
              %s, %s, 'understood', 'internal', 'internal_material'
            )
            """,
            (material_id, owner_assignment_id, str(uuid4()), "a" * 64, f"authority/{material_id}.md"),
        )

        def insert_change_event(actor_assignment_id: str) -> None:
            connection.execute(
                """
                INSERT INTO hxy_material_authority_events (
                  material_id, owner_assignment_id, actor_assignment_id,
                  previous_origin, new_origin, previous_authority, new_authority,
                  version_no, reason
                ) VALUES (
                  %s, %s, %s, 'internal', 'internal',
                  'internal_material', 'official_internal', 2, '测试权威变更授权边界'
                )
                """,
                (material_id, owner_assignment_id, actor_assignment_id),
            )

        with pytest.raises(psycopg.Error), connection.transaction():
            connection.execute(
                """
                UPDATE hxy_product_materials
                SET source_authority = 'official_internal', authority_version = 2
                WHERE material_id = %s
                """,
                (material_id,),
            )
        with pytest.raises(psycopg.Error), connection.transaction():
            insert_change_event(unauthorized_assignment_id)
        with pytest.raises(psycopg.Error), connection.transaction():
            insert_change_event(foreign_assignment_id)

        insert_change_event(owner_assignment_id)
        connection.execute(
            """
            UPDATE hxy_product_materials
            SET source_authority = 'official_internal', authority_version = 2
            WHERE material_id = %s
            """,
            (material_id,),
        )
        authority = connection.execute(
            """
            SELECT source_authority, authority_version
            FROM hxy_product_materials
            WHERE material_id = %s
            """,
            (material_id,),
        ).fetchone()
        assert authority == ("official_internal", 2)
        connection.rollback()


@pytest.mark.skipif(not DATABASE_URL, reason="HXY_TEST_DATABASE_URL is not configured")
def test_postgres_material_queue_lease_reclaim_and_completion() -> None:
    repository = MaterialRepository(DATABASE_URL)
    organization_id = str(uuid4())
    account_id = str(uuid4())
    foreign_account_id = str(uuid4())
    assignment_id = str(uuid4())
    foreign_assignment_id = str(uuid4())
    material_id = str(uuid4())
    client_upload_id = str(uuid4())
    username = f"material-test-{uuid4().hex}"
    foreign_username = f"material-foreign-test-{uuid4().hex}"

    with psycopg.connect(DATABASE_URL) as connection:
        connection.execute(
            "INSERT INTO hxy_organizations (organization_id, slug, name) VALUES (%s, %s, %s)",
            (organization_id, f"test-{uuid4().hex}", "材料队列测试组织"),
        )
        connection.execute(
            """
            INSERT INTO staff_accounts (
              id, username, display_name, password_hash, role
            )
            VALUES (%s, %s, %s, %s, 'hq_admin')
            """,
            (account_id, username, "材料测试", "not-a-login-credential"),
        )
        connection.execute(
            """
            INSERT INTO staff_accounts (
              id, username, display_name, password_hash, role
            )
            VALUES (%s, %s, %s, %s, 'hq_admin')
            """,
            (
                foreign_account_id,
                foreign_username,
                "隔离材料测试",
                "not-a-login-credential",
            ),
        )
        connection.execute(
            """
            INSERT INTO hxy_role_assignments (
              assignment_id, account_id, organization_id, role
            )
            VALUES (%s, %s, %s, 'founder')
            """,
            (assignment_id, account_id, organization_id),
        )
        connection.execute(
            """
            INSERT INTO hxy_role_assignments (
              assignment_id, account_id, organization_id, role
            )
            VALUES (%s, %s, %s, 'founder')
            """,
            (foreign_assignment_id, foreign_account_id, organization_id),
        )

    try:
        repository.create_material(
            {
                "material_id": material_id,
                "assignment_id": assignment_id,
                "client_upload_id": client_upload_id,
                "file_name": "真实数据库资料.txt",
                "extension": ".txt",
                "media_type": "text/plain",
                "size_bytes": 24,
                "sha256": "a" * 64,
                "storage_key": f"{assignment_id}/{material_id}/真实数据库资料.txt",
                "note": "隔离测试",
                "status": "processing",
                "understanding": {
                    "domain": "operations",
                    "official_use_allowed": False,
                },
                "max_assignment_storage_bytes": 1024,
            }
        )
        with psycopg.connect(DATABASE_URL) as connection:
            queued = connection.execute(
                "SELECT count(*) FROM hxy_material_parser_jobs WHERE material_id = %s",
                (material_id,),
            ).fetchone()[0]
        assert queued == 1

        barrier = Barrier(2)

        def claim(worker_id: str):
            barrier.wait()
            return repository.claim_next_job(worker_id, lease_seconds=30)

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(claim, ("worker-a", "worker-b")))
        claimed = [item for item in results if item is not None]
        assert len(claimed) == 1

        first = claimed[0]
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                """
                UPDATE hxy_material_parser_jobs
                SET lease_expires_at = NOW() - INTERVAL '1 second'
                WHERE job_id = %s
                """,
                (first["job_id"],),
            )
        assert repository.reclaim_stale_leases(limit=10) == 1

        second = repository.claim_next_job("worker-c", lease_seconds=30)
        assert second is not None
        assert second["job_id"] == first["job_id"]
        assert second["attempt_number"] == 2

        normalized_artifact_id = str(uuid4())
        completed = repository.complete_job(
            second["job_id"],
            "worker-c",
            artifacts=[
                {
                    "artifact_id": normalized_artifact_id,
                    "artifact_type": "normalized_markdown",
                    "storage_key": (
                        f"{assignment_id}/{material_id}/derived/"
                        f"{second['job_id']}/normalized.md"
                    ),
                    "sha256": "b" * 64,
                    "size_bytes": 12,
                    "metadata": {"parser": "markitdown"},
                },
                {
                    "artifact_id": str(uuid4()),
                    "artifact_type": "source_card",
                    "storage_key": (
                        f"{assignment_id}/{material_id}/derived/"
                        f"{second['job_id']}/source-card.json"
                    ),
                    "sha256": "c" * 64,
                    "size_bytes": 16,
                    "metadata": {"version": "hxy-source-card.v1"},
                },
            ],
            chunks=[
                {
                    "chunk_id": str(uuid4()),
                    "artifact_id": normalized_artifact_id,
                    "chunk_index": 0,
                    "heading": "首店接待原则",
                    "content": "首店接待先询问顾客当下感受，再介绍合适的体验项目。",
                    "char_count": 27,
                    "official_use_allowed": False,
                }
            ],
            understanding={
                "summary": "真实数据库队列已完成。",
                "domain": "operations",
                "official_use_allowed": False,
            },
            parser_name="markitdown",
            parser_version="0.1.6",
        )
        assert completed["status"] == "ready"

        with psycopg.connect(DATABASE_URL) as connection:
            job_status = connection.execute(
                "SELECT status FROM hxy_material_parser_jobs WHERE job_id = %s",
                (second["job_id"],),
            ).fetchone()[0]
            artifacts = connection.execute(
                """
                SELECT artifact_type, official_use_allowed
                FROM hxy_material_artifacts
                WHERE material_id = %s
                ORDER BY artifact_type
                """,
                (material_id,),
            ).fetchall()
            chunks = connection.execute(
                """
                SELECT assignment_id::text, material_id::text, official_use_allowed
                FROM hxy_material_chunks
                WHERE material_id = %s
                """,
                (material_id,),
            ).fetchall()
        assert job_status == "succeeded"
        assert artifacts == [
            ("normalized_markdown", False),
            ("source_card", False),
        ]
        assert chunks == [(assignment_id, material_id, False)]

        keyword_results = repository.search_material_chunks(
            assignment_id,
            "首店接待应该怎么做",
            limit=5,
        )
        assert len(keyword_results) == 1
        assert keyword_results[0]["material_id"] == material_id
        assert keyword_results[0]["official_use_allowed"] is False
        assert keyword_results[0]["source_path"] == f"material:{material_id}"
        assert keyword_results[0]["source_url"] == f"/api/v1/materials/{material_id}/content"

        latest_results = repository.search_material_chunks(
            assignment_id,
            "总结我刚上传的资料",
            limit=5,
        )
        assert len(latest_results) == 1
        assert latest_results[0]["material_id"] == material_id

        foreign_results = repository.search_material_chunks(
            foreign_assignment_id,
            "首店接待应该怎么做",
            limit=5,
        )
        assert foreign_results == []

        conversation_repository = ConversationRepository(DATABASE_URL)
        conversation = conversation_repository.create_conversation(assignment_id)
        client_message_id = str(uuid4())
        reservation = conversation_repository.reserve_user_message(
            assignment_id,
            conversation["id"],
            client_message_id,
            "首店接待应该怎么做？",
        )
        assert reservation is not None
        assert reservation["state"] == "reserved"

        trace_id = str(uuid4())
        assistant = conversation_repository.complete_assistant_message(
            assignment_id,
            conversation["id"],
            reservation["user_message"]["id"],
            client_message_id,
            {
                "answer": "先询问顾客当下感受，再介绍合适的体验项目。",
                "answer_status": "AI 草稿",
                "confidence": "medium",
                "needs_review": True,
                "sources": [
                    {
                        "id": f"material:{material_id}",
                        "title": "真实数据库资料.txt",
                        "url": f"/api/v1/materials/{material_id}/content",
                    }
                ],
                "next_actions": [],
            },
            trace_payload={
                "trace_id": trace_id,
                "role": "founder",
                "intent": "knowledge_question",
                "retrieval_count": 1,
                "private_material_count": 1,
                "authority_card_hit": False,
                "model_name": "integration-test",
                "input_tokens": 12,
                "output_tokens": 18,
                "latency_ms": 25,
                "payload": {"source_types": ["private_material"]},
            },
        )
        assert assistant is not None
        assert assistant["answer_status"] == "AI 草稿"

        repeated = conversation_repository.complete_assistant_message(
            assignment_id,
            conversation["id"],
            reservation["user_message"]["id"],
            client_message_id,
            {
                "answer": "重复完成不应产生第二条 Trace。",
                "answer_status": "AI 草稿",
            },
            trace_payload={
                "trace_id": str(uuid4()),
                "role": "founder",
                "intent": "knowledge_question",
            },
        )
        assert repeated is not None
        assert repeated["id"] == assistant["id"]

        with psycopg.connect(DATABASE_URL) as connection:
            traces = connection.execute(
                """
                SELECT trace_id::text,
                       assignment_id::text,
                       assistant_message_id::text,
                       retrieval_count,
                       private_material_count,
                       authority_card_hit,
                       outcome,
                       payload_json
                FROM hxy_product_answer_traces
                WHERE conversation_id = %s
                """,
                (conversation["id"],),
            ).fetchall()
        assert len(traces) == 1
        assert traces[0][:7] == (
            trace_id,
            assignment_id,
            assistant["id"],
            1,
            1,
            False,
            "succeeded",
        )
        assert traces[0][7] == {"source_types": ["private_material"]}

        postflight = run_postflight(Path(__file__).resolve().parents[1], DATABASE_URL)
        assert postflight["status"] == "passed"
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "DELETE FROM hxy_product_materials WHERE material_id = %s",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM hxy_role_assignments WHERE assignment_id IN (%s, %s)",
                (assignment_id, foreign_assignment_id),
            )
            connection.execute(
                "DELETE FROM staff_accounts WHERE id IN (%s, %s)",
                (account_id, foreign_account_id),
            )
            connection.execute(
                "DELETE FROM hxy_organizations WHERE organization_id = %s",
                (organization_id,),
            )
