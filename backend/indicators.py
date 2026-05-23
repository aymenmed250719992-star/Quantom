import pandas as pd
import numpy as np


def get_market_indicators(ohlcv_data: list) -> dict:
    if len(ohlcv_data) < 30:
        return {"error": "Insufficient OHLCV data for indicator calculation"}

    df = pd.DataFrame(
        ohlcv_data,
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = df[col].astype(float)

    close = df["close"]
    high = df["high"]
    low = df["low"]

    try:
        import ta
        rsi_val = float(ta.momentum.RSIIndicator(close=close, window=14).rsi().iloc[-1])
        macd_ind = ta.trend.MACD(close=close, window_slow=26, window_fast=12, window_sign=9)
        macd_val = float(macd_ind.macd().iloc[-1])
        macd_signal_val = float(macd_ind.macd_signal().iloc[-1])
        macd_hist_val = float(macd_ind.macd_diff().iloc[-1])
        bb_ind = ta.volatility.BollingerBands(close=close, window=20, window_dev=2)
        bb_upper_val = float(bb_ind.bollinger_hband().iloc[-1])
        bb_middle_val = float(bb_ind.bollinger_mavg().iloc[-1])
        bb_lower_val = float(bb_ind.bollinger_lband().iloc[-1])
        bb_pct_val = float(bb_ind.bollinger_pband().iloc[-1])
    except ImportError:
        rsi_val = _calc_rsi(close.values, 14)
        macd_val, macd_signal_val, macd_hist_val = _calc_macd(close.values)
        bb_upper_val, bb_middle_val, bb_lower_val = _calc_bollinger(close.values, 20, 2)
        bb_pct_val = (close.iloc[-1] - bb_lower_val) / (bb_upper_val - bb_lower_val + 1e-10)

    def safe(v: float) -> float:
        return 0.0 if (np.isnan(v) or np.isinf(v)) else round(v, 6)

    current_price = float(close.iloc[-1])
    prev_price = float(close.iloc[-2])
    price_change_pct = ((current_price - prev_price) / prev_price) * 100 if prev_price > 0 else 0.0

    rsi = safe(rsi_val)

    # Extra indicators used by rule-based fallback
    ma20_val  = float(close.rolling(20).mean().iloc[-1]) if len(close) >= 20 else float(close.mean())
    vol_series = df["volume"].astype(float)
    vol_avg_val = float(vol_series.iloc[-10:].mean()) if len(vol_series) >= 10 else float(vol_series.mean())

    # Multi-candle trend: price change over last 6 candles (90 min on 15m chart)
    price_6c_ago = float(close.iloc[-7]) if len(close) >= 7 else float(close.iloc[0])
    price_change_90m = ((current_price - price_6c_ago) / price_6c_ago * 100) if price_6c_ago > 0 else 0.0

    # 3-candle slope: how many of last 3 candles closed higher than previous
    last4 = close.iloc[-4:].values if len(close) >= 4 else close.values
    candle_ups   = sum(1 for i in range(1, len(last4)) if last4[i] > last4[i-1])
    candle_downs = sum(1 for i in range(1, len(last4)) if last4[i] < last4[i-1])
    # candle_trend: +1 = rising, -1 = falling, 0 = mixed
    candle_trend = 1 if candle_ups >= 3 else (-1 if candle_downs >= 3 else 0)

    return {
        "current_price": round(current_price, 4),
        "price_change_pct": round(price_change_pct, 4),
        "price_change_90m": round(price_change_90m, 4),
        "candle_trend": candle_trend,
        "rsi": rsi,
        "macd": safe(macd_val),
        "macd_signal": safe(macd_signal_val),
        "macd_histogram": safe(macd_hist_val),
        "bb_upper": safe(bb_upper_val),
        "bb_middle": safe(bb_middle_val),
        "bb_lower": safe(bb_lower_val),
        "bb_pct": safe(bb_pct_val),
        "volume": round(float(vol_series.iloc[-1]), 2),
        "volume_avg": round(vol_avg_val, 2),
        "ma20": round(safe(ma20_val), 4),
        "market_condition": _classify_market(rsi, price_change_90m),
    }


def _classify_market(rsi: float, price_change_90m: float) -> str:
    """Classify market using 90-minute price change (6 × 15-min candles) for stability."""
    if rsi > 70:
        return "overbought"
    if rsi < 30:
        return "oversold"
    if abs(price_change_90m) > 4:
        return "volatile"
    if price_change_90m > 1.0:
        return "bullish"
    if price_change_90m < -1.0:
        return "bearish"
    return "sideways"


def _calc_rsi(prices: np.ndarray, period: int = 14) -> float:
    if len(prices) < period + 1:
        return 50.0
    deltas = np.diff(prices)
    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)
    avg_gain = np.mean(gains[-period:])
    avg_loss = np.mean(losses[-period:])
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _calc_macd(prices: np.ndarray) -> tuple[float, float, float]:
    if len(prices) < 26:
        return 0.0, 0.0, 0.0
    def ema(arr: np.ndarray, n: int) -> np.ndarray:
        alpha = 2.0 / (n + 1)
        result = np.zeros(len(arr))
        result[0] = arr[0]
        for i in range(1, len(arr)):
            result[i] = alpha * arr[i] + (1 - alpha) * result[i - 1]
        return result
    ema12 = ema(prices, 12)
    ema26 = ema(prices, 26)
    macd_line = ema12 - ema26
    signal_line = ema(macd_line, 9)
    return float(macd_line[-1]), float(signal_line[-1]), float(macd_line[-1] - signal_line[-1])


def _calc_bollinger(prices: np.ndarray, period: int = 20, std_dev: int = 2) -> tuple[float, float, float]:
    if len(prices) < period:
        return float(prices[-1]), float(prices[-1]), float(prices[-1])
    window = prices[-period:]
    middle = float(np.mean(window))
    std = float(np.std(window))
    return middle + std_dev * std, middle, middle - std_dev * std
