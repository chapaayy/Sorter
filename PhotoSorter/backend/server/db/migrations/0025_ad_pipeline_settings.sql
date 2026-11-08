-- Explicit opt-in for the integrated CPU pipeline. Existing beta jobs remain MegaLoc-only.
ALTER TABLE processing_settings ADD COLUMN IF NOT EXISTS ad_pipeline_enabled BOOLEAN NOT NULL DEFAULT false;
