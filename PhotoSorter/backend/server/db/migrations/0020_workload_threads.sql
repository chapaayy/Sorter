-- Split worker compute preferences without losing the prior saved CPU limit.
ALTER TABLE processing_settings ADD COLUMN IF NOT EXISTS cpu_mode TEXT NOT NULL DEFAULT 'manual'
 CHECK (cpu_mode IN ('manual','auto'));
ALTER TABLE processing_settings ADD COLUMN IF NOT EXISTS fo_cpu_threads INTEGER
 CHECK (fo_cpu_threads BETWEEN 1 AND 32);
ALTER TABLE processing_settings ADD COLUMN IF NOT EXISTS reference_cpu_threads INTEGER
 CHECK (reference_cpu_threads BETWEEN 1 AND 32);
UPDATE processing_settings
 SET fo_cpu_threads=coalesce(fo_cpu_threads,cpu_threads),
     reference_cpu_threads=coalesce(reference_cpu_threads,cpu_threads)
 WHERE id=1;
ALTER TABLE processing_settings ALTER COLUMN fo_cpu_threads SET NOT NULL;
ALTER TABLE processing_settings ALTER COLUMN reference_cpu_threads SET NOT NULL;
