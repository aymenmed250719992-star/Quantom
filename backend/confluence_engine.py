"""
ConfluenceEngine — محرك تقاطع الإطارات الزمنية المتعددة  (T003)

يُحلّل 4 إطارات زمنية في آن واحد ويُطلق إشارة فقط عند تطابق الأغلبية.
الإطارات: 15m (سريع) | 1h (متوسط) | 4h (بطيء) | 1d (استراتيجي)

كل إطار يُنتج: BUY / SELL / HOLD + confidence (0–100)
القرار النهائي = متوسط مرجّح للإطارات المتوافقة.

الأوزان:
  15m → 20%  (توقيت الدخول)
  1h  → 35%  (الاتجاه الرئيسي)
  4h  → 30%  (الحكم الأساسي)
  1d  → 15%  (التحيّز الاستراتيجي)

متطلب الإجماع: ≥ 2 إطارات تتفق على نفس الاتجاه (قابل للتخصيص).
"""

import asyncio
from typing import Any, Optional

TIMEFRAMES = ["15m", "1h", "4h", "1d"]
WEIGHTS    = {"15m": 0.20, "1h": 0.35, "4h": 0.30, "1d": 0.15}
CANDLE_COUNTS = {"15m": 100, "1h": 60, "4h": 30, "1d": 14}


def _analyze_single_tf(ohlcv: list, timeframe: str) -> dict:
    """
    Compute a simple but solid directional signal from one timeframe.
    Returns {"action": BUY|SELL|HOLD, "confidence": 0-100, "reason": str}
    CPU-bound — called via asyncio.to_thread.
    """
    if not ohlcv or len(ohlcv) < 14:
        return {"action": "HOLD", "confidence": 0, "reason": "insufficient data"}

    try:
        import pandas as pd
        import ta

        df = pd.DataFrame(ohlcv, columns=["ts", "open", "high", "low", "close", "volume"])
        for c in ["open", "high", "low", "close", "volume"]:
            df[c] = df[c].astype(float)
        close = df["close"]

        # RSI
        rsi = float(ta.momentum.RSIIndicator(close, window=14).rsi().iloc[-1])

        # MACD
        macd_ind  = ta.trend.MACD(close)
        macd_hist = float(macd_ind.macd_diff().iloc[-1])

        # Bollinger Bands
        bb     = ta.volatility.BollingerBands(close, window=20)
        bb_pct = float(bb.bollinger_pband().iloc[-1])

        # EMA trend
        ema20 = float(close.ewm(span=20).mean().iloc[-1])
        ema50 = float(close.ewm(span=50).mean().iloc[-1]) if len(close) >= 50 else ema20
        price = float(close.iloc[-1])

        trend_up   = price > ema20 > ema50
        trend_down = price < ema20 < ema50

        # Score aggregation
        buy_signals = sell_signals = 0

        if rsi < 35:       buy_signals  += 2
        elif rsi < 45:     buy_signals  += 1
        if rsi > 65:       sell_signals += 2
        elif rsi > 55:     sell_signals += 1

        if macd_hist > 0:  buy_signals  += 1
        if macd_hist < 0:  sell_signals += 1

        if bb_pct < 0.25:  buy_signals  += 2
        elif bb_pct < 0.40: buy_signals += 1
        if bb_pct > 0.75:  sell_signals += 2
        elif bb_pct > 0.60: sell_signals += 1

        if trend_up:       buy_signals  += 2
        if trend_down:     sell_signals += 2

        max_score = 8
        buy_conf  = min(100, int(buy_signals  / max_score * 100))
        sell_conf = min(100, int(sell_signals / max_score * 100))

        if buy_signals > sell_signals and buy_conf >= 40:
            return {
                "action": "BUY", "confidence": buy_conf,
                "rsi": round(rsi, 1), "bb_pct": round(bb_pct, 3), "macd": round(macd_hist, 6),
                "trend": "up" if trend_up else "neutral",
                "reason": f"RSI={rsi:.0f} BB={bb_pct:.2f} MACD={'↑' if macd_hist > 0 else '↓'} trend={'↑' if trend_up else '→'}",
            }
        elif sell_signals > buy_signals and sell_conf >= 40:
            return {
                "action": "SELL", "confidence": sell_conf,
                "rsi": round(rsi, 1), "bb_pct": round(bb_pct, 3), "macd": round(macd_hist, 6),
                "trend": "down" if trend_down else "neutral",
                "reason": f"RSI={rsi:.0f} BB={bb_pct:.2f} MACD={'↑' if macd_hist > 0 else '↓'} trend={'↓' if trend_down else '→'}",
            }
        else:
            return {"action": "HOLD", "confidence": 50, "reason": "mixed signals"}

    except Exception as e:
        return {"action": "HOLD", "confidence": 0, "reason": f"error: {e}"}


