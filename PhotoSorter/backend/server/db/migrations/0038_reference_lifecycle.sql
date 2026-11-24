-- New installation only: explicit job version pin and retained metadata headers.
ALTER TABLE reference_library_versions ADD COLUMN superseded_at TIMESTAMPTZ;
ALTER TABLE reference_library_versions ADD COLUMN members_retired_at TIMESTAMPTZ;
ALTER TABLE jobs ADD COLUMN reference_version_id BIGINT REFERENCES reference_library_versions(id) ON DELETE RESTRICT;
CREATE INDEX idx_jobs_pinned_reference_version ON jobs(reference_version_id);
CREATE INDEX idx_ref_members_digest ON reference_version_members(source_hash);
CREATE INDEX idx_ref_import_digest ON reference_import_files(checksum);
CREATE INDEX idx_ref_upload_digest ON uploads(checksum) WHERE kind='reference' AND finalized;
CREATE TABLE reference_physical_objects (
 source_hash TEXT PRIMARY KEY CHECK (source_hash ~ '^[0-9a-f]{64}$'),
 declared_size BIGINT NOT NULL CHECK (declared_size>0),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 unowned_since TIMESTAMPTZ
);
ALTER TABLE reference_cache ADD COLUMN unowned_since TIMESTAMPTZ;
CREATE TABLE thumbnail_gc_candidates (
 scope_key TEXT NOT NULL,
 checksum TEXT NOT NULL CHECK (checksum ~ '^[0-9a-f]{64}$'),
 version INTEGER NOT NULL,
 unowned_since TIMESTAMPTZ NOT NULL DEFAULT now(),
 PRIMARY KEY(scope_key,checksum,version)
);
CREATE VIEW reference_live_hashes AS
 SELECT source_hash FROM reference_version_members
 UNION SELECT checksum FROM uploads WHERE kind='reference' AND finalized AND checksum IS NOT NULL
 UNION SELECT f.checksum FROM reference_import_files f JOIN reference_import_sessions s ON s.id=f.session_id
 WHERE f.checksum IS NOT NULL AND s.upload_state<>'cancelled' AND s.preparation_state NOT IN ('completed','stopped');
