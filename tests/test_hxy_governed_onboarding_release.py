from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from apps.api.hxy_release import onboarding_release
from apps.api.hxy_release.onboarding_release import (
    APPLY_CONFIRMATION,
    BACKUP_VERSION,
    ONBOARDING_MIGRATIONS,
    ONBOARDING_RELEASE,
    build_argument_parser,
    migration_inventory,
)


ROOT = Path(__file__).resolve().parents[1]


def test_release_profile_is_isolated_to_017() -> None:
    assert ONBOARDING_MIGRATIONS == ("017_hxy_governed_onboarding.sql",)
    assert ONBOARDING_RELEASE.release_id == "hxy-governed-onboarding-017"
    assert ONBOARDING_RELEASE.migrations == ONBOARDING_MIGRATIONS
    assert ONBOARDING_RELEASE.confirmation == "APPLY-HXY-017"
    assert ONBOARDING_RELEASE.advisory_lock == "hxy-governed-onboarding-017"
    assert ONBOARDING_RELEASE.dump_filename == "hxy-before-onboarding.dump"
    assert BACKUP_VERSION == "hxy-governed-onboarding-backup.v1"
    assert APPLY_CONFIRMATION == "APPLY-HXY-017"

    inventory = migration_inventory(ROOT, trusted_root=Path("/root/hxy"))

    assert inventory == [
        {
            "name": "017_hxy_governed_onboarding.sql",
            "sha256": hashlib.sha256(
                (ROOT / "data/migrations/017_hxy_governed_onboarding.sql").read_bytes()
            ).hexdigest(),
        }
    ]


def test_inventory_hashes_supplied_head_blob_bytes() -> None:
    blob = b"-- exact committed migration bytes\n"

    inventory = migration_inventory(
        ROOT,
        trusted_root=Path("/root/hxy"),
        migration_loader=lambda _root, name: (
            blob
            if name == "017_hxy_governed_onboarding.sql"
            else pytest.fail(f"unexpected migration: {name}")
        ),
    )

    assert inventory == [
        {
            "name": "017_hxy_governed_onboarding.sql",
            "sha256": hashlib.sha256(blob).hexdigest(),
        }
    ]


def test_cli_exposes_only_guarded_release_commands() -> None:
    parser = build_argument_parser()

    for command in ("preflight", "backup", "apply", "postflight"):
        assert parser.parse_args([command]).command == command
    for rejected in ("restore", "migrate", "seed", "publish"):
        with pytest.raises(SystemExit):
            parser.parse_args([rejected])

    script = (ROOT / "scripts/hxy-governed-onboarding-release.py").read_text(
        encoding="utf-8"
    )
    assert "apps.api.hxy_release.onboarding_release" in script
    assert "htops" not in script.lower()


def test_release_module_exports_guarded_operations() -> None:
    assert callable(onboarding_release.run_preflight)
    assert callable(onboarding_release.create_backup)
    assert callable(onboarding_release.apply_onboarding_migration)
    assert callable(onboarding_release.run_postflight)
    assert callable(onboarding_release.main)
