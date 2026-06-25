CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'vector') THEN
    CREATE EXTENSION IF NOT EXISTS vector;
  ELSE
    RAISE NOTICE 'pgvector extension is not installed; embedding column will be skipped.';
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS hxy_knowledge_import_runs (
  run_name TEXT PRIMARY KEY,
  source_manifest_path TEXT NOT NULL DEFAULT '',
  source_index_path TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  asset_count INTEGER NOT NULL DEFAULT 0,
  chunk_count INTEGER NOT NULL DEFAULT 0,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS hxy_knowledge_assets (
  asset_id TEXT PRIMARY KEY,
  run_name TEXT NOT NULL REFERENCES hxy_knowledge_import_runs(run_name) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '',
  file_name TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL,
  normalized_path TEXT NOT NULL DEFAULT '',
  extension TEXT NOT NULL DEFAULT '',
  mime_type TEXT NOT NULL DEFAULT '',
  file_size BIGINT NOT NULL DEFAULT 0,
  sha256 TEXT NOT NULL DEFAULT '',
  domain TEXT NOT NULL DEFAULT 'external',
  stage TEXT NOT NULL DEFAULT 'evergreen',
  status TEXT NOT NULL DEFAULT 'staged',
  warnings JSONB NOT NULL DEFAULT '[]'::jsonb,
  quality_score NUMERIC(5,3) NOT NULL DEFAULT 0,
  quality_grade TEXT NOT NULL DEFAULT 'unknown',
  quality_scores_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE hxy_knowledge_assets
  ADD COLUMN IF NOT EXISTS quality_score NUMERIC(5,3) NOT NULL DEFAULT 0,
  ADD COLUMN IF NOT EXISTS quality_grade TEXT NOT NULL DEFAULT 'unknown',
  ADD COLUMN IF NOT EXISTS quality_scores_json JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE TABLE IF NOT EXISTS hxy_knowledge_chunks (
  chunk_id TEXT PRIMARY KEY,
  asset_id TEXT NOT NULL REFERENCES hxy_knowledge_assets(asset_id) ON DELETE CASCADE,
  run_name TEXT NOT NULL REFERENCES hxy_knowledge_import_runs(run_name) ON DELETE CASCADE,
  chunk_index INTEGER NOT NULL DEFAULT 0,
  title TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL DEFAULT '',
  normalized_path TEXT NOT NULL DEFAULT '',
  domain TEXT NOT NULL DEFAULT 'external',
  stage TEXT NOT NULL DEFAULT 'evergreen',
  content TEXT NOT NULL,
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  search_vector TSVECTOR GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(source_path, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(content, '')), 'C')
  ) STORED,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vector') THEN
    ALTER TABLE hxy_knowledge_chunks
      ADD COLUMN IF NOT EXISTS embedding vector(1536);
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_assets_run ON hxy_knowledge_assets(run_name);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_assets_domain_stage ON hxy_knowledge_assets(domain, stage);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_assets_status ON hxy_knowledge_assets(status);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_assets_quality_score ON hxy_knowledge_assets(quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_assets_quality_grade ON hxy_knowledge_assets(quality_grade);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_assets_title_trgm ON hxy_knowledge_assets USING GIN(title gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_assets_path_trgm ON hxy_knowledge_assets USING GIN(source_path gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_chunks_run ON hxy_knowledge_chunks(run_name);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_chunks_asset ON hxy_knowledge_chunks(asset_id);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_chunks_domain_stage ON hxy_knowledge_chunks(domain, stage);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_chunks_fts ON hxy_knowledge_chunks USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_chunks_title_trgm ON hxy_knowledge_chunks USING GIN(title gin_trgm_ops);

DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'hxy_knowledge_chunks'
      AND column_name = 'embedding'
  ) THEN
    EXECUTE 'CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_chunks_embedding ON hxy_knowledge_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)';
  END IF;
EXCEPTION
  WHEN undefined_object THEN
    RAISE NOTICE 'Skipping vector index because pgvector operator class is unavailable.';
END $$;
