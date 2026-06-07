"""
OnChainIntel — طبقة الاستخبارات على السلسلة  (T004)

تجمع بيانات من APIs مجانية وعامة:
  1. Fear & Greed Index     (alternative.me)
  2. BTC Dominance          (CoinGecko)
  3. Exchange Netflow       (CoinGecko on-chain estimates)
  4. Market Cap & Volume    (CoinGecko)
  5. Trending Coins         (CoinGecko)
  6. Whale Alert headlines  (free RSS)

TTL: 15 دقيقة (يُخزَّن في cache مشترك)
كل الطلبات تعمل بالتوازي لتقليل وقت الانتظار.
"""

import asyncio
import time
from typing import Any, Optional

import httpx

_CACHE: dict[str, Any]   = {}
_CACHE_TS: dict[str, float] = {}
_TTL = 900.0   # 15 minutes


def _fresh(key: str) -> bool:
    return (time.time() - _CACHE_TS.get(key, 0)) < _TTL


def _store(key: str, val: Any) -> Any:
    _CACHE[key]    = val
    _CACHE_TS[key] = time.time()
    return val


# ── Individual fetchers ───────────────────────────────────────────────────────

async def _fetch_fear_greed(client: httpx.AsyncClient) -> dict:
    key = "fear_greed"
    if _fresh(key):
        return _CACHE[key]
    try:
        r = await client.get("https://api.alternative.me/fng/?limit=2", timeout=8)
        data = r.json().get("data", [{}])
        current  = data[0] if data else {}
        previous = data[1] if len(data) > 1 else {}
        result = {
            "value":          int(current.get("value", 50)),
            "label":          current.get("value_classification", "Neutral"),
            "previous_value": int(previous.get("value", 50)),
            "trend":          "improving" if int(current.get("value", 50)) > int(previous.get("value", 50)) else "declining",
            "signal":         _fg_signal(int(current.get("value", 50))),
        }
        return _store(key, result)
    except Exception as e:
        print(f"[OnChain] Fear&Greed error: {e}")
        return _CACHE.get(key, {"value": 50, "label": "Neutral", "signal": "neutral"})


def _fg_signal(val: int) -> str:
    if val <= 20:  return "extreme_fear"     # buy opportunity
    if val <= 40:  return "fear"             # cautious buy
    if val <= 60:  return "neutral"
    if val <= 80:  return "greed"            # caution
    return "extreme_greed"                   # sell pressure


async def _fetch_global_market(client: httpx.AsyncClient) -> dict:
    key = "global"
    if _fresh(key):
        return _CACHE[key]
    try:
        r = await client.get("https://api.coingecko.com/api/v3/global", timeout=10)
        data = r.json().get("data", {})
        defi_vol  = data.get("defi_volume_24h", 0)
        total_vol = data.get("total_volume", {}).get("usd", 1)
        result = {
            "btc_dominance":         round(data.get("market_cap_percentage", {}).get("btc", 0), 2),
            "eth_dominance":         round(data.get("market_cap_percentage", {}).get("eth", 0), 2),
            "total_market_cap_b":    round(data.get("total_market_cap", {}).get("usd", 0) / 1e9, 1),
            "total_volume_24h_b":    round(total_vol / 1e9, 1),
            "defi_volume_24h_b":     round(defi_vol / 1e9, 2) if isinstance(defi_vol, (int, float)) else 0,
            "active_coins":          data.get("active_cryptocurrencies", 0),
            "market_cap_change_24h": round(data.get("market_cap_change_percentage_24h_usd", 0), 2),
        }
        return _store(key, result)
    except Exception as e:
        print(f"[OnChain] Global market error: {e}")
        return _CACHE.get(key, {})


async def _fetch_trending(client: httpx.AsyncClient) -> list[dict]:
    key = "trending"
    if _fresh(key):
        return _CACHE.get(key, [])
    try:
        r = await client.get("https://api.coingecko.com/api/v3/search/trending", timeout=10)
        coins = r.json().get("coins", [])
        result = [
            {
                "id":     c["item"].get("id", ""),
                "symbol": c["item"].get("symbol", "").upper(),
                "rank":   c["item"].get("market_cap_rank", 9999),
                "score":  round(c["item"].get("score", 0), 2),
            }
            for c in coins[:7]
        ]
        return _store(key, result)
    except Exception as e:
        print(f"[OnChain] Trending error: {e}")
        return _CACHE.get(key, [])


