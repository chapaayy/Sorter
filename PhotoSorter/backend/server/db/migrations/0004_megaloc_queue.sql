-- Queue metadata — no historical job rewrite or loss of prior runs.
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_jobs_queue_order ON jobs(created_at,id)
 WHERE status='queued';
CREATE INDEX IF NOT EXISTS idx_jobs_batch_active ON jobs(batch_id)
 WHERE status IN ('queued','running','stopping');
