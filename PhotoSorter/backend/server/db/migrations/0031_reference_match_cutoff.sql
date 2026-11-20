-- Conservative per-photo matching gate; 0.000 keeps all historical behavior.
-- Applied to future jobs only. Grouping threshold (0.50 .. 0.99) is independent.
ALTER TABLE processing_settings
    ADD COLUMN IF NOT EXISTS min_match_score DOUBLE PRECISION NOT NULL DEFAULT 0.000
    CHECK (min_match_score >= 0.000 AND min_match_score <= 1.000);
