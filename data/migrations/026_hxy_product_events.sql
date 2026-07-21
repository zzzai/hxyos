CREATE TABLE IF NOT EXISTS hxy_product_events (
  product_event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT,
  assignment_id UUID NOT NULL,
  client_event_id UUID NOT NULL,
  event_name TEXT NOT NULL CHECK (
    event_name IN (
      'intake_succeeded',
      'service_feedback_completed',
      'briefing_feedback',
      'learning_completed',
      'closing_review_completed'
    )
  ),
  subject_id UUID NOT NULL,
  duration_ms INTEGER CHECK (duration_ms BETWEEN 0 AND 86400000),
  useful BOOLEAN,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, assignment_id, client_event_id),
  UNIQUE (organization_id, assignment_id, event_name, subject_id),
  CONSTRAINT fk_hxy_product_events_assignment
    FOREIGN KEY (organization_id, assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_product_events_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT chk_hxy_product_event_values CHECK (
    (
      event_name = 'briefing_feedback'
      AND useful IS NOT NULL
      AND duration_ms IS NULL
    )
    OR
    (
      event_name = 'service_feedback_completed'
      AND useful IS NULL
    )
    OR
    (
      event_name NOT IN ('briefing_feedback', 'service_feedback_completed')
      AND useful IS NULL
      AND duration_ms IS NULL
    )
  )
);

CREATE INDEX IF NOT EXISTS idx_hxy_product_events_scope_time
  ON hxy_product_events (organization_id, store_id, event_name, created_at DESC);

ALTER TABLE hxy_service_feedback
  ADD COLUMN IF NOT EXISTS duration_ms INTEGER;

ALTER TABLE hxy_service_feedback
  DROP CONSTRAINT IF EXISTS chk_hxy_service_feedback_duration;

ALTER TABLE hxy_service_feedback
  ADD CONSTRAINT chk_hxy_service_feedback_duration
  CHECK (duration_ms BETWEEN 0 AND 86400000);

CREATE OR REPLACE FUNCTION hxy_record_authoritative_product_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.sender_assignment_id IS NOT NULL
     AND NEW.intent_hint = 'organization_record' THEN
    INSERT INTO hxy_product_events (
      organization_id, store_id, assignment_id, client_event_id,
      event_name, subject_id, useful
    )
    VALUES (
      NEW.organization_id, NEW.store_id, NEW.sender_assignment_id, NEW.envelope_id,
      CASE
        WHEN NEW.raw_payload ->> 'purpose' = 'closing_review'
          THEN 'closing_review_completed'
        ELSE 'intake_succeeded'
      END,
      NEW.envelope_id,
      NULL
    )
    ON CONFLICT DO NOTHING;
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_hxy_record_authoritative_product_event
  ON hxy_inbound_envelopes;
CREATE TRIGGER trg_hxy_record_authoritative_product_event
AFTER INSERT ON hxy_inbound_envelopes
FOR EACH ROW EXECUTE FUNCTION hxy_record_authoritative_product_event();

CREATE OR REPLACE FUNCTION hxy_training_authoritative_product_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO hxy_product_events (
    organization_id, store_id, assignment_id, client_event_id,
    event_name, subject_id, useful
  )
  VALUES (
    NEW.organization_id, NEW.store_id, NEW.assignment_id, NEW.training_session_id,
    'learning_completed', NEW.training_session_id, NULL
  )
  ON CONFLICT DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_hxy_training_authoritative_product_event
  ON hxy_product_training_sessions;
CREATE TRIGGER trg_hxy_training_authoritative_product_event
AFTER INSERT ON hxy_product_training_sessions
FOR EACH ROW EXECUTE FUNCTION hxy_training_authoritative_product_event();

CREATE OR REPLACE FUNCTION hxy_service_feedback_authoritative_product_event()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  INSERT INTO hxy_product_events (
    organization_id, store_id, assignment_id, client_event_id,
    event_name, subject_id, duration_ms, useful
  )
  VALUES (
    NEW.organization_id, NEW.store_id, NEW.created_by_assignment_id,
    NEW.service_feedback_id, 'service_feedback_completed',
    NEW.service_feedback_id, NEW.duration_ms, NULL
  )
  ON CONFLICT DO NOTHING;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_hxy_service_feedback_authoritative_product_event
  ON hxy_service_feedback;
CREATE TRIGGER trg_hxy_service_feedback_authoritative_product_event
AFTER INSERT ON hxy_service_feedback
FOR EACH ROW EXECUTE FUNCTION hxy_service_feedback_authoritative_product_event();

CREATE OR REPLACE FUNCTION prevent_hxy_product_event_mutation()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  RAISE EXCEPTION 'product events are append-only';
END;
$$;

DROP TRIGGER IF EXISTS trg_hxy_product_events_append_only ON hxy_product_events;
CREATE TRIGGER trg_hxy_product_events_append_only
BEFORE UPDATE OR DELETE ON hxy_product_events
FOR EACH ROW EXECUTE FUNCTION prevent_hxy_product_event_mutation();

DROP TRIGGER IF EXISTS trg_hxy_product_events_no_truncate ON hxy_product_events;
CREATE TRIGGER trg_hxy_product_events_no_truncate
BEFORE TRUNCATE ON hxy_product_events
FOR EACH STATEMENT EXECUTE FUNCTION prevent_hxy_product_event_mutation();
