-- Version 5: Product-neutral multi-pair execution ledger

CREATE TABLE IF NOT EXISTS execution_intents (
    intent_id TEXT PRIMARY KEY,
    client_order_id TEXT NOT NULL UNIQUE,
    mode TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    product TEXT NOT NULL CHECK (product IN ('spot', 'futures')),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    position_side TEXT NOT NULL CHECK (position_side IN ('LONG', 'SHORT', 'BOTH')),
    order_type TEXT NOT NULL,
    quantity_text TEXT NOT NULL,
    price_text TEXT,
    stop_price_text TEXT,
    margin_mode TEXT NOT NULL DEFAULT 'isolated',
    leverage INTEGER NOT NULL DEFAULT 1,
    reduce_only INTEGER NOT NULL DEFAULT 0,
    time_in_force TEXT NOT NULL DEFAULT 'GTC',
    correlation_id TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS execution_orders (
    order_id TEXT PRIMARY KEY,
    intent_id TEXT NOT NULL REFERENCES execution_intents(intent_id),
    client_order_id TEXT NOT NULL UNIQUE,
    exchange_order_id TEXT,
    mode TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    product TEXT NOT NULL CHECK (product IN ('spot', 'futures')),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    position_side TEXT NOT NULL CHECK (position_side IN ('LONG', 'SHORT', 'BOTH')),
    order_type TEXT NOT NULL,
    quantity_text TEXT NOT NULL,
    price_text TEXT,
    stop_price_text TEXT,
    status TEXT NOT NULL,
    filled_quantity_text TEXT NOT NULL DEFAULT '0',
    avg_price_text TEXT,
    fee_text TEXT NOT NULL DEFAULT '0',
    fee_asset TEXT NOT NULL DEFAULT 'USDT',
    margin_mode TEXT NOT NULL DEFAULT 'isolated',
    leverage INTEGER NOT NULL DEFAULT 1,
    reduce_only INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_fills (
    fill_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES execution_orders(order_id),
    client_order_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
    position_side TEXT NOT NULL CHECK (position_side IN ('LONG', 'SHORT', 'BOTH')),
    price_text TEXT NOT NULL,
    quantity_text TEXT NOT NULL,
    fee_text TEXT NOT NULL DEFAULT '0',
    fee_asset TEXT NOT NULL DEFAULT 'USDT',
    realized_pnl_text TEXT NOT NULL DEFAULT '0',
    occurred_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_positions (
    position_id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    product TEXT NOT NULL CHECK (product IN ('spot', 'futures')),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL CHECK (side IN ('LONG', 'SHORT', 'BOTH')),
    quantity_text TEXT NOT NULL,
    entry_price_text TEXT NOT NULL,
    current_price_text TEXT,
    liquidation_price_text TEXT,
    margin_mode TEXT NOT NULL DEFAULT 'isolated',
    leverage INTEGER NOT NULL DEFAULT 1,
    isolated_margin_text TEXT NOT NULL DEFAULT '0',
    unrealized_pnl_text TEXT NOT NULL DEFAULT '0',
    realized_pnl_text TEXT NOT NULL DEFAULT '0',
    status TEXT NOT NULL CHECK (status IN ('OPEN', 'CLOSED')),
    opened_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS execution_protections (
    position_id TEXT PRIMARY KEY REFERENCES execution_positions(position_id),
    stop_loss_price_text TEXT,
    take_profit_price_text TEXT,
    trailing_stop_delta_text TEXT,
    max_drawdown_limit_text TEXT,
    created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%S+00:00', 'now'))
);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL CHECK (mode IN ('paper', 'live')),
    total_equity_usdt TEXT NOT NULL,
    free_margin_usdt TEXT NOT NULL,
    used_margin_usdt TEXT NOT NULL,
    unrealized_pnl_usdt TEXT NOT NULL,
    positions_count INTEGER NOT NULL DEFAULT 0,
    observed_at TEXT NOT NULL
);

