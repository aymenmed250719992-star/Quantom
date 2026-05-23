"""
MultiExchangeRouter — manages all 4 exchange connections and auto-selects the best performer.

Strategy:
  auto   → evaluates all configured exchanges, picks highest scorer, auto-switches on failure
  manual → always sticks to the manually selected exchange

Score = 0.7 × success_rate + 0.3 × (1 − latency_ms/5000)

Auto-switch triggers:
  • 3 consecutive trade failures on current exchange
  • Manual call to get_active() re-evaluates scores
"""

import os
import time
from typing import Optional

EXCHANGE_CONFIGS: dict[str, dict] = {
    "mexc":    {"key_env": "MEXC_API_KEY",     "secret_env": "MEXC_API_SECRET",     "pass_env": None,                     "needs_pass": False},
    "binance": {"key_env": "BINANCE_API_KEY",   "secret_env": "BINANCE_API_SECRET",   "pass_env": None,                     "needs_pass": False},
    "bybit":   {"key_env": "BYBIT_API_KEY",     "secret_env": "BYBIT_API_SECRET",     "pass_env": None,                     "needs_pass": False},
    "kucoin":  {"key_env": "KUCOIN_API_KEY",    "secret_env": "KUCOIN_API_SECRET",    "pass_env": "KUCOIN_API_PASSPHRASE",  "needs_pass": True},
}

EXCHANGE_ORDER = ["mexc", "binance", "bybit", "kucoin"]

# Exchanges that may be blocked by hosting provider IPs — deprioritised in auto mode
# Set CEX_ALLOW_ALL=true in env to disable this restriction on Render/VPS
_CEX_ALLOW_ALL = os.environ.get("CEX_ALLOW_ALL", "false").lower() == "true"
IP_BLOCKED = set() if _CEX_ALLOW_ALL else {"binance", "bybit", "kucoin"}


