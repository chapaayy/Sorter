-- Single authoritative FIFO ledger for FO and reference preparation.
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
