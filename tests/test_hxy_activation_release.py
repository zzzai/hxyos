from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.api.hxy_release.activation_release import (
    ACTIVATION_MIGRATIONS,
    ReleaseBoundaryError,
    build_argument_parser,
    database_identity,
    migration_inventory,
    render_result,
    validate_hxy_boundary,
)


ROOT = Path(__file__).resolve().parents[1]


def test_activation_release_allows_only_migrations_009_through_014() -> None:
    assert ACTIVATION_MIGRATIONS == (
        "009_hxy_product_identity.sql",
        "010_hxy_product_conversations.sql",
        "011_hxy_product_materials.sql",
        "012_hxy_assignment_sessions.sql",
        "013_hxy_material_intake_jobs.sql",
        "014_hxy_knowledge_activation.sql",
    )

    inventory = migration_inventory(ROOT)

    assert [item["name"] for item in inventory] == list(ACTIVATION_MIGRATIONS)
    assert all(len(item["sha256"]) == 64 for item in inventory)
    assert all(set(item) == {"name", "sha256"} for item in inventory)


def test_database_identity_omits_password_and_complete_dsn() -> None:
    password = "release-secret-value"
    dsn = (
        "host=127.0.0.1 port=55433 dbname=hxy_release_test "
        f"user=hxy_app password={password}"
    )

    identity = database_identity(dsn)
    rendered = json.dumps(identity, ensure_ascii=False)

    assert identity == {
        "host": "127.0.0.1",
        "port": "55433",
        "database": "hxy_release_test",
        "user": "hxy_app",
    }
    assert password not in rendered
    assert "password" not in rendered.lower()
    assert dsn not in rendered


def test_release_boundary_rejects_htops_database_or_root() -> None:
    identity = {
        "host": "127.0.0.1",
        "port": "55433",
        "database": "hxy_release_test",
        "user": "hxy_app",
    }

    validate_hxy_boundary(ROOT, identity)

    with pytest.raises(ReleaseBoundaryError, match="database"):
        validate_hxy_boundary(ROOT, identity | {"database": "htops"})
    with pytest.raises(ReleaseBoundaryError, match="root"):
        validate_hxy_boundary(Path("/root/htops"), identity)


def test_release_result_redacts_secrets_and_bounds_nested_values() -> None:
    password = "release-secret-value"
    full_dsn = f"host=127.0.0.1 dbname=hxy user=hxy_app password={password}"

    rendered = render_result(
        {
            "status": "passed",
            "detail": full_dsn,
            "nested": {"token": password, "long": "x" * 2000},
        },
        sensitive_values=(password, full_dsn),
    )

    assert password not in rendered
    assert full_dsn not in rendered
    assert "[redacted]" in rendered
    assert len(json.loads(rendered)["nested"]["long"]) <= 500


def test_activation_release_cli_exposes_only_guarded_commands() -> None:
    parser = build_argument_parser()

    for command in ("preflight", "backup", "apply", "postflight"):
        assert parser.parse_args([command]).command == command

    with pytest.raises(SystemExit):
        parser.parse_args(["restore"])

    script = (ROOT / "scripts" / "hxy-activation-release.py").read_text(encoding="utf-8")
    assert "apps.api.hxy_release.activation_release" in script
    assert "htops" not in script.lower()
