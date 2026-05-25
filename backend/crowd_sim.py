"""
CrowdSim — محاكاة MiroFish لآلاف المتداولين الوهميين
مستوحى من: https://github.com/666ghj/MiroFish

يُحاكي 1000+ متداول وهمي بشخصيات مختلفة لتوقع سيكولوجية الجماهير:
• Whale Traders       — حيتان: صبر عالٍ، رأس مال ضخم، تحرك السوق
• Emotional Retail    — عاطفيون: FOMO، ذعر، قطيع
• Technical Analysts  — تقنيون: مؤشرات، أنماط، منطق بحت
• News Traders        — أخباريون: يتفاعلون مع الأحداث فوراً
• Contrarians         — عكسيون: يشترون الذعر، يبيعون الطمع
• Scalpers            — سكالبرز: سريعون، يصطادون الحركات الصغيرة
• Long-Term Holders   — محتفظون: لا يتأثرون بالضجيج اليومي
"""

import hashlib
import math
import random
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class PersonalityType(Enum):
    WHALE            = "whale"
    EMOTIONAL_RETAIL = "emotional_retail"
    TECHNICAL        = "technical_analyst"
    NEWS_TRADER      = "news_trader"
    CONTRARIAN       = "contrarian"
    SCALPER          = "scalper"
    LONG_TERM        = "long_term_holder"


# Distribution of trader types in a realistic market
PERSONALITY_DISTRIBUTION = {
    PersonalityType.WHALE:            0.02,   # 2%  — نادر لكن ثقيل
    PersonalityType.EMOTIONAL_RETAIL: 0.40,   # 40% — الأغلبية
    PersonalityType.TECHNICAL:        0.20,   # 20% — محللون
    PersonalityType.NEWS_TRADER:      0.15,   # 15% — أخباريون
    PersonalityType.CONTRARIAN:       0.08,   # 8%  — عكسيون
    PersonalityType.SCALPER:          0.10,   # 10% — سكالبرز
    PersonalityType.LONG_TERM:        0.05,   # 5%  — محتفظون
}

# Capital weight — الحيتان تتحكم بالسوق رغم قلتها
CAPITAL_WEIGHT = {
    PersonalityType.WHALE:            35.0,
    PersonalityType.EMOTIONAL_RETAIL:  1.0,
    PersonalityType.TECHNICAL:         3.0,
    PersonalityType.NEWS_TRADER:       2.0,
    PersonalityType.CONTRARIAN:        4.0,
    PersonalityType.SCALPER:           1.5,
    PersonalityType.LONG_TERM:         8.0,
}