async def analyze_confluence(
    symbol: str,
    client: Any,
    min_agreement: int = 2,
) -> dict:
    """
    Fetch all timeframes in parallel and compute confluence signal.

    Returns:
    {
      "action": "BUY" | "SELL" | "HOLD",
      "confidence": 0-100,
      "confluence_score": 0-4,
      "agreement": 2,
      "tf_signals": {tf: {action, confidence, reason}, ...},
      "reason": str,
    }
    """
    # Fetch all OHLCV in parallel
    from indicator_cache import IndicatorCache
    cache = IndicatorCache.get_instance()

    fetch_tasks = {
        tf: cache.get_ohlcv(symbol, tf, CANDLE_COUNTS[tf], fetch_fn=client.get_ohlcv)
        for tf in TIMEFRAMES
    }
    ohlcv_results = await asyncio.gather(*fetch_tasks.values(), return_exceptions=True)
    ohlcv_map = dict(zip(fetch_tasks.keys(), ohlcv_results))

    # Analyze each timeframe in parallel threads
    analysis_tasks = []
    valid_tfs = []
    for tf in TIMEFRAMES:
        ohlcv = ohlcv_map.get(tf)
        if ohlcv and not isinstance(ohlcv, Exception) and len(ohlcv) >= 14:
            analysis_tasks.append(asyncio.to_thread(_analyze_single_tf, ohlcv, tf))
            valid_tfs.append(tf)

    if not analysis_tasks:
        return {"action": "HOLD", "confidence": 0, "confluence_score": 0, "agreement": 0,
                "tf_signals": {}, "reason": "no data"}

    results = await asyncio.gather(*analysis_tasks, return_exceptions=True)
    tf_signals: dict[str, dict] = {}
    for tf, res in zip(valid_tfs, results):
        if not isinstance(res, Exception):
            tf_signals[tf] = res

    # Count agreements
    buy_tfs  = [tf for tf, s in tf_signals.items() if s.get("action") == "BUY"]
    sell_tfs = [tf for tf, s in tf_signals.items() if s.get("action") == "SELL"]

    dominant_action = "HOLD"
    agreement_tfs   = []

    if len(buy_tfs) >= min_agreement and len(buy_tfs) >= len(sell_tfs):
        dominant_action = "BUY"
        agreement_tfs   = buy_tfs
    elif len(sell_tfs) >= min_agreement and len(sell_tfs) > len(buy_tfs):
        dominant_action = "SELL"
        agreement_tfs   = sell_tfs

    # Weighted confidence
    if agreement_tfs:
        total_weight = sum(WEIGHTS[tf] for tf in agreement_tfs)
        weighted_conf = sum(
            tf_signals[tf]["confidence"] * WEIGHTS[tf]
            for tf in agreement_tfs
        ) / total_weight if total_weight else 0
        final_conf = int(weighted_conf)
    else:
        final_conf = 0

    agreement_count = len(agreement_tfs)
    confluence_score = agreement_count  # 0-4

    reason_parts = []
    for tf in TIMEFRAMES:
        sig = tf_signals.get(tf, {})
        action = sig.get("action", "?")
        conf   = sig.get("confidence", 0)
        icon   = "✅" if action == dominant_action else ("🔴" if action != "HOLD" else "⬜")
        reason_parts.append(f"{icon}{tf}({action}/{conf}%)")

    return {
        "action":           dominant_action,
        "confidence":       final_conf,
        "confluence_score": confluence_score,
        "agreement":        agreement_count,
        "tf_signals":       tf_signals,
        "agreeing_tfs":     agreement_tfs,
        "reason":           " | ".join(reason_parts),
    }
