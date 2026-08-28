-- Version 3: Control plane and security tables

CREATE TABLE profile_versions (
    hash TEXT PRIMARY KEY,
    payload JSON NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')),
    created_by TEXT NOT NULL,
    correlation_id TEXT NOT NULL
);

CREATE TABLE active_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    hash TEXT NOT NULL REFERENCES profile_versions(hash)
);

CREATE TABLE live_arming_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    status TEXT NOT NULL, -- 'disarmed', 'armed_pending_reconciliation', 'armed_ready', 'blocked'
    profile_hash TEXT NOT NULL REFERENCES profile_versions(hash),
    expected_equity_usdt TEXT NOT NULL,
    armed_at TEXT NOT NULL,
    armed_by TEXT NOT NULL
);

CREATE TABLE admin_users (
    username TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    totp_secret TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))
);

CREATE TABLE admin_sessions (
    session_hash TEXT PRIMARY KEY,
    username TEXT NOT NULL REFERENCES admin_users(username),
    expires_at TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now')),
    last_totp_at TEXT
);

CREATE TABLE security_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    actor TEXT,
    ip_address TEXT,
    user_agent TEXT,
    correlation_id TEXT,
    metadata JSON,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))
);

INSERT INTO schema_migrations (version) VALUES (3);
