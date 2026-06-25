# HXY Knowledge Service Design

## Goal

Upgrade the HXY file-based knowledge brain into a project-level AI knowledge service backed by PostgreSQL, optional pgvector, FastAPI, and an admin web page.

## Scope

This version focuses on a reliable local/project deployment:

- PostgreSQL schema for assets, chunks, runs, and search metadata.
- Optional `pgvector` support when the extension exists.
- FastAPI service under `apps/api` using `hxy-*` ownership.
- Admin page under `apps/admin-web` for upload, status, ingestion, and search.
- Import existing HXY knowledge artifacts from `knowledge/structured` and `knowledge/normalized`.

This is not yet a full enterprise RAG platform with external model embeddings, RBAC, workflow approvals, or graph database. The schema leaves room for those.

## Architecture

```text
knowledge/raw/inbox
knowledge/structured/*.json
knowledge/normalized/**/*.md
        ↓
scripts/import-hxy-knowledge-db.py
        ↓
PostgreSQL
  hxy_knowledge_assets
  hxy_knowledge_chunks
  hxy_knowledge_import_runs
        ↓
FastAPI apps/api/hxy_knowledge_api.py
        ↓
apps/admin-web/knowledge.html
```

## Database

PostgreSQL remains the system of record for metadata and searchable chunks.

Tables:

- `hxy_knowledge_assets`: one row per source asset.
- `hxy_knowledge_chunks`: search units from normalized/search-index chunks.
- `hxy_knowledge_import_runs`: ingestion run history.

Extensions:

- `pgcrypto` for UUIDs.
- `pg_trgm` for fuzzy title/path search.
- `vector` if pgvector is installed.

The first implementation uses PostgreSQL full text and trigram search. Embeddings are optional and nullable because local embedding infrastructure is not yet configured.

## API

FastAPI exposes:

- `GET /health`
- `GET /api/knowledge/summary`
- `GET /api/knowledge/assets`
- `GET /api/knowledge/search?q=...`
- `POST /api/knowledge/upload`
- `POST /api/knowledge/import`

Upload writes files to `knowledge/raw/inbox`. Import reads the current manifest/search index and upserts database rows.

## Admin UI

`apps/admin-web/knowledge.html` is a quiet operational UI:

- Status strip: assets, chunks, domains, pending review.
- Upload panel.
- Import action.
- Search panel with filters.
- Asset table.

It is a production-like tool surface, not a landing page.

## Boundaries

All code, data, and API routes stay inside `/root/hxy`.

The service name is HXY-owned. It does not call htops `api/main.py` and does not write HXY business data into `/root/htops`.

## Validation

Required checks:

- Python unit tests for search/import logic.
- SQL migration parses under `psql` when PostgreSQL is available.
- API import and search work against a local database when `HXY_DATABASE_URL` is configured.
- Admin page loads and can call API endpoints.
- No generated output references `/root/htops` except boundary documentation.
