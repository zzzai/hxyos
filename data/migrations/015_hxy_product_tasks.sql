CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_role_assignments_organization_assignment
  ON hxy_role_assignments (organization_id, assignment_id);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_role_assignments_organization_store_assignment
  ON hxy_role_assignments (organization_id, store_id, assignment_id);

CREATE TABLE IF NOT EXISTS hxy_product_tasks (
  task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT REFERENCES stores(store_id) ON DELETE RESTRICT,
  creator_assignment_id UUID NOT NULL REFERENCES hxy_role_assignments(assignment_id) ON DELETE RESTRICT,
  assignee_assignment_id UUID REFERENCES hxy_role_assignments(assignment_id) ON DELETE RESTRICT,
  source_conversation_id UUID,
  source_message_id UUID,
  title TEXT NOT NULL CHECK (char_length(btrim(title)) BETWEEN 1 AND 160),
  details TEXT NOT NULL DEFAULT '' CHECK (char_length(details) <= 5000),
  priority TEXT NOT NULL DEFAULT 'normal' CHECK (
    priority IN ('low', 'normal', 'high', 'urgent')
  ),
  visibility TEXT NOT NULL DEFAULT 'assignee' CHECK (
    visibility IN ('assignee', 'store')
  ),
  status TEXT NOT NULL DEFAULT 'open' CHECK (
    status IN ('open', 'in_progress', 'completed', 'cancelled')
  ),
  result TEXT CHECK (result IS NULL OR char_length(result) <= 5000),
  due_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT chk_hxy_product_tasks_visibility_scope CHECK (
    (visibility = 'assignee' AND assignee_assignment_id IS NOT NULL)
    OR (visibility = 'store' AND store_id IS NOT NULL)
  ),
  CONSTRAINT fk_hxy_product_tasks_organization_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_product_tasks_creator_organization
    FOREIGN KEY (organization_id, creator_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_product_tasks_assignee_organization
    FOREIGN KEY (organization_id, assignee_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_product_tasks_assignee_store
    FOREIGN KEY (organization_id, store_id, assignee_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_product_tasks_source_conversation
    FOREIGN KEY (creator_assignment_id, source_conversation_id)
    REFERENCES hxy_product_conversations(assignment_id, conversation_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_product_tasks_source_message
    FOREIGN KEY (creator_assignment_id, source_conversation_id, source_message_id)
    REFERENCES hxy_product_messages(assignment_id, conversation_id, message_id)
    ON DELETE RESTRICT,
  CONSTRAINT chk_hxy_product_tasks_completion CHECK (
    (status = 'completed' AND completed_at IS NOT NULL)
    OR (status <> 'completed' AND completed_at IS NULL)
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_product_tasks_organization_task
  ON hxy_product_tasks (organization_id, task_id);

CREATE TABLE IF NOT EXISTS hxy_product_task_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  task_id UUID NOT NULL,
  actor_assignment_id UUID NOT NULL,
  event_type TEXT NOT NULL CHECK (
    event_type IN ('created', 'in_progress', 'completed', 'cancelled')
  ),
  payload JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_hxy_product_task_events_task_organization
    FOREIGN KEY (organization_id, task_id)
    REFERENCES hxy_product_tasks(organization_id, task_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_product_task_events_actor_organization
    FOREIGN KEY (organization_id, actor_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION hxy_reject_task_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'hxy_product_task_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_product_task_events_append_only
  ON hxy_product_task_events;

CREATE TRIGGER trg_hxy_product_task_events_append_only
  BEFORE UPDATE OR DELETE ON hxy_product_task_events
  FOR EACH ROW EXECUTE FUNCTION hxy_reject_task_event_mutation();

DROP TRIGGER IF EXISTS trg_hxy_product_task_events_no_truncate
  ON hxy_product_task_events;

CREATE TRIGGER trg_hxy_product_task_events_no_truncate
  BEFORE TRUNCATE ON hxy_product_task_events
  FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_task_event_mutation();

CREATE INDEX IF NOT EXISTS idx_hxy_product_tasks_organization_recent
  ON hxy_product_tasks (organization_id, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_product_tasks_assignee_active
  ON hxy_product_tasks (assignee_assignment_id, priority, updated_at DESC)
  WHERE status IN ('open', 'in_progress');

CREATE INDEX IF NOT EXISTS idx_hxy_product_tasks_store_active
  ON hxy_product_tasks (organization_id, store_id, priority, updated_at DESC)
  WHERE visibility = 'store' AND status IN ('open', 'in_progress');

CREATE INDEX IF NOT EXISTS idx_hxy_product_task_events_task_created
  ON hxy_product_task_events (task_id, created_at, event_id);
