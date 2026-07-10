DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'uq_hxy_material_artifacts_activation_owner'
      AND conrelid = 'hxy_material_artifacts'::regclass
  ) THEN
    ALTER TABLE hxy_material_artifacts
      ADD CONSTRAINT uq_hxy_material_artifacts_activation_owner
      UNIQUE (artifact_id, assignment_id, material_id, artifact_type);
  END IF;
END
$$;

CREATE TABLE IF NOT EXISTS hxy_material_chunks (
  chunk_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id UUID NOT NULL,
  material_id UUID NOT NULL,
  artifact_id UUID NOT NULL,
  artifact_type TEXT NOT NULL DEFAULT 'normalized_markdown'
    CHECK (artifact_type = 'normalized_markdown'),
  chunk_index INTEGER NOT NULL CHECK (chunk_index >= 0),
  heading TEXT NOT NULL DEFAULT '' CHECK (char_length(heading) <= 300),
  content TEXT NOT NULL CHECK (
    char_length(btrim(content)) BETWEEN 1 AND 20000
  ),
  char_count INTEGER NOT NULL CHECK (char_count > 0),
  official_use_allowed BOOLEAN NOT NULL DEFAULT FALSE
    CHECK (official_use_allowed = FALSE),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (assignment_id, material_id)
    REFERENCES hxy_product_materials(assignment_id, material_id)
    ON DELETE CASCADE,
  FOREIGN KEY (artifact_id, assignment_id, material_id, artifact_type)
    REFERENCES hxy_material_artifacts(artifact_id, assignment_id, material_id, artifact_type)
    ON DELETE CASCADE,
  UNIQUE (artifact_id, chunk_index)
);

CREATE INDEX IF NOT EXISTS idx_hxy_material_chunks_assignment_material
  ON hxy_material_chunks (assignment_id, material_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_hxy_material_chunks_assignment_recent
  ON hxy_material_chunks (assignment_id, created_at DESC, material_id, chunk_index);

CREATE INDEX IF NOT EXISTS idx_hxy_material_chunks_content_trgm
  ON hxy_material_chunks USING GIN (content gin_trgm_ops);

CREATE TABLE IF NOT EXISTS hxy_product_answer_traces (
  trace_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id UUID NOT NULL REFERENCES hxy_role_assignments(assignment_id) ON DELETE CASCADE,
  conversation_id UUID NOT NULL,
  user_message_id UUID NOT NULL,
  assistant_message_id UUID NOT NULL UNIQUE,
  role TEXT NOT NULL CHECK (char_length(btrim(role)) BETWEEN 1 AND 80),
  intent TEXT NOT NULL DEFAULT 'unknown' CHECK (
    char_length(btrim(intent)) BETWEEN 1 AND 120
  ),
  retrieval_count INTEGER NOT NULL DEFAULT 0 CHECK (retrieval_count >= 0),
  private_material_count INTEGER NOT NULL DEFAULT 0 CHECK (
    private_material_count >= 0
  ),
  authority_card_hit BOOLEAN NOT NULL DEFAULT FALSE,
  model_name TEXT NOT NULL DEFAULT '' CHECK (char_length(model_name) <= 120),
  input_tokens INTEGER CHECK (input_tokens IS NULL OR input_tokens >= 0),
  output_tokens INTEGER CHECK (output_tokens IS NULL OR output_tokens >= 0),
  latency_ms INTEGER NOT NULL DEFAULT 0 CHECK (latency_ms >= 0),
  outcome TEXT NOT NULL CHECK (outcome IN ('succeeded', 'failed')),
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  FOREIGN KEY (assignment_id, conversation_id)
    REFERENCES hxy_product_conversations(assignment_id, conversation_id)
    ON DELETE CASCADE,
  FOREIGN KEY (assignment_id, conversation_id, user_message_id)
    REFERENCES hxy_product_messages(assignment_id, conversation_id, message_id)
    ON DELETE CASCADE,
  FOREIGN KEY (assignment_id, conversation_id, assistant_message_id)
    REFERENCES hxy_product_messages(assignment_id, conversation_id, message_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hxy_product_answer_traces_assignment_recent
  ON hxy_product_answer_traces (assignment_id, created_at DESC, trace_id DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_product_answer_traces_intent_recent
  ON hxy_product_answer_traces (intent, created_at DESC);
