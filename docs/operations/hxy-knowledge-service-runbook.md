# HXY Knowledge Service Runbook

## Scope

This service is the HXY-owned project brain runtime:

- API service: `apps/api/hxy_knowledge_api.py`
- User brain page: `apps/admin-web/brain.html`
- Admin page: `apps/admin-web/knowledge.html`
- Database migration: `data/migrations/002_hxy_knowledge_service.sql`
- Answer engine migrations:
  - `data/migrations/003_hxy_answer_engine.sql`
  - `data/migrations/004_hxy_answer_evolution.sql`
- Image understanding migration:
  - `data/migrations/005_hxy_image_understanding.sql`
- Import script: `scripts/import-hxy-knowledge-db.py`
- Image understanding script: `scripts/understand-hxy-images.py`

Do not use htops API routes or databases for HXY knowledge data.

## Current Knowledge Storage

Raw uploads and original files:

```text
/root/hxy/knowledge/raw/inbox
```

Classified raw references:

```text
/root/hxy/knowledge/raw/classified
```

Normalized markdown:

```text
/root/hxy/knowledge/normalized
```

Structured manifests, indexes, OCR output, and generated knowledge JSON:

```text
/root/hxy/knowledge/structured
```

Human-readable reports:

```text
/root/hxy/knowledge/reports
```

PostgreSQL tables after migration/import:

```text
hxy_knowledge_import_runs
hxy_knowledge_assets
hxy_knowledge_chunks
hxy_knowledge_answer_runs
hxy_knowledge_feedback
hxy_knowledge_review_tasks
hxy_knowledge_answer_cards
hxy_knowledge_image_understandings
```

Answer engine data:

- `hxy_knowledge_answer_runs`: every structured answer returned by `/api/knowledge/chat`.
- `hxy_knowledge_feedback`: user feedback for useful, incorrect, or needs-work answers.
- `hxy_knowledge_review_tasks`: open review work created from incorrect or needs-work feedback.
- `hxy_knowledge_answer_cards`: approved authority answers. When a question matches an approved card, chat returns the card before synthesizing a new answer.

Knowledge asset quality scores:

- `quality_score`: 0-1 weighted score for retrieval and answer readiness.
- `quality_grade`: A-E quality band.
- `quality_scores_json`: full scoring payload with dimension scores, weights, reasons, and recommended action.

The scoring model is `hxy-quality-score.v1`. It combines:

```text
classification_confidence 14%
extraction_quality        18%
business_value            20%
authority                 16%
recency                    8%
conflict_safety           10%
answerability             14%
```

Grades:

```text
A >= 0.85  authority-ready
B >= 0.70  usable
C >= 0.55  usable with caution
D >= 0.40  review first
E <  0.40  repair or summarize manually
```

Recommended actions:

- `approve`: can be used by the answer engine with normal evidence citation.
- `review`: visible and searchable, but should be reviewed before becoming an authority source.
- `repair`: usually image-only, weak extraction, or insufficient metadata; add OCR/manual summary before relying on it.

## Image Understanding V2

Images are handled as business knowledge, not as OCR-only attachments.

The local Image Understanding V2 pipeline reads the inbox manifest and normalized OCR text, then produces:

```text
knowledge/structured/hxy-image-understandings-inbox-2026-06-11.json
knowledge/structured/hxy-inbox-search-index-inbox-2026-06-11.json
```

It creates one `image_understanding` chunk per image and stores the structured record in:

```text
hxy_knowledge_image_understandings
```

Current fields include:

```text
image_type
visual_summary
business_summary
ocr_text
detected_entities
prices
related_domains
confidence
qa_ready
needs_review
```

Run the parser before importing when new images arrive:

```bash
cd /root/hxy
python3 scripts/understand-hxy-images.py --run-name inbox-2026-06-11
HXY_DATABASE_URL="$HXY_DATABASE_URL" python3 scripts/import-hxy-knowledge-db.py
```

The current local run contains 90 image understanding records:

```text
brand_visual           9
competitor_reference 45
menu                  36
```

For image questions, `/api/knowledge/chat` now adds a picture-aware fallback query using `图片类型`, `视觉摘要`, and `业务摘要`, then prefers the `business_summary` field in the final answer. This keeps answers oriented to product value, price, selling point, competitor reference, and review status instead of raw OCR text.

The repository search also supports a parameterized multi-token fallback:

```text
full query ILIKE
OR
all meaningful business tokens ILIKE
```

This makes queries such as `产品菜单类图片 草本泡脚 复购话术` and `竞品参考品牌图片 背书 价格 视觉风格` recall image understanding chunks even when the exact full sentence is absent.

## Dependencies

Install the API dependencies:

```bash
cd /root/hxy
python3 -m pip install --break-system-packages -r apps/api/requirements.txt
```

## PostgreSQL Setup

The current local HXY PostgreSQL container is `hxy-postgres`. It listens on:

```text
127.0.0.1:55433
```

Use the HXY-owned env file for local credentials:

```bash
cp ops/env/hxy-postgres.env.example ops/env/hxy-postgres.env
# Edit POSTGRES_PASSWORD locally. Do not commit real secrets.
```

When a command needs `HXY_DATABASE_URL`, prefer a psycopg keyword DSN so special
characters in `POSTGRES_PASSWORD` are not treated as URL separators:

