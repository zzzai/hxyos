#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
HOOK_DIR="${ROOT_DIR}/.git/hooks"
HOOK_FILE="${HOOK_DIR}/pre-commit"

if [[ ! -d "${ROOT_DIR}/.git" ]]; then
  echo "This script must be run inside the HXY Git repository." >&2
  exit 1
fi

mkdir -p "${HOOK_DIR}"

cat > "${HOOK_FILE}" <<'HOOK'
#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(git rev-parse --show-toplevel)"
cd "${ROOT_DIR}"

python3 scripts/check-hxy-secrets.py
HOOK

chmod +x "${HOOK_FILE}"
echo "Installed HXY pre-commit hook: ${HOOK_FILE}"
