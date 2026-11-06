-- New batches opt in; NULL fields mean legacy batch with unchanged semantics.
ALTER TABLE batches ADD COLUMN IF NOT EXISTS upload_manifest_signature TEXT;
ALTER TABLE batches ADD COLUMN IF NOT EXISTS upload_manifest_state TEXT
    CHECK (upload_manifest_state IN ('waiting','complete'));
ALTER TABLE batches ADD COLUMN IF NOT EXISTS upload_manifest_completed_at TIMESTAMPTZ;

CREATE TABLE IF NOT EXISTS batch_upload_manifest_files (
    batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,
    upload_id UUID NOT NULL UNIQUE,
    relative_path TEXT NOT NULL,
    filename TEXT NOT NULL,
    declared_size BIGINT NOT NULL CHECK (declared_size > 0),
    PRIMARY KEY (batch_id, upload_id),
    UNIQUE (batch_id, relative_path)
);
CREATE INDEX IF NOT EXISTS idx_batch_upload_manifest_files_batch
    ON batch_upload_manifest_files(batch_id);