```bash
set -a
. ops/env/hxy-postgres.env
set +a
export HXY_DATABASE_URL="host=127.0.0.1 port=${HXY_PG_HOST_PORT:-55433} dbname=${POSTGRES_DB} user=${POSTGRES_USER} password=${POSTGRES_PASSWORD}"
```

If using the PostgreSQL 16 Docker image and pgvector is not available, install it in the database container:

```bash
docker exec -u root hxy-postgres bash -lc 'apt-get update && apt-get install -y postgresql-16-pgvector'
```

Apply the migration:

```bash
psql "$HXY_DATABASE_URL" -v ON_ERROR_STOP=1 -f data/migrations/002_hxy_knowledge_service.sql
psql "$HXY_DATABASE_URL" -v ON_ERROR_STOP=1 -f data/migrations/003_hxy_answer_engine.sql
psql "$HXY_DATABASE_URL" -v ON_ERROR_STOP=1 -f data/migrations/004_hxy_answer_evolution.sql
psql "$HXY_DATABASE_URL" -v ON_ERROR_STOP=1 -f data/migrations/005_hxy_image_understanding.sql
```

The migration enables `pgcrypto`, `pg_trgm`, and `vector` when available. It creates `embedding vector(1536)` and an ivfflat index when pgvector exists. If pgvector is not installed, the service still works with full-text and trigram search.

## Import Current Knowledge

Import the current HXY inbox run:

```bash
cd /root/hxy
HXY_DATABASE_URL="$HXY_DATABASE_URL" python3 scripts/import-hxy-knowledge-db.py
```

The default run is:

```text
inbox-2026-06-11
```

Override it when needed:

```bash
HXY_KNOWLEDGE_RUN=inbox-2026-06-11 python3 scripts/import-hxy-knowledge-db.py
```

## Start API

Run FastAPI on an HXY-owned local port:

```bash
cd /root/hxy
scripts/start-hxy-knowledge-api.sh --restart
```

For foreground debugging:

```bash
cd /root/hxy
scripts/start-hxy-knowledge-api.sh --foreground
```

Key endpoints:

```text
GET  /health
GET  /api/knowledge/summary
GET  /api/knowledge/assets
GET  /api/knowledge/search?q=泡脚
POST /api/knowledge/chat
POST /api/knowledge/feedback
GET  /api/knowledge/review-tasks
POST /api/knowledge/review-tasks/{task_id}/resolve
POST /api/knowledge/answer-cards
POST /api/knowledge/upload
POST /api/knowledge/import
```

Answer engine contract:

```text
POST /api/knowledge/chat
```

Returns conclusion-first structured answers with:

```text
intent
audience
answer
reasoning
evidence
conflicts
corrections
confidence
next_actions
needs_review
from_answer_card
```

Self-evolution loop:

```text
POST /api/knowledge/feedback
```

`incorrect` and `needs_work` feedback create open review tasks and a structured correction package.

The correction package is stored in `hxy_knowledge_review_tasks.payload_json.correction_package` and contains:

```text
failure_type
target
normalized_question
review_notes
recommended_actions
answer_card_draft
```

Current behavior:

- `incorrect`: marks the failure as `incorrect_answer`, sets high priority, and targets corrected authority-card creation.
- `needs_work`: marks the failure as `incomplete_answer`, sets medium priority, and targets missing-field completion.
- `answer_card_draft`: creates a draft payload only. It is not approved automatically.

This keeps self-evolution human-reviewed: the system prepares the correction work; the team confirms the right answer before approving an authority answer card.

```text
GET /api/knowledge/review-tasks?status=open&limit=20
```

Returns the team's current review queue.

`brain.html` displays the correction package fields and includes a button to create a draft answer card from `answer_card_draft`.

```text
POST /api/knowledge/review-tasks/{task_id}/resolve
```

Marks a review task as handled after the team has corrected the answer, added missing material, or promoted an approved answer card.

```text
POST /api/knowledge/answer-cards
```

Creates a draft, approved, or archived authority answer card. Approved cards are used before synthesized answers when the question pattern and intent match.

## Start Admin Page

Serve the static admin page:

```bash
cd /root/hxy
python3 -m http.server 18990 --directory apps/admin-web
```

Open:

```text
http://127.0.0.1:18990/brain.html
http://127.0.0.1:18990/knowledge.html
```

Both pages default to:

```text
http://127.0.0.1:18081
```

`brain.html` is the user-facing answer engine entry:

- upload files into `/root/hxy/knowledge/raw/inbox`
- import uploaded files into PostgreSQL
- ask structured questions
- give feedback
- view open review tasks
- promote strong answers into approved answer cards

`knowledge.html` is the admin asset surface for upload, import, search, and asset status checks.

## Verification

Run tests and compile checks:

```bash
cd /root/hxy
python3 -m unittest tests/test_hxy_knowledge_service.py tests/test_hxy_knowledge_api.py -v
python3 -m unittest tests/test_hxy_brain_frontend.py -v
python3 -m py_compile apps/api/hxy_knowledge/*.py apps/api/hxy_knowledge_api.py scripts/import-hxy-knowledge-db.py
```

Check HXY runtime code does not depend on htops runtime paths:

```bash
rg -n "/root/htops|htops api/main.py|htops-" apps/api apps/admin-web data/migrations scripts/import-hxy-knowledge-db.py || true
```

Boundary documentation may mention htops only to state what not to use.
