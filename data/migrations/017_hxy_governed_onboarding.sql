CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_role_assignments_onboarding_identity
  ON hxy_role_assignments (organization_id, store_id, assignment_id, account_id);

CREATE TABLE IF NOT EXISTS hxy_member_invites (
  invite_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE RESTRICT,
  role TEXT NOT NULL CHECK (role IN ('store_manager', 'store_employee')),
  display_name TEXT NOT NULL CHECK (
    char_length(btrim(display_name)) BETWEEN 1 AND 80
  ),
  token_hash TEXT NOT NULL CHECK (token_hash ~ '^[0-9a-f]{64}$'),
  created_by_assignment_id UUID NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (
    status IN ('pending', 'redeemed', 'revoked')
  ),
  expires_at TIMESTAMPTZ NOT NULL,
  redeemed_account_id UUID REFERENCES staff_accounts(id) ON DELETE RESTRICT,
  redeemed_assignment_id UUID REFERENCES hxy_role_assignments(assignment_id) ON DELETE RESTRICT,
  redeemed_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT uq_hxy_member_invites_token_hash UNIQUE (token_hash),
  CONSTRAINT fk_hxy_member_invites_organization_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_member_invites_creator_organization
    FOREIGN KEY (organization_id, created_by_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_member_invites_redeemed_identity_store
    FOREIGN KEY (organization_id, store_id, redeemed_assignment_id, redeemed_account_id)
    REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id, account_id)
    ON DELETE RESTRICT,
  CONSTRAINT chk_hxy_member_invites_expiry CHECK (expires_at > created_at),
  CONSTRAINT chk_hxy_member_invites_state_shape CHECK (
    (
      status = 'pending'
      AND redeemed_account_id IS NULL
      AND redeemed_assignment_id IS NULL
      AND redeemed_at IS NULL
      AND revoked_at IS NULL
    )
    OR
    (
      status = 'redeemed'
      AND redeemed_account_id IS NOT NULL
      AND redeemed_assignment_id IS NOT NULL
      AND redeemed_at IS NOT NULL
      AND revoked_at IS NULL
    )
    OR
    (
      status = 'revoked'
      AND redeemed_account_id IS NULL
      AND redeemed_assignment_id IS NULL
      AND redeemed_at IS NULL
      AND revoked_at IS NOT NULL
    )
  )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_member_invites_scope_invite
  ON hxy_member_invites (organization_id, store_id, invite_id);

CREATE INDEX IF NOT EXISTS idx_hxy_member_invites_expires
  ON hxy_member_invites (expires_at);

CREATE INDEX IF NOT EXISTS idx_hxy_member_invites_scope_status
  ON hxy_member_invites (organization_id, store_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS hxy_member_invite_events (
  event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  store_id TEXT NOT NULL REFERENCES stores(store_id) ON DELETE RESTRICT,
  invite_id UUID,
  actor_assignment_id UUID NOT NULL,
  subject_assignment_id UUID,
  event_type TEXT NOT NULL CHECK (
    event_type IN ('created', 'redeemed', 'revoked', 'member_deactivated')
  ),
  payload JSONB NOT NULL DEFAULT '{}'::jsonb CHECK (payload = '{}'::jsonb),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  CONSTRAINT fk_hxy_member_invite_events_organization_store
    FOREIGN KEY (organization_id, store_id)
    REFERENCES hxy_organization_stores(organization_id, store_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_member_invite_events_invite_store
    FOREIGN KEY (organization_id, store_id, invite_id)
    REFERENCES hxy_member_invites(organization_id, store_id, invite_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_member_invite_events_actor_organization
    FOREIGN KEY (organization_id, actor_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT fk_hxy_member_invite_events_subject_store
    FOREIGN KEY (organization_id, store_id, subject_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, store_id, assignment_id)
    ON DELETE RESTRICT,
  CONSTRAINT chk_hxy_member_invite_events_subject CHECK (
    (
      event_type IN ('created', 'revoked')
      AND invite_id IS NOT NULL
      AND subject_assignment_id IS NULL
    )
    OR
    (
      event_type = 'redeemed'
      AND invite_id IS NOT NULL
      AND subject_assignment_id IS NOT NULL
    )
    OR
    (
      event_type = 'member_deactivated'
      AND invite_id IS NULL
      AND subject_assignment_id IS NOT NULL
    )
  )
);

CREATE INDEX IF NOT EXISTS idx_hxy_member_invite_events_invite_created
  ON hxy_member_invite_events (invite_id, created_at, event_id)
  WHERE invite_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_hxy_member_invite_events_scope_created
  ON hxy_member_invite_events (organization_id, store_id, created_at DESC);

CREATE OR REPLACE FUNCTION hxy_reject_member_invite_event_mutation()
RETURNS TRIGGER AS $$
BEGIN
  RAISE EXCEPTION 'hxy_member_invite_events is append-only';
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_hxy_member_invite_events_append_only
  ON hxy_member_invite_events;

CREATE TRIGGER trg_hxy_member_invite_events_append_only
  BEFORE UPDATE OR DELETE ON hxy_member_invite_events
  FOR EACH ROW EXECUTE FUNCTION hxy_reject_member_invite_event_mutation();

DROP TRIGGER IF EXISTS trg_hxy_member_invite_events_no_truncate
  ON hxy_member_invite_events;

CREATE TRIGGER trg_hxy_member_invite_events_no_truncate
  BEFORE TRUNCATE ON hxy_member_invite_events
  FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_member_invite_event_mutation();
