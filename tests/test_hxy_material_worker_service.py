from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
API_UNIT = ROOT / "ops/systemd/hxy-knowledge-api.service"
WEB_UNIT = ROOT / "ops/systemd/hxy-product-web.service"
UNIT = ROOT / "ops/systemd/hxy-material-worker.service"
OUTBOX_UNIT = ROOT / "ops/systemd/hxy-outbox-worker.service"


def test_knowledge_api_runs_from_the_atomic_release_pointer() -> None:
    service = API_UNIT.read_text(encoding="utf-8")

    assert "WorkingDirectory=/root/hxy/releases/current" in service
    assert "Environment=HXY_ROOT_DIR=/root/hxy" in service
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in service
    assert "Environment=PYTHONPATH=/root/hxy/releases/current/apps/api" in service
    assert "/root/hxy/releases/current/.venv/bin/python" in service
    assert "apps.api.hxy_knowledge_api:app" in service
    assert "ExecStart=/usr/bin/env bash /root/hxy/ops/hxy-knowledge-api.sh" not in service
    assert "ExecStart=/root/hxy/.venv/bin/python" not in service


def test_product_web_runs_from_the_atomic_release_pointer() -> None:
    service = WEB_UNIT.read_text(encoding="utf-8")

    assert "WorkingDirectory=/root/hxy/releases/current/apps/hxy-web/dist" in service
    assert "/root/hxy/releases/current/apps/hxy-web/dist" in service
    assert "http.server 18084" in service
    assert "/root/hxy/apps/hxy-web/dist" not in service


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


def test_outbox_worker_runs_from_the_atomic_release_pointer() -> None:
    service = OUTBOX_UNIT.read_text(encoding="utf-8")

    assert "WorkingDirectory=/root/hxy/releases/current" in service
    assert "Environment=HXY_ROOT_DIR=/root/hxy" in service
    assert "Environment=HXY_ENV_FILE=/root/hxy/ops/env/hxy-knowledge-api.env" in service
    assert "source /root/hxy/ops/env/hxy-knowledge-api.env" in service
    assert "Environment=PYTHONDONTWRITEBYTECODE=1" in service
    assert "Environment=PYTHONPATH=/root/hxy/releases/current/apps/api" in service
    assert "/root/hxy/releases/current/.venv/bin/python" in service
    assert "/root/hxy/releases/current/scripts/run-hxy-outbox-worker.py" in service
    assert "/root/htops" not in service
    assert "ExecStart=/root/hxy/.venv/bin/python" not in service
