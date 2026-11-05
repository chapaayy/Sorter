-- Additive migration only. Never drop historical jobs, files, or sessions.
ALTER TABLE batches ADD COLUMN IF NOT EXISTS display_name TEXT;
UPDATE batches SET display_name = 'ФО ' || to_char(created_at AT TIME ZONE 'UTC','DD.MM.YYYY HH24:MI')
 WHERE display_name IS NULL;
ALTER TABLE batches ALTER COLUMN display_name SET NOT NULL;
ALTER TABLE batches ADD COLUMN IF NOT EXISTS upload_state TEXT NOT NULL DEFAULT 'open';
ALTER TABLE batches ADD COLUMN IF NOT EXISTS thumbnail_state TEXT NOT NULL DEFAULT 'pending';
ALTER TABLE batches ADD COLUMN IF NOT EXISTS delete_state TEXT NOT NULL DEFAULT 'active';
ALTER TABLE batches ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;
ALTER TABLE batches ADD COLUMN IF NOT EXISTS download_confirmed_at TIMESTAMPTZ;
ALTER TABLE batches ADD COLUMN IF NOT EXISTS confirmed_run_id TEXT;
ALTER TABLE batches ADD COLUMN IF NOT EXISTS delete_after_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_batches_delete_due ON batches(delete_after_at)
 WHERE delete_state = 'active' AND delete_after_at IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_jobs_batch ON jobs(batch_id);
CREATE INDEX IF NOT EXISTS idx_uploads_kind_batch_finalized ON uploads(batch_id, kind, finalized);
CREATE TABLE IF NOT EXISTS batch_operations (
 id UUID PRIMARY KEY,
 batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
 kind TEXT NOT NULL,
 started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 heartbeat_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_batch_operations_batch ON batch_operations(batch_id);
CREATE TABLE IF NOT EXISTS download_confirmations (
 id UUID PRIMARY KEY,
 batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
 run_id TEXT NOT NULL,
 confirmed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 event TEXT NOT NULL DEFAULT 'confirmed'
);
CREATE INDEX IF NOT EXISTS idx_download_confirmations_batch ON download_confirmations(batch_id);
CREATE TABLE IF NOT EXISTS cleanup_tasks (
 batch_id UUID PRIMARY KEY REFERENCES batches(id) ON DELETE CASCADE,
 state TEXT NOT NULL DEFAULT 'pending',
 attempts INTEGER NOT NULL DEFAULT 0,
 error TEXT,
 requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 completed_at TIMESTAMPTZ
);
