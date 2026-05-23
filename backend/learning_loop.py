"""
LearningLoop — Deep trade reflection with Gemini.

After every trade closes, the agent:
1. Reflects on WHY it won or lost (Gemini analysis)
2. Extracts a specific actionable lesson
3. Updates the agent's pattern memory
4. Triggers strategic review every 5 trades
"""

import json
import os
from datetime import datetime
from typing import Any, Callable, Optional

from dotenv import load_dotenv

load_dotenv()


class LearningLoop:
    def __init__(self, db: Any):
        self.db = db
        # Uses AIAgent pool (multi-provider, shared quota) instead of direct Gemini
        # This prevents quota double-spend and benefits from fallback chain

    async def reflect_on_trade(
        self,
        trade: dict,
        broadcast_fn: Optional[Callable] = None,
    ) -> str:
        symbol = trade.get("symbol", "UNKNOWN")
        entry_price = float(trade.get("entry_price") or 0)
        exit_price = float(trade.get("exit_price") or 0)
        pnl = float(trade.get("pnl") or 0)
        side = trade.get("side", "buy")
        ai_confidence = trade.get("ai_confidence", 0)
        ai_reasoning = trade.get("ai_reasoning", "")
        market_condition = trade.get("market_condition", "unknown")
        pattern = trade.get("pattern", "")
        rsi = trade.get("rsi_at_entry")
        bb_pct = trade.get("bb_pct_at_entry")
        macd_h = trade.get("macd_hist_at_entry")

        result = "WIN" if pnl > 0 else "LOSS"
        pnl_pct = 0.0
        if entry_price > 0:
            raw_pct = ((exit_price - entry_price) / entry_price) * 100
            pnl_pct = raw_pct if side == "buy" else -raw_pct

        lesson_text = await self._generate_lesson(
            symbol=symbol, side=side, result=result,
            entry_price=entry_price, exit_price=exit_price,
            pnl=pnl, pnl_pct=pnl_pct, ai_confidence=ai_confidence,
            ai_reasoning=ai_reasoning, market_condition=market_condition,
            pattern=pattern, rsi=rsi, bb_pct=bb_pct, macd_h=macd_h,
        )

        lesson_data = {
            "lesson": lesson_text,
            "symbol": symbol,
            "market_condition": market_condition,
            "pattern": pattern,
            "outcome": "win" if result == "WIN" else "loss",
            "confidence_at_trade": ai_confidence,
            "pnl_at_close": pnl,
            "created_at": datetime.utcnow().isoformat(),
        }
        await self.db.save_lesson(lesson_data)

        try:
            from agent_core import TradingAgent
            agent = TradingAgent.get_instance()
            await agent.post_trade_learn(trade)
        except Exception:
            pass

        if broadcast_fn:
            await broadcast_fn(json.dumps({
                "type": "lesson",
                "message": f"💡 Lesson: {lesson_text[:150]}{'...' if len(lesson_text) > 150 else ''}",
            }))

        return lesson_text

    async def _generate_lesson(self, **kwargs) -> str:
        symbol = kwargs["symbol"]
        side = kwargs["side"]
        result = kwargs["result"]
        entry_price = kwargs["entry_price"]
        exit_price = kwargs["exit_price"]
        pnl = kwargs["pnl"]
        pnl_pct = kwargs["pnl_pct"]
        ai_confidence = kwargs["ai_confidence"]
        ai_reasoning = kwargs["ai_reasoning"]
        market_condition = kwargs["market_condition"]
        pattern = kwargs.get("pattern", "")
        rsi = kwargs.get("rsi")
        bb_pct = kwargs.get("bb_pct")
        macd_h = kwargs.get("macd_h")

        indicator_text = ""
        if rsi is not None:
            indicator_text += f"\nRSI at entry: {rsi:.1f}"
        if bb_pct is not None:
            indicator_text += f"\nBB%B at entry: {bb_pct:.3f}"
        if macd_h is not None:
            indicator_text += f"\nMACD histogram: {macd_h:.6f}"

        prompt = f"""You are a self-improving Islamic trading AI. Analyze this trade and extract ONE deep lesson.

TRADE RESULT: {result}
Symbol: {symbol} | Side: {side.upper()} | Pattern: {pattern or 'none'}
Entry: ${entry_price:.4f} → Exit: ${exit_price:.4f} ({pnl_pct:+.2f}%)
PNL: ${pnl:.4f} | AI Confidence at entry: {ai_confidence}%
Market: {market_condition}
AI Reasoning: {ai_reasoning[:200]}{indicator_text}

Write ONE deep, specific lesson (2-3 sentences) that:
- Identifies EXACTLY which indicator/signal was right or wrong
- Gives a specific actionable rule for future trades
- Starts with "{result}:"

Do NOT be generic. Be specific to the indicators and market conditions above."""

        try:
            from ai_agent import AIAgent
            agent = AIAgent.get_instance()
            slot = agent._get_slot()
            if slot:
                try:
                    text = slot.call(
                        "You are a trading lesson extractor. Be concise and specific.",
                        prompt,
                        temperature=0.3,
                    )
                    slot.success_calls += 1
                    return text.strip()
                except Exception as e:
                    slot.failed_calls += 1
                    err = str(e).lower()
                    if any(x in err for x in ["429", "quota", "rate", "exhausted", "resource_exhausted"]):
                        if any(x in err for x in ["day", "daily", "per_day"]):
                            slot.mark_exhausted(82800)
                        else:
                            slot.mark_exhausted(180)
                    print(f"[LearningLoop] AI error: {str(e)[:80]}")
        except Exception as e:
            print(f"[LearningLoop] reflect error: {e}")

        return (
            f"{result}: {symbol} {side.upper()} in {market_condition} market. "
            f"Entry ${entry_price:.4f} → Exit ${exit_price:.4f} ({pnl_pct:+.2f}%). "
            f"AI confidence was {ai_confidence}%. "
            + (f"Pattern: {pattern}. " if pattern else "")
            + (f"RSI={rsi:.0f}" if rsi else "")
        )

    async def strategic_review(
        self,
        broadcast_fn: Optional[Callable] = None,
    ) -> str:
        """
        Runs after every 5 trades — strategic review of recent performance.
        Uses the AIAgent pool (multi-provider, shared quota) instead of direct Gemini.
        """

        try:
            trades = await self.db.get_trades(limit=20)
            closed = [t for t in trades if t.get("status") == "closed"]
            if len(closed) < 5:
                return ""

            recent = closed[:10]
            wins = [t for t in recent if (t.get("pnl") or 0) > 0]
            total_pnl = sum(float(t.get("pnl") or 0) for t in recent)
            win_rate = len(wins) / len(recent) * 100 if recent else 0

            trade_summary = "\n".join(
                f"  {'✅' if (t.get('pnl') or 0) > 0 else '❌'} {t.get('symbol')} "
                f"{t.get('side','').upper()} | conf:{t.get('ai_confidence',0)}% | "
                f"PNL:${t.get('pnl') or 0:.4f} | cond:{t.get('market_condition','')} | "
                f"pattern:{t.get('pattern','none')}"
                for t in recent
            )

            lessons = await self.db.get_recent_lessons(limit=10)
            lessons_text = "\n".join(f"  • {l.get('lesson','')[:100]}" for l in lessons[:8])

            prompt = f"""You are the strategic brain of an Islamic trading agent reviewing your last {len(recent)} trades.

RECENT TRADES:
{trade_summary}

Win Rate: {win_rate:.1f}% | Total PNL: ${total_pnl:.4f}
Recent Lessons:
{lessons_text}

Provide a STRATEGIC REVIEW (3-4 sentences):
1. What is the #1 issue causing losses?
2. What one change would most improve performance?
3. Are there any market conditions or symbols to avoid right now?

Answer in Arabic or English based on context. Be direct and specific."""

            from ai_agent import AIAgent
            agent = AIAgent.get_instance()
            slot  = agent._get_slot()
            if not slot:
                return ""
            review = slot.call(
                "You are a strategic trading AI. Be concise, direct, and specific.",
                prompt,
                temperature=0.3,
            )
            review = review.strip()

            if broadcast_fn:
                await broadcast_fn(json.dumps({
                    "type": "agent",
                    "message": f"📋 Strategic Review: {review[:200]}...",
                }))

            await self.db.save_lesson({
                "lesson": f"[STRATEGIC REVIEW] {review}",
                "symbol": "PORTFOLIO",
                "market_condition": "review",
                "outcome": "win" if win_rate >= 50 else "loss",
                "created_at": datetime.utcnow().isoformat(),
            })

            return review

        except Exception as e:
            print(f"[LearningLoop] strategic_review error: {e}")
            return ""
