-- Add only metadata; existing staged objects and sessions remain valid.
ALTER TABLE reference_import_files ADD COLUMN IF NOT EXISTS side TEXT CHECK (side IN ('A','A1','A2','A3','B','B1','B2','B3'));
