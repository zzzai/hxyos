# HXY GitHub Upload Readiness Report

**Date:** 2026-07-05
**Scope:** `/root/hxy`
**Policy:** project code can be uploaded; private brand knowledge and operating data stay local.

## Current Gate Status

These checks passed locally:

```bash
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
python3 scripts/export-hxyos-public.py --target /tmp/hxyos-public-ci-check
npm test
```

Observed results:

- secret scan: no committed or commit-eligible HXY secrets found;
- public release preflight: `public_release_preflight_ok=true`;
- public scaffold export: generated and verified under `/tmp/hxyos-public-ci-check`;
- project tests: Python `441 passed`, TypeScript `52 passed`.

## Private Material Boundary

The following paths are now explicitly local-only:

```text
ops/env/*.env
ops/env/*.toml
knowledge/raw/
knowledge/normalized/
knowledge/structured/
knowledge/reports/
knowledge/runs/
knowledge/wiki/
knowledge/okf/core/
data/seeds/
data/exports/
data/backups/
quarantine/
```

Current `git check-ignore` confirms:

- `ops/env/hxy-postgres.env` is ignored;
- `data/seeds/catalog.current.json` is ignored;
- `knowledge/okf/core/hxy-positioning.md` is ignored;
- `knowledge/raw/inbox` is ignored.

## Removed From Git Index, Kept Locally

These files were removed from the Git index with `git rm --cached`, but the local files remain on disk:

```text
data/seeds/catalog.current.json
knowledge/okf/core/franchise-store-model.md
knowledge/okf/core/hxy-positioning.md
knowledge/okf/core/qingpao-tiaobuyang-script.md
```

They should not be restored to Git unless a separate explicit declassification review is completed.

## Commit Batches

Recommended upload sequence:

1. **Security and release guardrails**
   - `.gitignore`
   - `.github/workflows/ci.yml`
   - `SECURITY-AUDIT-P0-FIXES.md`
   - `docs/operations/2026-07-05-hxy-secret-rotation-status.md`
   - `docs/operations/hxy-github-public-release-checklist.md`
   - `scripts/check-hxy-secrets.py`
   - `scripts/check-hxy-public-release.py`
   - `scripts/install-hxy-git-hooks.sh`
   - `tests/test_hxy_secret_scanner.py`
   - `tests/test_hxy_public_release_guardrails.py`
   - the four `git rm --cached` index removals listed above

2. **Knowledge foundation and Loop Engine**
   - benchmark, compiler, ingest loop, memory context, process memory, governance modules;
   - related scripts and tests;
   - keep raw/private knowledge out.

3. **Hermes runtime**
   - HXY-owned compose files, env examples, gateway script, service file, runbook;
   - no Feishu secrets.

4. **Frontend and product surface**
   - `apps/admin-web/*` changes;
   - include only after a separate UI/product review.

## Do Not Batch Blindly

The worktree still contains many modified and untracked files from multiple workstreams. Do not run a broad `git add .` before reviewing the batch. Use explicit path staging.

Before any push:

```bash
python3 scripts/check-hxy-secrets.py
python3 scripts/check-hxy-public-release.py
npm test
git status --short
```

## Remaining External Step

The DashScope model API key still requires provider-side rotation:

1. revoke the old key in Alibaba Cloud DashScope;
2. create a new key;
3. place it only in the ignored local env file;
4. set `HXY_MODEL_ROUTER_ENABLED=true` only after verification.
