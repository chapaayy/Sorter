-- Add a construction registry without changing existing reference IDs or stored files.
CREATE TABLE IF NOT EXISTS reference_constructions (
 sam TEXT PRIMARY KEY,
 city_code TEXT NOT NULL,
 construction_number TEXT NOT NULL,
 address TEXT NOT NULL,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(city_code,construction_number)
);
CREATE INDEX IF NOT EXISTS idx_reference_constructions_city ON reference_constructions(city_code);
