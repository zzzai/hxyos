from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def test_hxy_hermes_deployment_files_are_hxy_owned() -> None:
    expected_files = [
        "ops/docker/hxy-hermes-compose.yml",
        "ops/docker/hxy-hermes-prebuilt-compose.yml",
        "ops/env/hxy-hermes.env.example",
        "ops/hxy-hermes-gateway.sh",
        "ops/systemd/hxy-hermes-gateway.service",
        "docs/operations/hxy-hermes-runtime.md",
    ]

    for relative_path in expected_files:
        assert (ROOT / relative_path).is_file(), f"missing {relative_path}"


def test_hxy_hermes_compose_is_isolated_from_default_and_htops_runtime() -> None:
    compose = read("ops/docker/hxy-hermes-compose.yml")

    assert "container_name: hxy-hermes" in compose
    assert "container_name: hxy-hermes-dashboard" in compose
    assert "../../.hermes-runtime:/opt/data" in compose
    assert "HERMES_HOME=/opt/data" in compose
    assert "HXY_HERMES_API_SERVER_KEY" in compose
    assert "build:\n      context: ${HXY_HERMES_SOURCE_DIR:-/root/hxy/.hermes-source/hermes-agent}\n      network: host" in compose

    forbidden = [
        "container_name: hermes\n",
        "container_name: hermes-dashboard\n",
        "~/.hermes",
        "/root/htops",
        "HETANG_",
    ]
    for token in forbidden:
        assert token not in compose


def test_hxy_hermes_prebuilt_compose_uses_official_image_and_hxy_runtime() -> None:
    compose = read("ops/docker/hxy-hermes-prebuilt-compose.yml")

    assert "image: ${HXY_HERMES_PREBUILT_IMAGE:-nousresearch/hermes-agent:latest}" in compose
    assert "container_name: hxy-hermes" in compose
    assert "container_name: hxy-hermes-dashboard" in compose
    assert "../../.hermes-runtime:/opt/data" in compose
    assert "HERMES_HOME=/opt/data" in compose
    assert "build:" not in compose

    forbidden = [
        "container_name: hermes\n",
        "container_name: hermes-dashboard\n",
        "~/.hermes",
        "/root/htops",
        "HETANG_",
    ]
    for token in forbidden:
        assert token not in compose


def test_hxy_hermes_systemd_service_uses_hxy_names_and_paths() -> None:
    service = read("ops/systemd/hxy-hermes-gateway.service")

    assert "Description=HXY Hermes Gateway" in service
    assert "WorkingDirectory=/root/hxy" in service
    assert "HXY_ROOT_DIR=/root/hxy" in service
    assert "ExecStart=/usr/bin/env bash /root/hxy/ops/hxy-hermes-gateway.sh up" in service
    assert "ExecStop=/usr/bin/env bash /root/hxy/ops/hxy-hermes-gateway.sh down" in service

    forbidden = ["/root/htops", "HETANG_", "hermes-gateway.service"]
    for token in forbidden:
        assert token not in service


def test_hxy_hermes_env_template_does_not_contain_real_secrets() -> None:
    env_template = read("ops/env/hxy-hermes.env.example")

    assert "HXY_HERMES_IMAGE_TAG=v2026.6.19" in env_template
    assert "HXY_HERMES_PREBUILT_IMAGE=nousresearch/hermes-agent:latest" in env_template
    assert "FEISHU_APP_ID=" in env_template
    assert "FEISHU_APP_SECRET=" in env_template
    assert "\nAPI_SERVER_KEY=" not in env_template
    assert "sk-" not in env_template
    assert "/root/htops" not in env_template


def test_hxy_hermes_runtime_artifacts_are_gitignored() -> None:
    gitignore = read(".gitignore")

    assert ".hermes-source/" in gitignore
    assert ".hermes-runtime/" in gitignore


def test_hxy_knowledge_api_script_exports_model_router_environment() -> None:
    script = read("ops/hxy-knowledge-api.sh")

    assert ": \"${HXY_DATABASE_URL:?HXY_DATABASE_URL is required for hxy-knowledge-api}\"" in script
    assert "POSTGRES_DB" not in script
    assert "POSTGRES_USER" not in script
    assert "POSTGRES_PASSWORD" not in script
    assert "HXY_PG_HOST_PORT" not in script
    assert "export HXY_MODEL_ROUTER_ENABLED" in script
    assert "export HXY_MODEL_API_KEY" in script
    assert "export HXY_MODEL_CONFIG_PATH" in script
    assert "hxy-knowledge-api.env" in script

    api_env_template = read("ops/env/hxy-knowledge-api.env.example")
    assert 'HXY_DATABASE_URL="host=127.0.0.1 port=55433 dbname=hxy user=hxy_app password=change-me"' in api_env_template
    assert "HXY_API_TOKEN=" in api_env_template
    assert "http://127.0.0.1:18084" in api_env_template
    assert "POSTGRES_PASSWORD" not in api_env_template
    assert "HXY_MODEL_API_KEY" not in api_env_template

    postgres_env_template = read("ops/env/hxy-postgres.env.example")
    assert "POSTGRES_DB=hxy" in postgres_env_template
    assert "POSTGRES_USER=hxy_app" in postgres_env_template


def test_hxy_hermes_prepare_uses_local_pinned_tag_before_network_fetch() -> None:
    script = read("ops/hxy-hermes-gateway.sh")

    local_tag_check = 'git -C "${HXY_HERMES_SOURCE_DIR}" rev-parse --verify "${HXY_HERMES_IMAGE_TAG}^{commit}"'
    fetch_command = 'git -C "${HXY_HERMES_SOURCE_DIR}" fetch --tags --prune origin'

    assert local_tag_check in script
    assert fetch_command in script
    assert script.index(local_tag_check) < script.index(fetch_command)


def test_hxy_hermes_script_defaults_to_prebuilt_and_keeps_source_build_commands() -> None:
    script = read("ops/hxy-hermes-gateway.sh")

    assert 'COMPOSE_FILE="${HXY_HERMES_COMPOSE_FILE:-${ROOT_DIR}/ops/docker/hxy-hermes-prebuilt-compose.yml}"' in script
    assert 'SOURCE_COMPOSE_FILE="${HXY_HERMES_SOURCE_COMPOSE_FILE:-${ROOT_DIR}/ops/docker/hxy-hermes-compose.yml}"' in script
    assert "require_prebuilt_inputs()" in script
    assert "require_source_inputs()" in script
    assert "up)\n    require_prebuilt_inputs" in script
    assert "restart)\n    require_prebuilt_inputs" in script
    assert "config)\n    require_prebuilt_inputs" in script
    assert "up-source)\n    require_source_inputs" in script
    assert "config-source)\n    require_source_inputs" in script
    assert "up-source)" in script
    assert "build-source)" in script
    assert "compose_source build" in script
    assert "validate-feishu)" in script
    assert "validate_feishu_credentials" in script


def test_hxy_hermes_runbook_documents_read_only_p0_notification_payload() -> None:
    runbook = read("docs/operations/hxy-hermes-runtime.md")

    for phrase in [
        "GET /api/v1/hxy/p0/notification",
        "hxy-p0-governance-notification.v1",
        "send_allowed: false",
        "write_to_database: false",
        "publish_allowed: false",
        "does not send Feishu messages",
    ]:
        assert phrase in runbook
