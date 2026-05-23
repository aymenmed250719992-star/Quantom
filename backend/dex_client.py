"""
DEX Client — تداول مباشر عبر البلوكشين (Uniswap v3 / PancakeSwap v3)

الشبكات المدعومة:
  • Base      — Uniswap v3  (رسوم ~$0.01، الأسرع)
  • Polygon   — Uniswap v3  (رسوم ~$0.02)
  • BSC       — PancakeSwap (رسوم ~$0.05)

منطق الحصول على السعر:
  Factory.getPool(tokenA, tokenB, fee) → pool address
  pool.slot0() → sqrtPriceX96 → السعر الحقيقي من DEX

التدفق الحلال:
  نشتري ونبيع الـ tokens مباشرة دون وسيط مركزي.
  Spot swap فقط — لا رافعة، لا استقراض، لا ربا.

المفاتيح المطلوبة:
  DEX_PRIVATE_KEY   — مفتاح المحفظة الخاصة (محفوظ في .env)
  DEX_NETWORK       — base | polygon | bsc  (افتراضي: base)
  DEX_RPC_URL       — اختياري: RPC مخصص (Alchemy / Infura)
"""

import asyncio
import json
import os
import time
from typing import Optional

# ── ABI مُختصرة ──────────────────────────────────────────────────────────────

FACTORY_ABI = json.loads('[{"name":"getPool","inputs":[{"type":"address","name":"tokenA"},{"type":"address","name":"tokenB"},{"type":"uint24","name":"fee"}],"outputs":[{"type":"address","name":"pool"}],"stateMutability":"view","type":"function"}]')

POOL_ABI = json.loads('[{"name":"slot0","inputs":[],"outputs":[{"type":"uint160","name":"sqrtPriceX96"},{"type":"int24","name":"tick"},{"type":"uint16","name":"observationIndex"},{"type":"uint16","name":"observationCardinality"},{"type":"uint16","name":"observationCardinalityNext"},{"type":"uint8","name":"feeProtocol"},{"type":"bool","name":"unlocked"}],"stateMutability":"view","type":"function"},{"name":"token0","inputs":[],"outputs":[{"type":"address"}],"stateMutability":"view","type":"function"},{"name":"token1","inputs":[],"outputs":[{"type":"address"}],"stateMutability":"view","type":"function"},{"name":"liquidity","inputs":[],"outputs":[{"type":"uint128","name":""}],"stateMutability":"view","type":"function"}]')

ERC20_ABI = json.loads('[{"name":"approve","inputs":[{"name":"spender","type":"address"},{"name":"amount","type":"uint256"}],"outputs":[{"name":"","type":"bool"}],"type":"function","stateMutability":"nonpayable"},{"name":"balanceOf","inputs":[{"name":"account","type":"address"}],"outputs":[{"name":"","type":"uint256"}],"type":"function","stateMutability":"view"},{"name":"decimals","inputs":[],"outputs":[{"name":"","type":"uint8"}],"type":"function","stateMutability":"view"},{"name":"allowance","inputs":[{"name":"owner","type":"address"},{"name":"spender","type":"address"}],"outputs":[{"name":"","type":"uint256"}],"type":"function","stateMutability":"view"}]')

ROUTER_ABI = json.loads('[{"inputs":[{"components":[{"internalType":"address","name":"tokenIn","type":"address"},{"internalType":"address","name":"tokenOut","type":"address"},{"internalType":"uint24","name":"fee","type":"uint24"},{"internalType":"address","name":"recipient","type":"address"},{"internalType":"uint256","name":"amountIn","type":"uint256"},{"internalType":"uint256","name":"amountOutMinimum","type":"uint256"},{"internalType":"uint160","name":"sqrtPriceLimitX96","type":"uint160"}],"internalType":"struct IV3SwapRouter.ExactInputSingleParams","name":"params","type":"tuple"}],"name":"exactInputSingle","outputs":[{"internalType":"uint256","name":"amountOut","type":"uint256"}],"stateMutability":"payable","type":"function"}]')

# ── إعدادات الشبكات ──────────────────────────────────────────────────────────

