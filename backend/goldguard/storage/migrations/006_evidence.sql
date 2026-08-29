-- Version 6: Cited and scored evidence storage

CREATE TABLE IF NOT EXISTS evidence_items (
    evidence_id TEXT PRIMARY KEY,
    source_kind TEXT NOT NULL,
    source_url TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT,
    event_at TEXT,
    retrieved_at TEXT NOT NULL,
    affected_assets_json TEXT NOT NULL,
    event_class TEXT NOT NULL,
    claims_json TEXT NOT NULL,
    raw_content_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_evidence_retrieved
ON evidence_items(retrieved_at);

CREATE INDEX IF NOT EXISTS idx_evidence_event_class
ON evidence_items(event_class);

