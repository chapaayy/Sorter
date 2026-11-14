-- Null denotes a verified, MegaLoc-compatible image (including existing rows).
ALTER TABLE uploads ADD COLUMN IF NOT EXISTS original_media_type TEXT;
