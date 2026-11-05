-- Backfill existing parties without changing IDs, files, or recognition results.
UPDATE batches b SET upload_state=CASE
 WHEN EXISTS (SELECT 1 FROM jobs j WHERE j.batch_id=b.id) THEN 'sealed'
 WHEN EXISTS (SELECT 1 FROM uploads u WHERE u.batch_id=b.id AND u.kind='fo'
              AND NOT u.finalized) THEN 'open'
 WHEN EXISTS (SELECT 1 FROM uploads u WHERE u.batch_id=b.id AND u.kind='fo'
              AND u.finalized) THEN 'ready'
 ELSE 'open' END;
