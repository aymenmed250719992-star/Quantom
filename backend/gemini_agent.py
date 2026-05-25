"""
GeminiAgent — Multi-key rotation pool with automatic failover.

Supports up to 10 API keys:
  GEMINI_API_KEY       (primary)
  GEMINI_API_KEY_2     (secondary)
  GEMINI_API_KEY_3     ...
  ...
  GEMINI_API_KEY_10

When a key hits the daily 429 quota:
  1. Marks it exhausted for 24 h (persisted to disk — survives restarts)
  2. Immediately switches to the next available key
  3. Broadcasts a notification to the mobile app

Consultation mode (2+ keys available, borderline confidence 65-79%):
  - Queries a second key independently
  - If they AGREE on action → averages confidence, adds +5% bonus
  - If they DISAGREE → confidence reduced -10% (more cautious)
"""

import json
import os
import time
from typing import Any, Optional

from dotenv import load_dotenv
from trading_knowledge import SYSTEM_PROMPT, TRADING_KNOWLEDGE

load_dotenv()

_QUOTA_DIR = os.path.dirname(__file__)
_CONSULTATION_THRESHOLD_LOW  = 65  # confidence below this → no consultation
_CONSULTATION_THRESHOLD_HIGH = 80  # confidence above this → no consultation (already strong)


# ── Per-key persistence helpers ───────────────────────────────────────────────

def _quota_path(idx: int) -> str:
    return os.path.join(_QUOTA_DIR, f".gemini_quota_{idx}")


def _load_quota_reset(idx: int) -> float:
    try:
        p = _quota_path(idx)
        if os.path.exists(p):
            val = float(open(p).read().strip())
            if val > time.time():
                return val
    except Exception:
        pass
    return 0.0


def _save_quota_reset(idx: int, ts: float) -> None:
    try:
        with open(_quota_path(idx), "w") as f:
            f.write(str(ts))
    except Exception:
        pass


def _clear_quota_reset(idx: int) -> None:
    try:
        p = _quota_path(idx)
        if os.path.exists(p):
            os.remove(p)
    except Exception:
        pass


# ── Single key slot ───────────────────────────────────────────────────────────

class GeminiKeySlot:
    """One API key with its own quota state and usage counters."""

    def __init__(self, idx: int, api_key: str) -> None:
        self.idx   = idx
        self.label = f"Key #{idx + 1}"
        self._client: Any = None
        self._quota_reset_at: float = _load_quota_reset(idx)
        self._quota_exhausted: bool = self._quota_reset_at > time.time()
        self.total_calls   = 0
        self.success_calls = 0
        self.failed_calls  = 0

        try:
            from google import genai as genai_sdk
            # GOOGLE_API_KEY already removed at startup (main.py) — use our explicit key
            self._client = genai_sdk.Client(api_key=api_key)
        except Exception as e:
            print(f"[Gemini] {self.label} init error: {e}")

        if self._quota_exhausted:
            hrs = (self._quota_reset_at - time.time()) / 3600
            print(f"[Gemini] {self.label} quota exhausted — retry in {hrs:.1f}h (from disk)")
        else:
            print(f"[Gemini] {self.label} ready ✅")

    @property
    def available(self) -> bool:
        if self._client is None:
            return False
        if self._quota_exhausted:
            if time.time() >= self._quota_reset_at:
                self._quota_exhausted = False
                _clear_quota_reset(self.idx)
                print(f"[Gemini] {self.label} quota restored — back online ✅")
                return True
            return False
        return True

    def mark_exhausted(self, error_str: str = "") -> None:
        """
        Smart cooldown: per-minute rate limit → 2 min cooldown.
        Daily quota exhaustion → 24 h cooldown.
        """
        err_lower = error_str.lower()
        # Retry hint in the error tells us the real wait time
        retry_secs = 0
        import re as _re
        m = _re.search(r"retry[^0-9]*(\d+(?:\.\d+)?)\s*s", error_str, _re.IGNORECASE)
        if m:
            retry_secs = float(m.group(1))

        # "per_day" or "PerDay" in the quota metric → true daily exhaustion
        is_daily = "per_day" in err_lower or "perday" in err_lower or "permodel-freetier" in err_lower or retry_secs > 3600
        if is_daily and "minute" not in err_lower and retry_secs > 3600:
            cooldown = 24 * 3600
            label = "24 h"
        elif retry_secs > 0:
            cooldown = max(retry_secs + 10, 120)   # add 10s buffer, min 2 min
            label = f"{cooldown/60:.1f} min"
        else:
            # Default: 2-min cooldown (will self-heal quickly)
            cooldown = 120
            label = "2 min"

        self._quota_reset_at  = time.time() + cooldown
        self._quota_exhausted = True
        _save_quota_reset(self.idx, self._quota_reset_at)
        print(f"[Gemini] {self.label} quota hit — cooldown {label}")

    def hours_remaining(self) -> float:
        return max(0.0, (self._quota_reset_at - time.time()) / 3600)

    def status(self) -> dict:
        return {
            "label":           self.label,
            "available":       self.available,
            "exhausted":       self._quota_exhausted,
            "hours_remaining": round(self.hours_remaining(), 1),
            "total_calls":     self.total_calls,
            "success_calls":   self.success_calls,
            "failed_calls":    self.failed_calls,
        }


