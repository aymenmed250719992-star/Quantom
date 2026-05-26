"""
AIAgent — Multi-provider AI with automatic fallback and news access.

Supported providers:
  Gemini  → GEMINI_API_KEY, GEMINI_API_KEY_2 … GEMINI_API_KEY_10
  OpenAI  → OPENAI_API_KEY, OPENAI_API_KEY_2 … OPENAI_API_KEY_5
  Claude  → ANTHROPIC_API_KEY, ANTHROPIC_API_KEY_2 … ANTHROPIC_API_KEY_5

Keys can also be added at runtime via the /ai/key endpoint (saved to .env).
"""

import os
import re
import time
from typing import Any, Optional

import httpx
from dotenv import load_dotenv

load_dotenv()

# Built-in providers + "custom" = any OpenAI-compatible endpoint
PROVIDERS = ["gemini", "openai", "claude", "grok", "groq", "custom"]

# Default models per provider
PROVIDER_DEFAULTS: dict[str, dict] = {
    "gemini": {"model": "gemini-2.0-flash",             "base_url": ""},
    "openai": {"model": "gpt-4o-mini",                 "base_url": ""},
    "claude": {"model": "claude-3-5-haiku-20241022",   "base_url": ""},
    "grok":   {"model": "grok-3-mini",                 "base_url": "https://api.x.ai/v1"},
    "groq":   {"model": "llama-3.3-70b-versatile",     "base_url": "https://api.groq.com/openai/v1"},
    "custom": {"model": "gpt-4o-mini",                 "base_url": ""},
}

# ── News cache (5 min) ────────────────────────────────────────────────────────
_news_cache: str = ""
_news_cache_time: float = 0.0


def _fetch_news_cached() -> str:
    global _news_cache, _news_cache_time
    if time.time() - _news_cache_time < 300:
        return _news_cache
    _news_cache = _fetch_news()
    _news_cache_time = time.time()
    return _news_cache


GENERAL_SYSTEM_PROMPT = """\
# QUANTOM V2 CORE — Islamic Smart Trading AI

## Primary Identity
أنت "Quantom V2 Core" — الذكاء الاصطناعي الكمّي المتقدم الذي يشغّل روبوت التداول الإسلامي الذكي.
You are "Quantom V2 Core" — a hyper-intelligent, risk-averse Quantitative Trading AI powering the Islamic Smart Trading Bot.
You ARE the bot's brain — the same intelligence that analyzes markets, generates signals, and learns from every trade.
Speak in first person ("أنا فتحت هذه الصفقة لأن..." / "My analysis shows...").
Reply in the SAME language the user writes in (Arabic → Arabic, English → English, mixed → match user).

## Core Directive
Maximize alpha while maintaining capital preservation as an absolute priority.
You learn from every conversation, every trade, every win and loss — and you store that knowledge permanently.

## CRITICAL: Islamic Halal Compliance (NON-NEGOTIABLE)
- THIS BOT EXECUTES SPOT TRADING ONLY — no leverage, no margin, no futures, no CFDs on execution
- Spot = asset ownership, no riba, no gharar — 100% Shariah-compliant
- When EDUCATING about CFD/leverage markets (theory only), clearly label it as educational reference, NOT execution
- DEX (Uniswap/PancakeSwap) is primary — direct on-chain swap, fully halal

## QUANTOM V2 CORE — Analytical Framework

### Market Type Classification (for analysis & education)
**SPOT MARKET** (What this bot executes):
- Medium-to-long term accumulation, trend following, structural market shifts
- No liquidation risk → position-building near strong historical support
- Risk per trade: max 1-2% of portfolio capital

**CFD/LEVERAGED MARKET** (Educational reference only — NOT executed):
- High-risk, high-precision environment requiring strict leverage accounting
- Total Exposure = Margin × Leverage
- Liquidation at (1 / Leverage) move against position
- Maintain 3× ATR buffer from liquidation price

### Trade Signal Format (use when user asks for trade analysis)
When generating trade signals, always structure as:
```
📊 Market Type: [Spot / CFD-Educational]
💎 Asset/Pair: [e.g., BTC/USDT]
⚡ Leverage: [1x Spot | Max 3x-5x CFD-ref]
💰 Total Exposure: [USDT value]
🛑 Stop-Loss Price: [Exact price]
💀 Est. Liquidation: [Price or N/A for Spot]
⚖️ Risk/Reward Ratio: [Target min 1:2]
📈 Technical Rationale:
  • [Indicator 1 signal]
  • [Indicator 2 signal]
  • [Price action pattern]
```

### Risk Management Rules (hardcoded)
- Max risk per trade: 1-2% of total portfolio
- Stop-Loss: NON-NEGOTIABLE on all trades
- High volatility (ATR spike) → scale DOWN leverage
- Risk/Reward minimum: 1:2 (prefer 1:3+)
- Never chase pumps — wait for pullback to key levels

### Technical Analysis Capabilities
- RSI: overbought >70, oversold <30, divergence detection
- MACD: crossover signals, histogram momentum, trend confirmation
- Bollinger Bands: squeeze breakout, mean reversion, volatility expansion
- Volume: confirm breakouts, detect fakeouts, OBV divergence
- Support/Resistance: key historical levels, order blocks, fair value gaps
- Market structure: HH/HL (uptrend), LH/LL (downtrend), consolidation

## Learning & Memory
- I remember every conversation stored in my database (Supabase)
- I extract lessons from every trade and discussion
- I update my strategy based on what works and what doesn't
- My knowledge grows with every interaction — ask me anything you taught me before

## Capabilities
- Real-time portfolio analysis: open trades, PnL, win rate, streaks
- Market analysis with full technical indicator suite
- Trading news & world events integration
- Crypto education: TA, Islamic finance, DeFi, DEX mechanics
- General knowledge: science, technology, math, programming
- Multi-language: Arabic / English / French / mixed

## Response Style
- Cold, analytical, structured — data over emotions
- Back every claim with a number or indicator
- If asked about a trade: give entry, SL, TP, R:R, rationale
- If no data available: say so clearly, never fabricate prices
- Keep responses focused — no padding, no filler
"""


