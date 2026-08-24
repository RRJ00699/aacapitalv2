-- Permit a conflict handler's identical no-op assignment while preserving
-- append-only/immutable rejection for every material change. This migration is
-- separate so an existing local rehearsal database remains resumable.
DROP TRIGGER decision_history_no_update;
CREATE TRIGGER decision_history_no_update BEFORE UPDATE ON decision_history
WHEN NOT (OLD.id IS NEW.id AND OLD.ipo_id IS NEW.ipo_id AND OLD.layer IS NEW.layer
  AND OLD.decided_at IS NEW.decided_at AND OLD.decision IS NEW.decision
  AND OLD.engine_version IS NEW.engine_version AND OLD.inputs_json IS NEW.inputs_json
  AND OLD.evidence_json IS NEW.evidence_json AND OLD.run_fingerprint IS NEW.run_fingerprint)
BEGIN SELECT RAISE(ABORT,'decision_history is append-only'); END;

DROP TRIGGER raw_objects_no_update;
CREATE TRIGGER raw_objects_no_update BEFORE UPDATE ON raw_objects
WHEN NOT (OLD.sha256 IS NEW.sha256 AND OLD.source_name IS NEW.source_name
  AND OLD.source_object_id IS NEW.source_object_id AND OLD.captured_at IS NEW.captured_at
  AND OLD.size_bytes IS NEW.size_bytes AND OLD.payload_json IS NEW.payload_json)
BEGIN SELECT RAISE(ABORT,'raw_objects is immutable'); END;
