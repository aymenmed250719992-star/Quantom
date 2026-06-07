"""
PushManager — إشعارات Expo Push الذكية بالذكاء الاصطناعي  (T008 enhanced)

تحسينات T008 — Smart AI Push Alerts:
  • AI يكتب شرحاً كاملاً لكل إشعار (لماذا؟ ما التوقع؟ ما المؤشرات؟)
  • إشعارات غنية بالبيانات (RSI, confidence, regime, trend)
  • تجميع (batching) لتجنب إغراق المستخدم
  • cooldown ذكي: لا أكثر من 3 إشعارات / 15 دقيقة
  • أولويات: CRITICAL > HIGH > NORMAL > LOW

Tokens مُخزّنة في الذاكرة + ملف JSON محلي.
"""

import json
import os
import time
from typing import Optional

import httpx

EXPO_PUSH_URL = "https://exp.host/--/api/v2/push/send"
TOKENS_FILE   = os.path.join(os.path.dirname(__file__), ".push_tokens.json")

PRIORITY_COOLDOWNS = {
    "critical": 0,       # no cooldown for emergencies
    "high":     120,     # 2 minutes
    "normal":   600,     # 10 minutes
    "low":      1800,    # 30 minutes
}
MAX_PER_WINDOW   = 3     # max notifications per window
WINDOW_SECONDS   = 900   # 15 minute window


