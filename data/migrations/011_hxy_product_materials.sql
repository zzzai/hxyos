CREATE TABLE IF NOT EXISTS hxy_product_materials (
  material_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  assignment_id UUID NOT NULL REFERENCES hxy_role_assignments(assignment_id) ON DELETE RESTRICT,
  client_upload_id UUID NOT NULL,
  original_file_name TEXT NOT NULL CHECK (
    char_length(btrim(original_file_name)) BETWEEN 1 AND 180
  ),
  extension TEXT NOT NULL CHECK (char_length(extension) BETWEEN 2 AND 12),
  media_type TEXT NOT NULL DEFAULT 'application/octet-stream',
  size_bytes BIGINT NOT NULL CHECK (size_bytes > 0),
  sha256 CHAR(64) NOT NULL CHECK (sha256 ~ '^[0-9a-f]{64}$'),
  storage_key TEXT NOT NULL UNIQUE,
  note TEXT NOT NULL DEFAULT '' CHECK (char_length(note) <= 1000),
  status TEXT NOT NULL DEFAULT 'received' CHECK (
    status IN ('received', 'understood', 'understanding_failed', 'archived')
  ),
  understanding_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  official_use_allowed BOOLEAN NOT NULL DEFAULT FALSE CHECK (official_use_allowed = FALSE),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (assignment_id, material_id),
  UNIQUE (assignment_id, client_upload_id)
);

CREATE INDEX IF NOT EXISTS idx_hxy_product_materials_assignment_recent
  ON hxy_product_materials (assignment_id, created_at DESC, material_id DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_product_materials_assignment_sha256
  ON hxy_product_materials (assignment_id, sha256);

CREATE INDEX IF NOT EXISTS idx_hxy_product_materials_status
  ON hxy_product_materials (assignment_id, status, updated_at DESC);
