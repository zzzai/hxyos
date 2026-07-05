# HXY Hermes Runtime

## Purpose

HXY uses Hermes Agent as an optional mobile and chat gateway, especially for Feishu/Lark workflows.

This runtime is HXY-owned. It must stay separate from any other Hermes instance on the same host.

## Official Docker Basis

Hermes Agent has an official Docker deployment:

- `Dockerfile`
- `docker-compose.yml`
- gateway command: `hermes gateway run`
- dashboard command: `hermes dashboard --host 127.0.0.1 --no-open`

HXY pins the build to the latest verified official release tag:

```text
v2026.6.19
```

The default HXY runtime uses the official prebuilt Docker image:

```text
nousresearch/hermes-agent:latest
```

For source builds, the HXY wrapper clones the pinned tag into:

```text
/root/hxy/.hermes-source/hermes-agent
```

Runtime data is stored in:

```text
/root/hxy/.hermes-runtime
```

## Why HXY Does Not Use The Default Compose Directly

The upstream compose defaults are suitable for a single generic local Hermes instance. HXY needs stricter boundaries:

- HXY container names must be `hxy-*`.
- HXY data must live under `/root/hxy`.
- HXY must not use a user-level shared Hermes home.
- Dashboard stays localhost-only.
- API server stays localhost-only unless an authenticated reverse proxy is added.

## Files

```text
ops/docker/hxy-hermes-compose.yml
ops/env/hxy-hermes.env.example
ops/hxy-hermes-gateway.sh
ops/systemd/hxy-hermes-gateway.service
```

## Setup

Create the local env file:

```bash
cd /root/hxy
cp ops/env/hxy-hermes.env.example ops/env/hxy-hermes.env
chmod 600 ops/env/hxy-hermes.env
```

Edit `ops/env/hxy-hermes.env` and fill Feishu values when the Feishu app is ready.

Pull the official prebuilt image:

```bash
cd /root/hxy
bash ops/hxy-hermes-gateway.sh build
```

Start:

```bash
cd /root/hxy
bash ops/hxy-hermes-gateway.sh up
```

With an empty Feishu configuration the gateway starts but does not enable any
messaging platform. This is the expected safe default for infrastructure
verification.

Check status and logs:

```bash
bash ops/hxy-hermes-gateway.sh ps
bash ops/hxy-hermes-gateway.sh logs hxy-hermes-gateway
```

Dashboard health check:

```bash
curl -fsS http://127.0.0.1:9119 >/tmp/hxy-hermes-dashboard.html
```

Stop the runtime after a smoke test:

```bash
bash ops/hxy-hermes-gateway.sh down
```

## Systemd

Install the HXY service:

```bash
cp /root/hxy/ops/systemd/hxy-hermes-gateway.service /etc/systemd/system/hxy-hermes-gateway.service
systemctl daemon-reload
systemctl enable --now hxy-hermes-gateway.service
```

Do not replace or stop another Hermes service unless that is a separate planned maintenance task.

## Feishu

Set these in `ops/env/hxy-hermes.env`:

```text
FEISHU_APP_ID=
FEISHU_APP_SECRET=
FEISHU_DOMAIN=feishu
FEISHU_CONNECTION_MODE=websocket
FEISHU_ENCRYPT_KEY=
FEISHU_VERIFICATION_TOKEN=
FEISHU_ALLOWED_USERS=
FEISHU_ALLOW_BOTS=none
FEISHU_REQUIRE_MENTION=true
FEISHU_HOME_CHANNEL=
```

Use `FEISHU_ALLOWED_USERS` before any broad rollout.

## Read-Only P0 Governance Notification

HXY exposes a read-only P0 governance notification payload for Hermes / Feishu routing:

```text
GET /api/v1/hxy/p0/notification
GET /api/v1/hxy/p0/notification?run_id=benchmark-loop-latest
```

The payload version is:

```text
hxy-p0-governance-notification.v1
```

Boundary fields must remain:

```text
send_allowed: false
write_to_database: false
publish_allowed: false
```

This endpoint only renders a message payload. It does not send Feishu messages, edit `p0-review-decisions.json`, approve answer cards, publish cards, or import cards into storage.

## API Server

The compose maps HXY-prefixed settings to Hermes API settings:

```text
HXY_HERMES_API_SERVER_HOST=127.0.0.1
HXY_HERMES_API_SERVER_KEY=
```

Keep the host as `127.0.0.1`. If remote access is needed, put it behind a separately authenticated reverse proxy.

## Update

To update Hermes:

1. Confirm the new official tag.
2. Change `HXY_HERMES_IMAGE_TAG` in `ops/env/hxy-hermes.env`.
3. Run:

```bash
cd /root/hxy
bash ops/hxy-hermes-gateway.sh prepare
bash ops/hxy-hermes-gateway.sh build
bash ops/hxy-hermes-gateway.sh restart
```

## Boundary Check

Before enabling in production, run:

```bash
cd /root/hxy
.venv/bin/pytest tests/test_hxy_hermes_deployment.py -q
bash ops/hxy-hermes-gateway.sh config
```
If a pinned source build is required instead of the prebuilt image:

```bash
cd /root/hxy
bash ops/hxy-hermes-gateway.sh prepare
bash ops/hxy-hermes-gateway.sh build-source
bash ops/hxy-hermes-gateway.sh up-source
```
