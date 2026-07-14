from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "ops/systemd/hxy-material-worker.service"


def test_material_worker_runs_from_the_atomic_release_pointer() -> None:
    service = UNIT.read_text(encoding="utf-8")

    assert "WorkingDirectory=/root/hxy/releases/current" in service
    assert "Environment=HXY_ROOT_DIR=/root/hxy" in service
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in service
    assert "Environment=PYTHONPATH=/root/hxy/releases/current/apps/api" in service
    assert "/root/hxy/releases/current/.venv/bin/python" in service
    assert "/root/hxy/releases/current/scripts/run-hxy-material-worker.py" in service
    assert "ReadWritePaths=/root/hxy/data/product-materials" in service
    assert "ExecStart=/usr/bin/env bash /root/hxy/ops/hxy-material-worker.sh" not in service
    assert "ExecStart=/root/hxy/.venv/bin/python" not in service
