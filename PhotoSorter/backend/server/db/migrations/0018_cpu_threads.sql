-- One persisted CPU preference; no fallback workers or alternative pathways.
ALTER TABLE processing_settings
ADD COLUMN IF NOT EXISTS cpu_threads INTEGER NOT NULL DEFAULT 7
CHECK (cpu_threads BETWEEN 1 AND 32);
