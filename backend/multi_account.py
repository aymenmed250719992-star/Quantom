"""
Multi-Account Trading Manager — Quantom V2
Replicates trading signals to multiple exchange accounts simultaneously.
All accounts share the same AI decisions but execute independently.
"""
import asyncio
import os
import uuid
from typing import Any, Optional


class AccountClient:
    """Lightweight exchange client for a single additional account."""

    def __init__(self, account: dict) -> None:
        self.account_id  = str(account["id"])
        self.name        = account.get("name", "Account")
        self.exchange_name = account.get("exchange_name", "mexc").lower()
        self.mode        = account.get("mode", "demo").lower()
        self.api_key     = account.get("api_key", "")
        self.api_secret  = account.get("api_secret", "")
        self.api_passphrase = account.get("api_passphrase", "")
        self._has_credentials = bool(self.api_key and self.api_secret)
        self._paper_balance   = float(account.get("balance", 10000))
        self._paper_counter   = 0
        self._exchange: Any   = None
        self._init_exchange()

    def _init_exchange(self) -> None:
        try:
            import ccxt.async_support as ccxt_async
            KNOWN = {"mexc", "kucoin", "binance", "bybit", "gate", "okx", "huobi"}
            name = self.exchange_name if self.exchange_name in KNOWN else "mexc"

            opts: dict[str, Any] = {"options": {"defaultType": "spot"}}
            if self.mode == "live" and self.api_key:
                opts["apiKey"] = self.api_key
            if self.mode == "live" and self.api_secret:
                opts["secret"] = self.api_secret
            if self.mode == "live" and self.api_passphrase:
                opts["password"] = self.api_passphrase

            self._exchange = getattr(ccxt_async, name)(opts)
        except Exception as e:
            print(f"[AccountClient] Init error for {self.name}: {e}")

    async def get_balance(self) -> dict:
        base = {
            "account_id":    self.account_id,
            "account_name":  self.name,
            "exchange":      self.exchange_name,
            "mode":          self.mode,
        }
        if self.mode == "demo" or not self._has_credentials:
            return {**base, "total": round(self._paper_balance, 4),
                    "free": round(self._paper_balance, 4), "used": 0.0}
        try:
            raw  = await self._exchange.fetch_balance()
            usdt = raw.get("USDT", {})
            return {
                **base,
                "total": float(usdt.get("total") or 0),
                "free":  float(usdt.get("free") or 0),
                "used":  float(usdt.get("used") or 0),
            }
        except Exception as e:
            return {**base, "total": 0.0, "free": 0.0, "used": 0.0,
                    "error": str(e)[:120]}

    async def place_spot_order(
        self,
        symbol:     str,
        side:       str,
        quantity:   float,
        price:      Optional[float] = None,
    ) -> dict:
        """Enforce spot-only (Islamic compliance)."""
        if self.mode == "demo" or not self._has_credentials:
            self._paper_counter += 1
            order_id = f"PAPER-{self.account_id[:6]}-{self._paper_counter:04d}"
            return {
                "id": order_id, "symbol": symbol, "side": side,
                "amount": quantity, "price": price, "status": "closed", "demo": True,
            }
        try:
            return await self._exchange.create_market_order(symbol, side, quantity)
        except Exception as e:
            return {"error": str(e)[:200], "symbol": symbol, "side": side}

    async def close(self) -> None:
        try:
            if self._exchange:
                await self._exchange.close()
        except Exception:
            pass


