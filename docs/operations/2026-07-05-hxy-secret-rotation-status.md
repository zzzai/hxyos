# HXY Secret Rotation Status

**Date:** 2026-07-05
**Scope:** HXY local services only.

## Database

- Rotated `POSTGRES_PASSWORD` for the HXY PostgreSQL role.
- Updated local `ops/env/hxy-postgres.env`.
- Kept `ops/env/hxy-postgres.env` untracked and ignored.
- Tightened HXY PostgreSQL local authentication from `trust` to `scram-sha-256`.
- Verified:
  - new password connects;
  - wrong password is rejected;
  - no password is rejected.

## Model API Key

- Removed the local active `HXY_MODEL_API_KEY` value from `ops/env/hxy-postgres.env`.
- Set `HXY_MODEL_ROUTER_ENABLED=false` locally until a new DashScope key is issued.
- Provider config remains DashScope-compatible mode in `ops/env/hxy-model-router.toml`.

The old model API key must still be revoked in the Alibaba Cloud DashScope console. A new key should be issued there, then placed only in the ignored local env file.

## Verification

Run:

```bash
python3 scripts/check-hxy-secrets.py
.venv/bin/pytest -q tests/test_hxy_secret_scanner.py
```

Do not paste real secrets into this document.
