ALTER TABLE storage_accounting_state ADD COLUMN requested_at TIMESTAMPTZ;
CREATE TABLE storage_maintenance (
 kind TEXT PRIMARY KEY CHECK(kind IN ('expired_archives','unused_thumbnails','abandoned_scratch')),
 state TEXT NOT NULL CHECK(state IN ('queued','running','completed','failed','interrupted')),
 requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 started_at TIMESTAMPTZ,
 finished_at TIMESTAMPTZ,
 removed BIGINT,
 detail TEXT
);
