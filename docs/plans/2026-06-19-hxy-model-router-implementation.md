# HXY Model Router Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a safe HXY model-routing layer that reuses `/root/.codex/config.toml` for provider and model selection without exposing credentials or overriding approved answer cards.

**Architecture:** `ModelRouter` reads Codex's public model configuration, returns sanitized routing metadata, and keeps model execution opt-in through `HXY_MODEL_ROUTER_ENABLED`. FastAPI exposes the route status for Inspector/admin use, while `/api/knowledge/chat` attaches hidden `model_route` metadata to answer payloads. Approved answer cards stay authoritative and never call a model by default.

**Tech Stack:** Python 3.12 `tomllib`, FastAPI, unittest, existing HXY repository and answer engine.

---

## Implemented Tasks

1. Added `apps/api/hxy_knowledge/model_router.py`.
   - Reads `/root/.codex/config.toml` by default.
   - Supports `HXY_MODEL_CONFIG_PATH` override.
   - Emits sanitized public fields only: provider, selected model, wire API, endpoint host, reasoning effort, execution mode.
   - Does not read `/root/.codex/auth.json` or `.credentials.json`.

2. Added `GET /api/operating-brain/model-router`.
   - Returns `hxy-model-router.v1`.
   - Lists routes for `reasoning`, `classification`, `vision`, `embedding`, and `speech`.
   - Current live config: `custom`, `gpt-5.5`, `responses`, `code.yunfei.best`, `metadata_only`.

3. Attached `model_route` to `/api/knowledge/chat`.
   - Authority-card answers use `task_type = authority_answer`.
   - RAG fallback answers use `task_type = rag_answer`.
   - Main answer remains conclusion-first; route details are Inspector metadata.

4. Added tests.
   - Config loading and secret-field exclusion.
   - API route status.
   - Chat route metadata without changing answer-card priority.

## Execution Rule

Model calls are not executed unless `HXY_MODEL_ROUTER_ENABLED=1` is explicitly set. This prevents unstable model output from overriding approved HXY answer cards or leaking technical traces into the user-facing chat.

