# HXYOS Governed Onboarding V1 Release

## Scope

This runbook releases the HXY-owned governed onboarding feature and migration `017`.
It does not approve knowledge, publish brand content, change VI/SI, or access `/root/htops`.
The local HXY host remains behind FRP; the public edge is `115.190.245.14`, and the
public product origin is `https://hxyos.hexiaoyue.com`.

## Stop Rule

Run every Gate in order against one approved 40-character commit. Stop immediately
when a command fails, a result is not `passed`, the release seal changes, the target
database identity changes, or evidence is incomplete. Never print or record a database
password, complete DSN, session, request body, invitation value, employee data, or
private knowledge.

## Gate 1: Immutable Source

```bash
export HXY_RELEASE_COMMIT='<approved-40-character-commit>'
export HXY_RELEASE_PATH="/root/hxy/releases/onboarding/${HXY_RELEASE_COMMIT}"
test "${#HXY_RELEASE_COMMIT}" -eq 40
git -C /root/hxy rev-parse --verify "${HXY_RELEASE_COMMIT}^{commit}"
git -C /root/hxy worktree add --detach "$HXY_RELEASE_PATH" "$HXY_RELEASE_COMMIT"
test -z "$(git -C "$HXY_RELEASE_PATH" status --porcelain=v1 --untracked-files=all)"
test "$(git -C "$HXY_RELEASE_PATH" rev-parse HEAD)" = "$HXY_RELEASE_COMMIT"
```

The release source must be a detached HXY worktree. Do not clean, stash, reset, or
modify `/root/hxy` to manufacture a clean source.

## Gate 2: Test Build And Seal

```bash
cd "$HXY_RELEASE_PATH"
python3 -m venv .venv
.venv/bin/pip install -i https://pypi.tuna.tsinghua.edu.cn/simple \
  --requirement apps/api/requirements.txt
npm ci --registry=https://registry.npmmirror.com
npm --prefix apps/hxy-web ci --registry=https://registry.npmmirror.com
npm test
npm run build:web
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
git diff --check
printf '%s\n' "$HXY_RELEASE_COMMIT" > apps/hxy-web/dist/release-commit.txt
test "$(cat apps/hxy-web/dist/release-commit.txt)" = "$HXY_RELEASE_COMMIT"
```

Remove build-only Node dependencies, then seal all runtime files outside the release:

```bash
rm -rf node_modules apps/hxy-web/node_modules
export HXY_RELEASE_SEAL_DIR=/root/hxy/data/releases/onboarding
export HXY_RELEASE_SEAL="$HXY_RELEASE_SEAL_DIR/${HXY_RELEASE_COMMIT}.sha256"
mkdir -p "$HXY_RELEASE_SEAL_DIR"
test ! -e "$HXY_RELEASE_SEAL"
(
  cd "$HXY_RELEASE_PATH"
  find -L . -xdev -type f -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum
) > "$HXY_RELEASE_SEAL.tmp"
mv -T "$HXY_RELEASE_SEAL.tmp" "$HXY_RELEASE_SEAL"
chmod 0444 "$HXY_RELEASE_SEAL"
chmod -R a-w "$HXY_RELEASE_PATH"
cd "$HXY_RELEASE_PATH"
sha256sum -c "$HXY_RELEASE_SEAL"
test -z "$(find "$HXY_RELEASE_PATH" -xdev -perm /222 -print -quit)"
```

## Gate 3: Read-Only Preflight

Load the existing protected API environment without printing it. The release CLI reads
the database but must not write any row or schema in this Gate.

```bash
cd "$HXY_RELEASE_PATH"
set -a
source /root/hxy/ops/env/hxy-knowledge-api.env
set +a
sha256sum -c "$HXY_RELEASE_SEAL"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  scripts/hxy-governed-onboarding-release.py preflight
```

Pass criteria: PostgreSQL major 16, HXY boundary, `009-016` prerequisite contract,
clean exact commit, and one checksummed Git `HEAD` blob named
`017_hxy_governed_onboarding.sql`.

## Gate 4: Verified Restorable Backup

```bash
cd "$HXY_RELEASE_PATH"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  scripts/hxy-governed-onboarding-release.py backup
```

The command must produce a `0600` custom-format dump and `manifest.json` under
`/root/hxy/data/backups/onboarding/<UTC>/`, list the dump, restore it into an isolated
temporary database, verify that restore, remove the temporary database, and bind the
manifest to the exact PostgreSQL instance, commit, and `017` checksum.

Store only the returned path in the maintenance shell:

```bash
read -r HXY_ONBOARDING_BACKUP_MANIFEST
export HXY_ONBOARDING_BACKUP_MANIFEST
test -f "$HXY_ONBOARDING_BACKUP_MANIFEST"
pg_restore --list "$(dirname "$HXY_ONBOARDING_BACKUP_MANIFEST")/hxy-before-onboarding.dump" >/dev/null
```

## Gate 5: Apply 017

```bash
cd "$HXY_RELEASE_PATH"
sha256sum -c "$HXY_RELEASE_SEAL"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  scripts/hxy-governed-onboarding-release.py apply \
  --backup-manifest "$HXY_ONBOARDING_BACKUP_MANIFEST" \
  --confirm APPLY-HXY-017
```

The CLI must revalidate source, instance fingerprint, backup age, restore evidence and
checksum before SQL. It applies only `017` with `ON_ERROR_STOP`, one transaction, and
the `hxy-governed-onboarding-017` advisory lock.

