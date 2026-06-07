"""
AuditTrail — سجل التدقيق الكامل وغير القابل للتغيير  (T010)

يُسجّل كل قرار تداولي بالتفصيل الكامل:
  • من قرر (Gemini / Ensemble / Rules / User)
  • لماذا قرر (المؤشرات، التصويت، الثقة)
  • ماذا كانت الظروف (السوق، الوقت، الرصيد)
  • ما نتيجة القرار (ربح/خسارة/قيد)

يُخزَّن في جدول `audit_log` في PostgreSQL.
يدعم: تصدير JSON | فلترة | إحصاءات | تقرير أسبوعي.
"""

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any, Optional


# ── Schema (يُنشأ في ensure_all_tables) ──────────────────────────────────────

CREATE_AUDIT_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id              BIGSERIAL PRIMARY KEY,
    event_type      TEXT NOT NULL,          -- SIGNAL | TRADE_OPEN | TRADE_CLOSE | REFLECTION | SYSTEM
    symbol          TEXT,
    action          TEXT,                   -- BUY | SELL | HOLD | BLOCK
    decided_by      TEXT,                   -- gemini | ensemble | rules | user | system
    confidence      REAL,
    trade_id        TEXT,

    -- Decision inputs
    indicators      JSONB,                  -- RSI, MACD, BB, etc.
    ai_votes        JSONB,                  -- ensemble voting results
    onchain_data    JSONB,                  -- fear&greed, btc dominance
    confluence      JSONB,                  -- multi-TF signal

    -- Decision output
    reason          TEXT,
    blocked_reason  TEXT,                   -- if action was BLOCK
    kelly_pct       REAL,                   -- applied Kelly %
    position_size   REAL,

    -- Outcome (filled when trade closes)
    outcome         TEXT,                   -- WIN | LOSS | PENDING | CANCELLED
    pnl_usd         REAL,
    pnl_pct         REAL,
    duration_min    REAL,

    -- Context
    balance_at      REAL,
    exchange        TEXT,
    mode            TEXT,                   -- demo | live
    strategy        TEXT,

    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_symbol    ON audit_log(symbol);