# ── Multi-key pool ─────────────────────────────────────────────────────────────

class GeminiAgent:
    """
    Singleton — always call GeminiAgent.get_instance().
    Manages a pool of API keys and rotates them automatically on quota errors.
    """

    _instance: Optional["GeminiAgent"] = None

    @classmethod
    def get_instance(cls) -> "GeminiAgent":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Force-recreate the singleton on next get_instance() call."""
        cls._instance = None

    def __init__(self) -> None:
        self._slots: list[GeminiKeySlot] = []
        self._active_idx: int = 0
        self._model_name   = "gemini-2.5-flash"
        self._system_prompt = SYSTEM_PROMPT
        self.min_confidence = int(os.environ.get("MIN_CONFIDENCE_SCORE", 55))

        self._reload_keys()

    def _reload_keys(self) -> None:
        """Load all Gemini keys from environment variables into the slot pool."""
        existing_keys = {s._client for s in self._slots if s._client is not None}
        added = 0
        for i in range(10):
            env_var = "GEMINI_API_KEY" if i == 0 else f"GEMINI_API_KEY_{i + 1}"
            key = os.environ.get(env_var, "").strip()
            if not key or key.startswith("your_"):
                continue
            # Skip if already in pool (same index)
            already = any(s.idx == i for s in self._slots)
            if not already:
                self._slots.append(GeminiKeySlot(i, key))
                added += 1

        if not self._slots:
            print("[Gemini] No API keys configured — using rule-based fallback only")
        else:
            print(f"[Gemini] Pool ready: {len(self._slots)} key(s) configured")

    def inject_key(self, api_key: str) -> bool:
        """
        Inject a new Gemini key into the pool at runtime (after DB load).
        Returns True if the key was newly added.
        """
        # Find next available slot index
        used_idxs = {s.idx for s in self._slots}
        for i in range(10):
            if i not in used_idxs:
                env_var = "GEMINI_API_KEY" if i == 0 else f"GEMINI_API_KEY_{i + 1}"
                os.environ[env_var] = api_key
                self._slots.append(GeminiKeySlot(i, api_key))
                print(f"[Gemini] Key #{i+1} injected at runtime ✅")
                return True
        return False

    # ── Key selection ─────────────────────────────────────────────────────────

    def _get_slot(self) -> Optional[GeminiKeySlot]:
        """Return the first available key, rotating past exhausted ones."""
        for offset in range(len(self._slots)):
            idx = (self._active_idx + offset) % len(self._slots)
            if self._slots[idx].available:
                self._active_idx = idx
                return self._slots[idx]
        return None

    def _get_second_slot(self) -> Optional[GeminiKeySlot]:
        """Return a second available key (different from current) for consultation."""
        primary = self._active_idx
        for offset in range(1, len(self._slots)):
            idx = (primary + offset) % len(self._slots)
            if self._slots[idx].available:
                return self._slots[idx]
        return None

    def _has_keys(self) -> bool:
        return bool(self._slots)

    # ── Low-level call ────────────────────────────────────────────────────────

    def _call_slot(self, slot: GeminiKeySlot, prompt: str, temperature: float = 0.3) -> str:
        """Synchronous Gemini call. Returns raw text or raises."""
        from google import genai as genai_sdk
        config = genai_sdk.types.GenerateContentConfig(
            system_instruction=self._system_prompt,
            temperature=temperature,
        )
        slot.total_calls += 1
        response = slot._client.models.generate_content(
            model=self._model_name,
            contents=prompt,
            config=config,
        )
        slot.success_calls += 1
        return response.text.strip()

    def _is_quota_error(self, err: Exception) -> bool:
        s = str(err)
        return "429" in s or "RESOURCE_EXHAUSTED" in s or "quota" in s.lower()

    # ── Market analysis ───────────────────────────────────────────────────────

    async def _analyze_with_ai_agent(
        self, symbol: str, prompt: str, indicators: dict
    ) -> Optional[dict]:
        """
        Fallback: use AIAgent's multi-provider pool (Groq, OpenAI, custom…)
        for trading analysis when no Gemini key is available.
        Returns a parsed decision dict or None on failure.
        """
        try:
            from ai_agent import AIAgent
            agent = AIAgent.get_instance()
            slot = agent._get_slot()
            if slot is None:
                return None
            system = (
                "You are a crypto trading analyst. "
                "Respond ONLY with a single JSON object — no markdown, no code block. "
                "Keys: action (BUY/SELL/HOLD), confidence (0-99 int), "
                "reasoning (str), stop_loss_percent (float), take_profit_percent (float), pattern (str)."
            )
            text = slot.call(system, prompt, temperature=0.3)
            decision = self._parse_json_decision(text, symbol)
            if decision:
                lbl = slot.label
                decision["reasoning"] = f"[{lbl}] {decision.get('reasoning', '')}"
                print(f"[Gemini→{lbl}] {symbol}: {decision.get('action')} {decision.get('confidence')}%")
            return decision
        except Exception as e:
            print(f"[Gemini→AIAgent] fallback error: {e}")
            return None

    async def analyze_market(
        self, symbol: str, ohlcv: list, indicators: dict, lessons: list
    ) -> dict:
        slot = self._get_slot()
        prompt = self._build_analysis_prompt(symbol, ohlcv, indicators, lessons)

        if slot is None:
            # ── No Gemini key: try AIAgent multi-provider pool (Groq/OpenAI/custom) ──
            ai_decision = await self._analyze_with_ai_agent(symbol, prompt, indicators)
            if ai_decision:
                ai_decision["confidence"] = int(ai_decision.get("confidence", 0))
                if ai_decision["confidence"] < self.min_confidence:
                    ai_decision["action"] = "HOLD"
                return ai_decision
            return self._fallback_decision(symbol, indicators, all_exhausted=True)

        try:
            text    = self._call_slot(slot, prompt, temperature=0.3)
            decision = self._parse_json_decision(text, symbol)
            if decision is None:
                return self._fallback_decision(symbol, indicators)

            decision["confidence"] = int(decision.get("confidence", 0))
            if decision["confidence"] < self.min_confidence:
                decision["action"] = "HOLD"

            # ── Consultation: query a second key if confidence is borderline ──
            second = self._get_second_slot()
            if (
                second is not None
                and decision["action"] in ("BUY", "SELL")
                and _CONSULTATION_THRESHOLD_LOW <= decision["confidence"] < _CONSULTATION_THRESHOLD_HIGH
            ):
                decision = await self._consult(decision, prompt, second, symbol, indicators)

            return decision

        except Exception as e:
            slot.failed_calls += 1
            err_str = str(e)
            if self._is_quota_error(e):
                slot.mark_exhausted(err_str)
                # Try next key immediately
                fallback_slot = self._get_slot()
                if fallback_slot:
                    try:
                        text2 = self._call_slot(fallback_slot, prompt, temperature=0.3)
                        d2 = self._parse_json_decision(text2, symbol)
                        if d2:
                            d2["confidence"] = int(d2.get("confidence", 0))
                            d2["reasoning"] = f"[{fallback_slot.label}] {d2.get('reasoning', '')}"
                            return d2
                    except Exception as e2:
                        if self._is_quota_error(e2):
                            fallback_slot.mark_exhausted(str(e2))
                result = self._fallback_decision(symbol, indicators)
                result["reasoning"] = f"[Rule-based] {result['reasoning']} ({slot.label} quota — {len([s for s in self._slots if s.available])} key(s) left)"
                return result
            return self._fallback_decision(symbol, indicators)

    async def _consult(
        self,
        primary_decision: dict,
        prompt: str,
        second_slot: GeminiKeySlot,
        symbol: str,
        indicators: dict,
    ) -> dict:
        """Query a second key and merge the two opinions."""
        try:
            text2 = self._call_slot(second_slot, prompt, temperature=0.3)
            d2 = self._parse_json_decision(text2, symbol)
            if d2 is None:
                return primary_decision

            d2["confidence"] = int(d2.get("confidence", 0))
            a1 = primary_decision["action"]
            a2 = d2["action"]
            c1 = primary_decision["confidence"]
            c2 = d2["confidence"]

            if a1 == a2:
                # Agreement → average confidence + 5% bonus
                merged_conf = min(99, int((c1 + c2) / 2) + 5)
                primary_decision["confidence"] = merged_conf
                primary_decision["reasoning"] = (
                    f"[2-key agreement +5%] {primary_decision.get('reasoning', '')}"
                )
            else:
                # Disagreement → reduce confidence, lean toward HOLD
                merged_conf = max(0, int((c1 + c2) / 2) - 10)
                primary_decision["confidence"] = merged_conf
                if merged_conf < self.min_confidence:
                    primary_decision["action"] = "HOLD"
                primary_decision["reasoning"] = (
                    f"[2-key disagreement −10%] K1={a1}@{c1}% K2={a2}@{c2}% → {primary_decision['action']}"
                )
        except Exception as e:
            if self._is_quota_error(e):
                second_slot.mark_exhausted(str(e))
        return primary_decision

    # ── Chat ─────────────────────────────────────────────────────────────────

    async def chat(
        self, message: str, trades: list, status: dict, performance: dict | None = None
    ) -> dict:
        """Returns {"response": str, "ai_powered": bool}"""
        closed    = [t for t in trades if t.get("status") == "closed"]
        wins      = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
        total_pnl = sum(float(t.get("pnl") or 0) for t in closed)
        stats_line = (
            f"{len(closed)} صفقة مغلقة، {wins} رابحة، "
            f"نسبة الفوز {status.get('win_rate', 0):.1f}%، "
            f"إجمالي الربح/الخسارة ${total_pnl:.4f}"
        )

        if self._get_slot() is None:
            return {
                "response": self._rule_based_chat(message, trades, status, closed, wins, total_pnl, stats_line),
                "ai_powered": False,
            }

        prompt = self._build_chat_prompt(message, trades, status, performance, stats_line)

        # Try every available key until one succeeds
        for attempt in range(len(self._slots)):
            slot = self._get_slot()
            if slot is None:
                break
            try:
                result = self._call_slot(slot, prompt, temperature=0.7)
                return {"response": result, "ai_powered": True}
            except Exception as e:
                slot.failed_calls += 1
                err_str = str(e)
                if self._is_quota_error(e):
                    slot.mark_exhausted(err_str)
                    continue          # rotate to next key and retry
                # Non-quota error — fall through to rule-based
                print(f"[Gemini Chat] non-quota error on {slot.label}: {err_str[:120]}")
                break

        return {
            "response": self._rule_based_chat(message, trades, status, closed, wins, total_pnl, stats_line),
            "ai_powered": False,
        }

    def _rule_based_chat(
        self, message: str, trades: list, status: dict,
        closed: list, wins: int, total_pnl: float, stats_line: str
    ) -> str:
        """
        Smart rule-based chat that answers trading questions without Gemini.
        Activated when all Gemini keys are quota-exhausted.
        """
        msg = message.lower().strip()
        win_rate   = status.get("win_rate", 0)
        mode       = status.get("mode", "demo")
        running    = status.get("is_running", False)
        open_count = len([t for t in trades if t.get("status") == "open"])

        # ── Greetings ──────────────────────────────────────────────────────
        if any(w in msg for w in ["hi", "hello", "مرحب", "هلا", "اهلا", "السلام", "مساء", "صباح"]):
            return (
                f"مرحباً! 👋 أنا مساعدك للتداول الإسلامي.\n\n"
                f"📊 **وضعك الحالي:**\n"
                f"• الوضع: {'🟢 LIVE' if mode == 'live' else '🔵 DEMO'}\n"
                f"• الـ Autopilot: {'✅ يعمل' if running else '⏸ متوقف'}\n"
                f"• الصفقات المفتوحة: {open_count}\n"
                f"• {stats_line}\n\n"
                f"اسألني عن أي شيء — الأداء، الاستراتيجية، المخاطر، أو التداول الحلال."
            )

        # ── Performance ────────────────────────────────────────────────────
        if any(w in msg for w in ["أداء", "performance", "نتائج", "ربح", "خسار", "profit", "loss", "pnl", "win"]):
            losses = len(closed) - wins
            avg_win = (
                sum(float(t.get("pnl") or 0) for t in closed if (t.get("pnl") or 0) > 0) / wins
                if wins > 0 else 0
            )
            avg_loss = (
                sum(float(t.get("pnl") or 0) for t in closed if (t.get("pnl") or 0) <= 0) / losses
                if losses > 0 else 0
            )
            rr = abs(avg_win / avg_loss) if avg_loss != 0 else 0
            rating = "ممتاز 🏆" if win_rate >= 65 else "جيد ✅" if win_rate >= 50 else "يحتاج تحسين ⚠️"
            return (
                f"📊 **تقرير الأداء الكامل:**\n\n"
                f"• الصفقات المغلقة: {len(closed)} ({wins} رابحة / {losses} خاسرة)\n"
                f"• نسبة الفوز: {win_rate:.1f}% — {rating}\n"
                f"• إجمالي PNL: ${total_pnl:+.4f}\n"
                f"• متوسط الربح: ${avg_win:+.4f}\n"
                f"• متوسط الخسارة: ${avg_loss:+.4f}\n"
                f"• نسبة المخاطرة/المكافأة: 1:{rr:.2f}\n"
                f"• الصفقات المفتوحة الآن: {open_count}\n\n"
                f"{'🎯 نسبة فوز جيدة! حافظ على الاستراتيجية.' if win_rate >= 55 else '💡 نصيحة: رفع عتبة الثقة في الإعدادات قد يحسن النتائج.'}"
            )

        # ── Strategy ───────────────────────────────────────────────────────
        if any(w in msg for w in ["استراتيج", "strategy", "خطة", "plan", "كيف", "how"]):
            return (
                f"🧠 **استراتيجية البوت الحالية:**\n\n"
                f"البوت يستخدم نظام **6 محفزات ذكية** للتعلم:\n"
                f"• 🔴 3 خسائر متتالية → تأمل فوري + رفع العتبة\n"
                f"• 🛑 5 خسائر → إيقاف طارئ لحماية رأس المال\n"
                f"• 🏆 5 انتصارات → تثبيت الاستراتيجية الناجحة\n"
                f"• 📉 هبوط نسبة الفوز >10% → تحليل فوري\n"
                f"• 🕐 كل 30 دقيقة → تأمل دوري\n"
                f"• 📊 كل 10 صفقات → مراجعة شاملة\n\n"
                f"🎯 **الهدف:** نسبة فوز >65% مع الالتزام الكامل بالشريعة الإسلامية.\n"
                f"✅ Spot Trading فقط — لا رافعة، لا هامش، لا ربا."
            )

        # ── Halal / Islamic ────────────────────────────────────────────────
        if any(w in msg for w in ["حلال", "إسلام", "شريعة", "ربا", "halal", "islam", "riba", "haram", "حرام"]):
            return (
                f"☪️ **الامتثال الشرعي الكامل:**\n\n"
                f"✅ **مسموح (حلال):**\n"
                f"• Spot Trading فقط — ملكية فعلية للأصول\n"
                f"• شراء وبيع مباشر بدون ديون\n"
                f"• عملات رقمية حلالة (BTC, ETH, SOL...)\n\n"
                f"❌ **محظور تلقائياً (حرام):**\n"
                f"• Futures — عقود آجلة محظورة\n"
                f"• Margin/Leverage — رافعة مالية (ربا)\n"
                f"• Short Selling — بيع ما لا تملك\n"
                f"• Swap/Perpetual — محظورة شرعاً\n\n"
                f"🔒 هذه القيود مدمجة في الكود ولا يمكن تجاوزها."
            )

        # ── Risk ────────────────────────────────────────────────────────────
        if any(w in msg for w in ["مخاطر", "risk", "خطر", "stop loss", "وقف", "loss"]):
            return (
                f"⚖️ **إدارة المخاطر:**\n\n"
                f"• الحد الأقصى لكل صفقة: 1.5% من المحفظة\n"
                f"• وقف الخسارة (Stop Loss): تلقائي لكل صفقة\n"
                f"• هدف الربح (Take Profit): تلقائي لكل صفقة\n"
                f"• الحماية الطارئة: إيقاف عند 5 خسائر متتالية\n\n"
                f"💡 يمكنك تعديل نسبة المخاطرة من شاشة **الإعدادات** (CONFIG).\n"
                f"⚠️ الحد الأقصى المسموح به: 3% لكل صفقة."
            )

        # ── Status / Running ───────────────────────────────────────────────
        if any(w in msg for w in ["حال", "status", "يعمل", "running", "autopilot", "وضع"]):
            recent = sorted(
                [t for t in trades if t.get("status") == "closed"],
                key=lambda x: x.get("created_at", ""), reverse=True
            )[:3]
            recent_txt = ""
            for t in recent:
                pnl = float(t.get("pnl") or 0)
                recent_txt += f"  • {t.get('symbol')} {'✅' if pnl > 0 else '❌'} ${pnl:+.4f}\n"

            return (
                f"🤖 **الحالة الحالية:**\n\n"
                f"• الوضع: {'🟢 LIVE — تداول حقيقي' if mode == 'live' else '🔵 DEMO — تداول ورقي'}\n"
                f"• Autopilot: {'✅ يعمل' if running else '⏸ متوقف — اضغط Start'}\n"
                f"• الصفقات المفتوحة: {open_count}\n"
                f"• {stats_line}\n"
                + (f"\n📋 **آخر الصفقات:**\n{recent_txt}" if recent_txt else "")
            )

        # ── KuCoin / Exchange ───────────────────────────────────────────────
        if any(w in msg for w in ["kucoin", "exchange", "بورصة", "منصة", "api", "مفتاح"]):
            return (
                f"🔑 **معلومات KuCoin:**\n\n"
                f"KuCoin هي المنصة التي يتداول عليها البوت.\n\n"
                f"**ما يستخدمه البوت:**\n"
                f"• أسعار السوق الحية (بدون API)\n"
                f"• تنفيذ الأوامر الحقيقية (يحتاج API Key)\n"
                f"• فحص رصيدك الفعلي\n\n"
                f"**للتداول الحقيقي تحتاج:**\n"
                f"1. API Key\n"
                f"2. API Secret\n"
                f"3. API Passphrase\n\n"
                f"أضفها من شاشة **الإعدادات** (CONFIG) ← قسم KuCoin API."
            )

        # ── Default helpful response ────────────────────────────────────────
        topics = [
            "📊 **أداء البوت** — اسأل: 'كيف أداء البوت؟'",
            "⚖️ **إدارة المخاطر** — اسأل: 'ما هي المخاطر؟'",
            "🧠 **الاستراتيجية** — اسأل: 'ما هي استراتيجية البوت؟'",
            "☪️ **الحلال والحرام** — اسأل: 'هل البوت حلال؟'",
            "🤖 **الحالة** — اسأل: 'ما حالة البوت الآن؟'",
        ]
        return (
            f"📊 **إحصائياتك:** {stats_line}\n\n"
            f"يسعدني مساعدتك! إليك ما يمكنني الإجابة عنه:\n\n"
            + "\n".join(topics)
            + f"\n\n💡 *ملاحظة: الـ AI في فترة راحة يومية — أُجيبك بالقواعد الذكية.*"
        )

    # ── Status ────────────────────────────────────────────────────────────────

    def pool_status(self) -> dict:
        available = [s for s in self._slots if s.available]
        active_label = self._slots[self._active_idx].label if self._slots else "none"
        return {
            "total_keys":    len(self._slots),
            "available_keys": len(available),
            "active_key":    active_label,
            "all_exhausted": len(self._slots) > 0 and len(available) == 0,
            "keys":          [s.status() for s in self._slots],
        }

    # Keep old name for compatibility
    def quota_status(self) -> dict:
        slot = self._get_slot()
        return {
            "exhausted":      slot is None and len(self._slots) > 0,
            "hours_remaining": 0 if slot else min(
                (s.hours_remaining() for s in self._slots), default=0
            ),
        }

    # ── Prompt builders ───────────────────────────────────────────────────────

    def _build_analysis_prompt(
        self, symbol: str, ohlcv: list, indicators: dict, lessons: list
    ) -> str:
        lessons_text = ""
        if lessons:
            lessons_text = (
                "\n━━━ LESSONS FROM PAST TRADES ━━━\n"
                + "\n".join(f"  • {l.get('lesson', '')}" for l in lessons[:8])
            )

        recent = ohlcv[-15:] if len(ohlcv) >= 15 else ohlcv
        candles = "\n".join(
            f"  [{i+1:02d}] O:{c[1]:.4f} H:{c[2]:.4f} L:{c[3]:.4f} C:{c[4]:.4f} V:{c[5]:.0f}"
            for i, c in enumerate(recent)
        )
        rsi = indicators.get("rsi", 50)
        macd_hist = indicators.get("macd_histogram", 0)
        bb_pct = indicators.get("bb_pct", 0.5)

        rsi_signal = (
            "STRONGLY OVERSOLD — look for bullish reversal" if rsi < 25 else
            "Oversold zone" if rsi < 35 else
            "STRONGLY OVERBOUGHT — look for bearish reversal" if rsi > 75 else
            "Overbought zone" if rsi > 65 else "Neutral zone"
        )
        bb_signal = (
            "Price near LOWER band — mean reversion BUY zone" if bb_pct < 0.1 else
            "Price near UPPER band — mean reversion SELL zone" if bb_pct > 0.9 else
            f"BB position: {bb_pct:.2f}"
        )
        macd_signal = (
            "MACD POSITIVE & RISING — bullish" if macd_hist > 0.0001 else
            "MACD NEGATIVE & FALLING — bearish" if macd_hist < -0.0001 else
            "MACD near zero — neutral"
        )

        # بناء سياق الصفقة المفتوحة إن وُجدت
        open_pos_text = ""
        open_trade = indicators.get("_open_trade")
        if open_trade:
            entry_p    = float(open_trade.get("entry_price") or 0)
            cur_p      = indicators.get("current_price", 0)
            profit_pct = ((cur_p - entry_p) / entry_p * 100) if entry_p > 0 else 0
            open_pos_text = (
                f"\n⚠️  OPEN POSITION: BUY @ ${entry_p:.4f} | "
                f"Current PnL: {profit_pct:+.2f}% | "
                f"You MUST consider SELL to lock profits or cut losses.\n"
            )

        return f"""{TRADING_KNOWLEDGE}