## Gate 6: Read-Only Postflight

```bash
cd "$HXY_RELEASE_PATH"
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  scripts/hxy-governed-onboarding-release.py postflight
```

Pass criteria include the two onboarding tables, exact columns and state checks,
organization/store/assignment foreign keys, token-hash uniqueness, supporting indexes,
and enabled row and statement append-only triggers. Postflight never repairs schema.

## Gate 7: Environment And Edge

The local protected environment must contain this exact non-secret setting:

```bash
HXY_PUBLIC_APP_URL=https://hxyos.hexiaoyue.com
```

Verify without printing the rest of the environment:

```bash
test "$(sed -n 's/^HXY_PUBLIC_APP_URL=//p' /root/hxy/ops/env/hxy-knowledge-api.env)" \
  = 'https://hxyos.hexiaoyue.com'
systemctl cat hxy-knowledge-api.service
systemctl cat hxy-product-web.service
```

On public server `115.190.245.14`, merge
`ops/nginx/hxyos-public-edge.conf.example` into the existing TLS vhost. Preserve its
managed certificate directives. The `limit_req_zone` belongs in the `http` scope and
the exact redemption location must precede the generic API location.

```bash
sudo nginx -t
sudo systemctl reload nginx
sudo nginx -t
```

Do not continue unless HTTPS still serves the old release and repeated invalid
redemption requests produce bounded `401` responses followed by edge `429`, without
logging submitted values.

## Gate 8: Isolated Canary

Start the sealed candidate on loopback-only alternate ports while production remains on
the previous release:

```bash
export HXY_CANARY_API_PORT=28081
export HXY_CANARY_WEB_PORT=28084
(
  cd "$HXY_RELEASE_PATH"
  set -a; source /root/hxy/ops/env/hxy-knowledge-api.env; set +a
  export HXY_ROOT_DIR=/root/hxy
  export HXY_PUBLIC_APP_URL=https://hxyos.hexiaoyue.com
  export PYTHONPATH="$HXY_RELEASE_PATH/apps/api" PYTHONDONTWRITEBYTECODE=1
  exec .venv/bin/python -m uvicorn apps.api.hxy_knowledge_api:app \
    --host 127.0.0.1 --port "$HXY_CANARY_API_PORT"
) &
HXY_CANARY_API_PID=$!
python3 -m http.server "$HXY_CANARY_WEB_PORT" --bind 127.0.0.1 \
  --directory "$HXY_RELEASE_PATH/apps/hxy-web/dist" &
HXY_CANARY_WEB_PID=$!
```

Verify `/health`, unauthorized `/api/v1/me`, an invalid bounded redemption request,
the OpenAPI onboarding routes, and both local and candidate `release-commit.txt`.
Terminate and wait for both canary PIDs. Re-run the release seal afterward.

## Gate 9: Atomic Activation

Verify `/root/hxy/releases/current` is a sealed, detached, tested release and preserve it:

```bash
export HXY_PREVIOUS_RELEASE_PATH="$(readlink -f /root/hxy/releases/current)"
test -d "$HXY_PREVIOUS_RELEASE_PATH"
ln -sfn "$HXY_PREVIOUS_RELEASE_PATH" /root/hxy/releases/previous.next
mv -Tf /root/hxy/releases/previous.next /root/hxy/releases/previous
ln -sfn "$HXY_RELEASE_PATH" /root/hxy/releases/current.next
mv -Tf /root/hxy/releases/current.next /root/hxy/releases/current
test "$(readlink -f /root/hxy/releases/current)" = "$HXY_RELEASE_PATH"
```

Restart API and Web as one maintenance action and fail closed if either does not start:

```bash
systemctl restart hxy-knowledge-api.service hxy-product-web.service
systemctl is-active --quiet hxy-knowledge-api.service
systemctl is-active --quiet hxy-product-web.service
test "$(curl -fsS https://hxyos.hexiaoyue.com/release-commit.txt)" \
  = "$HXY_RELEASE_COMMIT"
```

## Gate 10: Production Canaries And Evidence

Use a designated HXY canary store and short-lived maintenance sessions to execute:

```text
Founder -> create one manager invitation -> redeem
Manager -> create one employee invitation -> redeem
Employee -> open conversation and role home
Manager -> deactivate temporary employee
Founder -> deactivate temporary manager
Founder/Manager -> revoke any unused invitations
```

Confirm `invite_created`, `invite_redeemed`, `invite_revoked` and
`member_deactivated` audit events by identifiers and counts only. Revoke every temporary
session. Inspect local API, Nginx and public-edge logs and prove they contain no request body,
cookie, URL fragment, invitation token, display name, or private knowledge. Record
only commit, release and previous paths, seal checksums, migration manifest path, bounded
Gate statuses, canary identifiers, status codes, and timestamps.

## Rollback

If API/Web activation or canaries fail after migration `017` committed, migration 017
must not be reversed by dropping tables, deleting events, or editing schema manually.
It is additive and the previous code does not depend on it. Atomically switch
`/root/hxy/releases/current` to the already verified `/root/hxy/releases/previous`,
restart both services, verify the previous `release-commit.txt`, health, authentication,
conversation, task and training journeys, then retain the failed candidate and all
evidence for investigation.

If apply failed before commit, the guarded transaction leaves schema unchanged. If
postflight failed after commit, stop and investigate against the verified backup; do not
rerun SQL or restore production without a separate approved recovery plan.
