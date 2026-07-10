from __future__ import annotations

import os
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import psycopg
import pytest

from apps.api.hxy_product.material_repository import MaterialRepository


DATABASE_URL = os.getenv("HXY_TEST_DATABASE_URL", "").strip()


@pytest.mark.skipif(not DATABASE_URL, reason="HXY_TEST_DATABASE_URL is not configured")
def test_postgres_material_queue_lease_reclaim_and_completion() -> None:
    repository = MaterialRepository(DATABASE_URL)
    organization_id = str(uuid4())
    account_id = str(uuid4())
    assignment_id = str(uuid4())
    material_id = str(uuid4())
    client_upload_id = str(uuid4())
    username = f"material-test-{uuid4().hex}"

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
            INSERT INTO hxy_role_assignments (
              assignment_id, account_id, organization_id, role
            )
            VALUES (%s, %s, %s, 'founder')
            """,
            (assignment_id, account_id, organization_id),
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

        completed = repository.complete_job(
            second["job_id"],
            "worker-c",
            artifacts=[
                {
                    "artifact_id": str(uuid4()),
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
            understanding={
                "summary": "真实数据库队列已完成。",
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
        assert job_status == "succeeded"
        assert artifacts == [
            ("normalized_markdown", False),
            ("source_card", False),
        ]
    finally:
        with psycopg.connect(DATABASE_URL) as connection:
            connection.execute(
                "DELETE FROM hxy_product_materials WHERE material_id = %s",
                (material_id,),
            )
            connection.execute(
                "DELETE FROM hxy_role_assignments WHERE assignment_id = %s",
                (assignment_id,),
            )
            connection.execute(
                "DELETE FROM staff_accounts WHERE id = %s",
                (account_id,),
            )
            connection.execute(
                "DELETE FROM hxy_organizations WHERE organization_id = %s",
                (organization_id,),
            )
