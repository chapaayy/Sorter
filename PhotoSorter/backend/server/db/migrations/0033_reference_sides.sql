-- Optional labels on reference photos; never rewrite immutable reference images.
CREATE TABLE IF NOT EXISTS reference_photo_sides (
    reference_id UUID PRIMARY KEY REFERENCES uploads(id) ON DELETE CASCADE,
    sam TEXT NOT NULL,
    side TEXT NOT NULL CHECK (char_length(side) BETWEEN 1 AND 60),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_reference_photo_sides_sam ON reference_photo_sides(sam);
