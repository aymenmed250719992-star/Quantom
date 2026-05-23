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
        self._running = True

    def stop(self) -> None:
        if not self._running:
            return
        try:
            self.scheduler.remove_job("market_scan")
        except Exception:
            pass
        self._running = False

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

                    # ── Push Notification: trade close ────────────────────────
                    try:
                        from push_manager import PushManager
                        _push = PushManager.get_instance()
                        if _push.token_count > 0:
                            sym_short = symbol.replace("/USDT", "")
                            if hit_tp:
                                await _push.send(
                                    f"✅ ربح — {sym_short}",
                                    f"PnL: ${pnl:+.4f} USDT | السعر: ${current_price:.4f}",
                                    {"type": "trade_close", "result": "win", "symbol": symbol},
                                )
                            else:
                                await _push.send(
                                    f"🔴 Stop Loss — {sym_short}",
                                    f"PnL: ${pnl:+.4f} USDT | السعر: ${current_price:.4f}",
                                    {"type": "trade_close", "result": "loss", "symbol": symbol},
                                )
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
                    await _push.send(
                        "🛑 إيقاف طارئ!",
                        "5 خسائر متتالية — البوت موقف مؤقتاً للمراجعة العميقة",
                        {"type": "emergency"},
                    )
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
                    await _push.send(
                        "⚠️ تنبيه انخفاض",
                        "3 خسائر متتالية — تم رفع عتبة الثقة تلقائياً",
                        {"type": "drawdown"},
                    )
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
                    await _push.send(
                        "🏆 سلسلة فوز رائعة!",
                        "5 صفقات رابحة متتالية — استراتيجيتك تعمل بشكل ممتاز",
                        {"type": "win_streak"},
                    )
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

        # ── 6. ML retraining ───────────────────────────────────────────────
        try:
            from ml_model import TradingMLModel
            ml = TradingMLModel.get_instance()
            if ml.should_retrain():
                closed_for_ml = await self.db.get_closed_trades_for_ml()
                trained = ml.train(closed_for_ml)
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

        # ── 3. Scan each symbol for signals ───────────────────────────────
        for symbol in symbols:
            try:
                ohlcv = await client.get_ohlcv(symbol, "15m", 100)
                if not ohlcv or len(ohlcv) < 30:
                    await self._broadcast(json.dumps({
                        "type": "log",
                        "message": f"⚠️ {symbol}: insufficient OHLCV ({len(ohlcv)} candles)",
                    }))
                    continue

                indicators = get_market_indicators(ohlcv)
                if "error" in indicators:
                    continue

                current_price = indicators.get("current_price", 0)

                rsi    = indicators.get("rsi", 50)
                bb_pct = indicators.get("bb_pct", 0.5)

                # ── Pre-filter + startup grace: skip AI unless there's a real signal ──
                has_signal = (
                    rsi <= 40 or rsi >= 60                   # RSI oversold/overbought (relaxed)
                    or bb_pct <= 0.20 or bb_pct >= 0.80      # Price near BB band edge (relaxed)
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

                # Throttle Gemini calls — 8s gap keeps us well under 15 req/min free tier
                await asyncio.sleep(8)
                raw_decision = await gemini.analyze_market(symbol, ohlcv, indicators, lessons)

                # ── Agent layer ────────────────────────────────────────────
                decision    = await agent.enhance_decision(symbol, raw_decision, indicators, perception)
                action      = decision.get("action", "HOLD")
                confidence  = decision.get("confidence", 0)
                reasoning   = decision.get("reasoning", "")
                pattern     = decision.get("pattern", "")
                agent_notes = decision.get("agent_notes", "")

                sig_msg = (
                    f"📡 {symbol}: {action} ({confidence}%)"
                    + (f" [{pattern}]" if pattern else "")
                    + (f" — {reasoning[:80]}" if reasoning else "")
                )
                await self._broadcast(json.dumps({
                    "type": "signal", "symbol": symbol, "action": action,
                    "confidence": confidence, "message": sig_msg,
                }))

                if action not in ("BUY", "SELL") or confidence < gemini.min_confidence:
                    continue

                # ── Spot-only checks ────────────────────────────────────────
                all_trades     = await self.db.get_trades(limit=500)
                open_for_sym   = [t for t in all_trades if t.get("symbol") == symbol and t.get("status") == "open"]

                # ── SELL: close open BUY ────────────────────────────────────
                if action == "SELL":
                    open_buys = [t for t in open_for_sym if t.get("side") == "buy"]
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
                    await self._broadcast(json.dumps({
                        "type": "log",
                        "message": f"🛑 {symbol}: BUY blocked — emergency halt active",
                    }))
                    continue

                side = "buy"

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
                quantity         = risk_manager.calculate_position_size(total_balance, current_price, stop_loss_pct)

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

                # ── Push Notification: new trade opened ───────────────────
                try:
                    from push_manager import PushManager
                    _push = PushManager.get_instance()
                    if _push.token_count > 0:
                        sym_short = symbol.replace("/USDT", "")
                        conf_pct  = int(round(confidence * 100)) if confidence <= 1 else int(confidence)
                        mode_tag  = "ورقي" if order.get("demo") else "حقيقي"
                        await _push.send(
                            f"📊 إشارة شراء — {sym_short}",
                            f"ثقة: {conf_pct}% | SL: ${stop_price:.4f} | TP: ${tp_price:.4f} [{mode_tag}]",
                            {"type": "trade_open", "symbol": symbol, "confidence": conf_pct},
                        )
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
