ALTER TABLE hxy_knowledge_assets
  ADD COLUMN IF NOT EXISTS source_origin TEXT NOT NULL DEFAULT 'unknown'
    CHECK (source_origin IN ('internal', 'external', 'unknown')),
  ADD COLUMN IF NOT EXISTS source_authority TEXT NOT NULL DEFAULT 'external_reference'
    CHECK (source_authority IN ('official_internal', 'internal_material', 'external_reference')),
  ADD COLUMN IF NOT EXISTS authority_version INTEGER NOT NULL DEFAULT 1
    CHECK (authority_version > 0),
  ADD COLUMN IF NOT EXISTS authority_organization_id UUID
    REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'hxy_knowledge_assets_source_authority_origin_check'
      AND conrelid = 'hxy_knowledge_assets'::regclass
  ) THEN
    ALTER TABLE hxy_knowledge_assets
      ADD CONSTRAINT hxy_knowledge_assets_source_authority_origin_check
      CHECK (source_origin = 'internal' OR source_authority = 'external_reference');
  END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS hxy_knowledge_asset_authority_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id TEXT NOT NULL REFERENCES hxy_knowledge_assets(asset_id) ON DELETE RESTRICT,
  event_type TEXT NOT NULL CHECK (event_type IN ('baseline', 'classification')),
  organization_id UUID REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  actor_assignment_id UUID REFERENCES hxy_role_assignments(assignment_id) ON DELETE RESTRICT,
  previous_origin TEXT CHECK (
    previous_origin IS NULL OR previous_origin IN ('internal', 'external', 'unknown')
  ),
  new_origin TEXT NOT NULL CHECK (new_origin IN ('internal', 'external', 'unknown')),
  previous_authority TEXT CHECK (
    previous_authority IS NULL OR previous_authority IN (
      'official_internal', 'internal_material', 'external_reference'
    )
  ),
  new_authority TEXT NOT NULL CHECK (
    new_authority IN ('official_internal', 'internal_material', 'external_reference')
  ),
  previous_version INTEGER CHECK (previous_version IS NULL OR previous_version > 0),
  version_no INTEGER NOT NULL CHECK (version_no > 0),
  reason TEXT NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 4 AND 500),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (asset_id, version_no),
  CHECK (
    (
      event_type = 'baseline'
      AND organization_id IS NULL
      AND actor_assignment_id IS NULL
      AND previous_origin IS NULL
      AND previous_authority IS NULL
      AND previous_version IS NULL
      AND new_origin = 'unknown'
      AND new_authority = 'external_reference'
      AND version_no = 1
    )
    OR
    (
      event_type = 'classification'
      AND organization_id IS NOT NULL
      AND actor_assignment_id IS NOT NULL
      AND previous_origin IS NOT NULL
      AND previous_authority IS NOT NULL
      AND previous_version IS NOT NULL
      AND version_no = previous_version + 1
    )
  )
);

CREATE INDEX IF NOT EXISTS idx_hxy_knowledge_asset_authority_events_asset
  ON hxy_knowledge_asset_authority_events (asset_id, version_no DESC);

CREATE OR REPLACE FUNCTION hxy_validate_knowledge_asset_authority_event()
RETURNS TRIGGER AS $$
DECLARE
  asset_record RECORD;
  actor_record RECORD;
BEGIN
  SELECT asset.source_origin,
         asset.source_authority,
         asset.authority_version,
         asset.authority_organization_id
  INTO asset_record
  FROM hxy_knowledge_assets AS asset
  WHERE asset.asset_id = NEW.asset_id;

  IF NOT FOUND THEN
    RAISE EXCEPTION 'hxy knowledge asset authority event has no source';
  END IF;

  IF NEW.event_type = 'baseline' THEN
    IF asset_record.authority_organization_id IS NOT NULL
       OR NEW.new_origin <> asset_record.source_origin
       OR NEW.new_authority <> asset_record.source_authority
       OR NEW.version_no <> asset_record.authority_version THEN
      RAISE EXCEPTION 'hxy knowledge asset authority baseline does not match its source';
    END IF;
    RETURN NEW;
  END IF;

  SELECT role, organization_id, status
  INTO actor_record
  FROM hxy_role_assignments
  WHERE assignment_id = NEW.actor_assignment_id;

  IF NOT FOUND
     OR actor_record.status <> 'active'
     OR actor_record.role NOT IN ('founder', 'hq_operations')
     OR actor_record.organization_id <> NEW.organization_id THEN
    RAISE EXCEPTION 'hxy knowledge asset authority actor is not authorized';
  END IF;

  IF asset_record.authority_organization_id IS NOT NULL AND asset_record.authority_organization_id <> NEW.organization_id THEN
    RAISE EXCEPTION 'hxy knowledge asset authority cannot cross organizations';
  END IF;

  IF NEW.previous_origin <> asset_record.source_origin
     OR NEW.previous_authority <> asset_record.source_authority
     OR NEW.previous_version <> asset_record.authority_version
     OR NEW.version_no <> asset_record.authority_version + 1 THEN
    RAISE EXCEPTION 'hxy knowledge asset authority event does not match current state';
  END IF;

  IF NEW.new_origin <> 'internal' AND NEW.new_authority <> 'external_reference' THEN
    RAISE EXCEPTION 'hxy external knowledge asset cannot receive internal authority';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_knowledge_asset_authority_events_validate
  ON hxy_knowledge_asset_authority_events;
