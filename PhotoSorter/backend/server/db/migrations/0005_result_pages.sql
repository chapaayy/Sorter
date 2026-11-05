CREATE INDEX IF NOT EXISTS idx_uploads_finalized_target
    ON uploads(target_path) WHERE finalized AND kind='fo';
