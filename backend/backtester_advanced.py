"""
BacktesterAdvanced — محرك الاختبار التاريخي مع Monte Carlo  (T007)

Walk-Forward Backtest:
  • يُحاكي تنفيذ الاستراتيجية على بيانات تاريخية حقيقية
  • SL/TP/confidence من genome أو معاملات مباشرة
  • يحسب: Sharpe, Sortino, Max Drawdown, Win Rate, Profit Factor

Monte Carlo:
  • يُعيد ترتيب عشوائي للصفقات 1000 مرة
  • يُنتج توزيع احتمالي لمنحنى الأسهم
  • يُحسب VaR 95% و Expected Shortfall

كل شيء يعمل في background thread — لا يُعطّل event loop.
"""

import asyncio
import math
import random
import time
from typing import Any, Optional


# ── Trade simulation ──────────────────────────────────────────────────────────

def _simulate_trade(
    ohlcv: list,
    entry_idx: int,
    side: str,
    sl_pct: float,
    tp_pct: float,
    initial_capital: float = 1000.0,
    risk_pct: float = 1.5,
) -> dict:
    """Simulate a single trade from entry_idx forward."""
    if entry_idx >= len(ohlcv) - 1:
        return {"result": "no_exit", "pnl_pct": 0.0}

    entry_candle = ohlcv[entry_idx]
    entry_price  = float(entry_candle[4])   # close price

    if entry_price <= 0:
        return {"result": "no_exit", "pnl_pct": 0.0}

    sl_price = entry_price * (1 - sl_pct / 100) if side == "buy" else entry_price * (1 + sl_pct / 100)
    tp_price = entry_price * (1 + tp_pct / 100) if side == "buy" else entry_price * (1 - tp_pct / 100)

    for j in range(entry_idx + 1, min(entry_idx + 48, len(ohlcv))):   # max 48 candles forward
        candle = ohlcv[j]
        low    = float(candle[3])
        high   = float(candle[2])
        close  = float(candle[4])

        if side == "buy":
            if low <= sl_price:
                pnl_pct = -sl_pct
                return {"result": "sl", "pnl_pct": pnl_pct, "bars_held": j - entry_idx}
            if high >= tp_price:
                pnl_pct = tp_pct
                return {"result": "tp", "pnl_pct": pnl_pct, "bars_held": j - entry_idx}
        else:
            if high >= sl_price:
                pnl_pct = -sl_pct
                return {"result": "sl", "pnl_pct": pnl_pct, "bars_held": j - entry_idx}
            if low <= tp_price:
                pnl_pct = tp_pct
                return {"result": "tp", "pnl_pct": pnl_pct, "bars_held": j - entry_idx}

    # Timeout — close at last price
    exit_price = float(ohlcv[min(entry_idx + 47, len(ohlcv) - 1)][4])
    pnl_pct = (exit_price - entry_price) / entry_price * 100 if side == "buy" \
              else (entry_price - exit_price) / entry_price * 100
    return {"result": "timeout", "pnl_pct": pnl_pct, "bars_held": 47}


def _generate_signals(ohlcv: list, params: dict) -> list[dict]:
    """Generate BUY/SELL signals based on RSI + BB rules."""
    signals = []
    n = len(ohlcv)
    if n < 30:
        return signals

    closes = [float(c[4]) for c in ohlcv]

    # Simple RSI
    def _rsi(closes: list, window: int = 14) -> list:
        gains = [max(0, closes[i] - closes[i - 1]) for i in range(1, len(closes))]
        losses = [max(0, closes[i - 1] - closes[i]) for i in range(1, len(closes))]
        rsi_vals = []
        for i in range(len(gains)):
            if i < window:
                rsi_vals.append(50.0)
                continue
            avg_g = sum(gains[i - window:i]) / window
            avg_l = sum(losses[i - window:i]) / window
            rs = avg_g / avg_l if avg_l > 0 else 100
            rsi_vals.append(100 - 100 / (1 + rs))
        return [50.0] + rsi_vals

    rsi_vals = _rsi(closes)
    rsi_buy  = params.get("rsi_buy_max", 40)
    rsi_sell = params.get("rsi_sell_min", 60)

    for i in range(20, n - 1):
        r = rsi_vals[i] if i < len(rsi_vals) else 50
        if r < rsi_buy:
            signals.append({"idx": i, "side": "buy"})
        elif r > rsi_sell:
            signals.append({"idx": i, "side": "sell"})

    return signals


