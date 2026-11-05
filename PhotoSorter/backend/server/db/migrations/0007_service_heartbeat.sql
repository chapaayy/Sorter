-- Stage 4: additive worker presence, no existing jobs or user data changed.
CREATE TABLE IF NOT EXISTS service_heartbeats (
  service TEXT PRIMARY KEY CHECK(service IN ('megaloc','thumbnail','cleanup')),
  instance_id UUID NOT NULL,
  seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_service_heartbeats_seen_at ON service_heartbeats(seen_at);