NETWORKS: dict[str, dict] = {
    "base": {
        "name":      "Base",
        "chain_id":  8453,
        "rpc":       "https://mainnet.base.org",
        "explorer":  "https://basescan.org",
        "native":    "ETH",
        "gas_limit": 300_000,
        "factory":   "0x33128a8fC17869897dcE68Ed026d694621f6FDfD",  # Uniswap v3
        "router":    "0x2626664c2603336E57B271c5C0b26F421741e481",
        "stablecoin": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",  # USDC (أكثر سيولة على Base)
        "stable_dec": 6,
        "tokens": {
            "ETH":  "0x4200000000000000000000000000000000000006",  # WETH
            "WETH": "0x4200000000000000000000000000000000000006",
            "BTC":  "0xcbB7C0000aB88B473b1f5aFd9ef808440eed33Bf",  # cbBTC
            "BNB":  None,
            "USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "USDT": "0xfde4C96c8593536E31F229EA8f37b2ADa2699bb2",
        },
        "token_decimals": {"ETH": 18, "WETH": 18, "BTC": 8, "USDC": 6, "USDT": 6},
        "fees": [500, 3000, 10000],
    },
    "polygon": {
        "name":      "Polygon",
        "chain_id":  137,
        "rpc":       "https://polygon-rpc.com",
        "explorer":  "https://polygonscan.com",
        "native":    "MATIC",
        "gas_limit": 350_000,
        "factory":   "0x1F98431c8aD98523631AE4a59f267346ea31F984",  # Uniswap v3
        "router":    "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45",
        "stablecoin": "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",  # USDT
        "stable_dec": 6,
        "tokens": {
            "ETH":   "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
            "WETH":  "0x7ceB23fD6bC0adD59E62ac25578270cFf1b9f619",
            "BTC":   "0x1BFD67037B42Cf73acF2047067bd4F2C47D9BfD6",  # WBTC
            "MATIC": "0x0d500B1d8E8eF31E21C99d1Db9A6444d3ADf1270",
            "BNB":   None,
            "USDC":  "0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174",
            "USDT":  "0xc2132D05D31c914a87C6611C10748AEb04B58e8F",
        },
        "token_decimals": {"ETH": 18, "WETH": 18, "BTC": 8, "MATIC": 18, "USDC": 6, "USDT": 6},
        "fees": [500, 3000, 10000],
    },
    "bsc": {
        "name":      "BSC",
        "chain_id":  56,
        "rpc":       "https://bsc-dataseed.binance.org",
        "explorer":  "https://bscscan.com",
        "native":    "BNB",
        "gas_limit": 400_000,
        "factory":   "0x0BFbCF9fa4f9C56B0F40a671Ad40E0805A091865",  # PancakeSwap v3
        "router":    "0x13f4EA83D0bd40E75C8222255bc855a974568Dd4",
        "stablecoin": "0x55d398326f99059fF775485246999027B3197955",  # USDT-BSC
        "stable_dec": 18,
        "tokens": {
            "ETH":  "0x2170Ed0880ac9A755fd29B2688956BD959F933F8",
            "BTC":  "0x7130d2A12B9BCbFAe4f2634d864A1Ee1Ce3Ead9c",  # BTCB
            "BNB":  "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",  # WBNB
            "WBNB": "0xbb4CdB9CBd36B01bD1cBaEBF2De08d9173bc095c",
            "USDC": "0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d",
            "USDT": "0x55d398326f99059fF775485246999027B3197955",
        },
        "token_decimals": {"ETH": 18, "BTC": 18, "BNB": 18, "WBNB": 18, "USDC": 18, "USDT": 18},
        "fees": [100, 500, 2500, 10000],
    },
}

SYMBOL_MAP: dict[str, str] = {
    "BTC/USDT":  "BTC",
    "ETH/USDT":  "ETH",
    "BNB/USDT":  "BNB",
    "ETH/USDC":  "ETH",
    "BTC/USDC":  "BTC",
}

NULL_ADDR = "0x0000000000000000000000000000000000000000"


