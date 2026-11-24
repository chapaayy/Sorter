-- Only discrepancies are persisted: the immutable JSONL is still authoritative.
CREATE TABLE storage_result_issues (
 path TEXT PRIMARY KEY,
 run_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
 issue TEXT NOT NULL CHECK(issue IN ('missing_result_media','invalid_result_media','unreadable_result_media','invalid_result_manifest')),
 generation UUID NOT NULL,
 observed_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX storage_result_issues_run ON storage_result_issues(run_id);
