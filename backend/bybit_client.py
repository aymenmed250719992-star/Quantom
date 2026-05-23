"""
Exchange client — singleton with persistent connection.

DEMO  : Public market data (no API key needed) + in-memory paper trading
LIVE  : Real API keys required

Set env vars:
  EXCHANGE_MODE   = demo | live                    (default: demo)
  EXCHANGE_NAME   = mexc | kucoin | binance        (default: mexc)

For LIVE + MEXC (works from US/Replit servers — RECOMMENDED):
  MEXC_API_KEY, MEXC_API_SECRET

For LIVE + KuCoin (blocked from US IPs):
  KUCOIN_API_KEY, KUCOIN_API_SECRET, KUCOIN_API_PASSPHRASE

For LIVE + Binance (deployed non-US server only):
  BINANCE_API_KEY, BINANCE_API_SECRET
"""

import os
import time
from typing import Any, Optional

from dotenv import load_dotenv

load_dotenv()


class IslamicViolationError(Exception):
    """Hard block on any non-spot order — Islamic finance compliance."""
    pass


class ExchangeClient:
    """
    Singleton exchange client with a single persistent ccxt connection.
    Never call close() between individual requests — only call it at shutdown.
    """

    _instance: Optional["ExchangeClient"] = None

    @classmethod
    def get_instance(cls) -> "ExchangeClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Call this when switching mode at runtime."""
        cls._instance = None

    # ──────────────────────────────────────────────────────────────────────────
    def __init__(self) -> None:
        self.mode: str = os.environ.get("EXCHANGE_MODE", "demo").lower()
        self.exchange_name: str = os.environ.get("EXCHANGE_NAME", "mexc").lower()

        # Always read from env so _has_credentials reflects what is saved
        KNOWN = {"mexc", "kucoin", "binance", "bybit"}
        if self.exchange_name not in KNOWN:
            self.exchange_name = "mexc"

        if self.exchange_name == "binance":
            api_key        = os.environ.get("BINANCE_API_KEY", "")
            api_secret     = os.environ.get("BINANCE_API_SECRET", "")
            api_passphrase = ""
        elif self.exchange_name == "kucoin":
            api_key        = os.environ.get("KUCOIN_API_KEY", "")
            api_secret     = os.environ.get("KUCOIN_API_SECRET", "")
            api_passphrase = os.environ.get("KUCOIN_API_PASSPHRASE", "")
        elif self.exchange_name == "bybit":
            api_key        = os.environ.get("BYBIT_API_KEY", "")
            api_secret     = os.environ.get("BYBIT_API_SECRET", "")
            api_passphrase = ""
        else:  # mexc (default — works from US/Replit IPs)
            self.exchange_name = "mexc"
            api_key        = os.environ.get("MEXC_API_KEY", "")
            api_secret     = os.environ.get("MEXC_API_SECRET", "")
            api_passphrase = ""

        # Track whether credentials are configured (independent of mode)
        self._has_credentials: bool = bool(api_key and api_secret)

        import ccxt.async_support as ccxt_async

        # Only inject auth into ccxt when in live mode (demo = paper trading only)
        opts: dict[str, Any] = {"options": {"defaultType": "spot"}}
        if self.mode == "live" and api_key:
            opts["apiKey"] = api_key
        if self.mode == "live" and api_secret:
            opts["secret"] = api_secret
        if self.mode == "live" and api_passphrase:
            opts["password"] = api_passphrase

        self._exchange = getattr(ccxt_async, self.exchange_name)(opts)

        # Paper-trading state (DEMO)
        self._paper_balance: float = float(os.environ.get("DEMO_BALANCE_USDT", "10000"))
        self._paper_counter: int = 0

        print(
            f"[ExchangeClient] mode={self.mode} exchange={self.exchange_name} "
            f"credentials={'YES' if self._has_credentials else 'NO (public data only)'}"
        )

    # ──────────────────────────────────────────────────────────────────────────
    def _enforce_spot_only(self, order_type: str) -> None:
        forbidden = {"futures", "margin", "perpetual", "swap", "leveraged", "cross", "isolated"}
        if order_type.lower() in forbidden:
            raise IslamicViolationError(
                f"HARD BLOCK: '{order_type}' violates Islamic finance rules. "
                "Only halal spot trading is allowed."
            )

    # ──────────────────────────────────────────────────────────────────────────
    # Market data — always uses public endpoints, no auth required
    # ──────────────────────────────────────────────────────────────────────────

    async def get_ohlcv(self, symbol: str, timeframe: str = "15m", limit: int = 100) -> list:
        try:
            return await self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        except Exception as e:
            print(f"[ExchangeClient] get_ohlcv error {symbol}: {e}")
            return []

    async def get_ticker(self, symbol: str) -> dict:
        try:
            return await self._exchange.fetch_ticker(symbol)
        except Exception as e:
            print(f"[ExchangeClient] get_ticker error {symbol}: {e}")
            return {}

    async def get_current_price(self, symbol: str) -> float:
        ticker = await self.get_ticker(symbol)
        return float(ticker.get("last", 0) or 0)

    # ──────────────────────────────────────────────────────────────────────────
    # Account data
    # ──────────────────────────────────────────────────────────────────────────

    async def get_balance(self) -> dict:
        base = {"currency": "USDT", "mode": self.mode, "exchange": self.exchange_name}

        if self.mode == "demo" or not self._has_credentials:
            return {**base, "total": round(self._paper_balance, 4), "free": round(self._paper_balance, 4), "used": 0.0}

        try:
            raw = await self._exchange.fetch_balance()
            usdt = raw.get("USDT", {})
            return {
                **base,
                "total": float(usdt.get("total") or 0),
                "free": float(usdt.get("free") or 0),
                "used": float(usdt.get("used") or 0),
            }
        except Exception as e:
            return {**base, "total": 0.0, "free": 0.0, "used": 0.0, "error": str(e)[:120]}

    # ──────────────────────────────────────────────────────────────────────────
    # Orders
    # ──────────────────────────────────────────────────────────────────────────

    async def place_spot_order(
        self,
        symbol: str,
        side: str,
        quantity: float,
        price: Optional[float] = None,
        order_type: str = "market",
    ) -> dict:
        self._enforce_spot_only(order_type)

        # ── DEMO paper order ──────────────────────────────────────────────────
        if self.mode == "demo" or not self._has_credentials:
            self._paper_counter += 1
            order_id = f"PAPER-{self._paper_counter:04d}"
            print(f"[Paper] {side.upper()} {quantity:.6f} {symbol} @ {price} [{order_id}]")
            return {
                "id": order_id,
                "symbol": symbol,
                "side": side,
                "amount": quantity,
                "price": price,
                "status": "closed",
                "type": order_type,
                "demo": True,
            }

        # ── LIVE real order ───────────────────────────────────────────────────
        try:
            if order_type == "market":
                return await self._exchange.create_market_order(symbol, side, quantity)
            if price is None:
                raise ValueError("Price required for limit orders")
            return await self._exchange.create_limit_order(symbol, side, quantity, price)
        except IslamicViolationError:
            raise
        except Exception as e:
            raise RuntimeError(f"Order failed: {e}") from e

    async def cancel_order(self, order_id: str, symbol: str) -> dict:
        if self.mode == "demo" or not self._has_credentials:
            return {"id": order_id, "status": "canceled", "demo": True}
        try:
            return await self._exchange.cancel_order(order_id, symbol)
        except Exception as e:
            raise RuntimeError(f"Cancel failed: {e}") from e

    async def get_open_orders(self, symbol: Optional[str] = None) -> list:
        if self.mode == "demo" or not self._has_credentials:
            return []
        try:
            return await self._exchange.fetch_open_orders(symbol)
        except Exception as e:
            print(f"[ExchangeClient] get_open_orders error: {e}")
            return []

    # ──────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    async def close(self) -> None:
        """Call ONLY at application shutdown, never between requests."""
        try:
            await self._exchange.close()
        except Exception:
            pass


# ── Backwards-compatible alias ────────────────────────────────────────────────
BybitClient = ExchangeClient
