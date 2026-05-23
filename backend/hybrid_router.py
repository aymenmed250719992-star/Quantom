"""
HybridRouter — يختار تلقائياً بين DEX (بلوكشين) وCEX (MEXC / غيره)

منطق الاختيار:
  1. يحصل على سعر DEX + تكلفة الـ Gas
  2. يحصل على سعر CEX
  3. إذا كان DEX أفضل (بعد طرح الـ Gas) → DEX
  4. إذا كانت السيولة ضعيفة على DEX أو السعر أسوأ → CEX
  5. إذا فشل DEX لأي سبب → CEX تلقائياً

إعدادات بيئة التشغيل:
  HYBRID_MODE    — auto | dex_only | cex_only   (افتراضي: auto)
  CEX_ADVANTAGE  — فارق السعر بالـ% الذي يجعل CEX أفضل (افتراضي: 0.3)
"""

import asyncio
import os
import time
from typing import Optional


class HybridRouter:
    """يوجّه الأوامر بين DEX وCEX باختيار الأفضل تلقائياً."""

    _instance: Optional["HybridRouter"] = None

    @classmethod
    def get_instance(cls) -> "HybridRouter":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self.mode: str = os.environ.get("HYBRID_MODE", "auto")
        # فارق السعر (%) الذي يجعل CEX يُفضّل على DEX
        self.cex_advantage_pct: float = float(os.environ.get("CEX_ADVANTAGE", "0.3"))
        self._stats: dict = {
            "dex_trades":      0,
            "cex_trades":      0,
            "dex_savings_usd": 0.0,
            "last_route":      "—",
            "last_reason":     "—",
        }

    # ── Public API ────────────────────────────────────────────────────────────

    async def decide_route(
        self,
        symbol:        str,
        side:          str,       # "buy" | "sell"
        amount_usdt:   float,
        cex_price:     float,     # سعر CEX الحالي بالـ USDT
        native_price:  float = 0, # سعر العملة الأصلية (ETH/MATIC/BNB) بالـ USDT
    ) -> dict:
        """
        يُقرّر أفضل مسار.

        Returns:
          {
            "route":       "dex" | "cex",
            "reason":      str,             # شرح القرار
            "dex_price":   float | None,
            "cex_price":   float,
            "gas_usd":     float,
            "saving_usd":  float,           # الفرق لصالح المسار المختار
            "dex_quote":   dict | None,     # نتيجة الـ quoter
          }
        """
        if self.mode == "cex_only":
            return self._route_cex(cex_price, reason="الوضع: CEX فقط")
        if self.mode == "dex_only":
            return await self._route_dex_only(symbol, amount_usdt, cex_price, native_price)

        # ── وضع Auto ──────────────────────────────────────────────────────────
        try:
            from dex_client import DexClient
            dex = DexClient.get_instance()

            if not dex._connected:
                return self._route_cex(cex_price, reason="DEX غير متصل — CEX احتياطي")

            # الحصول على سعر DEX
            dex_quote = await dex.get_dex_price(symbol, amount_usdt)
            if not dex_quote["success"]:
                return self._route_cex(
                    cex_price,
                    reason=f"DEX: {dex_quote['error']} — CEX احتياطي",
                )

            dex_price = dex_quote["price"]

            # تكلفة الـ Gas
            gas_usd = await dex.estimate_gas_cost_usd(native_price or cex_price)

            # مقارنة الأسعار بعد الـ Gas
            # BUY: نريد أقل سعر
            if side == "buy":
                dex_effective = dex_price + (gas_usd / (amount_usdt / dex_price))
                diff_pct = (dex_effective - cex_price) / cex_price * 100
                dex_wins = diff_pct < self.cex_advantage_pct
            else:  # SELL
                dex_effective = dex_price - (gas_usd / (amount_usdt / dex_price))
                diff_pct = (cex_price - dex_effective) / cex_price * 100
                dex_wins = diff_pct < self.cex_advantage_pct

            saving_usd = abs(dex_price - cex_price) * (amount_usdt / cex_price) - gas_usd

            if dex_wins:
                self._stats["dex_trades"] += 1
                self._stats["dex_savings_usd"] += max(saving_usd, 0)
                reason = (
                    f"DEX أفضل: {dex_price:.4f} vs CEX {cex_price:.4f}"
                    f" (فرق {diff_pct:+.2f}%) | gas ~${gas_usd:.3f}"
                )
                self._stats.update({"last_route": "dex", "last_reason": reason})
                return {
                    "route": "dex", "reason": reason,
                    "dex_price": dex_price, "cex_price": cex_price,
                    "gas_usd": round(gas_usd, 4), "saving_usd": round(saving_usd, 4),
                    "dex_quote": dex_quote,
                }
            else:
                reason = (
                    f"CEX أفضل: {cex_price:.4f} vs DEX {dex_price:.4f}"
                    f" (فرق {diff_pct:+.2f}%) | gas ~${gas_usd:.3f}"
                )
                return self._route_cex(cex_price, reason=reason, dex_quote=dex_quote, gas_usd=gas_usd)

        except ImportError:
            return self._route_cex(cex_price, reason="DEX غير مثبّت — CEX احتياطي")
        except Exception as e:
            return self._route_cex(cex_price, reason=f"DEX خطأ ({e!s:.80}) — CEX احتياطي")

    async def execute_trade(
        self,
        symbol:       str,
        side:         str,
        amount_usdt:  float,
        cex_price:    float,
        cex_client:   object,
        quantity:     float,
        native_price: float = 0,
    ) -> dict:
        """
        يُنفّذ الصفقة عبر أفضل مسار.

        Returns dict with keys: route, success, order_id, price, message, ...
        """
        decision = await self.decide_route(symbol, side, amount_usdt, cex_price, native_price)
        route     = decision["route"]

        if route == "dex":
            try:
                from dex_client import DexClient
                dex = DexClient.get_instance()
                result = await dex.execute_swap(symbol, side, amount_usdt)
                if result["success"]:
                    self._stats["dex_trades"] += 1
                    return {**result, "route": "dex", "decision": decision}
                # DEX فشل → انتقل إلى CEX تلقائياً
                print(f"[Hybrid] DEX swap failed: {result.get('error')} — falling back to CEX")
            except Exception as e:
                print(f"[Hybrid] DEX exception: {e} — falling back to CEX")

        # CEX execution
        try:
            order = await cex_client.place_spot_order(symbol, side, quantity, price=cex_price)
            self._stats["cex_trades"] += 1
            self._stats["last_route"] = "cex"
            return {
                "route":    "cex",
                "success":  True,
                "order_id": order.get("id", "cex-order"),
                "price":    cex_price,
                "symbol":   symbol,
                "side":     side,
                "message":  f"✅ CEX — {symbol} {side.upper()} @ ${cex_price:.4f}",
                "decision": decision,
            }
        except Exception as e:
            return {"route": "cex", "success": False, "error": str(e), "decision": decision}

    def _route_cex(
        self,
        cex_price: float,
        reason: str = "",
        dex_quote: Optional[dict] = None,
        gas_usd: float = 0.0,
    ) -> dict:
        self._stats["cex_trades"] += 1
        self._stats.update({"last_route": "cex", "last_reason": reason})
        return {
            "route": "cex", "reason": reason,
            "dex_price": dex_quote["price"] if dex_quote and dex_quote.get("success") else None,
            "cex_price": cex_price, "gas_usd": gas_usd, "saving_usd": 0.0,
            "dex_quote": dex_quote,
        }

    async def _route_dex_only(
        self,
        symbol: str,
        amount_usdt: float,
        cex_price: float,
        native_price: float,
    ) -> dict:
        try:
            from dex_client import DexClient
            dex = DexClient.get_instance()
            quote = await dex.get_dex_price(symbol, amount_usdt)
            if quote["success"]:
                self._stats["dex_trades"] += 1
                reason = f"الوضع: DEX فقط | سعر: {quote['price']:.4f}"
                self._stats.update({"last_route": "dex", "last_reason": reason})
                return {
                    "route": "dex", "reason": reason,
                    "dex_price": quote["price"], "cex_price": cex_price,
                    "gas_usd": 0, "saving_usd": 0, "dex_quote": quote,
                }
            return self._route_cex(cex_price, reason=f"DEX only لكن فشل: {quote['error']}")
        except Exception as e:
            return self._route_cex(cex_price, reason=f"DEX only خطأ: {e}")

    def stats(self) -> dict:
        total = self._stats["dex_trades"] + self._stats["cex_trades"]
        return {
            "mode":            self.mode,
            "cex_advantage_pct": self.cex_advantage_pct,
            "total_trades":    total,
            "dex_trades":      self._stats["dex_trades"],
            "cex_trades":      self._stats["cex_trades"],
            "dex_pct":         round(100 * self._stats["dex_trades"] / total, 1) if total else 0,
            "dex_savings_usd": round(self._stats["dex_savings_usd"], 4),
            "last_route":      self._stats["last_route"],
            "last_reason":     self._stats["last_reason"],
        }

    def set_mode(self, mode: str) -> bool:
        if mode not in ("auto", "dex_only", "cex_only"):
            return False
        self.mode = mode
        os.environ["HYBRID_MODE"] = mode
        return True
