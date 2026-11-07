-- Stage 1: append-only reference memberships and a single published pointer.
CREATE TABLE IF NOT EXISTS reference_library_versions (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 version_number BIGINT NOT NULL UNIQUE CHECK (version_number >= 1),
 manifest_digest TEXT NOT NULL CHECK (manifest_digest ~ '^[0-9a-f]{64}$'),
 model_signature TEXT,
 preparation_job_id UUID UNIQUE REFERENCES reference_preparation_jobs(id) ON DELETE RESTRICT,
 published_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS reference_version_members (
 version_id BIGINT NOT NULL REFERENCES reference_library_versions(id) ON DELETE RESTRICT,
 reference_id UUID NOT NULL,
 sam TEXT NOT NULL,
 filename TEXT NOT NULL,
 source_hash TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),
 target_path TEXT NOT NULL,
 declared_size BIGINT NOT NULL CHECK (declared_size > 0),
 PRIMARY KEY(version_id,reference_id)
);
CREATE INDEX IF NOT EXISTS idx_reference_version_members_sam
 ON reference_version_members(version_id,sam);
CREATE TABLE IF NOT EXISTS reference_library_state (
 id SMALLINT PRIMARY KEY CHECK (id=1),
 current_version_id BIGINT REFERENCES reference_library_versions(id) ON DELETE RESTRICT,
 baseline_state TEXT NOT NULL DEFAULT 'pending'
   CHECK (baseline_state IN ('pending','ready','needs_attention')),
 baseline_error TEXT,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO reference_library_state(id) VALUES (1) ON CONFLICT (id) DO NOTHING;
CREATE TABLE IF NOT EXISTS reference_library_events (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 version_id BIGINT NOT NULL REFERENCES reference_library_versions(id) ON DELETE RESTRICT,
 event_kind TEXT NOT NULL,
 actor TEXT NOT NULL DEFAULT 'system',
 details JSONB NOT NULL DEFAULT '{}'::jsonb,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reference_library_events_version
 ON reference_library_events(version_id,id);
CREATE TABLE IF NOT EXISTS library_notice_cursors (
 scope_key TEXT PRIMARY KEY,
 last_fo_upload_version_id BIGINT REFERENCES reference_library_versions(id) ON DELETE RESTRICT,
 last_fo_uploaded_at TIMESTAMPTZ,
 acknowledged_version_id BIGINT REFERENCES reference_library_versions(id) ON DELETE RESTRICT,
 acknowledged_at TIMESTAMPTZ
);
