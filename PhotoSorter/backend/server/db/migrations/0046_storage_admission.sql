-- Limits are opt-in. Upload receipts are durable reservations until finalized/cancelled.
CREATE TABLE storage_limits (
 singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK(singleton),
 personal_enabled BOOLEAN NOT NULL DEFAULT false,
 temporary_limit_bytes BIGINT CHECK(temporary_limit_bytes IS NULL OR temporary_limit_bytes>=0),
 disk_reserve_bytes BIGINT CHECK(disk_reserve_bytes IS NULL OR disk_reserve_bytes>=0)
);
INSERT INTO storage_limits(singleton) VALUES(true);
ALTER TABLE users ADD COLUMN storage_limit_bytes BIGINT CHECK(storage_limit_bytes IS NULL OR storage_limit_bytes>=0);
ALTER TABLE reference_import_files ADD COLUMN storage_admitted BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE storage_reservations ADD COLUMN owner_id BIGINT;
ALTER TABLE storage_reservations ADD COLUMN personal_bytes BIGINT NOT NULL DEFAULT 0 CHECK(personal_bytes>=0);
ALTER TABLE storage_reservations ADD COLUMN temporary_bytes BIGINT NOT NULL DEFAULT 0 CHECK(temporary_bytes>=0);
ALTER TABLE storage_reservations ADD COLUMN work_key TEXT;
ALTER TABLE storage_reservations ADD COLUMN work_tree BOOLEAN NOT NULL DEFAULT false;
ALTER TABLE storage_reservations ADD COLUMN publish_keys TEXT[] NOT NULL DEFAULT '{}';
CREATE INDEX storage_pending_fo ON uploads(batch_id) WHERE NOT finalized AND kind='fo';
CREATE INDEX storage_pending_reference ON reference_import_files(session_id) WHERE state='pending' AND storage_admitted;
