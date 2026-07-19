# HXYOS Operating And Material Release

## Scope

This release activates only migrations `020-023`, the HXY operating-event workflow,
and the private material safety scan. It never reads from or writes to `/root/htops`,
does not approve formal knowledge, and does not promote uploaded material into an
official answer.

## Stop Rule

Run every gate against one clean 40-character Git commit. Stop when a release seal,
database identity, PostgreSQL instance fingerprint, migration checksum, backup
verification, postflight check, service health check, or canary fails.

## Gate 1: Immutable Release

Create a detached worktree under `/root/hxy/releases/operating-material/<commit>`,
install Python dependencies from the Tsinghua mirror and Node dependencies from the
npmmirror registry, run the complete test/build/security suite, write
`apps/hxy-web/dist/release-commit.txt`, and create an external SHA-256 release seal.
The sealed release must be read-only before database mutation.

## Gate 2: Read-Only Preflight

Load `/root/hxy/ops/env/hxy-knowledge-api.env` without printing it, then run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  scripts/hxy-operating-material-release.py preflight
```

It must report PostgreSQL 16, the HXY database boundary, the complete migration `019`
prerequisite, a clean commit, and `migration_state=pending`.

## Gate 3: Restorable Backup

Run:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  scripts/hxy-operating-material-release.py backup
```

The guarded runner uses `pg_dump`, restores the custom dump into a temporary database,
verifies the restore, removes the temporary database, and writes a manifest bound to
the instance, commit, and exact migration checksums. Preserve the returned manifest
path without printing the DSN.

## Gate 4: Apply Only 020-023

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python \
  scripts/hxy-operating-material-release.py apply \
  --backup-manifest "$HXY_OPERATING_MATERIAL_BACKUP_MANIFEST" \
  --confirm APPLY-HXY-020-023
```

The release uses one transaction and one advisory lock. Run `postflight` separately
after apply and require the full catalog, operating, idempotency, and material source
identity contract.

## Gate 5: ClamAV

The scanner must bind only to `127.0.0.1:3310`:

```bash
docker compose -f ops/docker/hxy-clamav-compose.yml up -d
docker compose -f ops/docker/hxy-clamav-compose.yml ps
```

Do not start material parsing until the container health check passes and the HXY env
contains bounded host, port, timeout, and maximum stream size values.

## Gate 6: Canary And Activation

Start the candidate API on a loopback-only alternate port and verify `/health`,
unauthorized access, authenticated operating routes, authenticated material routes,
and one private upload through scan, parse, artifact, preview and search.

Stop every process that can create or consume database work before changing the
release pointer. The services must report inactive before the switch; a nonzero
`is-active` result is expected only when every listed unit is inactive:

```bash
systemctl stop hxy-knowledge-api.service hxy-material-worker.service hxy-outbox-worker.service
systemctl is-active hxy-knowledge-api.service hxy-material-worker.service hxy-outbox-worker.service
for unit in hxy-knowledge-api.service hxy-material-worker.service hxy-outbox-worker.service; do
  test "$(systemctl is-active "$unit")" = "inactive"
done
```

Preserve the old release target, then atomically replace the current pointer without
exposing a partially written symlink:

```bash
HXY_PREVIOUS_RELEASE="$(readlink -f /root/hxy/releases/current)"
ln -sfn "$HXY_PREVIOUS_RELEASE" /root/hxy/releases/previous
ln -sfn "$HXY_CANDIDATE_RELEASE" /root/hxy/releases/current.next
mv -Tf /root/hxy/releases/current.next /root/hxy/releases/current
```

Reload the installed units and start the API before the workers. The web process is
read-only but is included so all public surfaces reference the same candidate:

```bash
systemctl daemon-reload
systemctl start hxy-knowledge-api.service hxy-product-web.service hxy-material-worker.service hxy-outbox-worker.service
```

Do not run an old material or Outbox worker against a database migrated for a newer
release. If any writer cannot be stopped, do not switch the release pointer.

## Gate 7: Rollback

If service health or canaries fail, stop the API, material worker, and Outbox worker;
verify that all writers are inactive; atomically point `releases/current` back to
`releases/previous`; restart the previous services; and verify the public release
marker. Database rollback is a separate maintenance action: restore the verified dump
only after preserving the failed postflight evidence and any new post-migration
business writes. Never perform a blind destructive rollback.