CREATE INDEX IF NOT EXISTS idx_audit_type      ON audit_log(event_type);
CREATE INDEX IF NOT EXISTS idx_audit_created   ON audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_trade_id  ON audit_log(trade_id);
"""


class AuditTrail:
    """
    Singleton audit trail writer/reader.
    All writes are fire-and-forget (won't block trading loop).
    """

    _instance: Optional["AuditTrail"] = None

    @classmethod
    def get_instance(cls) -> "AuditTrail":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._db: Any = None
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=500)
        self._writer_task: Optional[asyncio.Task] = None
        self._ready = False

    def init(self, db: Any) -> None:
        self._db = db
        if self._writer_task is None or self._writer_task.done():
            self._writer_task = asyncio.create_task(self._write_loop(), name="audit_writer")
        self._ready = True
        print("[Audit] Trail initialized ✅")

    # ── Write helpers ─────────────────────────────────────────────────────────

    def log_signal(
        self,
        symbol: str,
        action: str,
        decided_by: str,
        confidence: float,
        indicators: dict,
        reason: str,
        ai_votes: Optional[dict] = None,
        onchain_data: Optional[dict] = None,
        confluence: Optional[dict] = None,
        blocked_reason: str = "",
        kelly_pct: float = 0.0,
        position_size: float = 0.0,
        balance: float = 0.0,
        exchange: str = "",
        mode: str = "demo",
        strategy: str = "",
    ) -> None:
        """Log a trading signal decision (non-blocking)."""
        entry = {
            "event_type":    "SIGNAL",
            "symbol":        symbol,
            "action":        action.upper(),
            "decided_by":    decided_by,
            "confidence":    confidence,
            "indicators":    indicators,
            "ai_votes":      ai_votes or {},
            "onchain_data":  onchain_data or {},
            "confluence":    confluence or {},
            "reason":        reason[:500] if reason else "",
            "blocked_reason": blocked_reason[:200] if blocked_reason else "",
            "kelly_pct":     kelly_pct,
            "position_size": position_size,
            "balance_at":    balance,
            "exchange":      exchange,
            "mode":          mode,
            "strategy":      strategy,
            "outcome":       "PENDING",
        }
        self._enqueue(entry)

    def log_trade_open(self, trade: dict, decided_by: str = "system", **kwargs) -> None:
        entry = {
            "event_type":   "TRADE_OPEN",
            "symbol":       trade.get("symbol", ""),
            "action":       trade.get("side", "buy").upper(),
            "decided_by":   decided_by,
            "confidence":   float(trade.get("ai_confidence") or trade.get("confidence") or 0),
            "trade_id":     str(trade.get("id") or ""),
            "reason":       trade.get("reason", "")[:500],
            "position_size": float(trade.get("quantity") or 0),
            "mode":         trade.get("mode", "demo"),
            "outcome":      "PENDING",
            **{k: v for k, v in kwargs.items() if k in (
                "kelly_pct", "balance_at", "exchange", "strategy",
                "indicators", "ai_votes", "onchain_data", "confluence",
            )},
        }
        self._enqueue(entry)

    def log_trade_close(self, trade: dict, pnl: float, duration_min: float) -> None:
        outcome = "WIN" if pnl > 0 else "LOSS"
        entry_price = float(trade.get("entry_price") or 1)
        exit_price  = float(trade.get("exit_price") or entry_price)
        pnl_pct = (exit_price - entry_price) / entry_price * 100

        entry = {
            "event_type":    "TRADE_CLOSE",
            "symbol":        trade.get("symbol", ""),
            "action":        "CLOSE",
            "decided_by":    "system",
            "trade_id":      str(trade.get("id") or ""),
            "outcome":       outcome,
            "pnl_usd":       round(pnl, 4),
            "pnl_pct":       round(pnl_pct, 3),
            "duration_min":  round(duration_min, 1),
            "mode":          trade.get("mode", "demo"),
        }
        self._enqueue(entry)

    def log_reflection(self, trigger: str, insight: str, strategy: str) -> None:
        entry = {
            "event_type": "REFLECTION",
            "decided_by": "agent",
            "action":     trigger.upper(),
            "reason":     insight[:500],
            "strategy":   strategy,
            "outcome":    "APPLIED",
        }
        self._enqueue(entry)

    def log_block(self, symbol: str, reason: str, blocker: str) -> None:
        entry = {
            "event_type":    "SIGNAL",
            "symbol":        symbol,
            "action":        "BLOCK",
            "decided_by":    blocker,
            "blocked_reason": reason[:200],
            "outcome":       "CANCELLED",
        }
        self._enqueue(entry)

    def _enqueue(self, entry: dict) -> None:
        if not self._ready:
            return
        try:
            self._queue.put_nowait(entry)
        except asyncio.QueueFull:
            print("[Audit] Queue full — dropping entry")

    # ── Background writer ─────────────────────────────────────────────────────

    async def _write_loop(self) -> None:
        """Drain queue and write to DB in batches."""
        while True:
            try:
                entry = await asyncio.wait_for(self._queue.get(), timeout=5.0)
                batch = [entry]

                # Drain up to 9 more (batch of 10)
                while not self._queue.empty() and len(batch) < 10:
                    batch.append(self._queue.get_nowait())

                await self._write_batch(batch)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Audit] Writer error: {e}")
                await asyncio.sleep(2)

    async def _write_batch(self, entries: list[dict]) -> None:
        if not self._db:
            return
        try:
            pool = await self._db._get_pool()
            if pool is None:
                return
            async with pool.acquire() as conn:
                for entry in entries:
                    await conn.execute("""
                        INSERT INTO audit_log (
                            event_type, symbol, action, decided_by, confidence, trade_id,
                            indicators, ai_votes, onchain_data, confluence,
                            reason, blocked_reason, kelly_pct, position_size,
                            outcome, pnl_usd, pnl_pct, duration_min,
                            balance_at, exchange, mode, strategy
                        ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18,$19,$20,$21,$22)
                    """,
                        entry.get("event_type", "SYSTEM"),
                        entry.get("symbol"),
                        entry.get("action"),
                        entry.get("decided_by"),
                        entry.get("confidence"),
                        entry.get("trade_id"),
                        json.dumps(entry.get("indicators") or {}),
                        json.dumps(entry.get("ai_votes") or {}),
                        json.dumps(entry.get("onchain_data") or {}),
                        json.dumps(entry.get("confluence") or {}),
                        entry.get("reason"),
                        entry.get("blocked_reason"),
                        entry.get("kelly_pct"),
                        entry.get("position_size"),
                        entry.get("outcome"),
                        entry.get("pnl_usd"),
                        entry.get("pnl_pct"),
                        entry.get("duration_min"),
                        entry.get("balance_at"),
                        entry.get("exchange"),
                        entry.get("mode"),
                        entry.get("strategy"),
                    )
        except Exception as e:
            print(f"[Audit] DB write error: {e}")

    # ── Read API ──────────────────────────────────────────────────────────────

    async def get_recent(self, limit: int = 50, event_type: Optional[str] = None) -> list[dict]:
        try:
            pool = await self._db._get_pool()
            if pool is None:
                return []
            where = f"WHERE event_type = $2" if event_type else ""
            params = [limit, event_type] if event_type else [limit]
            async with pool.acquire() as conn:
                rows = await conn.fetch(
                    f"SELECT * FROM audit_log {where} ORDER BY created_at DESC LIMIT $1",
                    *params,
                )
                return [dict(r) for r in rows]
        except Exception as e:
            print(f"[Audit] Read error: {e}")
            return []

    async def get_weekly_summary(self) -> dict:
        """Generate weekly performance report data."""
        try:
            pool = await self._db._get_pool()
            if pool is None:
                return {}
            async with pool.acquire() as conn:
                rows = await conn.fetch("""
                    SELECT
                        COUNT(*) FILTER (WHERE event_type='TRADE_CLOSE') AS total_trades,
                        COUNT(*) FILTER (WHERE event_type='TRADE_CLOSE' AND outcome='WIN') AS wins,
                        COUNT(*) FILTER (WHERE event_type='TRADE_CLOSE' AND outcome='LOSS') AS losses,
                        ROUND(SUM(pnl_usd) FILTER (WHERE event_type='TRADE_CLOSE')::numeric, 4) AS total_pnl,
                        COUNT(*) FILTER (WHERE event_type='SIGNAL' AND action='BLOCK') AS blocked_signals,
                        COUNT(*) FILTER (WHERE event_type='REFLECTION') AS reflections,
                        COUNT(DISTINCT symbol) FILTER (WHERE event_type='TRADE_CLOSE') AS symbols_traded
                    FROM audit_log
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                """)
                row = dict(rows[0]) if rows else {}
                total = (row.get("total_trades") or 0)
                wins  = (row.get("wins") or 0)
                row["win_rate_pct"] = round(wins / total * 100, 1) if total else 0
                return row
        except Exception as e:
            print(f"[Audit] Weekly summary error: {e}")
            return {}

    async def ensure_table(self) -> None:
        """Create audit_log table if it doesn't exist."""
        try:
            pool = await self._db._get_pool()
            if pool is None:
                return
            async with pool.acquire() as conn:
                await conn.execute(CREATE_AUDIT_TABLE)
            print("[Audit] audit_log table ready ✅")
        except Exception as e:
            print(f"[Audit] Table creation error: {e}")
