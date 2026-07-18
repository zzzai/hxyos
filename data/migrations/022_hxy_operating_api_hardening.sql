ALTER TABLE hxy_operating_evidence
  ADD COLUMN IF NOT EXISTS client_evidence_id UUID;

CREATE UNIQUE INDEX IF NOT EXISTS uq_hxy_operating_evidence_client_request
  ON hxy_operating_evidence (
    organization_id,
    created_by_assignment_id,
    client_evidence_id
  )
  WHERE client_evidence_id IS NOT NULL;

ALTER TABLE hxy_inbound_envelopes
  ADD COLUMN IF NOT EXISTS request_fingerprint CHAR(64);

WITH envelope_assets AS (
  SELECT binding.organization_id,
         binding.target_id AS envelope_id,
         string_agg(binding.source_id::text, ',' ORDER BY binding.source_id::text)
           AS source_asset_ids
  FROM hxy_asset_bindings AS binding
  WHERE binding.source_type = 'source_asset'
    AND binding.target_type = 'inbound_envelope'
    AND binding.relation_type = 'attached_to'
  GROUP BY binding.organization_id, binding.target_id
), fingerprint_inputs AS (
  SELECT envelope.envelope_id,
         concat_ws(
           E'\n',
           'hxy-intake-v1',
           encode(convert_to(envelope.organization_id::text, 'UTF8'), 'hex'),
           encode(convert_to(envelope.channel, 'UTF8'), 'hex'),
           encode(convert_to(envelope.channel_tenant_id, 'UTF8'), 'hex'),
           encode(convert_to(envelope.channel_message_id, 'UTF8'), 'hex'),
           encode(convert_to(envelope.channel_thread_id, 'UTF8'), 'hex'),
           encode(convert_to(envelope.sender_user_id, 'UTF8'), 'hex'),
           encode(convert_to(COALESCE(envelope.sender_assignment_id::text, ''), 'UTF8'), 'hex'),
           encode(convert_to(COALESCE(envelope.store_id, ''), 'UTF8'), 'hex'),
           encode(convert_to(envelope.intent_hint, 'UTF8'), 'hex'),
           encode(convert_to(envelope.raw_text, 'UTF8'), 'hex'),
           encode(convert_to(COALESCE(assets.source_asset_ids, ''), 'UTF8'), 'hex')
         ) AS canonical_request
  FROM hxy_inbound_envelopes AS envelope
  LEFT JOIN envelope_assets AS assets
    ON assets.organization_id = envelope.organization_id
   AND assets.envelope_id = envelope.envelope_id
  WHERE envelope.request_fingerprint IS NULL
)
UPDATE hxy_inbound_envelopes AS envelope
SET request_fingerprint = encode(
  digest(convert_to(input.canonical_request, 'UTF8'), 'sha256'),
  'hex'
)
FROM fingerprint_inputs AS input
WHERE envelope.envelope_id = input.envelope_id;

ALTER TABLE hxy_inbound_envelopes
  ALTER COLUMN request_fingerprint SET NOT NULL;

ALTER TABLE hxy_inbound_envelopes
  DROP CONSTRAINT IF EXISTS hxy_inbound_envelopes_request_fingerprint_check;

ALTER TABLE hxy_inbound_envelopes
  ADD CONSTRAINT hxy_inbound_envelopes_request_fingerprint_check
  CHECK (request_fingerprint ~ '^[0-9a-f]{64}$');

CREATE TABLE IF NOT EXISTS hxy_operating_command_receipts (
  command_receipt_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id UUID NOT NULL
    REFERENCES hxy_organizations(organization_id) ON DELETE RESTRICT,
  correlation_id UUID NOT NULL,
  actor_assignment_id UUID NOT NULL,
  command_type TEXT NOT NULL
    CHECK (char_length(btrim(command_type)) BETWEEN 1 AND 100),
  aggregate_type TEXT NOT NULL
    CHECK (aggregate_type IN ('task', 'operating_event')),
  aggregate_id UUID NOT NULL,
  request_fingerprint CHAR(64) NOT NULL
    CHECK (request_fingerprint ~ '^[0-9a-f]{64}$'),
  receipt_json JSONB NOT NULL
    CHECK (jsonb_typeof(receipt_json) = 'object'),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (organization_id, correlation_id),
  CONSTRAINT fk_hxy_operating_command_receipts_actor
    FOREIGN KEY (organization_id, actor_assignment_id)
    REFERENCES hxy_role_assignments(organization_id, assignment_id)
    ON DELETE RESTRICT
);

DROP TRIGGER IF EXISTS trg_hxy_operating_command_receipts_append_only
  ON hxy_operating_command_receipts;
CREATE TRIGGER trg_hxy_operating_command_receipts_append_only
BEFORE UPDATE OR DELETE ON hxy_operating_command_receipts
FOR EACH ROW EXECUTE FUNCTION hxy_reject_operating_history_mutation();

DROP TRIGGER IF EXISTS trg_hxy_operating_command_receipts_no_truncate
  ON hxy_operating_command_receipts;
CREATE TRIGGER trg_hxy_operating_command_receipts_no_truncate
BEFORE TRUNCATE ON hxy_operating_command_receipts
FOR EACH STATEMENT EXECUTE FUNCTION hxy_reject_operating_history_mutation();
