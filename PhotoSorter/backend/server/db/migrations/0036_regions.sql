-- Region codes have no names, and no existing reference IDs or files change.
CREATE TABLE IF NOT EXISTS reference_regions (
 code TEXT PRIMARY KEY CHECK (code ~ '^[A-Z]{2,5}$'),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO reference_regions(code)
 SELECT DISTINCT city_code FROM reference_constructions
 WHERE city_code ~ '^[A-Z]{2,5}$'
 ON CONFLICT DO NOTHING;
INSERT INTO reference_regions(code)
 SELECT DISTINCT split_part(sam,' ',1) FROM uploads
 WHERE kind='reference' AND sam ~ '^[A-Z]{2,5} [0-9]{1,8}$'
 ON CONFLICT DO NOTHING;
ALTER TABLE batches ADD COLUMN IF NOT EXISTS auto_process_regions JSONB
 CHECK (auto_process_regions IS NULL OR jsonb_typeof(auto_process_regions)='array');
