"""
PortfolioCorrelation — مصفوفة الارتباط وإدارة تشتّت المحفظة  (T005)

يحسب ارتباط عوائد الأزواج لمنع تركّز المخاطرة في اتجاه واحد.

مثال: ETH/BTC correlation = 0.87 — فتح كلاهما يُضاعف الخسارة.

القواعد:
  • correlation > 0.85 مع صفقة مفتوحة → BLOCK الصفقة الجديدة
  • correlation 0.70–0.85               → WARNING (تخفيض الحجم 50%)
  • correlation < 0.70                  → ALLOW

بيانات المدخلات: OHLCV من البورصة (آخر 30 شمعة يومية)
"""

import asyncio
import math
import time
from typing import Any, Optional


BLOCK_THRESHOLD   = 0.85   # ارتباط يمنع الصفقة
WARNING_THRESHOLD = 0.70   # ارتباط يُصدر تحذيراً
CACHE_TTL         = 3600.0  # 1 hour


class PortfolioCorrelation:

    _instance: Optional["PortfolioCorrelation"] = None

    @classmethod
    def get_instance(cls) -> "PortfolioCorrelation":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._matrix:    dict[tuple[str, str], float] = {}
        self._matrix_ts: float = 0.0
        self._returns:   dict[str, list[float]] = {}

    # ── Internal math ─────────────────────────────────────────────────────────

    @staticmethod
    def _returns_from_ohlcv(ohlcv: list) -> list[float]:
        closes = [float(c[4]) for c in ohlcv if len(c) > 4]
        if len(closes) < 2:
            return []
        return [(closes[i] - closes[i - 1]) / closes[i - 1] for i in range(1, len(closes))]

    @staticmethod
    def _pearson(x: list[float], y: list[float]) -> float:
        n = min(len(x), len(y))
        if n < 5:
            return 0.0
        x, y = x[-n:], y[-n:]
        mx, my = sum(x) / n, sum(y) / n
        num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
        dx  = math.sqrt(sum((xi - mx) ** 2 for xi in x))
        dy  = math.sqrt(sum((yi - my) ** 2 for yi in y))
        if dx == 0 or dy == 0:
            return 0.0
        return round(num / (dx * dy), 4)

    # ── Data loading ──────────────────────────────────────────────────────────

    async def refresh(self, symbols: list[str], client: Any) -> None:
        """Fetch daily OHLCV for all symbols and recompute correlation matrix."""
        if (time.time() - self._matrix_ts) < CACHE_TTL:
            return   # still fresh

        async def _fetch(sym: str) -> tuple[str, list[float]]:
            try:
                ohlcv = await client.get_ohlcv(sym, "1d", 30)
                returns = self._returns_from_ohlcv(ohlcv or [])
                return sym, returns
            except Exception:
                return sym, []

        results = await asyncio.gather(*[_fetch(s) for s in symbols], return_exceptions=True)
        self._returns = {}
        for r in results:
            if not isinstance(r, Exception) and r[1]:
                self._returns[r[0]] = r[1]

        # Build pairwise matrix
        syms = list(self._returns.keys())
        self._matrix = {}
        for i, a in enumerate(syms):
            for b in syms[i + 1:]:
                corr = self._pearson(self._returns[a], self._returns[b])
                self._matrix[(a, b)] = corr
                self._matrix[(b, a)] = corr

        self._matrix_ts = time.time()
        print(f"[Correlation] Matrix updated — {len(self._matrix) // 2} pairs | {len(syms)} symbols")

    # ── Trade guard ───────────────────────────────────────────────────────────

    def check_new_trade(
        self,
        new_symbol: str,
        open_symbols: list[str],
    ) -> dict:
        """
        Check if opening new_symbol would create dangerous correlation with open positions.

        Returns:
          {"allowed": bool, "action": "ALLOW"|"WARN"|"BLOCK",
           "max_correlation": float, "correlated_with": str|None, "size_factor": float}
        """
        if not open_symbols:
            return {"allowed": True, "action": "ALLOW", "max_correlation": 0.0,
                    "correlated_with": None, "size_factor": 1.0}

        max_corr   = 0.0
        corr_with  = None

        for open_sym in open_symbols:
            if open_sym == new_symbol:
                continue
            corr = abs(self._matrix.get((new_symbol, open_sym), 0.0))
            if corr > max_corr:
                max_corr = corr
                corr_with = open_sym

        if max_corr >= BLOCK_THRESHOLD:
            return {
                "allowed":          False,
                "action":           "BLOCK",
                "max_correlation":  max_corr,
                "correlated_with":  corr_with,
                "size_factor":      0.0,
                "reason":           f"❌ Correlation {max_corr:.2f} with {corr_with} — تجاوز الحد الأقصى {BLOCK_THRESHOLD}",
            }
        elif max_corr >= WARNING_THRESHOLD:
            return {
                "allowed":          True,
                "action":           "WARN",
                "max_correlation":  max_corr,
                "correlated_with":  corr_with,
                "size_factor":      0.5,    # تخفيض الحجم 50%
                "reason":           f"⚠️ Correlation {max_corr:.2f} مع {corr_with} — تقليص الحجم 50%",
            }
        else:
            return {
                "allowed":          True,
                "action":           "ALLOW",
                "max_correlation":  max_corr,
                "correlated_with":  corr_with,
                "size_factor":      1.0,
                "reason":           f"✅ Max correlation {max_corr:.2f} — آمن",
            }

    # ── Heat map data ─────────────────────────────────────────────────────────

    def heat_map(self) -> dict:
        """Return full correlation matrix formatted for UI heat map."""
        syms = sorted(set(s for pair in self._matrix.keys() for s in pair))
        matrix = []
        for a in syms:
            row = []
            for b in syms:
                if a == b:
                    row.append(1.0)
                else:
                    row.append(self._matrix.get((a, b), 0.0))
            matrix.append({"symbol": a, "values": row})

        return {
            "symbols":      syms,
            "matrix":       matrix,
            "updated_at":   self._matrix_ts,
            "thresholds":   {"block": BLOCK_THRESHOLD, "warn": WARNING_THRESHOLD},
        }

    def get_correlation(self, a: str, b: str) -> float:
        return self._matrix.get((a, b), 0.0)

    def status(self) -> dict:
        return {
            "pairs_tracked":  len(self._matrix) // 2,
            "symbols":        list(self._returns.keys()),
            "last_refresh":   self._matrix_ts,
            "cache_age_min":  round((time.time() - self._matrix_ts) / 60, 1),
        }
