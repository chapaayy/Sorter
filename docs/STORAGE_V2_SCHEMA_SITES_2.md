# Baseline database relationships, migrations 0020–0036

Pinned SHA: c6d77ebb1c9c80c732df209a17a993dd38ec381f. Candidate fields and constraints from migration text; runtime consumers and semantic lifetime still require review. Not a new schema.

## 0020_workload_threads

Blob `a38b98f8b17b852702c09ce09f325536f40ffc8e`.

- L2: `ALTER TABLE processing_settings ADD COLUMN IF NOT EXISTS cpu_mode TEXT NOT NULL DEFAULT 'manual'`
- L3: `CHECK (cpu_mode IN ('manual','auto'));`
- L4: `ALTER TABLE processing_settings ADD COLUMN IF NOT EXISTS fo_cpu_threads INTEGER`
- L5: `CHECK (fo_cpu_threads BETWEEN 1 AND 32);`
- L6: `ALTER TABLE processing_settings ADD COLUMN IF NOT EXISTS reference_cpu_threads INTEGER`
- L7: `CHECK (reference_cpu_threads BETWEEN 1 AND 32);`
- L12: `ALTER TABLE processing_settings ALTER COLUMN fo_cpu_threads SET NOT NULL;`
- L13: `ALTER TABLE processing_settings ALTER COLUMN reference_cpu_threads SET NOT NULL;`

## 0021_archive_retry

Blob `23e4090e9c5feabcaa99fccee5227e33b1a75cf7`.

- L2: `CREATE TABLE IF NOT EXISTS archive_retries (`
- L3: `run_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,`
- L4: `batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,`
- L6: `CHECK (state IN ('pending','running','completed','failed')),`

## 0022_custom_constructions

Blob `89e1729493518420a548da5838d67d7602357160`.

- L3: `ALTER TABLE reference_constructions ALTER COLUMN city_code DROP NOT NULL;`
- L4: `ALTER TABLE reference_constructions ALTER COLUMN construction_number DROP NOT NULL;`
- L5: `ALTER TABLE reference_constructions ALTER COLUMN address DROP NOT NULL;`
- L6: `ALTER TABLE reference_constructions ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'standard'`
- L7: `CHECK (kind IN ('standard','custom'));`

## 0023_admin_env_password

Blob `0f62936109f67db7dd57aeedd92158657bb9a78a`.

- L2: `ALTER TABLE users ALTER COLUMN password_salt DROP NOT NULL;`
- L3: `ALTER TABLE users ALTER COLUMN password_hash DROP NOT NULL;`
- L4: `UPDATE users SET password_salt=NULL, password_hash=NULL WHERE username='admin';`

## 0024_access_requests

Blob `fe83a0cce94c8a7fde41a926e9fc9a9671920216`.

- L1: `ALTER TABLE users ADD COLUMN IF NOT EXISTS access_role TEXT NOT NULL DEFAULT 'viewer'`
- L2: `CHECK (access_role IN ('owner', 'viewer'));`
- L5: `CREATE TABLE IF NOT EXISTS access_requests (`
- L6: `id UUID PRIMARY KEY,`
- L10: `password_hash TEXT,`
- L11: `status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),`
- L14: `CHECK ((status='pending' AND password_salt IS NOT NULL AND password_hash IS NOT NULL AND decided_at IS NULL)`
- L15: `OR (status<>'pending' AND password_salt IS NULL AND password_hash IS NULL AND decided_at IS NOT NULL))`
- L17: `CREATE UNIQUE INDEX IF NOT EXISTS access_requests_one_pending_email`
- L21: `CREATE TABLE IF NOT EXISTS result_access_grants (`
- L22: `user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,`
- L23: `run_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,`
- L24: `PRIMARY KEY (user_id, run_id)`

## 0025_fo_original_media

Blob `9da6f1e1b43659b65ef07c87173fdeaaee1a1290`.

- L2: `ALTER TABLE uploads ADD COLUMN IF NOT EXISTS original_media_type TEXT;`

## 0026_cleanup_progress

Blob `fa11decee59317433fd2bef5e93d8e92d2cbd269`.

- L2: `ALTER TABLE cleanup_tasks ADD COLUMN IF NOT EXISTS progress JSONB;`

## 0027_batch_creation_names

Blob `9210187f761e0a5d792c4b1d0dcda13269f69544`.

