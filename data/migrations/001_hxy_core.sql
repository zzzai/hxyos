CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS stores (
  store_id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  city TEXT NOT NULL DEFAULT '',
  region TEXT NOT NULL DEFAULT '',
  address TEXT NOT NULL DEFAULT '',
  contact_phone TEXT NOT NULL DEFAULT '',
  opening_hours TEXT NOT NULL DEFAULT '',
  qr_code_url TEXT NOT NULL DEFAULT '',
  order_url TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'closed')),
  sort_order INTEGER NOT NULL DEFAULT 100,
  config_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staff_accounts (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  username TEXT NOT NULL UNIQUE,
  display_name TEXT NOT NULL DEFAULT '',
  password_hash TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('hq_admin', 'region_manager', 'store_manager', 'frontdesk', 'technician', 'operator', 'readonly')),
  store_id TEXT REFERENCES stores(store_id),
  region TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'disabled')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS staff_sessions (
  token_hash TEXT PRIMARY KEY,
  account_id UUID NOT NULL REFERENCES staff_accounts(id) ON DELETE CASCADE,
  expires_at TIMESTAMPTZ NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS users (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  phone TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL DEFAULT '',
  profile_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS catalogs (
  catalog_key TEXT PRIMARY KEY,
  store_id TEXT REFERENCES stores(store_id),
  version_no INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'paused', 'archived')),
  content JSONB NOT NULL,
  updated_by TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS catalog_drafts (
  catalog_key TEXT PRIMARY KEY,
  store_id TEXT REFERENCES stores(store_id),
  content JSONB NOT NULL,
  updated_by TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS catalog_versions (
  id BIGSERIAL PRIMARY KEY,
  catalog_key TEXT NOT NULL,
  store_id TEXT REFERENCES stores(store_id),
  version_no INTEGER NOT NULL,
  action TEXT NOT NULL CHECK (action IN ('publish', 'rollback', 'seed', 'import')),
  actor TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  content JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (catalog_key, version_no)
);

CREATE TABLE IF NOT EXISTS orders (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  order_no TEXT NOT NULL UNIQUE,
  store_id TEXT REFERENCES stores(store_id),
  user_id UUID REFERENCES users(id),
  customer_phone TEXT NOT NULL DEFAULT '',
  customer_name TEXT NOT NULL DEFAULT '',
  seat TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'confirmed', 'serving', 'completed', 'cancelled', 'exception')),
  total_amount NUMERIC(12, 2) NOT NULL DEFAULT 0,
  items_json JSONB NOT NULL DEFAULT '[]'::jsonb,
  selections_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  note TEXT NOT NULL DEFAULT '',
  source_channel TEXT NOT NULL DEFAULT 'h5',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS order_status_events (
  id BIGSERIAL PRIMARY KEY,
  order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
  from_status TEXT,
  to_status TEXT NOT NULL,
  actor TEXT NOT NULL DEFAULT '',
  note TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS memory_items (
  memory_id TEXT PRIMARY KEY,
  memory_type TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  project_stage TEXT,
  status TEXT NOT NULL,
  confidence DOUBLE PRECISION,
  version TEXT NOT NULL DEFAULT 'v0.1',
  source_kind TEXT NOT NULL DEFAULT 'import',
  source_path TEXT,
  source_object_id TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  review_at TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS memory_evidence_links (
  memory_id TEXT NOT NULL REFERENCES memory_items(memory_id) ON DELETE CASCADE,
  evidence_id TEXT NOT NULL,
  source_path TEXT,
  snippet TEXT,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  PRIMARY KEY (memory_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS memory_transitions (
  transition_id BIGSERIAL PRIMARY KEY,
  memory_id TEXT NOT NULL REFERENCES memory_items(memory_id) ON DELETE CASCADE,
  from_status TEXT,
  to_status TEXT NOT NULL,
  reason TEXT,
  actor TEXT NOT NULL DEFAULT '',
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS memory_import_runs (
  import_id TEXT PRIMARY KEY,
  source_dir TEXT NOT NULL,
  started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  status TEXT NOT NULL,
  item_count INTEGER NOT NULL DEFAULT 0,
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE TABLE IF NOT EXISTS memory_search_documents (
  memory_id TEXT PRIMARY KEY REFERENCES memory_items(memory_id) ON DELETE CASCADE,
  memory_type TEXT NOT NULL,
  title TEXT NOT NULL,
  body TEXT NOT NULL,
  keywords TEXT NOT NULL DEFAULT '',
  payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
  search_vector TSVECTOR GENERATED ALWAYS AS (
    setweight(to_tsvector('simple', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('simple', coalesce(keywords, '')), 'B') ||
    setweight(to_tsvector('simple', coalesce(body, '')), 'C')
  ) STORED,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_stores_status ON stores(status, sort_order);
CREATE INDEX IF NOT EXISTS idx_staff_accounts_role_store ON staff_accounts(role, store_id);
CREATE INDEX IF NOT EXISTS idx_staff_sessions_expires ON staff_sessions(expires_at);
CREATE INDEX IF NOT EXISTS idx_catalog_versions_key_version ON catalog_versions(catalog_key, version_no DESC);
CREATE INDEX IF NOT EXISTS idx_orders_store_status_created ON orders(store_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_order_status_events_order ON order_status_events(order_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_items_type_status ON memory_items(memory_type, status, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_items_stage ON memory_items(project_stage, updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_evidence_links_evidence ON memory_evidence_links(evidence_id);
CREATE INDEX IF NOT EXISTS idx_memory_transitions_memory ON memory_transitions(memory_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_search_documents_fts ON memory_search_documents USING GIN(search_vector);
CREATE INDEX IF NOT EXISTS idx_memory_search_documents_title_trgm ON memory_search_documents USING GIN(title gin_trgm_ops);