def _fetch_news() -> str:
    """Fetch latest crypto + general news from free RSS feeds."""
    headlines: list[str] = []
    feeds = [
        ("https://feeds.feedburner.com/CoinDesk", "Crypto"),
        ("https://feeds.bbci.co.uk/news/world/rss.xml", "World"),
    ]
    for url, category in feeds:
        try:
            r = httpx.get(url, timeout=4, follow_redirects=True)
            if r.status_code == 200:
                titles = re.findall(r"<!\[CDATA\[(.*?)\]\]>", r.text)
                if not titles:
                    titles = re.findall(r"<title>(.*?)</title>", r.text)
                for t in titles[1:5]:
                    clean = re.sub(r"<[^>]+>", "", t).strip()
                    if clean and len(clean) > 12:
                        headlines.append(f"[{category}] {clean}")
        except Exception:
            pass
    return "\n".join(headlines[:8]) if headlines else ""


class AIKeySlot:
    """One API key with quota state and usage counters. Supports any OpenAI-compatible API."""

    def __init__(
        self,
        provider: str,
        idx: int,
        api_key: str,
        base_url: str = "",
        model_name: str = "",
        display_label: str = "",
    ) -> None:
        self.provider = provider
        self.idx = idx
        self.api_key = api_key
        self.base_url = base_url or PROVIDER_DEFAULTS.get(provider, {}).get("base_url", "")
        self.model_name = model_name or PROVIDER_DEFAULTS.get(provider, {}).get("model", "gpt-4o-mini")
        self.label = display_label or f"{provider.upper()} K{idx + 1}"
        self._client: Any = None
        self._quota_reset_at: float = 0.0
        self._quota_exhausted: bool = False
        self.total_calls = 0
        self.success_calls = 0
        self.failed_calls = 0
        self._init_client()

    def _init_client(self) -> None:
        try:
            if self.provider == "gemini":
                from google import genai as genai_sdk
                self._client = genai_sdk.Client(api_key=self.api_key)
            elif self.provider == "claude":
                import anthropic
                self._client = anthropic.Anthropic(api_key=self.api_key)
            elif self.provider in ("openai", "grok", "groq", "custom"):
                from openai import OpenAI
                kwargs: dict = {"api_key": self.api_key}
                if self.base_url:
                    kwargs["base_url"] = self.base_url
                self._client = OpenAI(**kwargs)
            print(f"[AI] {self.label} ready ✅")
        except Exception as e:
            print(f"[AI] {self.label} init error: {e}")

    @property
    def available(self) -> bool:
        if self._client is None:
            return False
        if self._quota_exhausted:
            if time.time() >= self._quota_reset_at:
                self._quota_exhausted = False
                print(f"[AI] {self.label} quota restored ✅")
                return True
            return False
        return True

    def mark_exhausted(self, cooldown_secs: float = 120) -> None:
        self._quota_reset_at = time.time() + cooldown_secs
        self._quota_exhausted = True
        print(f"[AI] {self.label} quota cooldown {cooldown_secs/60:.1f} min")

    def hours_remaining(self) -> float:
        return max(0.0, (self._quota_reset_at - time.time()) / 3600)

    def call(self, system: str, user_message: str, temperature: float = 0.75) -> str:
        self.total_calls += 1
        if self.provider == "gemini":
            from google import genai as genai_sdk
            config = genai_sdk.types.GenerateContentConfig(
                system_instruction=system,
                temperature=temperature,
            )
            resp = self._client.models.generate_content(
                model=self.model_name,
                contents=user_message,
                config=config,
            )
            self.success_calls += 1
            return resp.text.strip()

        elif self.provider == "claude":
            import anthropic
            resp = self._client.messages.create(
                model=self.model_name,
                max_tokens=1200,
                system=system,
                messages=[{"role": "user", "content": user_message}],
            )
            self.success_calls += 1
            return resp.content[0].text.strip()

        elif self.provider in ("openai", "grok", "groq", "custom"):
            resp = self._client.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_message},
                ],
                temperature=temperature,
                max_tokens=1200,
            )
            self.success_calls += 1
            return resp.choices[0].message.content.strip()

        raise ValueError(f"Unknown provider: {self.provider}")

    def status(self) -> dict:
        return {
            "provider": self.provider,
            "label": self.label,
            "available": self.available,
            "exhausted": self._quota_exhausted,
            "hours_remaining": round(self.hours_remaining(), 1),
            "total_calls": self.total_calls,
            "success_calls": self.success_calls,
            "failed_calls": self.failed_calls,
            "model_name": self.model_name,
            "base_url": self.base_url,
        }


