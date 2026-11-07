-- Durable explicit ZIP-only retries: no MegaLoc recomputation.
CREATE TABLE IF NOT EXISTS archive_retries (
 run_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
 batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
 state TEXT NOT NULL DEFAULT 'pending'
   CHECK (state IN ('pending','running','completed','failed')),
 error TEXT,
 requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 finished_at TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_archive_retries_active ON archive_retries(requested_at)
 WHERE state IN ('pending','running');