━━━ CURRENT ANALYSIS REQUEST ━━━
Symbol: {symbol}
Price: ${indicators.get('current_price', 0):.4f} ({indicators.get('price_change_pct', 0):+.2f}%)
Market: {indicators.get('market_condition', 'unknown').upper()}
{open_pos_text}
INDICATORS:
• RSI(14): {rsi:.2f} → {rsi_signal}
• MACD: {indicators.get('macd', 0):.6f} | Signal: {indicators.get('macd_signal', 0):.6f} | Hist: {macd_hist:.6f} → {macd_signal}
• BB Upper: ${indicators.get('bb_upper', 0):.4f} | Mid: ${indicators.get('bb_middle', 0):.4f} | Lower: ${indicators.get('bb_lower', 0):.4f}
• BB %B: {bb_pct:.4f} → {bb_signal}
• Volume: {indicators.get('volume', 0):.2f}

PRICE ACTION (last 15 candles):
{candles}
{lessons_text}

Respond ONLY with valid JSON:
{{"action":"BUY"|"SELL"|"HOLD","symbol":"{symbol}","confidence":0-100,"reasoning":"specific signals","stop_loss_percent":0.5-3.0,"take_profit_percent":1.0-6.0,"pattern":"pattern name"}}"""

    def _build_chat_prompt(
        self,
        message: str,
        trades: list,
        status: dict,
        performance: dict | None,
        stats_line: str,
    ) -> str:
        closed    = [t for t in trades if t.get("status") == "closed"]
        wins      = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
        total_pnl = sum(float(t.get("pnl") or 0) for t in closed)

        perf_text = ""
        if performance:
            perf_text = (
                f"\nPERFORMANCE:\n"
                f"• Target: {performance.get('target_win_rate', 65):.1f}% | Actual: {performance.get('actual_win_rate', 0):.1f}%\n"
                f"• On Target: {'YES' if performance.get('on_target') else 'NO'}\n"
                f"• Profit Factor: {performance.get('profit_factor', 0):.2f}"
            )

        recent = "\n".join(
            f"• {t.get('symbol')} {t.get('side','').upper()} @ ${t.get('entry_price', 0):.4f} | "
            f"PNL: ${t.get('pnl') or 0:.4f} | Conf: {t.get('ai_confidence', 0)}%"
            for t in trades[:10]
        ) or "No trades yet."

        return f"""{TRADING_KNOWLEDGE}

