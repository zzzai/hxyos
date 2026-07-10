ALTER TABLE staff_sessions
  ADD COLUMN IF NOT EXISTS assignment_id UUID;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM pg_constraint
    WHERE conname = 'fk_staff_sessions_hxy_assignment'
      AND conrelid = 'staff_sessions'::regclass
  ) THEN
    ALTER TABLE staff_sessions
      ADD CONSTRAINT fk_staff_sessions_hxy_assignment
      FOREIGN KEY (assignment_id)
      REFERENCES hxy_role_assignments(assignment_id)
      ON DELETE CASCADE;
  END IF;
END
$$;

CREATE INDEX IF NOT EXISTS idx_staff_sessions_assignment_expires
  ON staff_sessions (assignment_id, expires_at)
  WHERE assignment_id IS NOT NULL;
