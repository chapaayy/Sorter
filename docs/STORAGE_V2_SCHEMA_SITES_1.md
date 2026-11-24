# Baseline database relationships, migrations 0001–0019

Pinned SHA: c6d77ebb1c9c80c732df209a17a993dd38ec381f. Candidate fields and constraints from migration text; runtime consumers and semantic lifetime still require review. Not a new schema.

## 0001_batch_lifecycle

Blob `83ab402f8193332f8b451806e345b6986435abd1`.

- L2: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS display_name TEXT;`
- L5: `ALTER TABLE batches ALTER COLUMN display_name SET NOT NULL;`
- L6: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS upload_state TEXT NOT NULL DEFAULT 'open';`
- L7: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS thumbnail_state TEXT NOT NULL DEFAULT 'pending';`
- L8: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS delete_state TEXT NOT NULL DEFAULT 'active';`
- L9: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMPTZ;`
- L10: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS download_confirmed_at TIMESTAMPTZ;`
- L11: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS confirmed_run_id TEXT;`
- L12: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS delete_after_at TIMESTAMPTZ;`
- L15: `CREATE INDEX IF NOT EXISTS idx_jobs_batch ON jobs(batch_id);`
- L16: `CREATE INDEX IF NOT EXISTS idx_uploads_kind_batch_finalized ON uploads(batch_id, kind, finalized);`
- L17: `CREATE TABLE IF NOT EXISTS batch_operations (`
- L18: `id UUID PRIMARY KEY,`
- L19: `batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,`
- L24: `CREATE INDEX IF NOT EXISTS idx_batch_operations_batch ON batch_operations(batch_id);`
- L25: `CREATE TABLE IF NOT EXISTS download_confirmations (`
- L26: `id UUID PRIMARY KEY,`
- L27: `batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,`
- L28: `run_id TEXT NOT NULL,`
- L32: `CREATE INDEX IF NOT EXISTS idx_download_confirmations_batch ON download_confirmations(batch_id);`
- L33: `CREATE TABLE IF NOT EXISTS cleanup_tasks (`
- L34: `batch_id UUID PRIMARY KEY REFERENCES batches(id) ON DELETE CASCADE,`

## 0002_batch_upload_state

Blob `587a4cfc26ee21bf236776cf26e79321f412c36e`.

- L3: `WHEN EXISTS (SELECT 1 FROM jobs j WHERE j.batch_id=b.id) THEN 'sealed'`
- L4: `WHEN EXISTS (SELECT 1 FROM uploads u WHERE u.batch_id=b.id AND u.kind='fo'`
- L6: `WHEN EXISTS (SELECT 1 FROM uploads u WHERE u.batch_id=b.id AND u.kind='fo'`

## 0003_thumbnails_queue

Blob `1330807d731eabbe8227dca84b78be5bb776e98d`.

- L2: `ALTER TABLE uploads ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();`
- L3: `CREATE TABLE IF NOT EXISTS thumbnail_tasks (`
- L4: `upload_id UUID PRIMARY KEY REFERENCES uploads(id) ON DELETE CASCADE,`
- L8: `CHECK(state IN ('queued','running','ready','failed')),`
- L16: `CREATE INDEX IF NOT EXISTS idx_uploads_created_seek ON uploads(kind,batch_id,created_at,id);`
- L18: `INSERT INTO thumbnail_tasks(upload_id,checksum)`
- L21: `ON CONFLICT (upload_id) DO NOTHING;`

## 0004_megaloc_queue

Blob `8ea3508ec1c67fb528e6e0a932124661797f46fd`.

- L2: `ALTER TABLE jobs ADD COLUMN IF NOT EXISTS started_at TIMESTAMPTZ;`
- L3: `ALTER TABLE jobs ADD COLUMN IF NOT EXISTS finished_at TIMESTAMPTZ;`
- L6: `CREATE INDEX IF NOT EXISTS idx_jobs_batch_active ON jobs(batch_id)`

## 0005_result_pages

Blob `99af3ed18419b4b2612b4730fca2b3a19c19dd1a`.

- L2: `ON uploads(target_path) WHERE finalized AND kind='fo';`

## 0006_unfinished_age

Blob `e73e28e69f42dade529274b781bfdcb202498e30`.



## 0007_service_heartbeat

Blob `f58d59c648311b39aeabbb345a9735c1d3f98cef`.

- L2: `CREATE TABLE IF NOT EXISTS service_heartbeats (`
- L3: `service TEXT PRIMARY KEY CHECK(service IN ('megaloc','thumbnail','cleanup')),`
- L4: `instance_id UUID NOT NULL,`

## 0008_reference_constructions

Blob `1d6bf13eeaf09d24ed250b2f10a69edf5c77c381`.

- L2: `CREATE TABLE IF NOT EXISTS reference_constructions (`
- L3: `sam TEXT PRIMARY KEY,`
- L9: `UNIQUE(city_code,construction_number)`

## 0009_batch_upload_manifest

Blob `e3b88442889dd2f48d8abd1790f95dc0fea0ad49`.

