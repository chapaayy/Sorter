-- Stage 2: opt-in automation for new manifest batches; all historical rows remain disabled.
CREATE TABLE IF NOT EXISTS processing_settings (
    id SMALLINT PRIMARY KEY CHECK (id=1),
    auto_process_new_batches BOOLEAN NOT NULL DEFAULT FALSE,
    grouping_threshold DOUBLE PRECISION NOT NULL DEFAULT 0.50
        CHECK (grouping_threshold >= 0.50 AND grouping_threshold <= 0.99),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO processing_settings (id) VALUES (1) ON CONFLICT (id) DO NOTHING;

ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_process_state TEXT
    CHECK (auto_process_state IN ('waiting','queued','cancelled','manual'));
ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_process_threshold DOUBLE PRECISION
    NOT NULL DEFAULT 0.50
    CHECK (auto_process_threshold >= 0.50 AND auto_process_threshold <= 0.99);
ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_process_run_id TEXT;
ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_process_error TEXT;
CREATE INDEX IF NOT EXISTS idx_batches_auto_processing_waiting
    ON batches(upload_manifest_completed_at, id)
    WHERE auto_process_state='waiting' AND upload_manifest_state='complete'
        AND delete_state='active';
