"""
TradingAgent — True Autonomous Agent Core v2.0

PLAN → ACT → OBSERVE → REFLECT → ADAPT → REMEMBER

استراتيجية التعلم المحسّنة:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
بدلاً من "كل 5 صفقات" (استراتيجية ضعيفة لا تعرف الفرق بين نجاح وفشل):

يستخدم الـ Agent الآن نظام تشغيل متعدد المحفزات:

1. DRAWDOWN ALERT   — تأمل فوري عند 3 خسائر متتالية
2. WIN STREAK       — تعديل استراتيجي عند 5 انتصارات متتالية
3. TIME RHYTHM      — تأمل كل 30 دقيقة بغض النظر
4. PERFORMANCE DIP  — تأمل إذا انخفض win rate أكثر من 10% فجأة
5. DEEP REVIEW      — مراجعة استراتيجية شاملة كل 10 صفقات مغلقة
6. EMERGENCY HALT   — إيقاف اختياري عند 5 خسائر متتالية (حماية رأس المال)

هذا النظام يُتيح للـ Agent التكيّف مع السوق بدلاً من انتظار عدد ثابت.
"""

import json
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Optional

AGENT_STATE_FILE = os.path.join(os.path.dirname(__file__), ".agent_state.json")


class AgentMemory:
    """
    Long-term agent memory — persisted to DB.
    Stores: lessons, patterns, strategy rules, performance hypotheses.
    """

    def __init__(self, db: Any) -> None:
        self.db = db
        self._session_thoughts: list[str] = []
        self._session_plans: list[dict] = []
        self._strategy_overrides: dict[str, Any] = {}
        self._pattern_scores: dict[str, dict] = {}
        self._goal: str = "Achieve consistent halal returns with >65% win rate"
        self._current_strategy: str = "mean_reversion"
        self._strategy_confidence: float = 1.0

        # ── Timing & smart triggers ───────────────────────────────────────────
        self._last_reflection_time: float = 0.0
        self._reflection_interval: float = 900.0    # 15 min — faster evolution
        self._last_performance_check: float = 0.0
        self._performance_win_rate_baseline: float = 0.0

        # ── Streak tracking ────────────────────────────────────────────────
        self._consecutive_losses: int = 0
        self._consecutive_wins: int = 0
        self._last_3_results: list[bool] = []       # True=win, False=loss
        self._emergency_halted: bool = False

        # ── Load persisted state so nothing is forgotten ───────────────────
        self._load_state()

    # ── Persistence: never forget ─────────────────────────────────────────────

    def _save_state(self) -> None:
        """Persist critical state to disk — non-blocking via background thread."""
        import threading
        state = {
            "pattern_scores":       self._pattern_scores,
            "current_strategy":     self._current_strategy,
            "strategy_confidence":  self._strategy_confidence,
            "goal":                 self._goal,
            "strategy_overrides":   self._strategy_overrides,
            "consecutive_losses":   self._consecutive_losses,
            "consecutive_wins":     self._consecutive_wins,
            "emergency_halted":     self._emergency_halted,
            "session_thoughts":     self._session_thoughts[-50:],
            "session_plans":        self._session_plans[-20:],
            "saved_at":             time.time(),
        }

        def _write() -> None:
            try:
                import tempfile, os
                tmp = AGENT_STATE_FILE + ".tmp"
                with open(tmp, "w") as f:
                    json.dump(state, f, indent=2)
                os.replace(tmp, AGENT_STATE_FILE)   # atomic rename — no partial writes
            except Exception as e:
                print(f"[Memory] save error: {e}")

        threading.Thread(target=_write, daemon=True).start()

    def _load_state(self) -> None:
        """Restore persisted state from disk on startup."""
        try:
            if not os.path.exists(AGENT_STATE_FILE):
                return
            data = json.loads(open(AGENT_STATE_FILE).read())
            age = time.time() - data.get("saved_at", 0)
            if age > 86400 * 30:   # Discard if older than 30 days
                return
            self._pattern_scores       = data.get("pattern_scores", {})
            self._current_strategy     = data.get("current_strategy", "mean_reversion")
            self._strategy_confidence  = data.get("strategy_confidence", 1.0)
            self._goal                 = data.get("goal", self._goal)
            self._strategy_overrides   = data.get("strategy_overrides", {})
            self._consecutive_losses   = data.get("consecutive_losses", 0)
            self._consecutive_wins     = data.get("consecutive_wins", 0)
            self._emergency_halted     = data.get("emergency_halted", False)
            self._session_thoughts     = data.get("session_thoughts", [])
            self._session_plans        = data.get("session_plans", [])
            n_patterns = len(self._pattern_scores)
            n_thoughts = len(self._session_thoughts)
            print(f"[Memory] ♻️  Restored: {n_patterns} pattern(s) | strategy={self._current_strategy} | streak: {self._consecutive_wins}W/{self._consecutive_losses}L | {n_thoughts} thoughts")
        except Exception as e:
            print(f"[Memory] load error: {e}")

    # ── Thoughts ──────────────────────────────────────────────────────────────

    def add_thought(self, thought: str) -> None:
        ts = datetime.utcnow().strftime("%H:%M:%S")
        self._session_thoughts.append(f"[{ts}] {thought}")
        if len(self._session_thoughts) > 60:
            self._session_thoughts = self._session_thoughts[-60:]

    def add_plan(self, plan: dict) -> None:
        plan["created_at"] = datetime.utcnow().isoformat()
        self._session_plans.append(plan)
        if len(self._session_plans) > 20:
            self._session_plans = self._session_plans[-20:]

    # ── Pattern tracking ──────────────────────────────────────────────────────

    def update_pattern_score(self, pattern: str, won: bool) -> None:
        if not pattern:
            return
        if pattern not in self._pattern_scores:
            self._pattern_scores[pattern] = {"wins": 0, "losses": 0}
        if won:
            self._pattern_scores[pattern]["wins"] += 1
        else:
            self._pattern_scores[pattern]["losses"] += 1

    def get_best_patterns(self, top_n: int = 5) -> list[dict]:
        results = []
        for pattern, scores in self._pattern_scores.items():
            total = scores["wins"] + scores["losses"]
            if total < 2:
                continue
            win_rate = scores["wins"] / total * 100
            results.append({"pattern": pattern, "win_rate": win_rate, "total": total})
        results.sort(key=lambda x: (x["win_rate"], x["total"]), reverse=True)
        return results[:top_n]

    # ── Strategy ──────────────────────────────────────────────────────────────

    def set_strategy(self, strategy: str, confidence: float = 1.0) -> None:
        old = self._current_strategy
        self._current_strategy = strategy
        self._strategy_confidence = confidence
        if old != strategy:
            self.add_thought(f"🔄 Strategy shifted: {old} → {strategy} ({confidence:.0%} conf)")
        self._save_state()

    # ── Smart trigger system ───────────────────────────────────────────────────

    def record_trade_result(self, won: bool) -> dict:
        """
        Record trade result and evaluate which triggers fire.
        Returns a dict of active triggers.
        """
        self._consecutive_losses = (self._consecutive_losses + 1) if not won else 0
        self._consecutive_wins  = (self._consecutive_wins + 1) if won else 0
        self._last_3_results.append(won)
        if len(self._last_3_results) > 10:
            self._last_3_results = self._last_3_results[-10:]

        triggers: dict[str, bool] = {
            "drawdown_alert":    self._consecutive_losses >= 3,
            "emergency_halt":    self._consecutive_losses >= 5,
            "win_streak_review": self._consecutive_wins >= 5,
            "time_rhythm":       (time.time() - self._last_reflection_time) > self._reflection_interval,
        }

        if triggers["drawdown_alert"]:
            self.add_thought(f"🚨 DRAWDOWN ALERT: {self._consecutive_losses} consecutive losses — reflecting NOW")
        if triggers["win_streak_review"]:
            self.add_thought(f"🏆 WIN STREAK: {self._consecutive_wins} consecutive wins — locking in strategy")
        if triggers["emergency_halt"]:
            self._emergency_halted = True
            self.add_thought(f"🛑 EMERGENCY: {self._consecutive_losses} consecutive losses — requesting halt")

        self._save_state()
        return triggers

    def should_reflect_time(self) -> bool:
        return (time.time() - self._last_reflection_time) > self._reflection_interval

    def mark_reflected(self) -> None:
        self._last_reflection_time = time.time()

    def reset_emergency(self) -> None:
        self._emergency_halted = False
        self._consecutive_losses = 0
        self.add_thought("✅ Emergency reset — ready to resume")
        self._save_state()

    # ── Long-term memory ──────────────────────────────────────────────────────

    def get_context_summary(self) -> dict:
        return {
            "goal": self._goal,
            "current_strategy": self._current_strategy,
            "strategy_confidence": self._strategy_confidence,
            "best_patterns": self.get_best_patterns(3),
            "recent_thoughts": self._session_thoughts[-5:],
            "strategy_overrides": self._strategy_overrides,
            "consecutive_losses": self._consecutive_losses,
            "consecutive_wins": self._consecutive_wins,
            "emergency_halted": self._emergency_halted,
        }

    async def get_long_term_lessons(self, limit: int = 15) -> list[dict]:
        try:
            return await self.db.get_recent_lessons(limit=limit)
        except Exception:
            return []

    async def save_strategic_insight(self, insight: str, source: str = "reflection") -> None:
        try:
            await self.db.save_lesson({
                "lesson": f"[STRATEGIC INSIGHT] {insight}",
                "symbol": "PORTFOLIO",
                "market_condition": "strategic",
                "outcome": "win",
                "created_at": datetime.utcnow().isoformat(),
            })
            self.add_thought(f"💾 Insight saved: {insight[:80]}")
        except Exception as e:
            print(f"[Agent] save_insight error: {e}")


