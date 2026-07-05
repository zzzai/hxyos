# HXY Hermes Docker Runtime Design

## Goal

Add an HXY-owned Hermes Agent deployment that uses the official Docker support while keeping HXY runtime data isolated.

## Decision

Use a dedicated compose file under `ops/docker`, a dedicated env file under `ops/env`, and a dedicated systemd unit named `hxy-hermes-gateway.service`.

The runtime does not use upstream defaults directly because the upstream compose mounts a shared Hermes home and uses generic container names. HXY needs project-owned names, data paths, and lifecycle scripts.

## Runtime Boundaries

```text
/root/hxy/.hermes-source/hermes-agent  # official Hermes source tag
/root/hxy/.hermes-runtime              # HXY Hermes runtime data
```

The official source tag is pinned through:

```text
HXY_HERMES_IMAGE_TAG=v2026.6.19
```

## Components

- `ops/docker/hxy-hermes-compose.yml`: HXY container names, HXY runtime volume, localhost dashboard.
- `ops/env/hxy-hermes.env.example`: HXY-prefixed env template without secrets.
- `ops/hxy-hermes-gateway.sh`: prepares official source, builds, starts, stops, and prints config/logs.
- `ops/systemd/hxy-hermes-gateway.service`: systemd wrapper for Docker compose.
- `docs/operations/hxy-hermes-runtime.md`: runbook.

## Verification

Static tests assert:

- required files exist
- container names are HXY-owned
- volume points to `.hermes-runtime`
- service uses `/root/hxy`
- env template has no real secrets
