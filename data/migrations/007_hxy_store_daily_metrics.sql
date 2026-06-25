CREATE TABLE IF NOT EXISTS hxy_store_daily_metrics (
  metrics_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  store_id TEXT NOT NULL DEFAULT '',
  store_name TEXT NOT NULL DEFAULT '',
  business_date DATE NOT NULL,
  revenue NUMERIC(12, 2) NOT NULL DEFAULT 0,
  target_revenue NUMERIC(12, 2) NOT NULL DEFAULT 0,
  orders INTEGER NOT NULL DEFAULT 0,
  average_ticket NUMERIC(12, 2) NOT NULL DEFAULT 0,
  target_average_ticket NUMERIC(12, 2) NOT NULL DEFAULT 0,
  repeat_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
  target_repeat_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
  product_mix_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  training_retrain_count INTEGER NOT NULL DEFAULT 0,
  customer_complaints INTEGER NOT NULL DEFAULT 0,
  raw_metrics_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  diagnosis_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (store_id, business_date)
);

CREATE INDEX IF NOT EXISTS idx_hxy_store_daily_metrics_store_date
  ON hxy_store_daily_metrics(store_id, business_date DESC);

CREATE INDEX IF NOT EXISTS idx_hxy_store_daily_metrics_created
  ON hxy_store_daily_metrics(created_at DESC);
