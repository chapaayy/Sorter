-- Layouts are independent from MegaLoc reference constructions and photo batches.
-- A layout image is immutable; metadata revisions do not overwrite its bytes.
CREATE TABLE ad_layouts (
 id UUID PRIMARY KEY,
 name TEXT NOT NULL CHECK (char_length(name) BETWEEN 1 AND 120),
 filename TEXT NOT NULL,
 checksum TEXT NOT NULL UNIQUE CHECK (char_length(checksum)=64),
 target_path TEXT NOT NULL,
 byte_size BIGINT NOT NULL CHECK (byte_size>0 AND byte_size<=20971520),
 expected_text TEXT NOT NULL DEFAULT '',
 active BOOLEAN NOT NULL DEFAULT true,
 version INTEGER NOT NULL DEFAULT 1 CHECK(version>=1),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_ad_layouts_active ON ad_layouts(active,created_at);
