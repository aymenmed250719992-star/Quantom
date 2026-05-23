"""
On-Chain Sentiment Engine — محرك تحليل مشاعر السوق
- Fear & Greed Index: alternative.me (مجاني، بدون مفتاح)
- Whale Activity: اكتشاف النشاط غير العادي من CoinGecko
- تحديث كل 5 دقائق (مؤقت)
"""

import asyncio
from datetime import datetime, timezone
from typing import Any

import httpx

# ── Cache ─────────────────────────────────────────────────────────────────────
_fng_cache: dict = {}
_fng_ts: float = 0
FNG_TTL = 300  # 5 دقائق

_whale_cache: list = []
_whale_ts: float = 0
WHALE_TTL = 600  # 10 دقائق

_market_cache: dict = {}
_market_ts: float = 0
MARKET_TTL = 120  # دقيقتان


# ── Fear & Greed Index ────────────────────────────────────────────────────────

async def get_fear_greed_index() -> dict:
    """يجلب مؤشر الخوف والجشع من alternative.me (7 أيام)."""
    global _fng_cache, _fng_ts
    now = datetime.now(timezone.utc).timestamp()

    if _fng_cache and (now - _fng_ts) < FNG_TTL:
        return _fng_cache

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                "https://api.alternative.me/fng/",
                params={"limit": 7, "format": "json"},
            )
            data = resp.json()

        entries = data.get("data", [])
        current = entries[0] if entries else {}

        history = [
            {
                "value": int(e.get("value", 50)),
                "label": e.get("value_classification", "Neutral"),
                "timestamp": e.get("timestamp", ""),
            }
            for e in entries
        ]

        result = {
            "value": int(current.get("value", 50)),
            "label": current.get("value_classification", "Neutral"),
            "history": history,
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "source": "alternative.me",
        }
        _fng_cache = result
        _fng_ts = now
        return result

    except Exception as e:
        return {
            "value": 50,
            "label": "Neutral",
            "history": [],
            "error": str(e),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }


def classify_fng(value: int) -> dict:
    """تصنيف قيمة الخوف والجشع مع توصية للتداول."""
    if value <= 20:
        return {
            "zone": "extreme_fear",
            "color": "#ef4444",
            "emoji": "🔴",
            "advice_ar": "خوف شديد — فرصة شراء محتملة (السوق مبالغ في الهبوط)",
            "advice_en": "Extreme Fear — Potential buy opportunity",
            "signal": "bullish",
        }
    elif value <= 40:
        return {
            "zone": "fear",
            "color": "#f97316",
            "emoji": "🟠",
            "advice_ar": "خوف — السوق حذر، انتظر تأكيداً",
            "advice_en": "Fear — Cautious market",
            "signal": "neutral_bullish",
        }
    elif value <= 60:
        return {
            "zone": "neutral",
            "color": "#eab308",
            "emoji": "🟡",
            "advice_ar": "محايد — لا اتجاه واضح",
            "advice_en": "Neutral — No clear direction",
            "signal": "neutral",
        }
    elif value <= 80:
        return {
            "zone": "greed",
            "color": "#22c55e",
            "emoji": "🟢",
            "advice_ar": "جشع — احتمال تصحيح قريب، كن حذراً",
            "advice_en": "Greed — Correction may be near",
            "signal": "neutral_bearish",
        }
    else:
        return {
            "zone": "extreme_greed",
            "color": "#a855f7",
            "emoji": "🟣",
            "advice_ar": "جشع شديد — تحذير من تصحيح حاد",
            "advice_en": "Extreme Greed — High correction risk",
            "signal": "bearish",
        }


# ── Market Overview (Whale Activity Proxy) ────────────────────────────────────

async def get_market_overview() -> dict:
    """يجلب نظرة عامة على السوق ويكتشف النشاط غير العادي."""
    global _market_cache, _market_ts
    now = datetime.now(timezone.utc).timestamp()

    if _market_cache and (now - _market_ts) < MARKET_TTL:
        return _market_cache

    WATCH_IDS = "bitcoin,ethereum,binancecoin,solana,ripple,cardano"

    try:
        async with httpx.AsyncClient(timeout=12) as client:
            resp = await client.get(
                "https://api.coingecko.com/api/v3/coins/markets",
                params={
                    "vs_currency": "usd",
                    "ids": WATCH_IDS,
                    "order": "market_cap_desc",
                    "sparkline": "false",
                    "price_change_percentage": "1h,24h",
                },
            )
            coins = resp.json()

        whale_signals: list[dict] = []
        market_data: list[dict] = []

        for coin in coins:
            price_1h  = coin.get("price_change_percentage_1h_in_currency") or 0.0
            price_24h = coin.get("price_change_percentage_24h") or 0.0
            volume    = coin.get("total_volume") or 0
            mkt_cap   = coin.get("market_cap") or 1
            vol_ratio = volume / mkt_cap

            market_data.append({
                "symbol":     coin.get("symbol", "").upper(),
                "name":       coin.get("name", ""),
                "price":      coin.get("current_price", 0),
                "change_1h":  round(price_1h, 2),
                "change_24h": round(price_24h, 2),
                "volume_usd": volume,
                "vol_ratio":  round(vol_ratio, 4),
            })

            # تحديد نشاط الحيتان: تحرك سعري + حجم غير عادي
            is_spike = abs(price_1h) > 2.5 and vol_ratio > 0.12
            is_major = abs(price_1h) > 4.0

            if is_spike:
                direction  = "شراء ضخم 🐋" if price_1h > 0 else "بيع ضخم 🔻"
                severity   = "high" if is_major else "medium"
                whale_signals.append({
                    "symbol":         coin.get("symbol", "").upper(),
                    "name":           coin.get("name", ""),
                    "direction":      direction,
                    "change_1h_pct":  round(price_1h, 2),
                    "change_24h_pct": round(price_24h, 2),
                    "volume_usd":     volume,
                    "severity":       severity,
                    "message":        (
                        f"{coin.get('name','')} — {direction} "
                        f"| {price_1h:+.1f}% خلال ساعة"
                        f" | حجم: ${volume/1e6:.0f}M"
                    ),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })

        result = {
            "whale_signals":   whale_signals,
            "market_overview": market_data,
            "updated_at":      datetime.now(timezone.utc).isoformat(),
        }
        _market_cache = result
        _market_ts    = now
        return result

    except Exception as e:
        return {
            "whale_signals":   [],
            "market_overview": [],
            "error":           str(e),
            "updated_at":      datetime.now(timezone.utc).isoformat(),
        }


# ── Full Sentiment Aggregation ────────────────────────────────────────────────

async def get_full_sentiment() -> dict:
    """يجمع كل مؤشرات المشاعر في استجابة واحدة."""
    fng, market = await asyncio.gather(
        get_fear_greed_index(),
        get_market_overview(),
    )

    fng_value = fng.get("value", 50)
    classif   = classify_fng(fng_value)

    return {
        "fear_greed": {**fng, **classif},
        "whale_signals":   market.get("whale_signals", []),
        "market_overview": market.get("market_overview", []),
        "summary": {
            "overall_sentiment":      classif["zone"],
            "fng_value":              fng_value,
            "fng_label":              fng.get("label", "Neutral"),
            "fng_emoji":              classif["emoji"],
            "fng_advice_ar":          classif["advice_ar"],
            "signal":                 classif["signal"],
            "whale_count":            len(market.get("whale_signals", [])),
            "high_severity_whales":   sum(1 for w in market.get("whale_signals", []) if w.get("severity") == "high"),
        },
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
