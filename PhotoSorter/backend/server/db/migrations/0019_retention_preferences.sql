-- Additive preferences. Keep existing per-batch deadlines unchanged.
CREATE TABLE IF NOT EXISTS retention_preferences (
 id SMALLINT PRIMARY KEY CHECK (id=1),
 enabled BOOLEAN NOT NULL DEFAULT TRUE,
 value INTEGER NOT NULL DEFAULT 2 CHECK (value BETWEEN 1 AND 525600),
 unit TEXT NOT NULL DEFAULT 'months' CHECK (unit IN ('minutes','hours','days','months')),
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO retention_preferences(id,enabled,value,unit)
 VALUES (1,TRUE,2,'months') ON CONFLICT(id) DO NOTHING;
