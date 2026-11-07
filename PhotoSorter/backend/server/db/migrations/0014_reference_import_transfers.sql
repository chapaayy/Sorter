-- Stage 2: isolated reference file transfers, without touching legacy uploads.
ALTER TABLE reference_import_files
 ADD COLUMN IF NOT EXISTS address TEXT;
ALTER TABLE reference_import_files
 ADD COLUMN IF NOT EXISTS received BIGINT NOT NULL DEFAULT 0;
ALTER TABLE reference_import_files
 ADD COLUMN IF NOT EXISTS stored_path TEXT;
ALTER TABLE reference_import_files
 ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
ALTER TABLE reference_import_sessions
 ADD COLUMN IF NOT EXISTS manifest_registered_at TIMESTAMPTZ;
CREATE INDEX IF NOT EXISTS idx_ref_import_files_lookup
 ON reference_import_files(sam,checksum,state);
CREATE INDEX IF NOT EXISTS idx_ref_import_sessions_unfinished
 ON reference_import_sessions(created_at,id) WHERE upload_state='uploading';
