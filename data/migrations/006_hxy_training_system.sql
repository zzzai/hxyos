CREATE TABLE IF NOT EXISTS hxy_training_sessions (
  session_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  employee_id TEXT NOT NULL DEFAULT '',
  employee_name TEXT NOT NULL DEFAULT '',
  store_id TEXT NOT NULL DEFAULT '',
  store_name TEXT NOT NULL DEFAULT '',
  training_item TEXT NOT NULL DEFAULT '',
  customer_question TEXT NOT NULL DEFAULT '',
  employee_answer TEXT NOT NULL DEFAULT '',
  scenario TEXT NOT NULL DEFAULT '门店员工培训',
  role TEXT NOT NULL DEFAULT '门店员工',
  score INTEGER NOT NULL DEFAULT 0 CHECK (score >= 0 AND score <= 100),
  level TEXT NOT NULL DEFAULT 'retrain' CHECK (level IN ('excellent', 'pass', 'retrain')),
  needs_retrain BOOLEAN NOT NULL DEFAULT FALSE,
  dimensions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  correction_points_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  follow_up_questions_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  retraining_task_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  answer_card_draft_json JSONB,
  review_task_id TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hxy_training_sessions_store_created
  ON hxy_training_sessions(store_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_training_sessions_employee_created
  ON hxy_training_sessions(employee_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_training_sessions_needs_retrain
  ON hxy_training_sessions(needs_retrain, created_at DESC);

