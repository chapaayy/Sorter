-- Durable journal for owner-authorized account lifecycle. Data is never
-- removed by a cascading user FK before the established batch cleanup.
CREATE TABLE account_lifecycle (
 source_id BIGINT PRIMARY KEY,
 recipient_id BIGINT,
 operation TEXT NOT NULL CHECK(operation IN ('transfer','transfer_delete','delete')),
 state TEXT NOT NULL CHECK(state IN ('queued','running','retry','completed')),
 actor TEXT NOT NULL,
 was_blocked BOOLEAN NOT NULL,
 plan JSONB,
 detail TEXT,
 requested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
 next_attempt TIMESTAMPTZ NOT NULL DEFAULT now(),
 finished_at TIMESTAMPTZ,
 CHECK((operation='delete' AND recipient_id IS NULL) OR
       (operation<>'delete' AND recipient_id IS NOT NULL AND recipient_id<>source_id))
);
CREATE INDEX account_lifecycle_pending ON account_lifecycle(next_attempt) WHERE state<>'completed';
