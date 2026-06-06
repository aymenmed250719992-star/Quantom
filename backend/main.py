import asyncio
import json
import os
from contextlib import asynccontextmanager
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, FastAPI, HTTPException, Request, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

load_dotenv()   # Load .env only if values are not already set by environment

from adaptive_strategy import AdaptiveStrategy
from bybit_client import ExchangeClient
from database import DatabaseClient
from exchange_router import ExchangeRouter, EXCHANGE_CONFIGS
from scheduler import TradingScheduler
import meta_engine

db = DatabaseClient()
scheduler_instance = TradingScheduler(db)
adaptive = AdaptiveStrategy(db)

_target_win_rate: float = float(os.environ.get("TARGET_WIN_RATE", 65.0))
_current_threshold: int = int(os.environ.get("MIN_CONFIDENCE_SCORE", 55))


class ConnectionManager:
    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: str) -> None:
        dead: list[WebSocket] = []
        for conn in list(self.active_connections):
            try:
                await conn.send_text(message)
            except Exception:
                dead.append(conn)
        for c in dead:
            self.disconnect(c)


manager = ConnectionManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup — bootstrap tables FIRST (idempotent, CREATE IF NOT EXISTS)
    await db.ensure_all_tables()
    await db.ensure_bot_status()
    await db.ensure_conversations_table()
    scheduler_instance.set_broadcast_fn(manager.broadcast)
    scheduler_instance.set_adaptive(adaptive, lambda: _target_win_rate, lambda: _current_threshold)
    # ── Init ExchangeRouter first so it can select the best exchange ──────────
    router_inst = ExchangeRouter.get_instance()
    best_exchange = router_inst.get_active()   # auto-picks if strategy=auto
    print(f"[Router] Strategy={router_inst.strategy} | Best exchange → {best_exchange}")
    # Pre-warm the exchange singleton (now using the router-selected exchange)
    client = ExchangeClient.get_instance()
    print(f"[Startup] Exchange ready: {client.exchange_name} / {client.mode}")

    # ── ML model warm-up (loads from disk if previously trained) ────────────
    from ml_model import TradingMLModel
    ml = TradingMLModel.get_instance()
    if ml.is_trained:
        print(f"[Startup] ML model ready — {ml.n_samples} training samples")
    else:
        print("[Startup] ML model not trained yet — will train after 10 closed trades")

    # ── Restore AI keys from DB → env → GeminiAgent + AIAgent ──────────────
    try:
        stored_env = await db.get_all_ai_keys_env()
        keys_restored = 0
        for env_var, api_key in stored_env.items():
            if not os.environ.get(env_var):           # only inject if not already set
                os.environ[env_var] = api_key
                keys_restored += 1
        if keys_restored:
            print(f"[Startup] Restored {keys_restored} AI key(s) from DB into environment")

        # Re-init AI agents so they pick up restored keys
        from ai_agent import AIAgent
        from gemini_agent import GeminiAgent
        AIAgent.reset_instance()
        GeminiAgent.reset_instance()
        ai_agent_inst  = AIAgent.get_instance()
        gemini_inst    = GeminiAgent.get_instance()

        # Also load directly into pool (covers duplicates / index mismatches)
        ai_loaded = await ai_agent_inst.load_keys_from_db(db)

        # Inject Gemini keys into GeminiAgent pool (trading analysis)
        gemini_rows = await db.get_ai_keys("gemini")
        gemini_injected = 0
        for row in gemini_rows:
            key = row.get("api_key", "").strip()
            if key:
                injected = gemini_inst.inject_key(key)
                if injected:
                    gemini_injected += 1

        total = keys_restored + ai_loaded + gemini_injected
        avail = ai_agent_inst.pool_status().get("available_keys", 0)
        print(f"[Startup] AI key restore complete — {avail} key(s) available for autopilot")
        if total > 0:
            await manager.broadcast(json.dumps({
                "type": "log",
                "message": f"🔑 {avail} AI key(s) restored from database — Autopilot ready",
            }))
    except Exception as _ke:
        print(f"[Startup] AI key restore error: {_ke}")

    # ── Portfolio assets table (multi-asset) ────────────────────────────────
    try:
        await db.ensure_portfolio_assets_table()
        print("[Startup] Portfolio assets table ready ✅")
    except Exception as _pa:
        print(f"[Startup] Portfolio assets table error: {_pa}")

    # ── Register current server domain in DB (for mobile reconnection) ──────
    try:
        # Priority: SERVER_DOMAIN (Cloudflare) > Replit > Render
        cf_domain    = os.environ.get("SERVER_DOMAIN", "")
        replit_domain = os.environ.get("REPLIT_DEV_DOMAIN", "") or os.environ.get("REPLIT_DOMAINS", "")
        render_domain = os.environ.get("RENDER_EXTERNAL_URL", "")
        raw_domain = cf_domain or replit_domain or render_domain
        if raw_domain:
            clean = raw_domain.replace("https://", "").replace("http://", "").rstrip("/").split(",")[0].strip()
            await db.save_server_domain(clean)
            print(f"[Startup] Server domain registered: {clean}")
    except Exception as _sd:
        print(f"[Startup] Domain register warning: {_sd}")

    # ── Trading Company: init multi-agent orchestrator ──────────────────────
    try:
        from trading_company import TradingCompany
        from crowd_sim import CrowdSimulator
        from max_hermes import MaxHermes
        company = TradingCompany.get_instance()
        company.set_db(db)
        company.set_broadcast_fn(manager.broadcast)
        CrowdSimulator.get_instance(1000)
        MaxHermes.get_instance(db)
        print("[Startup] Trading Company ready — 6 departments | CrowdSim(1000) | MaxHermes ✅")
    except Exception as _tc:
        print(f"[Startup] Trading Company init warning: {_tc}")

    # ── Auto-resume: if bot was running before restart, start it again ──────
    saved = await db.get_bot_status()
    if saved.get("is_running", False):
        scheduler_instance.start()
        print(f"[Startup] Auto-resumed autopilot (was running before restart)")
        await manager.broadcast(json.dumps({
            "type": "log",
            "message": "♻️ Autopilot auto-resumed after server restart",
        }))

    # ── Multi-account: load secondary exchange accounts ─────────────────────
    try:
        from multi_account import MultiAccountManager
        ma_mgr = MultiAccountManager.get_instance()
        n_acc  = await ma_mgr.load_accounts(db)
        if n_acc:
            print(f"[Startup] {n_acc} secondary account(s) loaded for multi-account trading")
    except Exception as _ma:
        print(f"[Startup] Multi-account init error: {_ma}")

    # ── Node coordinator: leader election for multi-server HA ────────────────
    try:
        from node_coordinator import NodeCoordinator
        nc = NodeCoordinator.get_instance()
        nc.set_db(db)
        nc.set_scheduler_fns(scheduler_instance.start, scheduler_instance.stop)
        await nc.start()
        print(f"[Startup] Node coordinator ready — leader={nc.is_leader}")
    except Exception as _nc:
        print(f"[Startup] Node coordinator error: {_nc}")

    # ── Self-pinger: keeps server awake (Replit + Render + Cloudflare) ──────
    async def _keep_alive_loop():
        import httpx
        # Always ping localhost internally — avoids SSL issues
        ping_url = "http://localhost:5000/trade/ping"
        cf_url     = os.environ.get("SERVER_DOMAIN", "").rstrip("/")
        replit_url = os.environ.get("REPLIT_DEV_DOMAIN", "") or os.environ.get("REPLIT_DOMAINS", "")
        render_url = os.environ.get("RENDER_EXTERNAL_URL", "").rstrip("/")
        if cf_url:
            display_url = f"https://{cf_url}/trade/ping"
        elif replit_url:
            display_url = f"https://{replit_url.split(',')[0].strip().rstrip('/')}/trade/ping"
        elif render_url:
            display_url = f"{render_url}/trade/ping"
        else:
            display_url = ping_url
        print(f"[KeepAlive] Will ping → {display_url} every 4 min")
        await asyncio.sleep(60)  # wait 1 min after startup before first ping
        while True:
            try:
                async with httpx.AsyncClient(timeout=10) as _hx:
                    await _hx.get(ping_url)
                print("[KeepAlive] ✅ Self-ping OK — server stays awake")
            except Exception as _e:
                print(f"[KeepAlive] ping failed (non-critical): {_e}")
            await asyncio.sleep(240)  # ping every 4 minutes

    _keep_alive_task = asyncio.create_task(_keep_alive_loop())

    yield
    # Shutdown
    _keep_alive_task.cancel()
    scheduler_instance.stop()
    # Shutdown node coordinator
    try:
        from node_coordinator import NodeCoordinator
        await NodeCoordinator.get_instance().stop()
    except Exception:
        pass
    # Shutdown multi-account clients
    try:
        from multi_account import MultiAccountManager
        await MultiAccountManager.get_instance().close_all()
    except Exception:
        pass
    await ExchangeClient.get_instance().close()
    ExchangeClient.reset_instance()


