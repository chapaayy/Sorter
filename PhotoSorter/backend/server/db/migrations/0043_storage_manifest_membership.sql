-- Keep manifest membership evidence in the one observed-path registry.
ALTER TABLE storage_files ADD COLUMN manifest_generation UUID;
CREATE INDEX storage_files_run_media ON storage_files(run_id,id) WHERE category='result_media';
ALTER TABLE storage_result_issues DROP CONSTRAINT storage_result_issues_issue_check;
ALTER TABLE storage_result_issues ADD CONSTRAINT storage_result_issues_issue_check
 CHECK(issue IN ('missing_result_media','invalid_result_media','unreadable_result_media','invalid_result_manifest','unlisted_result_media'));
