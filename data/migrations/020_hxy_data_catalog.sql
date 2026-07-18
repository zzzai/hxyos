CREATE EXTENSION IF NOT EXISTS btree_gist;

ALTER TABLE hxy_product_materials
  ADD COLUMN IF NOT EXISTS organization_id UUID,
  ADD COLUMN IF NOT EXISTS store_id TEXT,
  ADD COLUMN IF NOT EXISTS asset_kind TEXT NOT NULL DEFAULT 'file'
    CHECK (asset_kind IN ('file', 'image', 'audio', 'video', 'link', 'text')),
  ADD COLUMN IF NOT EXISTS visibility_scope JSONB NOT NULL DEFAULT
    '{"uploader": true, "store_manager": true, "hq": true}'::jsonb
    CHECK (jsonb_typeof(visibility_scope) = 'object'),
  ADD COLUMN IF NOT EXISTS retention_policy TEXT NOT NULL DEFAULT 'organization_default'
    CHECK (char_length(btrim(retention_policy)) BETWEEN 1 AND 80),
  ADD COLUMN IF NOT EXISTS scan_status TEXT NOT NULL DEFAULT 'legacy_unscanned'
    CHECK (scan_status IN ('pending', 'clean', 'blocked', 'failed', 'legacy_unscanned'));

UPDATE hxy_product_materials AS material
SET organization_id = assignment.organization_id,
    store_id = assignment.store_id
FROM hxy_role_assignments AS assignment
WHERE material.assignment_id = assignment.assignment_id
  AND material.organization_id IS NULL;

ALTER TABLE hxy_product_materials
  ALTER COLUMN organization_id SET NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_product_materials_organization_material
  ON hxy_product_materials (organization_id, material_id);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_hxy_product_materials_organization'
      AND conrelid = 'hxy_product_materials'::regclass
  ) THEN
    ALTER TABLE hxy_product_materials
      ADD CONSTRAINT fk_hxy_product_materials_organization
      FOREIGN KEY (organization_id)
      REFERENCES hxy_organizations(organization_id)
      ON DELETE RESTRICT;
  END IF;

  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_hxy_product_materials_organization_store'
      AND conrelid = 'hxy_product_materials'::regclass
  ) THEN
    ALTER TABLE hxy_product_materials
      ADD CONSTRAINT fk_hxy_product_materials_organization_store
      FOREIGN KEY (organization_id, store_id)
      REFERENCES hxy_organization_stores(organization_id, store_id)
      ON DELETE RESTRICT;
  END IF;
END;
$$;

CREATE INDEX IF NOT EXISTS idx_hxy_product_materials_organization_store_recent
  ON hxy_product_materials (organization_id, store_id, created_at DESC, material_id DESC);

CREATE TABLE IF NOT EXISTS hxy_legal_entities (
  entity_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  entity_type TEXT NOT NULL CHECK (
    entity_type IN ('brand_owner', 'company', 'individual_business', 'partner', 'other')
  ),
  display_name TEXT NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 1 AND 160),
  registration_reference TEXT NOT NULL DEFAULT ''
    CHECK (char_length(registration_reference) <= 160),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, entity_id)
);

