-- Stage 4 upgrade: establish a safe installation-wide starting point from
-- previously completed manifest batches and previously processed legacy FO.
-- Historical exact library revision per FO is not always recoverable; the
-- currently published revision is an explicit migration-time baseline.
-- This statement never overwrites an already established/acknowledged cursor.
WITH previous_fo AS (
  SELECT MAX(completed_at) AS last_uploaded_at FROM (
    SELECT b.upload_manifest_completed_at AS completed_at
    FROM batches b
    WHERE b.upload_manifest_state='complete'
      AND b.upload_manifest_completed_at IS NOT NULL
    UNION ALL
    SELECT MAX(u.updated_at) AS completed_at
    FROM jobs j
    JOIN uploads u ON u.batch_id=j.batch_id
      AND u.kind='fo' AND u.finalized
  ) historical
)
INSERT INTO library_notice_cursors(
  scope_key,last_fo_upload_version_id,last_fo_uploaded_at,
  acknowledged_version_id,acknowledged_at
)
SELECT 'installation',s.current_version_id,h.last_uploaded_at,
       s.current_version_id,now()
FROM reference_library_state s CROSS JOIN previous_fo h
WHERE s.id=1 AND s.current_version_id IS NOT NULL
  AND h.last_uploaded_at IS NOT NULL
ON CONFLICT(scope_key) DO NOTHING;
