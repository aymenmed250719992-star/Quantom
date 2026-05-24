"""
Database client — uses asyncpg for PostgreSQL.
Prefers SUPABASE_DB_URL (external Supabase) when set,
falls back to DATABASE_URL (Render PostgreSQL or any Postgres).
Falls back to in-memory storage if the database is unreachable.
"""

import os
import uuid
from datetime import datetime
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv(override=True)

# Priority: QUANTOM_DB_URL > SUPABASE_DB_URL > DATABASE_URL
# QUANTOM_DB_URL is used to avoid conflict with Replit's runtime-managed DATABASE_URL
_QUANTOM_DB_URL: str = os.environ.get("QUANTOM_DB_URL", "")
_SUPABASE_DB_URL: str = os.environ.get("SUPABASE_DB_URL", "")
_DATABASE_URL: str = _QUANTOM_DB_URL or _SUPABASE_DB_URL or os.environ.get("DATABASE_URL", "")
_USE_SSL: bool = bool(_SUPABASE_DB_URL) and not bool(_QUANTOM_DB_URL)  # Supabase requires SSL
_USE_SSL_RENDER: bool = bool(_QUANTOM_DB_URL)  # Render external connections require SSL


def _parse_supabase_url(url: str):
    """
    Robustly parse a Supabase pooler URL even when the password contains
    raw '@' characters (e.g. Nova3iNokiac25071999@@).

    Strategy: locate the Supabase host pattern directly in the raw string,
    then slice backwards for credentials — never rely on '@' as separator.

    Returns (user, password, host, port, dbname) or None if not a Supabase URL.
    """
    import re

    # Match the host+port+db suffix for Supabase pooler or direct connections
    host_re = re.compile(
        r"@(aws-0-[a-z0-9-]+\.pooler\.supabase\.com|db\.[a-z0-9]+\.supabase\.co)"
        r":(\d+)/([^?#]+)"
    )
    hm = host_re.search(url)
    if not hm:
        return None

    host     = hm.group(1)
    port     = int(hm.group(2))
    dbname   = hm.group(3)

    # Credentials = everything between "://" and "@host"
    cred_start = url.index("://") + 3
    cred_end   = hm.start()          # position of the '@' right before host
    credentials = url[cred_start:cred_end]  # "user:password" (may contain @)

    colon = credentials.index(":")   # split on FIRST colon only
    username = credentials[:colon]
    password = credentials[colon + 1:]

    return username, password, host, port, dbname


def _fix_url(url: str) -> str:
    """
    asyncpg needs postgresql:// not postgres://.
    For Supabase URLs also corrects the pooler region to the verified
    working one (aws-0-eu-west-1).
    """
    import re
    from urllib.parse import quote

    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)

    # Fix Supabase pooler region to the verified working region
    if "pooler.supabase.com" in url:
        url = re.sub(r"aws-0-[a-z0-9-]+\.pooler", "aws-0-eu-west-1.pooler", url)

    return url


