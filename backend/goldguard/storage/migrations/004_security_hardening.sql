-- Version 4: durable authentication hardening for databases already on migration 3.
-- Existing sessions cannot be safely upgraded with a CSRF value, so they are
-- invalidated while retaining the account and immutable security history.

ALTER TABLE admin_sessions ADD COLUMN csrf_hash TEXT NOT NULL DEFAULT '';
ALTER TABLE admin_sessions ADD COLUMN absolute_expires_at TEXT;
ALTER TABLE admin_sessions ADD COLUMN last_seen_at TEXT;
ALTER TABLE admin_sessions ADD COLUMN ip_address TEXT NOT NULL DEFAULT '';
ALTER TABLE admin_sessions ADD COLUMN user_agent TEXT NOT NULL DEFAULT '';

UPDATE admin_sessions
SET absolute_expires_at = expires_at,
    last_seen_at = created_at;

DELETE FROM admin_sessions WHERE csrf_hash = '';

ALTER TABLE admin_users ADD COLUMN last_totp_step INTEGER;

CREATE TABLE admin_auth_failures (
    kind TEXT NOT NULL CHECK (kind IN ('password', 'totp')),
    subject TEXT NOT NULL,
    failures INTEGER NOT NULL DEFAULT 0,
    first_failed_at TEXT,
    last_failed_at TEXT,
    locked_until TEXT,
    PRIMARY KEY (kind, subject)
);
