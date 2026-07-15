ALTER TABLE hxy_product_materials
  ADD COLUMN IF NOT EXISTS source_origin TEXT NOT NULL DEFAULT 'unknown'
    CHECK (source_origin IN ('internal', 'external', 'unknown')),
  ADD COLUMN IF NOT EXISTS source_authority TEXT NOT NULL DEFAULT 'external_reference'
    CHECK (source_authority IN ('official_internal', 'internal_material', 'external_reference')),
  ADD COLUMN IF NOT EXISTS authority_version INTEGER NOT NULL DEFAULT 1
    CHECK (authority_version > 0);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'hxy_product_materials_source_authority_origin_check'
      AND conrelid = 'hxy_product_materials'::regclass
  ) THEN
    ALTER TABLE hxy_product_materials
      ADD CONSTRAINT hxy_product_materials_source_authority_origin_check
      CHECK (source_origin = 'internal' OR source_authority = 'external_reference');
  END IF;
END;
$$;

CREATE TABLE IF NOT EXISTS hxy_material_authority_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  material_id UUID NOT NULL REFERENCES hxy_product_materials(material_id) ON DELETE RESTRICT,
  owner_assignment_id UUID NOT NULL REFERENCES hxy_role_assignments(assignment_id) ON DELETE RESTRICT,
  actor_assignment_id UUID NOT NULL REFERENCES hxy_role_assignments(assignment_id) ON DELETE RESTRICT,
  previous_origin TEXT CHECK (
    previous_origin IS NULL OR previous_origin IN ('internal', 'external', 'unknown')
  ),
  new_origin TEXT NOT NULL CHECK (new_origin IN ('internal', 'external', 'unknown')),
  previous_authority TEXT CHECK (
    previous_authority IS NULL OR previous_authority IN ('official_internal', 'internal_material', 'external_reference')
  ),
  new_authority TEXT NOT NULL CHECK (
    new_authority IN ('official_internal', 'internal_material', 'external_reference')
  ),
  version_no INTEGER NOT NULL CHECK (version_no > 0),
  reason TEXT NOT NULL CHECK (char_length(btrim(reason)) BETWEEN 4 AND 500),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (material_id, version_no)
);

CREATE INDEX IF NOT EXISTS idx_hxy_material_authority_events_material
  ON hxy_material_authority_events (material_id, version_no DESC);

CREATE OR REPLACE FUNCTION hxy_validate_material_authority_event()
RETURNS TRIGGER AS $$
DECLARE
  material_record RECORD;
  actor_record RECORD;
BEGIN
  SELECT material.assignment_id AS owner_assignment_id,
         material.source_origin,
         material.source_authority,
         material.authority_version,
         owner.organization_id
  INTO material_record
  FROM hxy_product_materials AS material
  JOIN hxy_role_assignments AS owner
    ON owner.assignment_id = material.assignment_id
  WHERE material.material_id = NEW.material_id;

  IF NOT FOUND OR NEW.owner_assignment_id <> material_record.owner_assignment_id THEN
    RAISE EXCEPTION 'hxy material authority event has an invalid owner';
  END IF;

  IF NEW.previous_origin IS NULL AND NEW.previous_authority IS NULL THEN
    IF NEW.actor_assignment_id <> material_record.owner_assignment_id
       OR NEW.version_no <> material_record.authority_version
       OR NEW.new_origin <> material_record.source_origin
       OR NEW.new_authority <> material_record.source_authority THEN
      RAISE EXCEPTION 'hxy material authority baseline does not match its source';
    END IF;
    RETURN NEW;
  END IF;

  IF NEW.previous_origin IS NULL OR NEW.previous_authority IS NULL THEN
    RAISE EXCEPTION 'hxy material authority change requires complete previous state';
  END IF;

  SELECT role, organization_id, status
  INTO actor_record
  FROM hxy_role_assignments
  WHERE assignment_id = NEW.actor_assignment_id;

  IF NOT FOUND
     OR actor_record.status <> 'active'
     OR actor_record.organization_id <> material_record.organization_id
     OR actor_record.role NOT IN ('founder', 'hq_operations') THEN
    RAISE EXCEPTION 'hxy material authority actor is not authorized';
  END IF;

  IF NEW.version_no <> material_record.authority_version + 1
     OR NEW.previous_origin <> material_record.source_origin
     OR NEW.previous_authority <> material_record.source_authority THEN
    RAISE EXCEPTION 'hxy material authority event does not match current state';
  END IF;

  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_material_authority_events_validate
  ON hxy_material_authority_events;