class DatabaseClient:
    def __init__(self) -> None:
        self._pool: Any = None  # asyncpg connection pool (lazy init)
        self._db_url: str = _fix_url(_DATABASE_URL)
        self._db_available: bool = bool(self._db_url)

        # In-memory fallback (used until pool is ready or if DB is unavailable)
        self._mem_status: dict = {
            "id": 1,
            "is_running": False,
            "mode": "demo",
            "last_scan_at": None,
            "total_trades": 0,
            "win_rate": 0.0,
        }
        self._mem_trades: list[dict] = []
        self._mem_lessons: list[dict] = []

        if self._db_available:
            print(f"[DB] PostgreSQL configured — pool will init on first use")
        else:
            print("[DB] No DATABASE_URL — using in-memory storage only")

    # ── Pool management ───────────────────────────────────────────────────────

    async def _get_pool(self) -> Any:
        if self._pool is not None:
            return self._pool
        if not self._db_available:
            return None
        try:
            import asyncpg
            import ssl as _ssl

            if _USE_SSL_RENDER:
                # Render external PostgreSQL — requires SSL, no hostname check
                ssl_ctx = _ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = _ssl.CERT_NONE
                self._pool = await asyncpg.create_pool(
                    self._db_url,
                    min_size=1, max_size=5,
                    command_timeout=15, ssl=ssl_ctx,
                )
            elif _USE_SSL:
                ssl_ctx = _ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = _ssl.CERT_NONE
                # Build connection kwargs from the robustly-parsed Supabase URL
                # (handles raw '@' or '%40' in passwords, and corrected region)
                parsed = _parse_supabase_url(self._db_url)
                if parsed:
                    user, password, host, port, dbname = parsed
                    from urllib.parse import unquote
                    kwargs = dict(
                        host=host, port=port,
                        user=unquote(user),
                        password=unquote(password),
                        database=unquote(dbname),
                    )
                else:
                    kwargs = dict(dsn=self._db_url)
                self._pool = await asyncpg.create_pool(
                    **kwargs,
                    min_size=1, max_size=5,
                    command_timeout=15, ssl=ssl_ctx,
                )
            else:
                self._pool = await asyncpg.create_pool(
                    self._db_url,
                    min_size=1, max_size=5,
                    command_timeout=15, ssl=False,
                )
            source = "Render" if _USE_SSL_RENDER else ("Supabase" if _USE_SSL else "PostgreSQL")
            print(f"[DB] {source} pool connected ✅")
            return self._pool
        except Exception as e:
            print(f"[DB] Pool creation failed: {e} — falling back to memory")
            self._db_available = False
            return None

    async def _exec(self, query: str, *args: Any) -> Optional[list]:
        """Execute a query and return rows as list of dicts."""
        pool = await self._get_pool()
        if pool is None:
            return None
        try:
            async with pool.acquire() as conn:
                rows = await conn.fetch(query, *args)
                return [dict(r) for r in rows]
        except Exception as e:
            print(f"[DB] Query error: {e}")
            return None

    async def _exec_one(self, query: str, *args: Any) -> Optional[dict]:
        rows = await self._exec(query, *args)
        if rows:
            return rows[0]
        return None

    async def _exec_status(self, query: str, *args: Any) -> bool:
        pool = await self._get_pool()
        if pool is None:
            return False
        try:
            async with pool.acquire() as conn:
                await conn.execute(query, *args)
                return True
        except Exception as e:
            print(f"[DB] Execute error: {e}")
            return False

    # ── Table bootstrap (idempotent — safe to call every startup) ───────────

    async def ensure_all_tables(self) -> None:
        """Creates ALL required tables if they don't exist yet.
        Must be called FIRST in lifespan before any other DB operation."""

        # ── bot_status ──────────────────────────────────────────────────────
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS bot_status (
                id                  INTEGER PRIMARY KEY DEFAULT 1,
                is_running          BOOLEAN     NOT NULL DEFAULT FALSE,
                mode                TEXT        NOT NULL DEFAULT 'demo',
                last_scan_at        TIMESTAMPTZ,
                total_trades        INTEGER     NOT NULL DEFAULT 0,
                win_rate            FLOAT       NOT NULL DEFAULT 0.0,
                total_pnl           FLOAT       NOT NULL DEFAULT 0.0,
                roi_percent         FLOAT       NOT NULL DEFAULT 0.0,
                target_win_rate     FLOAT       NOT NULL DEFAULT 65.0,
                current_threshold   INTEGER     NOT NULL DEFAULT 55,
                exchange            TEXT        NOT NULL DEFAULT 'mexc'
            )
        """)

        # ── trades ──────────────────────────────────────────────────────────
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS trades (
                id                      TEXT        PRIMARY KEY,
                symbol                  TEXT        NOT NULL,
                side                    TEXT        NOT NULL,
                entry_price             FLOAT,
                exit_price              FLOAT,
                stop_loss_price         FLOAT,
                take_profit_price       FLOAT,
                quantity                FLOAT,
                pnl                     FLOAT,
                pnl_percent             FLOAT,
                status                  TEXT        NOT NULL DEFAULT 'open',
                ai_confidence           INTEGER     NOT NULL DEFAULT 0,
                ai_reasoning            TEXT        NOT NULL DEFAULT '',
                market_condition        TEXT        NOT NULL DEFAULT 'unknown',
                pattern                 TEXT        NOT NULL DEFAULT '',
                created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                closed_at               TIMESTAMPTZ,
                rsi_at_entry            FLOAT,
                macd_hist_at_entry      FLOAT,
                bb_pct_at_entry         FLOAT,
                volume_at_entry         FLOAT,
                price_chg_pct_at_entry  FLOAT,
                entry_hour_utc          SMALLINT,
                ml_win_prob             FLOAT
            )
        """)
        await self._exec_status(
            "CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status)"
        )
        await self._exec_status(
            "CREATE INDEX IF NOT EXISTS idx_trades_created ON trades(created_at DESC)"
        )

        # ── ai_keys ─────────────────────────────────────────────────────────
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS ai_keys (
                id              SERIAL      PRIMARY KEY,
                provider        TEXT        NOT NULL,
                api_key         TEXT        NOT NULL,
                label           TEXT        NOT NULL DEFAULT '',
                display_label   TEXT        NOT NULL DEFAULT '',
                slot_index      INTEGER     NOT NULL DEFAULT 0,
                is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
                added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                base_url        TEXT        NOT NULL DEFAULT '',
                model_name      TEXT        NOT NULL DEFAULT '',
                UNIQUE(provider, api_key)
            )
        """)
        # Migrate old UNIQUE(provider, slot_index) → UNIQUE(provider, api_key) if needed
        await self._exec_status(
            "ALTER TABLE ai_keys DROP CONSTRAINT IF EXISTS ai_keys_provider_slot_index_key"
        )
        # Ensure new constraint exists
        await self._exec_status("""
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1 FROM pg_constraint
                    WHERE conname = 'ai_keys_provider_api_key_key'
                ) THEN
                    ALTER TABLE ai_keys ADD CONSTRAINT ai_keys_provider_api_key_key UNIQUE (provider, api_key);
                END IF;
            END $$;
        """)

        # ── agent_memory ────────────────────────────────────────────────────
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS agent_memory (
                id                  TEXT        PRIMARY KEY,
                lesson              TEXT        NOT NULL DEFAULT '',
                symbol              TEXT        NOT NULL DEFAULT '',
                market_condition    TEXT        NOT NULL DEFAULT 'unknown',
                pattern             TEXT        NOT NULL DEFAULT '',
                outcome             TEXT        NOT NULL DEFAULT 'loss',
                created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                importance          FLOAT       NOT NULL DEFAULT 5.0,
                category            TEXT        NOT NULL DEFAULT 'trade',
                tags                TEXT        NOT NULL DEFAULT '',
                confidence          FLOAT       NOT NULL DEFAULT 0.7,
                times_referenced    INT         NOT NULL DEFAULT 0,
                source              TEXT        NOT NULL DEFAULT 'auto'
            )
        """)
        await self._exec_status(
            "CREATE INDEX IF NOT EXISTS idx_agentmem_created ON agent_memory(created_at DESC)"
        )
        await self._exec_status(
            "CREATE INDEX IF NOT EXISTS idx_agentmem_importance ON agent_memory(importance DESC)"
        )
        # ── Migrate: add new columns if they don't exist (safe for existing DBs) ──
        for col, defn in [
            ("importance",       "FLOAT NOT NULL DEFAULT 5.0"),
            ("category",         "TEXT NOT NULL DEFAULT 'trade'"),
            ("tags",             "TEXT NOT NULL DEFAULT ''"),
            ("confidence",       "FLOAT NOT NULL DEFAULT 0.7"),
            ("times_referenced", "INT NOT NULL DEFAULT 0"),
            ("source",           "TEXT NOT NULL DEFAULT 'auto'"),
        ]:
            await self._exec_status(
                f"ALTER TABLE agent_memory ADD COLUMN IF NOT EXISTS {col} {defn}"
            )

        # ── bot_knowledge — persistent learned facts & strategies ────────────
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS bot_knowledge (
                id          TEXT        PRIMARY KEY,
                title       TEXT        NOT NULL DEFAULT '',
                content     TEXT        NOT NULL DEFAULT '',
                category    TEXT        NOT NULL DEFAULT 'general',
                importance  FLOAT       NOT NULL DEFAULT 5.0,
                tags        TEXT        NOT NULL DEFAULT '',
                source      TEXT        NOT NULL DEFAULT 'user',
                updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)
        await self._exec_status(
            "CREATE INDEX IF NOT EXISTS idx_botknow_importance ON bot_knowledge(importance DESC)"
        )
        await self._exec_status(
            "CREATE INDEX IF NOT EXISTS idx_botknow_category ON bot_knowledge(category)"
        )

        # ── conversations ────────────────────────────────────────────────────
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id  TEXT DEFAULT '',
                screen      TEXT DEFAULT 'chat',
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                provider    TEXT DEFAULT '',
                metadata    JSONB DEFAULT '{}',
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await self._exec_status(
            "CREATE INDEX IF NOT EXISTS idx_conv_screen ON conversations(screen)"
        )
        await self._exec_status(
            "CREATE INDEX IF NOT EXISTS idx_conv_created ON conversations(created_at DESC)"
        )

        # ── portfolio_assets ─────────────────────────────────────────────────
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS portfolio_assets (
                symbol          TEXT PRIMARY KEY,
                allocation_pct  FLOAT NOT NULL DEFAULT 10.0,
                enabled         BOOLEAN NOT NULL DEFAULT TRUE,
                added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ── exchange_accounts (multi-account trading) ────────────────────────
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS exchange_accounts (
                id              TEXT        PRIMARY KEY,
                name            TEXT        NOT NULL DEFAULT 'Account',
                exchange_name   TEXT        NOT NULL DEFAULT 'mexc',
                api_key         TEXT        NOT NULL DEFAULT '',
                api_secret      TEXT        NOT NULL DEFAULT '',
                api_passphrase  TEXT        NOT NULL DEFAULT '',
                mode            TEXT        NOT NULL DEFAULT 'demo',
                is_active       BOOLEAN     NOT NULL DEFAULT TRUE,
                balance         FLOAT       NOT NULL DEFAULT 10000.0,
                last_sync_at    TIMESTAMPTZ,
                created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ── server_nodes (multi-server HA) ───────────────────────────────────
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS server_nodes (
                node_id         TEXT        PRIMARY KEY,
                hostname        TEXT        NOT NULL DEFAULT '',
                is_leader       BOOLEAN     NOT NULL DEFAULT FALSE,
                last_heartbeat  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

        # ── trades: add account_id column (nullable — NULL = primary account) ─
        await self._exec_status(
            "ALTER TABLE trades ADD COLUMN IF NOT EXISTS account_id TEXT"
        )

        print("[DB] All tables bootstrapped ✅")

    # ── Bot status ─────────────────────────────────────────────────────────────

    async def save_server_domain(self, domain: str) -> None:
        """Store the current server domain so mobile clients can always find us."""
        await self._exec_status("""
            ALTER TABLE bot_status ADD COLUMN IF NOT EXISTS server_domain TEXT
        """)
        await self._exec_status(
            "UPDATE bot_status SET server_domain = $1 WHERE id = 1",
            domain
        )
        self._mem_status["server_domain"] = domain

    async def get_server_domain(self) -> str:
        """Retrieve the last registered server domain."""
        row = await self._exec_one(
            "SELECT server_domain FROM bot_status WHERE id = 1"
        )
        if row and row.get("server_domain"):
            return row["server_domain"]
        return self._mem_status.get("server_domain", "")

    async def ensure_bot_status(self) -> None:
        await self._exec_status("""
            INSERT INTO bot_status (id, is_running, mode, total_trades, win_rate,
                                    total_pnl, roi_percent, target_win_rate, current_threshold)
            VALUES (1, FALSE, 'demo', 0, 0.0, 0.0, 0.0, 65.0, 70)
            ON CONFLICT (id) DO NOTHING
        """)
        # ── ML columns migration (idempotent) ──────────────────────────────
        ml_cols = [
            ("rsi_at_entry",         "FLOAT"),
            ("macd_hist_at_entry",   "FLOAT"),
            ("bb_pct_at_entry",      "FLOAT"),
            ("volume_at_entry",      "FLOAT"),
            ("price_chg_pct_at_entry","FLOAT"),
            ("entry_hour_utc",       "SMALLINT"),
            ("ml_win_prob",          "FLOAT"),
        ]
        for col, dtype in ml_cols:
            await self._exec_status(
                f"ALTER TABLE trades ADD COLUMN IF NOT EXISTS {col} {dtype}"
            )
        print("[DB] ML columns verified ✅")

    async def get_bot_status(self) -> dict:
        row = await self._exec_one("SELECT * FROM bot_status WHERE id = 1")
        if row:
            self._mem_status.update(row)
            return dict(row)
        return self._mem_status.copy()

    async def update_bot_status(self, **kwargs: Any) -> None:
        if "last_scan_at" not in kwargs:
            kwargs["last_scan_at"] = datetime.utcnow()
        # asyncpg requires datetime objects for TIMESTAMPTZ, not ISO strings
        if "last_scan_at" in kwargs and isinstance(kwargs["last_scan_at"], str):
            try:
                kwargs["last_scan_at"] = datetime.fromisoformat(kwargs["last_scan_at"])
            except Exception:
                kwargs["last_scan_at"] = datetime.utcnow()
        self._mem_status.update(kwargs)

        if not kwargs:
            return

        set_parts = []
        values: list[Any] = []
        for i, (k, v) in enumerate(kwargs.items(), start=1):
            set_parts.append(f"{k} = ${i}")
            values.append(v)
        values.append(1)  # WHERE id = $N

        query = f"UPDATE bot_status SET {', '.join(set_parts)} WHERE id = ${len(values)}"
        await self._exec_status(query, *values)

    # ── Trades ────────────────────────────────────────────────────────────────

    async def create_trade(self, trade_data: dict) -> dict:
        trade_data = trade_data.copy()
        trade_data.setdefault("id", str(uuid.uuid4()))
        trade_data.setdefault("created_at", datetime.utcnow().isoformat())
        self._mem_trades.insert(0, trade_data)

        row = await self._exec_one("""
            INSERT INTO trades (
                id, symbol, side, entry_price, exit_price,
                stop_loss_price, take_profit_price, quantity, pnl, pnl_percent,
                status, ai_confidence, ai_reasoning, market_condition, pattern, created_at,
                rsi_at_entry, macd_hist_at_entry, bb_pct_at_entry,
                volume_at_entry, price_chg_pct_at_entry, entry_hour_utc, ml_win_prob
            ) VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,
                      $17,$18,$19,$20,$21,$22,$23)
            RETURNING *
        """,
            trade_data.get("id"),
            trade_data.get("symbol"),
            trade_data.get("side"),
            float(trade_data.get("entry_price") or 0),
            float(trade_data.get("exit_price") or 0) if trade_data.get("exit_price") else None,
            float(trade_data.get("stop_loss_price") or 0) if trade_data.get("stop_loss_price") else None,
            float(trade_data.get("take_profit_price") or 0) if trade_data.get("take_profit_price") else None,
            float(trade_data.get("quantity") or 0),
            float(trade_data.get("pnl") or 0) if trade_data.get("pnl") is not None else None,
            float(trade_data.get("pnl_percent") or 0) if trade_data.get("pnl_percent") is not None else None,
            trade_data.get("status", "open"),
            int(trade_data.get("ai_confidence") or 0),
            str(trade_data.get("ai_reasoning") or ""),
            str(trade_data.get("market_condition") or "unknown"),
            str(trade_data.get("pattern") or ""),
            datetime.fromisoformat(trade_data["created_at"]) if isinstance(trade_data.get("created_at"), str) else trade_data.get("created_at") or datetime.utcnow(),
            # ML feature columns
            float(trade_data["rsi_at_entry"])          if trade_data.get("rsi_at_entry")          is not None else None,
            float(trade_data["macd_hist_at_entry"])    if trade_data.get("macd_hist_at_entry")    is not None else None,
            float(trade_data["bb_pct_at_entry"])       if trade_data.get("bb_pct_at_entry")       is not None else None,
            float(trade_data["volume_at_entry"])       if trade_data.get("volume_at_entry")       is not None else None,
            float(trade_data["price_chg_pct_at_entry"]) if trade_data.get("price_chg_pct_at_entry") is not None else None,
            int(trade_data["entry_hour_utc"])          if trade_data.get("entry_hour_utc")        is not None else None,
            float(trade_data["ml_win_prob"])           if trade_data.get("ml_win_prob")           is not None else None,
        )
        return row or trade_data

    async def get_closed_trades_for_ml(self) -> list[dict]:
        """Returns all closed trades that have ML feature columns populated."""
        rows = await self._exec("""
            SELECT * FROM trades
            WHERE status = 'closed'
              AND pnl IS NOT NULL
              AND rsi_at_entry IS NOT NULL
            ORDER BY created_at ASC
        """)
        return rows or []

    async def update_trade(self, trade_id: str, updates: dict) -> dict:
        for t in self._mem_trades:
            if t.get("id") == trade_id:
                t.update(updates)
                break

        if not updates:
            return {}

        # Convert ISO strings to datetime for TIMESTAMPTZ columns
        _ts_cols = {"closed_at", "created_at", "last_scan_at"}
        coerced: dict[str, Any] = {}
        for k, v in updates.items():
            if k in _ts_cols and isinstance(v, str):
                try:
                    coerced[k] = datetime.fromisoformat(v.replace("Z", "+00:00"))
                except Exception:
                    coerced[k] = datetime.utcnow()
            else:
                coerced[k] = v

        set_parts = []
        values: list[Any] = []
        for i, (k, v) in enumerate(coerced.items(), start=1):
            set_parts.append(f"{k} = ${i}")
            values.append(v)
        values.append(trade_id)

        row = await self._exec_one(
            f"UPDATE trades SET {', '.join(set_parts)} WHERE id = ${len(values)} RETURNING *",
            *values,
        )
        return row or {}

    async def get_trades(self, limit: int = 50) -> list:
        rows = await self._exec(
            "SELECT * FROM trades ORDER BY created_at DESC LIMIT $1",
            min(limit, 500),
        )
        if rows is not None:
            return rows
        return self._mem_trades[:limit]

    # ── Agent memory (lessons) ────────────────────────────────────────────────

    async def save_lesson(self, lesson_data: dict) -> None:
        lesson_data = lesson_data.copy()
        lesson_data.setdefault("id", str(uuid.uuid4()))
        lesson_data.setdefault("created_at", datetime.utcnow().isoformat())
        self._mem_lessons.insert(0, lesson_data)

        raw_at = lesson_data.get("created_at")
        if isinstance(raw_at, str):
            try:
                raw_at = datetime.fromisoformat(raw_at.replace("Z", "+00:00"))
            except Exception:
                raw_at = datetime.utcnow()
        elif raw_at is None:
            raw_at = datetime.utcnow()

        await self._exec_status("""
            INSERT INTO agent_memory
                (id, lesson, symbol, market_condition, pattern, outcome, created_at,
                 importance, category, tags, confidence, source)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12)
            ON CONFLICT (id) DO NOTHING
        """,
            lesson_data.get("id"),
            str(lesson_data.get("lesson") or ""),
            str(lesson_data.get("symbol") or ""),
            str(lesson_data.get("market_condition") or "unknown"),
            str(lesson_data.get("pattern") or ""),
            str(lesson_data.get("outcome") or "loss"),
            raw_at,
            float(lesson_data.get("importance", 5.0)),
            str(lesson_data.get("category", "trade")),
            str(lesson_data.get("tags", "")),
            float(lesson_data.get("confidence", 0.7)),
            str(lesson_data.get("source", "auto")),
        )

    async def get_recent_lessons(self, limit: int = 5) -> list:
        rows = await self._exec(
            "SELECT * FROM agent_memory ORDER BY importance DESC, created_at DESC LIMIT $1",
            min(limit, 200),
        )
        if rows is not None:
            return rows
        return self._mem_lessons[:limit]

    async def search_memory(self, query: str, limit: int = 20) -> list:
        """Full-text search across agent_memory lessons."""
        q = f"%{query.lower()}%"
        rows = await self._exec(
            """SELECT * FROM agent_memory
               WHERE LOWER(lesson) LIKE $1 OR LOWER(symbol) LIKE $1
                  OR LOWER(pattern) LIKE $1 OR LOWER(tags) LIKE $1
               ORDER BY importance DESC, created_at DESC LIMIT $2""",
            q, min(limit, 100),
        )
        return rows or []

    async def delete_memory(self, memory_id: str) -> bool:
        """Delete a specific memory by ID."""
        return await self._exec_status(
            "DELETE FROM agent_memory WHERE id = $1", memory_id
        )

    # ── Bot Knowledge (persistent facts & strategies) ─────────────────────────

    async def save_knowledge(self, entry: dict) -> bool:
        entry = entry.copy()
        entry.setdefault("id", str(uuid.uuid4()))
        now = datetime.utcnow()
        return await self._exec_status("""
            INSERT INTO bot_knowledge
                (id, title, content, category, importance, tags, source, updated_at, created_at)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (id) DO UPDATE SET
                title      = EXCLUDED.title,
                content    = EXCLUDED.content,
                importance = EXCLUDED.importance,
                tags       = EXCLUDED.tags,
                updated_at = NOW()
        """,
            entry["id"],
            str(entry.get("title", "")),
            str(entry.get("content", "")),
            str(entry.get("category", "general")),
            float(entry.get("importance", 5.0)),
            str(entry.get("tags", "")),
            str(entry.get("source", "user")),
            now, now,
        )

    async def get_knowledge(self, category: str | None = None, limit: int = 50) -> list:
        """Retrieve bot knowledge, optionally filtered by category."""
        if category:
            rows = await self._exec(
                "SELECT * FROM bot_knowledge WHERE category = $1 ORDER BY importance DESC, updated_at DESC LIMIT $2",
                category, min(limit, 200),
            )
        else:
            rows = await self._exec(
                "SELECT * FROM bot_knowledge ORDER BY importance DESC, updated_at DESC LIMIT $1",
                min(limit, 200),
            )
        return rows or []

    async def search_knowledge(self, query: str, limit: int = 20) -> list:
        """Full-text search across bot_knowledge."""
        q = f"%{query.lower()}%"
        rows = await self._exec(
            """SELECT * FROM bot_knowledge
               WHERE LOWER(title) LIKE $1 OR LOWER(content) LIKE $1
                  OR LOWER(tags) LIKE $1 OR LOWER(category) LIKE $1
               ORDER BY importance DESC LIMIT $2""",
            q, min(limit, 100),
        )
        return rows or []

    async def delete_knowledge(self, kid: str) -> bool:
        return await self._exec_status("DELETE FROM bot_knowledge WHERE id = $1", kid)

    # ── AI Keys (persistent storage) ─────────────────────────────────────────

    async def save_ai_key(
        self,
        provider: str,
        api_key: str,
        slot_index: int,
        label: str,
        base_url: str = "",
        model_name: str = "",
    ) -> bool:
        """Upsert an AI key into the database — UNIQUE on (provider, api_key) → unlimited keys per provider."""
        # Auto-compute next slot_index if caller passes -1
        if slot_index < 0:
            row = await self._exec_one(
                "SELECT COALESCE(MAX(slot_index), -1) + 1 AS next_slot FROM ai_keys WHERE provider = $1",
                provider,
            )
            slot_index = int(row.get("next_slot", 0)) if row else 0

        return await self._exec_status("""
            INSERT INTO ai_keys (provider, api_key, label, slot_index, is_active, added_at, base_url, model_name, display_label)
            VALUES ($1, $2, $3, $4, TRUE, NOW(), $5, $6, $3)
            ON CONFLICT (provider, api_key)
            DO UPDATE SET label         = EXCLUDED.label,
                          display_label = EXCLUDED.display_label,
                          base_url      = EXCLUDED.base_url,
                          model_name    = EXCLUDED.model_name,
                          is_active     = TRUE,
                          added_at      = NOW()
        """, provider, api_key, label, slot_index, base_url or "", model_name or "")

    async def get_next_slot_index(self, provider: str) -> int:
        """Get next available slot_index for a provider (for unlimited keys)."""
        row = await self._exec_one(
            "SELECT COALESCE(MAX(slot_index), -1) + 1 AS next_slot FROM ai_keys WHERE provider = $1",
            provider,
        )
        return int(row.get("next_slot", 0)) if row else 0

    async def get_ai_keys(self, provider: Optional[str] = None) -> list[dict]:
        """Load all active AI keys, optionally filtered by provider."""
        if provider:
            rows = await self._exec(
                "SELECT * FROM ai_keys WHERE is_active = TRUE AND provider = $1 ORDER BY slot_index ASC",
                provider,
            )
        else:
            rows = await self._exec(
                "SELECT * FROM ai_keys WHERE is_active = TRUE ORDER BY provider, slot_index ASC"
            )
        return rows or []

    async def deactivate_ai_key(self, provider: str, slot_index: int) -> bool:
        """Mark a key as inactive (soft delete)."""
        return await self._exec_status(
            "UPDATE ai_keys SET is_active = FALSE WHERE provider = $1 AND slot_index = $2",
            provider, slot_index,
        )

    async def delete_ai_key(self, provider: str, label: str = "") -> bool:
        """Hard-delete AI key(s) from DB by provider and optional label."""
        if label:
            return await self._exec_status(
                "DELETE FROM ai_keys WHERE provider = $1 AND (label = $2 OR display_label = $2)",
                provider, label,
            )
        return await self._exec_status(
            "DELETE FROM ai_keys WHERE provider = $1",
            provider,
        )

    async def get_all_ai_keys_env(self) -> dict[str, str]:
        """Return a dict of env_var_name → api_key for all active stored keys."""
        rows = await self.get_ai_keys()
        result: dict[str, str] = {}
        for row in rows:
            provider   = row.get("provider", "")
            slot_index = int(row.get("slot_index", 0))
            api_key    = row.get("api_key", "")
            if provider == "gemini":
                env = "GEMINI_API_KEY" if slot_index == 0 else f"GEMINI_API_KEY_{slot_index + 1}"
            elif provider == "openai":
                env = "OPENAI_API_KEY" if slot_index == 0 else f"OPENAI_API_KEY_{slot_index + 1}"
            elif provider == "claude":
                env = "ANTHROPIC_API_KEY" if slot_index == 0 else f"ANTHROPIC_API_KEY_{slot_index + 1}"
            else:
                continue
            result[env] = api_key
        return result

    # ── Conversations (persistent chat history) ───────────────────────────────

    async def ensure_conversations_table(self) -> None:
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS conversations (
                id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                session_id  TEXT DEFAULT '',
                screen      TEXT DEFAULT 'chat',
                role        TEXT NOT NULL,
                content     TEXT NOT NULL,
                provider    TEXT DEFAULT '',
                metadata    JSONB DEFAULT '{}',
                created_at  TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        await self._exec_status(
            "CREATE INDEX IF NOT EXISTS idx_conv_screen ON conversations(screen)"
        )
        await self._exec_status(
            "CREATE INDEX IF NOT EXISTS idx_conv_created ON conversations(created_at DESC)"
        )

    async def save_message(
        self,
        role: str,
        content: str,
        screen: str = "chat",
        provider: str = "",
        session_id: str = "",
        metadata: dict | None = None,
    ) -> None:
        import json as _json
        await self._exec_status("""
            INSERT INTO conversations (session_id, screen, role, content, provider, metadata)
            VALUES ($1, $2, $3, $4, $5, $6::jsonb)
        """,
            session_id,
            screen,
            role,
            content[:8000],
            provider or "",
            _json.dumps(metadata or {}),
        )

    async def get_messages(
        self,
        screen: str | None = None,
        limit: int = 100,
        session_id: str | None = None,
    ) -> list[dict]:
        if screen and session_id:
            rows = await self._exec("""
                SELECT id::text, session_id, screen, role, content, provider, metadata, created_at
                FROM conversations
                WHERE screen = $1 AND session_id = $2
                ORDER BY created_at DESC LIMIT $3
            """, screen, session_id, min(limit, 500))
        elif screen:
            rows = await self._exec("""
                SELECT id::text, session_id, screen, role, content, provider, metadata, created_at
                FROM conversations
                WHERE screen = $1
                ORDER BY created_at DESC LIMIT $2
            """, screen, min(limit, 500))
        else:
            rows = await self._exec("""
                SELECT id::text, session_id, screen, role, content, provider, metadata, created_at
                FROM conversations
                ORDER BY created_at DESC LIMIT $1
            """, min(limit, 500))

        if not rows:
            return []

        import json as _json
        result = []
        for r in rows:
            row = dict(r)
            if hasattr(row.get("created_at"), "isoformat"):
                row["created_at"] = row["created_at"].isoformat()
            # Parse metadata if returned as string (asyncpg JSONB behaviour)
            meta = row.get("metadata")
            if isinstance(meta, str):
                try:
                    row["metadata"] = _json.loads(meta)
                except Exception:
                    row["metadata"] = {}
            elif meta is None:
                row["metadata"] = {}
            result.append(row)
        return result

    async def delete_old_messages(self, screen: str, keep: int = 500) -> None:
        """Keep only the most recent `keep` messages per screen."""
        await self._exec_status("""
            DELETE FROM conversations
            WHERE screen = $1
              AND id NOT IN (
                SELECT id FROM conversations
                WHERE screen = $1
                ORDER BY created_at DESC
                LIMIT $2
              )
        """, screen, keep)

    # ── Stats ─────────────────────────────────────────────────────────────────

    async def recalculate_stats(self) -> None:
        row = await self._exec_one("""
            SELECT
                COUNT(*) FILTER (WHERE status = 'closed') AS total,
                COUNT(*) FILTER (WHERE status = 'closed' AND pnl > 0) AS wins,
                COALESCE(SUM(pnl) FILTER (WHERE status = 'closed'), 0) AS total_pnl
            FROM trades
        """)
        if not row:
            return
        total = int(row.get("total") or 0)
        wins  = int(row.get("wins") or 0)
        total_pnl = float(row.get("total_pnl") or 0)
        win_rate  = round(wins / total * 100, 2) if total > 0 else 0.0
        await self.update_bot_status(
            total_trades=total,
            win_rate=win_rate,
            total_pnl=total_pnl,
        )

    # ── Portfolio Assets (Multi-Asset) ────────────────────────────────────────

    async def ensure_portfolio_assets_table(self) -> None:
        """Creates portfolio_assets table if it doesn't exist."""
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS portfolio_assets (
                symbol          TEXT PRIMARY KEY,
                allocation_pct  FLOAT NOT NULL DEFAULT 10.0,
                enabled         BOOLEAN NOT NULL DEFAULT TRUE,
                added_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

    async def get_portfolio_assets(self) -> list[dict]:
        rows = await self._exec("""
            SELECT symbol, allocation_pct, enabled, added_at
            FROM portfolio_assets
            ORDER BY allocation_pct DESC
        """)
        if not rows:
            return []
        result = []
        for r in rows:
            row = dict(r)
            if hasattr(row.get("added_at"), "isoformat"):
                row["added_at"] = row["added_at"].isoformat()
            result.append(row)
        return result

    async def set_portfolio_assets(self, assets: list[dict]) -> None:
        """Replace all portfolio assets with the given list."""
        await self._exec_status("DELETE FROM portfolio_assets")
        for asset in assets:
            symbol = str(asset.get("symbol", "")).upper().strip()
            alloc  = float(asset.get("allocation_pct", 10.0))
            enabled = bool(asset.get("enabled", True))
            if not symbol:
                continue
            await self._exec_status("""
                INSERT INTO portfolio_assets (symbol, allocation_pct, enabled)
                VALUES ($1, $2, $3)
                ON CONFLICT (symbol) DO UPDATE
                SET allocation_pct = $2, enabled = $3
            """, symbol, alloc, enabled)

    async def toggle_portfolio_asset(self, symbol: str, enabled: bool) -> None:
        await self._exec_status("""
            UPDATE portfolio_assets SET enabled = $1 WHERE symbol = $2
        """, enabled, symbol.upper())

    # ── Exchange Accounts (Multi-Account Trading) ─────────────────────────────

    async def get_exchange_accounts(self, active_only: bool = False) -> list[dict]:
        q = "SELECT * FROM exchange_accounts"
        if active_only:
            q += " WHERE is_active = TRUE"
        q += " ORDER BY created_at ASC"
        rows = await self._exec(q)
        if not rows:
            return []
        out = []
        for r in rows:
            row = dict(r)
            for ts_col in ("created_at", "last_sync_at"):
                if hasattr(row.get(ts_col), "isoformat"):
                    row[ts_col] = row[ts_col].isoformat()
            row.pop("api_secret", None)
            row.pop("api_passphrase", None)
            out.append(row)
        return out

    async def add_exchange_account(self, data: dict) -> dict:
        import uuid as _uuid
        aid = str(_uuid.uuid4())
        await self._exec_status("""
            INSERT INTO exchange_accounts
                (id, name, exchange_name, api_key, api_secret, api_passphrase, mode, is_active, balance)
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9)
        """,
            aid,
            str(data.get("name", "Account")),
            str(data.get("exchange_name", "mexc")).lower(),
            str(data.get("api_key", "")),
            str(data.get("api_secret", "")),
            str(data.get("api_passphrase", "")),
            str(data.get("mode", "demo")),
            bool(data.get("is_active", True)),
            float(data.get("balance", 10000.0)),
        )
        return {"id": aid, **data}

    async def delete_exchange_account(self, account_id: str) -> bool:
        return await self._exec_status(
            "DELETE FROM exchange_accounts WHERE id = $1", account_id
        )

    async def toggle_exchange_account(self, account_id: str, is_active: bool) -> bool:
        return await self._exec_status(
            "UPDATE exchange_accounts SET is_active = $1 WHERE id = $2",
            is_active, account_id
        )

    async def update_account_balance(self, account_id: str, balance: float) -> bool:
        return await self._exec_status("""
            UPDATE exchange_accounts
            SET balance = $1, last_sync_at = NOW()
            WHERE id = $2
        """, balance, account_id)

    # ── Server Nodes (Multi-Server HA) ────────────────────────────────────────

    async def ensure_server_nodes_table(self) -> None:
        await self._exec_status("""
            CREATE TABLE IF NOT EXISTS server_nodes (
                node_id         TEXT        PRIMARY KEY,
                hostname        TEXT        NOT NULL DEFAULT '',
                is_leader       BOOLEAN     NOT NULL DEFAULT FALSE,
                last_heartbeat  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
        """)

    async def register_server_node(self, node_id: str, hostname: str) -> None:
        await self._exec_status("""
            INSERT INTO server_nodes (node_id, hostname, is_leader, last_heartbeat, started_at)
            VALUES ($1, $2, FALSE, NOW(), NOW())
            ON CONFLICT (node_id) DO UPDATE
            SET hostname = $2, last_heartbeat = NOW()
        """, node_id, hostname)

    async def update_node_heartbeat(self, node_id: str, is_leader: bool) -> None:
        await self._exec_status("""
            UPDATE server_nodes
            SET last_heartbeat = NOW(), is_leader = $1
            WHERE node_id = $2
        """, is_leader, node_id)

    async def get_active_nodes(self, timeout_seconds: int = 75) -> list[dict]:
        rows = await self._exec(f"""
            SELECT * FROM server_nodes
            WHERE last_heartbeat > NOW() - INTERVAL '{timeout_seconds} seconds'
            ORDER BY started_at ASC
        """)
        if not rows:
            return []
        out = []
        for r in rows:
            row = dict(r)
            for ts in ("last_heartbeat", "started_at"):
                if hasattr(row.get(ts), "isoformat"):
                    row[ts] = row[ts].isoformat()
            out.append(row)
        return out

    async def get_all_nodes(self) -> list[dict]:
        rows = await self._exec("SELECT * FROM server_nodes ORDER BY started_at ASC")
        if not rows:
            return []
        out = []
        for r in rows:
            row = dict(r)
            for ts in ("last_heartbeat", "started_at"):
                if hasattr(row.get(ts), "isoformat"):
                    row[ts] = row[ts].isoformat()
            out.append(row)
        return out

    async def set_node_leader(self, node_id: str) -> None:
        await self._exec_status("UPDATE server_nodes SET is_leader = FALSE")
        await self._exec_status(
            "UPDATE server_nodes SET is_leader = TRUE, last_heartbeat = NOW() WHERE node_id = $1",
            node_id
        )

    async def remove_server_node(self, node_id: str) -> None:
        await self._exec_status("DELETE FROM server_nodes WHERE node_id = $1", node_id)

    # ── Zakat ─────────────────────────────────────────────────────────────────

    async def get_zakat_data(self) -> dict:
        """Returns profit/loss breakdown needed for Zakat calculation."""
        row = await self._exec_one("""
            SELECT
                COALESCE(SUM(pnl) FILTER (WHERE status='closed' AND pnl > 0), 0) AS total_profit,
                COALESCE(SUM(ABS(pnl)) FILTER (WHERE status='closed' AND pnl < 0), 0) AS total_loss,
                COALESCE(SUM(pnl) FILTER (WHERE status='closed'), 0) AS net_pnl,
                COUNT(*) FILTER (WHERE status='closed') AS total_trades,
                COUNT(*) FILTER (WHERE status='closed' AND pnl > 0) AS total_wins
            FROM trades
        """)
        if not row:
            return {
                "total_profit": 0.0,
                "total_loss":   0.0,
                "net_pnl":      0.0,
                "total_trades": 0,
                "total_wins":   0,
            }
        return {k: float(v) if isinstance(v, (int, float)) else v for k, v in dict(row).items()}

    async def get_monthly_profits(self) -> list[dict]:
        """Monthly profit breakdown for Zakat report."""
        rows = await self._exec("""
            SELECT
                TO_CHAR(COALESCE(closed_at, created_at), 'YYYY-MM') AS month,
                SUM(pnl) FILTER (WHERE pnl > 0) AS profit,
                SUM(ABS(pnl)) FILTER (WHERE pnl < 0) AS loss,
                COUNT(*) AS trades
            FROM trades
            WHERE status = 'closed'
            GROUP BY 1
            ORDER BY 1 ASC
        """)
        if not rows:
            return []
        return [
            {
                "month":   r.get("month", ""),
                "profit":  round(float(r.get("profit") or 0), 2),
                "loss":    round(float(r.get("loss") or 0), 2),
                "trades":  int(r.get("trades") or 0),
            }
            for r in rows
        ]