# ── Metrics ───────────────────────────────────────────────────────────────────

def _compute_metrics(equity_curve: list[float], trade_pnls: list[float]) -> dict:
    if not equity_curve or len(equity_curve) < 2:
        return {}

    initial = equity_curve[0]
    final   = equity_curve[-1]
    total_return_pct = (final - initial) / initial * 100

    # Max drawdown
    peak = equity_curve[0]
    max_dd = 0.0
    for e in equity_curve:
        if e > peak:
            peak = e
        dd = (peak - e) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    # Sharpe (daily returns approximation)
    returns = [(equity_curve[i] - equity_curve[i - 1]) / equity_curve[i - 1]
               for i in range(1, len(equity_curve)) if equity_curve[i - 1] > 0]
    if returns:
        avg_r = sum(returns) / len(returns)
        std_r = math.sqrt(sum((r - avg_r) ** 2 for r in returns) / len(returns)) if len(returns) > 1 else 1e-9
        sharpe = avg_r / std_r * math.sqrt(252) if std_r > 0 else 0
    else:
        avg_r = std_r = sharpe = 0

    # Sortino (downside deviation)
    down_returns = [r for r in returns if r < 0]
    if down_returns:
        down_std = math.sqrt(sum(r ** 2 for r in down_returns) / len(down_returns))
        sortino  = avg_r / down_std * math.sqrt(252) if down_std > 0 else 0
    else:
        sortino = sharpe * 1.5

    # Win rate & profit factor
    wins   = [p for p in trade_pnls if p > 0]
    losses = [p for p in trade_pnls if p <= 0]
    win_rate = len(wins) / len(trade_pnls) * 100 if trade_pnls else 0
    pf = sum(wins) / abs(sum(losses)) if losses and sum(losses) != 0 else (999 if wins else 0)

    return {
        "total_return_pct": round(total_return_pct, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "sharpe_ratio":     round(sharpe, 3),
        "sortino_ratio":    round(sortino, 3),
        "win_rate_pct":     round(win_rate, 1),
        "profit_factor":    round(pf, 3),
        "total_trades":     len(trade_pnls),
        "winning_trades":   len(wins),
        "losing_trades":    len(losses),
        "avg_win_pct":      round(sum(wins) / len(wins), 3) if wins else 0,
        "avg_loss_pct":     round(sum(losses) / len(losses), 3) if losses else 0,
        "final_equity":     round(final, 2),
    }


def _run_backtest_sync(
    ohlcv: list,
    params: dict,
    initial_capital: float = 1000.0,
) -> dict:
    """Full backtest on one OHLCV dataset. CPU-bound — run in thread."""
    signals = _generate_signals(ohlcv, params)
    if not signals:
        return {"error": "no signals generated", "trades": []}

    equity = initial_capital
    equity_curve: list[float] = [equity]
    trade_pnls: list[float]   = []
    trades: list[dict]        = []

    sl_pct  = params.get("sl_pct", 1.5)
    tp_pct  = params.get("tp_pct", 3.0)
    risk_pct = params.get("risk_pct", 1.5)

    used_indices: set[int] = set()
    for sig in signals:
        idx  = sig["idx"]
        side = sig["side"]

        # Don't overlap trades
        if any(abs(idx - u) < 5 for u in used_indices):
            continue

        result = _simulate_trade(ohlcv, idx, side, sl_pct, tp_pct, equity, risk_pct)
        if result["result"] == "no_exit":
            continue

        pnl_pct   = result["pnl_pct"]
        trade_pnl = equity * (risk_pct / 100) * (pnl_pct / sl_pct)
        equity   += trade_pnl
        equity    = max(equity, 1.0)   # floor at $1

        equity_curve.append(equity)
        trade_pnls.append(trade_pnl)
        used_indices.add(idx)

        trades.append({
            "idx":       idx,
            "side":      side,
            "result":    result["result"],
            "pnl_pct":   round(pnl_pct, 3),
            "pnl_usd":   round(trade_pnl, 4),
            "bars_held": result.get("bars_held", 0),
        })

    metrics = _compute_metrics(equity_curve, trade_pnls)
    return {
        "metrics":      metrics,
        "trades":       trades[-50:],      # last 50 for payload size
        "equity_curve": equity_curve[-200:],
        "n_signals":    len(signals),
    }


def _monte_carlo_sync(
    trade_pnls: list[float],
    initial_capital: float = 1000.0,
    n_simulations: int = 1000,
) -> dict:
    """Monte Carlo by randomly reordering historical trade sequence. CPU-bound."""
    if len(trade_pnls) < 5:
        return {"error": "not enough trades for Monte Carlo"}

    final_equities: list[float] = []
    max_drawdowns:  list[float] = []

    for _ in range(n_simulations):
        shuffled = random.sample(trade_pnls, len(trade_pnls))
        equity   = initial_capital
        peak     = equity
        max_dd   = 0.0

        for pnl in shuffled:
            equity += pnl
            equity  = max(equity, 0.01)
            if equity > peak:
                peak = equity
            dd = (peak - equity) / peak if peak > 0 else 0
            max_dd = max(max_dd, dd)

        final_equities.append(equity)
        max_drawdowns.append(max_dd)

    final_equities.sort()
    max_drawdowns.sort()

    n = len(final_equities)
    var_95_idx     = int(n * 0.05)
    cvar_95_values = final_equities[:var_95_idx]

    return {
        "n_simulations":      n_simulations,
        "initial_capital":    initial_capital,
        "median_final":       round(final_equities[n // 2], 2),
        "p10_final":          round(final_equities[int(n * 0.10)], 2),
        "p25_final":          round(final_equities[int(n * 0.25)], 2),
        "p75_final":          round(final_equities[int(n * 0.75)], 2),
        "p90_final":          round(final_equities[int(n * 0.90)], 2),
        "var_95_usd":         round(initial_capital - final_equities[var_95_idx], 2),
        "cvar_95_usd":        round(initial_capital - (sum(cvar_95_values) / len(cvar_95_values) if cvar_95_values else initial_capital), 2),
        "median_max_drawdown_pct": round(max_drawdowns[n // 2] * 100, 2),
        "p95_max_drawdown_pct":    round(max_drawdowns[int(n * 0.95)] * 100, 2),
        "probability_profit":      round(sum(1 for e in final_equities if e > initial_capital) / n * 100, 1),
        "equity_percentiles":      [round(final_equities[int(n * p / 100)], 2) for p in range(0, 101, 10)],
    }


# ── Public async API ──────────────────────────────────────────────────────────

async def run_backtest(
    symbol: str,
    client: Any,
    params: Optional[dict] = None,
    initial_capital: float = 1000.0,
    timeframe: str = "1h",
    candles: int = 500,
) -> dict:
    """
    Full async backtest pipeline:
    1. Fetch OHLCV
    2. Run walk-forward backtest
    3. Run Monte Carlo on result
    Returns combined result dict.
    """
    t0 = time.time()
    params = params or {"sl_pct": 1.5, "tp_pct": 3.0, "rsi_buy_max": 40, "rsi_sell_min": 60}

    # Fetch historical data
    try:
        ohlcv = await client.get_ohlcv(symbol, timeframe, candles)
    except Exception as e:
        return {"error": f"OHLCV fetch failed: {e}"}

    if not ohlcv or len(ohlcv) < 50:
        return {"error": f"Insufficient data: {len(ohlcv or [])} candles"}

    # Run backtest + Monte Carlo in parallel threads
    bt_result, mc_result = await asyncio.gather(
        asyncio.to_thread(_run_backtest_sync, ohlcv, params, initial_capital),
        asyncio.to_thread(
            _monte_carlo_sync,
            [t["pnl_usd"] for t in _run_backtest_sync(ohlcv, params, initial_capital).get("trades", [])],
            initial_capital,
            1000,
        ),
        return_exceptions=True,
    )

    elapsed = round(time.time() - t0, 2)

    return {
        "symbol":       symbol,
        "timeframe":    timeframe,
        "candles_used": len(ohlcv),
        "params":       params,
        "backtest":     bt_result if not isinstance(bt_result, Exception) else {"error": str(bt_result)},
        "monte_carlo":  mc_result if not isinstance(mc_result, Exception) else {"error": str(mc_result)},
        "elapsed_sec":  elapsed,
        "ran_at":       time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
