-- Real stage reporting; existing preparation counters remain authoritative.
ALTER TABLE reference_preparation_jobs ADD COLUMN IF NOT EXISTS progress_stage TEXT
  NOT NULL DEFAULT 'queued'
  CHECK (progress_stage IN ('queued','validating','loading','extracting','publishing','completed'));
