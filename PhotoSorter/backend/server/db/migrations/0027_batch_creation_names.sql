ALTER TABLE batches ADD COLUMN IF NOT EXISTS creation_request_id UUID;
CREATE UNIQUE INDEX IF NOT EXISTS idx_batches_creation_request ON batches(creation_request_id)
    WHERE creation_request_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_batches_visible_name ON batches(lower(display_name))
    WHERE delete_state <> 'deleted';
