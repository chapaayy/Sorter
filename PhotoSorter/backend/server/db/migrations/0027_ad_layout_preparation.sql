-- Advertising layout preparation shares the existing global FIFO and immutable run claims.
ALTER TABLE processing_settings
 ADD COLUMN IF NOT EXISTS ad_grouping_threshold NUMERIC(3,2) NOT NULL DEFAULT 0.81
 CHECK (ad_grouping_threshold BETWEEN 0 AND 1);
ALTER TABLE processing_settings
 ADD COLUMN IF NOT EXISTS ad_matching_threshold NUMERIC(3,2) NOT NULL DEFAULT 0.81
 CHECK (ad_matching_threshold BETWEEN 0 AND 1);
CREATE TABLE ad_layout_prepared_cache (
 cache_key TEXT PRIMARY KEY,
 checksum TEXT NOT NULL,
 dino_signature TEXT NOT NULL,
 ocr_signature TEXT NOT NULL,
 embedding_path TEXT NOT NULL,
 ocr_lines JSONB NOT NULL,
 normalized_text TEXT NOT NULL,
 prepared_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE ad_layouts
 ADD COLUMN IF NOT EXISTS preparation_state TEXT NOT NULL DEFAULT 'queued'
 CHECK (preparation_state IN ('queued','running','completed','failed'));
ALTER TABLE ad_layouts ADD COLUMN IF NOT EXISTS preparation_stage TEXT NOT NULL DEFAULT 'queued';
ALTER TABLE ad_layouts ADD COLUMN IF NOT EXISTS preparation_progress SMALLINT NOT NULL DEFAULT 0;
ALTER TABLE ad_layouts ADD COLUMN IF NOT EXISTS preparation_error TEXT;
ALTER TABLE ad_layouts ADD COLUMN IF NOT EXISTS prepared_key TEXT REFERENCES ad_layout_prepared_cache(cache_key);
ALTER TABLE ad_layouts ADD COLUMN IF NOT EXISTS ocr_corrected_text TEXT;
ALTER TABLE ad_layouts ADD COLUMN IF NOT EXISTS prepared_at TIMESTAMPTZ;
UPDATE ad_layouts SET ocr_corrected_text=expected_text WHERE expected_text<>'';
CREATE TABLE ad_layout_preparation_jobs (
 id UUID PRIMARY KEY,
 layout_id UUID REFERENCES ad_layouts(id) ON DELETE SET NULL,
 checksum TEXT NOT NULL,
 target_path TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'queued'
 CHECK (state IN ('queued','running','completed','failed','stopped','interrupted')),
 progress_stage TEXT NOT NULL DEFAULT 'queued',
 progress_percent SMALLINT NOT NULL DEFAULT 0 CHECK (progress_percent BETWEEN 0 AND 100),
 error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 started_at TIMESTAMPTZ,
 finished_at TIMESTAMPTZ
);
ALTER TABLE work_queue ADD COLUMN IF NOT EXISTS layout_job_id UUID
 UNIQUE REFERENCES ad_layout_preparation_jobs(id) ON DELETE RESTRICT;
ALTER TABLE work_queue DROP CONSTRAINT IF EXISTS work_queue_kind_check;
ALTER TABLE work_queue ADD CONSTRAINT work_queue_kind_check
 CHECK (kind IN ('fo_processing','reference_preparation','layout_preparation'));
ALTER TABLE work_queue DROP CONSTRAINT IF EXISTS work_queue_check;
ALTER TABLE work_queue ADD CONSTRAINT work_queue_check CHECK (
 (kind='fo_processing' AND fo_run_id IS NOT NULL AND reference_job_id IS NULL AND layout_job_id IS NULL)
 OR (kind='reference_preparation' AND reference_job_id IS NOT NULL AND fo_run_id IS NULL AND layout_job_id IS NULL)
 OR (kind='layout_preparation' AND layout_job_id IS NOT NULL AND fo_run_id IS NULL AND reference_job_id IS NULL)
);
CREATE TABLE ad_layout_library_state (
 id SMALLINT PRIMARY KEY CHECK (id=1),
 revision BIGINT NOT NULL DEFAULT 0
);
INSERT INTO ad_layout_library_state(id,revision) VALUES (1,0) ON CONFLICT DO NOTHING;
INSERT INTO ad_layout_preparation_jobs(id,layout_id,checksum,target_path,created_at)
 SELECT gen_random_uuid(),id,checksum,target_path,created_at FROM ad_layouts;
INSERT INTO work_queue(kind,layout_job_id,state,created_at)
 SELECT 'layout_preparation',id,'queued',created_at FROM ad_layout_preparation_jobs;