class ExchangeRouter:
    """Singleton multi-exchange router."""

    _instance: Optional["ExchangeRouter"] = None

    @classmethod
    def get_instance(cls) -> "ExchangeRouter":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def __init__(self) -> None:
        self.strategy: str = os.environ.get("EXCHANGE_STRATEGY", "auto")

        self._stats: dict[str, dict] = {
            name: {
                "trades_ok":         0,
                "trades_fail":       0,
                "success_rate":      100.0,
                "latency_ms":        9999,
                "consecutive_fails": 0,
                "last_test_ts":      0.0,
            }
            for name in EXCHANGE_CONFIGS
        }

        self._active: str = self._pick_initial()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_configured(self, name: str) -> bool:
        cfg = EXCHANGE_CONFIGS[name]
        key    = os.environ.get(cfg["key_env"], "")
        secret = os.environ.get(cfg["secret_env"], "")
        if cfg["needs_pass"]:
            passph = os.environ.get(cfg["pass_env"], "")
            return bool(key and secret and passph)
        return bool(key and secret)

    def _score(self, name: str) -> float:
        st = self._stats[name]
        lat_score = max(0.0, 1.0 - st["latency_ms"] / 5000.0)
        base = 0.7 * (st["success_rate"] / 100.0) + 0.3 * lat_score
        # Penalise exchanges that may be blocked on shared hosting IPs
        # so MEXC always wins unless it has catastrophic failure rate
        if name in IP_BLOCKED:
            base *= 0.5
        return base

    def _pick_initial(self) -> str:
        preferred = os.environ.get("EXCHANGE_NAME", "mexc").lower()
        if preferred in EXCHANGE_CONFIGS and self._is_configured(preferred):
            return preferred
        for name in EXCHANGE_ORDER:
            if self._is_configured(name):
                return name
        return preferred

    # ── Active exchange ───────────────────────────────────────────────────────

    @property
    def active(self) -> str:
        return self._active

    def get_active(self) -> str:
        if self.strategy == "auto":
            return self._auto_pick()
        return self._active

    def _auto_pick(self) -> str:
        # Configured exchanges (have API keys)
        candidates: dict[str, float] = {
            n: self._score(n) for n in EXCHANGE_ORDER if self._is_configured(n)
        }
        # Non-blocked exchanges always participate even without credentials
        # (they work for market data and demo mode with public endpoints)
        for n in EXCHANGE_ORDER:
            if n not in IP_BLOCKED and n not in candidates:
                # Give it a score just above blocked exchanges so it wins when
                # no credentials are configured for it yet
                candidates[n] = self._score(n)
        if not candidates:
            return self._active
        best = max(candidates, key=lambda n: candidates[n])
        if best != self._active:
            old_score = candidates.get(self._active, 0)
            new_score = candidates[best]
            print(f"[Router] Auto-switch {self._active}({old_score:.2f}) → {best}({new_score:.2f})")
            self._active = best
            os.environ["EXCHANGE_NAME"] = best
        return best

    def set_active(self, name: str) -> bool:
        if name not in EXCHANGE_CONFIGS:
            return False
        self._active = name
        os.environ["EXCHANGE_NAME"] = name
        return True

    def set_strategy(self, strategy: str) -> bool:
        if strategy not in ("auto", "manual"):
            return False
        self.strategy = strategy
        os.environ["EXCHANGE_STRATEGY"] = strategy
        return True

    # ── Performance tracking ──────────────────────────────────────────────────

    def record_success(self, name: str) -> None:
        if name not in self._stats:
            return
        st = self._stats[name]
        st["trades_ok"] += 1
        st["consecutive_fails"] = 0
        total = st["trades_ok"] + st["trades_fail"]
        if total:
            st["success_rate"] = 100.0 * st["trades_ok"] / total

    def record_failure(self, name: str) -> None:
        if name not in self._stats:
            return
        st = self._stats[name]
        st["trades_fail"] += 1
        st["consecutive_fails"] += 1
        total = st["trades_ok"] + st["trades_fail"]
        if total:
            st["success_rate"] = 100.0 * st["trades_ok"] / total
        if self.strategy == "auto" and st["consecutive_fails"] >= 3:
            print(f"[Router] {name} failed {st['consecutive_fails']}× — auto-switching...")
            self._auto_pick()

    def update_latency(self, name: str, ms: float) -> None:
        if name in self._stats:
            self._stats[name]["latency_ms"] = ms
            self._stats[name]["last_test_ts"] = time.time()

    # ── Credentials ──────────────────────────────────────────────────────────

    def save_credentials(self, name: str, key: str, secret: str, passphrase: str = "") -> None:
        if name not in EXCHANGE_CONFIGS:
            raise ValueError(f"Unknown exchange: {name}")
        cfg = EXCHANGE_CONFIGS[name]
        kv: dict[str, str] = {
            cfg["key_env"]:    key,
            cfg["secret_env"]: secret,
        }
        if cfg["needs_pass"] and cfg["pass_env"]:
            kv[cfg["pass_env"]] = passphrase
        for k, v in kv.items():
            os.environ[k] = v
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        self._patch_env(env_path, kv)

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

    # ── Status ────────────────────────────────────────────────────────────────

    def status_all(self) -> dict:
        active = self.get_active()
        exchanges: dict[str, dict] = {}
        any_configured = False
        for name in EXCHANGE_ORDER:
            cfg = EXCHANGE_CONFIGS[name]
            key  = os.environ.get(cfg["key_env"], "")
            configured = self._is_configured(name)
            if configured:
                any_configured = True
            st = self._stats[name]
            exchanges[name] = {
                "configured":        configured,
                "is_active":         name == active,
                "needs_pass":        cfg["needs_pass"],
                "score":             round(self._score(name) * 100, 1),
                "success_rate":      round(st["success_rate"], 1),
                "trades_ok":         st["trades_ok"],
                "trades_fail":       st["trades_fail"],
                "latency_ms":        int(st["latency_ms"]),
                "consecutive_fails": st["consecutive_fails"],
                "api_key_preview":   (key[:4] + "****" + key[-4:]) if len(key) >= 8 else ("****" if key else ""),
            }
        return {
            "strategy":        self.strategy,
            "active_exchange": active,
            "any_configured":  any_configured,
            "exchanges":       exchanges,
        }

    # ── Connectivity test ─────────────────────────────────────────────────────

    async def test_exchange(self, name: str) -> dict:
        if name not in EXCHANGE_CONFIGS:
            return {"success": False, "message": f"بورصة غير معروفة: {name}"}
        if not self._is_configured(name):
            return {"success": False, "message": f"لا توجد مفاتيح لـ {name.upper()} — أضفها أولاً"}

        import ccxt.async_support as ccxt_async
        cfg = EXCHANGE_CONFIGS[name]
        key    = os.environ.get(cfg["key_env"], "")
        secret = os.environ.get(cfg["secret_env"], "")
        passph = os.environ.get(cfg["pass_env"], "") if cfg["needs_pass"] and cfg["pass_env"] else ""

        opts: dict = {"apiKey": key, "secret": secret, "options": {"defaultType": "spot"}}
        if passph:
            opts["password"] = passph

        ex = getattr(ccxt_async, name)(opts)
        t0 = time.time()
        try:
            balance = await ex.fetch_balance()
            latency = (time.time() - t0) * 1000
            self.update_latency(name, latency)
            usdt  = balance.get("USDT", {})
            total = float(usdt.get("total", 0))
            free  = float(usdt.get("free", 0))
            return {
                "success":    True,
                "exchange":   name,
                "latency_ms": round(latency),
                "usdt_total": total,
                "usdt_free":  free,
                "message":    f"✅ {name.upper()} متصل | رصيد: ${total:.2f} | سرعة: {latency:.0f}ms",
            }
        except Exception as e:
            self.update_latency(name, 9999)
            err = str(e)
            if "451" in err or "restricted location" in err.lower():
                msg = f"❌ {name.upper()} محجوب من سيرفرات Replit الأمريكية (خطأ 451)"
            elif "400302" in err:
                msg = f"❌ {name.upper()} يمنع IPs الأمريكية (خطأ 400302)"
            elif "400004" in err or "passphrase" in err.lower():
                msg = f"❌ Passphrase خاطئ لـ {name.upper()}"
            elif "401" in err or "invalid" in err.lower() or "apiKey" in err:
                msg = f"❌ مفاتيح {name.upper()} غير صحيحة — تحقق من الـ Key والـ Secret"
            elif "403" in err:
                msg = f"❌ {name.upper()} رفض الاتصال (IP محجوب أو صلاحيات ناقصة)"
            else:
                msg = f"❌ {name.upper()}: {err[:150]}"
            return {"success": False, "exchange": name, "message": msg}
        finally:
            try:
                await ex.close()
            except Exception:
                pass
