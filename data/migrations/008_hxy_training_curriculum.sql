CREATE TABLE IF NOT EXISTS hxy_training_manager_acceptances (
  acceptance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id TEXT NOT NULL DEFAULT '',
  manager_id TEXT NOT NULL DEFAULT '',
  manager_name TEXT NOT NULL DEFAULT '',
  accepted BOOLEAN NOT NULL DEFAULT FALSE,
  score INTEGER NOT NULL DEFAULT 0 CHECK (score >= 0 AND score <= 100),
  note TEXT NOT NULL DEFAULT '',
  operating_metric_links_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hxy_training_capability_levels (
  capability_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id TEXT NOT NULL DEFAULT '',
  store_id TEXT NOT NULL DEFAULT '',
  training_item TEXT NOT NULL DEFAULT '',
  current_level TEXT NOT NULL DEFAULT 'newbie',
  accepted_count INTEGER NOT NULL DEFAULT 0,
  last_acceptance_id TEXT NOT NULL DEFAULT '',
  acceptance_evidence_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (employee_id, store_id, training_item)
);

ALTER TABLE hxy_training_sessions
  ADD COLUMN IF NOT EXISTS capability_profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS adaptive_retrain_plan_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS operating_metric_links_json JSONB NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_hxy_training_acceptances_session
  ON hxy_training_manager_acceptances(session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_training_acceptances_manager
  ON hxy_training_manager_acceptances(manager_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_training_capability_levels_employee
  ON hxy_training_capability_levels(employee_id, store_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_training_capability_levels_store
  ON hxy_training_capability_levels(store_id, updated_at DESC);
