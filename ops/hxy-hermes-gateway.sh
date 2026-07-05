#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${HXY_ROOT_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ENV_FILE="${HXY_HERMES_ENV_FILE:-${ROOT_DIR}/ops/env/hxy-hermes.env}"
COMPOSE_FILE="${HXY_HERMES_COMPOSE_FILE:-${ROOT_DIR}/ops/docker/hxy-hermes-prebuilt-compose.yml}"
SOURCE_COMPOSE_FILE="${HXY_HERMES_SOURCE_COMPOSE_FILE:-${ROOT_DIR}/ops/docker/hxy-hermes-compose.yml}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi

export HXY_ROOT_DIR="${ROOT_DIR}"
export HXY_HERMES_ENV_FILE="${ENV_FILE}"
export HXY_HERMES_IMAGE_TAG="${HXY_HERMES_IMAGE_TAG:-v2026.6.19}"
export HXY_HERMES_PREBUILT_IMAGE="${HXY_HERMES_PREBUILT_IMAGE:-nousresearch/hermes-agent:latest}"
export HXY_HERMES_REPO_URL="${HXY_HERMES_REPO_URL:-https://github.com/NousResearch/hermes-agent.git}"
export HXY_HERMES_SOURCE_DIR="${HXY_HERMES_SOURCE_DIR:-${ROOT_DIR}/.hermes-source/hermes-agent}"
export HXY_HERMES_API_SERVER_HOST="${HXY_HERMES_API_SERVER_HOST:-127.0.0.1}"
export HXY_HERMES_API_SERVER_KEY="${HXY_HERMES_API_SERVER_KEY:-}"
export HERMES_UID="${HERMES_UID:-10000}"
export HERMES_GID="${HERMES_GID:-10000}"

runtime_dir="${ROOT_DIR}/.hermes-runtime"

compose() {
  docker compose --project-name hxy-hermes --file "${COMPOSE_FILE}" "$@"
}

compose_source() {
  docker compose --project-name hxy-hermes --file "${SOURCE_COMPOSE_FILE}" "$@"
}

validate_feishu_credentials() {
  if [[ -z "${FEISHU_APP_ID:-}" || -z "${FEISHU_APP_SECRET:-}" ]]; then
    echo "FEISHU_APP_ID and FEISHU_APP_SECRET are required" >&2
    exit 1
  fi

  python3 - <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

body = json.dumps({
    "app_id": os.environ["FEISHU_APP_ID"],
    "app_secret": os.environ["FEISHU_APP_SECRET"],
}).encode("utf-8")

domain = os.getenv("FEISHU_DOMAIN", "feishu").strip().lower()
host = "https://open.larksuite.com" if domain == "lark" else "https://open.feishu.cn"
url = f"{host}/open-apis/auth/v3/tenant_access_token/internal"

request = urllib.request.Request(
    url,
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)

try:
    with urllib.request.urlopen(request, timeout=15) as response:
        payload = json.loads(response.read().decode("utf-8"))
except urllib.error.HTTPError as exc:
    raw = exc.read().decode("utf-8", errors="replace")
    print(f"Feishu credential validation request failed: HTTP {exc.code} {raw}", file=sys.stderr)
    sys.exit(2)
except Exception as exc:
    print(f"Feishu credential validation request failed: {type(exc).__name__}: {exc}", file=sys.stderr)
    sys.exit(2)

code = payload.get("code")
message = payload.get("msg", "")
if code == 0:
    print("Feishu credential validation passed")
    sys.exit(0)

print(f"Feishu credential validation failed: code={code} msg={message}", file=sys.stderr)
sys.exit(1)
PY
}

prepare_source() {
  mkdir -p "$(dirname "${HXY_HERMES_SOURCE_DIR}")" "${runtime_dir}"

  if [[ ! -d "${HXY_HERMES_SOURCE_DIR}/.git" ]]; then
    rm -rf "${HXY_HERMES_SOURCE_DIR}"
    git clone --depth 1 --branch "${HXY_HERMES_IMAGE_TAG}" "${HXY_HERMES_REPO_URL}" "${HXY_HERMES_SOURCE_DIR}"
    return
  fi

  if git -C "${HXY_HERMES_SOURCE_DIR}" rev-parse --verify "${HXY_HERMES_IMAGE_TAG}^{commit}" >/dev/null 2>&1; then
    git -C "${HXY_HERMES_SOURCE_DIR}" checkout --detach "${HXY_HERMES_IMAGE_TAG}"
    return
  fi

  git -C "${HXY_HERMES_SOURCE_DIR}" fetch --tags --prune origin
  git -C "${HXY_HERMES_SOURCE_DIR}" checkout --detach "${HXY_HERMES_IMAGE_TAG}"
}

require_prebuilt_inputs() {
  if [[ ! -f "${COMPOSE_FILE}" ]]; then
    echo "Missing compose file: ${COMPOSE_FILE}" >&2
    exit 1
  fi
  mkdir -p "${runtime_dir}"
}

require_source_inputs() {
  if [[ ! -f "${SOURCE_COMPOSE_FILE}" ]]; then
    echo "Missing source compose file: ${SOURCE_COMPOSE_FILE}" >&2
    exit 1
  fi
  if [[ ! -d "${HXY_HERMES_SOURCE_DIR}" ]]; then
    prepare_source
  fi
  mkdir -p "${runtime_dir}"
}

case "${1:-up}" in
  prepare)
    prepare_source
    ;;
  build)
    compose pull
    ;;
  build-source)
    prepare_source
    compose_source build
    ;;
  up)
    require_prebuilt_inputs
    compose up -d hxy-hermes-gateway hxy-hermes-dashboard
    ;;
  up-source)
    require_source_inputs
    compose_source up -d --build hxy-hermes-gateway hxy-hermes-dashboard
    ;;
  down)
    compose down
    ;;
  restart)
    require_prebuilt_inputs
    compose up -d --force-recreate hxy-hermes-gateway hxy-hermes-dashboard
    ;;
  logs)
    shift || true
    compose logs -f "$@"
    ;;
  ps)
    compose ps
    ;;
  config)
    require_prebuilt_inputs
    compose config
    ;;
  config-source)
    require_source_inputs
    compose_source config
    ;;
  validate-feishu)
    validate_feishu_credentials
    ;;
  *)
    cat >&2 <<USAGE
Usage: $0 {prepare|build|build-source|up|up-source|down|restart|logs|ps|config|config-source|validate-feishu}

Environment:
  HXY_HERMES_ENV_FILE      ${ENV_FILE}
  HXY_HERMES_IMAGE_TAG     ${HXY_HERMES_IMAGE_TAG}
  HXY_HERMES_PREBUILT_IMAGE ${HXY_HERMES_PREBUILT_IMAGE}
  HXY_HERMES_SOURCE_DIR    ${HXY_HERMES_SOURCE_DIR}
  HXY_HERMES_REPO_URL      ${HXY_HERMES_REPO_URL}
USAGE
    exit 2
    ;;
esac
