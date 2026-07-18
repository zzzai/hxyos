ALTER TABLE hxy_material_parser_jobs
  ADD COLUMN IF NOT EXISTS job_type TEXT NOT NULL DEFAULT 'parse';

ALTER TABLE hxy_material_parser_jobs
  DROP CONSTRAINT IF EXISTS hxy_material_parser_jobs_material_id_key,
  DROP CONSTRAINT IF EXISTS hxy_material_parser_jobs_parser_strategy_check,
  DROP CONSTRAINT IF EXISTS hxy_material_parser_jobs_job_type_check,
  DROP CONSTRAINT IF EXISTS hxy_material_parser_jobs_job_type_strategy_check,
  DROP CONSTRAINT IF EXISTS hxy_material_parser_jobs_material_job_type_key;

ALTER TABLE hxy_material_parser_jobs
  ADD CONSTRAINT hxy_material_parser_jobs_job_type_check
    CHECK (job_type IN ('scan', 'parse')),
  ADD CONSTRAINT hxy_material_parser_jobs_parser_strategy_check
    CHECK (parser_strategy IN ('clamav', 'markitdown')),
  ADD CONSTRAINT hxy_material_parser_jobs_job_type_strategy_check
    CHECK (
      (job_type = 'scan' AND parser_strategy = 'clamav')
      OR (job_type = 'parse' AND parser_strategy = 'markitdown')
    ),
  ADD CONSTRAINT hxy_material_parser_jobs_material_job_type_key
    UNIQUE (material_id, job_type);

CREATE INDEX IF NOT EXISTS idx_hxy_material_jobs_type_claim
  ON hxy_material_parser_jobs (job_type, available_at, created_at, job_id)
  WHERE status IN ('queued', 'retryable_failed');

ALTER TABLE hxy_material_job_attempts
  ADD COLUMN IF NOT EXISTS source_sha256 CHAR(64),
  ADD COLUMN IF NOT EXISTS source_size_bytes BIGINT;

ALTER TABLE hxy_material_job_attempts
  DROP CONSTRAINT IF EXISTS hxy_material_job_attempts_source_identity_check;

ALTER TABLE hxy_material_job_attempts
  ADD CONSTRAINT hxy_material_job_attempts_source_identity_check
  CHECK (
    (source_sha256 IS NULL AND source_size_bytes IS NULL)
    OR (
      source_sha256 IS NOT NULL
      AND source_size_bytes IS NOT NULL
      AND source_sha256 ~ '^[0-9a-f]{64}$'
      AND source_size_bytes >= 0
    )
  );

CREATE TABLE IF NOT EXISTS hxy_material_scan_results (
  scan_result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id UUID NOT NULL,
  material_id UUID NOT NULL,
  job_id UUID NOT NULL REFERENCES hxy_material_parser_jobs(job_id) ON DELETE CASCADE,
  attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
  result_status TEXT NOT NULL CHECK (result_status IN ('clean', 'blocked')),
  engine TEXT NOT NULL CHECK (char_length(btrim(engine)) BETWEEN 1 AND 80),
  engine_version TEXT NOT NULL CHECK (char_length(btrim(engine_version)) BETWEEN 1 AND 80),
  signature TEXT CHECK (signature IS NULL OR char_length(signature) <= 160),
  source_sha256 CHAR(64) NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
  source_size_bytes BIGINT NOT NULL CHECK (source_size_bytes >= 0),
  scanned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (assignment_id, material_id)
    REFERENCES hxy_product_materials(assignment_id, material_id)
    ON DELETE CASCADE,
  UNIQUE (job_id, attempt_number),
  CHECK (
    (result_status = 'clean' AND signature IS NULL)
    OR (result_status = 'blocked' AND char_length(btrim(signature)) > 0)
  )
);

CREATE INDEX IF NOT EXISTS idx_hxy_material_scan_results_material
  ON hxy_material_scan_results (assignment_id, material_id, scanned_at DESC);

CREATE TABLE IF NOT EXISTS hxy_material_job_requeue_events (
  requeue_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  assignment_id UUID NOT NULL,
  material_id UUID NOT NULL,
  actor_assignment_id UUID NOT NULL,
  job_id UUID NOT NULL REFERENCES hxy_material_parser_jobs(job_id) ON DELETE RESTRICT,
  from_status TEXT NOT NULL CHECK (
    from_status IN ('missing', 'queued', 'running', 'retryable_failed', 'permanent_failed')
  ),
  target_job_type TEXT NOT NULL CHECK (target_job_type IN ('scan', 'parse')),
  reason TEXT NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 4 AND 500),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (organization_id, assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  FOREIGN KEY (organization_id, actor_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  FOREIGN KEY (assignment_id, material_id)
    REFERENCES hxy_product_materials(assignment_id, material_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_hxy_material_requeue_events_material
  ON hxy_material_job_requeue_events (
    organization_id,
    material_id,
    created_at DESC,
    requeue_event_id DESC
  );

DROP TRIGGER IF EXISTS trg_hxy_material_requeue_events_append_only
  ON hxy_material_job_requeue_events;
CREATE TRIGGER trg_hxy_material_requeue_events_append_only
BEFORE UPDATE OR DELETE ON hxy_material_job_requeue_events
FOR EACH ROW EXECUTE FUNCTION hxy_reject_operating_history_mutation();

DROP TRIGGER IF EXISTS trg_hxy_material_requeue_events_no_truncate
  ON hxy_material_job_requeue_events;
CREATE TRIGGER trg_hxy_material_requeue_events_no_truncate
BEFORE TRUNCATE ON hxy_material_job_requeue_events
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_operating_history_mutation();

UPDATE hxy_product_materials
SET scan_status = 'pending',
    updated_at = NOW()
WHERE scan_status = 'legacy_unscanned'
  AND status <> 'archived';

UPDATE hxy_material_job_attempts AS attempt
SET outcome = 'lost_lease',
    error_code = 'safety_scan_required',
    error_summary = 'file safety scan must complete before parsing',
    completed_at = NOW()
FROM hxy_material_parser_jobs AS job
JOIN hxy_product_materials AS material
  ON material.assignment_id = job.assignment_id
 AND material.material_id = job.material_id
WHERE attempt.job_id = job.job_id
  AND attempt.attempt_number = job.attempt_count
  AND attempt.outcome = 'running'
  AND job.job_type = 'parse'
  AND material.scan_status = 'pending';

UPDATE hxy_material_parser_jobs AS job
SET status = 'retryable_failed',
    available_at = NOW(),
    lease_owner = NULL,
    lease_expires_at = NULL,
    last_error_code = 'safety_scan_required',
    last_error_summary = 'file safety scan must complete before parsing',
    completed_at = NULL,
    updated_at = NOW()
FROM hxy_product_materials AS material
WHERE material.assignment_id = job.assignment_id
  AND material.material_id = job.material_id
  AND material.scan_status = 'pending'
  AND job.job_type = 'parse'
  AND job.status = 'running';

INSERT INTO hxy_material_parser_jobs (
  assignment_id,
  material_id,
  job_type,
  parser_strategy,
  status,
  max_attempts
)
SELECT material.assignment_id,
       material.material_id,
       'scan',
       'clamav',
       'queued',
       3
FROM hxy_product_materials AS material
WHERE material.scan_status = 'pending'
  AND material.status <> 'archived'
ON CONFLICT (material_id, job_type) DO NOTHING;
