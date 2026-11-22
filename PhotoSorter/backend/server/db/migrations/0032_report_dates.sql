-- Each batch has one report date. Processing date is resolved per run at ZIP export.
ALTER TABLE batches ADD COLUMN report_date DATE;
ALTER TABLE batches ADD COLUMN report_date_mode TEXT NOT NULL DEFAULT 'processing'
    CHECK (report_date_mode IN ('manual','processing'));
ALTER TABLE batches ADD CONSTRAINT batches_report_date_mode_check CHECK (
    (report_date_mode='manual' AND report_date IS NOT NULL) OR
    (report_date_mode='processing' AND report_date IS NULL)
);
