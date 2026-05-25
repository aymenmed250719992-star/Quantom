"""
TradingCompany — شركة تداول ذكية متعددة الوكلاء

هيكل الشركة:
┌─────────────────────────────────────────────────────────────┐
│                    QUANTOM TRADING COMPANY                   │
├──────────────┬──────────────┬──────────────┬───────────────┤
│  قسم الأخبار │ قسم الجماهير │ قسم الذاكرة  │قسم القرارات  │
│   (Gemini)   │  (MiroFish)  │  (MaxHermes) │    (Groq)    │
├──────────────┴──────────────┴──────────────┴───────────────┤
│                     مكتب التنفيذ (Execution Desk)           │
└─────────────────────────────────────────────────────────────┘

كل API له دور محدد، يعملون معاً كشركة تداول حقيقية.
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Any, Optional


class Department:
    """قسم في الشركة."""
    def __init__(self, name: str, role: str, icon: str, ai_provider: str):
        self.name         = name
        self.role         = role
        self.icon         = icon
        self.ai_provider  = ai_provider
        self.status       = "idle"
        self.last_output  = None
        self.last_run_at  = 0.0
        self.total_runs   = 0
        self.errors       = 0

    def to_dict(self) -> dict:
        return {
            "name":         self.name,
            "role":         self.role,
            "icon":         self.icon,
            "ai_provider":  self.ai_provider,
            "status":       self.status,
            "last_run_at":  self.last_run_at,
            "total_runs":   self.total_runs,
            "errors":       self.errors,
            "last_output":  str(self.last_output)[:200] if self.last_output else None,
        }


class TradingCompany:
    """
    الشركة الكاملة — تُنسّق بين كل الوكلاء وتُصدر القرار النهائي.
    """

    _instance: Optional["TradingCompany"] = None

    def __init__(self) -> None:
        self.departments = {
            "intelligence": Department(
                name         = "قسم الاستخبارات والأخبار",
                role         = "رصد الأخبار والمؤشرات بشكل دوري",
                icon         = "📰",
                ai_provider  = "gemini",
            ),
            "crowd": Department(
                name         = "قسم تحليل الجماهير (MiroFish)",
                role         = "محاكاة آلاف المتداولين وسيكولوجية السوق",
                icon         = "🐟",
                ai_provider  = "crowd_sim",
            ),
            "memory": Department(
                name         = "قسم الذاكرة والتعلم (MaxHermes)",
                role         = "ذاكرة دائمة، تعلم من الصفقات، تحليل Excel",
                icon         = "🧠",
                ai_provider  = "max_hermes",
            ),
            "decision": Department(
                name         = "مكتب القرارات السريعة",
                role         = "دمج كل المعلومات وإصدار القرار النهائي",
                icon         = "⚡",
                ai_provider  = "groq",
            ),
            "risk": Department(
                name         = "قسم إدارة المخاطر",
                role         = "التحقق من الامتثال الشرعي والمخاطر",
                icon         = "🛡️",
                ai_provider  = "rule_engine",
            ),
            "execution": Department(
                name         = "مكتب التنفيذ",
                role         = "تنفيذ صفقات Spot الحلالية فوراً",
                icon         = "🎯",
                ai_provider  = "exchange_api",
            ),
        }
        self.company_decisions: list[dict] = []
        self.news_cache: Optional[dict]    = None
        self.news_cache_time: float        = 0.0
        self._db: Any                      = None
        self._broadcast_fn: Any            = None

    @classmethod
    def get_instance(cls) -> "TradingCompany":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def set_db(self, db: Any) -> None:
        self._db = db

    def set_broadcast_fn(self, fn: Any) -> None:
        self._broadcast_fn = fn

    async def _broadcast(self, msg: str) -> None:
        if self._broadcast_fn:
            try:
                await self._broadcast_fn(msg)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # الدائرة 1 — قسم الأخبار (Gemini)
    # ─────────────────────────────────────────────────────────────────────────

    async def fetch_intelligence(self, symbol: str) -> dict:
        """Gemini يرصد الأخبار والمؤشرات."""
        dept = self.departments["intelligence"]
        dept.status = "working"
        dept.total_runs += 1
        try:
            result = await self._gemini_news_prompt(symbol)

            dept.last_output = result
            dept.last_run_at = time.time()
            dept.status = "done"
            self.news_cache = result
            self.news_cache_time = time.time()
            return result

        except Exception as e:
            dept.errors += 1
            dept.status = "error"
            return {"news_summary": f"خطأ: {e}", "fear_greed": 50, "news_score": 0.0}

    # ─────────────────────────────────────────────────────────────────────────
    # الدائرة 1b — Gemini يسأل عن الأخبار (بدون GeminiAgent الثقيل)
    # ─────────────────────────────────────────────────────────────────────────

    async def _gemini_news_prompt(self, symbol: str) -> dict:
        """Gemini يُراقب الأخبار — يستخدم AIAgent مع preferred=gemini."""
        try:
            from ai_agent import AIAgent
            agent = AIAgent.get_instance()
            prompt = (
                f"أنت محلل أخبار في شركة تداول. قيّم {symbol} الآن:\n"
                f"1. أهم خبر يؤثر عليه\n"
                f"2. مستوى الخوف والطمع (0-100)\n"
                f"3. درجة الأخبار: -1 إلى +1\n"
                f"رد بـ JSON فقط: {{\"news_summary\":\"...\",\"fear_greed\":70,\"news_score\":0.3}}"
            )
            raw = await agent.prompt_by_provider(prompt, preferred_provider="gemini")
            result = {"news_summary": raw[:300], "fear_greed": 50, "news_score": 0.0}
            try:
                import re, json as _json
                m = re.search(r'\{.*?\}', raw, re.DOTALL)
                if m:
                    result = _json.loads(m.group())
            except Exception:
                pass
            return result
        except Exception as e:
            return {"news_summary": f"خطأ Gemini: {e}", "fear_greed": 50, "news_score": 0.0}

    # ─────────────────────────────────────────────────────────────────────────
    # الدائرة 2 — قسم الجماهير (MiroFish)
    # ─────────────────────────────────────────────────────────────────────────

    async def run_crowd_analysis(
        self,
        symbol: str,
        price:  float,
        rsi:    float,
        price_change_24h: float,
        price_change_1h:  float = 0.0,
        volume_ratio:     float = 1.0,
        bb_position:      float = 0.0,
        news_score:       float = 0.0,
    ) -> dict:
        """MiroFish يُشغّل محاكاة الجماهير."""
        dept = self.departments["crowd"]
        dept.status = "working"
        dept.total_runs += 1
        try:
            from crowd_sim import CrowdSimulator
            sim = CrowdSimulator.get_instance()

            result = await asyncio.to_thread(
                sim.simulate,
                symbol, price, price_change_1h, price_change_24h,
                rsi, volume_ratio, news_score, bb_position,
            )
            dept.last_output = result
            dept.last_run_at = time.time()
            dept.status = "done"
            return result

        except Exception as e:
            dept.errors += 1
            dept.status = "error"
            return {"crowd_signal": "NEUTRAL", "bullish_pct": 50, "bearish_pct": 50, "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────────
    # الدائرة 3 — قسم الذاكرة (MaxHermes)
    # ─────────────────────────────────────────────────────────────────────────

    async def get_memory_context(self, symbol: str, action: str = "") -> dict:
        """MaxHermes يجلب السياق من الذاكرة."""
        dept = self.departments["memory"]
        dept.status = "working"
        dept.total_runs += 1
        try:
            from max_hermes import MaxHermes
            hermes = MaxHermes.get_instance(self._db)

            rich_ctx = await hermes.get_rich_context(symbol=symbol, action=action)
            lessons  = await hermes.get_relevant_lessons(symbol, action)

            result = {
                "rich_context": rich_ctx[:500] if rich_ctx else "",
                "lessons":      lessons[:3],
                "has_context":  bool(rich_ctx),
            }
            dept.last_output = result
            dept.last_run_at = time.time()
            dept.status = "done"
            return result

        except Exception as e:
            dept.errors += 1
            dept.status = "error"
            return {"rich_context": "", "lessons": [], "has_context": False, "error": str(e)}

    # ─────────────────────────────────────────────────────────────────────────
    # الدائرة 4 — مكتب القرارات (Groq)
    # ─────────────────────────────────────────────────────────────────────────

    async def make_final_decision(
        self,
        symbol:       str,
        price:        float,
        intelligence: dict,
        crowd:        dict,
        memory:       dict,
        technicals:   dict,
    ) -> dict:
        """
        Groq يستقبل مدخلات كل الأقسام ويُصدر القرار النهائي السريع.
        """
        dept = self.departments["decision"]
        dept.status = "working"
        dept.total_runs += 1
        try:
            from ai_agent import AIAgent
            agent = AIAgent.get_instance()

            prompt = f"""أنت كبير المحللين في Quantom Trading. لديك مدخلات من كل الأقسام:

