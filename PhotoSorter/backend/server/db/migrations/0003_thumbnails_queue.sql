-- Durable, additive, foreign-key-owned preview queue — legacy rows backfilled.
ALTER TABLE uploads ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NOT NULL DEFAULT now();
CREATE TABLE IF NOT EXISTS thumbnail_tasks (
 upload_id UUID PRIMARY KEY REFERENCES uploads(id) ON DELETE CASCADE,
 checksum TEXT NOT NULL,
 version INTEGER NOT NULL DEFAULT 1,
 state TEXT NOT NULL DEFAULT 'queued'
    CHECK(state IN ('queued','running','ready','failed')),
 attempts INTEGER NOT NULL DEFAULT 0,
 lease_until TIMESTAMPTZ,
 last_error TEXT,
 created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_thumbnail_tasks_claim ON thumbnail_tasks(state, lease_until, created_at);
CREATE INDEX IF NOT EXISTS idx_uploads_created_seek ON uploads(kind,batch_id,created_at,id);
CREATE INDEX IF NOT EXISTS idx_uploads_sam_seek ON uploads(kind,sam,created_at,id);
INSERT INTO thumbnail_tasks(upload_id,checksum)
 SELECT id,checksum FROM uploads
 WHERE finalized AND checksum ~ '^[0-9a-f]{64}$'
 ON CONFLICT (upload_id) DO NOTHING;
