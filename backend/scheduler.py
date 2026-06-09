"""
Trading scheduler — Agent-powered autonomous scanner v2.0

Smart multi-trigger learning system:
  بدلاً من "كل 5 صفقات":
  • DRAWDOWN (3+ خسائر متتالية) → تأمل فوري + رفع العتبة
  • WIN_STREAK (5+ انتصارات)     → تثبيت الاستراتيجية الناجحة
  • TIME_RHYTHM (كل 30 دقيقة)   → تأمل دوري بغض النظر
  • PERF_DIP (هبوط win rate >10%) → تحليل فوري لسبب التراجع
  • DEEP_REVIEW (كل 10 صفقات)   → مراجعة شاملة لاستراتيجية المحفظة
  • EMERGENCY (5+ خسائر)        → إيقاف اختياري + تأمل عميق
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Callable, Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from dotenv import load_dotenv

load_dotenv()

# ── New world-class modules (imported lazily inside methods for safety) ────────
# price_feed, genetic_optimizer, confluence_engine, onchain_intel,
# portfolio_correlation, ensemble_ai, kelly_criterion, audit_trail


class TradingScheduler:
    def __init__(self, db: Any) -> None:
        self.db = db
        self.scheduler = AsyncIOScheduler()
        self._broadcast_fn: Optional[Callable] = None
        self._adaptive: Any = None
        self._get_target_win_rate: Optional[Callable] = None
        self._get_threshold: Optional[Callable] = None
        self._running = False
        self._scan_lock = asyncio.Lock()
        self._scan_number: int = 0          # 0 = not yet run; first scan = 1
        # ── AI key health tracker (provider+label → last_ok bool) ─────────────
        self._key_health: dict[str, bool] = {}

    def set_broadcast_fn(self, fn: Callable) -> None:
        self._broadcast_fn = fn

    def set_adaptive(self, adaptive: Any, get_target_fn: Callable, get_threshold_fn: Callable) -> None:
        self._adaptive = adaptive
        self._get_target_win_rate = get_target_fn
        self._get_threshold = get_threshold_fn

    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        scan_interval = int(os.environ.get("SCAN_INTERVAL_MINUTES", 5))

        if not self.scheduler.running:
            self.scheduler.start()

        try:
            self.scheduler.remove_job("market_scan")
        except Exception:
            pass

        self.scheduler.add_job(
            self._scan_markets,
            "interval",
            minutes=scan_interval,
            id="market_scan",
            next_run_time=datetime.now(),
            max_instances=1,
            coalesce=True,
        )

        # ── Gemini periodic news polling (every 15 min) ──────────────────────
        try:
            self.scheduler.remove_job("gemini_news_poll")
        except Exception:
            pass
        self.scheduler.add_job(
            self._poll_gemini_news,
            "interval",
            minutes=15,
            id="gemini_news_poll",
            next_run_time=datetime.now(),
            max_instances=1,
            coalesce=True,
        )

        # ── Crowd simulation background refresh (every 10 min) ──────────────
        try:
            self.scheduler.remove_job("crowd_refresh")
        except Exception:
            pass
        self.scheduler.add_job(
            self._refresh_crowd_sim,
            "interval",
            minutes=10,
            id="crowd_refresh",
            next_run_time=datetime.now(),
            max_instances=1,
            coalesce=True,
        )

        # ── On-chain intel refresh (every 15 min) ────────────────────────────
        try:
            self.scheduler.remove_job("onchain_refresh")
        except Exception:
            pass
        self.scheduler.add_job(
            self._refresh_onchain_intel,
            "interval",
            minutes=15,
            id="onchain_refresh",
            next_run_time=datetime.now(),
            max_instances=1,
            coalesce=True,
        )

        # ── Genetic optimizer (every 24 h) ───────────────────────────────────
        try:
            self.scheduler.remove_job("genetic_optimizer")
        except Exception:
            pass
        self.scheduler.add_job(
            self._run_genetic_optimizer,
            "interval",
            hours=24,
            id="genetic_optimizer",
            max_instances=1,
            coalesce=True,
        )

        # ── Correlation matrix refresh (every 60 min) ────────────────────────
        try:
            self.scheduler.remove_job("correlation_refresh")
        except Exception:
            pass
        self.scheduler.add_job(
            self._refresh_correlation,
            "interval",
            minutes=60,
            id="correlation_refresh",
            next_run_time=datetime.now(),
            max_instances=1,
            coalesce=True,
        )

        # ── Price feed start ─────────────────────────────────────────────────
        asyncio.create_task(self._start_price_feed())

        # ── AI key health monitor (every 30 min) ─────────────────────────────
        try:
            self.scheduler.remove_job("ai_key_retry")
        except Exception:
            pass
        self.scheduler.add_job(
            self._retry_failed_keys,
            "interval",
            minutes=30,
            id="ai_key_retry",
            next_run_time=datetime.now(),
            max_instances=1,
            coalesce=True,
        )

        # ── Memory auto-consolidation (every 6 hours) ─────────────────────────
        try:
            self.scheduler.remove_job("memory_consolidation")
        except Exception:
            pass
        self.scheduler.add_job(
            self._consolidate_memory,
            "interval",
            hours=6,
            id="memory_consolidation",
            max_instances=1,
            coalesce=True,
        )

        # ── Audit trail init ─────────────────────────────────────────────────
        try:
            from audit_trail import AuditTrail
            AuditTrail.get_instance().init(self.db)
        except Exception as _at:
            print(f"[AuditTrail] init error: {_at}")

        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        for job_id in ("market_scan", "gemini_news_poll", "crowd_refresh",
                       "onchain_refresh", "genetic_optimizer", "correlation_refresh",
                       "ai_key_retry", "memory_consolidation"):
            try:
                self.scheduler.remove_job(job_id)
            except Exception:
                pass
        self._running = False

    # ── Price Feed ────────────────────────────────────────────────────────────

    async def _start_price_feed(self) -> None:
        """Start WebSocket/polling real-time price feed."""
        await asyncio.sleep(5)   # wait for exchange client to be ready
        try:
            from price_feed import PriceFeed
            from bybit_client import ExchangeClient
            symbols_env = os.environ.get("TRADING_SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT")
            syms = [s.strip() for s in symbols_env.split(",") if s.strip()]
            feed = PriceFeed.get_instance()
            await feed.start(syms)
            print(f"[PriceFeed] ▶ Started for {syms}")
        except Exception as e:
            print(f"[PriceFeed] Start error: {e}")

    # ── On-chain intel refresh ────────────────────────────────────────────────

    async def _refresh_onchain_intel(self) -> None:
        """Fetch Fear&Greed, BTC dominance, trending coins every 15 min."""
        try:
            from onchain_intel import get_intel
            symbols_env = os.environ.get("TRADING_SYMBOLS", "BTC/USDT,ETH/USDT")
            syms = [s.strip() for s in symbols_env.split(",") if s.strip()]
            intel = await get_intel(syms)
            summary = intel.get("summary", "")
            regime  = intel.get("market_regime", "neutral")
            print(f"[OnChain] {summary}")
            await self._broadcast(json.dumps({
                "type": "log",
                "message": f"🌐 On-Chain: {summary}",
            }))
        except Exception as e:
            print(f"[OnChain] Refresh error: {e}")

    # ── AI Key Health Monitor ─────────────────────────────────────────────────

    async def _retry_failed_keys(self) -> None:
        """
        كل 30 دقيقة: يختبر كل مفاتيح AI المخزنة.
        - إذا عاد مفتاح معطل → إشعار فوري + إعادة تفعيله
        - إذا مات مفتاح كان يعمل → تحذير فوري
        """
        import httpx, asyncio as _asyncio, time as _time

        _DEFAULTS = {
            "gemini": ("https://generativelanguage.googleapis.com", "gemini-2.0-flash"),
            "openai": ("https://api.openai.com/v1",                 "gpt-4o-mini"),
            "claude": ("https://api.anthropic.com/v1",              "claude-3-5-haiku-20241022"),
            "grok":   ("https://api.x.ai/v1",                       "grok-3-mini"),
            "groq":   ("https://api.groq.com/openai/v1",            "llama-3.3-70b-versatile"),
        }

        async def _ping(row: dict) -> tuple[str, bool, int]:
            provider = (row.get("provider") or "").lower()
            api_key  = row.get("api_key") or ""
            label    = row.get("label") or provider.upper()
            model    = row.get("model") or ""
            base_url = row.get("base_url") or ""
            b_url, default_model = _DEFAULTS.get(provider, (base_url, model or "gpt-4o-mini"))
            use_model = model or default_model
            if not api_key or not b_url:
                return label, False, 0
            t0 = _time.monotonic()
            try:
                async with httpx.AsyncClient(timeout=10) as c:
                    if provider == "gemini":
                        r = await c.post(
                            f"https://generativelanguage.googleapis.com/v1beta/models/{use_model}:generateContent?key={api_key}",
                            json={"contents": [{"parts": [{"text": "hi"}]}]},
                        )
                    elif provider == "claude":
                        r = await c.post(
                            f"{b_url}/messages",
                            headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                            json={"model": use_model, "max_tokens": 1, "messages": [{"role": "user", "content": "hi"}]},
                        )
                    else:
                        r = await c.post(
                            f"{b_url}/chat/completions",
                            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                            json={"model": use_model, "messages": [{"role": "user", "content": "hi"}], "max_tokens": 1},
                        )
                ok = r.status_code in (200, 201)
            except Exception:
                ok = False
            latency = round((_time.monotonic() - t0) * 1000)
            return label, ok, latency

        try:
            rows = await self.db.get_ai_keys()
            if not rows:
                return

            results = await _asyncio.gather(*[_ping(r) for r in rows])

            recovered, degraded = [], []
            for label, ok, latency in results:
                prev = self._key_health.get(label)   # None = first time
                self._key_health[label] = ok
                if prev is False and ok:              # was dead → now alive
                    recovered.append((label, latency))
                elif prev is True and not ok:         # was alive → now dead
                    degraded.append(label)

            # ── Broadcast events ──────────────────────────────────────────────
            for label, ms in recovered:
                msg = f"🟢 مفتاح AI عاد للعمل: {label} ({ms}ms) — تمّ إعادة تفعيله تلقائياً"
                print(f"[AIKeyMonitor] {msg}")
                await self._broadcast(json.dumps({"type": "log", "message": msg}))
                # Reload key into active pool
                try:
                    from ai_agent import AIAgent
                    AIAgent.get_instance().load_keys_from_env()
                except Exception:
                    pass

            for label in degraded:
                msg = f"🔴 مفتاح AI توقف عن العمل: {label} — سيُعاد الاختبار خلال 30 دقيقة"
                print(f"[AIKeyMonitor] {msg}")
                await self._broadcast(json.dumps({"type": "log", "message": msg}))

            # ── Summary log (only if we have keys) ───────────────────────────
            ok_count   = sum(1 for _, ok, _ in results if ok)
            fail_count = len(results) - ok_count
            status_emoji = "✅" if fail_count == 0 else ("⚠️" if ok_count > 0 else "❌")
            print(f"[AIKeyMonitor] {status_emoji} {ok_count}/{len(results)} مفاتيح AI نشطة")

        except Exception as e:
            print(f"[AIKeyMonitor] Error: {e}")

    # ── Memory Auto-Consolidation ─────────────────────────────────────────────

    async def _consolidate_memory(self) -> None:
        """
        كل 6 ساعات: يراجع الدروس المتراكمة ويستخلص منها قواعد استراتيجية.
        يحوّل الدروس المتفرقة إلى معرفة راسخة في bot_knowledge.
        """
        try:
            from memory_engine import MemoryEngine
            engine = MemoryEngine(self.db)
            summary = await engine.consolidate_lessons()
            if summary:
                print(f"[Memory] 🧠 Consolidation done: {summary}")
                await self._broadcast(json.dumps({
                    "type": "log",
                    "message": f"🧠 ذاكرة: {summary}",
                }))
        except Exception as e:
            print(f"[Memory] Consolidation error: {e}")

    # ── Genetic optimizer ─────────────────────────────────────────────────────

    async def _run_genetic_optimizer(self) -> None:
        """Run genetic evolution on closed trades every 24h."""
        try:
            from genetic_optimizer import GeneticOptimizer
            opt = GeneticOptimizer.get_instance()
            if not opt.should_run():
                return
            all_trades = await self.db.get_trades(limit=500)
            closed = [t for t in all_trades if t.get("status") == "closed"]
            best = await opt.maybe_evolve(closed)
            if best:
                await self._broadcast(json.dumps({
                    "type": "log",
                    "message": (
                        f"🧬 Genetic Optimizer: gen {best.generation} | "
                        f"fitness={best.fitness:.3f} | "
                        f"conf≥{best.min_confidence:.0f} SL={best.sl_pct:.1f}% TP={best.tp_pct:.1f}%"
                    ),
                }))
        except Exception as e:
            print(f"[GA] Optimizer error: {e}")

    # ── Correlation refresh ───────────────────────────────────────────────────

    async def _refresh_correlation(self) -> None:
        """Refresh portfolio correlation matrix every 60 min."""
        try:
            from portfolio_correlation import PortfolioCorrelation
            from bybit_client import ExchangeClient
            symbols_env = os.environ.get("TRADING_SYMBOLS", "BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT")
            syms   = [s.strip() for s in symbols_env.split(",") if s.strip()]
            client = ExchangeClient.get_instance()
            pc     = PortfolioCorrelation.get_instance()
            await pc.refresh(syms, client)
            status = pc.status()
            print(f"[Correlation] Matrix refreshed — {status['pairs_tracked']} pairs")
        except Exception as e:
            print(f"[Correlation] Refresh error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Gemini Periodic News Polling
    # ─────────────────────────────────────────────────────────────────────────

    async def _poll_gemini_news(self) -> None:
        """
        Gemini يرصد الأخبار كل 15 دقيقة ويُحدّث cache شركة التداول.
        يعمل حتى لو لم يكن الـ autopilot مشغّلاً.
        """
        symbols_env = os.environ.get("TRADING_SYMBOLS", "BTC/USDT,ETH/USDT")
        primary_symbol = symbols_env.split(",")[0].strip() if symbols_env else "BTC/USDT"
        try:
            from trading_company import TradingCompany
            company = TradingCompany.get_instance()
            company.set_db(self.db)
            intel = await company.fetch_intelligence(primary_symbol)
            news_score = intel.get("news_score", 0.0)
            fear_greed = intel.get("fear_greed", 50)
            summary    = intel.get("news_summary", "")[:120]
            print(f"[GeminiPoll] {primary_symbol} — score:{news_score:.2f} | F&G:{fear_greed} | {summary}")
            await self._broadcast(json.dumps({
                "type":    "log",
                "message": f"📰 Gemini News Poll — {primary_symbol}: {summary[:80]}",
            }))
        except Exception as e:
            print(f"[GeminiPoll] error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # Crowd Simulation Refresh
    # ─────────────────────────────────────────────────────────────────────────

    async def _refresh_crowd_sim(self) -> None:
        """
        MiroFish يُحدّث محاكاة 1000 متداول وهمي كل 10 دقائق.
        """
        symbols_env = os.environ.get("TRADING_SYMBOLS", "BTC/USDT,ETH/USDT")
        primary_symbol = symbols_env.split(",")[0].strip() if symbols_env else "BTC/USDT"
        try:
            from crowd_sim import CrowdSimulator
            from bybit_client import ExchangeClient

            sim    = CrowdSimulator.get_instance()
            client = ExchangeClient.get_instance()
            price  = await client.get_current_price(primary_symbol)
            if price <= 0:
                return

            # احسب RSI تقريبي من السعر الحالي وآخر سعر محفوظ
            rsi = 50.0
            try:
                import ta
                import pandas as pd
                ohlcv = await client.get_ohlcv(primary_symbol, timeframe="1h", limit=20)
                if ohlcv and len(ohlcv) >= 15:
                    closes = pd.Series([c[4] for c in ohlcv])
                    rsi_series = ta.momentum.RSIIndicator(closes, window=14).rsi()
                    rsi = float(rsi_series.iloc[-1])
            except Exception:
                pass

            result = await __import__("asyncio").to_thread(
                sim.simulate, primary_symbol, price,
                0.0, 0.0, rsi, 1.0, 0.0, 0.0,
            )
            signal = result.get("crowd_signal", "NEUTRAL")
            bull   = result.get("bullish_pct",  50)
            bear   = result.get("bearish_pct",  50)
            print(f"[CrowdSim] {primary_symbol} — {signal} | 🐂{bull:.0f}% / 🐻{bear:.0f}%")
            await self._broadcast(json.dumps({
                "type":    "log",
                "message": f"🐟 MiroFish — {primary_symbol}: {signal} | 🐂{bull:.0f}% 🐻{bear:.0f}%",
            }))
        except Exception as e:
            print(f"[CrowdSim] refresh error: {e}")

    async def _broadcast(self, message: str) -> None:
        if self._broadcast_fn:
            try:
                await self._broadcast_fn(message)
            except Exception:
                pass

    async def _run_adaptive_adjustment(self) -> None:
        if not self._adaptive or not self._get_target_win_rate or not self._get_threshold:
            return
        try:
            target  = self._get_target_win_rate()
            current = self._get_threshold()
            await self._adaptive.maybe_adjust(current, target, self._broadcast_fn)
        except Exception as e:
            print(f"[Scheduler] adaptive error: {e}")

    # ── SL / TP monitoring ────────────────────────────────────────────────────

    async def _check_open_trades(self, client: Any) -> list[dict]:
        """Check all open trades and close any that hit SL or TP. Returns closed trades."""
        from risk_manager import RiskManager
        rm = RiskManager()
        closed_trades: list[dict] = []

        try:
            trades      = await self.db.get_trades(limit=200)
            open_trades = [t for t in trades if t.get("status") == "open"]
        except Exception as e:
            print(f"[Scheduler] get open trades error: {e}")
            return []

        for trade in open_trades:
            try:
                symbol = trade.get("symbol", "")
                side   = trade.get("side", "buy")
                entry  = float(trade.get("entry_price") or 0)
                sl     = float(trade.get("stop_loss_price") or 0)
                tp     = float(trade.get("take_profit_price") or 0)
                qty    = float(trade.get("quantity") or 0)
                tid    = trade.get("id", "")

                if not symbol or entry <= 0:
                    continue

                current_price = await client.get_current_price(symbol)
                if current_price <= 0:
                    continue

                # ── Trailing Stop-Loss (حماية الأرباح تلقائياً) ──────────────
                if entry > 0 and sl > 0:
                    move_pct = (current_price - entry) / entry * 100 if side == "buy" else (entry - current_price) / entry * 100
                    new_sl: Optional[float] = None

                    if side == "buy":
                        if move_pct >= 10.0:
                            candidate = round(entry * 1.07, 6)   # lock in 7%
                            if candidate > sl:
                                new_sl = candidate
                        elif move_pct >= 5.0:
                            candidate = round(entry * 1.03, 6)   # lock in 3%
                            if candidate > sl:
                                new_sl = candidate
                        elif move_pct >= 2.0:
                            candidate = round(entry * 1.005, 6)  # break-even + 0.5%
                            if candidate > sl:
                                new_sl = candidate
                    else:  # sell
                        if move_pct >= 10.0:
                            candidate = round(entry * 0.93, 6)
                            if candidate < sl:
                                new_sl = candidate
                        elif move_pct >= 5.0:
                            candidate = round(entry * 0.97, 6)
                            if candidate < sl:
                                new_sl = candidate
                        elif move_pct >= 2.0:
                            candidate = round(entry * 0.995, 6)
                            if candidate < sl:
                                new_sl = candidate

                    if new_sl is not None:
                        old_sl = sl
                        sl = new_sl
                        await self.db.update_trade(tid, {"stop_loss_price": new_sl})
                        await self._broadcast(json.dumps({
                            "type": "log",
                            "message": (
                                f"🔒 Trailing SL — {symbol} | "
                                f"SL: ${old_sl:.4f} → ${new_sl:.4f} | "
                                f"حركة: +{move_pct:.1f}%"
                            ),
                        }))
                # ─────────────────────────────────────────────────────────────

                hit_sl = hit_tp = False
                if side == "buy":
                    if sl > 0 and current_price <= sl:
                        hit_sl = True
                    elif tp > 0 and current_price >= tp:
                        hit_tp = True
                else:
                    if sl > 0 and current_price >= sl:
                        hit_sl = True
                    elif tp > 0 and current_price <= tp:
                        hit_tp = True

                if hit_sl or hit_tp:
                    pnl     = rm.estimate_pnl(side, entry, current_price, qty)
                    outcome = "TP ✅" if hit_tp else "SL 🔴"

                    await self.db.update_trade(tid, {
                        "status":    "closed",
                        "exit_price": current_price,
                        "pnl":        pnl,
                        "closed_at":  datetime.utcnow().isoformat(),
                    })
                    await self.db.recalculate_stats()

                    await self._broadcast(json.dumps({
                        "type": "trade",
                        "message": (
                            f"[{outcome}] {symbol} @ ${current_price:.4f} | "
                            f"PnL: ${pnl:+.4f} | Entry: ${entry:.4f}"
                        ),
                    }))

                    # ── Audit Trail: log trade close ──────────────────────────
                    try:
                        from audit_trail import AuditTrail
                        open_ts  = trade.get("created_at")
                        dur_min  = 0.0
                        if open_ts:
                            import time as _time
                            dur_min = (_time.time() - (float(open_ts) if isinstance(open_ts, (int, float)) else 0)) / 60
                        AuditTrail.get_instance().log_trade_close(trade, pnl, dur_min)
                    except Exception as _atc:
                        print(f"[Audit] Trade close log error: {_atc}")

                    # ── Smart Push Notification: trade close ──────────────────
                    try:
                        from push_manager import PushManager
                        _push = PushManager.get_instance()
                        if _push.token_count > 0:
                            await _push.notify_trade_close(trade, pnl, current_price)
                    except Exception as _pe:
                        print(f"[Push] trade-close error: {_pe}")
                    # ─────────────────────────────────────────────────────────

                    closed_trade = {**trade, "exit_price": current_price, "pnl": pnl, "status": "closed"}
                    closed_trades.append(closed_trade)

                    # ── Auto trade commentary (brain chat) ────────────────────
                    try:
                        from trade_commentator import fire_trade_comment
                        event = "close_win" if hit_tp else "close_loss"
                        fire_trade_comment(self.db, closed_trade, event, current_price)
                    except Exception as _tc:
                        print(f"[Commentator] SL/TP hook error: {_tc}")

            except Exception as e:
                print(f"[Scheduler] SL/TP check error {trade.get('symbol')}: {e}")

        return closed_trades

    async def _process_closed_trade(self, trade: dict, agent: Any) -> None:
        """
        Run the full learning pipeline for a newly closed trade.
        Uses the Smart Multi-Trigger system instead of "every N trades".
        """
        from learning_loop import LearningLoop

        ll = LearningLoop(self.db)

        # ── 1. Per-trade reflection (Gemini lesson) ────────────────────────
        await ll.reflect_on_trade(trade, broadcast_fn=self._broadcast_fn)

        # ── 2. Agent learns + get smart triggers ──────────────────────────
        triggers = await agent.post_trade_learn(trade)

        # ── 3. Smart trigger responses ─────────────────────────────────────
        perception = await agent.perceive()

        if triggers.get("emergency_halt"):
            # 5+ consecutive losses — emergency protocol
            await self._broadcast(json.dumps({
                "type": "agent",
                "message": (
                    "🛑 EMERGENCY HALT: 5 consecutive losses detected. "
                    "Bot has BLOCKED new BUY signals pending deep reflection. "
                    "Running emergency analysis now..."
                ),
            }))
            # Push: emergency halt
            try:
                from push_manager import PushManager
                _push = PushManager.get_instance()
                if _push.token_count > 0:
                    cons_l = perception.get("consecutive_losses", 5)
                    await _push.notify_emergency(cons_l)
            except Exception as _pe:
                print(f"[Push] emergency error: {_pe}")

            await agent.deep_reflect(perception, trigger="drawdown")
            await ll.strategic_review(broadcast_fn=self._broadcast_fn)
            agent.reset_deep_review_counter()
            # Note: memory._emergency_halted is set True, new buys are blocked by enhance_decision
            # User must manually reset or it auto-resets after next reflection

        elif triggers.get("drawdown_alert"):
            # 3-4 consecutive losses — reflect + raise threshold
            await self._broadcast(json.dumps({
                "type": "agent",
                "message": "⚠️ DRAWDOWN ALERT: 3 خسائر متتالية — البوت يرفع عتبة الثقة تلقائياً",
            }))
            # Push: drawdown alert
            try:
                from push_manager import PushManager
                _push = PushManager.get_instance()
                if _push.token_count > 0:
                    cons_l = perception.get("consecutive_losses", 3)
                    await _push.notify_drawdown(cons_l)
            except Exception as _pe:
                print(f"[Push] drawdown error: {_pe}")

            await agent.deep_reflect(perception, trigger="drawdown")
            await self._run_adaptive_adjustment()

        elif triggers.get("win_streak_review"):
            # 5+ consecutive wins — lock in strategy
            await self._broadcast(json.dumps({
                "type": "agent",
                "message": "🏆 WIN STREAK: 5 صفقات رابحة متتالية — البوت في أفضل حالاته! يدرس الاستراتيجية...",
            }))
            # Push: win streak
            try:
                from push_manager import PushManager
                _push = PushManager.get_instance()
                if _push.token_count > 0:
                    cons_w = perception.get("consecutive_wins", 5)
                    await _push.notify_win_streak(cons_w)
            except Exception as _pe:
                print(f"[Push] win-streak error: {_pe}")

            await agent.deep_reflect(perception, trigger="win_streak")

        # ── 4. Performance dip (independent of streaks) ───────────────────
        if perception.get("perf_dip_trigger"):
            await agent.deep_reflect(perception, trigger="perf_dip")

        # ── 5. Deep review every 10 closed trades ─────────────────────────
        if agent._trades_since_deep_review >= 10:
            await ll.strategic_review(broadcast_fn=self._broadcast_fn)
            agent.reset_deep_review_counter()

        # ── 6. ML retraining (non-blocking — runs in background thread) ───────
        try:
            from ml_model import TradingMLModel
            ml = TradingMLModel.get_instance()
            if ml.should_retrain():
                closed_for_ml = await self.db.get_closed_trades_for_ml()
                trained = await ml.async_train(closed_for_ml)   # ← non-blocking
                if trained:
                    top = ml.feature_importances[0] if ml.feature_importances else ("?", 0)
                    await self._broadcast(json.dumps({
                        "type": "log",
                        "message": (
                            f"🧠 ML retrained on {ml.n_samples} trades | "
                            f"Top signal: {top[0]} ({top[1]*100:.0f}%)"
                        ),
                    }))
        except Exception as me:
            print(f"[ML] Retrain error: {me}")

        # ── 7. Adaptive threshold adjustment ──────────────────────────────
        await self._run_adaptive_adjustment()

    async def _get_closed_count(self) -> int:
        try:
            trades = await self.db.get_trades(limit=500)
            return len([t for t in trades if t.get("status") == "closed"])
        except Exception:
            return 0

    # ── Dynamic symbol selection ───────────────────────────────────────────────

    async def _select_symbols(self, client: Any, max_symbols: int = 6) -> list[str]:
        # ── 1. Load user-configured portfolio assets from DB ─────────────────
        try:
            db_assets = await self.db.get_portfolio_assets()
            db_enabled = [
                a["symbol"].replace("-", "/").upper()
                for a in db_assets
                if a.get("enabled", True) and a.get("symbol")
            ]
            if db_enabled:
                # User has configured a custom portfolio — use it
                print(f"[Scheduler] Using DB portfolio: {db_enabled}")
                return db_enabled[:max_symbols]
        except Exception as _e:
            print(f"[Scheduler] DB assets load error: {_e}")

        # ── 2. Fallback: env var or dynamic scoring ──────────────────────────
        fallback_raw = os.environ.get(
            "TRADING_SYMBOLS",
            "BTC/USDT,ETH/USDT,SOL/USDT,XRP/USDT,BNB/USDT,AVAX/USDT",
        )
        fallback = [s.strip() for s in fallback_raw.split(",") if s.strip()]

        FULL_POOL = [
            "BTC/USDT", "ETH/USDT", "BNB/USDT", "SOL/USDT",
            "XRP/USDT", "ADA/USDT", "AVAX/USDT", "LINK/USDT",
            "DOT/USDT", "LTC/USDT", "NEAR/USDT", "TRX/USDT",
        ]

        scores: list[tuple[float, str]] = []
        for sym in FULL_POOL:
            try:
                ohlcv = await client.get_ohlcv(sym, "1h", 12)
                if not ohlcv or len(ohlcv) < 6:
                    continue
                closes   = [c[4] for c in ohlcv]
                chg_pct  = abs(closes[-1] - closes[0]) / closes[0] * 100
                volumes  = [c[5] for c in ohlcv]
                avg_vol  = sum(volumes) / len(volumes) if volumes else 0
                if avg_vol < 10:
                    continue
                scores.append((chg_pct, sym))
            except Exception:
                continue

        if not scores:
            return fallback[:max_symbols]

        scores.sort(key=lambda x: x[0], reverse=True)
        selected = [s[1] for s in scores[:max_symbols]]

        # Always include BTC as market leader for context
        if "BTC/USDT" not in selected and len(selected) == max_symbols:
            selected[-1] = "BTC/USDT"

        return selected

    # ── Main scan ─────────────────────────────────────────────────────────────

    async def _scan_markets(self) -> None:
        if self._scan_lock.locked():
            print("[Scheduler] Scan already running — skipping tick")
            return
        async with self._scan_lock:
            try:
                await self._do_scan()
            except Exception as e:
                import traceback
                print(f"[Scheduler] _do_scan CRASHED: {e}")
                print(traceback.format_exc())

    async def _do_scan(self) -> None:
        from bybit_client import ExchangeClient, IslamicViolationError
        from gemini_agent import GeminiAgent
        from indicators import get_market_indicators
        from risk_manager import RiskManager
        from agent_core import TradingAgent

        client       = ExchangeClient.get_instance()
        gemini       = GeminiAgent.get_instance()
        risk_manager = RiskManager()
        agent        = TradingAgent.get_instance(db=self.db)
        agent.set_broadcast_fn(self._broadcast_fn)

        self._scan_number += 1
        scan_num = agent.increment_scan()

        # First scan after startup: skip Gemini to preserve quota for chat.
        # The scanner will use rule-based decisions; Gemini activates from scan #2.
        gemini_enabled = self._scan_number > 1

        # ── PERCEIVE ──────────────────────────────────────────────────────
        perception = await agent.perceive()

        # ── Emergency: skip new trades if halted ──────────────────────────
        emergency_halted = perception.get("emergency_halted", False)

        # ── THINK + PLAN ──────────────────────────────────────────────────
        symbols      = await self._select_symbols(client, max_symbols=6)

        # ── Shariah Filter (فلتر الامتثال الإسلامي) ───────────────────────
        try:
            from shariah_auditor import ShariahAuditor
            auditor  = ShariahAuditor.get_instance()
            halal    = auditor.filter_halal(symbols, allow_caution=True)
            rejected = [s for s in symbols if s not in halal]
            if rejected:
                print(f"[Shariah] ❌ رموز مرفوضة: {rejected}")
                await self._broadcast(json.dumps({
                    "type": "log",
                    "message": f"🕌 Shariah Auditor: رُفض {', '.join(rejected)} | تبقّى: {', '.join(halal)}",
                }))
            symbols = halal if halal else symbols   # fallback if all rejected
        except Exception as _sa:
            print(f"[Shariah] Auditor error: {_sa}")
        # ──────────────────────────────────────────────────────────────────

        market_data  = {s: {} for s in symbols}
        plan         = await agent.think(perception, market_data)

        # ── Time-rhythm reflection ─────────────────────────────────────────
        if plan.get("needs_reflection") and perception.get("total_closed", 0) >= 3:
            await agent.deep_reflect(perception, trigger="time")

        timestamp  = datetime.utcnow().strftime("%H:%M:%S UTC")
        mode_tag   = f"[{'LIVE' if client.mode == 'live' else 'DEMO'}]"
        strat_tag  = f"[{agent.memory._current_strategy.upper()[:6]}]"
        cons_loss  = perception.get("consecutive_losses", 0)
        cons_win   = perception.get("consecutive_wins", 0)
        streak_tag = f"🔴×{cons_loss}" if cons_loss > 0 else (f"🟢×{cons_win}" if cons_win > 0 else "—")

        halt_tag   = " 🛑HALTED" if emergency_halted else ""
        scan_msg   = (
            f"🤖 {mode_tag}{strat_tag} Scan #{scan_num} — {', '.join(s.replace('/USDT','') for s in symbols)}"
            f" @ {timestamp} | WR:{perception.get('win_rate',0):.0f}% | streak:{streak_tag}"
            f" | conf≥{gemini.min_confidence}%{halt_tag}"
        )
        print(f"[Scheduler] {scan_msg}")
        await self._broadcast(json.dumps({"type": "log", "message": scan_msg}))

        # ── 1. Check SL/TP on open trades ─────────────────────────────────
        newly_closed = await self._check_open_trades(client)
        for closed_trade in newly_closed:
            await self._process_closed_trade(closed_trade, agent)

        # ── 2. Get balance ─────────────────────────────────────────────────
        balance_data  = await client.get_balance()
        total_balance = balance_data.get("total", 0)
        await self.db.update_bot_status(last_scan_at=datetime.utcnow())

        trades_this_scan = 0

        # ── Pre-fetch all open trades once (used in SELL pre-filter) ──────
        try:
            _all_open = await self.db.get_trades(limit=300)
            _open_symbols = {
                t.get("symbol") for t in _all_open
                if t.get("status") == "open" and t.get("side") == "buy"
            }
        except Exception:
            _open_symbols = set()

        # ── 3. Scan each symbol for signals (with indicator cache) ────────
        from indicator_cache import IndicatorCache
        ind_cache = IndicatorCache.get_instance()

        for symbol in symbols:
            try:
                ohlcv = await ind_cache.get_ohlcv(
                    symbol, "15m", 100,
                    fetch_fn=client.get_ohlcv,
                )
                if not ohlcv or len(ohlcv) < 30:
                    await self._broadcast(json.dumps({
                        "type": "log",
                        "message": f"⚠️ {symbol}: insufficient OHLCV ({len(ohlcv) if ohlcv else 0} candles)",
                    }))
                    continue

                indicators = await ind_cache.get_indicators(
                    symbol, "15m", 100, ohlcv,
                    compute_fn=get_market_indicators,
                )
                if not indicators or "error" in indicators:
                    continue

                current_price = indicators.get("current_price", 0)

                rsi    = indicators.get("rsi", 50)
                bb_pct = indicators.get("bb_pct", 0.5)

                # هل يوجد صفقة BUY مفتوحة لهذا الرمز؟
                has_open_pos = symbol in _open_symbols

                # ── Pre-filter: تجاهل التحليل إلا إذا كان هناك إشارة حقيقية ──
                # مهم: إذا كان هناك صفقة مفتوحة، دائماً ادرس إمكانية البيع
                has_signal = (
                    rsi <= 40 or rsi >= 55            # أكثر حساسية للبيع (كان 60)
                    or bb_pct <= 0.20 or bb_pct >= 0.75  # أكثر حساسية (كان 0.80)
                    or has_open_pos                   # ← الإصلاح الرئيسي: دائماً حلّل إذا في صفقة
                )
                if not has_signal or not gemini_enabled:
                    label = "startup warm-up" if not gemini_enabled else f"RSI={rsi:.0f}, BB={bb_pct:.2f}"
                    await self._broadcast(json.dumps({
                        "type": "signal", "symbol": symbol, "action": "HOLD",
                        "confidence": 0,
                        "message": f"📡 {symbol}: HOLD ({label} — no AI call)",
                    }))
                    continue

                lessons = await self.db.get_recent_lessons(limit=8)

                # أضف سياق الصفقة المفتوحة للـ indicators حتى يعرف AI أن يقول SELL
                # (نستخدم _all_open المجلوب مسبقاً لتجنب DB call إضافي)
                _pre_open_buys = [
                    t for t in _all_open
                    if t.get("symbol") == symbol
                    and t.get("status") == "open"
                    and t.get("side") == "buy"
                ]
                if _pre_open_buys:
                    indicators["_open_trade"] = _pre_open_buys[0]

                # Throttle Gemini calls — 8s gap keeps us well under 15 req/min free tier
                await asyncio.sleep(8)
                raw_decision = await gemini.analyze_market(symbol, ohlcv, indicators, lessons)

                # ── Ensemble AI Voting (5 voters) ──────────────────────────
                ensemble_result = None
                try:
                    from ensemble_ai import ensemble_vote
                    ensemble_result = await ensemble_vote(symbol, indicators, raw_decision, client)
                    e_action = ensemble_result.action
                    e_conf   = ensemble_result.confidence
                    e_agree  = ensemble_result.agreement
                    print(f"[Ensemble] {symbol}: {e_action} {e_conf:.0f}% ({e_agree}/5 agree)")
                    await self._broadcast(json.dumps({
                        "type": "log",
                        "message": (
                            f"🗳️ Ensemble {symbol}: {e_action} {e_conf:.0f}% "
                            f"| agreement {e_agree}/5 "
                            f"| score={ensemble_result.weighted_score:.2f}"
                        ),
                    }))
                    # Override raw_decision with ensemble consensus
                    raw_decision = {
                        **raw_decision,
                        "action":     e_action,
                        "confidence": e_conf,
                        "reasoning":  f"[Ensemble {e_agree}/5] " + raw_decision.get("reasoning", ""),
                    }
                except Exception as _ev:
                    print(f"[Ensemble] Error: {_ev}")

                # ── Agent layer ────────────────────────────────────────────
                decision    = await agent.enhance_decision(symbol, raw_decision, indicators, perception)
                action      = decision.get("action", "HOLD")
                confidence  = decision.get("confidence", 0)
                reasoning   = decision.get("reasoning", "")
                pattern     = decision.get("pattern", "")
                agent_notes = decision.get("agent_notes", "")

                # ── Multi-Timeframe Confluence ──────────────────────────────
                confluence_result = None
                if action in ("BUY", "SELL"):
                    try:
                        from confluence_engine import analyze_confluence
                        confluence_result = await analyze_confluence(symbol, client, min_agreement=2)
                        cf_action = confluence_result.get("action", "HOLD")
                        cf_agree  = confluence_result.get("agreement", 0)
                        cf_score  = confluence_result.get("confluence_score", 0)
                        await self._broadcast(json.dumps({
                            "type": "log",
                            "message": (
                                f"📡 Confluence {symbol}: {cf_action} "
                                f"| {cf_agree}/4 TF agree "
                                f"| {confluence_result.get('reason','')[:60]}"
                            ),
                        }))
                        # If confluence strongly disagrees, reduce confidence
                        if cf_action != action and cf_score >= 3:
                            confidence = max(0, confidence - 15)
                            reasoning += f" [Confluence penalty: {cf_action}]"
                        elif cf_action == action and cf_agree >= 3:
                            confidence = min(99, confidence + 5)
                            reasoning += f" [Confluence bonus: {cf_agree}/4 TF]"
                    except Exception as _cf:
                        print(f"[Confluence] Error: {_cf}")

                # ── Audit Trail: log signal decision ───────────────────────
                try:
                    from audit_trail import AuditTrail
                    AuditTrail.get_instance().log_signal(
                        symbol=symbol, action=action, decided_by="ensemble" if ensemble_result else "gemini",
                        confidence=confidence, indicators=indicators, reason=reasoning,
                        ai_votes=ensemble_result.to_dict() if ensemble_result else {},
                        confluence=confluence_result or {},
                        kelly_pct=0.0, mode=client.mode, strategy=agent.memory._current_strategy,
                    )
                except Exception as _ata:
                    print(f"[Audit] Signal log error: {_ata}")

                sig_msg = (
                    f"📡 {symbol}: {action} ({confidence}%)"
                    + (f" [{pattern}]" if pattern else "")
                    + (f" — {reasoning[:80]}" if reasoning else "")
                )
                await self._broadcast(json.dumps({
                    "type": "signal", "symbol": symbol, "action": action,
                    "confidence": confidence, "message": sig_msg,
                }))

                # ── Spot-only checks ────────────────────────────────────────
                all_trades     = await self.db.get_trades(limit=500)
                open_for_sym   = [t for t in all_trades if t.get("symbol") == symbol and t.get("status") == "open"]
                open_buys      = [t for t in open_for_sym if t.get("side") == "buy"]

                # ── خروج ذكي بالربح: أغلق الصفقة عند الربح حتى لو AI قال HOLD ──────
                if open_buys and action != "SELL":
                    t_check = open_buys[0]
                    entry_p = float(t_check.get("entry_price") or 0)
                    if entry_p > 0 and current_price > 0:
                        profit_pct = (current_price - entry_p) / entry_p * 100
                        macd_h     = indicators.get("macd_histogram", 0)

                        # خروج ذكي: ربح >= 1.5% + RSI مشبع + MACD يتراجع
                        smart_exit = (
                            profit_pct >= 1.5 and rsi >= 65 and macd_h < 0
                        )
                        # حماية الأرباح: ربح >= 3% + أي إشارة هبوط
                        profit_protect = (
                            profit_pct >= 3.0 and (rsi >= 60 or macd_h < 0)
                        )
                        # انعكاس خطير: ربح تحوّل لخسارة وشيكة
                        reversal_risk = (
                            profit_pct >= 0.5 and rsi >= 72 and macd_h < -0.0001
                        )

                        if smart_exit or profit_protect or reversal_risk:
                            exit_reason = (
                                "Smart Exit" if smart_exit else
                                "Profit Protect" if profit_protect else
                                "Reversal Risk"
                            )
                            action     = "SELL"
                            confidence = 80 if profit_protect else 75
                            reasoning  = f"[{exit_reason}] ربح {profit_pct:.1f}% | RSI={rsi:.0f} | MACD={'↓' if macd_h < 0 else '↑'}"
                            await self._broadcast(json.dumps({
                                "type": "signal", "symbol": symbol, "action": "SELL",
                                "confidence": confidence,
                                "message": f"📡 {symbol}: SELL ({exit_reason} | ربح {profit_pct:+.2f}%)",
                            }))

                if action not in ("BUY", "SELL") or confidence < gemini.min_confidence:
                    continue

                # ── SELL: close open BUY ────────────────────────────────────
                if action == "SELL":
                    if not open_buys:
                        continue
                    t2close = open_buys[0]
                    pnl = risk_manager.estimate_pnl(
                        "buy",
                        float(t2close.get("entry_price") or 0),
                        current_price,
                        float(t2close.get("quantity") or 0),
                    )
                    await self.db.update_trade(t2close["id"], {
                        "status": "closed", "exit_price": current_price,
                        "pnl": pnl, "closed_at": datetime.utcnow().isoformat(),
                    })
                    await self.db.recalculate_stats()
                    await self._broadcast(json.dumps({
                        "type": "trade",
                        "message": (
                            f"💰 SELL→close {symbol} @ ${current_price:.4f} | "
                            f"Entry: ${t2close['entry_price']:.4f} | PnL: ${pnl:+.4f}"
                        ),
                    }))
                    closed_trade = {**t2close, "exit_price": current_price, "pnl": pnl, "status": "closed"}

                    # ── Multi-account: replicate SELL close to secondary accounts ─
                    try:
                        from multi_account import MultiAccountManager
                        ma_mgr = MultiAccountManager.get_instance()
                        if ma_mgr.count() > 0:
                            sym_qty = float(t2close.get("quantity") or 0)
                            rep_results = await ma_mgr.replicate_sell(
                                symbol, sym_qty, current_price, self.db,
                                t2close.get("id", ""), pnl,
                            )
                            ok_count = sum(1 for r in rep_results if r.get("status") == "ok")
                            if rep_results:
                                await self._broadcast(json.dumps({
                                    "type": "log",
                                    "message": (
                                        f"🔀 Multi-account SELL: {ok_count}/{len(rep_results)} حساب أغلق {symbol}"
                                    ),
                                }))
                    except Exception as _mae:
                        print(f"[MultiAccount] Replicate SELL error: {_mae}")

                    # ── Auto commentary for SELL-close ────────────────────────
                    try:
                        from trade_commentator import fire_trade_comment
                        event = "close_win" if pnl > 0 else "close_loss"
                        fire_trade_comment(self.db, closed_trade, event, current_price)
                    except Exception as _tc:
                        print(f"[Commentator] SELL hook error: {_tc}")
                    await self._process_closed_trade(closed_trade, agent)
                    trades_this_scan += 1
                    # Re-perceive after SELL (streak may have changed)
                    perception = await agent.perceive()
                    continue

                # ── BUY: skip if already in position ───────────────────────
                if open_for_sym:
                    continue

                if total_balance <= 0:
                    continue

                # ── Skip if emergency halted ───────────────────────────────
                if emergency_halted:
                    try:
                        from audit_trail import AuditTrail
                        AuditTrail.get_instance().log_block(symbol, "emergency halt active", "agent")
                    except Exception:
                        pass
                    await self._broadcast(json.dumps({
                        "type": "log",
                        "message": f"🛑 {symbol}: BUY blocked — emergency halt active",
                    }))
                    continue

                side = "buy"

                # ── Portfolio Correlation Guard ─────────────────────────────
                try:
                    from portfolio_correlation import PortfolioCorrelation
                    pc = PortfolioCorrelation.get_instance()
                    corr_result = pc.check_new_trade(symbol, list(_open_symbols))
                    if not corr_result["allowed"]:
                        await self._broadcast(json.dumps({
                            "type": "log",
                            "message": f"🔗 {symbol}: {corr_result['reason']}",
                        }))
                        try:
                            from audit_trail import AuditTrail
                            AuditTrail.get_instance().log_block(symbol, corr_result["reason"], "correlation")
                        except Exception:
                            pass
                        continue
                    size_factor = corr_result.get("size_factor", 1.0)
                    if size_factor < 1.0:
                        await self._broadcast(json.dumps({
                            "type": "log",
                            "message": f"⚠️ {symbol}: {corr_result['reason']}",
                        }))
                except Exception as _ce:
                    print(f"[Correlation] Guard error: {_ce}")
                    size_factor = 1.0

                # ── ML prediction ──────────────────────────────────────────
                from ml_model import TradingMLModel
                ml       = TradingMLModel.get_instance()
                ml_prob  = ml.predict_win_prob(indicators, side, confidence)
                adj_conf = ml.adjusted_confidence(confidence, ml_prob)

                ml_tag = ""
                if ml_prob is not None:
                    ml_tag = f" | ML:{ml_prob*100:.0f}%"
                    if adj_conf < gemini.min_confidence:
                        await self._broadcast(json.dumps({
                            "type": "signal", "symbol": symbol, "action": "HOLD",
                            "confidence": adj_conf,
                            "message": (
                                f"🔬 ML filtered {symbol}: Gemini={confidence}% → "
                                f"ML={ml_prob*100:.0f}% → adj={adj_conf:.0f}% < {gemini.min_confidence}% — SKIP"
                            ),
                        }))
                        continue
                    confidence = adj_conf

                stop_loss_pct    = float(decision.get("stop_loss_percent",    1.5))
                take_profit_pct  = float(decision.get("take_profit_percent",  3.0))

                # ── Kelly Criterion — Dynamic Position Sizing ───────────────
                kelly_result: dict = {}
                try:
                    from kelly_criterion import KellyPositionSizer
                    _all_trades_for_kelly = await self.db.get_trades(limit=300)
                    _closed_for_kelly = [t for t in _all_trades_for_kelly if t.get("status") == "closed"]
                    kelly_sizer   = KellyPositionSizer(_closed_for_kelly)
                    quantity, kelly_result = kelly_sizer.position_size(
                        symbol, total_balance, current_price, stop_loss_pct, pattern,
                    )
                    quantity *= size_factor   # apply correlation size reduction if any
                    print(f"[Kelly] {symbol}: risk={kelly_result.get('risk_pct',1.5):.2f}% qty={quantity:.6f} | {kelly_result.get('reason','')}")
                    await self._broadcast(json.dumps({
                        "type": "log",
                        "message": (
                            f"📐 Kelly {symbol}: risk={kelly_result.get('risk_pct',1.5):.2f}% "
                            f"({kelly_result.get('source','default')}) "
                            f"qty={quantity:.6f}"
                        ),
                    }))
                except Exception as _ke:
                    print(f"[Kelly] Error: {_ke}")
                    quantity = risk_manager.calculate_position_size(total_balance, current_price, stop_loss_pct)
                    quantity *= size_factor

                if quantity <= 0:
                    continue

                order      = await client.place_spot_order(symbol, side, quantity, price=current_price)
                try:
                    from exchange_router import ExchangeRouter
                    ExchangeRouter.get_instance().record_success(client.exchange_name)
                except Exception:
                    pass
                stop_price = risk_manager.calculate_stop_loss_price(current_price, side, stop_loss_pct)
                tp_price   = risk_manager.calculate_take_profit_price(current_price, side, take_profit_pct)

                from datetime import timezone
                entry_hour = datetime.now(timezone.utc).hour

                trade_data = {
                    "symbol": symbol, "side": side,
                    "entry_price": current_price, "quantity": quantity,
                    "stop_loss_price": stop_price, "take_profit_price": tp_price,
                    "pnl": None, "status": "open",
                    "ai_confidence":       int(confidence),
                    "ai_reasoning":        reasoning,
                    "market_condition":    indicators.get("market_condition", "unknown"),
                    "pattern":             pattern,
                    "rsi_at_entry":        indicators.get("rsi"),
                    "macd_hist_at_entry":  indicators.get("macd_histogram"),
                    "bb_pct_at_entry":     indicators.get("bb_pct"),
                    "volume_at_entry":     indicators.get("volume"),
                    "price_chg_pct_at_entry": indicators.get("price_change_pct"),
                    "entry_hour_utc":      entry_hour,
                    "ml_win_prob":         ml_prob,
                }
                trade = await self.db.create_trade(trade_data)
                trades_this_scan += 1
                await self.db.recalculate_stats()

                # ── Multi-account: replicate BUY to all secondary accounts ────
                try:
                    from multi_account import MultiAccountManager
                    ma_mgr = MultiAccountManager.get_instance()
                    if ma_mgr.count() > 0:
                        rep_results = await ma_mgr.replicate_buy(
                            symbol, quantity, current_price,
                            self.db, trade.get("id", ""),
                            reasoning[:80],
                        )
                        ok_count  = sum(1 for r in rep_results if r.get("status") == "ok")
                        err_count = len(rep_results) - ok_count
                        if rep_results:
                            await self._broadcast(json.dumps({
                                "type": "log",
                                "message": (
                                    f"🔀 Multi-account: {ok_count}/{len(rep_results)} حساب نسّخ {symbol}"
                                    + (f" | {err_count} خطأ" if err_count else "")
                                ),
                            }))
                except Exception as _mae:
                    print(f"[MultiAccount] Replicate BUY error: {_mae}")

                # ── Auto commentary for BUY open ──────────────────────────────
                try:
                    from trade_commentator import fire_trade_comment
                    fire_trade_comment(self.db, trade, "open", current_price)
                except Exception as _tc:
                    print(f"[Commentator] BUY hook error: {_tc}")

                demo_tag = " [PAPER]" if order.get("demo") else " [LIVE]"
                await self._broadcast(json.dumps({
                    "type": "trade",
                    "message": (
                        f"✅ BUY {symbol} @ ${current_price:.4f}{demo_tag} | "
                        f"Qty:{quantity:.6f} | SL:${stop_price:.4f} | TP:${tp_price:.4f}"
                        f"{ml_tag}"
                        + (f" | 🤖 {agent_notes}" if agent_notes else "")
                    ),
                    "trade": trade,
                }))

                # ── Audit Trail: log trade open ────────────────────────────
                try:
                    from audit_trail import AuditTrail
                    AuditTrail.get_instance().log_trade_open(
                        trade, decided_by="ensemble" if ensemble_result else "gemini",
                        kelly_pct=kelly_result.get("risk_pct", 1.5),
                        balance_at=total_balance, exchange=client.exchange_name,
                        strategy=agent.memory._current_strategy,
                        indicators=indicators,
                        ai_votes=ensemble_result.to_dict() if ensemble_result else {},
                        confluence=confluence_result or {},
                    )
                except Exception as _ata:
                    print(f"[Audit] Trade open log error: {_ata}")

                # ── Smart Push Notification: new trade opened ─────────────
                try:
                    from push_manager import PushManager
                    _push = PushManager.get_instance()
                    if _push.token_count > 0:
                        await _push.notify_trade_open(trade, indicators, kelly_result)
                except Exception as _pe:
                    print(f"[Push] trade-open error: {_pe}")
                # ─────────────────────────────────────────────────────────

            except IslamicViolationError as e:
                await self._broadcast(json.dumps({
                    "type": "error",
                    "message": f"🚫 HALAL VIOLATION BLOCKED: {str(e)}",
                }))
            except Exception as e:
                await self._broadcast(json.dumps({
                    "type": "error",
                    "message": f"❌ {symbol}: {str(e)[:120]}",
                }))

        # ── 4. Scan summary ────────────────────────────────────────────────
        summary = (
            f"✅ Scan #{scan_num} done — {trades_this_scan} trade(s)"
            f" | strategy:{agent.memory._current_strategy}"
            f" | WR:{perception.get('win_rate',0):.0f}%"
        )
        if emergency_halted:
            summary += " | 🛑 EMERGENCY HALT ACTIVE"
        print(f"[Scheduler] {summary}")
        await self._broadcast(json.dumps({"type": "log", "message": summary}))
