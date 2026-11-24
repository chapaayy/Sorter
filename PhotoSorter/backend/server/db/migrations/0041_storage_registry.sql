-- Evidence is per path; inode is sampled evidence, never a permanent object ID.
CREATE TABLE storage_files (
 id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 path TEXT NOT NULL UNIQUE,
 category TEXT NOT NULL,
 scope TEXT NOT NULL,
 owner_id BIGINT,
 batch_id UUID,
 run_id TEXT,
 device BIGINT NOT NULL,
 inode NUMERIC(20,0) NOT NULL,
 logical_bytes BIGINT NOT NULL CHECK(logical_bytes>=0),
 allocated_bytes BIGINT NOT NULL CHECK(allocated_bytes>=0),
 links BIGINT NOT NULL CHECK(links>=0),
 mtime_ns BIGINT NOT NULL,
 ctime_ns BIGINT NOT NULL,
 kind TEXT NOT NULL CHECK(kind IN ('file','symlink','other')),
 issue TEXT,
 seen_generation UUID,
 observed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX storage_files_inode ON storage_files(device,inode);
CREATE INDEX storage_files_owner ON storage_files(owner_id,batch_id);
CREATE INDEX storage_files_generation ON storage_files(seen_generation,id);
CREATE INDEX storage_files_issue ON storage_files(issue) WHERE issue IS NOT NULL;
CREATE TABLE storage_dirty (
 path TEXT PRIMARY KEY,
 subtree BOOLEAN NOT NULL DEFAULT false,
 revision BIGINT NOT NULL DEFAULT 1,
 touched_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX storage_dirty_order ON storage_dirty(touched_at,path);
CREATE TABLE storage_accounting_state (
 singleton BOOLEAN PRIMARY KEY DEFAULT true CHECK(singleton),
 generation UUID,
 started_at TIMESTAMPTZ,
 reconciled_at TIMESTAMPTZ,
 sampled_at TIMESTAMPTZ,
 summary JSONB NOT NULL DEFAULT '{}'::jsonb,
 errors BIGINT NOT NULL DEFAULT 0,
 temporary_peak_bytes BIGINT NOT NULL DEFAULT 0
);
INSERT INTO storage_accounting_state(singleton) VALUES(true);
CREATE TABLE storage_reservations (
 id UUID PRIMARY KEY,
 kind TEXT NOT NULL,
 lease_key BIGINT NOT NULL UNIQUE,
 requested_bytes BIGINT NOT NULL CHECK(requested_bytes>=0),
 created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Only the kernel lease owner can hold a reservation, not a persistent quota.
CREATE VIEW storage_ranked_files AS
 SELECT f.*,
 row_number() OVER(PARTITION BY device,inode ORDER BY
 CASE scope WHEN 'personal' THEN 0 WHEN 'shared' THEN 1 WHEN 'protected' THEN 2
 WHEN 'temporary' THEN 4 ELSE 3 END,
 CASE category WHEN 'fo_original' THEN 0 WHEN 'fo_normalized' THEN 1 ELSE 2 END,path) AS physical_rank,
 row_number() OVER(PARTITION BY device,inode,owner_id ORDER BY
 CASE WHEN scope='personal' AND issue IS NULL THEN 0 ELSE 1 END,path) AS charge_rank
 FROM storage_files f;
CREATE VIEW storage_accounted_files AS SELECT *,
 CASE WHEN physical_rank=1 THEN allocated_bytes ELSE 0 END AS physical_bytes,
 CASE WHEN scope='personal' AND owner_id IS NOT NULL AND issue IS NULL AND charge_rank=1
 THEN greatest(logical_bytes,allocated_bytes) ELSE 0 END AS charged_bytes
 FROM storage_ranked_files;
