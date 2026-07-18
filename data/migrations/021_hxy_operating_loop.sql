CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_governance_profiles_event_snapshot
  ON hxy_governance_profiles (
    organization_id,
    profile_id,
    profile_version
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_store_operating_relationships_event_snapshot
  ON hxy_store_operating_relationships (
    organization_id,
    store_id,
    relationship_id,
    relationship_version,
    governance_profile_id
  );

CREATE TABLE IF NOT EXISTS hxy_channel_identity_bindings (
  binding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  channel TEXT NOT NULL CHECK (channel IN ('feishu', 'pwa', 'admin', 'api')),
  channel_tenant_id TEXT NOT NULL
    CHECK (char_length(btrim(channel_tenant_id)) BETWEEN 1 AND 160),
  channel_user_id TEXT NOT NULL
    CHECK (char_length(btrim(channel_user_id)) BETWEEN 1 AND 160),
  assignment_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'revoked')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  revoked_at TIMESTAMPTZ,
  UNIQUE (organization_id, binding_id),
  UNIQUE (organization_id, channel, channel_tenant_id, channel_user_id),
  CONSTRAINT chk_hxy_channel_identity_bindings_revocation CHECK (
    (status = 'active' AND revoked_at IS NULL)
    OR (status = 'revoked' AND revoked_at IS NOT NULL)
  ),
  CONSTRAINT fk_hxy_channel_identity_bindings_assignment
    FOREIGN KEY (organization_id, assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_inbound_envelopes (
  envelope_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  channel TEXT NOT NULL CHECK (channel IN ('feishu', 'pwa', 'admin', 'api')),
  channel_tenant_id TEXT NOT NULL DEFAULT ''
    CHECK (char_length(channel_tenant_id) <= 160),
  channel_message_id TEXT NOT NULL DEFAULT ''
    CHECK (char_length(channel_message_id) <= 240),
  channel_thread_id TEXT NOT NULL DEFAULT ''
    CHECK (char_length(channel_thread_id) <= 240),
  sender_user_id TEXT NOT NULL DEFAULT '' CHECK (char_length(sender_user_id) <= 160),
  sender_assignment_id UUID,
  store_id TEXT,
  intent_hint TEXT NOT NULL DEFAULT '' CHECK (char_length(intent_hint) <= 100),
  raw_payload JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(raw_payload) = 'object'),
  raw_text TEXT NOT NULL DEFAULT '' CHECK (char_length(raw_text) <= 20000),
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  idempotency_key TEXT NOT NULL
    CHECK (char_length(btrim(idempotency_key)) BETWEEN 1 AND 240),
  visibility_scope JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(visibility_scope) = 'object'),
  status TEXT NOT NULL DEFAULT 'received'
    CHECK (status IN ('received', 'queued', 'processed', 'needs_attention', 'rejected')),
  processed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, envelope_id),
  UNIQUE (organization_id, channel, idempotency_key),
  CONSTRAINT chk_hxy_inbound_envelopes_processed_at CHECK (
    (status = 'processed' AND processed_at IS NOT NULL)
    OR (status <> 'processed' AND processed_at IS NULL)
  ),
  CONSTRAINT fk_hxy_inbound_envelopes_sender
    FOREIGN KEY (organization_id, sender_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_inbound_envelopes_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_ai_proposals (
  proposal_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  source_envelope_id UUID NOT NULL,
  target_type TEXT NOT NULL DEFAULT 'operating_event'
    CHECK (target_type IN ('operating_event', 'task', 'knowledge_candidate', 'content_draft')),
  target_id UUID,
  proposal_type TEXT NOT NULL
    CHECK (char_length(btrim(proposal_type)) BETWEEN 2 AND 100),
  payload JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
  confidence NUMERIC(5, 4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  risk_level TEXT NOT NULL CHECK (risk_level IN ('low', 'medium', 'high', 'critical')),
  model_provider TEXT NOT NULL CHECK (char_length(btrim(model_provider)) BETWEEN 1 AND 100),
  model_name TEXT NOT NULL CHECK (char_length(btrim(model_name)) BETWEEN 1 AND 160),
  prompt_version TEXT NOT NULL CHECK (char_length(btrim(prompt_version)) BETWEEN 1 AND 100),
  input_hash CHAR(64) NOT NULL CHECK (input_hash ~ '^[0-9a-f]{64}$'),
  status TEXT NOT NULL DEFAULT 'proposed'
    CHECK (status IN ('proposed', 'auto_accepted', 'accepted', 'rejected', 'superseded')),
  decided_at TIMESTAMPTZ,
  decided_by_assignment_id UUID,
  decision_policy_version TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, proposal_id),
  CONSTRAINT chk_hxy_ai_proposals_decision CHECK (
    (status = 'proposed' AND decided_at IS NULL
      AND decided_by_assignment_id IS NULL AND decision_policy_version IS NULL)
    OR
    (status <> 'proposed' AND decided_at IS NOT NULL
      AND (decided_by_assignment_id IS NOT NULL
        OR (decision_policy_version IS NOT NULL
          AND char_length(btrim(decision_policy_version)) BETWEEN 1 AND 100)))
  ),
  CONSTRAINT fk_hxy_ai_proposals_source_envelope
    FOREIGN KEY (organization_id, source_envelope_id)
    REFERENCES hxy_inbound_envelopes(organization_id, envelope_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_ai_proposals_decider
    FOREIGN KEY (organization_id, decided_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_outbox_messages (
  outbox_message_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  topic TEXT NOT NULL CHECK (char_length(btrim(topic)) BETWEEN 3 AND 160),
  aggregate_type TEXT NOT NULL CHECK (char_length(btrim(aggregate_type)) BETWEEN 2 AND 100),
  aggregate_id UUID NOT NULL,
  payload JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(payload) = 'object'),
  idempotency_key TEXT NOT NULL
    CHECK (char_length(btrim(idempotency_key)) BETWEEN 1 AND 240),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (
    status IN ('pending', 'leased', 'retryable_failed', 'succeeded', 'dead_letter')
  ),
  attempt_count INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
  max_attempts INTEGER NOT NULL DEFAULT 5 CHECK (max_attempts BETWEEN 1 AND 100),
  available_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  lease_owner TEXT CHECK (lease_owner IS NULL OR char_length(btrim(lease_owner)) BETWEEN 1 AND 160),
  lease_expires_at TIMESTAMPTZ,
  last_error_code TEXT CHECK (last_error_code IS NULL OR char_length(last_error_code) <= 100),
  last_error_summary TEXT CHECK (last_error_summary IS NULL OR char_length(last_error_summary) <= 2000),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ,
  UNIQUE (organization_id, outbox_message_id),
  UNIQUE (organization_id, topic, idempotency_key),
  CONSTRAINT chk_hxy_outbox_messages_attempt_limit CHECK (attempt_count <= max_attempts),
  CONSTRAINT chk_hxy_outbox_messages_lease CHECK (
    (status = 'leased' AND lease_owner IS NOT NULL AND lease_expires_at IS NOT NULL)
    OR (status <> 'leased' AND lease_owner IS NULL AND lease_expires_at IS NULL)
  ),
  CONSTRAINT chk_hxy_outbox_messages_completion CHECK (
    (status IN ('succeeded', 'dead_letter') AND completed_at IS NOT NULL)
    OR (status NOT IN ('succeeded', 'dead_letter') AND completed_at IS NULL)
  )
);

CREATE TABLE IF NOT EXISTS hxy_outbox_attempts (
  attempt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  outbox_message_id UUID NOT NULL,
  attempt_number INTEGER NOT NULL CHECK (attempt_number > 0),
  worker_id TEXT NOT NULL CHECK (char_length(btrim(worker_id)) BETWEEN 1 AND 160),
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  outcome TEXT NOT NULL DEFAULT 'leased'
    CHECK (outcome IN ('leased', 'succeeded', 'retryable_failed', 'dead_letter')),
  error_code TEXT CHECK (error_code IS NULL OR char_length(error_code) <= 100),
  error_summary TEXT CHECK (error_summary IS NULL OR char_length(error_summary) <= 2000),
  result JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(result) = 'object'),
  UNIQUE (organization_id, outbox_message_id, attempt_number, outcome),
  CONSTRAINT chk_hxy_outbox_attempts_finished CHECK (
    (outcome = 'leased' AND finished_at IS NULL)
    OR (outcome <> 'leased' AND finished_at IS NOT NULL)
  ),
  CONSTRAINT fk_hxy_outbox_attempts_message
    FOREIGN KEY (organization_id, outbox_message_id)
    REFERENCES hxy_outbox_messages(organization_id, outbox_message_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_operating_events (
  operating_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT NOT NULL,
  event_type TEXT NOT NULL CHECK (char_length(btrim(event_type)) BETWEEN 2 AND 100),
  title TEXT NOT NULL CHECK (char_length(btrim(title)) BETWEEN 1 AND 160),
  description TEXT NOT NULL DEFAULT '' CHECK (char_length(description) <= 10000),
  location TEXT NOT NULL DEFAULT '' CHECK (char_length(location) <= 240),
  impact TEXT NOT NULL DEFAULT '' CHECK (char_length(impact) <= 2000),
  acceptance_criteria TEXT NOT NULL DEFAULT '' CHECK (char_length(acceptance_criteria) <= 3000),
  source_envelope_id UUID NOT NULL,
  source_proposal_id UUID,
  reporter_assignment_id UUID NOT NULL,
  owner_assignment_id UUID,
  severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
  status TEXT NOT NULL DEFAULT 'open'
    CHECK (status IN ('open', 'active', 'resolved', 'closed', 'cancelled')),
  occurred_at TIMESTAMPTZ NOT NULL,
  detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  due_at TIMESTAMPTZ,
  closed_at TIMESTAMPTZ,
  policy_version TEXT NOT NULL CHECK (char_length(btrim(policy_version)) BETWEEN 1 AND 100),
  store_operating_relationship_id UUID NOT NULL,
  store_operating_relationship_version INTEGER NOT NULL CHECK (
    store_operating_relationship_version > 0
  ),
  governance_profile_id UUID NOT NULL,
  governance_profile_version INTEGER NOT NULL CHECK (governance_profile_version > 0),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, operating_event_id),
  UNIQUE (organization_id, store_id, operating_event_id),
  CONSTRAINT chk_hxy_operating_events_closed_at CHECK (
    (status IN ('closed', 'cancelled') AND closed_at IS NOT NULL)
    OR (status NOT IN ('closed', 'cancelled') AND closed_at IS NULL)
  ),
  CONSTRAINT fk_hxy_operating_events_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_events_source_envelope
    FOREIGN KEY (organization_id, source_envelope_id)
    REFERENCES hxy_inbound_envelopes(organization_id, envelope_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_events_source_proposal
    FOREIGN KEY (organization_id, source_proposal_id)
    REFERENCES hxy_ai_proposals(organization_id, proposal_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_events_reporter_store
    FOREIGN KEY (organization_id, store_id, reporter_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_events_owner
    FOREIGN KEY (organization_id, owner_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_events_relationship_snapshot
    FOREIGN KEY (
      organization_id,
      store_id,
      store_operating_relationship_id,
      store_operating_relationship_version,
      governance_profile_id
    )
    REFERENCES hxy_store_operating_relationships(
      organization_id,
      store_id,
      relationship_id,
      relationship_version,
      governance_profile_id
    )
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_events_governance_snapshot
    FOREIGN KEY (organization_id, governance_profile_id, governance_profile_version)
    REFERENCES hxy_governance_profiles(organization_id, profile_id, profile_version)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_workflow_instances (
  workflow_instance_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT NOT NULL,
  operating_event_id UUID NOT NULL,
  workflow_type TEXT NOT NULL CHECK (char_length(btrim(workflow_type)) BETWEEN 2 AND 100),
  workflow_version INTEGER NOT NULL CHECK (workflow_version > 0),
  status TEXT NOT NULL DEFAULT 'pending'
    CHECK (status IN ('pending', 'running', 'waiting', 'completed', 'cancelled', 'failed')),
  current_state TEXT NOT NULL CHECK (char_length(btrim(current_state)) BETWEEN 1 AND 100),
  started_at TIMESTAMPTZ,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, workflow_instance_id),
  UNIQUE (organization_id, store_id, workflow_instance_id),
  CONSTRAINT chk_hxy_workflow_instances_completion CHECK (
    (status IN ('completed', 'cancelled', 'failed') AND completed_at IS NOT NULL)
    OR (status NOT IN ('completed', 'cancelled', 'failed') AND completed_at IS NULL)
  ),
  CONSTRAINT fk_hxy_workflow_instances_event
    FOREIGN KEY (organization_id, store_id, operating_event_id)
    REFERENCES hxy_operating_events(organization_id, store_id, operating_event_id)
    ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_workflow_instances_active
  ON hxy_workflow_instances (
    organization_id,
    operating_event_id,
    workflow_type,
    workflow_version
  )
  WHERE status IN ('pending', 'running', 'waiting');

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_workflow_instances_event_instance
  ON hxy_workflow_instances (
    organization_id,
    store_id,
    operating_event_id,
    workflow_instance_id
  );

CREATE TABLE IF NOT EXISTS hxy_operating_evidence (
  evidence_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT NOT NULL,
  operating_event_id UUID NOT NULL,
  workflow_instance_id UUID,
  task_id UUID,
  evidence_type TEXT NOT NULL CHECK (
    evidence_type IN ('photo', 'audio', 'video', 'document', 'text', 'system_record')
  ),
  source_asset_id UUID NOT NULL,
  statement TEXT NOT NULL DEFAULT '' CHECK (char_length(statement) <= 5000),
  metadata JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(metadata) = 'object'),
  visibility_scope JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(visibility_scope) = 'object'),
  created_by_assignment_id UUID NOT NULL,
  supersedes_evidence_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, evidence_id),
  CONSTRAINT chk_hxy_operating_evidence_supersedes CHECK (
    supersedes_evidence_id IS NULL OR supersedes_evidence_id <> evidence_id
  ),
  CONSTRAINT fk_hxy_operating_evidence_event
    FOREIGN KEY (organization_id, store_id, operating_event_id)
    REFERENCES hxy_operating_events(organization_id, store_id, operating_event_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_evidence_workflow
    FOREIGN KEY (organization_id, store_id, workflow_instance_id)
    REFERENCES hxy_workflow_instances(organization_id, store_id, workflow_instance_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_evidence_task
    FOREIGN KEY (organization_id, store_id, task_id)
    REFERENCES hxy_product_tasks(organization_id, store_id, task_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_evidence_source_asset
    FOREIGN KEY (organization_id, source_asset_id)
    REFERENCES hxy_product_materials(organization_id, material_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_evidence_creator
    FOREIGN KEY (organization_id, created_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_operating_evidence_supersedes
    FOREIGN KEY (organization_id, supersedes_evidence_id)
    REFERENCES hxy_operating_evidence(organization_id, evidence_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_state_transitions (
  transition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT,
  aggregate_type TEXT NOT NULL CHECK (
    aggregate_type IN ('operating_event', 'workflow_instance', 'task', 'ai_proposal')
  ),
  aggregate_id UUID NOT NULL,
  from_state TEXT CHECK (from_state IS NULL OR char_length(from_state) <= 100),
  to_state TEXT NOT NULL CHECK (char_length(btrim(to_state)) BETWEEN 1 AND 100),
  command_type TEXT NOT NULL CHECK (char_length(btrim(command_type)) BETWEEN 1 AND 100),
  actor_type TEXT NOT NULL CHECK (actor_type IN ('user', 'policy', 'system')),
  actor_assignment_id UUID,
  actor_reference TEXT,
  reason TEXT NOT NULL DEFAULT '' CHECK (char_length(reason) <= 2000),
  policy_version TEXT CHECK (policy_version IS NULL OR char_length(policy_version) <= 100),
  occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  correlation_id UUID NOT NULL DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, transition_id),
  CONSTRAINT chk_hxy_state_transitions_actor CHECK (
    (actor_type = 'user' AND actor_assignment_id IS NOT NULL AND actor_reference IS NULL)
    OR
    (actor_type IN ('policy', 'system') AND actor_assignment_id IS NULL
      AND actor_reference IS NOT NULL
      AND char_length(btrim(actor_reference)) BETWEEN 1 AND 160)
  ),
  CONSTRAINT fk_hxy_state_transitions_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_state_transitions_actor
    FOREIGN KEY (organization_id, actor_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_metric_definitions_fact_snapshot
  ON hxy_metric_definitions (
    organization_id,
    metric_definition_id,
    metric_version,
    metric_key
  );

CREATE TABLE IF NOT EXISTS hxy_metric_facts (
  metric_fact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT,
  metric_definition_id UUID NOT NULL,
  metric_definition_version INTEGER NOT NULL CHECK (metric_definition_version > 0),
  metric_key TEXT NOT NULL CHECK (char_length(btrim(metric_key)) BETWEEN 2 AND 100),
  subject_type TEXT NOT NULL CHECK (char_length(btrim(subject_type)) BETWEEN 2 AND 100),
  subject_id UUID NOT NULL,
  value_numeric NUMERIC,
  value_text TEXT,
  unit TEXT NOT NULL DEFAULT '' CHECK (char_length(unit) <= 40),
  window_start TIMESTAMPTZ,
  window_end TIMESTAMPTZ,
  derived_from_transition_ids UUID[] NOT NULL DEFAULT '{}',
  source_snapshot_ids UUID[] NOT NULL DEFAULT '{}',
  calculation_version TEXT NOT NULL
    CHECK (char_length(btrim(calculation_version)) BETWEEN 1 AND 100),
  calculated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, metric_fact_id),
  CONSTRAINT chk_hxy_metric_facts_value CHECK (
    (value_numeric IS NOT NULL AND value_text IS NULL)
    OR (value_numeric IS NULL AND value_text IS NOT NULL)
  ),
  CONSTRAINT chk_hxy_metric_facts_window CHECK (
    window_end IS NULL OR window_start IS NULL OR window_end >= window_start
  ),
  CONSTRAINT chk_hxy_metric_facts_lineage CHECK (
    cardinality(derived_from_transition_ids) > 0 OR cardinality(source_snapshot_ids) > 0
  ),
  CONSTRAINT fk_hxy_metric_facts_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_metric_facts_definition
    FOREIGN KEY (
      organization_id,
      metric_definition_id,
      metric_definition_version,
      metric_key
    )
    REFERENCES hxy_metric_definitions(
      organization_id,
      metric_definition_id,
      metric_version,
      metric_key
    )
    ON DELETE RESTRICT
);

ALTER TABLE hxy_product_tasks
  ADD COLUMN IF NOT EXISTS operating_event_id UUID;

ALTER TABLE hxy_product_tasks
  ADD COLUMN IF NOT EXISTS workflow_instance_id UUID;

ALTER TABLE hxy_product_tasks
  ADD COLUMN IF NOT EXISTS task_type TEXT NOT NULL DEFAULT 'general'
    CHECK (char_length(btrim(task_type)) BETWEEN 1 AND 100);

ALTER TABLE hxy_product_tasks
  ADD COLUMN IF NOT EXISTS submitted_at TIMESTAMPTZ;

ALTER TABLE hxy_product_tasks
  ADD COLUMN IF NOT EXISTS accepted_at TIMESTAMPTZ;

ALTER TABLE hxy_product_tasks
  ADD COLUMN IF NOT EXISTS acceptance_assignment_id UUID;

ALTER TABLE hxy_product_tasks
  ADD COLUMN IF NOT EXISTS external_responsible_name TEXT
    CHECK (external_responsible_name IS NULL OR char_length(external_responsible_name) <= 160);

ALTER TABLE hxy_product_tasks
  DROP CONSTRAINT IF EXISTS hxy_product_tasks_status_check;

ALTER TABLE hxy_product_tasks
  ADD CONSTRAINT hxy_product_tasks_status_check CHECK (
    status IN (
      'open',
      'assigned',
      'in_progress',
      'submitted',
      'accepted',
      'rework',
      'cancelled',
      'completed'
    )
  );

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'fk_hxy_product_tasks_operating_event'
      AND conrelid = 'hxy_product_tasks'::regclass
  ) THEN
    ALTER TABLE hxy_product_tasks
      ADD CONSTRAINT fk_hxy_product_tasks_operating_event
      FOREIGN KEY (organization_id, store_id, operating_event_id)
      REFERENCES hxy_operating_events(organization_id, store_id, operating_event_id)
      ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'fk_hxy_product_tasks_workflow_event'
      AND conrelid = 'hxy_product_tasks'::regclass
  ) THEN
    ALTER TABLE hxy_product_tasks
      ADD CONSTRAINT fk_hxy_product_tasks_workflow_event
      FOREIGN KEY (
        organization_id,
        store_id,
        operating_event_id,
        workflow_instance_id
      )
      REFERENCES hxy_workflow_instances(
        organization_id,
        store_id,
        operating_event_id,
        workflow_instance_id
      )
      ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'fk_hxy_product_tasks_workflow_instance'
      AND conrelid = 'hxy_product_tasks'::regclass
  ) THEN
    ALTER TABLE hxy_product_tasks
      ADD CONSTRAINT fk_hxy_product_tasks_workflow_instance
      FOREIGN KEY (organization_id, store_id, workflow_instance_id)
      REFERENCES hxy_workflow_instances(organization_id, store_id, workflow_instance_id)
      ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'fk_hxy_product_tasks_acceptance_assignment'
      AND conrelid = 'hxy_product_tasks'::regclass
  ) THEN
    ALTER TABLE hxy_product_tasks
      ADD CONSTRAINT fk_hxy_product_tasks_acceptance_assignment
      FOREIGN KEY (organization_id, acceptance_assignment_id)
      REFERENCES hxy_role_assignments(organization_id, assignment_id)
      ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'chk_hxy_product_tasks_operating_acceptance'
      AND conrelid = 'hxy_product_tasks'::regclass
  ) THEN
    ALTER TABLE hxy_product_tasks
      ADD CONSTRAINT chk_hxy_product_tasks_operating_acceptance CHECK (
        (status = 'submitted' AND submitted_at IS NOT NULL AND accepted_at IS NULL)
        OR
        (status = 'accepted' AND submitted_at IS NOT NULL AND accepted_at IS NOT NULL
          AND acceptance_assignment_id IS NOT NULL)
        OR
        (status NOT IN ('submitted', 'accepted') AND accepted_at IS NULL)
      );
  END IF;
END;
$$;

CREATE OR REPLACE FUNCTION hxy_reject_operating_history_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'HXY operating history is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_outbox_attempts_append_only ON hxy_outbox_attempts;
CREATE TRIGGER trg_hxy_outbox_attempts_append_only
BEFORE UPDATE OR DELETE ON hxy_outbox_attempts
FOR EACH ROW EXECUTE FUNCTION hxy_reject_operating_history_mutation();

DROP TRIGGER IF EXISTS trg_hxy_outbox_attempts_no_truncate ON hxy_outbox_attempts;
CREATE TRIGGER trg_hxy_outbox_attempts_no_truncate
BEFORE TRUNCATE ON hxy_outbox_attempts
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_operating_history_mutation();

DROP TRIGGER IF EXISTS trg_hxy_operating_evidence_append_only ON hxy_operating_evidence;
CREATE TRIGGER trg_hxy_operating_evidence_append_only
BEFORE UPDATE OR DELETE ON hxy_operating_evidence
FOR EACH ROW EXECUTE FUNCTION hxy_reject_operating_history_mutation();

DROP TRIGGER IF EXISTS trg_hxy_operating_evidence_no_truncate ON hxy_operating_evidence;
CREATE TRIGGER trg_hxy_operating_evidence_no_truncate
BEFORE TRUNCATE ON hxy_operating_evidence
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_operating_history_mutation();

DROP TRIGGER IF EXISTS trg_hxy_state_transitions_append_only ON hxy_state_transitions;
CREATE TRIGGER trg_hxy_state_transitions_append_only
BEFORE UPDATE OR DELETE ON hxy_state_transitions
FOR EACH ROW EXECUTE FUNCTION hxy_reject_operating_history_mutation();

DROP TRIGGER IF EXISTS trg_hxy_state_transitions_no_truncate ON hxy_state_transitions;
CREATE TRIGGER trg_hxy_state_transitions_no_truncate
BEFORE TRUNCATE ON hxy_state_transitions
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_operating_history_mutation();

DROP TRIGGER IF EXISTS trg_hxy_metric_facts_append_only ON hxy_metric_facts;
CREATE TRIGGER trg_hxy_metric_facts_append_only
BEFORE UPDATE OR DELETE ON hxy_metric_facts
FOR EACH ROW EXECUTE FUNCTION hxy_reject_operating_history_mutation();

DROP TRIGGER IF EXISTS trg_hxy_metric_facts_no_truncate ON hxy_metric_facts;
CREATE TRIGGER trg_hxy_metric_facts_no_truncate
BEFORE TRUNCATE ON hxy_metric_facts
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_operating_history_mutation();

CREATE OR REPLACE FUNCTION hxy_require_published_metric_definition()
RETURNS TRIGGER AS $$
DECLARE
  metric_definition hxy_metric_definitions%ROWTYPE;
BEGIN
  SELECT definition.*
  INTO metric_definition
  FROM hxy_metric_definitions AS definition
  WHERE definition.organization_id = NEW.organization_id
    AND definition.metric_definition_id = NEW.metric_definition_id
    AND definition.metric_version = NEW.metric_definition_version
    AND definition.metric_key = NEW.metric_key;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'metric definition snapshot does not exist';
  END IF;

  IF metric_definition.status <> 'published' THEN
    RAISE EXCEPTION 'MetricFact requires a published MetricDefinition';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_metric_facts_published_definition ON hxy_metric_facts;
CREATE TRIGGER trg_hxy_metric_facts_published_definition
BEFORE INSERT ON hxy_metric_facts
FOR EACH ROW EXECUTE FUNCTION hxy_require_published_metric_definition();

CREATE INDEX IF NOT EXISTS idx_hxy_channel_identity_bindings_active
  ON hxy_channel_identity_bindings (organization_id, channel, channel_tenant_id, channel_user_id)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_hxy_inbound_envelopes_attention
  ON hxy_inbound_envelopes (organization_id, status, received_at DESC)
  WHERE status IN ('received', 'queued', 'needs_attention');

CREATE INDEX IF NOT EXISTS idx_hxy_ai_proposals_envelope_recent
  ON hxy_ai_proposals (organization_id, source_envelope_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_outbox_messages_claim
  ON hxy_outbox_messages (status, available_at, created_at, outbox_message_id)
  WHERE status IN ('pending', 'retryable_failed');

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_ai_proposals_input
  ON hxy_ai_proposals (organization_id, source_envelope_id, proposal_type, input_hash);

CREATE INDEX IF NOT EXISTS idx_hxy_outbox_messages_lease_expiry
  ON hxy_outbox_messages (lease_expires_at)
  WHERE status = 'leased';

CREATE INDEX IF NOT EXISTS idx_hxy_operating_events_store_status
  ON hxy_operating_events (organization_id, store_id, status, severity, detected_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_operating_evidence_event_recent
  ON hxy_operating_evidence (organization_id, operating_event_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_state_transitions_aggregate
  ON hxy_state_transitions (
    organization_id,
    aggregate_type,
    aggregate_id,
    occurred_at,
    transition_id
  );

CREATE INDEX IF NOT EXISTS idx_hxy_metric_facts_subject
  ON hxy_metric_facts (
    organization_id,
    store_id,
    metric_key,
    subject_type,
    subject_id,
    calculated_at DESC
  );
