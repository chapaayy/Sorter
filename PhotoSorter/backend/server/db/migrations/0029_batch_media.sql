-- Output profiles are opt-in per immutable upload manifest. Previous reports remain unchanged.
ALTER TABLE batches ADD COLUMN media_image_format TEXT CHECK (media_image_format IN ('jpg','png'));
ALTER TABLE batches ADD COLUMN media_video_format TEXT CHECK (media_video_format IN ('mp4','webm'));
ALTER TABLE uploads ADD COLUMN media_action TEXT CHECK (media_action IN ('keep','prepare'));
ALTER TABLE uploads ADD COLUMN media_output_path TEXT;
ALTER TABLE uploads ADD COLUMN media_error TEXT;
ALTER TABLE uploads ADD COLUMN media_duration DOUBLE PRECISION;

ALTER TABLE work_queue
 ADD COLUMN media_batch_id UUID REFERENCES batches(id) ON DELETE CASCADE,
 ADD COLUMN media_total_count INTEGER CHECK (media_total_count > 0),
 ADD COLUMN media_completed_count INTEGER,
 ADD COLUMN media_failed_count INTEGER,
 ADD COLUMN media_error TEXT;
ALTER TABLE work_queue DROP CONSTRAINT work_queue_kind_check;
ALTER TABLE work_queue DROP CONSTRAINT work_queue_check;
ALTER TABLE work_queue ADD CONSTRAINT work_queue_payload_check CHECK (
 (kind='fo_processing' AND fo_run_id IS NOT NULL AND reference_job_id IS NULL AND media_batch_id IS NULL)
 OR (kind='reference_preparation' AND reference_job_id IS NOT NULL AND fo_run_id IS NULL AND media_batch_id IS NULL)
 OR (kind='media_preparation' AND media_batch_id IS NOT NULL AND media_total_count IS NOT NULL AND fo_run_id IS NULL AND reference_job_id IS NULL)
);
CREATE INDEX work_queue_media_history ON work_queue(media_batch_id,seq DESC) WHERE media_batch_id IS NOT NULL;
CREATE UNIQUE INDEX work_queue_media_once_active ON work_queue(media_batch_id)
 WHERE kind='media_preparation' AND state IN ('queued','running');