class DexClient:
    """عميل DEX — يتصل بالبلوكشين ويُنفّذ عمليات الشراء والبيع مباشرة."""

    _instance: Optional["DexClient"] = None

    @classmethod
    def get_instance(cls) -> "DexClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def __init__(self) -> None:
        self.network_name: str = os.environ.get("DEX_NETWORK", "base").lower()
        self.network: dict    = NETWORKS.get(self.network_name, NETWORKS["base"])
        self._w3              = None
        self._account         = None
        self._connected: bool = False
        self._pool_cache: dict[str, str] = {}          # (token0,token1,fee) → pool_addr
        self._price_cache: dict[str, tuple] = {}       # symbol → (price, ts)
        self._last_gas_price_gwei: float = 0.0
        self._last_gas_check: float = 0.0
        self._web3_available = False
        try:
            from web3 import Web3  # noqa: F401
            self._web3_available = True
            self._connect()
        except ImportError:
            print("[DEX] web3 not installed — run: pip install web3")
        except Exception as e:
            print(f"[DEX] Connection error: {e}")

    def _connect(self) -> None:
        from web3 import Web3
        rpc = os.environ.get("DEX_RPC_URL", self.network["rpc"])
        self._w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 15}))
        if self._w3.is_connected():
            self._connected = True
            print(f"[DEX] ✅ Connected to {self.network['name']} — chain {self.network['chain_id']}")
            pk = os.environ.get("DEX_PRIVATE_KEY", "")
            if pk:
                if not pk.startswith("0x"):
                    pk = "0x" + pk
                try:
                    self._account = self._w3.eth.account.from_key(pk)
                    print(f"[DEX] Wallet: {self._account.address[:10]}...")
                except Exception as e:
                    print(f"[DEX] Wallet load error: {e}")
        else:
            print(f"[DEX] ❌ Cannot connect to {self.network['name']}")

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _parse_pair(self, symbol: str) -> tuple[str, str]:
        parts = symbol.replace("-", "/").upper().split("/")
        return parts[0], parts[1] if len(parts) > 1 else "USDT"

    def _token_addr(self, sym: str) -> Optional[str]:
        return self.network["tokens"].get(sym.upper())

    def _token_dec(self, sym: str) -> int:
        return self.network["token_decimals"].get(sym.upper(), 18)

    def _pool_key(self, t0: str, t1: str, fee: int) -> str:
        a, b = sorted([t0.lower(), t1.lower()])
        return f"{a}:{b}:{fee}"

    def _sqrt_price_to_price(
        self,
        sqrt_price_x96: int,
        token0_addr: str,
        stable_addr: str,
        token_dec: int,
        stable_dec: int,
    ) -> float:
        """
        يحوّل sqrtPriceX96 إلى سعر الـ token بالـ stable coin.
        token0 = العملة ذات العنوان الأصغر، token1 = الأكبر.
        """
        raw = (sqrt_price_x96 / 2 ** 96) ** 2
        # raw = token1_amount_per_token0_amount (in raw units)
        # price = STABLE per TOKEN
        decimal_adj = 10 ** (token_dec - stable_dec)  # +12 for ETH/USDC
        if token0_addr.lower() < stable_addr.lower():
            # token is token0, stable is token1
            # raw = stable_units per token_units → need decimal adjustment
            return raw * decimal_adj
        else:
            # stable is token0, token is token1
            # raw = token_units per stable_units
            if raw == 0:
                return 0
            return (1 / raw) * decimal_adj

    # ── Price via Factory + Pool slot0 ────────────────────────────────────────

    async def get_dex_price(
        self,
        symbol: str,
        amount_usdt: float = 100.0,
    ) -> dict:
        """
        يحصل على سعر الـ token من DEX.
        يستخدم Factory.getPool() → pool.slot0() → sqrtPriceX96 → سعر.
        """
        if not self._web3_available:
            return {"success": False, "error": "web3 غير مثبّت"}
        if not self._connected or not self._w3:
            return {"success": False, "error": f"غير متصل بـ {self.network['name']}"}

        base_sym, _  = self._parse_pair(symbol)
        token_addr   = self._token_addr(base_sym)
        if not token_addr:
            return {"success": False, "error": f"الرمز {base_sym} غير مدعوم على {self.network['name']}"}

        stable_addr = self.network["stablecoin"]
        token_dec   = self._token_dec(base_sym)
        stable_dec  = self.network["stable_dec"]

        # Cache check (30s)
        cache_key = f"{symbol}:{self.network_name}"
        if cache_key in self._price_cache:
            cached_price, cached_ts = self._price_cache[cache_key]
            if time.time() - cached_ts < 30:
                out = round(amount_usdt / cached_price, 8) if cached_price else 0
                return {
                    "success": True, "symbol": symbol,
                    "price": round(cached_price, 6),
                    "amount_in_usdt": amount_usdt,
                    "amount_out_tokens": out,
                    "fee_tier": 0, "fee_pct": 0,
                    "network": self.network["name"], "cached": True,
                }

        from web3 import Web3

        factory = self._w3.eth.contract(
            address=Web3.to_checksum_address(self.network["factory"]),
            abi=FACTORY_ABI,
        )

        best_price: float = 0.0
        best_fee:   int   = 0
        best_liq:   int   = 0

        loop = asyncio.get_event_loop()

        for fee in self.network["fees"]:
            pool_key = self._pool_key(token_addr, stable_addr, fee)

            # Get pool address (cached)
            if pool_key not in self._pool_cache:
                try:
                    pool_addr = await loop.run_in_executor(
                        None,
                        lambda fee=fee: factory.functions.getPool(
                            Web3.to_checksum_address(token_addr),
                            Web3.to_checksum_address(stable_addr),
                            fee,
                        ).call()
                    )
                    self._pool_cache[pool_key] = pool_addr
                except Exception:
                    continue
            else:
                pool_addr = self._pool_cache[pool_key]

            if not pool_addr or pool_addr == NULL_ADDR:
                continue

            try:
                pool = self._w3.eth.contract(
                    address=Web3.to_checksum_address(pool_addr),
                    abi=POOL_ABI,
                )
                # Batch: slot0 + token0 + liquidity
                slot0_res, token0_addr, liq = await loop.run_in_executor(
                    None,
                    lambda pool=pool: (
                        pool.functions.slot0().call(),
                        pool.functions.token0().call(),
                        pool.functions.liquidity().call(),
                    )
                )
                sqrt_price_x96 = slot0_res[0]
                if sqrt_price_x96 == 0 or liq == 0:
                    continue

                price = self._sqrt_price_to_price(
                    sqrt_price_x96, token0_addr,
                    stable_addr, token_dec, stable_dec,
                )
                if price > 0 and liq > best_liq:
                    best_price = price
                    best_fee   = fee
                    best_liq   = liq

            except Exception:
                continue

        if best_price == 0:
            return {"success": False, "error": f"لا يوجد pool لـ {symbol} على {self.network['name']}"}

        # Store in cache
        self._price_cache[cache_key] = (best_price, time.time())

        return {
            "success":           True,
            "symbol":            symbol,
            "price":             round(best_price, 4),
            "amount_in_usdt":    amount_usdt,
            "amount_out_tokens": round(amount_usdt / best_price, 8),
            "fee_tier":          best_fee,
            "fee_pct":           round(best_fee / 1_000_000 * 100, 3),
            "liquidity":         best_liq,
            "network":           self.network["name"],
            "cached":            False,
        }

    # ── Gas ──────────────────────────────────────────────────────────────────

    async def get_gas_price_gwei(self) -> float:
        if not self._connected or not self._w3:
            return 0.0
        if time.time() - self._last_gas_check < 60:
            return self._last_gas_price_gwei
        try:
            loop = asyncio.get_event_loop()
            gwei = await loop.run_in_executor(
                None, lambda: self._w3.from_wei(self._w3.eth.gas_price, "gwei")
            )
            self._last_gas_price_gwei = float(gwei)
            self._last_gas_check = time.time()
            return self._last_gas_price_gwei
        except Exception:
            return 1.0

    async def estimate_gas_cost_usd(self, native_price_usd: float) -> float:
        gwei      = await self.get_gas_price_gwei()
        gas_limit = self.network["gas_limit"]
        native    = gas_limit * (gwei * 1e-9)
        return native * native_price_usd

    # ── Swap execution ────────────────────────────────────────────────────────

    async def execute_swap(
        self,
        symbol:       str,
        side:         str,
        amount_usdt:  float,
        slippage_pct: float = 0.5,
    ) -> dict:
        if not self._web3_available:
            return {"success": False, "error": "web3 غير مثبّت"}
        if not self._connected or not self._w3:
            return {"success": False, "error": f"غير متصل بـ {self.network['name']}"}
        if not self._account:
            return {"success": False, "error": "لا توجد محفظة — أضف DEX_PRIVATE_KEY في الإعدادات"}

        from web3 import Web3

        base_sym, _ = self._parse_pair(symbol)
        token_addr  = self._token_addr(base_sym)
        if not token_addr:
            return {"success": False, "error": f"الرمز {base_sym} غير مدعوم"}

        quote = await self.get_dex_price(symbol, amount_usdt)
        if not quote["success"]:
            return {"success": False, "error": quote["error"]}

        stable_addr = self.network["stablecoin"]
        stable_dec  = self.network["stable_dec"]
        token_dec   = self._token_dec(base_sym)
        fee         = quote["fee_tier"] or self.network["fees"][0]
        router_addr = Web3.to_checksum_address(self.network["router"])
        loop        = asyncio.get_event_loop()

        if side == "buy":
            token_in   = Web3.to_checksum_address(stable_addr)
            token_out  = Web3.to_checksum_address(token_addr)
            amount_in  = int(amount_usdt * 10 ** stable_dec)
            expected   = int(quote["amount_out_tokens"] * 10 ** token_dec)
            min_out    = int(expected * (1 - slippage_pct / 100))
        else:
            token_in   = Web3.to_checksum_address(token_addr)
            token_out  = Web3.to_checksum_address(stable_addr)
            tokens_in  = amount_usdt / quote["price"]
            amount_in  = int(tokens_in * 10 ** token_dec)
            expected   = int(amount_usdt * 10 ** stable_dec)
            min_out    = int(expected * (1 - slippage_pct / 100))

        try:
            # Approve if needed
            in_contract = self._w3.eth.contract(address=token_in, abi=ERC20_ABI)
            allowance   = await loop.run_in_executor(
                None,
                lambda: in_contract.functions.allowance(self._account.address, router_addr).call()
            )
            if allowance < amount_in:
                approve_tx = await loop.run_in_executor(
                    None,
                    lambda: in_contract.functions.approve(router_addr, 2 ** 256 - 1).build_transaction({
                        "from":     self._account.address,
                        "nonce":    self._w3.eth.get_transaction_count(self._account.address),
                        "gas":      80_000,
                        "gasPrice": self._w3.eth.gas_price,
                    })
                )
                signed = self._w3.eth.account.sign_transaction(approve_tx, self._account.key)
                await loop.run_in_executor(None, lambda: self._w3.eth.send_raw_transaction(signed.raw_transaction))
                print(f"[DEX] Approved {token_in[:10]}...")

            # Build swap
            deadline   = int(time.time()) + 1200
            router     = self._w3.eth.contract(address=router_addr, abi=ROUTER_ABI)
            swap_tx    = await loop.run_in_executor(
                None,
                lambda: router.functions.exactInputSingle({
                    "tokenIn":           token_in,
                    "tokenOut":          token_out,
                    "fee":               fee,
                    "recipient":         self._account.address,
                    "amountIn":          amount_in,
                    "amountOutMinimum":  min_out,
                    "sqrtPriceLimitX96": 0,
                }).build_transaction({
                    "from":     self._account.address,
                    "nonce":    self._w3.eth.get_transaction_count(self._account.address),
                    "gas":      self.network["gas_limit"],
                    "gasPrice": self._w3.eth.gas_price,
                    "value":    0,
                })
            )
            signed_swap = self._w3.eth.account.sign_transaction(swap_tx, self._account.key)
            tx_hash     = await loop.run_in_executor(
                None, lambda: self._w3.eth.send_raw_transaction(signed_swap.raw_transaction)
            )
            tx_hex = tx_hash.hex()
            print(f"[DEX] Swap TX: {tx_hex}")

            try:
                receipt = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: self._w3.eth.wait_for_transaction_receipt(tx_hash, timeout=60)),
                    timeout=65,
                )
                status = "confirmed" if receipt["status"] == 1 else "failed"
            except asyncio.TimeoutError:
                status  = "pending"

            explorer_url = f"{self.network['explorer']}/tx/{tx_hex}"
            return {
                "success":      status != "failed",
                "status":       status,
                "tx_hash":      tx_hex,
                "explorer_url": explorer_url,
                "side":         side,
                "symbol":       symbol,
                "amount_usdt":  amount_usdt,
                "price":        quote["price"],
                "network":      self.network["name"],
                "fee_pct":      quote["fee_pct"],
                "message":      f"✅ DEX Swap {status} | {self.network['name']} | {explorer_url}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)[:300]}

    # ── Wallet info ───────────────────────────────────────────────────────────

    async def get_wallet_info(self) -> dict:
        if not self._web3_available:
            return {"connected": False, "error": "web3 غير مثبّت"}
        if not self._connected or not self._w3:
            return {"connected": False, "error": f"لا يوجد اتصال بـ {self.network['name']}"}
        if not self._account:
            return {
                "connected":  True,
                "has_wallet": False,
                "network":    self.network["name"],
                "error":      "لا توجد محفظة — أضف DEX_PRIVATE_KEY",
            }
        from web3 import Web3
        loop = asyncio.get_event_loop()
        try:
            native_wei = await loop.run_in_executor(
                None, lambda: self._w3.eth.get_balance(self._account.address)
            )
            native_bal = float(Web3.from_wei(native_wei, "ether"))
            stable_addr = self.network["stablecoin"]
            stable_dec  = self.network["stable_dec"]
            sc          = self._w3.eth.contract(
                address=Web3.to_checksum_address(stable_addr), abi=ERC20_ABI
            )
            raw_stable = await loop.run_in_executor(
                None, lambda: sc.functions.balanceOf(self._account.address).call()
            )
            stable_bal = raw_stable / 10 ** stable_dec
            stable_sym = "USDC" if stable_addr == self.network.get("usdc", "") else "USDT"
            return {
                "connected":      True,
                "has_wallet":     True,
                "address":        self._account.address,
                "address_short":  self._account.address[:6] + "..." + self._account.address[-4:],
                "network":        self.network["name"],
                "chain_id":       self.network["chain_id"],
                "native_symbol":  self.network["native"],
                "native_balance": round(native_bal, 6),
                "stable_balance": round(stable_bal, 2),
                "stable_symbol":  stable_sym,
            }
        except Exception as e:
            return {
                "connected": True, "has_wallet": True,
                "address": self._account.address,
                "address_short": self._account.address[:6] + "..." + self._account.address[-4:],
                "error": str(e)[:200],
            }

    # ── Status & config ───────────────────────────────────────────────────────

    def status(self) -> dict:
        token_list = [s for s, a in self.network["tokens"].items() if a]
        return {
            "web3_available":    self._web3_available,
            "connected":         self._connected,
            "has_wallet":        self._account is not None,
            "network":           self.network["name"],
            "chain_id":          self.network.get("chain_id"),
            "rpc":               self.network["rpc"],
            "supported_symbols": list(SYMBOL_MAP.keys()),
            "available_tokens":  token_list,
            "explorer":          self.network.get("explorer", ""),
        }

    def save_config(self, network: str, private_key: str = "", rpc_url: str = "") -> dict:
        network = network.lower()
        if network not in NETWORKS:
            return {"success": False, "error": f"شبكة غير مدعومة: {network}"}
        kv: dict[str, str] = {"DEX_NETWORK": network}
        if private_key:
            if not private_key.startswith("0x"):
                private_key = "0x" + private_key
            kv["DEX_PRIVATE_KEY"] = private_key
        if rpc_url:
            kv["DEX_RPC_URL"] = rpc_url
        for k, v in kv.items():
            os.environ[k] = v
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        self._patch_env(env_path, kv)
        # Reconnect
        self.network_name = network
        self.network      = NETWORKS[network]
        self._connected   = False
        self._account     = None
        self._pool_cache  = {}
        self._price_cache = {}
        if self._web3_available:
            self._connect()
        net_name = NETWORKS[network]["name"]
        return {"success": True, "network": network, "message": f"✅ DEX مُهيّأ على {net_name}"}

    @staticmethod
    def _patch_env(path: str, kv: dict[str, str]) -> None:
        lines: list[str] = []
        if os.path.exists(path):
            with open(path) as f:
                lines = f.readlines()
        updated: set[str] = set()
        new_lines: list[str] = []
        for line in lines:
            s = line.strip()
            if "=" in s and not s.startswith("#"):
                k = s.split("=", 1)[0].strip()
                if k in kv:
                    new_lines.append(f"{k}={kv[k]}\n")
                    updated.add(k)
                    continue
            new_lines.append(line)
        for k, v in kv.items():
            if k not in updated:
                new_lines.append(f"{k}={v}\n")
        with open(path, "w") as f:
            f.writelines(new_lines)
