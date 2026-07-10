CREATE TABLE IF NOT EXISTS hxy_product_conversations (
  conversation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id UUID NOT NULL REFERENCES hxy_role_assignments(assignment_id) ON DELETE CASCADE,
  title TEXT NOT NULL DEFAULT '新对话' CHECK (
    char_length(btrim(title)) BETWEEN 1 AND 120
  ),
  message_count INTEGER NOT NULL DEFAULT 0 CHECK (message_count >= 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  last_message_at TIMESTAMPTZ,
  UNIQUE (assignment_id, conversation_id)
);

CREATE TABLE IF NOT EXISTS hxy_product_messages (
  message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id UUID NOT NULL REFERENCES hxy_role_assignments(assignment_id) ON DELETE CASCADE,
  conversation_id UUID NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL CHECK (
    char_length(btrim(content)) BETWEEN 1 AND 50000
  ),
  client_message_id UUID,
  reply_to_message_id UUID,
  answer_id UUID REFERENCES hxy_knowledge_answer_runs(answer_id) ON DELETE SET NULL,
  answer_payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  generation_status TEXT NOT NULL DEFAULT 'completed' CHECK (
    generation_status IN ('pending', 'processing', 'completed', 'failed')
  ),
  generation_started_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_hxy_product_messages_conversation
    FOREIGN KEY (assignment_id, conversation_id)
    REFERENCES hxy_product_conversations(assignment_id, conversation_id)
    ON DELETE CASCADE,
  CONSTRAINT chk_hxy_product_messages_role_shape CHECK (
    (
      role = 'user'
      AND client_message_id IS NOT NULL
      AND reply_to_message_id IS NULL
      AND answer_id IS NULL
    )
    OR
    (
      role = 'assistant'
      AND client_message_id IS NULL
      AND reply_to_message_id IS NOT NULL
      AND generation_status = 'completed'
    )
  ),
  UNIQUE (assignment_id, conversation_id, message_id),
  UNIQUE (assignment_id, client_message_id),
  UNIQUE (assignment_id, conversation_id, reply_to_message_id),
  CONSTRAINT fk_hxy_product_messages_reply
    FOREIGN KEY (assignment_id, conversation_id, reply_to_message_id)
    REFERENCES hxy_product_messages(assignment_id, conversation_id, message_id)
    ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_hxy_product_conversations_assignment_recent
  ON hxy_product_conversations (assignment_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_product_messages_conversation_created
  ON hxy_product_messages (assignment_id, conversation_id, created_at, message_id);

CREATE INDEX IF NOT EXISTS idx_hxy_product_messages_generation_status
  ON hxy_product_messages (assignment_id, generation_status, generation_started_at)
  WHERE role = 'user' AND generation_status IN ('processing', 'failed');

CREATE INDEX IF NOT EXISTS idx_hxy_product_messages_answer_id
  ON hxy_product_messages (answer_id)
  WHERE answer_id IS NOT NULL;
