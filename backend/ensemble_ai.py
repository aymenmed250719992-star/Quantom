"""
EnsembleAI — نظام التصويت بالذكاء الاصطناعي المتعدد  (T006)

5 ناخبون مستقلون يُصوّتون على كل صفقة — الأغلبية تقرر:

  1. GeminiAgent       → تحليل لغوي + خبرة تداولية  (وزن: 30%)
  2. TechnicalRules    → قواعد خوارزمية صارمة        (وزن: 25%)
  3. MLModel           → نموذج Gradient Boosting     (وزن: 20%)
  4. CrowdSim          → محاكاة 1000 متداول           (وزن: 15%)
  5. ConfluenceEngine  → تقاطع 4 إطارات زمنية        (وزن: 10%)

القرار النهائي:
  • weighted_score ≥ 0.60 → BUY
  • weighted_score ≤ 0.40 → SELL
  • otherwise             → HOLD

Dissent bonus/penalty:
  • إذا اتفق 5/5 → +10% confidence
  • إذا اختلف ناخب واحد → لا تغيير
  • إذا اختلف 2+ → -10% confidence (تشكيك في الإشارة)
"""

import asyncio
from typing import Any, Optional


VOTER_WEIGHTS = {
    "gemini":      0.30,
    "technical":   0.25,
    "ml_model":    0.20,
    "crowd_sim":   0.15,
    "confluence":  0.10,
}

ACTION_SCORE = {"BUY": 1.0, "SELL": 0.0, "HOLD": 0.5}


class VoterResult:
    __slots__ = ("voter", "action", "confidence", "weight", "reason")

    def __init__(self, voter: str, action: str, confidence: float, reason: str = ""):
        self.voter      = voter
        self.action     = action.upper()
        self.confidence = float(confidence)
        self.weight     = VOTER_WEIGHTS.get(voter, 0.10)
        self.reason     = reason

    def to_dict(self) -> dict:
        return {
            "voter":      self.voter,
            "action":     self.action,
            "confidence": self.confidence,
            "weight":     self.weight,
            "reason":     self.reason[:120],
        }


class EnsembleResult:
    def __init__(
        self,
        action: str,
        confidence: float,
        votes: list[VoterResult],
        weighted_score: float,
        agreement: int,
    ):
        self.action         = action
        self.confidence     = confidence
        self.votes          = votes
        self.weighted_score = weighted_score
        self.agreement      = agreement   # how many voters agreed with final action

    def to_dict(self) -> dict:
        return {
            "action":          self.action,
            "confidence":      round(self.confidence, 1),
            "weighted_score":  round(self.weighted_score, 3),
            "agreement":       self.agreement,
            "total_voters":    len(self.votes),
            "consensus":       self.agreement >= 4,
            "votes":           [v.to_dict() for v in self.votes],
        }


# ── Individual voter functions ────────────────────────────────────────────────

async def _vote_technical(symbol: str, indicators: dict) -> VoterResult:
    """Pure rule-based technical analysis voter."""
    try:
        rsi      = float(indicators.get("rsi", 50))
        macd_h   = float(indicators.get("macd_histogram", 0))
        bb_pct   = float(indicators.get("bb_pct", 0.5))
        price    = float(indicators.get("current_price", 0))
        ma20     = float(indicators.get("ma20", price))
        ma_trend = price > ma20

        buy_pts = sell_pts = 0

        if rsi < 30:       buy_pts  += 3
        elif rsi < 42:     buy_pts  += 1
        if rsi > 70:       sell_pts += 3
        elif rsi > 58:     sell_pts += 1

        if macd_h > 0.001: buy_pts  += 2
        elif macd_h < -0.001: sell_pts += 2

        if bb_pct < 0.20:  buy_pts  += 3
        elif bb_pct < 0.35: buy_pts += 1
        if bb_pct > 0.80:  sell_pts += 3
        elif bb_pct > 0.65: sell_pts += 1

        if ma_trend:       buy_pts  += 1
        else:              sell_pts += 1

        max_pts  = 9
        if buy_pts > sell_pts:
            conf   = min(95, int(buy_pts / max_pts * 100))
            return VoterResult("technical", "BUY", conf,
                               f"RSI={rsi:.0f} BB={bb_pct:.2f} MACD={'↑' if macd_h > 0 else '↓'}")
        elif sell_pts > buy_pts:
            conf   = min(95, int(sell_pts / max_pts * 100))
            return VoterResult("technical", "SELL", conf,
                               f"RSI={rsi:.0f} BB={bb_pct:.2f} MACD={'↓' if macd_h < 0 else '↑'}")
        return VoterResult("technical", "HOLD", 50, "mixed signals")
    except Exception as e:
        return VoterResult("technical", "HOLD", 50, f"error: {e}")


