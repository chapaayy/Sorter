-- Portable imports preserve old labels; the normal UI still accepts only A/B presets.
ALTER TABLE reference_import_files DROP CONSTRAINT IF EXISTS reference_import_files_side_check;
ALTER TABLE reference_import_files ADD CONSTRAINT reference_import_files_side_check CHECK (side IS NULL OR char_length(side) BETWEEN 1 AND 60);
