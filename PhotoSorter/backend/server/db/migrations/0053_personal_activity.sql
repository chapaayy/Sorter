-- Shared library data remains shared. Only record who initiated NEW work.
ALTER TABLE reference_import_sessions ADD COLUMN requested_by BIGINT REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE reference_deletion_tasks ADD COLUMN requested_by BIGINT REFERENCES users(id) ON DELETE SET NULL;
CREATE INDEX idx_reference_import_requester ON reference_import_sessions(requested_by);
CREATE INDEX idx_reference_deletion_requester ON reference_deletion_tasks(requested_by);
-- ZIP preparation is an HTTP operation, not a second compute queue.
CREATE TABLE favicon_archive_activity (
 id UUID PRIMARY KEY,
 actor_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
 kind TEXT NOT NULL CHECK (kind IN ('results','references')),
 state TEXT NOT NULL CHECK (state IN ('running','completed','failed')),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_favicon_archive_actor ON favicon_archive_activity(actor_id,updated_at);
CREATE INDEX idx_favicon_archive_expiry ON favicon_archive_activity(updated_at);
