-- A manually created empty construction is valid before the first reference photo.
-- Existing standard names and immutable reference versions remain unchanged.
ALTER TABLE reference_constructions ALTER COLUMN city_code DROP NOT NULL;
ALTER TABLE reference_constructions ALTER COLUMN construction_number DROP NOT NULL;
ALTER TABLE reference_constructions ALTER COLUMN address DROP NOT NULL;
ALTER TABLE reference_constructions ADD COLUMN IF NOT EXISTS kind TEXT NOT NULL DEFAULT 'standard'
 CHECK (kind IN ('standard','custom'));
