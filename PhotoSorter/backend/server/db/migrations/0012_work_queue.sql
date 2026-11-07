-- Stage 1: passive FIFO ledger. Existing worker and /api/runs still use jobs.
CREATE TABLE IF NOT EXISTS work_queue (
 seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 kind TEXT NOT NULL CHECK (kind IN ('fo_processing','reference_preparation')),
 fo_run_id TEXT UNIQUE,
 reference_job_id UUID UNIQUE REFERENCES reference_preparation_jobs(id) ON DELETE RESTRICT,
 state TEXT NOT NULL DEFAULT 'queued'
   CHECK (state IN ('queued','running','completed','completed_with_errors','failed','stopped','interrupted','blocked')),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 started_at TIMESTAMPTZ,
 finished_at TIMESTAMPTZ,
 CHECK (
   (kind='fo_processing' AND fo_run_id IS NOT NULL AND reference_job_id IS NULL)
   OR
   (kind='reference_preparation' AND reference_job_id IS NOT NULL AND fo_run_id IS NULL)
 )
);
CREATE INDEX IF NOT EXISTS idx_work_queue_active
 ON work_queue(seq) WHERE state IN ('queued','running','blocked');
-- Migration is executed under the same advisory lock as existing enqueue.
-- The historical order is created_at, id, even for identical timestamps.
INSERT INTO work_queue(kind,fo_run_id,state,created_at)
 SELECT 'fo_processing',id,'queued',created_at
 FROM jobs WHERE status='queued' ORDER BY created_at,id
 ON CONFLICT (fo_run_id) DO NOTHING;