CREATE TRIGGER trg_hxy_material_authority_events_validate
BEFORE INSERT ON hxy_material_authority_events
FOR EACH ROW EXECUTE FUNCTION hxy_validate_material_authority_event();

INSERT INTO hxy_material_authority_events (
  material_id,
  owner_assignment_id,
  actor_assignment_id,
  previous_origin,
  new_origin,
  previous_authority,
  new_authority,
  version_no,
  reason
)
SELECT material_id,
       assignment_id,
       assignment_id,
       NULL,
       source_origin,
       NULL,
       source_authority,
       authority_version,
       '迁移建立源文件级权威基线'
FROM hxy_product_materials
WHERE NOT EXISTS (
  SELECT 1
  FROM hxy_material_authority_events AS existing
  WHERE existing.material_id = hxy_product_materials.material_id
    AND existing.version_no = hxy_product_materials.authority_version
)
ON CONFLICT (material_id, version_no) DO NOTHING;

CREATE OR REPLACE FUNCTION hxy_record_initial_material_authority()
RETURNS TRIGGER AS $$
BEGIN
  INSERT INTO hxy_material_authority_events (
    material_id,
    owner_assignment_id,
    actor_assignment_id,
    previous_origin,
    new_origin,
    previous_authority,
    new_authority,
    version_no,
    reason
  )
  VALUES (
    NEW.material_id,
    NEW.assignment_id,
    NEW.assignment_id,
    NULL,
    NEW.source_origin,
    NULL,
    NEW.source_authority,
    NEW.authority_version,
    '资料上传时建立源文件级权威分类'
  );
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_product_materials_initial_authority
  ON hxy_product_materials;
CREATE TRIGGER trg_hxy_product_materials_initial_authority
AFTER INSERT ON hxy_product_materials
FOR EACH ROW EXECUTE FUNCTION hxy_record_initial_material_authority();

CREATE OR REPLACE FUNCTION hxy_enforce_material_authority_version()
RETURNS TRIGGER AS $$
BEGIN
  IF NEW.source_origin = OLD.source_origin
     AND NEW.source_authority = OLD.source_authority
     AND NEW.authority_version = OLD.authority_version THEN
    RETURN NEW;
  END IF;

  IF NEW.authority_version <> OLD.authority_version + 1 THEN
    RAISE EXCEPTION 'hxy material authority version must advance by one';
  END IF;

  PERFORM 1
  FROM hxy_material_authority_events AS event
  JOIN hxy_role_assignments AS actor
    ON actor.assignment_id = event.actor_assignment_id
   AND actor.status = 'active'
   AND actor.role IN ('founder', 'hq_operations')
  JOIN hxy_role_assignments AS owner
    ON owner.assignment_id = event.owner_assignment_id
   AND owner.organization_id = actor.organization_id
  WHERE event.material_id = NEW.material_id
    AND event.owner_assignment_id = OLD.assignment_id
    AND event.version_no = NEW.authority_version
    AND event.previous_origin = OLD.source_origin
    AND event.new_origin = NEW.source_origin
    AND event.previous_authority = OLD.source_authority
    AND event.new_authority = NEW.source_authority;
  IF NOT FOUND THEN
    RAISE EXCEPTION 'hxy material authority change requires a matching event';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_product_materials_authority_version_guard
  ON hxy_product_materials;
CREATE TRIGGER trg_hxy_product_materials_authority_version_guard
BEFORE UPDATE OF source_origin, source_authority, authority_version
ON hxy_product_materials
FOR EACH ROW EXECUTE FUNCTION hxy_enforce_material_authority_version();

CREATE OR REPLACE FUNCTION hxy_reject_material_authority_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'hxy material authority events are append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_material_authority_events_append_only
  ON hxy_material_authority_events;
CREATE TRIGGER trg_hxy_material_authority_events_append_only
BEFORE UPDATE OR DELETE ON hxy_material_authority_events
FOR EACH ROW EXECUTE FUNCTION hxy_reject_material_authority_event_mutation();

DROP TRIGGER IF EXISTS trg_hxy_material_authority_events_no_truncate
  ON hxy_material_authority_events;
CREATE TRIGGER trg_hxy_material_authority_events_no_truncate
BEFORE TRUNCATE ON hxy_material_authority_events
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_material_authority_event_mutation();
