#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${HXY_ENV_FILE:-${ROOT_DIR}/ops/env/hxy-postgres.env}"
HOST="${HXY_API_HOST:-0.0.0.0}"
PORT="${HXY_API_PORT:-18081}"
LOG_FILE="${HXY_API_LOG:-/tmp/hxy-knowledge-api.log}"

usage() {
  cat <<'USAGE'
Usage: scripts/start-hxy-knowledge-api.sh [--restart|--stop|--foreground|--print-dsn]

Starts the HXY-owned knowledge API on port 18081 by default.
It builds HXY_DATABASE_URL as a psycopg keyword DSN so special characters in
POSTGRES_PASSWORD are not misread as URL separators.
USAGE
}

require_env() {
  if [[ ! -f "${ENV_FILE}" ]]; then
    echo "Missing ${ENV_FILE}. Create it from ops/env/hxy-postgres.env.example." >&2
    exit 1
  fi

  set -a
  source "${ENV_FILE}"
  set +a

  : "${POSTGRES_DB:?POSTGRES_DB is required}"
  : "${POSTGRES_USER:?POSTGRES_USER is required}"
  : "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD is required}"
}

build_database_dsn() {
  local pg_port="${HXY_PG_HOST_PORT:-55433}"
  printf 'host=127.0.0.1 port=%s dbname=%s user=%s password=%s' \
    "${pg_port}" "${POSTGRES_DB}" "${POSTGRES_USER}" "${POSTGRES_PASSWORD}"
}

hxy_api_pids() {
  ps -eo pid=,args= | awk '/python3 -m uvicorn apps[.]api[.]hxy_knowledge_api:app/ {print $1}'
}

stop_api() {
  local pids
  pids="$(hxy_api_pids || true)"
  if [[ -z "${pids}" ]]; then
    return 0
  fi
  # shellcheck disable=SC2086
  kill ${pids} 2>/dev/null || true
}

start_api() {
  export HXY_DATABASE_URL
  HXY_DATABASE_URL="$(build_database_dsn)"
  export PYTHONPATH="${ROOT_DIR}/apps/api:${PYTHONPATH:-}"
  cd "${ROOT_DIR}"
  setsid python3 -m uvicorn apps.api.hxy_knowledge_api:app --host "${HOST}" --port "${PORT}" >"${LOG_FILE}" 2>&1 &
  sleep 1
  hxy_api_pids
}

start_api_foreground() {
  export HXY_DATABASE_URL
  HXY_DATABASE_URL="$(build_database_dsn)"
  export PYTHONPATH="${ROOT_DIR}/apps/api:${PYTHONPATH:-}"
  cd "${ROOT_DIR}"
  exec python3 -m uvicorn apps.api.hxy_knowledge_api:app --host "${HOST}" --port "${PORT}"
}

main() {
  local command="${1:-start}"
  case "${command}" in
    -h|--help)
      usage
      ;;
    --print-dsn)
      require_env
      build_database_dsn
      printf '\n'
      ;;
    --stop)
      stop_api
      ;;
    --restart)
      require_env
      stop_api
      start_api
      ;;
    --foreground)
      require_env
      start_api_foreground
      ;;
    start)
      require_env
      start_api
      ;;
    *)
      usage >&2
      exit 2
      ;;
  esac
}

main "$@"
