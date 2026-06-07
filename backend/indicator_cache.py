"""
IndicatorCache — كاش مشترك للمؤشرات التقنية عبر كل المكونات

يمنع إعادة حساب RSI / MACD / BB لنفس الرمز أكثر من مرة في دورة الفحص الواحدة.
TTL افتراضي: 4 دقائق (أقل من أي فاصل فحص)

الاستخدام:
    cache = IndicatorCache.get_instance()
    data = await cache.get_or_fetch(symbol, fetch_fn, timeframe="15m", limit=100)
"""

import asyncio
import time
from typing import Any, Callable, Coroutine, Optional


class _CacheEntry:
    __slots__ = ("value", "expires_at", "lock")

    def __init__(self, value: Any, ttl: float):
        self.value      = value
        self.expires_at = time.monotonic() + ttl
        self.lock       = asyncio.Lock()

    def is_fresh(self) -> bool:
        return time.monotonic() < self.expires_at


class IndicatorCache:
    """
    Thread-safe async TTL cache for OHLCV + computed indicators.

    Keys are (symbol, timeframe, limit) tuples.
    Two simultaneous fetches for the same key collapse into one request (dogpile prevention).
    """

    _instance: Optional["IndicatorCache"] = None

    DEFAULT_TTL: float = 240.0   # 4 دقائق
    OHLCV_TTL:   float = 120.0   # 2 دقيقة للبيانات الخام
    IND_TTL:     float = 240.0   # 4 دقائق للمؤشرات المحسوبة

    @classmethod
    def get_instance(cls) -> "IndicatorCache":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """مسح الكاش (بداية دورة فحص جديدة)."""
        if cls._instance:
            cls._instance._store.clear()
            cls._instance._locks.clear()

    def __init__(self) -> None:
        self._store: dict[str, _CacheEntry] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._hits   = 0
        self._misses = 0

    # ─────────────────────────────────────────────────────────────────────────

    def _key(self, symbol: str, kind: str, timeframe: str = "", limit: int = 0) -> str:
        return f"{symbol}|{kind}|{timeframe}|{limit}"

    def _get_lock(self, key: str) -> asyncio.Lock:
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    # ─── OHLCV ───────────────────────────────────────────────────────────────

    async def get_ohlcv(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        fetch_fn: Callable[..., Coroutine],
    ) -> Optional[list]:
        """
        Fetches OHLCV via fetch_fn(symbol, timeframe, limit) and caches result.
        Collapses concurrent calls for the same key into one network request.
        """
        key = self._key(symbol, "ohlcv", timeframe, limit)
        lock = self._get_lock(key)

        async with lock:
            entry = self._store.get(key)
            if entry and entry.is_fresh():
                self._hits += 1
                return entry.value

            self._misses += 1
            try:
                value = await fetch_fn(symbol, timeframe, limit)
                self._store[key] = _CacheEntry(value, self.OHLCV_TTL)
                return value
            except Exception as e:
                print(f"[IndicatorCache] OHLCV fetch error {symbol}/{timeframe}: {e}")
                return None

    # ─── Indicators ──────────────────────────────────────────────────────────

    async def get_indicators(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        ohlcv_data: list,
        compute_fn: Callable,
    ) -> Optional[dict]:
        """
        Computes indicators from ohlcv_data via compute_fn(ohlcv_data) and caches.
        compute_fn is CPU-bound, so runs in a thread to avoid blocking the event loop.
        """
        key = self._key(symbol, "indicators", timeframe, limit)
        lock = self._get_lock(key)

        async with lock:
            entry = self._store.get(key)
            if entry and entry.is_fresh():
                self._hits += 1
                return entry.value

            self._misses += 1
            try:
                value = await asyncio.to_thread(compute_fn, ohlcv_data)
                self._store[key] = _CacheEntry(value, self.IND_TTL)
                return value
            except Exception as e:
                print(f"[IndicatorCache] Indicator compute error {symbol}: {e}")
                return None

    # ─── Generic ─────────────────────────────────────────────────────────────

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[[], Any],
        ttl: float = DEFAULT_TTL,
        run_in_thread: bool = False,
    ) -> Any:
        """Generic cache entry with optional thread offloading."""
        lock = self._get_lock(key)
        async with lock:
            entry = self._store.get(key)
            if entry and entry.is_fresh():
                self._hits += 1
                return entry.value

            self._misses += 1
            value = (
                await asyncio.to_thread(compute_fn)
                if run_in_thread
                else (await compute_fn() if asyncio.iscoroutinefunction(compute_fn) else compute_fn())
            )
            self._store[key] = _CacheEntry(value, ttl)
            return value

    # ─── Invalidation ────────────────────────────────────────────────────────

    def invalidate(self, symbol: str) -> None:
        """Evict all cache entries for a given symbol."""
        keys_to_drop = [k for k in self._store if k.startswith(f"{symbol}|")]
        for k in keys_to_drop:
            self._store.pop(k, None)
            self._locks.pop(k, None)

    def clear(self) -> None:
        self._store.clear()
        self._locks.clear()

    # ─── Stats ───────────────────────────────────────────────────────────────

    def stats(self) -> dict:
        total  = self._hits + self._misses
        ratio  = self._hits / total if total else 0.0
        fresh  = sum(1 for e in self._store.values() if e.is_fresh())
        return {
            "hits":      self._hits,
            "misses":    self._misses,
            "hit_ratio": round(ratio, 3),
            "cached_entries": len(self._store),
            "fresh_entries":  fresh,
        }
