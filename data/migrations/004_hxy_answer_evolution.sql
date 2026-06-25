CREATE TABLE IF NOT EXISTS hxy_knowledge_review_tasks (
  task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  answer_id UUID REFERENCES hxy_knowledge_answer_runs(answer_id) ON DELETE SET NULL,
  feedback_id UUID REFERENCES hxy_knowledge_feedback(feedback_id) ON DELETE SET NULL,
  question TEXT NOT NULL DEFAULT '',
  intent TEXT NOT NULL DEFAULT 'unknown',
  reason TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'resolved', 'dismissed')),
  priority TEXT NOT NULL DEFAULT 'medium' CHECK (priority IN ('high', 'medium', 'low')),
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  resolved_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS hxy_knowledge_answer_cards (
  card_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question_pattern TEXT NOT NULL,
  intent TEXT NOT NULL DEFAULT 'unknown',
  audience TEXT NOT NULL DEFAULT 'general',
  answer TEXT NOT NULL,
  reasoning JSONB NOT NULL DEFAULT '[]'::jsonb,
  evidence JSONB NOT NULL DEFAULT '[]'::jsonb,
  corrections JSONB NOT NULL DEFAULT '[]'::jsonb,
  next_actions JSONB NOT NULL DEFAULT '[]'::jsonb,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'approved', 'archived')),
  source_answer_id UUID REFERENCES hxy_knowledge_answer_runs(answer_id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_review_tasks_status ON hxy_knowledge_review_tasks(status, priority, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_review_tasks_intent ON hxy_knowledge_review_tasks(intent);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_answer_cards_status_intent ON hxy_knowledge_answer_cards(status, intent);
CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_answer_cards_question_trgm ON hxy_knowledge_answer_cards USING GIN(question_pattern gin_trgm_ops);
