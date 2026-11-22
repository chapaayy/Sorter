-- Reference removals are safe FIFO tasks while MegaLoc is busy.
CREATE TABLE IF NOT EXISTS reference_deletion_tasks (
    id UUID PRIMARY KEY,
    reference_id UUID,
    sam TEXT,
    requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error TEXT,
    CHECK ((reference_id IS NULL) <> (sam IS NULL))
);
ALTER TABLE work_queue ADD COLUMN reference_deletion_id UUID UNIQUE
    REFERENCES reference_deletion_tasks(id) ON DELETE RESTRICT;
ALTER TABLE work_queue DROP CONSTRAINT work_queue_payload_check;
ALTER TABLE work_queue ADD CONSTRAINT work_queue_payload_check CHECK (
 (kind='fo_processing' AND fo_run_id IS NOT NULL AND reference_job_id IS NULL
   AND media_batch_id IS NULL AND reference_deletion_id IS NULL)
 OR (kind='reference_preparation' AND reference_job_id IS NOT NULL AND fo_run_id IS NULL
   AND media_batch_id IS NULL AND reference_deletion_id IS NULL)
 OR (kind='media_preparation' AND media_batch_id IS NOT NULL AND media_total_count IS NOT NULL
   AND fo_run_id IS NULL AND reference_job_id IS NULL AND reference_deletion_id IS NULL)
 OR (kind='reference_deletion' AND reference_deletion_id IS NOT NULL
   AND fo_run_id IS NULL AND reference_job_id IS NULL AND media_batch_id IS NULL)
);