class MultiAccountManager:
    """
    Singleton that manages all secondary exchange accounts.
    Primary account is handled by ExchangeClient (existing).
    This manager handles ALL additional accounts.
    """

    _instance: Optional["MultiAccountManager"] = None

    @classmethod
    def get_instance(cls) -> "MultiAccountManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._clients: dict[str, AccountClient] = {}
        self._lock = asyncio.Lock()
        self._loaded = False

    async def load_accounts(self, db: Any) -> int:
        """Reload active accounts from DB — safe to call repeatedly."""
        async with self._lock:
            try:
                accounts = await db.get_exchange_accounts(active_only=True)
                current_ids = {str(a["id"]) for a in accounts}

                # Close and remove deactivated accounts
                for aid in list(self._clients.keys()):
                    if aid not in current_ids:
                        await self._clients[aid].close()
                        del self._clients[aid]

                # Add new accounts
                for acc in accounts:
                    aid = str(acc["id"])
                    if aid not in self._clients:
                        self._clients[aid] = AccountClient(acc)

                self._loaded = True
                n = len(self._clients)
                if n:
                    print(f"[MultiAccount] {n} secondary account(s) loaded")
                return n
            except Exception as e:
                print(f"[MultiAccount] Load error: {e}")
                return 0

    def all_clients(self) -> list[AccountClient]:
        return list(self._clients.values())

    def count(self) -> int:
        return len(self._clients)

    async def get_all_balances(self) -> list[dict]:
        """Fetch balances from all secondary accounts in parallel."""
        clients = self.all_clients()
        if not clients:
            return []
        results = await asyncio.gather(
            *[c.get_balance() for c in clients],
            return_exceptions=True,
        )
        out = []
        for i, r in enumerate(results):
            if isinstance(r, Exception):
                out.append({
                    "account_name": clients[i].name,
                    "error": str(r)[:100],
                    "total": 0.0,
                })
            else:
                out.append(r)
        return out

    async def replicate_buy(
        self,
        symbol:        str,
        quantity:      float,
        price:         float,
        db:            Any,
        base_trade_id: str,
        reasoning:     str = "",
    ) -> list[dict]:
        """
        Replicate a BUY signal to ALL active secondary accounts.
        Each account gets its own trade record tagged with account_id.
        """
        clients = self.all_clients()
        if not clients:
            return []

        results = []
        for client in clients:
            try:
                order = await client.place_spot_order(symbol, "buy", quantity, price)
                err   = order.get("error")
                if not err:
                    trade_data = {
                        "id":              str(uuid.uuid4()),
                        "symbol":          symbol,
                        "side":            "buy",
                        "entry_price":     price,
                        "quantity":        quantity,
                        "status":          "open",
                        "ai_confidence":   0,
                        "ai_reasoning":    f"Replicated from {base_trade_id}. {reasoning[:100]}",
                        "market_condition": "replicated",
                        "pattern":         "multi_account",
                        "account_id":      client.account_id,
                    }
                    await db.create_trade(trade_data)
                    results.append({
                        "account": client.name,
                        "status":  "ok",
                        "order_id": order.get("id", ""),
                    })
                    print(f"[MultiAccount] ✅ Replicated BUY {symbol} → {client.name}")
                else:
                    results.append({"account": client.name, "status": "error", "error": err})
            except Exception as e:
                results.append({"account": client.name, "status": "error", "error": str(e)[:120]})
                print(f"[MultiAccount] ❌ Replicate error on {client.name}: {e}")

        return results

    async def replicate_sell(
        self,
        symbol:        str,
        quantity:      float,
        price:         float,
        db:            Any,
        base_trade_id: str = "",
        primary_pnl:   float = 0.0,
    ) -> list[dict]:
        """Close open replicated positions for this symbol on all secondary accounts."""
        clients = self.all_clients()
        if not clients:
            return []

        results = []
        for client in clients:
            try:
                # Find open replicated trade for this account + symbol
                all_trades = await db.get_trades(limit=500)
                open_rep   = [
                    t for t in all_trades
                    if t.get("symbol") == symbol
                    and t.get("status") == "open"
                    and t.get("account_id") == client.account_id
                ]
                if not open_rep:
                    continue

                order = await client.place_spot_order(symbol, "sell", quantity, price)
                err   = order.get("error")
                if not err:
                    from datetime import datetime
                    from risk_manager import RiskManager
                    rm  = RiskManager()
                    t2c = open_rep[0]
                    pnl = rm.estimate_pnl(
                        "buy",
                        float(t2c.get("entry_price") or 0),
                        price,
                        float(t2c.get("quantity") or 0),
                    )
                    await db.update_trade(t2c["id"], {
                        "status":     "closed",
                        "exit_price": price,
                        "pnl":        pnl,
                        "closed_at":  datetime.utcnow().isoformat(),
                    })
                    results.append({"account": client.name, "status": "ok", "pnl": pnl})
                    print(f"[MultiAccount] ✅ Replicated SELL {symbol} → {client.name} | PnL: ${pnl:+.4f}")
                else:
                    results.append({"account": client.name, "status": "error", "error": err})
            except Exception as e:
                results.append({"account": client.name, "status": "error", "error": str(e)[:120]})

        return results

    async def close_all(self) -> None:
        for client in self._clients.values():
            await client.close()
        self._clients.clear()
