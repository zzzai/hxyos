CREATE TABLE IF NOT EXISTS hxy_knowledge_answer_runs (
  answer_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question TEXT NOT NULL,
  normalized_query TEXT NOT NULL DEFAULT '',
  intent TEXT NOT NULL DEFAULT 'unknown',
  audience TEXT NOT NULL DEFAULT 'general',
  answer TEXT NOT NULL DEFAULT '',
  confidence TEXT NOT NULL DEFAULT 'low' CHECK (confidence IN ('high', 'medium', 'low')),
  needs_review BOOLEAN NOT NULL DEFAULT TRUE,
  evidence_count INTEGER NOT NULL DEFAULT 0,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hxy_knowledge_feedback (
  feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  answer_id UUID REFERENCES hxy_knowledge_answer_runs(answer_id) ON DELETE SET NULL,
  question TEXT NOT NULL DEFAULT '',
  rating TEXT NOT NULL CHECK (rating IN ('useful', 'incorrect', 'needs_work')),
  note TEXT NOT NULL DEFAULT '',
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_answer_runs_intent ON hxy_knowledge_answer_runs(intent);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_answer_runs_created_at ON hxy_knowledge_answer_runs(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_feedback_answer_id ON hxy_knowledge_feedback(answer_id);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_feedback_rating ON hxy_knowledge_feedback(rating);
