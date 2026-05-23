"""
Backtesting Engine — محرك اختبار الاستراتيجية على البيانات التاريخية
يستخدم نفس منطق المؤشرات (RSI / BB / MA) على شمعات OHLCV تاريخية من MEXC.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Optional

import httpx

INITIAL_CAPITAL = 10_000.0
RISK_PER_TRADE  = 0.015   # 1.5% من رأس المال لكل صفقة
TRADE_FEE       = 0.001   # 0.1% رسوم في كل اتجاه


# ── Math helpers ──────────────────────────────────────────────────────────────

def _calc_rsi(closes: list[float], period: int = 14) -> list[float]:
    n = len(closes)
    rsi = [50.0] * n
    if n < period + 1:
        return rsi

    gains, losses = [], []
    for i in range(1, n):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0.0))
        losses.append(max(-diff, 0.0))

    avg_g = sum(gains[:period]) / period
    avg_l = sum(losses[:period]) / period

    for i in range(period, n):
        if i > period:
            avg_g = (avg_g * (period - 1) + gains[i - 1]) / period
            avg_l = (avg_l * (period - 1) + losses[i - 1]) / period
        rs = avg_g / (avg_l + 1e-10)
        rsi[i] = 100.0 - 100.0 / (1.0 + rs)

    return rsi


def _bb_pct(closes: list[float], i: int, window: int = 20) -> float:
    """Bollinger Band %B at index i."""
    if i < window:
        return 0.5
    sl = closes[i - window: i]
    mean = sum(sl) / window
    std  = (sum((x - mean) ** 2 for x in sl) / window) ** 0.5
    upper = mean + 2 * std
    lower = mean - 2 * std
    return (closes[i] - lower) / (upper - lower + 1e-10)


def _ma(closes: list[float], i: int, window: int = 20) -> float:
    if i < window:
        return closes[i]
    return sum(closes[i - window: i]) / window


def _generate_signal(
    rsi: float, prev_rsi: float,
    close: float, ma20: float,
    bb: float,
) -> Optional[str]:
    """نفس منطق الإشارة المستخدم في البوت الحقيقي."""
    # BUY: RSI oversold + يتعافى + قرب الحد الأدنى من BB
    if rsi < 35 and rsi > prev_rsi and bb < 0.25:
        return "buy"
    # BUY: عبور MA + RSI في نطاق معتدل
    if close > ma20 and 45 < rsi < 60 and bb > 0.4:
        return "buy"
    # SELL: RSI overbought + يتراجع + قرب الحد الأعلى من BB
    if rsi > 68 and rsi < prev_rsi and bb > 0.75:
        return "sell"
    return None


# ── MEXC Data Fetcher ─────────────────────────────────────────────────────────

async def _fetch_ohlcv(symbol: str, interval: str, limit: int) -> list[dict]:
    """يجلب بيانات OHLCV من MEXC (public, بدون مفتاح)."""
    sym = symbol.replace("/", "").upper()
    if not sym.endswith("USDT"):
        sym += "USDT"

    url = "https://api.mexc.com/api/v3/klines"
    params = {"symbol": sym, "interval": interval, "limit": limit}

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, params=params)
        raw  = resp.json()

    if not raw or not isinstance(raw, list):
        return []

    return [
        {
            "ts":     int(r[0]),
            "open":   float(r[1]),
            "high":   float(r[2]),
            "low":    float(r[3]),
            "close":  float(r[4]),
            "volume": float(r[5]),
        }
        for r in raw
    ]


# ── Main Backtest ─────────────────────────────────────────────────────────────

async def run_backtest(
    symbol: str,
    days: int = 30,
    initial_capital: float = INITIAL_CAPITAL,
    interval: str = "15m",
) -> dict:
    """
    يشغّل اختبار الاستراتيجية على بيانات تاريخية.
    يعيد إحصائيات شاملة + آخر 20 صفقة للعرض.
    """
    try:
        # كل يوم = 96 شمعة على 15m (24h * 4)
        limit = min(days * 96 + 50, 1500)
        candles = await _fetch_ohlcv(symbol, interval, limit)

        if not candles or len(candles) < 50:
            return {
                "success": False,
                "error": f"بيانات غير كافية لـ {symbol} ({len(candles)} شمعة)",
            }

        closes = [c["close"] for c in candles]
        rsi_series = _calc_rsi(closes, 14)

        capital    = initial_capital
        equity     = [initial_capital]   # equity curve
        open_trade: Optional[dict] = None
        trades: list[dict] = []

        for i in range(30, len(candles)):
            c        = candles[i]
            rsi      = rsi_series[i]
            prev_rsi = rsi_series[i - 1]
            ma20     = _ma(closes, i, 20)
            bb       = _bb_pct(closes, i, 20)

            # ── إغلاق الصفقة إذا ضرب SL أو TP ──────────────────────────────
            if open_trade:
                entry = open_trade["entry"]
                sl    = open_trade["sl"]
                tp    = open_trade["tp"]
                side  = open_trade["side"]

                hit_sl = (side == "buy"  and c["low"]  <= sl) or \
                         (side == "sell" and c["high"] >= sl)
                hit_tp = (side == "buy"  and c["high"] >= tp) or \
                         (side == "sell" and c["low"]  <= tp)

                if hit_sl or hit_tp:
                    exit_px  = tp if hit_tp else sl
                    sign     = 1 if side == "buy" else -1
                    pnl_pct  = sign * (exit_px - entry) / entry - TRADE_FEE * 2
                    pnl_usd  = open_trade["size"] * pnl_pct
                    capital += pnl_usd
                    equity.append(capital)

                    trades.append({
                        "symbol":          symbol,
                        "side":            side,
                        "entry":           round(entry, 6),
                        "exit":            round(exit_px, 6),
                        "pnl_pct":         round(pnl_pct * 100, 2),
                        "pnl_usd":         round(pnl_usd, 2),
                        "won":             hit_tp,
                        "duration_candles": i - open_trade["idx"],
                        "candle_in_ts":    open_trade["ts"],
                        "candle_out_ts":   c["ts"],
                    })
                    open_trade = None

            # ── فتح صفقة جديدة ────────────────────────────────────────────
            if open_trade is None:
                signal = _generate_signal(rsi, prev_rsi, c["close"], ma20, bb)
                if signal:
                    entry    = c["close"]
                    risk_usd = capital * RISK_PER_TRADE

                    if signal == "buy":
                        sl = entry * 0.985   # -1.5%
                        tp = entry * 1.030   # +3.0%
                    else:
                        sl = entry * 1.015
                        tp = entry * 0.970

                    risk_per_unit = abs(entry - sl)
                    qty  = risk_usd / risk_per_unit if risk_per_unit > 0 else 0
                    size = min(qty * entry, capital * 0.5)

                    open_trade = {
                        "side":  signal,
                        "entry": entry,
                        "sl":    sl,
                        "tp":    tp,
                        "size":  size,
                        "idx":   i,
                        "ts":    c["ts"],
                    }

        # ── إحصائيات ─────────────────────────────────────────────────────────
        if not trades:
            return {
                "success":         True,
                "symbol":          symbol,
                "days":            days,
                "interval":        interval,
                "total_trades":    0,
                "win_rate":        0,
                "total_pnl_usd":   0,
                "total_pnl_pct":   0,
                "max_drawdown_pct": 0,
                "profit_factor":   0,
                "sharpe_ratio":    0,
                "initial_capital": initial_capital,
                "final_capital":   round(capital, 2),
                "candles_analyzed": len(candles),
                "equity_curve":    equity[-50:],
                "trades":          [],
                "message":         "لا توجد إشارات في هذه الفترة",
            }

        wins        = [t for t in trades if t["won"]]
        losses_t    = [t for t in trades if not t["won"]]
        total_pnl   = sum(t["pnl_usd"] for t in trades)
        gross_profit = sum(t["pnl_usd"] for t in wins)    if wins    else 0.0
        gross_loss   = abs(sum(t["pnl_usd"] for t in losses_t)) if losses_t else 0.0
        pf          = round(gross_profit / gross_loss, 2) if gross_loss > 0 else 99.0

        # Max drawdown
        running, peak, max_dd = initial_capital, initial_capital, 0.0
        for t in trades:
            running += t["pnl_usd"]
            peak     = max(peak, running)
            dd       = (peak - running) / peak
            max_dd   = max(max_dd, dd)

        # Sharpe (simplified, per-trade)
        pnls    = [t["pnl_pct"] for t in trades]
        avg_pnl = sum(pnls) / len(pnls)
        std_pnl = (sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)) ** 0.5
        sharpe  = round(avg_pnl / std_pnl, 2) if std_pnl > 0 else 0.0

        avg_dur = round(sum(t["duration_candles"] for t in trades) / len(trades), 1)

        # Equity curve (max 100 نقطة)
        step = max(1, len(equity) // 100)
        eq_sample = equity[::step][-100:]

        return {
            "success":         True,
            "symbol":          symbol,
            "days":            days,
            "interval":        interval,
            "total_trades":    len(trades),
            "wins":            len(wins),
            "losses":          len(losses_t),
            "win_rate":        round(len(wins) / len(trades) * 100, 1),
            "total_pnl_usd":   round(total_pnl, 2),
            "total_pnl_pct":   round(total_pnl / initial_capital * 100, 2),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "profit_factor":   pf,
            "sharpe_ratio":    sharpe,
            "avg_win_usd":     round(gross_profit / len(wins), 2)    if wins    else 0.0,
            "avg_loss_usd":    round(-gross_loss / len(losses_t), 2) if losses_t else 0.0,
            "avg_duration_candles": avg_dur,
            "avg_duration_hours":   round(avg_dur * 0.25, 1),
            "initial_capital": initial_capital,
            "final_capital":   round(capital, 2),
            "candles_analyzed": len(candles),
            "equity_curve":    [round(v, 2) for v in eq_sample],
            "trades":          trades[-20:],
        }

    except Exception as e:
        return {"success": False, "error": str(e), "symbol": symbol}


# ── Multi-Symbol Backtest ─────────────────────────────────────────────────────

async def run_multi_backtest(
    symbols: list[str],
    days: int = 30,
    initial_capital: float = INITIAL_CAPITAL,
) -> dict:
    """يشغّل الاختبار على عدة عملات بالتوازي ويرجع ملخصاً مقارناً."""
    tasks = [run_backtest(s, days, initial_capital) for s in symbols]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out = []
    for sym, res in zip(symbols, results):
        if isinstance(res, Exception):
            out.append({"symbol": sym, "success": False, "error": str(res)})
        else:
            out.append(res)

    # ترتيب حسب PnL
    out.sort(key=lambda x: x.get("total_pnl_usd", -9999), reverse=True)

    return {
        "symbols":    symbols,
        "days":       days,
        "results":    out,
        "best":       out[0]["symbol"] if out else None,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
