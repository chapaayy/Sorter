-- Physical screen identity is independent from the reference photo and its camera angle.
CREATE TABLE reference_screens (
 id UUID PRIMARY KEY,
 sam TEXT NOT NULL REFERENCES reference_constructions(sam) ON DELETE CASCADE,
 name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 80),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_reference_screens_sam ON reference_screens(sam);
CREATE TABLE reference_screen_annotations (
 id UUID PRIMARY KEY,
 screen_id UUID NOT NULL REFERENCES reference_screens(id) ON DELETE CASCADE,
 reference_id UUID NOT NULL REFERENCES uploads(id) ON DELETE CASCADE,
 corners JSONB NOT NULL,
 band_width_px DOUBLE PRECISION NOT NULL CHECK (band_width_px > 0),
 source_sha256 TEXT NOT NULL,
 image_width INTEGER NOT NULL CHECK (image_width > 0),
 image_height INTEGER NOT NULL CHECK (image_height > 0),
 version INTEGER NOT NULL DEFAULT 1 CHECK (version > 0),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 UNIQUE(screen_id,reference_id)
);
CREATE INDEX idx_screen_annotations_reference ON reference_screen_annotations(reference_id);
