-- Only unfinalized transfers are considered for the thirty-day TTL.
CREATE INDEX IF NOT EXISTS idx_unfinished_upload_age
 ON uploads(updated_at,id) WHERE NOT finalized;
