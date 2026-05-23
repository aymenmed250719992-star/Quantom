-- Islamic Trading Bot v2 — Supabase PostgreSQL Schema
-- Run this in your Supabase SQL editor at:
-- https://supabase.com/dashboard → your project → SQL Editor

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- ══════════════════════════════════════
--  TRADES TABLE
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS trades (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    symbol          TEXT NOT NULL,
    side            TEXT NOT NULL CHECK (side IN ('buy', 'sell')),
    entry_price     FLOAT NOT NULL,
    exit_price      FLOAT,
    stop_loss_price FLOAT,
    take_profit_price FLOAT,
    quantity        FLOAT NOT NULL,
    pnl             FLOAT,
    pnl_percent     FLOAT,
    status          TEXT NOT NULL DEFAULT 'open'
                        CHECK (status IN ('open', 'closed', 'cancelled')),
    ai_confidence   INTEGER NOT NULL DEFAULT 0,
    ai_reasoning    TEXT NOT NULL DEFAULT '',
    market_condition TEXT NOT NULL DEFAULT 'unknown',
    pattern         TEXT DEFAULT '',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    closed_at       TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_trades_created_at   ON trades (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_trades_status        ON trades (status);
CREATE INDEX IF NOT EXISTS idx_trades_symbol        ON trades (symbol);
CREATE INDEX IF NOT EXISTS idx_trades_pnl           ON trades (pnl);

-- ══════════════════════════════════════
--  AGENT MEMORY (Lessons Learned)
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS agent_memory (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    lesson           TEXT NOT NULL,
    symbol           TEXT NOT NULL,
    market_condition TEXT NOT NULL DEFAULT 'unknown',
    pattern          TEXT DEFAULT '',
    outcome          TEXT NOT NULL CHECK (outcome IN ('win', 'loss')),
    confidence_at_trade INTEGER DEFAULT 0,
    pnl_at_close     FLOAT DEFAULT 0,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_memory_created_at ON agent_memory (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_memory_outcome    ON agent_memory (outcome);
CREATE INDEX IF NOT EXISTS idx_memory_symbol     ON agent_memory (symbol);

-- ══════════════════════════════════════
--  BOT STATUS (single row, id = 1)
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS bot_status (
    id                  INTEGER PRIMARY KEY DEFAULT 1,
    is_running          BOOLEAN NOT NULL DEFAULT FALSE,
    mode                TEXT NOT NULL DEFAULT 'demo'
                            CHECK (mode IN ('demo', 'live')),
    last_scan_at        TIMESTAMPTZ,
    total_trades        INTEGER NOT NULL DEFAULT 0,
    win_rate            FLOAT NOT NULL DEFAULT 0.0,
    total_pnl           FLOAT NOT NULL DEFAULT 0.0,
    roi_percent         FLOAT NOT NULL DEFAULT 0.0,
    target_win_rate     FLOAT NOT NULL DEFAULT 65.0,
    current_threshold   INTEGER NOT NULL DEFAULT 70,
    CONSTRAINT single_row CHECK (id = 1)
);

INSERT INTO bot_status (
    id, is_running, mode, total_trades, win_rate,
    total_pnl, roi_percent, target_win_rate, current_threshold
)
VALUES (1, FALSE, 'demo', 0, 0.0, 0.0, 0.0, 65.0, 70)
ON CONFLICT (id) DO NOTHING;

-- ══════════════════════════════════════
--  PORTFOLIO SNAPSHOTS (daily ROI tracking)
-- ══════════════════════════════════════
CREATE TABLE IF NOT EXISTS portfolio_snapshots (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    balance         FLOAT NOT NULL DEFAULT 0.0,
    total_pnl       FLOAT NOT NULL DEFAULT 0.0,
    roi_percent     FLOAT NOT NULL DEFAULT 0.0,
    win_rate        FLOAT NOT NULL DEFAULT 0.0,
    total_trades    INTEGER NOT NULL DEFAULT 0,
    mode            TEXT DEFAULT 'demo',
    snapshot_date   DATE NOT NULL DEFAULT CURRENT_DATE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_snapshots_date ON portfolio_snapshots (snapshot_date DESC);

-- ══════════════════════════════════════
--  ROW LEVEL SECURITY
-- ══════════════════════════════════════
ALTER TABLE trades              ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_memory        ENABLE ROW LEVEL SECURITY;
ALTER TABLE bot_status          ENABLE ROW LEVEL SECURITY;
ALTER TABLE portfolio_snapshots ENABLE ROW LEVEL SECURITY;

-- Allow full access via service role key (used by backend server)
DO $$ BEGIN
  CREATE POLICY "service_full_access" ON trades             FOR ALL USING (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "service_full_access" ON agent_memory       FOR ALL USING (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "service_full_access" ON bot_status         FOR ALL USING (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;
DO $$ BEGIN
  CREATE POLICY "service_full_access" ON portfolio_snapshots FOR ALL USING (true);
  EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

-- ══════════════════════════════════════
--  HELPFUL VIEWS
-- ══════════════════════════════════════

-- Win rate by symbol
CREATE OR REPLACE VIEW symbol_performance AS
SELECT
    symbol,
    COUNT(*) FILTER (WHERE status = 'closed') AS total_trades,
    COUNT(*) FILTER (WHERE status = 'closed' AND pnl > 0) AS wins,
    ROUND(
        COUNT(*) FILTER (WHERE status = 'closed' AND pnl > 0)::numeric
        / NULLIF(COUNT(*) FILTER (WHERE status = 'closed'), 0) * 100,
        2
    ) AS win_rate_pct,
    ROUND(SUM(pnl) FILTER (WHERE status = 'closed')::numeric, 4) AS total_pnl
FROM trades
GROUP BY symbol
ORDER BY total_pnl DESC;

-- Daily PnL summary
CREATE OR REPLACE VIEW daily_pnl AS
SELECT
    DATE(closed_at) AS trade_date,
    COUNT(*) AS trades,
    COUNT(*) FILTER (WHERE pnl > 0) AS wins,
    ROUND(SUM(pnl)::numeric, 4) AS daily_pnl
FROM trades
WHERE status = 'closed' AND closed_at IS NOT NULL
GROUP BY DATE(closed_at)
ORDER BY trade_date DESC;
