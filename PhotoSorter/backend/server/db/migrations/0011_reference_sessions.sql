-- Stage 1: durable session and preparation records, deliberately inactive.
CREATE TABLE IF NOT EXISTS reference_import_sessions (
 id UUID PRIMARY KEY,
 upload_state TEXT NOT NULL DEFAULT 'uploading'
   CHECK (upload_state IN ('uploading','complete','cancelled')),
 preparation_state TEXT NOT NULL DEFAULT 'pending'
   CHECK (preparation_state IN ('pending','queued','running','completed','failed','stopped','interrupted')),
 expected_count INTEGER CHECK (expected_count IS NULL OR expected_count >= 0),
 manifest_digest TEXT CHECK (manifest_digest IS NULL OR manifest_digest ~ '^[0-9a-f]{64}$'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 completed_at TIMESTAMPTZ,
 error TEXT
);
CREATE TABLE IF NOT EXISTS reference_import_files (
 session_id UUID NOT NULL REFERENCES reference_import_sessions(id) ON DELETE RESTRICT,
 upload_id UUID NOT NULL UNIQUE,
 sam TEXT NOT NULL,
 relative_path TEXT NOT NULL,
 filename TEXT NOT NULL,
 declared_size BIGINT NOT NULL CHECK (declared_size > 0),
 checksum TEXT CHECK (checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'),
 state TEXT NOT NULL DEFAULT 'pending'
   CHECK (state IN ('pending','finalized','duplicate')),
 PRIMARY KEY(session_id,upload_id),
 UNIQUE(session_id,relative_path)
);
CREATE INDEX IF NOT EXISTS idx_reference_import_files_session_state
 ON reference_import_files(session_id,state);
CREATE TABLE IF NOT EXISTS reference_preparation_jobs (
 id UUID PRIMARY KEY,
 session_id UUID NOT NULL UNIQUE REFERENCES reference_import_sessions(id) ON DELETE RESTRICT,
 state TEXT NOT NULL DEFAULT 'queued'
   CHECK (state IN ('queued','running','completed','failed','stopped','interrupted')),
 total_count INTEGER NOT NULL DEFAULT 0 CHECK (total_count >= 0),
 completed_count INTEGER NOT NULL DEFAULT 0 CHECK (completed_count >= 0),
 failed_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),
 model_signature TEXT,
 error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 started_at TIMESTAMPTZ,
 finished_at TIMESTAMPTZ,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reference_preparation_jobs_state
 ON reference_preparation_jobs(state,created_at);
