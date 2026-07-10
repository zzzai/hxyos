# HXY Material Intake Runtime

## Boundary

The material worker processes private HXY uploads only.

```text
original
-> durable parser job
-> normalized Markdown
-> Source Card
```

所有衍生产物都保持 `official_use_allowed=false`，不得自动进入正式知识、正式回答或长期记忆。

## Prerequisites

1. Install API dependencies in `/root/hxy/.venv`.
2. Configure `HXY_DATABASE_URL` in `/root/hxy/ops/env/hxy-knowledge-api.env`.
3. Apply migrations through `013_hxy_material_intake_jobs.sql`.
4. Ensure `/root/hxy/data/product-materials` exists and is owned by the service account.

Apply migrations:

```bash
cd /root/hxy
HXY_ENV_FILE=/root/hxy/ops/env/hxy-knowledge-api.env \
  bash scripts/apply-db-migrations.sh
```

## One-Shot Check

Run one claim cycle without installing systemd:

```bash
cd /root/hxy
bash ops/hxy-material-worker.sh --once
```

Expected output is one JSON line with `idle`, `succeeded`, `retryable_failed`, or `permanent_failed`. It must not include source paths or stack traces.

## Systemd

Install and start only after the one-shot check succeeds:

```bash
install -m 0644 ops/systemd/hxy-material-worker.service \
  /etc/systemd/system/hxy-material-worker.service
systemctl daemon-reload
systemctl enable --now hxy-material-worker
systemctl status hxy-material-worker
```

Inspect recent structured output:

```bash
journalctl -u hxy-material-worker -n 100 --no-pager
```

## Recovery

The worker claims work with a lease. If the process exits, the next worker cycle reclaims the expired lease and retries within the stored attempt budget.

For repeated failures:

1. keep the original file unchanged;
2. inspect `last_error_code`, not raw parser output;
3. verify MarkItDown in the project virtual environment;
4. run one `--once` cycle;
5. use the existing product retry action only after the dependency or file issue is fixed.

Do not edit queue rows manually to mark them `succeeded`. Do not copy any HXY material into `/root/htops`.
