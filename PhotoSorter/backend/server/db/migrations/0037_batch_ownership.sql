-- Fresh V2 database: existing unowned batches intentionally block activation.
ALTER TABLE batches ADD COLUMN owner_id BIGINT NOT NULL REFERENCES users(id) ON DELETE RESTRICT;
CREATE INDEX idx_batches_owner_id ON batches(owner_id);