@dataclass
class VirtualTrader:
    """متداول وهمي بشخصية وحالة نفسية محددة."""
    id:                 int
    personality:        PersonalityType
    capital_weight:     float
    fear_level:         float = 0.5        # 0=شجاع, 1=خائف
    greed_level:        float = 0.5        # 0=راضٍ, 1=جشع
    recent_wins:        int   = 0
    recent_losses:      int   = 0
    position:           str   = "none"     # "long", "short", "none"
    entry_price:        float = 0.0
    conviction:         float = 0.5        # قناعة القرار 0-1

    def decide(
        self,
        price:       float,
        price_change_1h:  float,
        price_change_24h: float,
        rsi:         float,
        volume_ratio: float,    # current_volume / avg_volume
        news_score:  float,     # -1=سلبي, 0=محايد, +1=إيجابي
        bb_position: float,     # -1=أسفل، 0=وسط، +1=أعلى باند بولنجر
        seed:        int = 0,
    ) -> dict:
        """يتخذ قرار BUY / SELL / HOLD بناءً على شخصيته والبيانات."""
        rng = random.Random(seed + self.id)
        noise = rng.gauss(0, 0.05)

        action = "hold"
        confidence = 0.5

        if self.personality == PersonalityType.WHALE:
            # الحيتان تتصرف عكس الجموع عند التطرف
            if rsi < 30 and price_change_24h < -0.05:
                action = "buy"
                confidence = 0.80 + noise
            elif rsi > 75 and price_change_24h > 0.08:
                action = "sell"
                confidence = 0.75 + noise
            elif bb_position < -0.7:
                action = "buy"
                confidence = 0.70 + noise
            else:
                action = "hold"
                confidence = 0.60

        elif self.personality == PersonalityType.EMOTIONAL_RETAIL:
            # عاطفيون: يشترون عند الارتفاع (FOMO)، يبيعون عند الانخفاض (ذعر)
            fear_factor = self.fear_level + rng.gauss(0, 0.1)
            if price_change_1h > 0.02 and self.greed_level > 0.6:
                action = "buy"
                confidence = 0.55 + noise + (self.greed_level * 0.2)
            elif price_change_24h < -0.05 and fear_factor > 0.7:
                action = "sell"
                confidence = 0.65 + fear_factor * 0.2 + noise
            elif volume_ratio > 2.0 and price_change_1h > 0.01:
                action = "buy"
                confidence = 0.50 + noise
            else:
                action = "hold"
                confidence = 0.4

        elif self.personality == PersonalityType.TECHNICAL:
            # تقنيون: يتبعون RSI وبولنجر والحجم
            if rsi < 35 and bb_position < -0.5 and volume_ratio > 1.2:
                action = "buy"
                confidence = 0.72 + noise
            elif rsi > 68 and bb_position > 0.5:
                action = "sell"
                confidence = 0.70 + noise
            elif rsi > 40 and rsi < 60 and volume_ratio > 1.5:
                action = "buy" if price_change_1h > 0 else "hold"
                confidence = 0.60 + noise
            else:
                action = "hold"
                confidence = 0.55

        elif self.personality == PersonalityType.NEWS_TRADER:
            # أخباريون: يتفاعلون مع الأخبار فوراً
            if news_score > 0.4:
                action = "buy"
                confidence = 0.65 + news_score * 0.25 + noise
            elif news_score < -0.4:
                action = "sell"
                confidence = 0.65 + abs(news_score) * 0.25 + noise
            else:
                action = "hold"
                confidence = 0.45

        elif self.personality == PersonalityType.CONTRARIAN:
            # عكسيون: يعملون عكس الجماهير
            if rsi > 72 and self.greed_level < 0.4:
                action = "sell"
                confidence = 0.70 + noise
            elif rsi < 32 and self.fear_level < 0.4:
                action = "buy"
                confidence = 0.72 + noise
            elif volume_ratio > 3.0 and price_change_1h > 0.03:
                action = "sell"
                confidence = 0.60 + noise
            else:
                action = "hold"
                confidence = 0.50

        elif self.personality == PersonalityType.SCALPER:
            # سكالبرز: يصطادون كل حركة صغيرة
            if abs(price_change_1h) > 0.005 and volume_ratio > 1.3:
                action = "buy" if price_change_1h > 0 else "sell"
                confidence = 0.58 + abs(price_change_1h) * 5 + noise
            else:
                action = "hold"
                confidence = 0.42

        elif self.personality == PersonalityType.LONG_TERM:
            # محتفظون: يتجاهلون الضجيج، ينظرون للقيمة فقط
            if price_change_24h < -0.10 and rsi < 40:
                action = "buy"
                confidence = 0.65 + noise
            elif price_change_24h > 0.20 and rsi > 75:
                action = "sell"
                confidence = 0.60 + noise
            else:
                action = "hold"
                confidence = 0.55

        confidence = max(0.0, min(1.0, confidence))
        return {
            "id":          self.id,
            "personality": self.personality.value,
            "action":      action,
            "confidence":  confidence,
            "weight":      self.capital_weight,
        }


