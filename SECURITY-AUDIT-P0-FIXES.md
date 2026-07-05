# HXY P0 Security Runbook

**Date:** 2026-07-05
**Priority:** P0
**Scope:** HXY only. Do not touch `/root/htops`.

## Finding

The local runtime env file `ops/env/hxy-postgres.env` contains secret values and must remain local-only:

```bash
POSTGRES_PASSWORD=<redacted>
HXY_MODEL_API_KEY=<redacted>
```

Current repository controls:

- `ops/env/*.env` is ignored by `.gitignore`.
- `ops/env/*.toml` is ignored by `.gitignore`.
- `*.env.example` files are allowed as templates.
- Real secret values must never be pasted into Markdown, code, tests, scripts, issues, or chat output.

## Immediate Actions

1. Rotate the database password in PostgreSQL.
2. Revoke and recreate the model API key in the provider console.
3. Replace `ops/env/hxy-postgres.env` with newly issued local values.
4. Keep file permissions restricted:

```bash
chmod 600 /root/hxy/ops/env/hxy-postgres.env
```

5. Restart only HXY services after rotation.

## Git Verification

Run these checks before publishing or pushing:

```bash
git ls-files -- ops/env/hxy-postgres.env
git log --all --full-history -- ops/env/hxy-postgres.env
git check-ignore -v ops/env/hxy-postgres.env
python3 scripts/check-hxy-secrets.py
```

Expected result:

- `git ls-files` returns nothing for the real env file.
- `git log --all --full-history` returns nothing for the real env file.
- `git check-ignore` shows the file is ignored.
- `scripts/check-hxy-secrets.py` passes.

## History Cleanup Policy

Only rewrite Git history if a real secret was actually committed.

If history cleanup is required:

1. Create a full repository backup first.
2. Coordinate with every collaborator before force-push.
3. Use `git filter-repo` or an equivalent audited history rewrite tool.
4. Force-push only after backups and coordination are complete.
5. Require collaborators to reclone.

Do not run destructive history rewrite commands as a routine fix when verification shows the file was never tracked.

## Prevention

Required gates:

- Keep local env files ignored.
- Keep examples secret-free.
- Run `python3 scripts/check-hxy-secrets.py` before commits.
- Install the local pre-commit hook with:

```bash
scripts/install-hxy-git-hooks.sh
```

## Acceptance Criteria

- [ ] Real local env files are ignored.
- [ ] Real local env files are not tracked by Git.
- [ ] No real secret values appear in tracked or untracked non-ignored files.
- [ ] The model API key has been revoked and recreated externally.
- [ ] The database password has been rotated externally.
- [ ] HXY services restart successfully with the new local env.
- [ ] The secret scanner passes.

## Notes

This runbook intentionally does not contain real passwords, API keys, database URLs, tokens, or revoked key fragments.
