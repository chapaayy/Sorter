-- Keep the last fully prepared layout immutable while a newer original is queued.
ALTER TABLE ad_layouts ADD COLUMN IF NOT EXISTS published_snapshot JSONB;
