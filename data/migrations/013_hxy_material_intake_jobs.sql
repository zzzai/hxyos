ALTER TABLE hxy_product_materials
  DROP CONSTRAINT IF EXISTS hxy_product_materials_status_check;

ALTER TABLE hxy_product_materials
  ADD CONSTRAINT hxy_product_materials_status_check CHECK (
    status IN (
      'received',
      'understood',
      'understanding_failed',
      'processing',
      'ready',
      'needs_attention',
      'archived'
    )
  );

CREATE TABLE IF NOT EXISTS hxy_material_parser_jobs (
  job_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id UUID NOT NULL,
  material_id UUID NOT NULL UNIQUE,
  parser_strategy TEXT NOT NULL DEFAULT 'markitdown' CHECK (
    parser_strategy IN ('markitdown')
  ),
  status TEXT NOT NULL DEFAULT 'queued' CHECK (
    status IN ('queued', 'running', 'retryable_failed', 'succeeded', 'permanent_failed')
  ),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts BETWEEN 1 AND 10),
  available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  lease_owner TEXT CHECK (
    lease_owner IS NULL OR char_length(btrim(lease_owner)) BETWEEN 1 AND 120
  ),
  lease_expires_at TIMESTAMPTZ,
  last_error_code TEXT CHECK (
    last_error_code IS NULL OR char_length(last_error_code) <= 80
  ),
  last_error_summary TEXT CHECK (
    last_error_summary IS NULL OR char_length(last_error_summary) <= 500
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (assignment_id, material_id)
    REFERENCES hxy_product_materials(assignment_id, material_id)
    ON DELETE CASCADE,
  CHECK (attempt_count <= max_attempts),
  CHECK ((status = 'running') = (lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)),
  CHECK (status <> 'succeeded' OR completed_at IS NOT NULL),
  CHECK (status <> 'permanent_failed' OR completed_at IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_hxy_material_parser_jobs_claim
  ON hxy_material_parser_jobs (available_at, created_at, job_id)
  WHERE status IN ('queued', 'retryable_failed');

CREATE INDEX IF NOT EXISTS idx_hxy_material_parser_jobs_stale_lease
  ON hxy_material_parser_jobs (lease_expires_at, job_id)
  WHERE status = 'running';

CREATE INDEX IF NOT EXISTS idx_hxy_material_parser_jobs_assignment
  ON hxy_material_parser_jobs (assignment_id, updated_at DESC, job_id DESC);

CREATE TABLE IF NOT EXISTS hxy_material_job_attempts (
  attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id UUID NOT NULL REFERENCES hxy_material_parser_jobs(job_id) ON DELETE CASCADE,
  attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
  worker_id TEXT NOT NULL CHECK (char_length(btrim(worker_id)) BETWEEN 1 AND 120),
  outcome TEXT NOT NULL DEFAULT 'running' CHECK (
    outcome IN ('running', 'succeeded', 'retryable_failed', 'permanent_failed', 'lost_lease')
  ),
  parser_name TEXT CHECK (
    parser_name IS NULL OR char_length(parser_name) <= 80
  ),
  parser_version TEXT CHECK (
    parser_version IS NULL OR char_length(parser_version) <= 80
  ),
  error_code TEXT CHECK (
    error_code IS NULL OR char_length(error_code) <= 80
  ),
  error_summary TEXT CHECK (
    error_summary IS NULL OR char_length(error_summary) <= 500
  ),
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  UNIQUE (job_id, attempt_number),
  CHECK ((outcome = 'running') = (completed_at IS NULL))
);

CREATE INDEX IF NOT EXISTS idx_hxy_material_job_attempts_job
  ON hxy_material_job_attempts (job_id, attempt_number DESC);

CREATE TABLE IF NOT EXISTS hxy_material_artifacts (
  artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id UUID NOT NULL,
  material_id UUID NOT NULL,
  job_id UUID NOT NULL REFERENCES hxy_material_parser_jobs(job_id) ON DELETE CASCADE,
  artifact_type TEXT NOT NULL CHECK (
    artifact_type IN ('normalized_markdown', 'source_card')
  ),
  storage_key TEXT NOT NULL UNIQUE,
  sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
  metadata_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  official_use_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (official_use_allowed = FALSE),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (assignment_id, material_id)
    REFERENCES hxy_product_materials(assignment_id, material_id)
    ON DELETE CASCADE,
  UNIQUE (job_id, artifact_type)
);

CREATE INDEX IF NOT EXISTS idx_hxy_material_artifacts_material
  ON hxy_material_artifacts (assignment_id, material_id, created_at DESC);