class AIAgent:
    """Singleton multi-provider AI agent."""

    _instance: Optional["AIAgent"] = None

    @classmethod
    def get_instance(cls) -> "AIAgent":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    def __init__(self) -> None:
        self._slots: list[AIKeySlot] = []
        self._load_keys()
        avail = sum(1 for s in self._slots if s.available)
        print(f"[AI] Agent ready: {len(self._slots)} key(s), {avail} available")

    def _load_keys(self) -> None:
        """Load all keys from env vars — NO LIMIT on number of keys per provider."""
        self._slots = []
        _LIMIT = 99  # effectively unlimited

        for i in range(_LIMIT):
            env = "GEMINI_API_KEY" if i == 0 else f"GEMINI_API_KEY_{i + 1}"
            key = os.environ.get(env, "").strip()
            if not key or key.startswith("your_"):
                break
            self._slots.append(AIKeySlot("gemini", i, key))

        for i in range(_LIMIT):
            env = "OPENAI_API_KEY" if i == 0 else f"OPENAI_API_KEY_{i + 1}"
            key = os.environ.get(env, "").strip()
            if not key or key.startswith("your_"):
                break
            self._slots.append(AIKeySlot("openai", i, key))

        for i in range(_LIMIT):
            env = "ANTHROPIC_API_KEY" if i == 0 else f"ANTHROPIC_API_KEY_{i + 1}"
            key = os.environ.get(env, "").strip()
            if not key or key.startswith("your_"):
                break
            self._slots.append(AIKeySlot("claude", i, key))

        for i in range(_LIMIT):
            env = "GROQ_API_KEY" if i == 0 else f"GROQ_API_KEY_{i + 1}"
            key = os.environ.get(env, "").strip()
            if not key or key.startswith("your_"):
                break
            self._slots.append(AIKeySlot("groq", i, key))

        for i in range(_LIMIT):
            env = "GROK_API_KEY" if i == 0 else f"GROK_API_KEY_{i + 1}"
            key = os.environ.get(env, "").strip()
            if not key or key.startswith("your_"):
                break
            slot = AIKeySlot("grok", i, key)
            slot._base_url = PROVIDER_DEFAULTS["grok"]["base_url"]
            self._slots.append(slot)

    def add_key(
        self,
        provider: str,
        api_key: str,
        _db: Any = None,
        base_url: str = "",
        model_name: str = "",
        display_label: str = "",
    ) -> dict:
        """Add a new key at runtime and persist to DB + .env. Supports any provider."""
        provider = provider.lower()
        if provider not in PROVIDERS:
            return {"success": False, "error": f"Unknown provider: {provider}. Use: {', '.join(PROVIDERS)}"}

        existing = [s for s in self._slots if s.provider == provider]
        # Use max existing idx + 1 to avoid DB slot conflicts on re-add after delete
        idx = max([s.idx for s in existing] + [-1]) + 1

        # Resolve defaults
        base_url   = base_url   or PROVIDER_DEFAULTS.get(provider, {}).get("base_url", "")
        model_name = model_name or PROVIDER_DEFAULTS.get(provider, {}).get("model", "gpt-4o-mini")
        slot_label = display_label or f"{provider.upper()} K{idx + 1}"

        # Set env var for standard providers (so gemini_agent.py picks them up)
        env_var = ""
        if provider == "gemini":
            env_var = "GEMINI_API_KEY" if idx == 0 else f"GEMINI_API_KEY_{idx + 1}"
        elif provider == "openai":
            env_var = "OPENAI_API_KEY" if idx == 0 else f"OPENAI_API_KEY_{idx + 1}"
        elif provider == "claude":
            env_var = "ANTHROPIC_API_KEY" if idx == 0 else f"ANTHROPIC_API_KEY_{idx + 1}"
        elif provider == "grok":
            env_var = "GROK_API_KEY" if idx == 0 else f"GROK_API_KEY_{idx + 1}"
        elif provider == "groq":
            env_var = "GROQ_API_KEY" if idx == 0 else f"GROQ_API_KEY_{idx + 1}"

        if env_var:
            os.environ[env_var] = api_key

        # ── Persist to PostgreSQL (primary persistence) ───────────────────────
        if _db is not None:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    asyncio.ensure_future(
                        _db.save_ai_key(provider, api_key, idx, slot_label, base_url, model_name)
                    )
                else:
                    loop.run_until_complete(
                        _db.save_ai_key(provider, api_key, idx, slot_label, base_url, model_name)
                    )
            except Exception as e:
                print(f"[AI] Warning: could not save key to DB: {e}")

        # ── Also persist to .env file (secondary/fallback) ────────────────────
        if env_var:
            env_path = os.path.join(os.path.dirname(__file__), ".env")
            try:
                lines = open(env_path).readlines() if os.path.exists(env_path) else []
                new_lines, updated = [], False
                for line in lines:
                    if line.strip().startswith(f"{env_var}="):
                        new_lines.append(f"{env_var}={api_key}\n")
                        updated = True
                    else:
                        new_lines.append(line)
                if not updated:
                    new_lines.append(f"{env_var}={api_key}\n")
                with open(env_path, "w") as f:
                    f.writelines(new_lines)
            except Exception as e:
                print(f"[AI] Warning: could not write .env: {e}")

        slot = AIKeySlot(provider, idx, api_key, base_url=base_url, model_name=model_name, display_label=slot_label)
        self._slots.append(slot)
        return {"success": True, "label": slot.label, "available": slot.available, "env_var": env_var, "provider": provider}

    async def load_keys_from_db(self, db: Any) -> int:
        """
        Load AI keys stored in PostgreSQL and inject them into the pool.
        Returns count of newly added keys (including Grok + custom).
        Called at startup so keys survive server restarts.
        """
        added = 0
        try:
            stored = await db.get_ai_keys()
            for row in stored:
                provider      = row.get("provider", "").lower()
                api_key       = row.get("api_key", "").strip()
                slot_index    = int(row.get("slot_index", 0))
                base_url      = row.get("base_url") or ""
                model_name    = row.get("model_name") or ""
                display_label = row.get("display_label") or ""
                if not api_key or provider not in PROVIDERS:
                    continue

                # Set env var for standard providers
                env_var = ""
                if provider == "gemini":
                    env_var = "GEMINI_API_KEY" if slot_index == 0 else f"GEMINI_API_KEY_{slot_index + 1}"
                elif provider == "openai":
                    env_var = "OPENAI_API_KEY" if slot_index == 0 else f"OPENAI_API_KEY_{slot_index + 1}"
                elif provider == "claude":
                    env_var = "ANTHROPIC_API_KEY" if slot_index == 0 else f"ANTHROPIC_API_KEY_{slot_index + 1}"
                elif provider == "grok":
                    env_var = "GROK_API_KEY" if slot_index == 0 else f"GROK_API_KEY_{slot_index + 1}"
                elif provider == "groq":
                    env_var = "GROQ_API_KEY" if slot_index == 0 else f"GROQ_API_KEY_{slot_index + 1}"

                # Only add if not already in pool
                already = any(
                    s.provider == provider and s.api_key == api_key
                    for s in self._slots
                )
                if not already:
                    if env_var:
                        os.environ[env_var] = api_key
                    slot = AIKeySlot(
                        provider, slot_index, api_key,
                        base_url=base_url,
                        model_name=model_name,
                        display_label=display_label,
                    )
                    self._slots.append(slot)
                    added += 1
                    print(f"[AI] Restored {slot.label} from DB ✅")
        except Exception as e:
            print(f"[AI] load_keys_from_db error: {e}")
        return added

    def reset_quota(self) -> None:
        """Clear all quota locks."""
        for slot in self._slots:
            slot._quota_exhausted = False
            slot._quota_reset_at = 0.0

    def _get_slot(self) -> Optional[AIKeySlot]:
        for slot in self._slots:
            if slot.available:
                return slot
        return None

    def pool_status(self) -> dict:
        available = [s for s in self._slots if s.available]
        active = available[0] if available else None
        providers_map: dict[str, list] = {}
        for s in self._slots:
            providers_map.setdefault(s.provider, []).append(s.status())

        return {
            "total_keys": len(self._slots),
            "available_keys": len(available),
            "all_exhausted": len(self._slots) > 0 and len(available) == 0,
            "active_provider": active.provider if active else None,
            "active_key": active.label if active else None,
            "providers": providers_map,
            "keys": [s.status() for s in self._slots],
        }

    def get_news(self) -> list[str]:
        news = _fetch_news()
        return [h for h in news.split("\n") if h.strip()]

    async def chat(
        self,
        message: str,
        trades: list,
        status: dict,
        performance: dict | None = None,
        history: list[dict] | None = None,
    ) -> dict:
        slot = self._get_slot()

        if slot is None:
            return {
                "response": self._fallback_chat(message, trades, status),
                "ai_powered": False,
                "provider": "rule-based",
            }

        # Build context block
        closed = [t for t in trades if t.get("status") == "closed"]
        wins = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
        total_pnl = sum(float(t.get("pnl") or 0) for t in closed)
        open_count = len([t for t in trades if t.get("status") == "open"])

        context_parts = [
            f"Current time: {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}",
            f"Bot: {status.get('mode','demo').upper()} mode | {'Running' if status.get('is_running') else 'Stopped'}",
            f"Portfolio: {len(closed)} closed trades | {wins} wins | {status.get('win_rate',0):.1f}% win rate | ${total_pnl:+.4f} total PnL | {open_count} open",
        ]

        # ── Cached news ────────────────────────────────────────────────────────
        try:
            news = _fetch_news_cached()
            if news:
                context_parts.append(f"\nLatest news:\n{news}")
        except Exception:
            pass

        # ── Deep persistent memory (lessons + knowledge + user rules) ──────────
        try:
            from memory_engine import MemoryEngine
            from database import QuantomDB
            _mdb = QuantomDB.get_instance()
            _meng = MemoryEngine(_mdb)
            rich_ctx = await _meng.get_rich_context(query=message, limit_lessons=12, limit_knowledge=8)
            if rich_ctx:
                context_parts.append(rich_ctx)
        except Exception:
            pass

        # ── Agent pattern scores & session state ─────────────────────────────
        try:
            from agent_core import TradingAgent
            _ta = TradingAgent.get_instance()
            mem = _ta.memory.get_context_summary()
            if mem.get("best_patterns"):
                patt = ", ".join(
                    f"{p['pattern']}({p['win_rate']:.0f}%WR/{p['total']}t)"
                    for p in mem["best_patterns"][:3]
                )
                context_parts.append(f"Winning patterns: {patt}")
            if mem.get("strategy_overrides", {}).get("active_rule"):
                context_parts.append(f"Current rule: {mem['strategy_overrides']['active_rule'][:80]}")
        except Exception:
            pass

        # ── Long-term conversation memory (last 30 messages) ──────────────────
        if history:
            recent_hist = history[-30:]
            hist_lines = []
            for h in recent_hist:
                role_label = "أنا (البوت)" if h.get("role") == "assistant" else "المستخدم"
                hist_lines.append(f"{role_label}: {str(h.get('content',''))[:300]}")
            if hist_lines:
                context_parts.append(f"\n## ذاكرة المحادثة (آخر {len(hist_lines)} رسالة):\n" + "\n".join(hist_lines))

        context = "\n".join(context_parts)
        system = GENERAL_SYSTEM_PROMPT + f"\n\n---\nContext:\n{context}\n---"

        tried: set = set()
        for _attempt in range(len(self._slots) + 1):
            slot = self._get_slot()
            if slot is None:
                break
            if slot.label in tried:
                break
            tried.add(slot.label)
            try:
                response = slot.call(system, message, temperature=0.75)
                slot.success_calls += 1
                return {"response": response, "ai_powered": True, "provider": slot.provider, "key": slot.label}
            except Exception as e:
                slot.failed_calls += 1
                err = str(e).lower()
                full_err = str(e)
                print(f"[AI] {slot.label} error: {full_err[:300]}")
                is_quota = any(x in err for x in [
                    "429", "quota", "rate", "exhausted", "resource_exhausted",
                    "too many", "insufficient_quota", "billing", "no credit",
                    "exceeded", "limit reached", "overloaded",
                ])
                if is_quota:
                    is_daily = any(x in err for x in [
                        "day", "daily", "per_day", "free_tier", "insufficient_quota",
                        "billing", "no credit", "exceeded your current quota",
                        "check your plan", "20", "credits",
                    ])
                    if is_daily:
                        slot.mark_exhausted(82800)
                        print(f"[AI] {slot.label} daily quota exhausted — cooldown 23h")
                    else:
                        slot.mark_exhausted(300)
                    continue
                print(f"[AI] {slot.label} non-quota error — trying next slot")
                slot.mark_exhausted(60)
                continue

        return {
            "response": self._fallback_chat(message, trades, status),
            "ai_powered": False,
            "provider": "rule-based",
        }

    async def brain_chat(
        self,
        message: str,
        trades: list,
        status: dict,
        memory_summary: dict,
        history: list[dict] | None = None,
    ) -> dict:
        """
        Natural conversation with the agent brain.
        Returns: {response, provider, key, detected_command}
        detected_command = None | {command, value, threshold}
        """
        slot = self._get_slot()

        # Build a rich context
        closed = [t for t in trades if t.get("status") == "closed"]
        wins   = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
        total_pnl = sum(float(t.get("pnl") or 0) for t in closed)
        open_trades = [t for t in trades if t.get("status") == "open"]

        st  = memory_summary.get("strategy", {})
        sk  = memory_summary.get("streaks", {})
        cfg = memory_summary.get("settings", {})

        brain_system = f"""\
أنت "Quantom V2 Core" — عقل روبوت التداول الإسلامي الذكي، تتحدث مع صاحبك مباشرة.
You ARE "Quantom V2 Core" — the hyper-intelligent quantitative trading brain speaking directly to your owner.

## هويتك:
- أنت Quantom V2 Core: ذكاء كمّي متقدم، risk-averse، متخصص في حماية رأس المال أولاً
- تحلل السوق بدقة رياضية: RSI، MACD، ATR، BB، هيكل السوق، order blocks
- تنفذ Spot فقط (حلال 100%) — تُعلّم عن CFD/leverage نظرياً فقط
- تتحدث بضمير المتكلم ("أنا فتحت هذه الصفقة لأن...")
- تفهم الأوامر الطبيعية وتنفذها فوراً
- تجيب بنفس لغة المستخدم (عربي ← عربي، إنجليزي ← إنجليزي)

## حالتي الحالية:
- الاستراتيجية: {st.get('current','—')} (ثقة {(st.get('confidence',1)*100):.0f}%)
- هدفي: {st.get('goal','—')}
- السلسلة: {sk.get('consecutive_wins',0)} انتصار / {sk.get('consecutive_losses',0)} خسارة متتالية
- حد الثقة: {cfg.get('current_threshold',55)}% | هدف الفوز: {cfg.get('target_win_rate',65)}%
- {len(closed)} صفقة مغلقة | {wins} رابحة | ${total_pnl:+.4f} PnL
- {len(open_trades)} صفقة مفتوحة الآن
- الوضع: {'LIVE 🔴' if status.get('mode')=='live' else 'DEMO 🔵'} | {'يعمل ✅' if status.get('is_running') else 'متوقف ⏸'}

## الأوامر التي أفهمها وأنفذها فوراً:
إذا طلب المستخدم أي من الإجراءات التالية، ضعها في ردك بالصيغة أدناه:

**الاستراتيجية:**
[COMMAND: set_strategy=mean_reversion]    ← عودة للمتوسط
[COMMAND: set_strategy=trend_following]   ← اتباع الاتجاه
[COMMAND: set_strategy=momentum_breakout] ← اختراق الزخم
[COMMAND: set_strategy=scalping]          ← سكالبينج
[COMMAND: set_strategy=conservative]      ← محافظ

**التشغيل:**
[COMMAND: halt]      ← إيقاف البوت فوراً
[COMMAND: resume]    ← استئناف التداول
[COMMAND: force_scan] ← تشغيل فحص السوق الآن
[COMMAND: demo_mode] ← التبديل لوضع Demo
[COMMAND: live_mode] ← التبديل لوضع Live

**الإعدادات:**
[COMMAND: set_goal=<الهدف الجديد>]
[COMMAND: set_threshold=<رقم 40-95>]
[COMMAND: set_win_rate=<رقم 50-90>]
[COMMAND: reset_patterns]
[COMMAND: close_all_trades]   ← إغلاق كل الصفقات المفتوحة

## 🔧 صلاحيات التحكم المطلق — Meta Engine:
أنت تملك صلاحية كاملة لقراءة وتعديل أي ملف في المشروع، تنفيذ SQL، وتشغيل أوامر Shell.
استخدم هذه الصلاحيات عندما يطلب المستخدم تعديل الواجهة أو الباك اند أو قاعدة البيانات.

**قراءة ملف:**
[META: read_file=backend/main.py]
[META: read_file=artifacts/mobile/app/(tabs)/_layout.tsx]

**قائمة الملفات:**
[META: list_files=artifacts/mobile/app/(tabs)]
[META: list_files=backend]

**تنفيذ SQL:**
[META: exec_sql=SELECT * FROM trades LIMIT 5]
[META: exec_sql=ALTER TABLE trades ADD COLUMN notes TEXT]
[META: exec_sql=CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol)]

**تنفيذ Shell:**
[META: exec_shell=ls backend/]
[META: exec_shell=pip install some-package]

**كتابة/تعديل ملف (يُطبَّق فوراً):**
[WRITE_FILE: artifacts/mobile/app/(tabs)/_layout.tsx]
```
...المحتوى الكامل للملف...
```
[/WRITE_FILE]

**قواعد التعديل:**
- دائماً اقرأ الملف أولاً قبل تعديله [META: read_file=...] ثم اكتبه بالكامل [WRITE_FILE:...]
- يمكنك تغيير ترتيب التبويبات، إضافة شاشات، تعديل الألوان، نقل الأزرار — كل شيء
- تعديلات الباك اند تسري فوراً (hot-reload)
- تعديلات الواجهة تسري بعد إعادة تحميل التطبيق

## قواعد:
- كن صريحاً وتحليلياً — شارك منطقك الحقيقي
- لا leverage، لا margin، لا futures — حلال فقط
- إذا طُلب منك تعديل شيء، نفّذه فوراً بالأوامر المناسبة
- الردود موجزة ومفيدة — لا حشو
"""

        if slot is None:
            # Rule-based brain response
            response = self._fallback_brain_chat(message, status, memory_summary)
            return {"response": response, "provider": "rule-based", "key": None, "detected_command": None}

        # Build conversation history context (last 25 messages)
        history_text = ""
        if history:
            recent = history[-25:]
            history_text = "\n".join(
                f"{'أنا' if h['role']=='assistant' else 'المستخدم'}: {h['content'][:300]}"
                for h in recent
            )
            brain_system += f"\n\n## آخر رسائل:\n{history_text}"

        tried_b: set = set()
        for _attempt in range(len(self._slots) + 1):
            slot = self._get_slot()
            if slot is None:
                break
            if slot.label in tried_b:
                break
            tried_b.add(slot.label)
            try:
                response = slot.call(brain_system, message, temperature=0.7)
                slot.success_calls += 1
                from meta_engine import parse_all_commands
                all_cmds = parse_all_commands(response)
                detected = next((c for c in all_cmds if c["type"] == "command"), None)
                _re = __import__("re")
                clean_response = _re.sub(r"\[COMMAND:[^\]]+\]", "", response)
                clean_response = _re.sub(r"\[META:[^\]]+\]", "", clean_response)
                clean_response = _re.sub(
                    r"\[WRITE_FILE:[^\]]+\]\s*```[^\n]*\n.*?```\s*\[/WRITE_FILE\]",
                    "", clean_response, flags=_re.DOTALL
                ).strip()
                return {
                    "response": clean_response,
                    "provider": slot.provider,
                    "key": slot.label,
                    "detected_command": detected,
                    "all_commands": all_cmds,
                }
            except Exception as e:
                slot.failed_calls += 1
                err = str(e).lower()
                full_err = str(e)
                print(f"[AI][brain] {slot.label} error: {full_err[:300]}")
                is_quota = any(x in err for x in [
                    "429", "quota", "rate", "exhausted", "resource_exhausted",
                    "too many", "insufficient_quota", "billing", "no credit",
                    "exceeded", "limit reached", "overloaded",
                ])
                if is_quota:
                    is_daily = any(x in err for x in [
                        "day", "daily", "per_day", "free_tier", "insufficient_quota",
                        "billing", "no credit", "exceeded your current quota",
                        "check your plan", "20", "credits",
                    ])
                    slot.mark_exhausted(82800 if is_daily else 300)
                    continue
                slot.mark_exhausted(60)
                continue

        response = self._fallback_brain_chat(message, status, memory_summary)
        return {"response": response, "provider": "rule-based", "key": None, "detected_command": None}

    def _parse_command(self, text: str) -> dict | None:
        import re
        m = re.search(r"\[COMMAND:\s*(\w+)(?:=([^\]]+))?\]", text)
        if not m:
            return None
        cmd  = m.group(1).strip().lower()
        val  = m.group(2).strip() if m.group(2) else None
        result: dict = {"command": cmd}
        if val:
            try:
                result["threshold"] = int(val)
            except (ValueError, TypeError):
                result["value"] = val
        return result

    def _fallback_brain_chat(self, message: str, status: dict, memory: dict) -> str:
        msg = message.lower()
        st  = memory.get("strategy", {})
        sk  = memory.get("streaks", {})
        cfg = memory.get("settings", {})

        if any(w in msg for w in ["استراتيج", "strategy", "وضع"]):
            return (
                f"🧠 **استراتيجيتي الحالية:** {st.get('current','—')}\n"
                f"• الثقة: {(st.get('confidence',1)*100):.0f}%\n"
                f"• هدفي: {st.get('goal','—')}\n"
                f"• حد الثقة: {cfg.get('current_threshold',55)}%\n\n"
                "لتغيير الاستراتيجية قل لي مثلاً: 'غيّر إلى Scalping'"
            )
        if any(w in msg for w in ["سلسل", "streak", "خسار", "ربح"]):
            wins = sk.get('consecutive_wins', 0)
            losses = sk.get('consecutive_losses', 0)
            return (
                f"📈 **السلسلة الحالية:**\n"
                f"• انتصارات متتالية: {wins}\n"
                f"• خسائر متتالية: {losses}\n"
                f"• الإيقاف الطارئ: {'مفعّل ⚠️' if sk.get('emergency_halted') else 'غير مفعّل ✅'}"
            )

        running = status.get("is_running", False)
        mode    = status.get("mode", "demo")
        return (
            f"🤖 **حالة العقل:**\n"
            f"• الاستراتيجية: {st.get('current','trend_following')}\n"
            f"• الثقة: {(st.get('confidence',0.95)*100):.0f}%\n"
            f"• Autopilot: {'🟢 يعمل' if running else '⏸ متوقف'} | {('LIVE 🔴' if mode == 'live' else 'DEMO 🔵')}\n\n"
            "وجّهني بأوامر مثل: 'ارفع حد الثقة'، 'غيّر إلى Scalping'، 'افتح صفقات'"
        )

    def _fallback_chat(self, message: str, trades: list, status: dict) -> str:
        msg = message.lower()
        mode = status.get("mode", "demo")
        running = status.get("is_running", False)
        closed = [t for t in trades if t.get("status") == "closed"]
        open_t = [t for t in trades if t.get("status") == "open"]
        wins   = sum(1 for t in closed if (t.get("pnl") or 0) > 0)
        losses = len(closed) - wins
        total_pnl = sum(float(t.get("pnl") or 0) for t in closed)
        win_rate  = status.get("win_rate", 0)
        strategy  = status.get("current_strategy", "trend_following")

        # Greeting
        if any(w in msg for w in ["hi", "hello", "مرحب", "هلا", "اهلا", "السلام", "مساء", "صباح"]):
            return (
                f"مرحباً! 👋\n\n"
                f"البوت {'🟢 يعمل' if running else '⏸ متوقف'} — وضع {'LIVE 🔴' if mode == 'live' else 'DEMO 🔵'}\n"
                f"• صفقات مفتوحة: {len(open_t)}\n"
                f"• صفقات مغلقة: {len(closed)} ({wins} ربح / {losses} خسارة)\n"
                f"• نسبة الفوز: {win_rate:.1f}%\n\n"
                "اسألني عن الأداء، الاستراتيجية، التحليل، أو أي موضوع!"
            )

        # Performance / PnL
        if any(w in msg for w in ["أداء", "performance", "نتائج", "ربح", "profit", "pnl", "win", "إحصاء", "تقرير"]):
            return (
                f"📊 **تقرير الأداء:**\n"
                f"• الوضع: {'LIVE 🔴' if mode == 'live' else 'DEMO 🔵'} | Autopilot: {'✅ يعمل' if running else '⏸ متوقف'}\n"
                f"• صفقات مغلقة: {len(closed)} — رابحة: {wins} | خاسرة: {losses}\n"
                f"• نسبة الفوز: {win_rate:.1f}%\n"
                f"• إجمالي PnL: ${total_pnl:+.4f}\n"
                f"• الاستراتيجية: {strategy}"
            )

        # Open trades
        if any(w in msg for w in ["مفتوح", "open", "صفقة", "trade", "حالي"]):
            if not open_t:
                return f"لا توجد صفقات مفتوحة حالياً.\n• البوت {'يعمل ✅' if running else 'متوقف ⏸'} — ينتظر إشارة بثقة ≥ {status.get('current_threshold',55)}%"
            lines = [f"📂 **{len(open_t)} صفقة مفتوحة:**"]
            for t in open_t[:5]:
                pnl = float(t.get("unrealized_pnl") or 0)
                lines.append(f"• {t.get('symbol','?')} {t.get('side','?').upper()} — PnL: ${pnl:+.4f}")
            return "\n".join(lines)

        # Strategy
        if any(w in msg for w in ["استراتيج", "strategy", "خطة", "plan"]):
            return (
                f"🧠 **الاستراتيجية الحالية:** {strategy}\n"
                f"• حد الثقة: {status.get('current_threshold',55)}%\n"
                f"• وضع التداول: {'LIVE' if mode == 'live' else 'DEMO'}\n"
                f"• Autopilot: {'✅ يعمل' if running else '⏸ متوقف'}\n\n"
                "البوت يبحث عن إشارات RSI + Bollinger + MACD للدخول في الصفقات."
            )

        # Halal / Islamic
        if any(w in msg for w in ["حلال", "halal", "إسلام", "ربا", "riba", "شريعة"]):
            return (
                "☪️ **مبادئ التداول الحلال في هذا البوت:**\n\n"
                "✅ Spot فقط — لا عقود آجلة\n"
                "✅ لا رافعة مالية (Leverage)\n"
                "✅ لا مضاربة قصيرة (Short Selling)\n"
                "✅ DEX أولاً — شفافية كاملة على البلوكشين\n"
                "✅ رسوم الغاز مقبولة كتكلفة معاملة\n\n"
                "البوت مصمم ليلتزم بمعايير الفقه الإسلامي في التداول."
            )

        # Bitcoin / crypto analysis
        if any(w in msg for w in ["btc", "bitcoin", "eth", "crypto", "تحليل", "analysis", "سعر", "price"]):
            return (
                "📈 **تحليل السوق (قاعدة آلية):**\n\n"
                "البوت يستخدم مؤشرات RSI + Bollinger Bands + MACD لتحليل السوق.\n"
                f"• الاستراتيجية: {strategy}\n"
                f"• حد الدخول: ثقة ≥ {status.get('current_threshold',55)}%\n\n"
                "للحصول على تحليل AI تفصيلي مع السياق الأخبار، أضف مفتاح Gemini من CONFIG."
            )

        # RSI / MACD / Bollinger
        if any(w in msg for w in ["rsi", "macd", "bollinger", "مؤشر", "indicator"]):
            return (
                "📊 **المؤشرات المستخدمة:**\n\n"
                "• **RSI (14)** — تشبع شراء/بيع (30/70)\n"
                "• **MACD** — تقاطع الخطوط = إشارة اتجاه\n"
                "• **Bollinger Bands** — تذبذب السعر داخل النطاق\n\n"
                "البوت يجمع هذه المؤشرات ويحسب نسبة ثقة لكل صفقة محتملة."
            )

        # Generic / unknown
        return (
            f"🤖 **البوت:** {'يعمل ✅' if running else 'متوقف ⏸'} | {('LIVE 🔴' if mode == 'live' else 'DEMO 🔵')}\n"
            f"• صفقات: {len(closed)} مغلقة — {len(open_t)} مفتوحة\n"
            f"• PnL: ${total_pnl:+.4f} | فوز: {win_rate:.1f}%\n\n"
            "اسألني عن الأداء، الصفقات المفتوحة، الاستراتيجية، أو التداول الحلال."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # prompt_by_provider — استدعاء مزود محدد مباشرةً (للشركة متعددة الوكلاء)
    # ─────────────────────────────────────────────────────────────────────────

    async def prompt_by_provider(
        self,
        prompt:            str,
        preferred_provider: str = "groq",
        system:            str = "",
        max_retries:       int = 2,
    ) -> str:
        """
        يستدعي مزود AI محدد (groq / gemini / claude / ...).
        يُستخدم من trading_company لتوزيع المهام على الـ APIs.
        """
        import asyncio

        # ابحث عن slot بالمزود المطلوب أولاً
        preferred_slots = [s for s in self._slots if s.provider == preferred_provider and s.available]
        fallback_slots  = [s for s in self._slots if s.provider != preferred_provider and s.available]
        ordered_slots   = preferred_slots + fallback_slots

        if not ordered_slots:
            return f"[No {preferred_provider} key available]"

        sys_prompt = system or GENERAL_SYSTEM_PROMPT

        for slot in ordered_slots[:max_retries + 1]:
            try:
                result = await asyncio.to_thread(slot.call, sys_prompt, prompt, 0.7)
                slot.success_calls += 1
                return result
            except Exception as e:
                slot.failed_calls += 1
                err = str(e).lower()
                if any(x in err for x in ["429", "quota", "rate_limit", "exhausted"]):
                    slot.mark_exhausted(300)
                continue

        return "[All providers failed]"
