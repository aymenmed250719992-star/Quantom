CREATE TABLE IF NOT EXISTS bot_status (
    id INTEGER PRIMARY KEY DEFAULT 1,
    is_running BOOLEAN NOT NULL DEFAULT FALSE,
    mode TEXT NOT NULL DEFAULT 'demo',
    last_scan_at TIMESTAMPTZ,
    total_trades INTEGER NOT NULL DEFAULT 0,
    win_rate FLOAT NOT NULL DEFAULT 0.0,
    total_pnl FLOAT NOT NULL DEFAULT 0.0,
    roi_percent FLOAT NOT NULL DEFAULT 0.0,
    target_win_rate FLOAT NOT NULL DEFAULT 65.0,
    current_threshold INTEGER NOT NULL DEFAULT 70
);

CREATE TABLE IF NOT EXISTS trades (
    id TEXT PRIMARY KEY,
    symbol TEXT,
    side TEXT,
    entry_price FLOAT,
    exit_price FLOAT,
    stop_loss_price FLOAT,
    take_profit_price FLOAT,
    quantity FLOAT,
    pnl FLOAT,
    pnl_percent FLOAT,
    status TEXT NOT NULL DEFAULT 'open',
    ai_confidence INTEGER,
    ai_reasoning TEXT,
    market_condition TEXT,
    pattern TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at TIMESTAMPTZ,
    rsi_at_entry FLOAT,
    macd_hist_at_entry FLOAT,
    bb_pct_at_entry FLOAT,
    volume_at_entry FLOAT,
    price_chg_pct_at_entry FLOAT,
    entry_hour_utc SMALLINT,
    ml_win_prob FLOAT
);

CREATE TABLE IF NOT EXISTS agent_memory (
    id TEXT PRIMARY KEY,
    lesson TEXT,
    symbol TEXT,
    market_condition TEXT,
    pattern TEXT,
    outcome TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS ai_keys (
    provider TEXT NOT NULL,
    slot_index INTEGER NOT NULL DEFAULT 0,
    api_key TEXT NOT NULL,
    label TEXT NOT NULL DEFAULT '',
    display_label TEXT NOT NULL DEFAULT '',
    base_url TEXT NOT NULL DEFAULT '',
    model_name TEXT NOT NULL DEFAULT '',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    added_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (provider, slot_index)
);