CREATE TRIGGER trg_hxy_knowledge_asset_authority_events_validate
BEFORE INSERT ON hxy_knowledge_asset_authority_events
FOR EACH ROW EXECUTE FUNCTION hxy_validate_knowledge_asset_authority_event();

INSERT INTO hxy_knowledge_asset_authority_events (
  asset_id,
  event_type,
  organization_id,
  actor_assignment_id,
  previous_origin,
  new_origin,
  previous_authority,
  new_authority,
  previous_version,
  version_no,
  reason
)
SELECT asset_id,
       'baseline',
       NULL,
       NULL,
       NULL,
       source_origin,
       NULL,
       source_authority,
       NULL,
       authority_version,
       '迁移建立全局资料权威基线'
FROM hxy_knowledge_assets
WHERE NOT EXISTS (
  SELECT 1
  FROM hxy_knowledge_asset_authority_events AS existing
  WHERE existing.asset_id = hxy_knowledge_assets.asset_id
    AND existing.version_no = hxy_knowledge_assets.authority_version
)
ON CONFLICT (asset_id, version_no) DO NOTHING;

CREATE OR REPLACE FUNCTION hxy_record_initial_knowledge_asset_authority()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO hxy_knowledge_asset_authority_events (
    asset_id,
    event_type,
    organization_id,
    actor_assignment_id,
    previous_origin,
    new_origin,
    previous_authority,
    new_authority,
    previous_version,
    version_no,
    reason
  )
  VALUES (
    NEW.asset_id,
    'baseline',
    NULL,
    NULL,
    NULL,
    NEW.source_origin,
    NULL,
    NEW.source_authority,
    NULL,
    NEW.authority_version,
    '资料导入时建立全局资料权威基线'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_knowledge_assets_initial_authority
  ON hxy_knowledge_assets;
CREATE TRIGGER trg_hxy_knowledge_assets_initial_authority
AFTER INSERT ON hxy_knowledge_assets
FOR EACH ROW EXECUTE FUNCTION hxy_record_initial_knowledge_asset_authority();

CREATE OR REPLACE FUNCTION hxy_enforce_knowledge_asset_authority_version()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.source_origin = OLD.source_origin
     AND NEW.source_authority = OLD.source_authority
     AND NEW.authority_version = OLD.authority_version
     AND NEW.authority_organization_id IS NOT DISTINCT FROM OLD.authority_organization_id THEN
    RETURN NEW;
  END IF;

  IF NEW.authority_version <> OLD.authority_version + 1 THEN
    RAISE EXCEPTION 'hxy knowledge asset authority version must advance by one';
  END IF;

  IF NEW.authority_organization_id IS NULL
     OR (OLD.authority_organization_id IS NOT NULL AND NEW.authority_organization_id <> OLD.authority_organization_id) THEN
    RAISE EXCEPTION 'hxy knowledge asset authority organization is invalid';
  END IF;

  PERFORM 1
  FROM hxy_knowledge_asset_authority_events AS event
  JOIN hxy_role_assignments AS actor
    ON actor.assignment_id = event.actor_assignment_id
   AND actor.status = 'active'
   AND actor.role IN ('founder', 'hq_operations')
   AND actor.organization_id = event.organization_id
  WHERE event.asset_id = NEW.asset_id
    AND event.event_type = 'classification'
    AND event.organization_id = NEW.authority_organization_id
    AND event.previous_origin = OLD.source_origin
    AND event.new_origin = NEW.source_origin
    AND event.previous_authority = OLD.source_authority
    AND event.new_authority = NEW.source_authority
    AND event.previous_version = OLD.authority_version
    AND event.version_no = NEW.authority_version;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'hxy knowledge asset authority change requires a matching event';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_knowledge_assets_authority_version_guard
  ON hxy_knowledge_assets;
CREATE TRIGGER trg_hxy_knowledge_assets_authority_version_guard
BEFORE UPDATE OF source_origin, source_authority, authority_version, authority_organization_id
ON hxy_knowledge_assets
FOR EACH ROW EXECUTE FUNCTION hxy_enforce_knowledge_asset_authority_version();

CREATE OR REPLACE FUNCTION hxy_reject_knowledge_asset_authority_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'hxy knowledge asset authority events are append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_knowledge_asset_authority_events_append_only
  ON hxy_knowledge_asset_authority_events;
CREATE TRIGGER trg_hxy_knowledge_asset_authority_events_append_only
BEFORE UPDATE OR DELETE ON hxy_knowledge_asset_authority_events
FOR EACH ROW EXECUTE FUNCTION hxy_reject_knowledge_asset_authority_event_mutation();

DROP TRIGGER IF EXISTS trg_hxy_knowledge_asset_authority_events_no_truncate
  ON hxy_knowledge_asset_authority_events;
CREATE TRIGGER trg_hxy_knowledge_asset_authority_events_no_truncate
BEFORE TRUNCATE ON hxy_knowledge_asset_authority_events
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_knowledge_asset_authority_event_mutation();
