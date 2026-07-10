#!/usr/bin/env bash
set -euo pipefail

HXY_ROOT_DIR="${HXY_ROOT_DIR:-/root/hxy}"
HXY_ENV_FILE="${HXY_ENV_FILE:-${HXY_ROOT_DIR}/ops/env/hxy-knowledge-api.env}"

if [[ -f "${HXY_ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${HXY_ENV_FILE}"
  set +a
fi

exec "${HXY_ROOT_DIR}/.venv/bin/python" \
  "${HXY_ROOT_DIR}/scripts/run-hxy-material-worker.py" \
  --poll-seconds "${HXY_MATERIAL_WORKER_POLL_SECONDS:-2}" \
  --lease-seconds "${HXY_MATERIAL_WORKER_LEASE_SECONDS:-300}" \
  --base-retry-seconds "${HXY_MATERIAL_WORKER_BASE_RETRY_SECONDS:-30}" \
  "$@"
