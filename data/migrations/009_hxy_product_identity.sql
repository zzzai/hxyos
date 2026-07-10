CREATE TABLE IF NOT EXISTS hxy_organizations (
  organization_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS hxy_role_assignments (
  assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id UUID NOT NULL REFERENCES staff_accounts(id) ON DELETE CASCADE,
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT REFERENCES stores(store_id) ON DELETE RESTRICT,
  role TEXT NOT NULL CHECK (role IN (
      'founder',
      'hq_operations',
      'store_manager',
      'store_employee',
      'system_admin'
    )
  ),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_role_assignments_store_scope
  ON hxy_role_assignments (account_id, organization_id, store_id, role)
  WHERE store_id IS NOT NULL;

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_role_assignments_organization_scope
  ON hxy_role_assignments (account_id, organization_id, role)
  WHERE store_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_hxy_role_assignments_account_status
  ON hxy_role_assignments (account_id, status, created_at);

CREATE INDEX IF NOT EXISTS idx_hxy_role_assignments_organization_status
  ON hxy_role_assignments (organization_id, status);

CREATE INDEX IF NOT EXISTS idx_hxy_role_assignments_store_status
  ON hxy_role_assignments (store_id, status)
  WHERE store_id IS NOT NULL;