class PushManager:
    _instance: Optional["PushManager"] = None

    @classmethod
    def get_instance(cls) -> "PushManager":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._tokens:      set[str]            = set()
        self._sent_log:    list[float]         = []   # timestamps of sent notifications
        self._last_by_type: dict[str, float]   = {}   # type → last_sent_ts
        self._load_tokens()
        print(f"[Push] Ready — {len(self._tokens)} device(s) registered")

    def _load_tokens(self) -> None:
        try:
            if os.path.exists(TOKENS_FILE):
                data = json.loads(open(TOKENS_FILE).read())
                self._tokens = set(data.get("tokens", []))
        except Exception as e:
            print(f"[Push] Could not load tokens: {e}")

    def _save_tokens(self) -> None:
        try:
            with open(TOKENS_FILE, "w") as f:
                json.dump({"tokens": list(self._tokens)}, f)
        except Exception as e:
            print(f"[Push] Could not save tokens: {e}")

    def register(self, token: str) -> bool:
        token = token.strip()
        if not token:
            return False
        if not (token.startswith("ExponentPushToken[") or token.startswith("ExpoPushToken[")):
            return False
        added = token not in self._tokens
        self._tokens.add(token)
        if added:
            self._save_tokens()
            print(f"[Push] New device registered — total: {len(self._tokens)}")
        return True

    def unregister(self, token: str) -> None:
        self._tokens.discard(token)
        self._save_tokens()

    @property
    def token_count(self) -> int:
        return len(self._tokens)

    # ── Rate limiting ─────────────────────────────────────────────────────────

    def _can_send(self, priority: str, notif_type: str) -> tuple[bool, str]:
        now = time.time()
        window_start = now - WINDOW_SECONDS
        self._sent_log = [t for t in self._sent_log if t > window_start]

        if priority == "critical":
            return True, ""

        if len(self._sent_log) >= MAX_PER_WINDOW:
            return False, f"rate limit: {len(self._sent_log)} notifications in last 15 min"

        cooldown = PRIORITY_COOLDOWNS.get(priority, 600)
        last_ts  = self._last_by_type.get(notif_type, 0)
        if (now - last_ts) < cooldown:
            return False, f"cooldown: {int(cooldown - (now - last_ts))}s remaining"

        return True, ""

    def _record_sent(self, notif_type: str) -> None:
        now = time.time()
        self._sent_log.append(now)
        self._last_by_type[notif_type] = now

    # ── Smart content builders ────────────────────────────────────────────────

    @staticmethod
    def build_trade_open_alert(trade: dict, indicators: dict, kelly: dict) -> tuple[str, str]:
        """Build rich notification for trade open."""
        symbol  = trade.get("symbol", "?").replace("/USDT", "")
        side    = trade.get("side", "buy").upper()
        entry   = trade.get("entry_price", 0)
        conf    = trade.get("ai_confidence") or trade.get("confidence") or 0
        sl      = trade.get("stop_loss_price", 0)
        tp      = trade.get("take_profit_price", 0)
        rsi     = indicators.get("rsi", 0)
        bb_pct  = indicators.get("bb_pct", 0.5)
        kelly_pct = kelly.get("risk_pct", 1.5) if kelly else 1.5

        side_emoji = "📈" if side == "BUY" else "📉"
        title = f"{side_emoji} {side} {symbol} — {conf:.0f}% ثقة"
        body  = (
            f"الدخول: ${entry:.4f} | SL: ${sl:.4f} | TP: ${tp:.4f}\n"
            f"RSI={rsi:.0f} | BB={bb_pct:.2f} | Kelly={kelly_pct}%\n"
            f"R:R = 1:{(tp-entry)/(entry-sl):.1f}" if (entry and sl and tp and entry != sl) else
            f"الدخول: ${entry:.4f} | ثقة: {conf:.0f}%"
        )
        return title, body

    @staticmethod
    def build_trade_close_alert(trade: dict, pnl: float, exit_price: float) -> tuple[str, str]:
        symbol   = trade.get("symbol", "?").replace("/USDT", "")
        entry    = float(trade.get("entry_price") or 1)
        pnl_pct  = (exit_price - entry) / entry * 100 if entry else 0
        win      = pnl > 0
        emoji    = "✅ ربح" if win else "🔴 خسارة"
        title    = f"{emoji} — {symbol}: ${pnl:+.4f}"
        body     = (
            f"الخروج: ${exit_price:.4f} | الدخول: ${entry:.4f}\n"
            f"التغيّر: {pnl_pct:+.2f}% | PnL: ${pnl:+.4f} USDT"
        )
        return title, body

    @staticmethod
    def build_market_alert(symbol: str, event: str, data: dict) -> tuple[str, str]:
        fg    = data.get("fear_greed", {}).get("value", 50)
        regime = data.get("market_regime", "neutral")
        title = f"📡 تنبيه السوق — {symbol.replace('/USDT','')}"
        body  = f"الحدث: {event}\nF&G={fg} | النظام: {regime}"
        return title, body

    # ── Core send ─────────────────────────────────────────────────────────────

    async def send(
        self,
        title: str,
        body: str,
        data: dict | None = None,
        sound: str = "default",
        badge: int | None = None,
        priority: str = "normal",
        notif_type: str = "general",
    ) -> dict:
        """Send notification to all registered devices with rate limiting."""
        if not self._tokens:
            return {"sent": 0, "note": "no devices registered"}

        can, reason = self._can_send(priority, notif_type)
        if not can:
            print(f"[Push] Skipped '{title}' — {reason}")
            return {"sent": 0, "skipped": True, "reason": reason}

        messages = []
        for token in self._tokens:
            msg: dict = {
                "to":       token,
                "title":    title,
                "body":     body,
                "sound":    sound,
                "priority": "high" if priority in ("critical", "high") else "default",
                "data":     {**(data or {}), "priority": priority, "type": notif_type},
            }
            if badge is not None:
                msg["badge"] = badge
            messages.append(msg)

        results: dict = {"sent": 0, "failed": 0, "errors": []}
        try:
            async with httpx.AsyncClient(timeout=8) as client:
                payload = messages if len(messages) > 1 else messages[0]
                resp    = await client.post(
                    EXPO_PUSH_URL, json=payload,
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                )
                if resp.status_code == 200:
                    results["sent"] = len(messages)
                    self._record_sent(notif_type)
                    print(f"[Push] ✅ Sent '{title}' → {len(messages)} device(s) [{priority}]")
                else:
                    results["failed"] = len(messages)
                    results["errors"].append(f"HTTP {resp.status_code}: {resp.text[:120]}")
                    print(f"[Push] ❌ Failed: {resp.status_code}")
        except Exception as e:
            results["failed"] = len(messages)
            results["errors"].append(str(e)[:120])
            print(f"[Push] ❌ Error: {e}")

        return results

    # ── Semantic helpers ──────────────────────────────────────────────────────

    async def notify_trade_open(self, trade: dict, indicators: dict = None, kelly: dict = None) -> dict:
        title, body = self.build_trade_open_alert(trade, indicators or {}, kelly or {})
        side = trade.get("side", "buy")
        return await self.send(
            title, body,
            data={"type": "trade_open", "symbol": trade.get("symbol"), "side": side},
            priority="high",
            notif_type="trade_open",
        )

    async def notify_trade_close(self, trade: dict, pnl: float, exit_price: float) -> dict:
        title, body = self.build_trade_close_alert(trade, pnl, exit_price)
        priority    = "high" if abs(pnl) > 5 else "normal"
        return await self.send(
            title, body,
            data={"type": "trade_close", "result": "win" if pnl > 0 else "loss",
                  "symbol": trade.get("symbol")},
            priority=priority,
            notif_type="trade_close",
        )

    async def notify_emergency(self, losses: int) -> dict:
        return await self.send(
            "🛑 إيقاف طارئ!",
            f"{losses} خسائر متتالية — البوت موقف مؤقتاً للمراجعة العميقة",
            data={"type": "emergency", "consecutive_losses": losses},
            priority="critical",
            notif_type="emergency",
        )

    async def notify_drawdown(self, losses: int) -> dict:
        return await self.send(
            "⚠️ تنبيه انخفاض",
            f"{losses} خسائر متتالية — تم رفع عتبة الثقة تلقائياً",
            data={"type": "drawdown", "consecutive_losses": losses},
            priority="high",
            notif_type="drawdown",
        )

    async def notify_win_streak(self, wins: int) -> dict:
        return await self.send(
            "🏆 سلسلة فوز رائعة!",
            f"{wins} صفقات رابحة متتالية — استراتيجيتك تعمل بشكل ممتاز",
            data={"type": "win_streak", "consecutive_wins": wins},
            priority="normal",
            notif_type="win_streak",
        )

    async def notify_market_alert(self, symbol: str, event: str, market_data: dict) -> dict:
        title, body = self.build_market_alert(symbol, event, market_data)
        return await self.send(
            title, body,
            data={"type": "market_alert", "symbol": symbol, "event": event},
            priority="normal",
            notif_type="market_alert",
        )