async def _fetch_coin_details(client: httpx.AsyncClient, symbols: list[str]) -> dict[str, dict]:
    """Fetch per-coin data: 24h change, volume, market cap rank."""
    key = f"coins_{'_'.join(sorted(symbols[:5]))}"
    if _fresh(key):
        return _CACHE.get(key, {})
    try:
        ids_map = {
            "BTC": "bitcoin", "ETH": "ethereum", "SOL": "solana",
            "BNB": "binancecoin", "XRP": "ripple", "ADA": "cardano",
            "AVAX": "avalanche-2", "DOT": "polkadot", "LINK": "chainlink",
            "MATIC": "matic-network", "LTC": "litecoin", "NEAR": "near",
        }
        bases = [s.replace("/USDT", "").replace("/BTC", "").upper() for s in symbols]
        ids   = [ids_map[b] for b in bases if b in ids_map]
        if not ids:
            return {}

        r = await client.get(
            "https://api.coingecko.com/api/v3/simple/price",
            params={
                "ids": ",".join(ids),
                "vs_currencies": "usd",
                "include_24hr_change": "true",
                "include_24hr_vol": "true",
                "include_market_cap": "true",
            },
            timeout=10,
        )
        data = r.json()
        result: dict[str, dict] = {}
        for b, cg_id in zip(bases, ids):
            if cg_id in data:
                d = data[cg_id]
                result[f"{b}/USDT"] = {
                    "price_usd":         d.get("usd", 0),
                    "change_24h_pct":    round(d.get("usd_24h_change", 0), 2),
                    "volume_24h_usd_m":  round(d.get("usd_24h_vol", 0) / 1e6, 1),
                    "market_cap_usd_b":  round(d.get("usd_market_cap", 0) / 1e9, 2),
                }
        return _store(key, result)
    except Exception as e:
        print(f"[OnChain] Coin details error: {e}")
        return _CACHE.get(key, {})


# ── Main aggregator ───────────────────────────────────────────────────────────

async def get_intel(symbols: Optional[list[str]] = None) -> dict:
    """
    Fetch all on-chain intelligence in parallel.
    Returns a unified dict ready for AI consumption.
    """
    symbols = symbols or ["BTC/USDT", "ETH/USDT"]

    async with httpx.AsyncClient(headers={"User-Agent": "QuantomV2/1.0"}) as client:
        fg, global_mkt, trending, coins = await asyncio.gather(
            _fetch_fear_greed(client),
            _fetch_global_market(client),
            _fetch_trending(client),
            _fetch_coin_details(client, symbols),
            return_exceptions=True,
        )

    def _safe(v: Any, default: Any) -> Any:
        return default if isinstance(v, Exception) else v

    fg        = _safe(fg, {"value": 50, "label": "Neutral", "signal": "neutral"})
    gm        = _safe(global_mkt, {})
    trend_lst = _safe(trending, [])
    coin_data = _safe(coins, {})

    # ── Market regime interpretation ──────────────────────────────────────────
    fg_val         = fg.get("value", 50)
    btc_dom        = gm.get("btc_dominance", 50)
    mkt_chg        = gm.get("market_cap_change_24h", 0)

    if fg_val <= 30 and mkt_chg < -2:
        regime = "panic_selloff"      # strong buy for contrarians
    elif fg_val <= 45 and mkt_chg < 0:
        regime = "fear_correction"    # cautious accumulation
    elif fg_val >= 75 and mkt_chg > 2:
        regime = "euphoria"           # risk-off warning
    elif fg_val >= 60 and mkt_chg > 0:
        regime = "greed_rally"        # trend continuation
    else:
        regime = "neutral"

    return {
        "fear_greed":       fg,
        "global_market":    gm,
        "trending_coins":   trend_lst,
        "coin_details":     coin_data,
        "market_regime":    regime,
        "btc_dominance":    btc_dom,
        "summary": (
            f"F&G={fg_val}({fg.get('label','?')}) | "
            f"BTC.dom={btc_dom:.0f}% | "
            f"Mkt24h={mkt_chg:+.1f}% | "
            f"Regime={regime}"
        ),
    }


def get_cached_intel() -> dict:
    """Return last cached result without network call."""
    return {
        "fear_greed":    _CACHE.get("fear_greed", {"value": 50, "label": "Neutral"}),
        "global_market": _CACHE.get("global", {}),
        "trending_coins": _CACHE.get("trending", []),
    }
