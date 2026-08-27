PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TEXT NOT NULL
);

INSERT OR IGNORE INTO schema_migrations(version, applied_at)
VALUES (2, strftime('%Y-%m-%dT%H:%M:%f+00:00', 'now'));

CREATE TABLE IF NOT EXISTS settings_versions (
    id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS paper_accounts (
    id TEXT PRIMARY KEY,
    initial_balance_text TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS app_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    current_paper_account_id TEXT REFERENCES paper_accounts(id),
    active_settings_id TEXT REFERENCES settings_versions(id),
    bot_state TEXT NOT NULL DEFAULT 'DISARMED'
);

INSERT OR IGNORE INTO app_state(singleton, bot_state) VALUES (1, 'DISARMED');

CREATE TABLE IF NOT EXISTS state_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    reason TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS worker_leases (
    name TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS market_candles (
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    open_time TEXT NOT NULL,
    close_time TEXT NOT NULL,
    open_text TEXT NOT NULL,
    high_text TEXT NOT NULL,
    low_text TEXT NOT NULL,
    close_text TEXT NOT NULL,
    volume_text TEXT NOT NULL,
    source_hash TEXT NOT NULL,
    PRIMARY KEY(symbol, timeframe, open_time)
);

CREATE TABLE IF NOT EXISTS data_quality_events (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    event_type TEXT NOT NULL,
    details_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS context_snapshots (
    id TEXT PRIMARY KEY,
    fetched_at TEXT NOT NULL,
    event_time TEXT,
    freshness TEXT NOT NULL,
    conflict_level TEXT NOT NULL,
    content_hash TEXT NOT NULL UNIQUE,
    summary_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS context_sources (
    id TEXT PRIMARY KEY,
    context_snapshot_id TEXT NOT NULL REFERENCES context_snapshots(id),
    url TEXT NOT NULL,
    title TEXT NOT NULL,
    published_at TEXT,
    source_tier INTEGER NOT NULL CHECK (source_tier BETWEEN 1 AND 4)
);

CREATE TABLE IF NOT EXISTS macro_risk_windows (
    id TEXT PRIMARY KEY,
    event_name TEXT NOT NULL,
    starts_at TEXT NOT NULL,
    ends_at TEXT NOT NULL,
    source_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decision_chains (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    account_scope TEXT NOT NULL,
    symbol TEXT NOT NULL,
    timeframe TEXT NOT NULL,
    candle_close_time TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(mode, account_scope, symbol, timeframe, candle_close_time)
);

CREATE TABLE IF NOT EXISTS ai_decisions (
    id TEXT PRIMARY KEY,
    decision_chain_id TEXT NOT NULL REFERENCES decision_chains(id),
    context_snapshot_id TEXT REFERENCES context_snapshots(id),
    decision TEXT NOT NULL,
    confidence INTEGER NOT NULL CHECK (confidence BETWEEN 0 AND 100),
    reason_codes_json TEXT NOT NULL,
    prompt_hash TEXT NOT NULL,
    model TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_decisions (
    id TEXT PRIMARY KEY,
    decision_chain_id TEXT NOT NULL REFERENCES decision_chains(id),
    approved INTEGER NOT NULL CHECK (approved IN (0, 1)),
    details_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    paper_account_id TEXT REFERENCES paper_accounts(id),
    client_order_id TEXT NOT NULL UNIQUE,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    quantity_text TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    CHECK (
        (mode = 'paper' AND paper_account_id IS NOT NULL)
        OR (mode = 'live' AND paper_account_id IS NULL)
    )
);

CREATE TABLE IF NOT EXISTS fills (
    id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(id),
    price_text TEXT NOT NULL,
    quantity_text TEXT NOT NULL,
    fee_text TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    paper_account_id TEXT REFERENCES paper_accounts(id),
    entry_order_id TEXT NOT NULL REFERENCES orders(id),
    exit_order_id TEXT REFERENCES orders(id),
    status TEXT NOT NULL,
    realized_pnl_text TEXT,
    opened_at TEXT NOT NULL,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS equity_snapshots (
    id TEXT PRIMARY KEY,
    paper_account_id TEXT NOT NULL REFERENCES paper_accounts(id),
    equity_text TEXT NOT NULL,
    cash_text TEXT NOT NULL,
    observed_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reflections (
    id TEXT PRIMARY KEY,
    trade_id TEXT NOT NULL,
    namespace TEXT NOT NULL CHECK (namespace IN ('historical', 'forward')),
    lesson_code TEXT NOT NULL DEFAULT 'GENERAL',
    lesson TEXT NOT NULL DEFAULT '',
    regime_tags_json TEXT NOT NULL DEFAULT '[]',
    net_pnl_text TEXT NOT NULL DEFAULT '0',
    fee_drag_text TEXT NOT NULL DEFAULT '0',
    mae_text TEXT NOT NULL DEFAULT '0',
    mfe_text TEXT NOT NULL DEFAULT '0',
    exit_reason TEXT NOT NULL DEFAULT 'TAKE_PROFIT',
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS historical_data_manifests (
    id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    requested_start TEXT NOT NULL,
    requested_end TEXT NOT NULL,
    checksum TEXT NOT NULL,
    status TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS backtest_runs (
    id TEXT PRIMARY KEY,
    strategy_version TEXT NOT NULL,
    partition TEXT NOT NULL,
    status TEXT NOT NULL,
    metrics_json TEXT,
    run_hash TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS strategy_proposals (
    id TEXT PRIMARY KEY,
    parent_version TEXT NOT NULL,
    proposal_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS shadow_runs (
    id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL REFERENCES strategy_proposals(id),
    status TEXT NOT NULL,
    metrics_json TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS hermes_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS system_health_events (
    id TEXT PRIMARY KEY,
    component TEXT NOT NULL,
    status TEXT NOT NULL,
    details_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at TEXT NOT NULL,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS agent_events (
    event_id TEXT PRIMARY KEY,
    action TEXT NOT NULL,
    reason TEXT NOT NULL,
    reason_codes_json TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL
);

-- Storage v2 additions: Providers, Model Routes, Genomes, Evaluations, Promotions, Quotas

CREATE TABLE IF NOT EXISTS providers (
    name TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    base_url TEXT NOT NULL,
    key_fingerprint TEXT NOT NULL,
    status TEXT NOT NULL,
    last_probe_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS model_routes (
    id TEXT PRIMARY KEY,
    role TEXT NOT NULL CHECK (role IN ('decision', 'context', 'hermes')),
    provider TEXT NOT NULL REFERENCES providers(name),
    model TEXT NOT NULL,
    pinned INTEGER NOT NULL DEFAULT 1,
    version INTEGER NOT NULL,
    created_at TEXT NOT NULL
);

CREATE VIEW IF NOT EXISTS active_routes AS
SELECT r.* FROM model_routes r
INNER JOIN (
    SELECT role, MAX(version) as max_version
    FROM model_routes
    GROUP BY role
) latest ON r.role = latest.role AND r.version = latest.max_version;

CREATE TABLE IF NOT EXISTS genomes (
    genome_id TEXT PRIMARY KEY,
    genome_hash TEXT NOT NULL UNIQUE,
    parent_id TEXT REFERENCES genomes(genome_id),
    origin TEXT NOT NULL CHECK (origin IN ('baseline', 'hermes', 'human')),
    status TEXT NOT NULL CHECK (status IN ('candidate', 'dev_passed', 'val_passed', 'holdout_passed', 'shadow', 'active', 'quarantined', 'retired', 'archived')),
    hypothesis TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    evidence_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS evaluations (
    evaluation_id TEXT PRIMARY KEY,
    genome_id TEXT NOT NULL REFERENCES genomes(genome_id),
    partition TEXT NOT NULL CHECK (partition IN ('development', 'validation', 'holdout')),
    window TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    run_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    UNIQUE(genome_id, partition, window, run_hash)
);

CREATE TABLE IF NOT EXISTS promotions (
    promotion_id TEXT PRIMARY KEY,
    genome_id TEXT NOT NULL REFERENCES genomes(genome_id),
    promoted_by TEXT NOT NULL,
    mode TEXT NOT NULL,
    gate_report_json TEXT NOT NULL,
    at TEXT NOT NULL
);

-- One row per promoted candidate under canary observation. Survives restart so a bot that
-- crashes mid-canary still knows which baseline to roll back to and why it stopped.
CREATE TABLE IF NOT EXISTS promotion_canary (
    genome_id TEXT PRIMARY KEY REFERENCES genomes(genome_id),
    promotion_id TEXT NOT NULL,
    baseline_genome_id TEXT NOT NULL REFERENCES genomes(genome_id),
    baseline_hash TEXT NOT NULL,
    stage TEXT NOT NULL CHECK (stage IN ('canary', 'confirmed', 'rolled_back')),
    rollback_reason TEXT,
    circuit_breaker_tripped INTEGER NOT NULL DEFAULT 0,
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS one_open_promotion_canary
ON promotion_canary(stage) WHERE stage = 'canary';

-- Autonomy is a kill switch, so it is durable: a revocation must not evaporate on restart.
CREATE TABLE IF NOT EXISTS autonomy_state (
    singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
    full_autonomy INTEGER NOT NULL DEFAULT 1,
    revoked_reason TEXT,
    updated_at TEXT NOT NULL
);

INSERT OR IGNORE INTO autonomy_state(singleton, full_autonomy, updated_at)
VALUES (1, 1, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));

CREATE TABLE IF NOT EXISTS research_quota (
    date TEXT PRIMARY KEY,
    backtests_used INTEGER NOT NULL DEFAULT 0,
    web_calls_used INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS research_events (
    event_id TEXT PRIMARY KEY,
    tool TEXT NOT NULL,
    bytes_out INTEGER NOT NULL DEFAULT 0,
    started_at TEXT NOT NULL,
    finished_at TEXT NOT NULL
);

-- Immutability triggers
CREATE TRIGGER IF NOT EXISTS settings_versions_no_update
BEFORE UPDATE ON settings_versions BEGIN
    SELECT RAISE(ABORT, 'settings versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS settings_versions_no_delete
BEFORE DELETE ON settings_versions BEGIN
    SELECT RAISE(ABORT, 'settings versions are immutable');
END;

CREATE TRIGGER IF NOT EXISTS paper_accounts_no_update
BEFORE UPDATE ON paper_accounts BEGIN
    SELECT RAISE(ABORT, 'paper accounts are immutable');
END;

CREATE TRIGGER IF NOT EXISTS paper_accounts_no_delete
BEFORE DELETE ON paper_accounts BEGIN
    SELECT RAISE(ABORT, 'paper accounts are immutable');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_update
BEFORE UPDATE ON audit_events BEGIN
    SELECT RAISE(ABORT, 'audit events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS audit_events_no_delete
BEFORE DELETE ON audit_events BEGIN
    SELECT RAISE(ABORT, 'audit events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS agent_events_no_update
BEFORE UPDATE ON agent_events BEGIN
    SELECT RAISE(ABORT, 'agent events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS agent_events_no_delete
BEFORE DELETE ON agent_events BEGIN
    SELECT RAISE(ABORT, 'agent events are immutable');
END;

CREATE TRIGGER IF NOT EXISTS reflections_no_update
BEFORE UPDATE ON reflections BEGIN
    SELECT RAISE(ABORT, 'reflections are immutable');
END;

CREATE TRIGGER IF NOT EXISTS reflections_no_delete
BEFORE DELETE ON reflections BEGIN
    SELECT RAISE(ABORT, 'reflections are immutable');
END;
