CREATE TABLE IF NOT EXISTS hxy_customer_subjects (
  customer_subject_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'merged', 'restricted')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, customer_subject_id)
);

CREATE TABLE IF NOT EXISTS hxy_service_contexts (
  service_context_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT NOT NULL,
  created_by_assignment_id UUID NOT NULL,
  client_context_id UUID NOT NULL,
  occurred_at TIMESTAMPTZ NOT NULL,
  service_label TEXT NOT NULL CHECK (char_length(btrim(service_label)) BETWEEN 1 AND 120),
  original_identity_hint JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(original_identity_hint) = 'object'),
  customer_subject_id UUID,
  request_fingerprint CHAR(64) NOT NULL CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
  status TEXT NOT NULL DEFAULT 'provisional'
    CHECK (status IN ('provisional', 'reconciled', 'closed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, service_context_id),
  UNIQUE (organization_id, store_id, service_context_id),
  UNIQUE (organization_id, created_by_assignment_id, client_context_id),
  CONSTRAINT fk_hxy_service_contexts_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_service_contexts_creator
    FOREIGN KEY (organization_id, store_id, created_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_service_contexts_subject
    FOREIGN KEY (organization_id, customer_subject_id)
    REFERENCES hxy_customer_subjects(organization_id, customer_subject_id)
    ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION prevent_hxy_service_identity_hint_update()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
  IF NEW.original_identity_hint IS DISTINCT FROM OLD.original_identity_hint THEN
    RAISE EXCEPTION 'original identity hint is immutable';
  END IF;
  RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_hxy_service_identity_hint_immutable ON hxy_service_contexts;
CREATE TRIGGER trg_hxy_service_identity_hint_immutable
BEFORE UPDATE ON hxy_service_contexts
FOR EACH ROW EXECUTE FUNCTION prevent_hxy_service_identity_hint_update();

CREATE TABLE IF NOT EXISTS hxy_service_feedback (
  service_feedback_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT NOT NULL,
  service_context_id UUID NOT NULL,
  created_by_assignment_id UUID NOT NULL,
  client_feedback_id UUID NOT NULL,
  feedback_text TEXT NOT NULL CHECK (char_length(btrim(feedback_text)) BETWEEN 1 AND 4000),
  request_fingerprint CHAR(64) NOT NULL CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, service_feedback_id),
  UNIQUE (organization_id, created_by_assignment_id, client_feedback_id),
  CONSTRAINT fk_hxy_service_feedback_context
    FOREIGN KEY (organization_id, store_id, service_context_id)
    REFERENCES hxy_service_contexts(organization_id, store_id, service_context_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_service_feedback_creator
    FOREIGN KEY (organization_id, store_id, created_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_service_feedback_assets (
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  service_feedback_id UUID NOT NULL,
  source_asset_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organization_id, service_feedback_id, source_asset_id),
  CONSTRAINT fk_hxy_service_feedback_assets_feedback
    FOREIGN KEY (organization_id, service_feedback_id)
    REFERENCES hxy_service_feedback(organization_id, service_feedback_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_service_feedback_assets_source
    FOREIGN KEY (organization_id, source_asset_id)
    REFERENCES hxy_product_materials(organization_id, material_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_external_identity_mappings (
  identity_mapping_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  source_system TEXT NOT NULL CHECK (char_length(btrim(source_system)) BETWEEN 2 AND 80),
  entity_type TEXT NOT NULL CHECK (entity_type IN ('customer', 'service')),
  external_identifier_hash CHAR(64) NOT NULL
    CHECK (external_identifier_hash ~ '^[0-9a-f]{64}$'),
  customer_subject_id UUID,
  service_context_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, identity_mapping_id),
  UNIQUE (organization_id, source_system, entity_type, external_identifier_hash),
  CONSTRAINT chk_hxy_external_identity_mapping_target CHECK (
    (entity_type = 'customer' AND customer_subject_id IS NOT NULL AND service_context_id IS NULL)
    OR
    (entity_type = 'service' AND customer_subject_id IS NULL AND service_context_id IS NOT NULL)
  ),
  CONSTRAINT fk_hxy_external_identity_mapping_subject
    FOREIGN KEY (organization_id, customer_subject_id)
    REFERENCES hxy_customer_subjects(organization_id, customer_subject_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_external_identity_mapping_context
    FOREIGN KEY (organization_id, service_context_id)
    REFERENCES hxy_service_contexts(organization_id, service_context_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_service_context_reconciliations (
  reconciliation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  service_context_id UUID NOT NULL,
  customer_subject_id UUID NOT NULL,
  source_system TEXT NOT NULL CHECK (char_length(btrim(source_system)) BETWEEN 2 AND 80),
  reconciled_by_assignment_id UUID NOT NULL,
  reconciled_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, reconciliation_id),
  CONSTRAINT fk_hxy_service_context_reconciliation_context
    FOREIGN KEY (organization_id, service_context_id)
    REFERENCES hxy_service_contexts(organization_id, service_context_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_service_context_reconciliation_subject
    FOREIGN KEY (organization_id, customer_subject_id)
    REFERENCES hxy_customer_subjects(organization_id, customer_subject_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_service_context_reconciliation_actor
    FOREIGN KEY (organization_id, reconciled_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_hxy_service_contexts_recent
  ON hxy_service_contexts (organization_id, store_id, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_service_feedback_context
  ON hxy_service_feedback (organization_id, service_context_id, created_at DESC);
