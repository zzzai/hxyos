CREATE TABLE IF NOT EXISTS hxy_knowledge_image_understandings (
  understanding_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id TEXT REFERENCES hxy_knowledge_assets(asset_id) ON DELETE CASCADE,
  run_name TEXT NOT NULL DEFAULT '',
  source_path TEXT NOT NULL DEFAULT '',
  normalized_path TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL DEFAULT '',
  image_type TEXT NOT NULL DEFAULT 'general_image',
  visual_summary TEXT NOT NULL DEFAULT '',
  business_summary TEXT NOT NULL DEFAULT '',
  ocr_text TEXT NOT NULL DEFAULT '',
  detected_entities JSONB NOT NULL DEFAULT '[]'::jsonb,
  prices JSONB NOT NULL DEFAULT '[]'::jsonb,
  related_domains JSONB NOT NULL DEFAULT '[]'::jsonb,
  confidence NUMERIC(5,3) NOT NULL DEFAULT 0,
  qa_ready BOOLEAN NOT NULL DEFAULT FALSE,
  needs_review BOOLEAN NOT NULL DEFAULT TRUE,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(asset_id, run_name)
);

CREATE INDEX IF NOT EXISTS idx_hxy_image_understandings_asset ON hxy_knowledge_image_understandings(asset_id);
CREATE INDEX IF NOT EXISTS idx_hxy_image_understandings_type ON hxy_knowledge_image_understandings(image_type);
CREATE INDEX IF NOT EXISTS idx_hxy_image_understandings_ready ON hxy_knowledge_image_understandings(qa_ready, needs_review);
CREATE INDEX IF NOT EXISTS idx_hxy_image_understandings_summary_trgm ON hxy_knowledge_image_understandings USING GIN((visual_summary || ' ' || business_summary || ' ' || ocr_text) gin_trgm_ops);