async def _vote_ml(indicators: dict, side_hint: str) -> VoterResult:
    """ML model voter."""
    try:
        from ml_model import TradingMLModel
        ml = TradingMLModel.get_instance()
        if not ml.is_trained:
            return VoterResult("ml_model", "HOLD", 50, "not trained yet")

        prob_buy  = ml.predict_win_prob(indicators, "buy",  float(indicators.get("ai_confidence", 60))) or 0.5
        prob_sell = ml.predict_win_prob(indicators, "sell", float(indicators.get("ai_confidence", 60))) or 0.5

        if prob_buy > prob_sell and prob_buy > 0.55:
            return VoterResult("ml_model", "BUY",  round(prob_buy * 100, 1), f"P(win|buy)={prob_buy:.2f}")
        elif prob_sell > prob_buy and prob_sell > 0.55:
            return VoterResult("ml_model", "SELL", round(prob_sell * 100, 1), f"P(win|sell)={prob_sell:.2f}")
        return VoterResult("ml_model", "HOLD", 50, "uncertain")
    except Exception as e:
        return VoterResult("ml_model", "HOLD", 50, f"error: {e}")


async def _vote_crowd(symbol: str, indicators: dict) -> VoterResult:
    """CrowdSim voter."""
    try:
        from crowd_sim import CrowdSimulator
        sim   = CrowdSimulator.get_instance()
        price = float(indicators.get("current_price", 0))
        rsi   = float(indicators.get("rsi", 50))
        if price <= 0:
            return VoterResult("crowd_sim", "HOLD", 50, "no price")

        result = await asyncio.to_thread(
            sim.simulate, symbol, price, 0.0, 0.0, rsi, 1.0, 0.0, 0.0,
        )
        signal  = result.get("crowd_signal", "NEUTRAL").upper()
        bull    = float(result.get("bullish_pct", 50))
        bear    = float(result.get("bearish_pct", 50))

        action = "BUY" if "BULLISH" in signal else ("SELL" if "BEARISH" in signal else "HOLD")
        conf   = max(bull, bear) if action != "HOLD" else 50
        return VoterResult("crowd_sim", action, round(conf, 1), f"🐂{bull:.0f}% 🐻{bear:.0f}%")
    except Exception as e:
        return VoterResult("crowd_sim", "HOLD", 50, f"error: {e}")


async def _vote_confluence(symbol: str, client: Any) -> VoterResult:
    """Multi-timeframe confluence voter."""
    try:
        from confluence_engine import analyze_confluence
        result = await analyze_confluence(symbol, client, min_agreement=2)
        action = result.get("action", "HOLD")
        conf   = float(result.get("confidence", 50))
        return VoterResult("confluence", action, conf, result.get("reason", "")[:100])
    except Exception as e:
        return VoterResult("confluence", "HOLD", 50, f"error: {e}")


# ── Ensemble engine ───────────────────────────────────────────────────────────

async def ensemble_vote(
    symbol: str,
    indicators: dict,
    gemini_decision: dict,
    client: Any,
) -> EnsembleResult:
    """
    Run all 5 voters in parallel and compute weighted ensemble decision.
    """
    gemini_action = gemini_decision.get("action", "HOLD").upper()
    gemini_conf   = float(gemini_decision.get("confidence", 60))
    gemini_reason = gemini_decision.get("reason", "")[:100]

    gemini_vote = VoterResult("gemini", gemini_action, gemini_conf, gemini_reason)

    # Run all voters in parallel
    tech_vote, ml_vote, crowd_vote, conf_vote = await asyncio.gather(
        _vote_technical(symbol, indicators),
        _vote_ml(indicators, gemini_action),
        _vote_crowd(symbol, indicators),
        _vote_confluence(symbol, client),
        return_exceptions=True,
    )

    def _safe_vote(v: Any, name: str) -> VoterResult:
        if isinstance(v, Exception):
            return VoterResult(name, "HOLD", 50, str(v)[:80])
        return v

    votes = [
        gemini_vote,
        _safe_vote(tech_vote,  "technical"),
        _safe_vote(ml_vote,    "ml_model"),
        _safe_vote(crowd_vote, "crowd_sim"),
        _safe_vote(conf_vote,  "confluence"),
    ]

    # Weighted score: BUY=1.0, SELL=0.0, HOLD=0.5
    total_weight   = sum(v.weight for v in votes)
    weighted_score = sum(ACTION_SCORE[v.action] * v.weight for v in votes) / total_weight

    # Determine action
    if weighted_score >= 0.60:
        action = "BUY"
    elif weighted_score <= 0.40:
        action = "SELL"
    else:
        action = "HOLD"

    # Weighted confidence
    action_votes = [v for v in votes if v.action == action]
    agreement    = len(action_votes)

    if agreement > 0:
        w_conf = sum(v.confidence * v.weight for v in action_votes) / sum(v.weight for v in action_votes)
    else:
        w_conf = 50.0

    # Consensus bonus/penalty
    dissent = len([v for v in votes if v.action != action and v.action != "HOLD"])
    if dissent == 0 and agreement >= 4:
        w_conf = min(99, w_conf + 10)    # full consensus bonus
    elif dissent >= 2:
        w_conf = max(0, w_conf - 10)     # dissent penalty

    return EnsembleResult(
        action         = action,
        confidence     = round(w_conf, 1),
        votes          = votes,
        weighted_score = weighted_score,
        agreement      = agreement,
    )
