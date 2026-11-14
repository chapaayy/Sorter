ALTER TABLE users ADD COLUMN IF NOT EXISTS access_role TEXT NOT NULL DEFAULT 'viewer'
    CHECK (access_role IN ('owner', 'viewer'));
UPDATE users SET access_role='owner' WHERE username='admin';

CREATE TABLE IF NOT EXISTS access_requests (
    id UUID PRIMARY KEY,
    email TEXT NOT NULL,
    comment TEXT NOT NULL,
    password_salt TEXT,
    password_hash TEXT,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    CHECK ((status='pending' AND password_salt IS NOT NULL AND password_hash IS NOT NULL AND decided_at IS NULL)
        OR (status<>'pending' AND password_salt IS NULL AND password_hash IS NULL AND decided_at IS NOT NULL))
);
CREATE UNIQUE INDEX IF NOT EXISTS access_requests_one_pending_email
    ON access_requests(email) WHERE status='pending';
CREATE INDEX IF NOT EXISTS access_requests_status_date ON access_requests(status, created_at DESC, id);

CREATE TABLE IF NOT EXISTS result_access_grants (
    user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, run_id)
);
