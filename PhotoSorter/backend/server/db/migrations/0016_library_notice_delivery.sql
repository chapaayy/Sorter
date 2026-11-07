-- Stage 4: one completion receipt per FO batch; keep site-wide notice cursor.
-- This is additive and does not rewrite any previous FO or version.
CREATE TABLE IF NOT EXISTS fo_library_upload_receipts (
 batch_id UUID PRIMARY KEY REFERENCES batches(id) ON DELETE CASCADE,
 version_id BIGINT REFERENCES reference_library_versions(id) ON DELETE RESTRICT,
 completed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_fo_library_upload_receipts_completed
 ON fo_library_upload_receipts(completed_at);
