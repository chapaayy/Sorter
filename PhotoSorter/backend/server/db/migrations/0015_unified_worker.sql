-- Stage 3: immutable member origins and safe action/audit state.
ALTER TABLE reference_version_members
 ADD COLUMN IF NOT EXISTS source_kind TEXT NOT NULL DEFAULT 'staged';
ALTER TABLE reference_version_members
 ADD CONSTRAINT reference_version_source_kind_check
 CHECK (source_kind='staged');
ALTER TABLE reference_preparation_jobs ADD COLUMN IF NOT EXISTS stop_requested BOOLEAN NOT NULL DEFAULT FALSE;
CREATE TABLE IF NOT EXISTS reference_preparation_actions (
 job_id UUID NOT NULL REFERENCES reference_preparation_jobs(id) ON DELETE RESTRICT,
 idempotency_key UUID NOT NULL,
 action TEXT NOT NULL CHECK (action IN ('retry','skip')),
 requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(job_id,idempotency_key)
);
CREATE TABLE IF NOT EXISTS reference_preparation_errors (
 job_id UUID NOT NULL REFERENCES reference_preparation_jobs(id) ON DELETE RESTRICT,
 upload_id UUID NOT NULL,
 detail TEXT NOT NULL,
 occurred_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(job_id,upload_id)
);
CREATE INDEX IF NOT EXISTS idx_reference_preparation_errors_job
 ON reference_preparation_errors(job_id);
