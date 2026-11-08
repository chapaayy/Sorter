-- Retire immutable originals only after all retained run snapshots release them.
CREATE TABLE ad_layout_retired_assets (
 target_path TEXT PRIMARY KEY,
 checksum TEXT NOT NULL,
 retired_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
