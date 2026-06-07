"""
KellyCriterion — حجم الصفقة الأمثل بمعيار كيلي  (T009)

صيغة Half-Kelly (الأكثر أماناً للتداول):
  f* = (p × b − q) / b    [Full Kelly]
  f  = f* / 2              [Half Kelly — يُقلّل التذبذب 50%]

حيث:
  p = احتمالية الربح (win rate)
  q = 1 − p
  b = نسبة متوسط الربح / متوسط الخسارة

مصادر البيانات (بالأولوية):
  1. إحصاءات لكل رمز/نمط محدد
  2. إحصاءات عامة عبر كل الصفقات
  3. قيمة افتراضية آمنة (1.5%)

الحدود:
  • الحد الأدنى: 0.5% (لا تقل عنها أبداً)
  • الحد الأقصى: 3.0% (لا تتجاوزه أبداً)
  • إذا كان Kelly سالباً → 0.5% (إشارة سيئة)
"""

import math
from typing import Optional

MIN_RISK_PCT = 0.5    # الحد الأدنى المطلق
MAX_RISK_PCT = 3.0    # الحد الأقصى المطلق
DEFAULT_PCT  = 1.5    # قيمة افتراضية آمنة
MIN_TRADES   = 10     # أقل عدد صفقات لحساب موثوق


def compute_kelly(
    win_rate: float,    # 0.0–1.0
    avg_win: float,     # متوسط الربح (موجب)
    avg_loss: float,    # متوسط الخسارة (موجب — بالقيمة المطلقة)
    half_kelly: bool = True,
) -> float:
    """
    Compute Kelly fraction as a percentage of capital to risk.

    Returns risk percentage (0.5–3.0).
    """
    if win_rate <= 0 or avg_loss <= 0 or avg_win <= 0:
        return DEFAULT_PCT

    q = 1.0 - win_rate
    b = avg_win / avg_loss    # Reward:Risk ratio

    kelly_full = (win_rate * b - q) / b

    if kelly_full <= 0:
        return MIN_RISK_PCT    # negative Kelly = bad edge → minimum position

    kelly = kelly_full / 2 if half_kelly else kelly_full

    # Convert to percentage and apply hard limits
    risk_pct = kelly * 100
    risk_pct = max(MIN_RISK_PCT, min(MAX_RISK_PCT, risk_pct))
    return round(risk_pct, 2)


def compute_kelly_from_trades(
    closed_trades: list[dict],
    symbol: Optional[str] = None,
    pattern: Optional[str] = None,
) -> dict:
    """
    Compute Kelly from historical trade data with optional symbol/pattern filter.

    Returns full analysis dict including the recommended risk %.
    """
    # Filter trades
    filtered = closed_trades
    if symbol:
        filtered = [t for t in filtered if t.get("symbol") == symbol]
    if pattern:
        filtered = [t for t in filtered if pattern.lower() in str(t.get("pattern", "")).lower()]

    # Need enough trades for reliable statistics
    if len(filtered) < MIN_TRADES:
        # Fallback to all trades if filtered set too small
        if len(closed_trades) >= MIN_TRADES and (symbol or pattern):
            filtered = closed_trades
        else:
            return {
                "risk_pct":     DEFAULT_PCT,
                "source":       "default",
                "reason":       f"insufficient data ({len(filtered)} trades, need {MIN_TRADES})",
                "n_trades":     len(filtered),
                "win_rate":     None,
                "kelly_full":   None,
                "kelly_half":   None,
            }

    # Compute stats
    wins   = [t for t in filtered if float(t.get("pnl") or 0) > 0]
    losses = [t for t in filtered if float(t.get("pnl") or 0) <= 0]

    win_rate = len(wins) / len(filtered)
    avg_win  = sum(float(t.get("pnl") or 0) for t in wins)  / len(wins)  if wins  else 0
    avg_loss = abs(sum(float(t.get("pnl") or 0) for t in losses) / len(losses)) if losses else avg_win

    q = 1.0 - win_rate
    b = avg_win / avg_loss if avg_loss > 0 else 1.0

    kelly_full = (win_rate * b - q) / b if b > 0 else -1
    kelly_half = kelly_full / 2
    risk_pct   = max(MIN_RISK_PCT, min(MAX_RISK_PCT, kelly_half * 100)) if kelly_full > 0 else MIN_RISK_PCT

    filter_desc = []
    if symbol:  filter_desc.append(f"symbol={symbol}")
    if pattern: filter_desc.append(f"pattern={pattern}")
    source = "/".join(filter_desc) if filter_desc else "all_trades"

    return {
        "risk_pct":     round(risk_pct, 2),
        "source":       source,
        "reason":       (
            f"Kelly={kelly_full*100:.1f}% → Half={kelly_half*100:.1f}% | "
            f"WR={win_rate*100:.0f}% B={b:.2f} ({len(filtered)} trades)"
        ),
        "n_trades":     len(filtered),
        "win_rate":     round(win_rate, 4),
        "avg_win_usd":  round(avg_win, 4),
        "avg_loss_usd": round(avg_loss, 4),
        "reward_risk":  round(b, 3),
        "kelly_full":   round(kelly_full * 100, 2),
        "kelly_half":   round(kelly_half * 100, 2),
        "applied_pct":  round(risk_pct, 2),
    }


class KellyPositionSizer:
    """
    Drop-in replacement for the fixed RiskManager.calculate_position_size.
    Uses per-symbol Kelly fractions when available, falls back gracefully.
    """

    def __init__(self, closed_trades: list[dict]) -> None:
        self._trades = closed_trades
        self._cache:  dict[str, dict] = {}

    def get_kelly_result(self, symbol: str, pattern: str = "") -> dict:
        key = f"{symbol}|{pattern}"
        if key not in self._cache:
            self._cache[key] = compute_kelly_from_trades(
                self._trades, symbol=symbol, pattern=pattern or None,
            )
        return self._cache[key]

    def position_size(
        self,
        symbol: str,
        total_balance: float,
        entry_price: float,
        stop_loss_percent: float,
        pattern: str = "",
    ) -> tuple[float, dict]:
        """
        Returns (quantity, kelly_result_dict).
        Uses Kelly-derived risk %, then computes quantity same way as RiskManager.
        """
        kr = self.get_kelly_result(symbol, pattern)
        risk_pct = kr["risk_pct"]

        if total_balance <= 0 or entry_price <= 0 or stop_loss_percent <= 0:
            return 0.0, kr

        max_risk_amount    = total_balance * (risk_pct / 100)
        stop_loss_distance = entry_price * (stop_loss_percent / 100)
        quantity           = max_risk_amount / stop_loss_distance

        # Cap at 50% of balance
        max_quantity = (total_balance * 0.5) / entry_price
        quantity     = min(quantity, max_quantity)

        return round(quantity, 6), kr
