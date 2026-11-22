-- Consolidate existing Russian/English A/B labels into Latin A/B presets.
-- Do not erase unrelated historical labels: they can be reassigned in the UI.
-- Existing completed FO snapshots and ZIP files are not changed.
WITH normalized AS (
    SELECT reference_id, upper(btrim(side)) AS old_side
    FROM reference_photo_sides
)
UPDATE reference_photo_sides AS s
SET side = (CASE WHEN left(n.old_side,1) IN ('A','А') THEN 'A' ELSE 'B' END)
             || substr(n.old_side,2),
    updated_at = now()
FROM normalized n
WHERE s.reference_id = n.reference_id
  AND n.old_side ~ '^[AАBБВ][1-3]?$';
