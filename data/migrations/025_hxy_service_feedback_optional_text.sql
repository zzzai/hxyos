ALTER TABLE hxy_service_feedback
  DROP CONSTRAINT IF EXISTS hxy_service_feedback_feedback_text_check;

ALTER TABLE hxy_service_feedback
  DROP CONSTRAINT IF EXISTS chk_hxy_service_feedback_text_length;

ALTER TABLE hxy_service_feedback
  ADD CONSTRAINT chk_hxy_service_feedback_text_length
  CHECK (char_length(btrim(feedback_text)) BETWEEN 0 AND 4000);