BOT STATUS: {status.get('mode','demo').upper()} | Running: {status.get('is_running', False)}
Trades: {status.get('total_trades', 0)} | Win Rate: {status.get('win_rate', 0):.1f}%
{perf_text}

RECENT TRADES:
{recent}

USER QUESTION: {message}

Answer in the same language as the user. Be specific, 4-6 sentences."""

    # ── Parsers & fallbacks ───────────────────────────────────────────────────

    def _parse_json_decision(self, text: str, symbol: str) -> dict | None:
        try:
            if "```" in text:
                for part in text.split("```"):
                    s = part.strip().lstrip("json").strip()
                    if s.startswith("{"):
                        text = s
                        break
            start, end = text.find("{"), text.rfind("}") + 1
            if start < 0 or end <= start:
                return None
            return json.loads(text[start:end])
        except Exception:
            return None

    def _fallback_decision(
        self, symbol: str, indicators: dict, all_exhausted: bool = False
    ) -> dict:
        """
        Rule-based signal engine — 6 signal sources, confidence formula
        ensures 3 aligned signals → 70% (just at threshold) and 4+ → 76-82%.

        Formula: min(82, 52 + total_signals * 6)
          3 signals → 70%  ✓ trades
          4 signals → 76%  ✓ confident
          5 signals → 82%  ✓ strong
        """
        rsi      = indicators.get("rsi", 50)
        macd_h   = indicators.get("macd_histogram", 0)
        bb_pct   = indicators.get("bb_pct", 0.5)
        mc           = indicators.get("market_condition", "sideways")
        pchg_90m     = indicators.get("price_change_90m", indicators.get("price_change_pct", 0))
        price        = indicators.get("current_price", 0)
        ma20         = indicators.get("ma20", 0)
        vol          = indicators.get("volume", 0)
        vol_avg      = indicators.get("volume_avg", vol)
        candle_trend = indicators.get("candle_trend", 0)   # +1 rising, -1 falling, 0 mixed

        buy_s = sell_s = 0
        sigs: list[str] = []

        # ── 1. RSI ────────────────────────────────────────────────────────────
        if rsi < 28:   buy_s += 2; sigs.append(f"RSI strongly oversold({rsi:.0f})")
        elif rsi < 40: buy_s += 1; sigs.append(f"RSI oversold({rsi:.0f})")
        elif rsi > 68: sell_s += 2; sigs.append(f"RSI strongly overbought({rsi:.0f})")  # كان 72
        elif rsi > 57: sell_s += 1; sigs.append(f"RSI overbought({rsi:.0f})")           # كان 60

        # ── 2. MACD histogram ─────────────────────────────────────────────────
        if macd_h > 0.0001:    buy_s += 1; sigs.append("MACD bullish")
        elif macd_h < -0.0001: sell_s += 1; sigs.append("MACD bearish")

        # ── 3. Bollinger Bands %B ─────────────────────────────────────────────
        if bb_pct < 0.1:   buy_s += 2; sigs.append("BB lower band touch")
        elif bb_pct < 0.25: buy_s += 1; sigs.append("BB below midline")
        elif bb_pct > 0.9: sell_s += 2; sigs.append("BB upper band touch")
        elif bb_pct > 0.75: sell_s += 1; sigs.append("BB above midline")

        # ── 4. Market condition (90-min trend — much more stable than 15-min) ──
        if mc in ("oversold", "bullish"):
            buy_s += 1; sigs.append(f"market:{mc}")
        elif mc in ("overbought", "bearish"):
            sell_s += 1; sigs.append(f"market:{mc}")

        # ── 5. Price vs MA20 (threshold 0.3% — realistic for 15m candles) ────
        if ma20 > 0:
            if price < ma20 * 0.997:   buy_s += 1; sigs.append("Price below MA20")
            elif price > ma20 * 1.003: sell_s += 1; sigs.append("Price above MA20")

        # ── 6. 3-candle consecutive trend ─────────────────────────────────────
        if candle_trend == 1:
            buy_s += 1; sigs.append("3-candle uptrend")
        elif candle_trend == -1:
            sell_s += 1; sigs.append("3-candle downtrend")

        # ── 7. Volume confirmation ────────────────────────────────────────────
        if vol_avg > 0 and vol > vol_avg * 1.5:
            if buy_s > sell_s:   buy_s  += 1; sigs.append("Volume surge(buy)")
            elif sell_s > buy_s: sell_s += 1; sigs.append("Volume surge(sell)")

        prefix = "[Rule-based] "
        total_buy  = buy_s
        total_sell = sell_s

        if total_buy >= 3 and total_buy > total_sell:
            conf = min(82, 52 + total_buy * 6)
            return {
                "action": "BUY", "symbol": symbol, "confidence": conf,
                "reasoning": prefix + ", ".join(sigs),
                "stop_loss_percent": 1.5, "take_profit_percent": 3.0,
                "pattern": "rule-based oversold",
            }
        # SELL: خُفِّضت من 3 إشارات إلى 2 لأن البيع أسهل تقنياً من الشراء
        if total_sell >= 2 and total_sell > total_buy:
            conf = min(80, 50 + total_sell * 7)
            return {
                "action": "SELL", "symbol": symbol, "confidence": conf,
                "reasoning": prefix + ", ".join(sigs),
                "stop_loss_percent": 1.5, "take_profit_percent": 3.0,
                "pattern": "rule-based overbought",
            }

        # Not enough aligned signals — return HOLD with signal summary
        summary = ", ".join(sigs) if sigs else "no signals"
        return {
            "action": "HOLD", "symbol": symbol, "confidence": 30,
            "reasoning": f"{prefix}Weak signals ({total_buy}B/{total_sell}S): {summary}",
            "stop_loss_percent": 1.5, "take_profit_percent": 3.0,
            "pattern": "no clear signal",
        }