- L1: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS creation_request_id UUID;`
- L2: `CREATE UNIQUE INDEX IF NOT EXISTS idx_batches_creation_request ON batches(creation_request_id)`
- L3: `WHERE creation_request_id IS NOT NULL;`

## 0028_owner_session_rotation

Blob `fe2520a2cf4836fb50fd4a5ca38a47a5b4f7e0a3`.

- L2: `CREATE TABLE IF NOT EXISTS owner_session_credential (`
- L3: `user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,`

## 0029_batch_media

Blob `58b3432f346847eca83a6686e9b8fe2d2381efc5`.

- L2: `ALTER TABLE batches ADD COLUMN media_image_format TEXT CHECK (media_image_format IN ('jpg','png'));`
- L3: `ALTER TABLE batches ADD COLUMN media_video_format TEXT CHECK (media_video_format IN ('mp4','webm'));`
- L4: `ALTER TABLE uploads ADD COLUMN media_action TEXT CHECK (media_action IN ('keep','prepare'));`
- L5: `ALTER TABLE uploads ADD COLUMN media_output_path TEXT;`
- L6: `ALTER TABLE uploads ADD COLUMN media_error TEXT;`
- L7: `ALTER TABLE uploads ADD COLUMN media_duration DOUBLE PRECISION;`
- L9: `ALTER TABLE work_queue`
- L10: `ADD COLUMN media_batch_id UUID REFERENCES batches(id) ON DELETE CASCADE,`
- L11: `ADD COLUMN media_total_count INTEGER CHECK (media_total_count > 0),`
- L15: `ALTER TABLE work_queue DROP CONSTRAINT work_queue_kind_check;`
- L16: `ALTER TABLE work_queue DROP CONSTRAINT work_queue_check;`
- L17: `ALTER TABLE work_queue ADD CONSTRAINT work_queue_payload_check CHECK (`
- L18: `(kind='fo_processing' AND fo_run_id IS NOT NULL AND reference_job_id IS NULL AND media_batch_id IS NULL)`
- L19: `OR (kind='reference_preparation' AND reference_job_id IS NOT NULL AND fo_run_id IS NULL AND media_batch_id IS NULL)`
- L20: `OR (kind='media_preparation' AND media_batch_id IS NOT NULL AND media_total_count IS NOT NULL AND fo_run_id IS NULL AND reference_job_id IS NULL)`
- L22: `CREATE INDEX work_queue_media_history ON work_queue(media_batch_id,seq DESC) WHERE media_batch_id IS NOT NULL;`
- L23: `CREATE UNIQUE INDEX work_queue_media_once_active ON work_queue(media_batch_id)`

## 0030_media_eta

Blob `6a66d768b09ff87f005b41ea78be1a5891666a43`.

- L1: `ALTER TABLE work_queue`

## 0031_reference_match_cutoff

Blob `9ca56b5feed121e419de78217bca525274c032c8`.

- L3: `ALTER TABLE processing_settings`
- L5: `CHECK (min_match_score >= 0.000 AND min_match_score <= 1.000);`

## 0032_report_dates

Blob `c419901e60c82ec50de97848d317c10b6d90c01b`.

- L2: `ALTER TABLE batches ADD COLUMN report_date DATE;`
- L3: `ALTER TABLE batches ADD COLUMN report_date_mode TEXT NOT NULL DEFAULT 'processing'`
- L4: `CHECK (report_date_mode IN ('manual','processing'));`
- L5: `ALTER TABLE batches ADD CONSTRAINT batches_report_date_consistency_check CHECK (`

## 0033_reference_sides

Blob `6c9e7fb4f1b61a0cc250d11c4ee35f10afe4c38b`.

- L2: `CREATE TABLE IF NOT EXISTS reference_photo_sides (`
- L3: `reference_id UUID PRIMARY KEY REFERENCES uploads(id) ON DELETE CASCADE,`
- L5: `side TEXT NOT NULL CHECK (char_length(side) BETWEEN 1 AND 60),`

## 0034_reference_deletions

Blob `641ee68c389656f6a8fb3e27c75754d922680851`.

- L2: `CREATE TABLE IF NOT EXISTS reference_deletion_tasks (`
- L3: `id UUID PRIMARY KEY,`
- L4: `reference_id UUID,`
- L8: `CHECK ((reference_id IS NULL) <> (sam IS NULL))`
- L10: `ALTER TABLE work_queue ADD COLUMN reference_deletion_id UUID UNIQUE`
- L11: `REFERENCES reference_deletion_tasks(id) ON DELETE RESTRICT;`
- L12: `ALTER TABLE work_queue DROP CONSTRAINT work_queue_payload_check;`
- L13: `ALTER TABLE work_queue ADD CONSTRAINT work_queue_payload_check CHECK (`
- L14: `(kind='fo_processing' AND fo_run_id IS NOT NULL AND reference_job_id IS NULL`
- L15: `AND media_batch_id IS NULL AND reference_deletion_id IS NULL)`
- L16: `OR (kind='reference_preparation' AND reference_job_id IS NOT NULL AND fo_run_id IS NULL`
- L17: `AND media_batch_id IS NULL AND reference_deletion_id IS NULL)`
- L18: `OR (kind='media_preparation' AND media_batch_id IS NOT NULL AND media_total_count IS NOT NULL`
- L19: `AND fo_run_id IS NULL AND reference_job_id IS NULL AND reference_deletion_id IS NULL)`
- L20: `OR (kind='reference_deletion' AND reference_deletion_id IS NOT NULL`
- L21: `AND fo_run_id IS NULL AND reference_job_id IS NULL AND media_batch_id IS NULL)`

## 0035_reference_side_labels

Blob `407ba387a9ccb92f76a5d30ae346d259a6453170`.

- L5: `SELECT reference_id, upper(btrim(side)) AS old_side`
- L13: `WHERE s.reference_id = n.reference_id`

## 0036_regions

Blob `38a612fb7877d47c7374d2ccfde38f34fac72dd4`.

- L2: `CREATE TABLE IF NOT EXISTS reference_regions (`
- L3: `code TEXT PRIMARY KEY CHECK (code ~ '^[A-Z]{2,5}$'),`
- L14: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_process_regions JSONB`
- L15: `CHECK (auto_process_regions IS NULL OR jsonb_typeof(auto_process_regions)='array');`

Failed fetches: none
