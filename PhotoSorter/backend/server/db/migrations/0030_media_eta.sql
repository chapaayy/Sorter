ALTER TABLE work_queue
 ADD COLUMN media_progress_percent DOUBLE PRECISION,
 ADD COLUMN media_eta_seconds DOUBLE PRECISION,
 ADD COLUMN media_current_file TEXT;