app = FastAPI(
    title="Islamic Trading Bot",
    version="2.0.0",
    description="Self-learning Halal spot-only autonomous trading bot",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

router = APIRouter(prefix="/trade")


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = ""


class BrainChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = ""


class ModeRequest(BaseModel):
    mode: str


class SettingsRequest(BaseModel):
    max_risk_percent: Optional[float] = None
    min_confidence_score: Optional[int] = None
    target_win_rate: Optional[float] = None


class CredentialsRequest(BaseModel):
    api_key: str
    api_secret: str
    api_passphrase: str = ""
    exchange_name: str = "mexc"


class AIKeyRequest(BaseModel):
    provider: str          # "gemini" | "openai" | "claude" | "grok" | "groq" | "custom"
    api_key: str
    base_url: Optional[str] = None    # required for "custom", auto-set for "grok"/"groq"
    model_name: Optional[str] = None  # model to use (e.g. "grok-3-mini", "llama-3.3-70b-versatile")
    display_label: Optional[str] = None  # friendly name shown in the UI
    test_only: bool = False           # if True: validate key without saving it


# ─────────────────────────────────────────────────────────────────────────────

@router.get("/status")
async def get_status():
    status = await db.get_bot_status()
    client = ExchangeClient.get_instance()
    status["target_win_rate"] = _target_win_rate
    status["current_threshold"] = _current_threshold
    status["exchange"] = client.exchange_name
    return status


@router.get("/domain")
async def get_domain():
    """Public endpoint — returns the current server domain for mobile auto-reconnect."""
    cf_url     = os.environ.get("SERVER_DOMAIN", "")
    replit_url = os.environ.get("REPLIT_DEV_DOMAIN", "") or os.environ.get("REPLIT_DOMAINS", "")
    render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
    raw = cf_url or replit_url or render_url
    domain = raw.replace("https://", "").replace("http://", "").rstrip("/").split(",")[0].strip() if raw else ""
    return {"domain": domain, "ok": True}


@router.get("/ping")
async def ping():
    """Keep-alive endpoint — ping every 5 min via UptimeRobot to keep server 24/7."""
    return {"status": "alive", "ok": True}


@router.get("/health")
async def health_check():
    """Quantom V2 Core — Full system health dashboard for 24/7 monitoring."""
    import time
    start = time.time()

    # ── Database ──────────────────────────────────────────────────────────────
    db_ok = False
    db_source = "none"
    try:
        pool = await db._get_pool()
        db_ok = pool is not None
        from database import _SUPABASE_DB_URL
        db_source = "supabase" if _SUPABASE_DB_URL else "replit_postgresql"
    except Exception:
        pass

    # ── AI Keys ───────────────────────────────────────────────────────────────
    from ai_agent import AIAgent
    ai = AIAgent.get_instance()
    ai_pool = ai.pool_status()
    ai_keys_total     = ai_pool.get("total_keys", 0)
    ai_keys_available = ai_pool.get("available_keys", 0)
    ai_active         = ai_pool.get("active_provider")
    providers_summary = {}
    for prov, slots in ai_pool.get("providers", {}).items():
        ok = sum(1 for s in slots if s.get("available"))
        providers_summary[prov] = {"total": len(slots), "available": ok}

    # ── ML Model ──────────────────────────────────────────────────────────────
    ml_trained = False
    ml_samples = 0
    try:
        from ml_model import TradingMLModel
        ml = TradingMLModel.get_instance()
        ml_trained  = ml.is_trained
        ml_samples  = getattr(ml, "n_samples", 0)
    except Exception:
        pass

    # ── DEX ───────────────────────────────────────────────────────────────────
    dex_connected = False
    dex_network   = "unknown"
    dex_wallet    = False
    try:
        from dex_client import DEXClient
        dex = DEXClient.get_instance()
        dex_connected = dex.w3 is not None and dex.w3.is_connected()
        dex_network   = dex.network
        dex_wallet    = bool(dex.account)
    except Exception:
        pass

    # ── Exchange (CEX) ────────────────────────────────────────────────────────
    cex_name = "unknown"
    cex_mode = "demo"
    try:
        client  = ExchangeClient.get_instance()
        cex_name = client.exchange_name
        cex_mode = client.mode
    except Exception:
        pass

    # ── Bot Status ────────────────────────────────────────────────────────────
    bot = await db.get_bot_status()

    # ── Response time ─────────────────────────────────────────────────────────
    elapsed_ms = round((time.time() - start) * 1000, 1)

    # ── Overall health score ──────────────────────────────────────────────────
    checks = {
        "database":    db_ok,
        "ai_keys":     ai_keys_available > 0,
        "dex":         dex_connected,
        "bot_ready":   True,
        "ml_model":    ml_trained,
    }
    score = int(sum(checks.values()) / len(checks) * 100)
    status_label = "🟢 HEALTHY" if score >= 80 else ("🟡 DEGRADED" if score >= 50 else "🔴 CRITICAL")

    return {
        "status":        status_label,
        "health_score":  score,
        "response_ms":   elapsed_ms,
        "timestamp":     time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
        "checks": checks,
        "components": {
            "database": {
                "ok":     db_ok,
                "source": db_source,
            },
            "ai": {
                "total_keys":     ai_keys_total,
                "available_keys": ai_keys_available,
                "active_provider": ai_active,
                "providers":      providers_summary,
                "quantom_core":   "Quantom V2 Core",
            },
            "dex": {
                "connected": dex_connected,
                "network":   dex_network,
                "wallet":    dex_wallet,
            },
            "cex": {
                "exchange": cex_name,
                "mode":     cex_mode,
            },
            "ml_model": {
                "trained":  ml_trained,
                "samples":  ml_samples,
            },
            "bot": {
                "running":    bot.get("is_running", False),
                "mode":       bot.get("mode", "demo"),
                "total_trades": bot.get("total_trades", 0),
                "win_rate":   bot.get("win_rate", 0.0),
            },
        },
    }


@router.post("/bot/start")
async def start_bot():
    if scheduler_instance.is_running():
        return {"success": False, "message": "Bot is already running"}
    client = ExchangeClient.get_instance()
    scheduler_instance.start()
    await db.update_bot_status(is_running=True, mode=client.mode)
    await manager.broadcast(json.dumps({
        "type": "log",
        "message": (
            f"🟢 Autopilot started | mode: {client.mode.upper()} | "
            f"exchange: {client.exchange_name} | target: {_target_win_rate:.0f}%"
        ),
    }))
    return {"success": True, "message": "Autopilot started"}


@router.post("/bot/stop")
async def stop_bot():
    scheduler_instance.stop()
    await db.update_bot_status(is_running=False)
    await manager.broadcast(json.dumps({"type": "log", "message": "🔴 Autopilot stopped"}))
    return {"success": True, "message": "Autopilot stopped"}


@router.get("/trades")
async def get_trades(limit: int = 50):
    trades = await db.get_trades(limit=min(limit, 100))
    return {"trades": trades}


@router.get("/trades/export/csv")
async def export_trades_csv():
    """Export all trades as a downloadable CSV file."""
    import csv
    import io
    from fastapi.responses import StreamingResponse

    trades = await db.get_trades(limit=10000)
    output = io.StringIO()
    fields = [
        "id", "symbol", "side", "status",
        "entry_price", "exit_price", "quantity", "pnl", "pnl_percent",
        "stop_loss_price", "take_profit_price",
        "ai_confidence", "market_condition", "pattern",
        "rsi_at_entry", "macd_hist_at_entry", "bb_pct_at_entry", "ml_win_prob",
        "ai_reasoning", "created_at", "closed_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fields, extrasaction="ignore")
    writer.writeheader()
    for t in trades:
        row = {k: (t.get(k) if t.get(k) is not None else "") for k in fields}
        # Truncate reasoning to 300 chars to keep CSV readable
        if row.get("ai_reasoning"):
            row["ai_reasoning"] = str(row["ai_reasoning"])[:300]
        writer.writerow(row)
    output.seek(0)
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=trades.csv"},
    )


@router.get("/balance")
async def get_balance():
    client = ExchangeClient.get_instance()
    return await client.get_balance()


@router.get("/portfolio/chart")
async def get_portfolio_chart(days: int = 0):
    """
    Returns chart-ready analytics data.
    days=0 → all-time, days=7 → last 7 days, days=30 → last 30 days
    """
    from datetime import datetime, timedelta, timezone

    trades = await db.get_trades(limit=1000)
    closed = [t for t in trades if t.get("status") == "closed"]

    # Filter by time range
    if days > 0:
        cutoff = datetime.now(timezone.utc) - timedelta(days=days)
        def _parse(ts: str | None) -> datetime | None:
            if not ts:
                return None
            for fmt in ("%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(ts[:26].replace("Z", ""), fmt)
                    return dt.replace(tzinfo=timezone.utc)
                except Exception:
                    pass
            return None
        closed = [t for t in closed if (_parse(t.get("closed_at") or t.get("created_at")) or datetime.min.replace(tzinfo=timezone.utc)) >= cutoff]

    # ── Daily aggregation ──────────────────────────────────────────────────────
    from collections import defaultdict
    daily: dict[str, dict] = defaultdict(lambda: {"pnl": 0.0, "wins": 0, "losses": 0, "trades": 0})
    for t in closed:
        ts = t.get("closed_at") or t.get("created_at", "")
        date_key = ts[:10] if ts else "unknown"
        pnl = float(t.get("pnl") or 0)
        daily[date_key]["pnl"]    += pnl
        daily[date_key]["trades"] += 1
        if pnl > 0:
            daily[date_key]["wins"] += 1
        else:
            daily[date_key]["losses"] += 1

    daily_sorted = [{"date": k, **v, "pnl": round(v["pnl"], 4)} for k, v in sorted(daily.items()) if k != "unknown"]

    # ── Cumulative PnL ─────────────────────────────────────────────────────────
    cumulative = []
    running = 0.0
    for d in daily_sorted:
        running += d["pnl"]
        cumulative.append({"date": d["date"], "cumPnl": round(running, 4)})

    # ── Streaks ────────────────────────────────────────────────────────────────
    results = [(float(t.get("pnl") or 0) > 0) for t in closed]
    cur_streak_type = "win" if (results[-1] if results else False) else "loss"
    cur_streak = 0
    for r in reversed(results):
        if (r and cur_streak_type == "win") or (not r and cur_streak_type == "loss"):
            cur_streak += 1
        else:
            break

    best_win = best_loss = 0
    cur_w = cur_l = 0
    for r in results:
        if r:
            cur_w += 1; cur_l = 0
        else:
            cur_l += 1; cur_w = 0
        best_win  = max(best_win,  cur_w)
        best_loss = max(best_loss, cur_l)

    # ── Top / Bottom trades ────────────────────────────────────────────────────
    def _enrich(t: dict) -> dict:
        ep = float(t.get("entry_price") or 0)
        xp = float(t.get("exit_price") or 0)
        side = t.get("side", "buy")
        pnl_pct = 0.0
        if ep > 0 and xp > 0:
            raw = (xp - ep) / ep * 100
            pnl_pct = raw if side == "buy" else -raw
        return {**t, "pnl_percent": round(pnl_pct, 3)}

    sorted_by_pnl = sorted(closed, key=lambda t: float(t.get("pnl") or 0), reverse=True)
    top_trades    = [_enrich(t) for t in sorted_by_pnl[:5]]
    bottom_trades = [_enrich(t) for t in sorted_by_pnl[-5:] if (t.get("pnl") or 0) < 0]

    # ── By-symbol stats ────────────────────────────────────────────────────────
    sym_map: dict[str, dict] = defaultdict(lambda: {"trades": 0, "wins": 0, "pnl": 0.0})
    for t in closed:
        sym = (t.get("symbol") or "???").replace("/USDT", "").replace("-USDT", "")
        pnl = float(t.get("pnl") or 0)
        sym_map[sym]["trades"] += 1
        sym_map[sym]["pnl"]    += pnl
        if pnl > 0:
            sym_map[sym]["wins"] += 1

    by_symbol = sorted([
        {
            "symbol":   sym,
            "trades":   d["trades"],
            "wins":     d["wins"],
            "pnl":      round(d["pnl"], 4),
            "win_rate": round(d["wins"] / d["trades"] * 100, 1) if d["trades"] else 0,
        }
        for sym, d in sym_map.items()
    ], key=lambda x: x["pnl"], reverse=True)

    total_pnl = sum(float(t.get("pnl") or 0) for t in closed)
    wins_all  = [t for t in closed if (t.get("pnl") or 0) > 0]
    losses_all = [t for t in closed if (t.get("pnl") or 0) <= 0]
    win_pnl   = sum(float(t.get("pnl") or 0) for t in wins_all)
    loss_pnl  = abs(sum(float(t.get("pnl") or 0) for t in losses_all))
    starting  = float(os.environ.get("DEMO_BALANCE_USDT", 10000))

    return {
        "daily":        daily_sorted,
        "cumulative":   cumulative,
        "streak": {
            "current_type":  cur_streak_type,
            "current_count": cur_streak,
            "best_win":      best_win,
            "best_loss":     best_loss,
        },
        "top_trades":    top_trades,
        "bottom_trades": bottom_trades,
        "by_symbol":     by_symbol,
        "summary": {
            "total_pnl":      round(total_pnl, 4),
            "roi_percent":    round(total_pnl / starting * 100, 3),
            "total_trades":   len(closed),
            "wins":           len(wins_all),
            "losses":         len(losses_all),
            "win_rate":       round(len(wins_all) / len(closed) * 100, 1) if closed else 0.0,
            "profit_factor":  round(win_pnl / loss_pnl, 2) if loss_pnl > 0 else (9.99 if win_pnl > 0 else 0.0),
            "avg_win":        round(win_pnl / len(wins_all), 4) if wins_all else 0.0,
            "avg_loss":       round(loss_pnl / len(losses_all), 4) if losses_all else 0.0,
        },
        "days_filter": days,
    }


@router.get("/portfolio")
async def get_portfolio():
    trades = await db.get_trades(limit=500)
    closed = [t for t in trades if t.get("status") == "closed"]
    open_trades = [t for t in trades if t.get("status") == "open"]

    total_pnl = sum(float(t.get("pnl") or 0) for t in closed)
    wins = [t for t in closed if (t.get("pnl") or 0) > 0]
    losses = [t for t in closed if (t.get("pnl") or 0) <= 0]

    client = ExchangeClient.get_instance()
    bal = await client.get_balance()
    starting_balance = float(os.environ.get("DEMO_BALANCE_USDT", 10000))
    current_balance = bal.get("total", starting_balance)
    roi_percent = (total_pnl / starting_balance * 100) if starting_balance > 0 else 0.0

    win_pnl = sum(float(t.get("pnl") or 0) for t in wins)
    loss_pnl = abs(sum(float(t.get("pnl") or 0) for t in losses))
    profit_factor = win_pnl / loss_pnl if loss_pnl > 0 else (9.99 if win_pnl > 0 else 0.0)

    enriched: list[dict] = []
    for t in closed[-20:]:
        ep = float(t.get("entry_price") or 0)
        xp = float(t.get("exit_price") or 0)
        side = t.get("side", "buy")
        pnl_pct = 0.0
        if ep > 0 and xp > 0:
            raw = (xp - ep) / ep * 100
            pnl_pct = raw if side == "buy" else -raw
        enriched.append({**t, "pnl_percent": round(pnl_pct, 3)})

    return {
        "total_pnl": round(total_pnl, 4),
        "roi_percent": round(roi_percent, 3),
        "total_closed": len(closed),
        "total_open": len(open_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(closed) * 100, 2) if closed else 0.0,
        "target_win_rate": _target_win_rate,
        "profit_factor": round(profit_factor, 2),
        "avg_win": round(win_pnl / len(wins), 4) if wins else 0.0,
        "avg_loss": round(loss_pnl / len(losses), 4) if losses else 0.0,
        "recent_trades": enriched,
        "exchange": client.exchange_name,
        "mode": client.mode,
    }


@router.get("/performance")
async def get_performance():
    report = await adaptive.get_performance_report(_target_win_rate)
    report["current_threshold"] = _current_threshold
    return report


async def _learn_from_conversation(question: str, answer: str, source: str) -> None:
    """
    Quantom V2 Core — extract and permanently store lessons from every conversation.
    Learns from: trading signals, risk rules, TA insights, user preferences, strategy discussions.
    """
    try:
        # Extended keyword set covering Quantom V2 Core domains
        LEARN_KEYWORDS = [
            # Technical Analysis
            "rsi", "macd", "bollinger", "ema", "sma", "atr", "vwap", "obv",
            "support", "resistance", "دعم", "مقاومة", "order block", "fair value gap",
            "breakout", "breakdown", "squeeze", "divergence", "تقارب", "تباعد",
            "bullish", "bearish", "صاعد", "هابط", "consolidation", "trend", "اتجاه",
            "هيكل", "market structure", "higher high", "lower low", "pivot",
            # Strategy & Risk
            "strategy", "استراتيج", "risk", "مخاطر", "stop loss", "take profit",
            "وقف خسارة", "هدف ربح", "risk reward", "r:r", "position size",
            "liquidation", "تصفية", "margin", "leverage", "رافعة", "exposure",
            "alpha", "beta", "sharpe", "drawdown", "سحب", "capital preservation",
            # Trading concepts
            "trading", "تداول", "pattern", "نمط", "signal", "إشارة",
            "scalping", "سكالبينج", "swing", "spot", "cfd", "futures",
            "volume", "حجم", "momentum", "زخم", "breakeven", "تعادل",
            # Portfolio & Market
            "portfolio", "محفظة", "allocation", "توزيع", "diversif",
            "analysis", "تحليل", "مؤشر", "indicator", "candle", "شمعة",
            "pump", "dump", "whale", "accumulation", "distribution",
            # Halal & DEX
            "halal", "حلال", "spot", "dex", "swap", "riba", "gharar",
            "uniswap", "pancakeswap", "blockchain", "بلوكشين", "web3",
            # Quantom V2 Core specific
            "quantom", "كوانتوم", "exposure", "buffer zone", "atr buffer",
            "invalidation", "liquidation price", "market type",
            # User preferences & rules
            "تعلم", "learn", "remember", "تذكر", "rule", "قاعدة",
            "always", "never", "دائماً", "أبداً", "prefer", "أفضل",
        ]
        combined = (question + " " + answer).lower()
        matched_kw = [kw for kw in LEARN_KEYWORDS if kw in combined]

        # Learn from ANY meaningful exchange — not just keyword-matched
        snippet = answer.strip()
        if len(snippet) < 40:
            return

        # Determine market_condition based on content
        if any(k in combined for k in ["rsi", "macd", "bollinger", "atr", "ema", "breakout"]):
            market_condition = "technical_analysis"
        elif any(k in combined for k in ["risk", "stop loss", "liquidation", "margin", "exposure"]):
            market_condition = "risk_management"
        elif any(k in combined for k in ["strategy", "استراتيج", "scalping", "swing", "trend"]):
            market_condition = "strategy"
        elif any(k in combined for k in ["halal", "حلال", "spot", "dex", "riba"]):
            market_condition = "islamic_finance"
        elif matched_kw:
            market_condition = "trading_knowledge"
        else:
            market_condition = "learning"

        # Always save if there's a meaningful response (Quantom V2 learns everything)
        await db.save_lesson({
            "lesson": f"[QUANTOM-{source.upper()}] Q: {question[:150]} → A: {snippet[:600]}",
            "symbol": "QUANTOM_CORE",
            "market_condition": market_condition,
            "pattern": f"quantom_{source}_insight",
            "outcome": "learn",
        })
        if matched_kw:
            print(f"[Quantom] 🧠 Learned from {source}: {market_condition} | keywords: {matched_kw[:3]}")
    except Exception as e:
        print(f"[learn_from_conversation] error: {e}")


@router.post("/chat")
async def chat_endpoint(request: ChatRequest):
    from ai_agent import AIAgent
    agent  = AIAgent.get_instance()
    trades = await db.get_trades(limit=20)
    status = await db.get_bot_status()
    performance = await adaptive.get_performance_report(_target_win_rate)
    # Save user message
    await db.save_message(
        role="user", content=request.message,
        screen="chat", session_id=request.session_id or "",
    )
    # Load conversation history for long-term memory (last 16 messages)
    history = await db.get_messages(screen="chat", limit=16)
    history_ordered = list(reversed(history))  # oldest first
    result = await agent.chat(request.message, trades, status, performance, history=history_ordered)
    answer   = result.get("response", "")
    provider = result.get("provider", "")
    # Save assistant response
    await db.save_message(
        role="assistant",
        content=answer,
        screen="chat",
        provider=provider,
        session_id=request.session_id or "",
    )
    # 🧠 Learn from this conversation if AI-powered
    if provider and provider != "rule-based" and answer:
        asyncio.ensure_future(
            _learn_from_conversation(request.message, answer, "tutor")
        )
    return result


@router.post("/brain/chat")
async def brain_chat_endpoint(request: BrainChatRequest):
    """Natural language conversation with the agent brain — understands Arabic commands."""
    from agent_core import TradingAgent
    from ai_agent import AIAgent
    global _current_threshold, _target_win_rate

    agent_inst = AIAgent.get_instance()
    trades = await db.get_trades(limit=30)
    status = await db.get_bot_status()

    # Get full memory context
    try:
        ta   = TradingAgent.get_instance(db=db)
        mem  = ta.memory
        lessons = await mem.get_long_term_lessons(limit=10)
        memory_summary = {
            "strategy": {
                "current":    mem._current_strategy,
                "confidence": round(mem._strategy_confidence, 2),
                "goal":       mem._goal,
                "overrides":  mem._strategy_overrides,
            },
            "streaks": {
                "consecutive_wins":   mem._consecutive_wins,
                "consecutive_losses": mem._consecutive_losses,
                "last_results":       mem._last_3_results,
                "emergency_halted":   mem._emergency_halted,
            },
            "settings": {
                "target_win_rate":    _target_win_rate,
                "current_threshold":  _current_threshold,
            },
            "lessons": lessons,
        }
    except Exception:
        memory_summary = {}
        ta = None

    # Load recent brain conversation history for context
    history = await db.get_messages(screen="brain", limit=16)
    history_ordered = list(reversed(history))  # oldest first

    # Save user message
    await db.save_message(
        role="user", content=request.message,
        screen="brain", session_id=request.session_id or "",
    )

    # Get AI response
    result = await agent_inst.brain_chat(
        request.message, trades, status, memory_summary,
        history=history_ordered,
    )

    # Auto-execute detected command
    executed_command = None
    cmd = result.get("detected_command")
    if cmd and ta:
        try:
            c = cmd["command"]
            if c == "set_strategy":
                v = cmd.get("value", "")
                STRATEGIES = ["mean_reversion", "trend_following", "momentum_breakout", "scalping", "conservative"]
                if v in STRATEGIES:
                    ta.memory.set_strategy(v, confidence=1.0)
                    executed_command = f"set_strategy:{v}"
            elif c == "halt":
                ta.memory._emergency_halted = True
                ta.memory._save_state()
                if scheduler_instance.is_running():
                    scheduler_instance.stop()
                    await db.update_bot_status(is_running=False)
                executed_command = "halt"
            elif c == "resume":
                ta.memory.reset_emergency()
                executed_command = "resume"
            elif c == "set_goal":
                v = cmd.get("value", "")
                if v:
                    ta.memory._goal = v
                    ta.memory._save_state()
                    executed_command = f"set_goal:{v[:40]}"
            elif c == "set_threshold":
                v = max(40, min(95, int(cmd.get("threshold", 55))))
                _current_threshold = v
                os.environ["MIN_CONFIDENCE_SCORE"] = str(v)
                scheduler_instance.set_adaptive(adaptive, lambda: _target_win_rate, lambda: _current_threshold)
                executed_command = f"set_threshold:{v}"
            elif c == "set_win_rate":
                v = float(max(50, min(90, int(cmd.get("threshold", 65)))))
                _target_win_rate = v
                os.environ["TARGET_WIN_RATE"] = str(v)
                scheduler_instance.set_adaptive(adaptive, lambda: _target_win_rate, lambda: _current_threshold)
                executed_command = f"set_win_rate:{v}"
            elif c == "reset_patterns":
                ta.memory._pattern_scores = {}
                ta.memory._save_state()
                executed_command = "reset_patterns"
            elif c == "force_scan":
                # Trigger an immediate market scan
                if scheduler_instance.is_running():
                    asyncio.ensure_future(scheduler_instance._scan_markets())
                    executed_command = "force_scan"
            elif c == "demo_mode":
                os.environ["TRADING_MODE"] = "demo"
                await db.update_bot_status(mode="demo")
                executed_command = "demo_mode"
            elif c == "live_mode":
                os.environ["TRADING_MODE"] = "live"
                await db.update_bot_status(mode="live")
                executed_command = "live_mode"
            elif c == "close_all_trades":
                # Close all open trades at current market price
                open_trades = [t for t in trades if t.get("status") == "open"]
                closed_count = 0
                from datetime import datetime as _dt
                for t in open_trades:
                    try:
                        sym = t.get("symbol", "")
                        from bybit_client import ExchangeClient as _EC
                        _client = _EC.get_instance()
                        cp = await _client.get_current_price(sym)
                        if cp and cp > 0:
                            from risk_manager import RiskManager as _RM
                            pnl = _RM().estimate_pnl(t.get("side","buy"), float(t.get("entry_price",0)), cp, float(t.get("quantity",0)))
                            await db.update_trade(t["id"], {
                                "status": "closed", "exit_price": cp,
                                "pnl": pnl, "closed_at": _dt.utcnow().isoformat(),
                            })
                            closed_count += 1
                    except Exception:
                        pass
                if closed_count > 0:
                    await db.recalculate_stats()
                executed_command = f"close_all_trades:{closed_count}"

            if executed_command:
                await manager.broadcast(json.dumps({
                    "type": "log",
                    "message": f"🧠 Brain command executed via chat: {executed_command}",
                }))
        except Exception as _ce:
            print(f"[BrainChat] Command exec error: {_ce}")

    # ── Meta Engine: execute file/sql/shell commands ───────────────────────
    meta_results: list[str] = []
    all_cmds = result.get("all_commands", [])
    meta_cmds = [c for c in all_cmds if c.get("type") == "meta"]

    # Phase 1 — reads (read_file / list_files)
    read_context: dict[str, str] = {}
    for mc in meta_cmds:
        op  = mc.get("operation", "")
        val = mc.get("value", "")
        if op == "read_file" and val:
            content = meta_engine.read_file(val)
            read_context[val] = content
        elif op == "list_files" and val:
            listing = meta_engine.list_files(val)
            read_context[f"dir:{val}"] = listing

    # Phase 2 — if reads happened, re-call AI with file contents
    if read_context:
        ctx_block = "\n\n".join(
            f"=== {k} ===\n{v}" for k, v in read_context.items()
        )
        augmented = (
            f"{request.message}\n\n"
            f"[نتائج القراءة — استخدمها الآن للتعديل]:\n{ctx_block}"
        )
        try:
            result2 = await agent_inst.brain_chat(
                augmented, trades, status, memory_summary,
                history=history_ordered,
            )
            result = result2
            # Re-collect meta commands from phase-2 response
            all_cmds  = result.get("all_commands", [])
            meta_cmds = [c for c in all_cmds if c.get("type") == "meta"]
        except Exception as _me2:
            print(f"[Meta] Phase-2 brain_chat error: {_me2}")

    # Phase 3 — write / sql / shell (after possible phase-2 re-call)
    for mc in meta_cmds:
        op = mc.get("operation", "")
        if op == "write_file":
            path    = mc.get("path", mc.get("value", ""))
            content = mc.get("content", "")
            if path and content:
                res = meta_engine.write_file(path, content)
                meta_results.append(res)
                print(f"[Meta] write_file: {res}")
        elif op == "exec_sql":
            val = mc.get("value", "")
            if val:
                res = await meta_engine.exec_sql(val, db)
                meta_results.append(f"🗄️ SQL:\n{res}")
                print(f"[Meta] exec_sql done")
        elif op == "exec_shell":
            val = mc.get("value", "")
            if val:
                res = await meta_engine.exec_shell(val)
                meta_results.append(f"🖥️ Shell:\n{res}")
                print(f"[Meta] exec_shell done")

    if meta_results:
        await manager.broadcast(json.dumps({
            "type": "log",
            "message": f"🔧 Meta Engine: {len(meta_results)} عملية نُفِّذت",
        }))

    brain_answer   = result.get("response", "")
    brain_provider = result.get("provider", "")

    # Append meta results to brain answer
    if meta_results:
        meta_block = "\n\n---\n🔧 **نتائج التنفيذ:**\n" + "\n\n".join(meta_results)
        brain_answer = (brain_answer + meta_block).strip()
    # Save assistant response
    await db.save_message(
        role="assistant",
        content=brain_answer,
        screen="brain",
        provider=brain_provider,
        session_id=request.session_id or "",
        metadata={"executed_command": executed_command} if executed_command else {},
    )
    # 🧠 Learn from brain conversation if AI-powered
    if brain_provider and brain_provider != "rule-based" and brain_answer:
        import asyncio as _aio
        _aio.ensure_future(
            _learn_from_conversation(request.message, brain_answer, "brain")
        )

    return {
        "response":          brain_answer,
        "provider":          brain_provider,
        "key":               result.get("key"),
        "executed_command":  executed_command,
        "meta_count":        len(meta_results),
    }


# ── Meta Engine — Direct control endpoint ─────────────────────────────────────

class MetaRequest(BaseModel):
    operation: str          # read_file | write_file | list_files | exec_sql | exec_shell
    path: Optional[str] = None
    content: Optional[str] = None
    query: Optional[str] = None
    command: Optional[str] = None


@router.post("/meta/execute")
async def meta_execute(req: MetaRequest):
    """Direct Meta Engine execution — absolute infrastructure control."""
    op = req.operation.lower().strip()
    try:
        if op == "read_file":
            if not req.path:
                raise HTTPException(status_code=400, detail="path required")
            result = meta_engine.read_file(req.path)
            return {"operation": op, "result": result, "success": True}

        elif op == "write_file":
            if not req.path or req.content is None:
                raise HTTPException(status_code=400, detail="path and content required")
            result = meta_engine.write_file(req.path, req.content)
            return {"operation": op, "result": result, "success": "❌" not in result}

        elif op == "list_files":
            if not req.path:
                raise HTTPException(status_code=400, detail="path required")
            result = meta_engine.list_files(req.path)
            return {"operation": op, "result": result, "success": True}

        elif op == "exec_sql":
            q = req.query or req.content or ""
            if not q:
                raise HTTPException(status_code=400, detail="query required")
            result = await meta_engine.exec_sql(q, db)
            return {"operation": op, "result": result, "success": "❌" not in result}

        elif op == "exec_shell":
            cmd = req.command or req.content or ""
            if not cmd:
                raise HTTPException(status_code=400, detail="command required")
            result = await meta_engine.exec_shell(cmd)
            return {"operation": op, "result": result, "success": True}

        elif op == "project_map":
            return {"operation": op, "result": meta_engine.PROJECT_MAP, "success": True}

        else:
            raise HTTPException(status_code=400, detail=f"Unknown operation: {op}")

    except HTTPException:
        raise
    except Exception as e:
        return {"operation": op, "result": f"❌ Error: {e}", "success": False}


@router.get("/conversations")
async def get_conversations(screen: str = "chat", limit: int = 80):
    """Return saved conversation history for a given screen."""
    rows = await db.get_messages(screen=screen, limit=min(limit, 300))
    return {"messages": rows, "count": len(rows)}


@router.delete("/conversations")
async def clear_conversations(screen: str = "chat"):
    """Delete all messages for a given screen."""
    await db.delete_old_messages(screen=screen, keep=0)
    return {"success": True, "message": f"Cleared {screen} history"}


# ── AI Provider management ────────────────────────────────────────────────────

@router.get("/ai/providers")
async def get_ai_providers():
    """Returns status of all configured AI providers (Gemini, OpenAI, Claude)."""
    from ai_agent import AIAgent
    return AIAgent.get_instance().pool_status()


@router.post("/ai/key")
async def add_ai_key(request: AIKeyRequest):
    """Add/test an AI API key for any provider (Gemini/OpenAI/Claude/Grok/Groq/Custom)."""
    from ai_agent import AIAgent, PROVIDERS as AI_PROVIDERS_LIST
    from gemini_agent import GeminiAgent

    provider  = request.provider.lower()
    api_key   = request.api_key.strip()
    base_url  = request.base_url or ""
    model_nm  = request.model_name or ""
    disp_lbl  = request.display_label or ""

    # ── test_only: validate without persisting ────────────────────────────────
    if request.test_only:
        try:
            import httpx, asyncio
            # Determine endpoint + model for quick ping
            _DEFAULTS = {
                "gemini":  ("https://generativelanguage.googleapis.com", "gemini-2.5-flash"),
                "openai":  ("https://api.openai.com/v1", "gpt-4o-mini"),
                "claude":  ("https://api.anthropic.com/v1", "claude-3-5-haiku-20241022"),
                "grok":    ("https://api.x.ai/v1", "grok-3-mini"),
                "groq":    ("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile"),
                "custom":  (base_url, model_nm or "gpt-4o-mini"),
            }
            b_url, model = _DEFAULTS.get(provider, ("", ""))
            if provider == "custom" and not b_url:
                return {"success": False, "error": "أدخل Base URL للمزود المخصص"}
            label_out = disp_lbl or provider.upper()

            if provider == "gemini":
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.post(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}",
                        json={"contents": [{"parts": [{"text": "hi"}]}]},
                    )
                ok = r.status_code in (200, 201)
            else:
                async with httpx.AsyncClient(timeout=10) as c:
                    r = await c.post(
                        f"{b_url}/chat/completions",
                        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                        json={"model": model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                    )
                ok = r.status_code in (200, 201)
            if ok:
                return {"success": True,  "label": label_out, "tested": True, "message": "المفتاح صالح ✅"}
            else:
                return {"success": False, "error": f"المفتاح غير صالح (HTTP {r.status_code})"}
        except Exception as e:
            return {"success": False, "error": f"تعذّر الاتصال: {str(e)[:120]}"}

    # ── Normal add path ───────────────────────────────────────────────────────
    agent = AIAgent.get_instance()
    result = agent.add_key(
        provider, api_key, _db=db,
        base_url=base_url, model_name=model_nm, display_label=disp_lbl,
    )
    if result.get("success"):
        if provider == "gemini":
            GeminiAgent.get_instance().inject_key(api_key)
        status = agent.pool_status()
        lbl    = result.get("label", provider.upper())
        await manager.broadcast(json.dumps({
            "type": "log",
            "message": f"🤖 AI key added: {lbl} — {status.get('available_keys', 0)} provider(s) active | 💾 Saved",
        }))
    return result


@router.get("/ai/keys/stored")
async def get_stored_ai_keys():
    """List all AI keys stored in the database (masked for security)."""
    rows = await db.get_ai_keys()
    masked = []
    for r in rows:
        key = r.get("api_key", "")
        masked.append({
            "provider":    r.get("provider"),
            "label":       r.get("label"),
            "slot_index":  r.get("slot_index"),
            "key_preview": key[:8] + "..." + key[-4:] if len(key) > 12 else "***",
            "added_at":    str(r.get("added_at", "")),
        })
    return {"stored_keys": masked, "count": len(masked)}


@router.post("/ai/reset")
async def reset_ai_quota():
    """Clear all AI quota locks and reinitialize."""
    import glob as _glob
    for f in _glob.glob(os.path.join(os.path.dirname(__file__), ".gemini_quota_*")):
        try:
            os.remove(f)
        except Exception:
            pass
    from ai_agent import AIAgent
    AIAgent.reset_instance()
    fresh = AIAgent.get_instance()
    status = fresh.pool_status()
    available_count = status.get("available_keys", 0)
    await manager.broadcast(json.dumps({
        "type": "log",
        "message": f"🔄 AI quota reset — {available_count} key(s) now active",
    }))
    return {"success": True, "status": status}


@router.delete("/ai/key")
async def delete_ai_key(provider: str, label: str = ""):
    """Remove an AI key from the pool and database by provider (+ optional label)."""
    from ai_agent import AIAgent
    agent = AIAgent.get_instance()
    removed = 0
    new_slots = []
    for slot in list(agent._slots):
        match = slot.provider == provider.lower()
        if label:
            match = match and (slot.label.lower() == label.lower() or slot.display_label.lower() == label.lower())
        if match:
            removed += 1
        else:
            new_slots.append(slot)
    agent._slots = new_slots
    # Remove from DB
    try:
        await db.delete_ai_key(provider.lower(), label)
    except Exception as e:
        print(f"[AI] delete_ai_key DB error: {e}")
    status = agent.pool_status()
    return {"success": removed > 0, "removed": removed, "status": status}


@router.get("/ai/news")
async def get_news():
    """Fetch latest crypto + world news headlines."""
    from ai_agent import AIAgent
    headlines = AIAgent.get_instance().get_news()
    return {"headlines": headlines, "count": len(headlines)}


class AILearnRequest(BaseModel):
    topic: str = ""
    question: str = ""


# ── Market data helper for LEARN ──────────────────────────────────────────────

def _extract_symbol_from_topic(topic: str) -> str:
    """Detect the most relevant coin from a topic string (Arabic or English)."""
    t = topic.upper()
    COIN_KEYWORDS = [
        ("BTC",  ["BTC", "BITCOIN", "بيتكوين", "بتكوين"]),
        ("ETH",  ["ETH", "ETHEREUM", "ايثيريوم", "إيثيريوم", "ETHER"]),
        ("BNB",  ["BNB", "BINANCE COIN", "بي إن بي"]),
        ("SOL",  ["SOL", "SOLANA", "سولانا"]),
        ("XRP",  ["XRP", "RIPPLE", "ريبل"]),
        ("ADA",  ["ADA", "CARDANO", "كاردانو"]),
        ("MATIC",["MATIC", "POLYGON", "بوليجون"]),
        ("DOGE", ["DOGE", "DOGECOIN", "دوج"]),
        ("AVAX", ["AVAX", "AVALANCHE"]),
        ("DOT",  ["DOT", "POLKADOT"]),
    ]
    for coin, keywords in COIN_KEYWORDS:
        for kw in keywords:
            if kw in t:
                return f"{coin}/USDT"
    return "BTC/USDT"


async def _fetch_learn_market_data(symbol: str) -> dict:
    """Fetch OHLCV from MEXC public API, compute indicators, return chart + indicators."""
    try:
        import ccxt.async_support as ccxt_async
        from indicators import get_market_indicators

        exchange = ccxt_async.mexc()
        try:
            ohlcv = await exchange.fetch_ohlcv(symbol, "15m", limit=100)
        finally:
            await exchange.close()

        if not ohlcv or len(ohlcv) < 30:
            return {}

        indicators = get_market_indicators(ohlcv)
        chart_candles = ohlcv[-60:]

        return {
            "symbol": symbol,
            "timeframe": "15m",
            "indicators": indicators,
            "chart": [
                {"t": int(c[0]), "o": float(c[1]), "h": float(c[2]),
                 "l": float(c[3]), "c": float(c[4]), "v": float(c[5])}
                for c in chart_candles
            ],
        }
    except Exception as e:
        print(f"[learn] market data error for {symbol}: {e}")
        return {}


def _build_market_context_block(md: dict) -> str:
    """Format market data as a context block for the AI prompt."""
    if not md or "indicators" not in md:
        return ""
    ind = md["indicators"]
    sym = md.get("symbol", "BTC/USDT").replace("/USDT", "")
    price   = ind.get("current_price", 0)
    change  = ind.get("price_change_pct", 0)
    rsi     = ind.get("rsi", 50)
    macd    = ind.get("macd", 0)
    macd_s  = ind.get("macd_signal", 0)
    bb_pct  = ind.get("bb_pct", 0.5)
    cond    = ind.get("market_condition", "sideways")
    vol     = ind.get("volume", 0)
    vol_avg = ind.get("volume_avg", 1)
    vol_ratio = (vol / vol_avg) if vol_avg > 0 else 1.0

    rsi_label  = "ذروة شراء" if rsi > 70 else ("ذروة بيع" if rsi < 30 else "محايد")
    macd_label = "إيجابي (صاعد)" if macd > macd_s else "سلبي (هابط)"
    bb_label   = "قرب القمة" if bb_pct > 0.8 else ("قرب القاع" if bb_pct < 0.2 else "وسط النطاق")
    cond_map   = {"bullish": "صاعد", "bearish": "هابط", "overbought": "ذروة شراء",
                  "oversold": "ذروة بيع", "volatile": "متقلب", "sideways": "جانبي"}

    return f"""
📊 بيانات السوق الحية لـ {sym}/USDT (آخر 15 دقيقة):
━━━━━━━━━━━━━━━━━━━━━━━
• السعر الحالي: ${price:,.4f}  ({'+' if change >= 0 else ''}{change:.2f}%)
• حالة السوق: {cond_map.get(cond, cond)}
• RSI (14): {rsi:.1f} — {rsi_label}
• MACD: {macd_label} ({macd:.6f} vs signal {macd_s:.6f})
• Bollinger Band: {bb_label} ({bb_pct*100:.0f}% من النطاق)
• الحجم: {vol:,.0f} ({'+' if vol_ratio >= 1 else ''}{(vol_ratio-1)*100:.0f}% عن المتوسط)
━━━━━━━━━━━━━━━━━━━━━━━
"""


@router.post("/ai/learn")
async def ai_learn_endpoint(req: AILearnRequest):
    """Bot AI asks Gemini a question with real market data context, returns Q&A + chart."""
    from ai_agent import AIAgent

    agent    = AIAgent.get_instance()
    topic    = (req.topic or "تحليل السوق الحلال").strip()
    question = (req.question or topic).strip()

    symbol = _extract_symbol_from_topic(topic + " " + question)
    market_data = await _fetch_learn_market_data(symbol)
    market_block = _build_market_context_block(market_data)

    learn_prompt = f"""أنت روبوت تداول إسلامي ذكي تتعلم باستمرار لتحسين أدائك.
{market_block}
موضوع التعلم: {topic}
السؤال: {question}

{"استخدم البيانات الحية أعلاه في تحليلك ليكون الجواب دقيقاً وعملياً." if market_block else ""}

قدم تحليلاً شاملاً ومفيداً يتضمن:
1. شرح الموضوع بوضوح {"مع الإشارة إلى البيانات الحية" if market_block else ""}
2. كيفية تطبيقه في التداول الحلال (Spot Only — لا رافعة مالية)
3. مثال عملي {"مبني على السعر الحالي" if market_block else "واحد"}
4. درس أساسي واحد يمكن تذكره دائماً

الجواب باللغة العربية:"""

    trades = await db.get_trades(limit=10)
    status = await db.get_bot_status()

    try:
        result   = await agent.chat(learn_prompt, trades, status)
        answer   = result.get("response", "لم يُستلم رد")
        provider = result.get("provider", "rule-based")

        await db.save_lesson({
            "lesson": f"[GEMINI LESSON] {topic}: {answer[:600]}",
            "symbol": symbol,
            "market_condition": market_data.get("indicators", {}).get("market_condition", "learning"),
            "pattern": topic[:80],
            "outcome": "learn",
        })

        await db.save_message(
            role="user", content=question,
            screen="learn", session_id="ai_learn",
        )
        await db.save_message(
            role="assistant", content=answer,
            screen="learn", session_id="ai_learn",
            provider=provider,
        )

        return {
            "question":    question,
            "answer":      answer,
            "provider":    provider,
            "topic":       topic,
            "market_data": market_data if market_data else None,
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI learn error: {str(e)}")


@router.get("/ai/learn/chart/{symbol}")
async def ai_learn_chart(symbol: str):
    """Return OHLCV + indicators for a symbol (for chart rendering in the learn screen)."""
    clean = symbol.upper().replace("-", "/")
    if "/" not in clean:
        clean = f"{clean}/USDT"
    data = await _fetch_learn_market_data(clean)
    if not data:
        raise HTTPException(status_code=503, detail="Could not fetch market data")
    return data


# ── Push Notifications ────────────────────────────────────────────────────────

class PushTokenRequest(BaseModel):
    token: str


@router.post("/push/register")
async def push_register(req: PushTokenRequest):
    """Register an Expo push token for trade notifications."""
    from push_manager import PushManager
    pm = PushManager.get_instance()
    ok = pm.register(req.token)
    return {"success": ok, "devices": pm.token_count}


@router.delete("/push/unregister")
async def push_unregister(req: PushTokenRequest):
    """Remove an Expo push token."""
    from push_manager import PushManager
    pm = PushManager.get_instance()
    pm.unregister(req.token)
    return {"success": True, "devices": pm.token_count}


@router.get("/push/status")
async def push_status():
    """Count of registered push devices."""
    from push_manager import PushManager
    pm = PushManager.get_instance()
    return {"devices": pm.token_count}


@router.post("/push/test")
async def push_test():
    """Send a test push notification to all registered devices."""
    from push_manager import PushManager
    result = await PushManager.get_instance().send(
        "🤖 البوت الإسلامي الذكي",
        "الإشعارات تعمل بشكل مثالي! ستصلك تنبيهات الصفقات فوراً ✅",
        {"type": "test"},
    )
    return result


# ── Backward-compat aliases ───────────────────────────────────────────────────

@router.get("/gemini/keys")
async def get_gemini_keys():
    """Backward-compat alias → /ai/providers"""
    from ai_agent import AIAgent
    return AIAgent.get_instance().pool_status()


@router.post("/gemini/reset-quota")
async def reset_gemini_quota():
    """Backward-compat alias → /ai/reset"""
    import glob as _glob
    for f in _glob.glob(os.path.join(os.path.dirname(__file__), ".gemini_quota_*")):
        try:
            os.remove(f)
        except Exception:
            pass
    from ai_agent import AIAgent
    AIAgent.reset_instance()
    fresh = AIAgent.get_instance()
    status = fresh.pool_status()
    available_count = status.get("available_keys", 0)
    await manager.broadcast(json.dumps({
        "type": "log",
        "message": f"🔄 AI quota reset — {available_count} key(s) now active",
    }))
    return {"success": True, "status": status}


@router.post("/credentials")
async def save_credentials(request: CredentialsRequest):
    """Save exchange API credentials to environment and reinitialize the exchange client."""
    key        = request.api_key.strip()
    secret     = request.api_secret.strip()
    passphrase = request.api_passphrase.strip()
    exchange   = request.exchange_name.strip().lower() or "mexc"

    SUPPORTED = {"mexc", "kucoin", "binance", "bybit"}
    if exchange not in SUPPORTED:
        exchange = "mexc"

    if not key or not secret:
        raise HTTPException(status_code=400, detail="api_key and api_secret are required")
    if exchange == "kucoin" and not passphrase:
        raise HTTPException(status_code=400, detail="Passphrase required for KuCoin")

    # Build env vars map per exchange
    if exchange == "mexc":
        keys_to_set = {
            "MEXC_API_KEY":    key,
            "MEXC_API_SECRET": secret,
            "EXCHANGE_NAME":   "mexc",
        }
    elif exchange == "kucoin":
        keys_to_set = {
            "KUCOIN_API_KEY":        key,
            "KUCOIN_API_SECRET":     secret,
            "KUCOIN_API_PASSPHRASE": passphrase,
            "EXCHANGE_NAME":         "kucoin",
        }
    elif exchange == "bybit":
        keys_to_set = {
            "BYBIT_API_KEY":    key,
            "BYBIT_API_SECRET": secret,
            "EXCHANGE_NAME":    "bybit",
        }
    else:  # binance
        keys_to_set = {
            "BINANCE_API_KEY":    key,
            "BINANCE_API_SECRET": secret,
            "EXCHANGE_NAME":      "binance",
        }

    # Persist to env (runtime)
    for k, v in keys_to_set.items():
        os.environ[k] = v

    # Write to .env file so they survive hot-reloads and restarts
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    try:
        lines: list[str] = []
        if os.path.exists(env_path):
            with open(env_path) as f:
                lines = f.readlines()
        updated: set[str] = set()
        new_lines: list[str] = []
        for line in lines:
            stripped = line.strip()
            if "=" in stripped and not stripped.startswith("#"):
                k = stripped.split("=", 1)[0].strip()
                if k in keys_to_set:
                    new_lines.append(f'{k}={keys_to_set[k]}\n')
                    updated.add(k)
                    continue
            new_lines.append(line)
        for k, v in keys_to_set.items():
            if k not in updated:
                new_lines.append(f'{k}={v}\n')
        with open(env_path, "w") as f:
            f.writelines(new_lines)
    except Exception as e:
        print(f"[Credentials] Warning: could not write .env: {e}")

    # Reinitialize exchange client with new credentials
    ExchangeClient.reset_instance()
    new_client = ExchangeClient.get_instance()
    has_creds  = new_client._has_credentials

    await manager.broadcast(json.dumps({
        "type": "log",
        "message": (
            f"🔑 {exchange.upper()} credentials saved | "
            f"credentials={'✅ VALID' if has_creds else '❌ MISSING'} | "
            f"Switch to LIVE mode to start real trading"
        ),
    }))

    return {
        "success":         True,
        "has_credentials": has_creds,
        "exchange":        new_client.exchange_name,
        "message":         f"Credentials saved for {exchange.upper()}. Switch to LIVE mode to activate real trading.",
    }


@router.get("/credentials/status")
async def get_credentials_status():
    """Check if exchange credentials are configured."""
    client   = ExchangeClient.get_instance()
    exchange = client.exchange_name

    if exchange == "mexc":
        key    = os.environ.get("MEXC_API_KEY", "")
        secret = os.environ.get("MEXC_API_SECRET", "")
        passphrase = ""
    elif exchange == "kucoin":
        key        = os.environ.get("KUCOIN_API_KEY", "")
        secret     = os.environ.get("KUCOIN_API_SECRET", "")
        passphrase = os.environ.get("KUCOIN_API_PASSPHRASE", "")
    elif exchange == "bybit":
        key    = os.environ.get("BYBIT_API_KEY", "")
        secret = os.environ.get("BYBIT_API_SECRET", "")
        passphrase = ""
    else:  # binance
        key    = os.environ.get("BINANCE_API_KEY", "")
        secret = os.environ.get("BINANCE_API_SECRET", "")
        passphrase = ""

    needs_passphrase = exchange == "kucoin"
    has_all = bool(key and secret and (passphrase if needs_passphrase else True))

    return {
        "has_api_key":         bool(key),
        "has_api_secret":      bool(secret),
        "has_passphrase":      bool(passphrase),
        "has_all_credentials": has_all,
        "has_credentials":     client._has_credentials,
        "exchange":            exchange,
        "mode":                client.mode,
        "api_key_preview":     (key[:4] + "****" + key[-4:]) if len(key) >= 8 else ("****" if key else ""),
    }


@router.post("/credentials/test")
async def test_credentials():
    """Test saved KuCoin credentials by fetching real account balance (works in demo mode too)."""
    import ccxt.async_support as ccxt_async
    client   = ExchangeClient.get_instance()
    exchange = client.exchange_name

    if exchange == "mexc":
        key    = os.environ.get("MEXC_API_KEY", "")
        secret = os.environ.get("MEXC_API_SECRET", "")
        if not key or not secret:
            raise HTTPException(status_code=400, detail="لا توجد بيانات MEXC — أضف الـ API Key والـ Secret أولاً")
        test_exchange = ccxt_async.mexc({
            "apiKey": key, "secret": secret,
            "options": {"defaultType": "spot"},
        })
    elif exchange == "kucoin":
        key        = os.environ.get("KUCOIN_API_KEY", "")
        secret     = os.environ.get("KUCOIN_API_SECRET", "")
        passphrase = os.environ.get("KUCOIN_API_PASSPHRASE", "")
        if not key or not secret or not passphrase:
            raise HTTPException(status_code=400, detail="لا توجد بيانات KuCoin — أضف الـ Key والـ Secret والـ Passphrase أولاً")
        test_exchange = ccxt_async.kucoin({
            "apiKey": key, "secret": secret, "password": passphrase,
            "options": {"defaultType": "spot"},
        })
    elif exchange == "bybit":
        key    = os.environ.get("BYBIT_API_KEY", "")
        secret = os.environ.get("BYBIT_API_SECRET", "")
        if not key or not secret:
            raise HTTPException(status_code=400, detail="لا توجد بيانات Bybit — أضف الـ API Key والـ Secret أولاً")
        test_exchange = ccxt_async.bybit({
            "apiKey": key, "secret": secret,
            "options": {"defaultType": "spot"},
        })
    else:  # binance
        key    = os.environ.get("BINANCE_API_KEY", "")
        secret = os.environ.get("BINANCE_API_SECRET", "")
        if not key or not secret:
            raise HTTPException(status_code=400, detail="لا توجد بيانات Binance — أضف الـ API Key والـ Secret أولاً")
        test_exchange = ccxt_async.binance({
            "apiKey": key, "secret": secret,
            "options": {"defaultType": "spot"},
        })

    try:
        balance = await test_exchange.fetch_balance()
        usdt    = balance.get("USDT", {})
        total   = float(usdt.get("total", 0))
        free    = float(usdt.get("free", 0))
        return {
            "success":    True,
            "usdt_total": total,
            "usdt_free":  free,
            "exchange":   exchange,
            "message":    f"✅ متصل بـ {exchange.upper()} بنجاح! رصيد USDT: ${total:.2f} (${free:.2f} متاح)",
        }
    except Exception as e:
        err = str(e)
        print(f"[{exchange.upper()} Test] FULL ERROR: {err}")
        if "400003" in err or "not exist" in err.lower():
            friendly = f"❌ API Key غير موجود أو محذوف من {exchange.upper()}"
        elif "400004" in err or "passphrase" in err.lower() or "password" in err.lower():
            friendly = "❌ Passphrase غير صحيح"
        elif "400302" in err or "unavailable in the u.s" in err.lower() or "restricted" in err.lower():
            friendly = f"❌ {exchange.upper()} محجوب من سيرفرات Replit (US) — استخدم MEXC بدلاً"
        elif "ip" in err.lower() or "403" in err:
            friendly = f"❌ IP غير مسموح — أضف IP السيرفر في إعدادات الـ API"
        elif "invalid" in err.lower() or "401" in err:
            friendly = f"❌ بيانات غير صحيحة — تحقق من الـ Key والـ Secret"
        elif "permission" in err.lower():
            friendly = "❌ صلاحيات غير كافية — فعّل Spot Trading في إعدادات الـ API"
        else:
            friendly = f"❌ خطأ: {err[:200]}"
        raise HTTPException(status_code=400, detail=friendly)
    finally:
        await test_exchange.close()


@router.post("/mode")
async def set_mode(request: ModeRequest):
    if request.mode not in ("demo", "live"):
        raise HTTPException(status_code=400, detail="Mode must be 'demo' or 'live'")

    if scheduler_instance.is_running():
        scheduler_instance.stop()

    # Update env and reset singleton so next start picks up new mode
    os.environ["EXCHANGE_MODE"] = request.mode
    ExchangeClient.reset_instance()
    new_client = ExchangeClient.get_instance()  # re-init with new mode

    await db.update_bot_status(mode=request.mode, is_running=False)
    await manager.broadcast(json.dumps({
        "type": "log",
        "message": (
            f"{'⚠️ LIVE MODE — real funds at risk' if request.mode == 'live' else '✅ DEMO mode — paper trading'} | "
            f"exchange: {new_client.exchange_name} | restart autopilot to begin"
        ),
    }))
    return {"success": True, "mode": request.mode, "exchange": new_client.exchange_name}


@router.post("/settings")
async def update_settings(request: SettingsRequest):
    global _target_win_rate, _current_threshold
    if request.max_risk_percent is not None:
        os.environ["MAX_RISK_PERCENT"] = str(request.max_risk_percent)
    if request.min_confidence_score is not None:
        _current_threshold = request.min_confidence_score
        os.environ["MIN_CONFIDENCE_SCORE"] = str(request.min_confidence_score)
    if request.target_win_rate is not None:
        _target_win_rate = request.target_win_rate
        os.environ["TARGET_WIN_RATE"] = str(request.target_win_rate)
    await manager.broadcast(json.dumps({
        "type": "log",
        "message": (
            f"⚙️ Settings updated — target: {_target_win_rate:.0f}% | "
            f"AI confidence: {_current_threshold}%"
        ),
    }))
    return {
        "success": True,
        "target_win_rate": _target_win_rate,
        "confidence_threshold": _current_threshold,
    }


@router.get("/ml/status")
async def get_ml_status():
    from ml_model import TradingMLModel
    ml = TradingMLModel.get_instance()
    return ml.status_dict()


@router.post("/scan/trigger")
async def trigger_scan():
    """Force an immediate market scan (for testing/debugging)."""
    if not scheduler_instance.is_running():
        raise HTTPException(status_code=400, detail="Bot is not running — start autopilot first")
    import asyncio
    asyncio.create_task(scheduler_instance._scan_markets())
    return {"success": True, "message": "Scan triggered — watch WebSocket for results"}


@router.post("/trades/close-all")
async def close_all_trades():
    """Emergency: close all open trades at current price (break-even / cleanup)."""
    from bybit_client import ExchangeClient
    from risk_manager import RiskManager
    client = ExchangeClient.get_instance()
    rm = RiskManager()
    trades = await db.get_trades(limit=500)
    open_trades = [t for t in trades if t.get("status") == "open"]
    closed = 0
    for trade in open_trades:
        try:
            symbol = trade.get("symbol", "")
            side   = trade.get("side", "buy")
            entry  = float(trade.get("entry_price") or 0)
            qty    = float(trade.get("quantity") or 0)
            current_price = await client.get_current_price(symbol)
            if current_price <= 0:
                current_price = entry   # close at entry if price unavailable
            pnl = rm.estimate_pnl(side, entry, current_price, qty)
            await db.update_trade(trade["id"], {
                "status": "closed",
                "exit_price": current_price,
                "pnl": pnl,
                "closed_at": __import__("datetime").datetime.utcnow().isoformat(),
            })
            closed += 1
        except Exception:
            pass
    await db.recalculate_stats()
    await manager.broadcast(__import__("json").dumps({
        "type": "log",
        "message": f"🧹 Emergency close: {closed} trade(s) closed at market price",
    }))
    return {"success": True, "closed": closed}


@router.post("/ml/train")
async def force_train_ml():
    """Manually trigger ML retraining on all closed trades."""
    from ml_model import TradingMLModel
    ml = TradingMLModel.get_instance()
    closed = await db.get_closed_trades_for_ml()
    success = ml.train(closed)
    return {
        "success": success,
        "n_samples": ml.n_samples,
        "is_trained": ml.is_trained,
        "feature_importances": ml.feature_importances[:5],
        "message": (
            f"Trained on {ml.n_samples} samples ✅"
            if success
            else f"Not enough data yet ({len(closed)}/{10} samples needed)"
        ),
    }


@router.get("/agent/status")
async def get_agent_status():
    """Full agent brain status — strategy, memory, patterns, thoughts."""
    from agent_core import TradingAgent
    try:
        agent = TradingAgent.get_instance(db=db)
        return agent.status_dict()
    except Exception as e:
        return {"error": str(e), "message": "Agent not initialized yet — start autopilot first"}


@router.post("/agent/reflect")
async def trigger_agent_reflection():
    """Force an immediate deep reflection cycle."""
    from agent_core import TradingAgent
    agent = TradingAgent.get_instance(db=db)
    agent.set_broadcast_fn(manager.broadcast)
    perception = await agent.perceive()
    result = await agent.deep_reflect(perception)
    return {"success": True, "reflection": result or "No reflection produced (need more trades)"}


@router.get("/agent/memory")
async def get_agent_memory_legacy():
    """Full agent brain state: lessons, patterns, strategy, AI health, streaks."""
    from agent_core import TradingAgent
    from ai_agent import AIAgent
    try:
        agent = TradingAgent.get_instance(db=db)
        mem     = agent.memory
        lessons = await mem.get_long_term_lessons(limit=25)
        ai_status = AIAgent.get_instance().pool_status()
        return {
            "strategy": {
                "current":    mem._current_strategy,
                "confidence": round(mem._strategy_confidence, 2),
                "goal":       mem._goal,
                "overrides":  mem._strategy_overrides,
            },
            "streaks": {
                "consecutive_wins":   mem._consecutive_wins,
                "consecutive_losses": mem._consecutive_losses,
                "last_results":       mem._last_3_results,
                "emergency_halted":   mem._emergency_halted,
            },
            "patterns":           mem.get_best_patterns(10),
            "pattern_scores_raw": mem._pattern_scores,
            "recent_thoughts":    mem._session_thoughts[-25:],
            "recent_plans":       mem._session_plans[-10:],
            "lessons":            lessons,
            "ai_status":          ai_status,
            "settings": {
                "target_win_rate":         _target_win_rate,
                "current_threshold":       _current_threshold,
                "reflection_interval_min": round(mem._reflection_interval / 60, 1),
            },
        }
    except Exception as e:
        return {"error": str(e)}


@router.get("/agent/memory/full")
async def get_full_memory():
    """Full bot memory: lessons + knowledge + stats — for the Brain screen."""
    from memory_engine import MemoryEngine
    engine = MemoryEngine(db)
    return await engine.get_memory_summary()


@router.get("/agent/memory/search")
async def search_agent_memory(q: str = "", category: str = ""):
    """Search across lessons and knowledge."""
    from memory_engine import MemoryEngine
    engine = MemoryEngine(db)
    if q:
        lessons   = await db.search_memory(q, limit=30)
        knowledge = await db.search_knowledge(q, limit=20)
    else:
        lessons   = await db.get_recent_lessons(limit=50)
        knowledge = await db.get_knowledge(limit=30)
    return {"lessons": lessons, "knowledge": knowledge}


@router.delete("/agent/memory/{memory_id}")
async def delete_agent_memory(memory_id: str):
    """Delete a specific lesson from memory."""
    ok = await db.delete_memory(memory_id)
    return {"success": ok}


class KnowledgeRequest(BaseModel):
    title:     str
    content:   str
    category:  str = "general"
    importance: float = 5.0
    tags:      str = ""
    source:    str = "user"


@router.post("/agent/knowledge")
async def add_knowledge(req: KnowledgeRequest):
    """Manually add a piece of knowledge to the bot's long-term memory."""
    ok = await db.save_knowledge({
        "title":     req.title,
        "content":   req.content,
        "category":  req.category,
        "importance": req.importance,
        "tags":      req.tags,
        "source":    req.source,
    })
    return {"success": ok}


@router.delete("/agent/knowledge/{kid}")
async def delete_knowledge(kid: str):
    """Delete a knowledge entry."""
    ok = await db.delete_knowledge(kid)
    return {"success": ok}


@router.post("/agent/strategic-review")
async def trigger_strategic_review():
    """Force an immediate strategic review of recent performance."""
    from learning_loop import LearningLoop
    ll = LearningLoop(db)
    review = await ll.strategic_review(broadcast_fn=manager.broadcast)
    return {"success": True, "review": review or "Not enough trades for review (need 5+)"}


@router.post("/agent/reset-emergency")
async def reset_emergency_halt():
    """Reset emergency halt — allows the bot to resume buying after consecutive losses."""
    from agent_core import TradingAgent
    agent = TradingAgent.get_instance(db=db)
    agent.memory.reset_emergency()
    await manager.broadcast(json.dumps({
        "type": "agent",
        "message": "✅ Emergency halt cleared — agent resumed. Increased caution mode active.",
    }))
    return {"success": True, "message": "Emergency halt cleared. Bot will resume on next scan."}


@router.get("/agent/smart-triggers")
async def get_smart_triggers():
    """Get the smart trigger system status and recent events."""
    from agent_core import TradingAgent
    try:
        agent = TradingAgent.get_instance(db=db)
        return {
            "consecutive_losses":  agent.memory._consecutive_losses,
            "consecutive_wins":    agent.memory._consecutive_wins,
            "emergency_halted":    agent.memory._emergency_halted,
            "trades_since_review": agent._trades_since_deep_review,
            "last_3_results":      agent.memory._last_3_results,
            "triggers": {
                "drawdown_alert_at":    3,
                "emergency_halt_at":    5,
                "win_streak_review_at": 5,
                "deep_review_at":       10,
                "time_rhythm_mins":     30,
            },
            "strategy_overrides": agent.memory._strategy_overrides,
        }
    except Exception as e:
        return {"error": str(e)}


class AgentCommandRequest(BaseModel):
    command: str
    value: Optional[str] = None
    threshold: Optional[int] = None


@router.post("/agent/command")
async def agent_command(request: AgentCommandRequest):
    """Control the agent: strategy, halt/resume, thresholds, goal, patterns."""
    from agent_core import TradingAgent
    global _current_threshold, _target_win_rate
    try:
        agent = TradingAgent.get_instance(db=db)
        mem   = agent.memory
        cmd   = request.command.lower()

        if cmd == "set_strategy":
            STRATEGIES = ["mean_reversion", "trend_following", "momentum_breakout", "scalping", "conservative"]
            if request.value not in STRATEGIES:
                return {"success": False, "error": f"Unknown strategy. Options: {', '.join(STRATEGIES)}"}
            old = mem._current_strategy
            mem.set_strategy(request.value, confidence=1.0)
            await manager.broadcast(json.dumps({
                "type": "log",
                "message": f"🔄 Strategy changed by user: {old} → {request.value}",
            }))
            return {"success": True, "message": f"Strategy: {old} → {request.value}"}

        elif cmd == "halt":
            mem._emergency_halted = True
            mem._save_state()
            if scheduler_instance.is_running():
                scheduler_instance.stop()
                await db.update_bot_status(is_running=False)
            await manager.broadcast(json.dumps({
                "type": "log", "message": "🛑 Agent halted by user",
            }))
            return {"success": True, "message": "Agent halted"}

        elif cmd == "resume":
            mem.reset_emergency()
            await manager.broadcast(json.dumps({
                "type": "log", "message": "✅ Emergency reset — agent ready",
            }))
            return {"success": True, "message": "Emergency reset complete"}

        elif cmd == "set_goal":
            if not request.value:
                return {"success": False, "error": "value required"}
            mem._goal = request.value
            mem._save_state()
            return {"success": True, "message": f"Goal: {request.value}"}

        elif cmd == "set_threshold":
            val = max(40, min(95, int(request.threshold or 55)))
            _current_threshold = val
            os.environ["MIN_CONFIDENCE_SCORE"] = str(val)
            scheduler_instance.set_adaptive(adaptive, lambda: _target_win_rate, lambda: _current_threshold)
            await manager.broadcast(json.dumps({
                "type": "log",
                "message": f"🎯 Confidence threshold → {val}%",
            }))
            return {"success": True, "threshold": val}

        elif cmd == "set_win_rate":
            val = float(max(50, min(90, int(request.threshold or 65))))
            _target_win_rate = val
            os.environ["TARGET_WIN_RATE"] = str(val)
            scheduler_instance.set_adaptive(adaptive, lambda: _target_win_rate, lambda: _current_threshold)
            await manager.broadcast(json.dumps({
                "type": "log",
                "message": f"🎯 Target win rate → {val:.0f}%",
            }))
            return {"success": True, "target_win_rate": val}

        elif cmd == "reset_patterns":
            mem._pattern_scores = {}
            mem._save_state()
            return {"success": True, "message": "Pattern scores reset"}

        elif cmd == "add_thought":
            if not request.value:
                return {"success": False, "error": "value required"}
            mem.add_thought(f"[USER] {request.value}")
            return {"success": True, "message": "Thought injected"}

        else:
            return {
                "success": False,
                "error":   f"Unknown command: {cmd}",
                "commands": ["set_strategy", "halt", "resume", "set_goal",
                             "set_threshold", "set_win_rate", "reset_patterns", "add_thought"],
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# Multi-Exchange Router endpoints
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/exchange/status")
async def exchange_status():
    """Return full multi-exchange status: scores, latency, configured flags, strategy."""
    try:
        rtr = ExchangeRouter.get_instance()
        return rtr.status_all()
    except Exception as e:
        return {"error": str(e)}


class ExchangeCredentialsRequest(BaseModel):
    exchange: str
    api_key: str
    api_secret: str
    passphrase: str = ""


@router.post("/exchange/credentials")
async def save_exchange_credentials(req: ExchangeCredentialsRequest):
    """Save credentials for a single exchange without touching other exchanges."""
    name = req.exchange.lower().strip()
    if name not in EXCHANGE_CONFIGS:
        raise HTTPException(status_code=400, detail=f"Unknown exchange: {name}. Allowed: mexc, binance, bybit, kucoin")
    if not req.api_key or not req.api_secret:
        raise HTTPException(status_code=400, detail="api_key and api_secret are required")
    cfg = EXCHANGE_CONFIGS[name]
    if cfg["needs_pass"] and not req.passphrase:
        raise HTTPException(status_code=400, detail=f"{name.upper()} requires a passphrase")
    try:
        rtr = ExchangeRouter.get_instance()
        rtr.save_credentials(name, req.api_key, req.api_secret, req.passphrase)
        return {"success": True, "exchange": name, "message": f"✅ {name.upper()} credentials saved"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ExchangeStrategyRequest(BaseModel):
    strategy: str  # "auto" | "manual"
    active_exchange: str = ""


@router.post("/exchange/strategy")
async def set_exchange_strategy(req: ExchangeStrategyRequest):
    """Set routing strategy: auto (best score) or manual (fixed exchange)."""
    rtr = ExchangeRouter.get_instance()
    if not rtr.set_strategy(req.strategy):
        raise HTTPException(status_code=400, detail="strategy must be 'auto' or 'manual'")
    msg = f"Strategy set to: {req.strategy}"
    if req.active_exchange:
        name = req.active_exchange.lower()
        if rtr.set_active(name):
            # Reset ExchangeClient so next call picks the new exchange
            await ExchangeClient.get_instance().close()
            ExchangeClient.reset_instance()
            msg += f" | active exchange → {name.upper()}"
    return {"success": True, "message": msg, "strategy": req.strategy}


@router.post("/exchange/switch/{name}")
async def switch_exchange(name: str):
    """Manually switch to a specific exchange (sets strategy to manual)."""
    name = name.lower()
    rtr = ExchangeRouter.get_instance()
    if not rtr.set_active(name):
        raise HTTPException(status_code=400, detail=f"Unknown exchange: {name}")
    rtr.set_strategy("manual")
    await ExchangeClient.get_instance().close()
    ExchangeClient.reset_instance()
    new_client = ExchangeClient.get_instance()
    return {
        "success":  True,
        "exchange": name,
        "message":  f"✅ Switched to {name.upper()} (manual mode) | mode: {new_client.mode}",
    }


@router.post("/exchange/test/{name}")
async def test_exchange_connection(name: str):
    """Test connectivity + credentials for a specific exchange."""
    rtr = ExchangeRouter.get_instance()
    result = await rtr.test_exchange(name.lower())
    return result


# ═══════════════════════════════════════════════════════════════════════════
# DEX / بلوكشين endpoints
# ═══════════════════════════════════════════════════════════════════════════

class DexConfigRequest(BaseModel):
    network:     str            # base | polygon | bsc
    private_key: str = ""       # DEX_PRIVATE_KEY — يُحفظ في .env
    rpc_url:     str = ""       # اختياري: Alchemy / Infura

class HybridModeRequest(BaseModel):
    mode:             str        # auto | dex_only | cex_only
    cex_advantage_pct: float = 0.3


@router.get("/dex/status")
async def dex_status():
    """حالة DEX: اتصال البلوكشين، المحفظة، الشبكة، الرصيد."""
    try:
        from dex_client import DexClient, NETWORKS
        dex = DexClient.get_instance()
        base_status = dex.status()
        wallet_info = await dex.get_wallet_info()
        return {
            **base_status,
            "wallet": wallet_info,
            "available_networks": {k: {"name": v["name"], "chain_id": v["chain_id"]} for k, v in NETWORKS.items()},
        }
    except ImportError:
        return {"web3_available": False, "error": "web3 غير مثبّت — شغّل: pip install web3"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/dex/configure")
async def configure_dex(req: DexConfigRequest):
    """حفظ إعدادات DEX (الشبكة + مفتاح المحفظة الخاصة)."""
    try:
        from dex_client import DexClient, NETWORKS
        if req.network.lower() not in NETWORKS:
            raise HTTPException(status_code=400, detail=f"شبكة غير مدعومة. المتاح: {list(NETWORKS.keys())}")
        DexClient.reset_instance()
        dex = DexClient.get_instance()
        result = dex.save_config(
            network=req.network,
            private_key=req.private_key,
            rpc_url=req.rpc_url,
        )
        return result
    except ImportError:
        raise HTTPException(status_code=503, detail="web3 غير مثبّت")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dex/quote/{symbol}")
async def dex_quote(symbol: str, amount: float = 100.0):
    """
    يحصل على سعر DEX للرمز المطلوب.
    symbol مثال: ETH-USDT أو ETH%2FUSDT
    """
    symbol = symbol.replace("-", "/").upper()
    try:
        from dex_client import DexClient
        dex = DexClient.get_instance()
        quote = await dex.get_dex_price(symbol, amount_usdt=amount)
        return quote
    except ImportError:
        return {"success": False, "error": "web3 غير مثبّت"}
    except Exception as e:
        return {"success": False, "error": str(e)}


@router.get("/dex/compare/{symbol}")
async def dex_compare_routes(symbol: str, amount: float = 100.0):
    """
    يقارن سعر DEX مع سعر CEX ويشرح أي المسارين أفضل.
    """
    symbol = symbol.replace("-", "/").upper()
    try:
        from dex_client import DexClient
        from hybrid_router import HybridRouter

        # سعر CEX الحالي
        client = ExchangeClient.get_instance()
        cex_ticker = await client.get_ticker(symbol)
        cex_price  = float(cex_ticker.get("last", 0) or cex_ticker.get("close", 0))

        dex = DexClient.get_instance()
        dex_quote = await dex.get_dex_price(symbol, amount_usdt=amount)

        hybrid = HybridRouter.get_instance()
        decision = await hybrid.decide_route(
            symbol=symbol, side="buy", amount_usdt=amount,
            cex_price=cex_price, native_price=cex_price,
        )
        return {
            "symbol":     symbol,
            "amount_usdt": amount,
            "cex_price":  cex_price,
            "dex_quote":  dex_quote,
            "decision":   decision,
            "hybrid_stats": hybrid.stats(),
        }
    except ImportError:
        return {"error": "web3 غير مثبّت"}
    except Exception as e:
        return {"error": str(e)}


@router.post("/dex/mode")
async def set_hybrid_mode(req: HybridModeRequest):
    """
    يُغيّر وضع التوجيه:
      auto     — يختار DEX أو CEX تلقائياً حسب السعر
      dex_only — DEX دائماً (البلوكشين المباشر)
      cex_only — CEX دائماً (MEXC / غيره)
    """
    try:
        from hybrid_router import HybridRouter
        hybrid = HybridRouter.get_instance()
        ok = hybrid.set_mode(req.mode)
        if not ok:
            raise HTTPException(status_code=400, detail="mode يجب أن يكون: auto | dex_only | cex_only")
        hybrid.cex_advantage_pct = req.cex_advantage_pct
        os.environ["CEX_ADVANTAGE"] = str(req.cex_advantage_pct)
        return {"success": True, "mode": req.mode, "cex_advantage_pct": req.cex_advantage_pct}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/dex/hybrid-stats")
async def hybrid_stats():
    """إحصائيات التوجيه — كم صفقة على DEX وكم على CEX وما الوفورات."""
    try:
        from hybrid_router import HybridRouter
        return HybridRouter.get_instance().stats()
    except Exception as e:
        return {"error": str(e)}


# ═══════════════════════════════════════════════════════════════════════════════
# ── SENTIMENT (Fear & Greed + Whale Activity) ────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/sentiment")
async def get_sentiment():
    """
    يجلب مؤشر الخوف والجشع + نشاط الحيتان في السوق.
    Fear & Greed Index من alternative.me + تحليل الحجم من CoinGecko.
    """
    try:
        from sentiment import get_full_sentiment
        return await get_full_sentiment()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ═══════════════════════════════════════════════════════════════════════════════
# ── BACKTESTING ───────────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

class BacktestRequest(BaseModel):
    symbol: str = "BTC/USDT"
    days: int = 30
    initial_capital: float = 10000.0
    interval: str = "15m"


class MultiBacktestRequest(BaseModel):
    symbols: list[str] = ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
    days: int = 30
    initial_capital: float = 10000.0


@router.post("/backtest")
async def run_backtest(req: BacktestRequest):
    """
    يشغّل اختبار الاستراتيجية على بيانات تاريخية لعملة واحدة.
    يستخدم نفس منطق RSI + Bollinger Bands المستخدم في البوت الحقيقي.
    """
    from backtester import run_backtest as _bt
    symbol = req.symbol.replace("-", "/").upper()
    days   = max(7, min(req.days, 180))
    return await _bt(
        symbol=symbol,
        days=days,
        initial_capital=req.initial_capital,
        interval=req.interval,
    )


@router.post("/backtest/multi")
async def run_multi_backtest(req: MultiBacktestRequest):
    """
    يشغّل الاختبار على عدة عملات بالتوازي ويعيد مقارنة بينها.
    """
    from backtester import run_multi_backtest as _mbt
    symbols = [s.replace("-", "/").upper() for s in req.symbols[:8]]
    days    = max(7, min(req.days, 90))
    return await _mbt(symbols=symbols, days=days, initial_capital=req.initial_capital)


# ═══════════════════════════════════════════════════════════════════════════════
# ── MULTI-ASSET PORTFOLIO ────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

class PortfolioAssetsRequest(BaseModel):
    assets: list[dict]   # [{symbol, allocation_pct, enabled}]


class ToggleAssetRequest(BaseModel):
    symbol: str
    enabled: bool


@router.get("/portfolio/assets")
async def get_portfolio_assets():
    """
    يعيد قائمة العملات المضافة للمحفظة مع نسبة التخصيص لكل منها.
    """
    assets = await db.get_portfolio_assets()
    total  = sum(a.get("allocation_pct", 0) for a in assets if a.get("enabled"))
    return {
        "assets":           assets,
        "total_allocation": round(total, 1),
        "is_valid":         80 <= total <= 100 or len(assets) == 0,
    }


@router.post("/portfolio/assets")
async def set_portfolio_assets(req: PortfolioAssetsRequest):
    """
    يحفظ قائمة العملات ونسب التخصيص.
    مثال: [{symbol: "BTC/USDT", allocation_pct: 40, enabled: true}, ...]
    """
    if not req.assets:
        raise HTTPException(status_code=400, detail="يجب تحديد عملة واحدة على الأقل")

    total = sum(float(a.get("allocation_pct", 0)) for a in req.assets if a.get("enabled", True))
    if total > 100:
        raise HTTPException(status_code=400, detail=f"مجموع النسب {total:.1f}% يتجاوز 100%")

    await db.set_portfolio_assets(req.assets)

    # Sync TRADING_SYMBOLS env to active symbols
    enabled = [a["symbol"].replace("-", "/").upper() for a in req.assets if a.get("enabled", True)]
    if enabled:
        os.environ["TRADING_SYMBOLS"] = ",".join(enabled)

    return {
        "success":          True,
        "assets_saved":     len(req.assets),
        "total_allocation": round(total, 1),
        "trading_symbols":  enabled,
    }


@router.post("/portfolio/assets/toggle")
async def toggle_portfolio_asset(req: ToggleAssetRequest):
    """يفعّل أو يعطّل عملة في المحفظة بدون حذفها."""
    await db.toggle_portfolio_asset(req.symbol, req.enabled)
    # Reload TRADING_SYMBOLS
    assets  = await db.get_portfolio_assets()
    enabled = [a["symbol"] for a in assets if a.get("enabled")]
    if enabled:
        os.environ["TRADING_SYMBOLS"] = ",".join(enabled)
    return {"success": True, "symbol": req.symbol, "enabled": req.enabled}


# ═══════════════════════════════════════════════════════════════════════════════
# ── ZAKAT CALCULATOR ─────────────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/zakat")
async def get_zakat():
    """
    يحسب الزكاة الواجبة على أرباح التداول.
    النصاب: ما يعادل 85 جرام ذهب ≈ $5,000 USD (تقريباً)
    الزكاة: 2.5% من صافي الربح إذا بلغ النصاب
    """
    from datetime import datetime, timezone

    data   = await db.get_zakat_data()
    monthly = await db.get_monthly_profits()

    NISAB_USD   = 5000.0   # تقريبي — 85g ذهب
    ZAKAT_RATE  = 0.025    # 2.5%

    total_profit = float(data.get("total_profit", 0))
    total_loss   = float(data.get("total_loss", 0))
    net_pnl      = float(data.get("net_pnl", 0))

    above_nisab  = net_pnl >= NISAB_USD
    zakat_due    = round(net_pnl * ZAKAT_RATE, 2) if above_nisab else 0.0
    remaining_after_zakat = round(net_pnl - zakat_due, 2)

    # حالة: جاهز للدفع / لم يبلغ النصاب / لا يوجد ربح
    if net_pnl <= 0:
        status = "no_profit"
        status_ar = "لا يوجد ربح صافٍ — لا زكاة واجبة"
    elif not above_nisab:
        status = "below_nisab"
        status_ar = f"الربح ${net_pnl:.2f} أقل من النصاب ${NISAB_USD:,.0f} — لا زكاة واجبة"
    else:
        status = "zakat_due"
        status_ar = f"الزكاة الواجبة: ${zakat_due:.2f} USDT (2.5% من ${net_pnl:.2f})"

    return {
        "zakat_calculation": {
            "total_profit_usd":       round(total_profit, 2),
            "total_loss_usd":         round(total_loss, 2),
            "net_pnl_usd":            round(net_pnl, 2),
            "nisab_usd":              NISAB_USD,
            "above_nisab":            above_nisab,
            "zakat_rate_pct":         ZAKAT_RATE * 100,
            "zakat_due_usd":          zakat_due,
            "remaining_after_zakat":  remaining_after_zakat,
        },
        "status":                 status,
        "status_ar":              status_ar,
        "total_trades":           int(data.get("total_trades", 0)),
        "total_wins":             int(data.get("total_wins", 0)),
        "monthly_profits":        monthly,
        "notes": [
            "الزكاة تُحسب على صافي الربح إذا بلغ النصاب",
            "النصاب: ما يعادل 85 جراماً من الذهب (≈ $5,000)",
            "المعدل: 2.5% من صافي الأرباح",
            "يُستحسن مراجعة عالم شرعي لتحديد التفاصيل الدقيقة",
        ],
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ── MULTI-ACCOUNT MANAGEMENT ──────────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

class AddAccountRequest(BaseModel):
    name:           str
    exchange_name:  str = "mexc"
    api_key:        str = ""
    api_secret:     str = ""
    api_passphrase: str = ""
    mode:           str = "demo"
    balance:        float = 10000.0

class ToggleAccountRequest(BaseModel):
    is_active: bool


@router.get("/accounts")
async def list_accounts():
    """List all configured exchange accounts (secrets hidden)."""
    accounts = await db.get_exchange_accounts()
    # Sync balances for all active accounts
    from multi_account import MultiAccountManager
    mgr = MultiAccountManager.get_instance()
    await mgr.load_accounts(db)
    balances_raw = await mgr.get_all_balances()
    bal_map = {b.get("account_id", ""): b.get("total", 0.0) for b in balances_raw}
    for acc in accounts:
        if acc.get("is_active") and acc.get("id") in bal_map:
            acc["live_balance"] = bal_map[acc["id"]]
    return {"accounts": accounts, "count": len(accounts)}


@router.post("/accounts")
async def add_account(req: AddAccountRequest):
    """Add a new secondary exchange account."""
    data = {
        "name":           req.name.strip() or "Account",
        "exchange_name":  req.exchange_name.lower().strip(),
        "api_key":        req.api_key.strip(),
        "api_secret":     req.api_secret.strip(),
        "api_passphrase": req.api_passphrase.strip(),
        "mode":           req.mode.lower().strip(),
        "balance":        req.balance,
        "is_active":      True,
    }
    acc = await db.add_exchange_account(data)
    # Reload MultiAccountManager
    from multi_account import MultiAccountManager
    await MultiAccountManager.get_instance().load_accounts(db)
    await manager.broadcast(json.dumps({
        "type": "log",
        "message": f"➕ حساب جديد مضاف: {data['name']} ({data['exchange_name'].upper()}) [{data['mode'].upper()}]",
    }))
    return {"success": True, "account": {"id": acc["id"], "name": data["name"]}}


@router.delete("/accounts/{account_id}")
async def delete_account(account_id: str):
    """Delete a secondary exchange account."""
    ok = await db.delete_exchange_account(account_id)
    from multi_account import MultiAccountManager
    await MultiAccountManager.get_instance().load_accounts(db)
    return {"success": ok}


@router.put("/accounts/{account_id}/toggle")
async def toggle_account(account_id: str, req: ToggleAccountRequest):
    """Enable or disable a secondary account."""
    ok = await db.toggle_exchange_account(account_id, req.is_active)
    from multi_account import MultiAccountManager
    await MultiAccountManager.get_instance().load_accounts(db)
    state = "مفعّل" if req.is_active else "موقف"
    await manager.broadcast(json.dumps({
        "type": "log",
        "message": f"🔄 حساب {account_id[:8]}… {state}",
    }))
    return {"success": ok, "is_active": req.is_active}


@router.get("/accounts/balances")
async def get_accounts_balances():
    """Get live balances from all active secondary accounts."""
    from multi_account import MultiAccountManager
    mgr = MultiAccountManager.get_instance()
    await mgr.load_accounts(db)
    balances = await mgr.get_all_balances()
    # Sync to DB
    for b in balances:
        aid = b.get("account_id")
        tot = b.get("total", 0.0)
        if aid and not b.get("error"):
            await db.update_account_balance(aid, tot)
    total = sum(b.get("total", 0) for b in balances if not b.get("error"))
    return {
        "accounts": balances,
        "total_combined_usdt": round(total, 4),
        "count": len(balances),
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ── MULTI-SERVER CLUSTER STATUS ───────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

@router.get("/nodes")
async def get_cluster_nodes():
    """Return all server nodes in the cluster with their heartbeat status."""
    from node_coordinator import NodeCoordinator, LEADER_TIMEOUT
    from datetime import datetime, timezone, timedelta
    nc = NodeCoordinator.get_instance()
    try:
        nodes = await db.get_all_nodes()
        now   = datetime.now(timezone.utc)
        for n in nodes:
            hb_str = n.get("last_heartbeat", "")
            try:
                hb = datetime.fromisoformat(hb_str.replace("Z", "+00:00")) if hb_str else None
                if hb:
                    if hb.tzinfo is None:
                        hb = hb.replace(tzinfo=timezone.utc)
                    age = (now - hb).total_seconds()
                    n["age_seconds"] = round(age)
                    n["alive"]       = age < LEADER_TIMEOUT
                else:
                    n["age_seconds"] = 9999
                    n["alive"]       = False
            except Exception:
                n["age_seconds"] = 9999
                n["alive"]       = False
        return {
            "this_node": nc.get_status(),
            "nodes":     nodes,
            "total":     len(nodes),
            "leaders":   sum(1 for n in nodes if n.get("is_leader") and n.get("alive")),
            "alive":     sum(1 for n in nodes if n.get("alive")),
        }
    except Exception as e:
        return {"this_node": nc.get_status(), "nodes": [], "error": str(e)}


# ── Add external server node ───────────────────────────────────────────────────

class AddNodeRequest(BaseModel):
    url:   str
    label: str = ""


@router.post("/nodes/add")
async def add_server_node(req: AddNodeRequest):
    """Register an external server URL and ping it to measure latency."""
    import time as _time
    import uuid as _uuid

    raw_url = req.url.strip().rstrip("/")
    if not raw_url.startswith("http"):
        raw_url = "https://" + raw_url

    ping_url = f"{raw_url}/trade/ping"
    latency_ms = 0
    ping_ok    = False
    ping_err   = ""

    try:
        t0 = _time.monotonic()
        async with httpx.AsyncClient(timeout=10) as cx:
            resp = await cx.get(ping_url)
        latency_ms = round((_time.monotonic() - t0) * 1000)
        ping_ok    = resp.status_code == 200
        if not ping_ok:
            ping_err = f"HTTP {resp.status_code}"
    except Exception as e:
        ping_err = str(e)[:120]

    if not ping_ok:
        return {
            "success":    False,
            "error":      f"لم يتم الوصول للسيرفر: {ping_err}",
            "latency_ms": latency_ms,
            "url":        raw_url,
        }

    # Register in DB
    node_id = f"ext-{str(_uuid.uuid4())[:8]}"
    label   = req.label.strip() or raw_url.split("//")[-1].split(".")[0]
    try:
        await db._exec_status("""
            INSERT INTO server_nodes (node_id, hostname, is_leader, last_heartbeat, started_at, url, label, latency_ms)
            VALUES ($1, $2, FALSE, NOW(), NOW(), $3, $4, $5)
            ON CONFLICT (node_id) DO UPDATE
            SET url=$3, label=$4, latency_ms=$5, last_heartbeat=NOW()
        """, node_id, label, raw_url, label, latency_ms)
    except Exception as e:
        return {"success": False, "error": f"DB error: {e}", "latency_ms": latency_ms}

    await manager.broadcast(json.dumps({
        "type": "log",
        "message": f"🖥️ Server added: {label} @ {raw_url} — {latency_ms}ms",
    }))

    return {
        "success":    True,
        "node_id":    node_id,
        "label":      label,
        "url":        raw_url,
        "latency_ms": latency_ms,
        "message":    f"✅ السيرفر متصل — زمن الاستجابة {latency_ms}ms",
    }


@router.delete("/nodes/{node_id}")
async def remove_server_node(node_id: str):
    """Remove a server node from the cluster."""
    from node_coordinator import NodeCoordinator
    nc = NodeCoordinator.get_instance()
    if node_id == nc.node_id:
        raise HTTPException(status_code=400, detail="Cannot remove the current leader node")
    await db.remove_server_node(node_id)
    return {"success": True, "removed": node_id}


@router.post("/nodes/ping-all")
async def ping_all_nodes():
    """Ping all registered external servers and update their latency."""
    import time as _time
    nodes  = await db.get_all_nodes()
    results = []
    for n in nodes:
        url = n.get("url", "")
        if not url:
            continue
        ping_url   = f"{url.rstrip('/')}/trade/ping"
        latency_ms = 9999
        alive      = False
        try:
            t0 = _time.monotonic()
            async with httpx.AsyncClient(timeout=6) as cx:
                r = await cx.get(ping_url)
            latency_ms = round((_time.monotonic() - t0) * 1000)
            alive      = r.status_code == 200
        except Exception:
            pass
        if url:
            await db._exec_status(
                "UPDATE server_nodes SET latency_ms=$1, last_heartbeat=NOW() WHERE node_id=$2",
                latency_ms, n["node_id"]
            )
        results.append({
            "node_id":    n["node_id"],
            "label":      n.get("label", ""),
            "url":        url,
            "alive":      alive,
            "latency_ms": latency_ms,
        })
    return {"pinged": len(results), "results": results}


# ── Global Power Rating ────────────────────────────────────────────────────────

@router.get("/power")
async def get_global_power():
    """Compute global power rating for the bot (0-100%)."""
    from ai_agent import AIAgent
    from node_coordinator import NodeCoordinator, LEADER_TIMEOUT
    from datetime import datetime, timezone

    breakdown: dict = {}

    # ── AI Keys (max 30) ──────────────────────────────────────────────────────
    ai_status = AIAgent.get_instance().pool_status()
    total_keys = ai_status.get("total_keys", 0)
    avail_keys = ai_status.get("available_keys", 0)
    if total_keys == 0:
        ai_score = 0
    elif total_keys == 1:
        ai_score = 12
    elif total_keys == 2:
        ai_score = 22
    else:
        ai_score = 30
    if avail_keys == 0 and total_keys > 0:
        ai_score = max(0, ai_score - 10)  # all exhausted penalty
    breakdown["ai_keys"] = {
        "score": ai_score, "max": 30,
        "label": "مفاتيح AI",
        "detail": f"{avail_keys}/{total_keys} نشط",
    }

    # ── Exchange mode (max 25) ────────────────────────────────────────────────
    bot = await db.get_bot_status()
    mode = bot.get("mode", "demo")
    exchange_name = os.environ.get("EXCHANGE_NAME", "mexc")
    has_creds = bool(os.environ.get("MEXC_API_KEY") or os.environ.get("BINANCE_API_KEY")
                     or os.environ.get("BYBIT_API_KEY") or os.environ.get("KUCOIN_API_KEY"))
    if mode == "live" and has_creds:
        ex_score = 25
    elif has_creds:
        ex_score = 15
    else:
        ex_score = 5
    breakdown["exchange"] = {
        "score": ex_score, "max": 25,
        "label": "اتصال البورصة",
        "detail": f"{exchange_name.upper()} — {'LIVE 🔴' if mode == 'live' else 'DEMO 🔵'}",
    }

    # ── Server count (max 20) ─────────────────────────────────────────────────
    try:
        all_nodes = await db.get_all_nodes()
        now = datetime.now(timezone.utc)
        alive_nodes = []
        for n in all_nodes:
            hb_str = n.get("last_heartbeat", "")
            try:
                hb = datetime.fromisoformat(hb_str.replace("Z", "+00:00")) if hb_str else None
                if hb:
                    if hb.tzinfo is None:
                        hb = hb.replace(tzinfo=timezone.utc)
                    if (now - hb).total_seconds() < LEADER_TIMEOUT:
                        alive_nodes.append(n)
            except Exception:
                pass
        n_alive = len(alive_nodes)
    except Exception:
        n_alive = 1

    if n_alive >= 3:
        srv_score = 20
    elif n_alive == 2:
        srv_score = 13
    elif n_alive == 1:
        srv_score = 6
    else:
        srv_score = 0
    breakdown["servers"] = {
        "score": srv_score, "max": 20,
        "label": "خوادم متصلة",
        "detail": f"{n_alive} سيرفر {'نشط' if n_alive == 1 else 'نشطة'}",
    }

    # ── ML Model (max 15) ─────────────────────────────────────────────────────
    try:
        from ml_model import MLModel
        ml = MLModel(db)
        ml_trained = ml.is_trained()
    except Exception:
        ml_trained = False
    ml_score = 15 if ml_trained else 0
    breakdown["ml_model"] = {
        "score": ml_score, "max": 15,
        "label": "نموذج ML",
        "detail": "مدرّب ✅" if ml_trained else "يحتاج 10+ صفقات",
    }

    # ── Memory (max 10) ───────────────────────────────────────────────────────
    try:
        mem_count = await db._exec_one("SELECT COUNT(*) AS c FROM agent_memory")
        know_count = await db._exec_one("SELECT COUNT(*) AS c FROM bot_knowledge")
        total_mem = (mem_count or {}).get("c", 0) + (know_count or {}).get("c", 0)
        mem_score = min(10, int(total_mem / 2))
    except Exception:
        total_mem = 0
        mem_score = 0
    breakdown["memory"] = {
        "score": mem_score, "max": 10,
        "label": "ذاكرة مكتسبة",
        "detail": f"{total_mem} دَرس/معرفة",
    }

    # ── Total ─────────────────────────────────────────────────────────────────
    total_score = sum(v["score"] for v in breakdown.values())
    total_max   = sum(v["max"]   for v in breakdown.values())
    pct = round(total_score / total_max * 100) if total_max else 0

    if pct >= 90:
        grade, label_ar, global_rank = "S",  "عالمي",      "أفضل من 95% عالمياً"
    elif pct >= 80:
        grade, label_ar, global_rank = "A+", "احترافي",    "أفضل من 85% عالمياً"
    elif pct >= 70:
        grade, label_ar, global_rank = "A",  "متقدم",      "أفضل من 70% عالمياً"
    elif pct >= 60:
        grade, label_ar, global_rank = "B+", "جيد جداً",   "أفضل من 55% عالمياً"
    elif pct >= 50:
        grade, label_ar, global_rank = "B",  "جيد",        "أفضل من 40% عالمياً"
    elif pct >= 35:
        grade, label_ar, global_rank = "C",  "متوسط",      "أفضل من 25% عالمياً"
    else:
        grade, label_ar, global_rank = "D",  "يحتاج إعداد", "أقل من 25% عالمياً"

    return {
        "score":        pct,
        "grade":        grade,
        "label":        label_ar,
        "global_rank":  global_rank,
        "breakdown":    breakdown,
        "tips": [
            v["label"] + " — " + v["detail"]
            for v in breakdown.values()
            if v["score"] < v["max"]
        ][:3],
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ── DATABASE MANAGEMENT Endpoints ──────────────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

class DbUrlRequest(BaseModel):
    url:   str
    label: str = ""


def _detect_db_source(url: str) -> str:
    u = url.lower()
    if "neon.tech" in u:              return "Neon"
    if "supabase" in u:               return "Supabase"
    if "cockroachdb" in u or "crdb" in u or "cockroach" in u: return "CockroachDB"
    if "railway" in u:                return "Railway"
    if "fly.io" in u or "fly.dev" in u: return "Fly.io"
    if "render.com" in u:             return "Render"
    if "localhost" in u or "127.0.0.1" in u: return "Local"
    return "PostgreSQL"


@router.get("/db/status")
async def get_db_status():
    """حالة اتصال قاعدة البيانات الحالية."""
    pool = await db._get_pool()
    connected = pool is not None
    current_url = (
        os.environ.get("QUANTOM_DB_URL", "")
        or os.environ.get("SUPABASE_DB_URL", "")
        or os.environ.get("DATABASE_URL", "")
    )
    source = _detect_db_source(current_url) if current_url else "Replit PostgreSQL"
    return {
        "connected": connected,
        "source":    source,
        "has_url":   bool(current_url),
    }


@router.post("/db/test-url")
async def test_db_url(req: DbUrlRequest):
    """اختبار رابط PostgreSQL دون حفظه."""
    import asyncpg
    import ssl as _ssl

    raw = req.url.strip()
    if not raw:
        return {"success": False, "error": "الرابط فارغ"}
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql://", 1)

    try:
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE
        conn = await asyncpg.connect(raw, ssl=ssl_ctx, command_timeout=10)
        await conn.execute("SELECT 1")
        await conn.close()
        source = _detect_db_source(raw)
        return {"success": True, "source": source, "message": f"✅ اتصال ناجح — {source}"}
    except Exception as e:
        return {"success": False, "error": str(e)[:300]}


@router.post("/db/update-url")
async def update_db_url(req: DbUrlRequest):
    """اختبار وحفظ رابط قاعدة بيانات جديد والاتصال به فوراً."""
    import asyncpg
    import ssl as _ssl

    raw = req.url.strip()
    if not raw:
        return {"success": False, "error": "الرابط فارغ"}
    if raw.startswith("postgres://"):
        raw = raw.replace("postgres://", "postgresql://", 1)

    # ── Test first ───────────────────────────────────────────────────────────
    try:
        ssl_ctx = _ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = _ssl.CERT_NONE
        conn = await asyncpg.connect(raw, ssl=ssl_ctx, command_timeout=10)
        await conn.execute("SELECT 1")
        await conn.close()
    except Exception as e:
        return {"success": False, "error": f"فشل الاتصال: {str(e)[:250]}"}

    # ── Save to env (runtime + .env file) ────────────────────────────────────
    os.environ["QUANTOM_DB_URL"] = raw
    try:
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        lines: list[str] = []
        if os.path.exists(env_path):
            with open(env_path, "r") as f:
                lines = f.readlines()
        found = False
        for i, line in enumerate(lines):
            if line.startswith("QUANTOM_DB_URL="):
                lines[i] = f"QUANTOM_DB_URL={raw}\n"
                found = True
                break
        if not found:
            lines.append(f"QUANTOM_DB_URL={raw}\n")
        with open(env_path, "w") as f:
            f.writelines(lines)
    except Exception as env_e:
        print(f"[DB] Warning: could not write .env: {env_e}")

    # ── Switch connection pool ────────────────────────────────────────────────
    try:
        await db.switch_url(raw)
        await db.ensure_all_tables()
    except Exception as sw_e:
        return {"success": False, "error": f"حُفظ الرابط لكن فشل إعادة الاتصال: {sw_e}"}

    source = _detect_db_source(raw)
    label  = req.label.strip() or source
    await manager.broadcast(json.dumps({
        "type":    "log",
        "message": f"🗄️ قاعدة البيانات تم تحديثها → {label}",
    }))
    return {
        "success": True,
        "source":  source,
        "message": f"✅ متصل بـ {label} — البيانات تُحفظ هناك الآن",
    }


# ═══════════════════════════════════════════════════════════════════════════════
# ── TRADING COMPANY — Multi-Agent Endpoints ────────────────────────────────────
# ═══════════════════════════════════════════════════════════════════════════════

class CompanyAnalyzeRequest(BaseModel):
    symbol:           str   = "BTC/USDT"
    price:            float = 0.0
    rsi:              float = 50.0
    price_change_24h: float = 0.0
    price_change_1h:  float = 0.0
    volume_ratio:     float = 1.0
    bb_position:      float = 0.0


@router.get("/company/status")
async def get_company_status():
    """حالة كل أقسام شركة التداول."""
    try:
        from trading_company import TradingCompany
        company = TradingCompany.get_instance()
        return company.get_company_status()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/company/analyze")
async def company_full_analysis(req: CompanyAnalyzeRequest):
    """
    تشغيل التحليل الشامل: Gemini (أخبار) + MiroFish (جماهير) + MaxHermes (ذاكرة) + Groq (قرار).
    إذا price=0 يجلب السعر الحالي تلقائياً.
    """
    try:
        from trading_company import TradingCompany
        from bybit_client import ExchangeClient
        company = TradingCompany.get_instance()
        company.set_db(db)
        company.set_broadcast_fn(manager.broadcast)

        price = req.price
        if price <= 0:
            try:
                client = ExchangeClient.get_instance()
                price = await client.get_current_price(req.symbol)
            except Exception:
                price = 0.0

        result = await company.full_analysis(
            symbol           = req.symbol,
            price            = price,
            rsi              = req.rsi,
            price_change_24h = req.price_change_24h,
            price_change_1h  = req.price_change_1h,
            volume_ratio     = req.volume_ratio,
            bb_position      = req.bb_position,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/company/decisions")
async def get_company_decisions(limit: int = 20):
    """آخر قرارات شركة التداول."""
    try:
        from trading_company import TradingCompany
        company = TradingCompany.get_instance()
        return {"decisions": company.get_recent_decisions(limit)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/crowd/latest")
async def get_crowd_latest():
    """آخر نتيجة محاكاة الجماهير (MiroFish)."""
    try:
        from crowd_sim import CrowdSimulator
        sim = CrowdSimulator.get_instance()
        if sim.last_result:
            return sim.last_result
        # لا نتيجة بعد — نُرجع حالة المحاكي
        return {
            "crowd_signal": "NEUTRAL",
            "bullish_pct":  50.0,
            "bearish_pct":  50.0,
            "neutral_pct":  0.0,
            "n_traders":    sim.n_traders,
            "fear_greed_index": 0.5,
            "market_psychology": "لم يُشغَّل بعد — اضغط تحليل شامل",
            "whale_action":  "hold",
            "whale_divergence": False,
            "recommendation": "شغّل التحليل الشامل أولاً",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/crowd/simulate")
async def run_crowd_simulation(req: CompanyAnalyzeRequest):
    """يُشغّل محاكاة الجماهير فقط بدون بقية الأقسام."""
    try:
        from crowd_sim import CrowdSimulator
        sim = CrowdSimulator.get_instance()
        price = req.price
        if price <= 0:
            try:
                from bybit_client import ExchangeClient
                price = await ExchangeClient.get_instance().get_current_price(req.symbol)
            except Exception:
                price = 0.0
        result = await __import__("asyncio").to_thread(
            sim.simulate,
            req.symbol, price, req.price_change_1h,
            req.price_change_24h, req.rsi,
            req.volume_ratio, 0.0, req.bb_position,
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


class ExcelUploadRequest(BaseModel):
    filename:     str   = "data.xlsx"
    base64_data:  str   = ""


@router.post("/max-hermes/excel")
async def max_hermes_excel(req: ExcelUploadRequest):
    """MaxHermes يحلل ملف Excel/CSV ويستخرج رؤى."""
    try:
        import base64
        from max_hermes import MaxHermes
        hermes = MaxHermes.get_instance(db)

        if not req.base64_data:
            raise HTTPException(status_code=400, detail="base64_data مطلوب")

        file_bytes = base64.b64decode(req.base64_data)
        result = await hermes.analyze_excel(file_bytes, req.filename)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/max-hermes/report")
async def max_hermes_report(period_days: int = 7):
    """MaxHermes يُولّد تقريراً مالياً شاملاً."""
    try:
        from max_hermes import MaxHermes
        hermes = MaxHermes.get_instance(db)
        return await hermes.generate_report(period_days)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/max-hermes/status")
async def max_hermes_status():
    """حالة MaxHermes."""
    try:
        from max_hermes import MaxHermes
        hermes = MaxHermes.get_instance(db)
        return hermes.get_status()
    except Exception as e:
        return {"active": False, "error": str(e)}


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    client = ExchangeClient.get_instance()
    try:
        await websocket.send_text(json.dumps({
            "type": "log",
            "message": (
                f"🤖 Islamic Trading Bot connected | "
                f"mode: {client.mode.upper()} | exchange: {client.exchange_name} | autopilot ready"
            ),
        }))
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


# ─────────────────────────────────────────────
#  SUPABASE — full freedom endpoints for the bot
# ─────────────────────────────────────────────

@router.get("/supabase/status")
async def supabase_status():
    try:
        from supabase_client import is_configured, SUPABASE_URL, get_supabase_admin
        configured = is_configured()
        connected = False
        if configured:
            sb = get_supabase_admin()
            connected = sb is not None
        return {
            "ok": True,
            "configured": configured,
            "connected": connected,
            "url": SUPABASE_URL if configured else None,
        }
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/supabase/query")
async def supabase_query_endpoint(req: Request):
    """Generic query — bot can SELECT/INSERT/UPDATE/DELETE any table freely."""
    try:
        body = await req.json()
        from supabase_client import supabase_query
        result = await supabase_query(
            table=body.get("table", ""),
            query_type=body.get("type", "select"),
            filters=body.get("filters"),
            data=body.get("data"),
            limit=body.get("limit", 100),
        )
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/supabase/tables")
async def supabase_list_tables():
    """List all public tables in Supabase via RPC."""
    try:
        from supabase_client import get_supabase_admin
        sb = get_supabase_admin()
        if not sb:
            return {"ok": False, "error": "Supabase not configured"}
        # Use rpc to call pg_catalog via a raw query through postgrest
        res = sb.rpc("list_tables", {}).execute()
        if res.data:
            return {"ok": True, "tables": [r.get("table_name") for r in res.data]}
        # Fallback: try querying pg_tables via a workaround
        import httpx, os
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_SERVICE_KEY", "")
        if not url or not key:
            return {"ok": False, "error": "Supabase URL/KEY not set"}
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{url}/rest/v1/rpc/pg_tables_list",
                headers={"apikey": key, "Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json={},
                timeout=8,
            )
        if r.status_code == 200:
            return {"ok": True, "tables": r.json()}
        return {"ok": True, "tables": [], "note": "No tables found or RPC not available — create tables in Supabase dashboard first"}
    except Exception as e:
        return {"ok": True, "tables": [], "note": f"Supabase connected — create tables via dashboard. ({e})"}


@router.post("/supabase/storage/upload")
async def supabase_upload(req: Request):
    """Upload a file to Supabase Storage."""
    try:
        body = await req.json()
        from supabase_client import supabase_storage_upload
        import base64
        content_b64 = body.get("content_base64", "")
        content = base64.b64decode(content_b64) if content_b64 else b""
        result = await supabase_storage_upload(
            bucket=body.get("bucket", "quantom"),
            path=body.get("path", "file"),
            content=content,
            content_type=body.get("content_type", "application/octet-stream"),
        )
        return result
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/supabase/storage/{bucket}")
async def supabase_list_storage(bucket: str, folder: str = ""):
    """List files in a Supabase Storage bucket."""
    try:
        from supabase_client import supabase_storage_list
        return await supabase_storage_list(bucket, folder)
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/supabase/configure")
async def supabase_configure(req: Request):
    """Set SUPABASE_URL at runtime (no restart needed)."""
    try:
        body = await req.json()
        url = body.get("url", "").strip().rstrip("/")
        if not url.startswith("https://"):
            return {"ok": False, "error": "URL must start with https://"}
        import supabase_client as sc
        sc.SUPABASE_URL = url
        sc._client = None
        sc._admin_client = None
        os.environ["SUPABASE_URL"] = url
        sb = sc.get_supabase_admin() or sc.get_supabase()
        return {"ok": sb is not None, "url": url, "connected": sb is not None}
    except Exception as e:
        return {"ok": False, "error": str(e)}


app.include_router(router)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8001))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, log_level="info")
