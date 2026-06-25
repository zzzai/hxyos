#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/ops/env/hxy-postgres.env"

if [[ ! -f "${ENV_FILE}" ]]; then
  echo "Missing ${ENV_FILE}. Create it from ops/env/hxy-postgres.env.example." >&2
  exit 1
fi

set -a
source "${ENV_FILE}"
set +a

for migration in "${ROOT_DIR}"/data/migrations/*.sql; do
  echo "Applying ${migration}"
  docker exec -i -e PGPASSWORD="${POSTGRES_PASSWORD}" hxy-postgres \
    psql -h 127.0.0.1 -p "${HXY_PG_HOST_PORT:-55433}" -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=1 < "${migration}"
done