class CrowdSimulator:
    """
    محاكي الجماهير — يُشغّل N متداول وهمي ويُجمّع قراراتهم.
    مستوحى من فلسفة MiroFish: السوق هو مجموع قرارات البشر.
    """

    _instance: Optional["CrowdSimulator"] = None

    def __init__(self, n_traders: int = 1000):
        self.n_traders    = n_traders
        self.traders:     list[VirtualTrader] = []
        self.last_result: Optional[dict]      = None
        self.last_run_at: float               = 0.0
        self._build_crowd()

    @classmethod
    def get_instance(cls, n: int = 1000) -> "CrowdSimulator":
        if cls._instance is None:
            cls._instance = cls(n)
        return cls._instance

    def _build_crowd(self) -> None:
        """يبني الجمهور بنسب واقعية من كل شخصية."""
        self.traders = []
        idx = 0
        for ptype, ratio in PERSONALITY_DISTRIBUTION.items():
            count  = max(1, int(self.n_traders * ratio))
            weight = CAPITAL_WEIGHT[ptype]
            for _ in range(count):
                trader = VirtualTrader(
                    id             = idx,
                    personality    = ptype,
                    capital_weight = weight,
                    fear_level     = random.uniform(0.2, 0.8),
                    greed_level    = random.uniform(0.2, 0.8),
                )
                self.traders.append(trader)
                idx += 1

    def simulate(
        self,
        symbol:            str,
        price:             float,
        price_change_1h:   float   = 0.0,
        price_change_24h:  float   = 0.0,
        rsi:               float   = 50.0,
        volume_ratio:      float   = 1.0,
        news_score:        float   = 0.0,
        bb_position:       float   = 0.0,
    ) -> dict:
        """
        يُشغّل كل المتداولين الوهميين ويُجمّع النتائج.
        Returns crowd sentiment dict.
        """
        seed = int(hashlib.md5(f"{symbol}{price:.2f}{time.time():.0f}".encode()).hexdigest(), 16) % 99999

        buy_weight  = 0.0
        sell_weight = 0.0
        hold_weight = 0.0
        total_weight = 0.0

        personality_votes: dict[str, dict] = {}
        whale_action = "hold"

        for trader in self.traders:
            decision = trader.decide(
                price, price_change_1h, price_change_24h,
                rsi, volume_ratio, news_score, bb_position, seed
            )
            w = decision["weight"] * decision["confidence"]
            total_weight += w
            action = decision["action"]

            if action == "buy":
                buy_weight  += w
            elif action == "sell":
                sell_weight += w
            else:
                hold_weight += w

            ptype = decision["personality"]
            if ptype not in personality_votes:
                personality_votes[ptype] = {"buy": 0, "sell": 0, "hold": 0}
            personality_votes[ptype][action] += 1

            if trader.personality == PersonalityType.WHALE:
                whale_action = action

        if total_weight == 0:
            total_weight = 1.0

        bullish_pct  = round(buy_weight  / total_weight * 100, 1)
        bearish_pct  = round(sell_weight / total_weight * 100, 1)
        neutral_pct  = round(hold_weight / total_weight * 100, 1)

        # درجة الخوف والطمع
        fear_greed = round((bullish_pct - bearish_pct) / 100 + 0.5, 2)
        fear_greed = max(0.0, min(1.0, fear_greed))

        # الإشارة الجماعية
        if bullish_pct > 60:
            crowd_signal = "STRONG_BUY"
        elif bullish_pct > 50:
            crowd_signal = "BUY"
        elif bearish_pct > 60:
            crowd_signal = "STRONG_SELL"
        elif bearish_pct > 50:
            crowd_signal = "SELL"
        else:
            crowd_signal = "NEUTRAL"

        # تباين الحيتان عن الجموع (إشارة عكسية قوية)
        whale_divergence = (
            whale_action == "buy"  and bearish_pct > 55 or
            whale_action == "sell" and bullish_pct > 55
        )

        # الشخصية المهيمنة
        dominant_personality = max(
            personality_votes.items(),
            key=lambda x: x[1].get("buy", 0) + x[1].get("sell", 0)
        )[0] if personality_votes else "unknown"

        # الحالة النفسية للسوق
        if fear_greed < 0.25:
            market_psychology = "ذعر شديد — Extreme Fear 🔴"
        elif fear_greed < 0.40:
            market_psychology = "خوف — Fear 🟠"
        elif fear_greed < 0.60:
            market_psychology = "محايد — Neutral ⚪"
        elif fear_greed < 0.75:
            market_psychology = "طمع — Greed 🟡"
        else:
            market_psychology = "طمع شديد — Extreme Greed 🟢"

        result = {
            "symbol":               symbol,
            "n_traders":            len(self.traders),
            "bullish_pct":          bullish_pct,
            "bearish_pct":          bearish_pct,
            "neutral_pct":          neutral_pct,
            "crowd_signal":         crowd_signal,
            "fear_greed_index":     fear_greed,
            "market_psychology":    market_psychology,
            "whale_action":         whale_action,
            "whale_divergence":     whale_divergence,
            "dominant_personality": dominant_personality,
            "personality_votes":    personality_votes,
            "recommendation":       self._interpret(crowd_signal, whale_divergence, rsi, news_score),
            "timestamp":            time.time(),
        }

        self.last_result = result
        self.last_run_at = time.time()
        return result

    def _interpret(
        self,
        crowd_signal:      str,
        whale_divergence:  bool,
        rsi:               float,
        news_score:        float,
    ) -> str:
        """تفسير النتيجة للمتداول."""
        lines = []

        if whale_divergence:
            lines.append("⚠️ تباين الحيتان: الحيتان تعمل عكس الجموع — إشارة عكسية قوية!")

        if crowd_signal in ("STRONG_BUY", "BUY"):
            if rsi > 70:
                lines.append("🐂 الجموع متفائلة لكن RSI مشبع شراءً — احذر من الفخ")
            else:
                lines.append("🐂 الجموع تشتري — زخم إيجابي مدعوم بالسيكولوجية الجماعية")
        elif crowd_signal in ("STRONG_SELL", "SELL"):
            if rsi < 30:
                lines.append("🐻 الجموع تبيع لكن RSI مشبع بيعاً — احتمال انعكاس وشيك")
            else:
                lines.append("🐻 الجموع متشائمة — ضغط بيع جماعي قوي")
        else:
            lines.append("⚪ الجموع في تردد — لا إشارة واضحة")

        if news_score > 0.5:
            lines.append("📰 الأخبار إيجابية تدعم الجموع")
        elif news_score < -0.5:
            lines.append("📰 الأخبار سلبية تُغذي الخوف")

        return " | ".join(lines) if lines else "لا توجد إشارة كافية"

    def get_status(self) -> dict:
        """حالة المحاكي."""
        return {
            "n_traders":     len(self.traders),
            "last_run_at":   self.last_run_at,
            "has_result":    self.last_result is not None,
            "last_signal":   self.last_result.get("crowd_signal") if self.last_result else None,
            "last_symbol":   self.last_result.get("symbol") if self.last_result else None,
        }
