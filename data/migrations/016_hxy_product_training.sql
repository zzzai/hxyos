CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_role_assignments_organization_assignment
  ON hxy_role_assignments (organization_id, assignment_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_role_assignments_organization_store_assignment
  ON hxy_role_assignments (organization_id, store_id, assignment_id);

ALTER TABLE hxy_product_tasks
  ADD COLUMN IF NOT EXISTS parent_task_id UUID;

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_product_tasks_organization_store_task
  ON hxy_product_tasks (organization_id, store_id, task_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_hxy_product_tasks_parent_store'
      AND conrelid = 'hxy_product_tasks'::regclass
  ) THEN
    ALTER TABLE hxy_product_tasks
      ADD CONSTRAINT fk_hxy_product_tasks_parent_store
      FOREIGN KEY (organization_id, store_id, parent_task_id)
      REFERENCES hxy_product_tasks(organization_id, store_id, task_id)
      ON DELETE RESTRICT;
  END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS hxy_product_training_sessions (
  training_session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT NOT NULL,
  assignment_id UUID NOT NULL,
  customer_question TEXT NOT NULL CHECK (
    char_length(btrim(customer_question)) BETWEEN 1 AND 1000
  ),
  employee_answer TEXT NOT NULL CHECK (
    char_length(btrim(employee_answer)) BETWEEN 1 AND 4000
  ),
  score INTEGER NOT NULL CHECK (score BETWEEN 0 AND 100),
  level TEXT NOT NULL CHECK (char_length(btrim(level)) BETWEEN 1 AND 80),
  needs_retrain BOOLEAN NOT NULL,
  standard_script TEXT NOT NULL DEFAULT '' CHECK (char_length(standard_script) <= 4000),
  correction_points JSONB NOT NULL DEFAULT '[]'::jsonb CHECK (
    jsonb_typeof(correction_points) = 'array'
  ),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_hxy_product_training_organization_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_product_training_assignment_organization
    FOREIGN KEY (organization_id, assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_product_training_assignment_store
    FOREIGN KEY (organization_id, store_id, assignment_id)
    REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_hxy_product_training_assignment_recent
  ON hxy_product_training_sessions (assignment_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_product_training_store_recent
  ON hxy_product_training_sessions (organization_id, store_id, created_at DESC);

CREATE OR REPLACE FUNCTION hxy_reject_product_training_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'hxy_product_training_sessions is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_product_training_append_only
  ON hxy_product_training_sessions;

CREATE TRIGGER trg_hxy_product_training_append_only
  BEFORE UPDATE OR DELETE ON hxy_product_training_sessions
  FOR EACH ROW EXECUTE FUNCTION hxy_reject_product_training_mutation();

DROP TRIGGER IF EXISTS trg_hxy_product_training_no_truncate
  ON hxy_product_training_sessions;

CREATE TRIGGER trg_hxy_product_training_no_truncate
  BEFORE TRUNCATE ON hxy_product_training_sessions
  FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_product_training_mutation();