CREATE TABLE IF NOT EXISTS hxy_operating_mode_catalog (
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  mode_code TEXT NOT NULL CHECK (char_length(btrim(mode_code)) BETWEEN 3 AND 80),
  mode_version INTEGER NOT NULL CHECK (mode_version > 0),
  display_name TEXT NOT NULL CHECK (char_length(btrim(display_name)) BETWEEN 1 AND 80),
  description TEXT NOT NULL DEFAULT '' CHECK (char_length(description) <= 1000),
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'active', 'superseded')),
  created_by_assignment_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (organization_id, mode_code, mode_version),
  CONSTRAINT fk_hxy_operating_mode_catalog_creator
    FOREIGN KEY (organization_id, created_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_governance_profiles (
  profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  profile_key TEXT NOT NULL CHECK (char_length(btrim(profile_key)) BETWEEN 3 AND 80),
  profile_version INTEGER NOT NULL CHECK (profile_version > 0),
  decision_rights JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(decision_rights) = 'object'),
  approval_policy_refs JSONB NOT NULL DEFAULT '[]'::jsonb
    CHECK (jsonb_typeof(approval_policy_refs) = 'array'),
  data_access_policy JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(data_access_policy) = 'object'),
  required_metric_definition_ids UUID[] NOT NULL DEFAULT '{}',
  audit_policy JSONB NOT NULL DEFAULT '{}'::jsonb
    CHECK (jsonb_typeof(audit_policy) = 'object'),
  effective_from TIMESTAMPTZ NOT NULL,
  effective_to TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'superseded')),
  approved_by_assignment_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, profile_id),
  UNIQUE (organization_id, profile_key, profile_version),
  CONSTRAINT chk_hxy_governance_profiles_effective_period
    CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT chk_hxy_governance_profiles_approval
    CHECK (status = 'draft' OR approved_by_assignment_id IS NOT NULL),
  CONSTRAINT fk_hxy_governance_profiles_approver
    FOREIGN KEY (organization_id, approved_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_store_operating_relationships (
  relationship_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT NOT NULL,
  relationship_version INTEGER NOT NULL CHECK (relationship_version > 0),
  mode_code TEXT NOT NULL,
  mode_version INTEGER NOT NULL CHECK (mode_version > 0),
  owner_entity_id UUID NOT NULL,
  operator_entity_id UUID NOT NULL,
  governance_profile_id UUID NOT NULL,
  agreement_asset_id UUID,
  effective_from TIMESTAMPTZ NOT NULL,
  effective_to TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'draft'
    CHECK (status IN ('draft', 'active', 'superseded', 'terminated')),
  created_by_assignment_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, relationship_id),
  UNIQUE (organization_id, store_id, relationship_version),
  CONSTRAINT chk_hxy_store_operating_relationships_effective_period
    CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT fk_hxy_store_operating_relationships_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_store_operating_relationships_mode
    FOREIGN KEY (organization_id, mode_code, mode_version)
    REFERENCES hxy_operating_mode_catalog(organization_id, mode_code, mode_version)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_store_operating_relationships_owner
    FOREIGN KEY (organization_id, owner_entity_id)
    REFERENCES hxy_legal_entities(organization_id, entity_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_store_operating_relationships_operator
    FOREIGN KEY (organization_id, operator_entity_id)
    REFERENCES hxy_legal_entities(organization_id, entity_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_store_operating_relationships_governance
    FOREIGN KEY (organization_id, governance_profile_id)
    REFERENCES hxy_governance_profiles(organization_id, profile_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_store_operating_relationships_agreement
    FOREIGN KEY (organization_id, agreement_asset_id)
    REFERENCES hxy_product_materials(organization_id, material_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_store_operating_relationships_creator
    FOREIGN KEY (organization_id, created_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  EXCLUDE USING gist (
    organization_id WITH =,
    store_id WITH =,
    tstzrange(effective_from, COALESCE(effective_to, 'infinity'::timestamptz), '[)') WITH &&
  ) WHERE (status = 'active')
);

CREATE TABLE IF NOT EXISTS hxy_data_sources (
  data_source_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  source_type TEXT NOT NULL CHECK (
    source_type IN ('pos', 'member', 'payment', 'groupbuy', 'finance', 'manual_ledger', 'other')
  ),
  name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 120),
  owner_assignment_id UUID,
  system_of_record BOOLEAN NOT NULL DEFAULT TRUE,
  data_classification TEXT NOT NULL DEFAULT 'confidential'
    CHECK (data_classification IN ('internal', 'confidential', 'restricted')),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'retired')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, data_source_id),
  CONSTRAINT fk_hxy_data_sources_owner
    FOREIGN KEY (organization_id, owner_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_data_connectors (
  connector_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  data_source_id UUID NOT NULL,
  connector_type TEXT NOT NULL CHECK (
    connector_type IN ('api', 'webhook', 'scheduled_sync', 'file_import')
  ),
  configuration_ref TEXT NOT NULL CHECK (char_length(btrim(configuration_ref)) BETWEEN 1 AND 240),
  schedule JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(schedule) = 'object'),
  cursor_state JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(cursor_state) = 'object'),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'failed', 'retired')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, connector_id),
  CONSTRAINT fk_hxy_data_connectors_source
    FOREIGN KEY (organization_id, data_source_id)
    REFERENCES hxy_data_sources(organization_id, data_source_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_dataset_snapshots (
  snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT,
  data_source_id UUID NOT NULL,
  connector_id UUID,
  schema_version TEXT NOT NULL CHECK (char_length(btrim(schema_version)) BETWEEN 1 AND 80),
  period_start TIMESTAMPTZ,
  period_end TIMESTAMPTZ,
  content_hash CHAR(64) NOT NULL CHECK (content_hash ~ '^[0-9a-f]{64}$'),
  record_count BIGINT NOT NULL DEFAULT 0 CHECK (record_count >= 0),
  object_key TEXT NOT NULL CHECK (char_length(btrim(object_key)) BETWEEN 1 AND 500),
  ingestion_status TEXT NOT NULL DEFAULT 'received'
    CHECK (ingestion_status IN ('received', 'validating', 'accepted', 'rejected', 'failed')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, snapshot_id),
  UNIQUE (organization_id, data_source_id, content_hash),
  CONSTRAINT chk_hxy_dataset_snapshots_period
    CHECK (period_end IS NULL OR period_start IS NULL OR period_end >= period_start),
  CONSTRAINT fk_hxy_dataset_snapshots_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_dataset_snapshots_source
    FOREIGN KEY (organization_id, data_source_id)
    REFERENCES hxy_data_sources(organization_id, data_source_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_dataset_snapshots_connector
    FOREIGN KEY (organization_id, connector_id)
    REFERENCES hxy_data_connectors(organization_id, connector_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_business_facts (
  fact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT,
  fact_type TEXT NOT NULL CHECK (char_length(btrim(fact_type)) BETWEEN 2 AND 100),
  source_snapshot_id UUID NOT NULL,
  source_record_key TEXT NOT NULL CHECK (char_length(btrim(source_record_key)) BETWEEN 1 AND 240),
  occurred_at TIMESTAMPTZ NOT NULL,
  dimensions JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(dimensions) = 'object'),
  measures JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(measures) = 'object'),
  normalization_version TEXT NOT NULL
    CHECK (char_length(btrim(normalization_version)) BETWEEN 1 AND 80),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, fact_id),
  UNIQUE (organization_id, source_snapshot_id, fact_type, source_record_key),
  CONSTRAINT fk_hxy_business_facts_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_business_facts_snapshot
    FOREIGN KEY (organization_id, source_snapshot_id)
    REFERENCES hxy_dataset_snapshots(organization_id, snapshot_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_metric_definitions (
  metric_definition_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  metric_key TEXT NOT NULL CHECK (char_length(btrim(metric_key)) BETWEEN 2 AND 100),
  metric_version INTEGER NOT NULL CHECK (metric_version > 0),
  name TEXT NOT NULL CHECK (char_length(btrim(name)) BETWEEN 1 AND 120),
  calculation_kind TEXT NOT NULL CHECK (calculation_kind IN ('dsl', 'implementation_ref')),
  formula_dsl JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(formula_dsl) = 'object'),
  calculation_ref TEXT,
  required_fact_types TEXT[] NOT NULL DEFAULT '{}',
  dimensions TEXT[] NOT NULL DEFAULT '{}',
  effective_from TIMESTAMPTZ NOT NULL,
  effective_to TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft', 'published', 'superseded')),
  approved_by_assignment_id UUID,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, metric_definition_id),
  UNIQUE (organization_id, metric_key, metric_version),
  CONSTRAINT chk_hxy_metric_definitions_effective_period
    CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT chk_hxy_metric_definitions_calculator
    CHECK (
      (calculation_kind = 'dsl' AND formula_dsl <> '{}'::jsonb AND calculation_ref IS NULL)
      OR
      (calculation_kind = 'implementation_ref' AND formula_dsl = '{}'::jsonb
        AND char_length(btrim(calculation_ref)) BETWEEN 3 AND 160)
    ),
  CONSTRAINT chk_hxy_metric_definitions_approval
    CHECK (status = 'draft' OR approved_by_assignment_id IS NOT NULL),
  CONSTRAINT fk_hxy_metric_definitions_approver
    FOREIGN KEY (organization_id, approved_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS hxy_asset_bindings (
  binding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  source_type TEXT NOT NULL CHECK (
    source_type IN ('source_asset', 'dataset_snapshot', 'business_fact', 'knowledge_asset')
  ),
  source_id UUID NOT NULL,
  target_type TEXT NOT NULL CHECK (
    target_type IN ('inbound_envelope', 'conversation', 'knowledge_asset', 'operating_event', 'task', 'evidence', 'training')
  ),
  target_id UUID NOT NULL,
  relation_type TEXT NOT NULL CHECK (
    relation_type IN ('attached_to', 'derived_from', 'evidence_for', 'supports', 'supersedes', 'mentioned_in')
  ),
  created_by_assignment_id UUID NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, source_type, source_id, target_type, target_id, relation_type),
  CONSTRAINT fk_hxy_asset_bindings_creator
    FOREIGN KEY (organization_id, created_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

CREATE OR REPLACE FUNCTION hxy_reject_data_catalog_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'HXY data catalog history is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_dataset_snapshots_append_only ON hxy_dataset_snapshots;
CREATE TRIGGER trg_hxy_dataset_snapshots_append_only
BEFORE UPDATE OR DELETE ON hxy_dataset_snapshots
FOR EACH ROW EXECUTE FUNCTION hxy_reject_data_catalog_mutation();

DROP TRIGGER IF EXISTS trg_hxy_dataset_snapshots_no_truncate ON hxy_dataset_snapshots;
CREATE TRIGGER trg_hxy_dataset_snapshots_no_truncate
BEFORE TRUNCATE ON hxy_dataset_snapshots
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_data_catalog_mutation();

DROP TRIGGER IF EXISTS trg_hxy_business_facts_append_only ON hxy_business_facts;
CREATE TRIGGER trg_hxy_business_facts_append_only
BEFORE UPDATE OR DELETE ON hxy_business_facts
FOR EACH ROW EXECUTE FUNCTION hxy_reject_data_catalog_mutation();

DROP TRIGGER IF EXISTS trg_hxy_business_facts_no_truncate ON hxy_business_facts;
CREATE TRIGGER trg_hxy_business_facts_no_truncate
BEFORE TRUNCATE ON hxy_business_facts
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_data_catalog_mutation();

DROP TRIGGER IF EXISTS trg_hxy_asset_bindings_append_only ON hxy_asset_bindings;
CREATE TRIGGER trg_hxy_asset_bindings_append_only
BEFORE UPDATE OR DELETE ON hxy_asset_bindings
FOR EACH ROW EXECUTE FUNCTION hxy_reject_data_catalog_mutation();

DROP TRIGGER IF EXISTS trg_hxy_asset_bindings_no_truncate ON hxy_asset_bindings;
CREATE TRIGGER trg_hxy_asset_bindings_no_truncate
BEFORE TRUNCATE ON hxy_asset_bindings
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_data_catalog_mutation();

CREATE OR REPLACE FUNCTION hxy_guard_published_catalog_row()
RETURNS TRIGGER AS $$
BEGIN
  IF OLD.status IN ('active', 'published', 'superseded') THEN
    RAISE EXCEPTION 'published HXY catalog rows cannot be changed in place';
  END IF;
  IF TG_OP = 'DELETE' THEN
    RETURN OLD;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_operating_mode_catalog_published_guard
  ON hxy_operating_mode_catalog;
CREATE TRIGGER trg_hxy_operating_mode_catalog_published_guard
BEFORE UPDATE OR DELETE ON hxy_operating_mode_catalog
FOR EACH ROW EXECUTE FUNCTION hxy_guard_published_catalog_row();

DROP TRIGGER IF EXISTS trg_hxy_governance_profiles_published_guard
  ON hxy_governance_profiles;
CREATE TRIGGER trg_hxy_governance_profiles_published_guard
BEFORE UPDATE OR DELETE ON hxy_governance_profiles
FOR EACH ROW EXECUTE FUNCTION hxy_guard_published_catalog_row();

DROP TRIGGER IF EXISTS trg_hxy_metric_definitions_published_guard
  ON hxy_metric_definitions;
CREATE TRIGGER trg_hxy_metric_definitions_published_guard
BEFORE UPDATE OR DELETE ON hxy_metric_definitions
FOR EACH ROW EXECUTE FUNCTION hxy_guard_published_catalog_row();

CREATE INDEX IF NOT EXISTS idx_hxy_store_operating_relationships_current
  ON hxy_store_operating_relationships (organization_id, store_id, status, effective_from DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_dataset_snapshots_source_recent
  ON hxy_dataset_snapshots (organization_id, data_source_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_business_facts_store_type_time
  ON hxy_business_facts (organization_id, store_id, fact_type, occurred_at DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_metric_definitions_key_status
  ON hxy_metric_definitions (organization_id, metric_key, status, metric_version DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_asset_bindings_target
  ON hxy_asset_bindings (organization_id, target_type, target_id, created_at DESC);