- L2: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS upload_manifest_signature TEXT;`
- L3: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS upload_manifest_state TEXT`
- L4: `CHECK (upload_manifest_state IN ('waiting','complete'));`
- L5: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS upload_manifest_completed_at TIMESTAMPTZ;`
- L7: `CREATE TABLE IF NOT EXISTS batch_upload_manifest_files (`
- L8: `batch_id UUID NOT NULL REFERENCES batches(id) ON DELETE CASCADE,`
- L9: `upload_id UUID NOT NULL UNIQUE,`
- L10: `relative_path TEXT NOT NULL,`
- L12: `declared_size BIGINT NOT NULL CHECK (declared_size > 0),`
- L13: `PRIMARY KEY (batch_id, upload_id),`
- L14: `UNIQUE (batch_id, relative_path)`
- L17: `ON batch_upload_manifest_files(batch_id);`

## 0010_auto_processing

Blob `d891dc19d2e30a0c94717e4dc68b8b8f9f210f35`.

- L2: `CREATE TABLE IF NOT EXISTS processing_settings (`
- L3: `id SMALLINT PRIMARY KEY CHECK (id=1),`
- L6: `CHECK (grouping_threshold >= 0.50 AND grouping_threshold <= 0.99),`
- L11: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_process_state TEXT`
- L12: `CHECK (auto_process_state IN ('waiting','queued','cancelled','manual'));`
- L13: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_process_threshold DOUBLE PRECISION`
- L15: `CHECK (auto_process_threshold >= 0.50 AND auto_process_threshold <= 0.99);`
- L16: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_process_run_id TEXT;`
- L17: `ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_process_error TEXT;`

## 0011_reference_sessions

Blob `5db0c81bb5fc9f7d87217b2ce9894591654df806`.

- L2: `CREATE TABLE IF NOT EXISTS reference_import_sessions (`
- L3: `id UUID PRIMARY KEY,`
- L5: `CHECK (upload_state IN ('uploading','complete','cancelled')),`
- L7: `CHECK (preparation_state IN ('pending','queued','running','completed','failed','stopped','interrupted')),`
- L8: `expected_count INTEGER CHECK (expected_count IS NULL OR expected_count >= 0),`
- L9: `manifest_digest TEXT CHECK (manifest_digest IS NULL OR manifest_digest ~ '^[0-9a-f]{64}$'),`
- L14: `CREATE TABLE IF NOT EXISTS reference_import_files (`
- L15: `session_id UUID NOT NULL REFERENCES reference_import_sessions(id) ON DELETE RESTRICT,`
- L16: `upload_id UUID NOT NULL UNIQUE,`
- L18: `relative_path TEXT NOT NULL,`
- L20: `declared_size BIGINT NOT NULL CHECK (declared_size > 0),`
- L21: `checksum TEXT CHECK (checksum IS NULL OR checksum ~ '^[0-9a-f]{64}$'),`
- L23: `CHECK (state IN ('pending','finalized','duplicate')),`
- L24: `PRIMARY KEY(session_id,upload_id),`
- L25: `UNIQUE(session_id,relative_path)`
- L28: `ON reference_import_files(session_id,state);`
- L29: `CREATE TABLE IF NOT EXISTS reference_preparation_jobs (`
- L30: `id UUID PRIMARY KEY,`
- L31: `session_id UUID NOT NULL UNIQUE REFERENCES reference_import_sessions(id) ON DELETE RESTRICT,`
- L33: `CHECK (state IN ('queued','running','completed','failed','stopped','interrupted')),`
- L34: `total_count INTEGER NOT NULL DEFAULT 0 CHECK (total_count >= 0),`
- L35: `completed_count INTEGER NOT NULL DEFAULT 0 CHECK (completed_count >= 0),`
- L36: `failed_count INTEGER NOT NULL DEFAULT 0 CHECK (failed_count >= 0),`
- L37: `model_signature TEXT,`

## 0012_work_queue

Blob `ee5466bee3a2efd95b9bb62d4f618508fac97bd6`.

- L2: `CREATE TABLE IF NOT EXISTS work_queue (`
- L3: `seq BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,`
- L4: `kind TEXT NOT NULL CHECK (kind IN ('fo_processing','reference_preparation')),`
- L5: `fo_run_id TEXT UNIQUE,`
- L6: `reference_job_id UUID UNIQUE REFERENCES reference_preparation_jobs(id) ON DELETE RESTRICT,`
- L8: `CHECK (state IN ('queued','running','completed','completed_with_errors','failed','stopped','interrupted','blocked')),`
- L12: `CHECK (`
- L13: `(kind='fo_processing' AND fo_run_id IS NOT NULL AND reference_job_id IS NULL)`
- L15: `(kind='reference_preparation' AND reference_job_id IS NOT NULL AND fo_run_id IS NULL)`

## 0013_reference_versions_notices

Blob `4f7f1f86408dae64e45a1710f0eb60cae73aab83`.

- L2: `CREATE TABLE IF NOT EXISTS reference_library_versions (`
- L3: `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,`
- L4: `version_number BIGINT NOT NULL UNIQUE CHECK (version_number >= 1),`
- L5: `manifest_digest TEXT NOT NULL CHECK (manifest_digest ~ '^[0-9a-f]{64}$'),`
- L6: `model_signature TEXT,`
- L7: `preparation_job_id UUID UNIQUE REFERENCES reference_preparation_jobs(id) ON DELETE RESTRICT,`
- L10: `CREATE TABLE IF NOT EXISTS reference_version_members (`
- L11: `version_id BIGINT NOT NULL REFERENCES reference_library_versions(id) ON DELETE RESTRICT,`
- L12: `reference_id UUID NOT NULL,`
- L15: `source_hash TEXT NOT NULL CHECK (source_hash ~ '^[0-9a-f]{64}$'),`
- L16: `target_path TEXT NOT NULL,`
- L17: `declared_size BIGINT NOT NULL CHECK (declared_size > 0),`
- L18: `PRIMARY KEY(version_id,reference_id)`
- L21: `ON reference_version_members(version_id,sam);`
- L22: `CREATE TABLE IF NOT EXISTS reference_library_state (`
- L23: `id SMALLINT PRIMARY KEY CHECK (id=1),`
- L24: `current_version_id BIGINT REFERENCES reference_library_versions(id) ON DELETE RESTRICT,`
- L26: `CHECK (baseline_state IN ('pending','ready','needs_attention')),`
- L31: `CREATE TABLE IF NOT EXISTS reference_library_events (`
- L32: `id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,`
- L33: `version_id BIGINT NOT NULL REFERENCES reference_library_versions(id) ON DELETE RESTRICT,`
- L36: `details JSONB NOT NULL DEFAULT '{}'::jsonb,`
- L40: `ON reference_library_events(version_id,id);`
- L41: `CREATE TABLE IF NOT EXISTS library_notice_cursors (`
- L42: `scope_key TEXT PRIMARY KEY,`
- L43: `last_fo_upload_version_id BIGINT REFERENCES reference_library_versions(id) ON DELETE RESTRICT,`
- L45: `acknowledged_version_id BIGINT REFERENCES reference_library_versions(id) ON DELETE RESTRICT,`

## 0014_reference_import_transfers

Blob `66255ed12f3cae284fb9cafaf2f05668e6fbb0bc`.

- L2: `ALTER TABLE reference_import_files`
- L4: `ALTER TABLE reference_import_files`
- L6: `ALTER TABLE reference_import_files`
- L7: `ADD COLUMN IF NOT EXISTS stored_path TEXT;`
- L8: `ALTER TABLE reference_import_files`
- L10: `ALTER TABLE reference_import_sessions`

## 0015_unified_worker

Blob `1ec14718b4cfbf6cf946e17add25707acfddeaba`.

- L2: `ALTER TABLE reference_version_members`
- L4: `ALTER TABLE reference_version_members`
- L6: `CHECK (source_kind='staged');`
- L7: `ALTER TABLE reference_preparation_jobs ADD COLUMN IF NOT EXISTS stop_requested BOOLEAN NOT NULL DEFAULT FALSE;`
- L8: `CREATE TABLE IF NOT EXISTS reference_preparation_actions (`
- L9: `job_id UUID NOT NULL REFERENCES reference_preparation_jobs(id) ON DELETE RESTRICT,`
- L11: `action TEXT NOT NULL CHECK (action IN ('retry','skip')),`
- L13: `PRIMARY KEY(job_id,idempotency_key)`
- L15: `CREATE TABLE IF NOT EXISTS reference_preparation_errors (`
- L16: `job_id UUID NOT NULL REFERENCES reference_preparation_jobs(id) ON DELETE RESTRICT,`
- L17: `upload_id UUID NOT NULL,`
- L20: `PRIMARY KEY(job_id,upload_id)`
- L23: `ON reference_preparation_errors(job_id);`

## 0016_library_notice_delivery

Blob `2f560b229471e32552b0a79ef1fef0393a204382`.

- L3: `CREATE TABLE IF NOT EXISTS fo_library_upload_receipts (`
- L4: `batch_id UUID PRIMARY KEY REFERENCES batches(id) ON DELETE CASCADE,`
- L5: `version_id BIGINT REFERENCES reference_library_versions(id) ON DELETE RESTRICT,`

## 0018_cpu_threads

Blob `7657e8f26cbd131bc6f1274a84228c6ee2cc6328`.

- L2: `ALTER TABLE processing_settings`
- L4: `CHECK (cpu_threads BETWEEN 1 AND 32);`

## 0019_retention_preferences

Blob `b79f67de89d29fe950a5b6271251bfc5aedbdad4`.

- L2: `CREATE TABLE IF NOT EXISTS retention_preferences (`
- L3: `id SMALLINT PRIMARY KEY CHECK (id=1),`
- L5: `value INTEGER NOT NULL DEFAULT 2 CHECK (value BETWEEN 1 AND 525600),`
- L6: `unit TEXT NOT NULL DEFAULT 'months' CHECK (unit IN ('minutes','hours','days','months')),`
- L9: `INSERT INTO retention_preferences(id,enabled,value,unit)`

Failed fetches: none
