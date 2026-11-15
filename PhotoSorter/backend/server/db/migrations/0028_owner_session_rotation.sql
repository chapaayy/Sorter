-- Salted rotation marker only. The admin login checks ADMIN_PASSWORD, not this table.
CREATE TABLE IF NOT EXISTS owner_session_credential (
    user_id BIGINT PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    salt TEXT NOT NULL,
    fingerprint TEXT NOT NULL
);
