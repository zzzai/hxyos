# HXY Hermes Docker Runtime Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add an HXY-owned Hermes Agent Docker deployment using the latest verified official release tag.

**Architecture:** A wrapper script prepares the official Hermes source into an HXY-owned directory and runs an HXY-specific compose file. Runtime state lives in `/root/hxy/.hermes-runtime`; service and container names use `hxy-*`.

**Tech Stack:** Docker Compose, systemd, Bash, pytest.

---

### Task 1: Add Boundary Tests

**Files:**
- Create: `tests/test_hxy_hermes_deployment.py`

**Step 1: Write failing tests**

Assert that the compose, env template, script, service, and runbook exist. Assert that compose uses `hxy-hermes`, `.hermes-runtime`, and no shared default Hermes runtime.

**Step 2: Run test to verify it fails**

Run:

```bash
.venv/bin/pytest tests/test_hxy_hermes_deployment.py -q
```

Expected: FAIL because the files do not exist yet.

### Task 2: Add HXY Hermes Runtime Files

**Files:**
- Create: `ops/docker/hxy-hermes-compose.yml`
- Create: `ops/env/hxy-hermes.env.example`
- Create: `ops/hxy-hermes-gateway.sh`
- Create: `ops/systemd/hxy-hermes-gateway.service`
- Create: `docs/operations/hxy-hermes-runtime.md`

**Step 1: Implement files**

Create HXY-owned deployment files with pinned `v2026.6.19` source tag, HXY container names, HXY runtime volume, and localhost-only dashboard/API server.

**Step 2: Run focused tests**

Run:

```bash
.venv/bin/pytest tests/test_hxy_hermes_deployment.py -q
```

Expected: PASS.

### Task 3: Validate Compose And Shell

**Files:**
- Verify: `ops/docker/hxy-hermes-compose.yml`
- Verify: `ops/hxy-hermes-gateway.sh`

**Step 1: Make script executable**

Run:

```bash
chmod +x ops/hxy-hermes-gateway.sh
```

**Step 2: Render compose config**

Run:

```bash
bash ops/hxy-hermes-gateway.sh config
```

Expected: Compose config renders without htops paths.

### Task 4: Run Regression Suite

**Files:**
- Verify: full repo

**Step 1: Run tests**

Run:

```bash
npm test
```

Expected: all Python and TypeScript tests pass.