📰 قسم الأخبار (Gemini):
- ملخص: {intelligence.get('news_summary', 'لا يوجد')[:200]}
- درجة الأخبار: {intelligence.get('news_score', 0):.2f}
- الخوف والطمع: {intelligence.get('fear_greed', 50)}/100

🐟 قسم الجماهير (MiroFish - {crowd.get('n_traders', 1000)} متداول وهمي):
- إشارة الجموع: {crowd.get('crowd_signal', 'NEUTRAL')}
- نسبة صاعدة: {crowd.get('bullish_pct', 50)}%
- نسبة هابطة: {crowd.get('bearish_pct', 50)}%
- سيكولوجية السوق: {crowd.get('market_psychology', 'محايد')}
- الحيتان: {crowd.get('whale_action', 'hold').upper()}
- تباين الحيتان: {"نعم ⚠️" if crowd.get('whale_divergence') else "لا"}

🧠 قسم الذاكرة (MaxHermes):
{memory.get('rich_context', 'لا سياق')[:300]}

📊 المؤشرات التقنية:
- RSI: {technicals.get('rsi', 50):.1f}
- التغير 24h: {technicals.get('price_change_24h', 0)*100:.2f}%

السعر الحالي: ${price:.4f}
الرمز: {symbol}

القرار المطلوب منك (Spot حلال فقط — لا رافعة):
رد بـ JSON: {{"action":"BUY"/"SELL"/"HOLD","confidence":75,"reason":"...","sl_pct":2.0,"tp_pct":4.0}}"""

            # نستخدم Groq بالأولوية
            result_raw = await agent.prompt_by_provider(
                prompt=prompt,
                preferred_provider="groq",
            )

            # تحليل JSON
            decision = {
                "action": "HOLD", "confidence": 50,
                "reason": result_raw[:200], "sl_pct": 2.0, "tp_pct": 4.0,
            }
            try:
                import re
                m = re.search(r'\{.*?\}', result_raw, re.DOTALL)
                if m:
                    parsed = json.loads(m.group())
                    decision.update(parsed)
            except Exception:
                pass

            decision["symbol"]    = symbol
            decision["price"]     = price
            decision["timestamp"] = datetime.utcnow().isoformat()
            decision["sources"]   = {
                "intelligence": intelligence.get("news_score", 0),
                "crowd":        crowd.get("crowd_signal", "NEUTRAL"),
                "memory":       memory.get("has_context", False),
            }

            dept.last_output = decision
            dept.last_run_at = time.time()
            dept.status = "done"

            # حفظ في سجل القرارات
            self.company_decisions.append(decision)
            if len(self.company_decisions) > 50:
                self.company_decisions = self.company_decisions[-50:]

            # بث للتطبيق
            await self._broadcast(json.dumps({
                "type":    "company_decision",
                "message": f"🏢 [{decision['action']}] {symbol} @ ${price:.4f} | ثقة: {decision.get('confidence', 50)}% | Groq قرر",
                "data":    decision,
            }))

            return decision

        except Exception as e:
            dept.errors += 1
            dept.status = "error"
            return {
                "action": "HOLD", "confidence": 0,
                "reason": f"خطأ في مكتب القرارات: {e}",
                "symbol": symbol, "price": price,
            }

    # ─────────────────────────────────────────────────────────────────────────
    # التحليل الشامل — يُشغّل كل الأقسام معاً
    # ─────────────────────────────────────────────────────────────────────────

    async def full_analysis(
        self,
        symbol:  str,
        price:   float,
        rsi:     float = 50.0,
        price_change_24h: float = 0.0,
        price_change_1h:  float = 0.0,
        volume_ratio:     float = 1.0,
        bb_position:      float = 0.0,
    ) -> dict:
        """
        يُشغّل كل أقسام الشركة بالتوازي ثم يُمرر النتائج لـ Groq.
        """
        await self._broadcast(json.dumps({
            "type":    "log",
            "message": f"🏢 الشركة تُحلل {symbol} — تشغيل كل الأقسام...",
        }))

        # الأقسام 1-3 بالتوازي
        # أحضر من الـ cache إذا الأخبار حديثة (< 5 دقائق)
        if self.news_cache and time.time() - self.news_cache_time < 300:
            intel_task = asyncio.create_task(asyncio.sleep(0))
            intelligence = self.news_cache
        else:
            intel_task = None

        crowd_coro  = self.run_crowd_analysis(
            symbol, price, rsi, price_change_24h,
            price_change_1h, volume_ratio, bb_position,
            self.news_cache.get("news_score", 0.0) if self.news_cache else 0.0,
        )
        memory_coro = self.get_memory_context(symbol)

        if intel_task is None:
            intelligence, crowd, memory = await asyncio.gather(
                self.fetch_intelligence(symbol),
                crowd_coro,
                memory_coro,
                return_exceptions=True,
            )
        else:
            crowd, memory = await asyncio.gather(
                crowd_coro,
                memory_coro,
                return_exceptions=True,
            )

        if isinstance(intelligence, Exception):
            intelligence = {"news_summary": "error", "fear_greed": 50, "news_score": 0.0}
        if isinstance(crowd, Exception):
            crowd = {"crowd_signal": "NEUTRAL", "bullish_pct": 50, "bearish_pct": 50}
        if isinstance(memory, Exception):
            memory = {"rich_context": "", "lessons": [], "has_context": False}

        technicals = {
            "rsi":              rsi,
            "price_change_24h": price_change_24h,
            "volume_ratio":     volume_ratio,
        }

        # القرار النهائي (Groq)
        decision = await self.make_final_decision(
            symbol, price, intelligence, crowd, memory, technicals
        )

        return {
            "symbol":       symbol,
            "price":        price,
            "intelligence": intelligence,
            "crowd":        crowd,
            "memory":       memory,
            "decision":     decision,
            "timestamp":    datetime.utcnow().isoformat(),
        }

    # ─────────────────────────────────────────────────────────────────────────
    # حالة الشركة
    # ─────────────────────────────────────────────────────────────────────────

    def get_company_status(self) -> dict:
        return {
            "company_name":       "Quantom Trading Company",
            "departments":        {k: v.to_dict() for k, v in self.departments.items()},
            "total_decisions":    len(self.company_decisions),
            "last_decision":      self.company_decisions[-1] if self.company_decisions else None,
            "recent_decisions":   self.company_decisions[-5:],
            "news_cache_age":     round(time.time() - self.news_cache_time, 0) if self.news_cache_time else None,
        }

    def get_recent_decisions(self, limit: int = 10) -> list[dict]:
        return self.company_decisions[-limit:]