class TradingAgent:
    """
    The autonomous agent brain.
    Wraps GeminiAgent + ML + Rules into a unified agentic system.
    """

    _instance: Optional["TradingAgent"] = None

    @classmethod
    def get_instance(cls, db: Any = None) -> "TradingAgent":
        if cls._instance is None:
            if db is None:
                raise RuntimeError("TradingAgent requires db on first init")
            cls._instance = cls(db)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def __init__(self, db: Any) -> None:
        self.db = db
        self.memory = AgentMemory(db)
        self._broadcast_fn: Optional[Callable] = None
        self._scan_count = 0
        self._trades_since_deep_review = 0
        self._performance_cache: dict = {}
        self._last_win_rate_snapshot: float = 0.0
        print("[Agent] TradingAgent v2.0 initialized — Smart Trigger System active")

    def set_broadcast_fn(self, fn: Callable) -> None:
        self._broadcast_fn = fn

    async def _broadcast(self, msg_type: str, message: str) -> None:
        if self._broadcast_fn:
            try:
                await self._broadcast_fn(json.dumps({"type": msg_type, "message": message}))
            except Exception:
                pass

    # ── PERCEIVE ──────────────────────────────────────────────────────────────

    async def perceive(self) -> dict:
        """Gather current world state: portfolio, trades, lessons, trends."""
        try:
            trades  = await self.db.get_trades(limit=200)
            lessons = await self.db.get_recent_lessons(limit=20)
            status  = await self.db.get_bot_status()

            closed     = [t for t in trades if t.get("status") == "closed"]
            open_trades = [t for t in trades if t.get("status") == "open"]

            wins      = [t for t in closed if (t.get("pnl") or 0) > 0]
            losses    = [t for t in closed if (t.get("pnl") or 0) <= 0]
            total_pnl = sum(float(t.get("pnl") or 0) for t in closed)
            win_rate  = len(wins) / len(closed) * 100 if closed else 0.0

            recent_10      = closed[:10]
            recent_wins    = sum(1 for t in recent_10 if (t.get("pnl") or 0) > 0)
            recent_win_rate = recent_wins / len(recent_10) * 100 if recent_10 else 0.0

            performance_trend = (
                "improving" if recent_win_rate > win_rate + 5
                else "declining" if recent_win_rate < win_rate - 5
                else "stable"
            )

            # ── Performance dip detection ──────────────────────────────────
            perf_dip_trigger = False
            if self._last_win_rate_snapshot > 0 and win_rate > 0:
                dip = self._last_win_rate_snapshot - win_rate
                if dip >= 10:
                    perf_dip_trigger = True
                    self.memory.add_thought(
                        f"📉 Performance dip detected: {self._last_win_rate_snapshot:.0f}% → {win_rate:.0f}% (−{dip:.0f}%)"
                    )
            if len(closed) >= 5:
                self._last_win_rate_snapshot = win_rate

            perception = {
                "total_closed":     len(closed),
                "total_open":       len(open_trades),
                "open_trades":      open_trades,
                "total_pnl":        total_pnl,
                "win_rate":         round(win_rate, 2),
                "recent_win_rate":  round(recent_win_rate, 2),
                "performance_trend": performance_trend,
                "recent_lessons":   lessons[:10],
                "win_lessons":      [l for l in lessons if l.get("outcome") == "win"][:5],
                "loss_lessons":     [l for l in lessons if l.get("outcome") == "loss"][:5],
                "is_running":       status.get("is_running", False),
                "mode":             status.get("mode", "demo"),
                "memory_context":   self.memory.get_context_summary(),
                "best_patterns":    self.memory.get_best_patterns(3),
                "consecutive_losses": self.memory._consecutive_losses,
                "consecutive_wins":   self.memory._consecutive_wins,
                "emergency_halted":   self.memory._emergency_halted,
                "perf_dip_trigger":   perf_dip_trigger,
                "timestamp":          datetime.utcnow().isoformat(),
            }

            self._performance_cache = perception
            return perception

        except Exception as e:
            print(f"[Agent] perceive() error: {e}")
            return {}

    # ── THINK ─────────────────────────────────────────────────────────────────

    async def think(self, perception: dict, market_data: dict) -> dict:
        """
        Plan the current scan based on perception.
        Returns a plan dict with active triggers and recommended actions.
        """
        win_rate  = perception.get("win_rate", 0)
        trend     = perception.get("performance_trend", "stable")
        cons_loss = perception.get("consecutive_losses", 0)
        cons_win  = perception.get("consecutive_wins", 0)

        scan_num = self._scan_count
        thought = (
            f"Scan #{scan_num} | WR:{win_rate:.0f}% ({trend}) | "
            f"Streak: {'🔴×'+str(cons_loss) if cons_loss > 0 else '🟢×'+str(cons_win)}"
        )
        self.memory.add_thought(thought)

        best_patterns = perception.get("best_patterns", [])
        plan: dict = {
            "scan_number":        scan_num,
            "strategy":           self.memory._current_strategy,
            "win_rate":           win_rate,
            "trend":              trend,
            "patterns_to_favor":  [p["pattern"] for p in best_patterns if p["win_rate"] > 60],
            "market_symbols":     list(market_data.keys()),
            "consecutive_losses": cons_loss,
            "consecutive_wins":   cons_win,
            "emergency_halted":   perception.get("emergency_halted", False),
            "needs_reflection":   self.memory.should_reflect_time(),
            "needs_deep_review":  (self._trades_since_deep_review >= 10),
            "perf_dip_trigger":   perception.get("perf_dip_trigger", False),
        }

        if cons_loss >= 3:
            plan["needs_reflection"] = True
            plan["caution_mode"] = True
            self.memory.add_thought(f"⚠️ Caution mode: {cons_loss} consecutive losses")

        if win_rate < 45 and perception.get("total_closed", 0) >= 10:
            plan["warning"] = "WIN_RATE_CRITICAL"
            self.memory.add_thought(f"🚨 Win rate critical ({win_rate:.0f}%) — tightening filters")

        self.memory.add_plan(plan)
        return plan

    # ── DEEP REFLECT ──────────────────────────────────────────────────────────

    async def deep_reflect(self, perception: dict, trigger: str = "time") -> str:
        """
        Periodic deep reflection using Gemini.
        Trigger can be: time | drawdown | win_streak | perf_dip | manual
        """
        from gemini_agent import GeminiAgent
        agent = GeminiAgent.get_instance()

        lessons   = perception.get("recent_lessons", [])
        win_rate  = perception.get("win_rate", 0)
        trend     = perception.get("performance_trend", "stable")
        best_patt = self.memory.get_best_patterns(5)
        cons_loss = perception.get("consecutive_losses", 0)
        cons_win  = perception.get("consecutive_wins", 0)

        trigger_context = {
            "time":        "periodic rhythm reflection",
            "drawdown":    f"URGENT: {cons_loss} consecutive losses — emergency analysis",
            "win_streak":  f"OPPORTUNITY: {cons_win} consecutive wins — lock in strategy",
            "perf_dip":    "ALERT: Performance drop detected — root cause analysis",
            "manual":      "user-triggered manual reflection",
        }.get(trigger, trigger)

        lessons_text = "\n".join(f"  • {l.get('lesson', '')[:120]}" for l in lessons[:15])
        patterns_text = "\n".join(
            f"  • {p['pattern']}: {p['win_rate']:.0f}% WR ({p['total']} trades)"
            for p in best_patt
        ) if best_patt else "  • No pattern data yet"

        urgency = "URGENT - " if trigger == "drawdown" else ""

        prompt = f"""You are a self-improving Islamic trading AI agent doing a {urgency}strategic reflection.

TRIGGER: {trigger_context}

CURRENT PERFORMANCE:
• Win rate: {win_rate:.1f}% | Trend: {trend}
• Consecutive losses: {cons_loss} | Consecutive wins: {cons_win}
• Total closed: {perception.get('total_closed', 0)}
• Total PNL: ${perception.get('total_pnl', 0):.4f}

RECENT LESSONS FROM TRADES:
{lessons_text if lessons_text else "  • None yet"}

PATTERN PERFORMANCE:
{patterns_text}

CURRENT STATE:
• Strategy: {self.memory._current_strategy}
• Goal: {self.memory._goal}

{"⚠️ DRAWDOWN MODE: Analyze what is causing consecutive losses and propose immediate changes." if trigger == "drawdown" else ""}

Provide a STRATEGIC REFLECTION in JSON:
{{"strategy_recommendation":"mean_reversion|trend_following|momentum_breakout|divergence","strategy_confidence":0.0-1.0,"key_insight":"1 sentence max","rule_change":"1 specific actionable rule","avoid_conditions":"specific market conditions to avoid now","confidence_adjustment":+0-10 or -0-10,"outlook":"bullish|bearish|neutral|uncertain"}}"""

        try:
            slot = agent._get_slot()
            if slot is None:
                return ""

            text   = agent._call_slot(slot, prompt, temperature=0.3)
            result = agent._parse_json_decision(text, "PORTFOLIO")

            if result:
                new_strategy = result.get("strategy_recommendation", self.memory._current_strategy)
                confidence   = float(result.get("strategy_confidence", 0.7))
                insight      = result.get("key_insight", "")
                rule_change  = result.get("rule_change", "")
                avoid        = result.get("avoid_conditions", "")
                conf_adj     = float(result.get("confidence_adjustment", 0))

                self.memory.set_strategy(new_strategy, confidence)

                if insight:
                    await self.memory.save_strategic_insight(f"[{trigger.upper()}] {insight}", source=trigger)

                if rule_change:
                    self.memory._strategy_overrides["active_rule"] = rule_change
                if avoid:
                    self.memory._strategy_overrides["avoid"] = avoid
                if conf_adj != 0:
                    self.memory._strategy_overrides["conf_adjustment"] = conf_adj

                self.memory.mark_reflected()

                emoji = {"drawdown": "🚨", "win_streak": "🏆", "perf_dip": "📉", "time": "🧠"}.get(trigger, "🤔")
                reflection_msg = (
                    f"{emoji} [{trigger.upper()}] Strategy={new_strategy} ({confidence:.0%}) | "
                    + (f"⚠️ Avoid: {avoid[:60]}" if avoid else insight[:80])
                )
                await self._broadcast("agent", reflection_msg)
                return reflection_msg

        except Exception as e:
            print(f"[Agent] deep_reflect error: {e}")

        return ""

    # ── ENHANCE DECISION ──────────────────────────────────────────────────────

    async def enhance_decision(
        self,
        symbol: str,
        gemini_decision: dict,
        indicators: dict,
        perception: dict,
    ) -> dict:
        """
        Apply learned rules, pattern scoring, and strategic filters
        on top of Gemini's raw signal.
        """
        action     = gemini_decision.get("action", "HOLD")
        confidence = float(gemini_decision.get("confidence", 0))
        pattern    = gemini_decision.get("pattern", "")
        reasoning  = gemini_decision.get("reasoning", "")

        agent_notes: list[str] = []

        if action not in ("BUY", "SELL"):
            return dict(gemini_decision)

        # ── Emergency: if halted, block ALL new buys ───────────────────────
        if self.memory._emergency_halted and action == "BUY":
            enhanced = dict(gemini_decision)
            enhanced["action"] = "HOLD"
            enhanced["confidence"] = 0
            enhanced["agent_notes"] = "EMERGENCY_HALT: consecutive losses protection"
            enhanced["reasoning"] = "🛑 Agent blocked: emergency halt active (5 consecutive losses)"
            return enhanced

        # ── Caution mode: consecutive losses ─────────────────────────────
        cons_loss = self.memory._consecutive_losses
        if cons_loss >= 3:
            penalty = min(25, cons_loss * 5)
            confidence = max(0, confidence - penalty)
            agent_notes.append(f"caution−{penalty}% ({cons_loss}× loss streak)")

        # ── Win streak: slightly boost confidence ─────────────────────────
        cons_win = self.memory._consecutive_wins
        if cons_win >= 3:
            boost = min(5, cons_win)
            confidence = min(99, confidence + boost)
            agent_notes.append(f"streak+{boost}% ({cons_win}× win)")

        # ── Pattern scoring from memory ────────────────────────────────────
        if pattern and pattern in self.memory._pattern_scores:
            scores = self.memory._pattern_scores[pattern]
            total  = scores["wins"] + scores["losses"]
            if total >= 3:
                pattern_wr = scores["wins"] / total * 100
                if pattern_wr >= 65:
                    boost = min(10, (pattern_wr - 65) * 0.5)
                    confidence = min(99, confidence + boost)
                    agent_notes.append(f"pattern+{boost:.0f}% ({pattern}:{pattern_wr:.0f}%WR)")
                elif pattern_wr < 40:
                    confidence = max(0, confidence - 10)
                    agent_notes.append(f"pattern−10% ({pattern}:{pattern_wr:.0f}%WR)")

        # ── Strategic avoid filter ─────────────────────────────────────────
        avoid = self.memory._strategy_overrides.get("avoid", "")
        current_condition = indicators.get("market_condition", "")
        if avoid and current_condition and current_condition.lower() in avoid.lower():
            confidence = max(0, confidence - 20)
            agent_notes.append(f"avoid−20% ({current_condition})")

        # ── Agent-level confidence adjustment from last reflection ─────────
        conf_adj = float(self.memory._strategy_overrides.get("conf_adjustment", 0))
        if conf_adj != 0:
            confidence = max(0, min(99, confidence + conf_adj))
            agent_notes.append(f"reflect_adj{conf_adj:+.0f}%")

        # ── Strategy-specific filter ───────────────────────────────────────
        current_strategy = self.memory._current_strategy
        rsi    = indicators.get("rsi", 50)
        macd_h = indicators.get("macd_histogram", 0)
        bb_pct = indicators.get("bb_pct", 0.5)

        if current_strategy == "mean_reversion":
            if action == "BUY" and rsi < 35 and bb_pct < 0.2:
                confidence = min(99, confidence + 5)
                agent_notes.append("strat+5% (mean_rev✓)")
            elif action == "BUY" and rsi > 60:
                confidence = max(0, confidence - 8)
                agent_notes.append("strat−8% (not_oversold)")

        elif current_strategy == "trend_following":
            if action == "BUY" and macd_h > 0 and rsi > 45:
                confidence = min(99, confidence + 5)
                agent_notes.append("strat+5% (trend✓)")
            elif action == "BUY" and macd_h < 0:
                confidence = max(0, confidence - 5)
                agent_notes.append("strat−5% (counter_trend)")

        elif current_strategy == "momentum_breakout":
            vol     = indicators.get("volume", 0)
            vol_avg = indicators.get("volume_avg", vol or 1)
            if vol > vol_avg * 1.5:
                confidence = min(99, confidence + 8)
                agent_notes.append("strat+8% (vol_breakout✓)")

        elif current_strategy == "divergence":
            if indicators.get("rsi_divergence"):
                confidence = min(99, confidence + 10)
                agent_notes.append("strat+10% (divergence✓)")

        # ── Overall win rate health ────────────────────────────────────────
        win_rate = perception.get("win_rate", 0)
        total_closed = perception.get("total_closed", 0)
        if win_rate < 45 and total_closed >= 10:
            confidence = max(0, confidence - 8)
            agent_notes.append("wr_risk−8%")
        elif win_rate > 72 and total_closed >= 10:
            confidence = min(99, confidence + 3)
            agent_notes.append("wr_boost+3%")

        enhanced = dict(gemini_decision)
        enhanced["confidence"]   = int(confidence)
        enhanced["agent_notes"]  = " | ".join(agent_notes)
        if agent_notes:
            enhanced["reasoning"] = f"[🤖 {', '.join(agent_notes[:3])}] {reasoning}"

        return enhanced

    # ── POST-TRADE LEARN ──────────────────────────────────────────────────────

    async def post_trade_learn(self, trade: dict) -> dict:
        """
        Called after every trade closes.
        Updates pattern scores, streak counters, and fires smart triggers.
        Returns the triggered events dict.
        """
        pnl     = float(trade.get("pnl") or 0)
        pattern = trade.get("pattern", "")
        won     = pnl > 0

        # Update pattern memory
        if pattern:
            self.memory.update_pattern_score(pattern, won)

        # Update streak counters and get triggered events
        triggers = self.memory.record_trade_result(won)
        self._trades_since_deep_review += 1

        outcome_emoji = "✅" if won else "❌"
        self.memory.add_thought(
            f"{outcome_emoji} Closed: {trade.get('symbol')} {trade.get('side','').upper()} "
            f"PNL=${pnl:+.4f} | pattern={pattern or 'none'} | "
            f"streak={'🔴×'+str(self.memory._consecutive_losses) if not won else '🟢×'+str(self.memory._consecutive_wins)}"
        )

        await self._broadcast(
            "agent",
            f"🤖 Learned: {trade.get('symbol')} {outcome_emoji} PNL=${pnl:+.4f} | "
            f"Streak: {'🔴×'+str(self.memory._consecutive_losses) if not won else '🟢×'+str(self.memory._consecutive_wins)} | "
            f"Patterns: {len(self.memory._pattern_scores)}"
        )

        return triggers

    # ── SCAN MANAGEMENT ───────────────────────────────────────────────────────

    def increment_scan(self) -> int:
        self._scan_count += 1
        return self._scan_count

    def get_scan_count(self) -> int:
        return self._scan_count

    def reset_deep_review_counter(self) -> None:
        self._trades_since_deep_review = 0

    # ── STATUS ────────────────────────────────────────────────────────────────

    def status_dict(self) -> dict:
        return {
            "scan_count":            self._scan_count,
            "goal":                  self.memory._goal,
            "current_strategy":      self.memory._current_strategy,
            "strategy_confidence":   round(self.memory._strategy_confidence, 2),
            "patterns_tracked":      len(self.memory._pattern_scores),
            "best_patterns":         self.memory.get_best_patterns(5),
            "recent_thoughts":       self.memory._session_thoughts[-15:],
            "strategy_overrides":    self.memory._strategy_overrides,
            "trades_since_review":   self._trades_since_deep_review,
            "consecutive_losses":    self.memory._consecutive_losses,
            "consecutive_wins":      self.memory._consecutive_wins,
            "emergency_halted":      self.memory._emergency_halted,
            "smart_triggers": {
                "drawdown_threshold":    3,
                "emergency_threshold":   5,
                "win_streak_threshold":  5,
                "deep_review_threshold": 10,
                "time_rhythm_minutes":   30,
            },
        }
