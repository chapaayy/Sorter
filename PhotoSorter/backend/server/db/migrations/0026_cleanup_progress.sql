-- Progress of the existing background cleanup task, independent of MegaLoc.
ALTER TABLE cleanup_tasks ADD COLUMN IF NOT EXISTS progress JSONB;
