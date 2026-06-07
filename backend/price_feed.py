"""
PriceFeed — WebSocket Real-Time Price Feed  (T001)

يستقبل أسعاراً حية من البورصة عبر WebSocket ويُذيعها لجميع المشتركين.
يستخدم ccxt.pro (watch_ticker) للاتصال الحي.
Fallback: polling عادي كل 10 ثوانٍ لو ccxt.pro غير متاح.

الاستخدام:
    feed = PriceFeed.get_instance()
    await feed.start(symbols)
    price = feed.get_price("BTC/USDT")
    feed.subscribe(callback)     # يُستدعى عند كل تحديث
"""

import asyncio
import time
from typing import Any, Callable, Optional


class PriceFeed:
    """
    Singleton real-time price cache.
    Provides sub-second price updates for all watched symbols.
    """

    _instance: Optional["PriceFeed"] = None

    POLL_INTERVAL: float = 10.0       # fallback polling interval (seconds)
    STALE_THRESHOLD: float = 60.0     # price older than this is considered stale

    @classmethod
    def get_instance(cls) -> "PriceFeed":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._prices: dict[str, float]        = {}   # symbol → latest price
        self._timestamps: dict[str, float]    = {}   # symbol → epoch when last updated
        self._subscribers: list[Callable]     = []   # callbacks(symbol, price)
        self._watched: set[str]               = set()
        self._running: bool                   = False
        self._task: Optional[asyncio.Task]    = None
        self._poll_task: Optional[asyncio.Task] = None
        self._client: Any                     = None
        self._lock = asyncio.Lock()

    # ── Public API ────────────────────────────────────────────────────────────

    def get_price(self, symbol: str) -> Optional[float]:
        """Return cached price, or None if stale / unknown."""
        ts = self._timestamps.get(symbol, 0)
        if time.time() - ts > self.STALE_THRESHOLD:
            return None
        return self._prices.get(symbol)

    def get_all_prices(self) -> dict[str, float]:
        """Return all fresh prices."""
        now = time.time()
        return {
            s: p for s, p in self._prices.items()
            if now - self._timestamps.get(s, 0) <= self.STALE_THRESHOLD
        }

    def is_fresh(self, symbol: str) -> bool:
        return (time.time() - self._timestamps.get(symbol, 0)) <= self.STALE_THRESHOLD

    def subscribe(self, callback: Callable) -> None:
        """Register callback(symbol: str, price: float) for live updates."""
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable) -> None:
        self._subscribers.discard(callback) if hasattr(self._subscribers, 'discard') else None
        try:
            self._subscribers.remove(callback)
        except ValueError:
            pass

    async def start(self, symbols: list[str]) -> None:
        """Start the price feed for the given symbols."""
        async with self._lock:
            new_syms = set(symbols) - self._watched
            self._watched.update(symbols)
            if not self._running:
                self._running = True
                self._task = asyncio.create_task(self._run_feed(), name="price_feed")
                print(f"[PriceFeed] ▶ Started — watching {len(self._watched)} symbol(s)")
            elif new_syms:
                print(f"[PriceFeed] + Added symbols: {new_syms}")

    async def stop(self) -> None:
        self._running = False
        for t in (self._task, self._poll_task):
            if t and not t.done():
                t.cancel()
                try:
                    await t
                except asyncio.CancelledError:
                    pass
        print("[PriceFeed] ■ Stopped")

    # ── Feed runner ──────────────────────────────────────────────────────────

    async def _run_feed(self) -> None:
        """Try WebSocket feed first, fall back to polling."""
        ws_ok = await self._try_ws_feed()
        if not ws_ok:
            print("[PriceFeed] WebSocket unavailable — using polling fallback")
            await self._poll_loop()

    async def _try_ws_feed(self) -> bool:
        """
        Attempt ccxt.pro WebSocket streaming.
        Returns False if ccxt.pro is not installed or exchange unsupported.
        """
        try:
            import ccxt.pro as ccxt_pro
            import os
            from exchange_router import ExchangeRouter

            exchange_name = ExchangeRouter.get_instance().active
            ex_class = getattr(ccxt_pro, exchange_name, None)
            if ex_class is None:
                return False

            ex = ex_class({"options": {"defaultType": "spot"}})
            self._client = ex

            print(f"[PriceFeed] ✅ WebSocket connected to {exchange_name}")

            syms = list(self._watched)
            while self._running:
                try:
                    tasks = [ex.watch_ticker(s) for s in syms if s]
                    tickers = await asyncio.gather(*tasks, return_exceptions=True)
                    for sym, ticker in zip(syms, tickers):
                        if isinstance(ticker, Exception):
                            continue
                        price = float(ticker.get("last") or ticker.get("close") or 0)
                        if price > 0:
                            await self._update_price(sym, price)
                    # Refresh symbol list
                    syms = list(self._watched)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    print(f"[PriceFeed] WS error: {e} — retrying in 5s")
                    await asyncio.sleep(5)

            try:
                await ex.close()
            except Exception:
                pass
            return True

        except ImportError:
            return False
        except Exception as e:
            print(f"[PriceFeed] WS init error: {e}")
            return False

    async def _poll_loop(self) -> None:
        """Fallback: fetch prices via REST every POLL_INTERVAL seconds."""
        from bybit_client import ExchangeClient
        client = ExchangeClient.get_instance()

        while self._running:
            syms = list(self._watched)
            for sym in syms:
                if not self._running:
                    break
                try:
                    price = await client.get_current_price(sym)
                    if price > 0:
                        await self._update_price(sym, price)
                except Exception as e:
                    print(f"[PriceFeed] Poll error {sym}: {e}")
            await asyncio.sleep(self.POLL_INTERVAL)

    async def _update_price(self, symbol: str, price: float) -> None:
        """Update internal cache and notify subscribers."""
        old = self._prices.get(symbol, 0)
        self._prices[symbol]     = price
        self._timestamps[symbol] = time.time()

        if abs(price - old) / (old or price) > 0.0001:   # notify only on >0.01% change
            for cb in list(self._subscribers):
                try:
                    if asyncio.iscoroutinefunction(cb):
                        asyncio.create_task(cb(symbol, price))
                    else:
                        cb(symbol, price)
                except Exception:
                    pass

    # ── Stats ─────────────────────────────────────────────────────────────────

    def status(self) -> dict:
        now = time.time()
        fresh = {s: p for s, p in self._prices.items()
                 if now - self._timestamps.get(s, 0) <= self.STALE_THRESHOLD}
        return {
            "running":      self._running,
            "watched":      list(self._watched),
            "fresh_prices": fresh,
            "stale_count":  len(self._prices) - len(fresh),
            "subscribers":  len(self._subscribers),
            "mode":         "websocket" if (self._client is not None) else "polling",
        }
