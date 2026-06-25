#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="${HXY_ROOT_DIR:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
ENV_FILE="${HXY_ENV_FILE:-${ROOT_DIR}/ops/env/hxy-postgres.env}"
HOST="${HXY_API_HOST:-127.0.0.1}"
PORT="${HXY_API_PORT:-18081}"
LOG_FILE="${HXY_API_LOG:-/tmp/hxy-knowledge-api.log}"
PYTHON_BIN="${HXY_API_PYTHON:-python3}"

if [[ -f "${ENV_FILE}" ]]; then
  set -a
  source "${ENV_FILE}"
  set +a
fi

if [[ -z "${HXY_DATABASE_URL:-}" ]]; then
  : "${POSTGRES_DB:?POSTGRES_DB is required when HXY_DATABASE_URL is not set}"
  : "${POSTGRES_USER:?POSTGRES_USER is required when HXY_DATABASE_URL is not set}"
  : "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required when HXY_DATABASE_URL is not set}"
  HXY_DATABASE_URL="host=127.0.0.1 port=${HXY_PG_HOST_PORT:-55433} dbname=${POSTGRES_DB} user=${POSTGRES_USER} password=${POSTGRES_PASSWORD}"
fi

: "${HXY_API_TOKEN:?HXY_API_TOKEN is required for hxy-knowledge-api}"

mkdir -p "$(dirname "${LOG_FILE}")"
cd "${ROOT_DIR}"

export HXY_ROOT_DIR="${ROOT_DIR}"
export HXY_DATABASE_URL
export HXY_API_TOKEN
export PYTHONPATH="${ROOT_DIR}/apps/api:${PYTHONPATH:-}"

exec "${PYTHON_BIN}" -m uvicorn apps.api.hxy_knowledge_api:app \
  --host "${HOST}" \
  --port "${PORT}"
