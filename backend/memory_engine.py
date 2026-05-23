"""
MemoryEngine — نظام الذاكرة الشاملة لـ Quantom V2 Core

يتعلم من:
• كل صفقة مفتوحة أو مغلقة (ربح/خسارة)
• كل محادثة مع المستخدم (استخراج حقائق ومعرفة)
• الأنماط والاستراتيجيات عبر الزمن
• ملاحظات السوق التلقائية

يُولّد:
• سياق غني لكل استدعاء AI
• ملخص الذاكرة للتطبيق
• بحث ذكي في الذاكرة
"""

import json
import re
import time
import uuid
from datetime import datetime
from typing import Any, Optional


# ─── Category labels ─────────────────────────────────────────────────────────
CATEGORIES = {
    "trade":       "📊 صفقة",
    "pattern":     "🔁 نمط",
    "strategy":    "🧠 استراتيجية",
    "risk":        "⚠️ مخاطرة",
    "market":      "📈 سوق",
    "user":        "👤 تعليمات المستخدم",
    "general":     "💡 معرفة عامة",
    "ai":          "🤖 ملاحظة AI",
}


class MemoryEngine:
    """
    المحرك المركزي للذاكرة — يُعالج ويُخزن ويسترجع كل شيء.
    """

    def __init__(self, db: Any) -> None:
        self.db = db

    # ─────────────────────────────────────────────────────────────────────────
    # حفظ الدروس (trade lessons)
    # ─────────────────────────────────────────────────────────────────────────

    async def record_trade_open(self, trade: dict) -> None:
        """تسجيل ملاحظة عند فتح صفقة جديدة."""
        symbol = trade.get("symbol", "?")
        entry  = trade.get("entry_price", 0)
        side   = trade.get("side", "buy").upper()
        conf   = trade.get("confidence", 0)
        lesson = (
            f"فتحت صفقة {side} على {symbol} عند ${entry:.4f} — "
            f"ثقة: {conf}% — السبب: {trade.get('reason', 'تحليل تقني')}"
        )
        await self.db.save_lesson({
            "lesson":           lesson,
            "symbol":           symbol,
            "market_condition": trade.get("market_condition", "unknown"),
            "pattern":          trade.get("pattern", ""),
            "outcome":          "open",
            "importance":       4.0,
            "category":         "trade",
            "tags":             f"{symbol},{side.lower()},open",
            "confidence":       conf / 100.0 if conf > 1 else conf,
            "source":           "auto_trade",
        })

    async def record_trade_close(self, trade: dict) -> None:
        """استخراج درس عميق من كل صفقة مغلقة."""
        symbol  = trade.get("symbol", "?")
        pnl     = float(trade.get("pnl") or 0)
        side    = trade.get("side", "buy").upper()
        pattern = trade.get("pattern", "")
        win     = pnl > 0
        outcome = "win" if win else "loss"

        # أهمية الدرس بناءً على حجم الربح/الخسارة
        importance = min(10.0, 5.0 + abs(pnl) * 0.5)

        # صياغة الدرس
        direction = "ربحت" if win else "خسرت"
        lesson = (
            f"{direction} على {symbol} {side}: ${pnl:+.4f} — "
            f"نمط: {pattern or 'غير محدد'} — "
            f"ثقة الدخول: {trade.get('confidence', 0)}%"
        )

        # استخراج قاعدة للمستقبل
        rule = self._extract_rule_from_trade(trade, win, pnl)
        if rule:
            lesson += f" | قاعدة: {rule}"

        await self.db.save_lesson({
            "lesson":           lesson,
            "symbol":           symbol,
            "market_condition": trade.get("market_condition", "unknown"),
            "pattern":          pattern,
            "outcome":          outcome,
            "importance":       importance,
            "category":         "trade",
            "tags":             f"{symbol},{outcome},{side.lower()},{pattern}",
            "confidence":       0.9 if win else 0.6,
            "source":           "auto_trade",
        })

        # حفظ قاعدة في bot_knowledge إذا كانت مهمة
        if rule and abs(pnl) > 0.5:
            await self.db.save_knowledge({
                "title":      f"قاعدة مكتسبة: {symbol}",
                "content":    rule,
                "category":   "strategy",
                "importance": importance,
                "tags":       f"{symbol},{outcome},{pattern}",
                "source":     "trade_analysis",
            })

    def _extract_rule_from_trade(self, trade: dict, win: bool, pnl: float) -> str:
        """استخراج قاعدة قابلة للتطبيق من نتيجة الصفقة."""
        symbol  = trade.get("symbol", "")
        pattern = trade.get("pattern", "")
        conf    = trade.get("confidence", 0)
        mc      = trade.get("market_condition", "")

        if win and conf >= 70:
            return f"نمط {pattern} مع ثقة ≥70% على {symbol} يُعطي نتائج إيجابية"
        elif not win and conf < 60:
            return f"تجنّب الدخول بثقة <60% — خاصة في {symbol} عند ظروف {mc}"
        elif win and pnl > 1.0:
            return f"الصبر على نمط {pattern} في {symbol} يُعطي عائداً جيداً"
        elif not win and pnl < -0.5:
            return f"مراجعة Stop-Loss على {symbol} — الخسارة تجاوزت المتوقع"
        return ""

    # ─────────────────────────────────────────────────────────────────────────
    # استخراج معرفة من المحادثات
    # ─────────────────────────────────────────────────────────────────────────

    async def extract_from_conversation(self, user_msg: str, bot_reply: str) -> None:
        """
        يستخرج حقائق وتعليمات وتفضيلات من كل رسالة.
        """
        # البحث عن تعليمات صريحة
        instruction_patterns = [
            r"(لا تفتح|لا تتداول|تجنّب|ابتعد عن)\s+(.+)",
            r"(دائماً|دائما|اعتمد على|استخدم)\s+(.+)",
            r"(أفضّل|أفضل|أريد|أحب)\s+(.+)",
            r"(ركز على|اهتم بـ?|خصص)\s+(.+)",
            r"(عندما|إذا|متى)\s+(.+فافعل|.+قم بـ?|.+استخدم)",
        ]

        found_instruction = None
        for pat in instruction_patterns:
            m = re.search(pat, user_msg, re.IGNORECASE)
            if m:
                found_instruction = user_msg.strip()
                break

        if found_instruction:
            await self.db.save_lesson({
                "lesson":     f"تعليمة المستخدم: {found_instruction}",
                "symbol":     "",
                "pattern":    "user_instruction",
                "outcome":    "instruction",
                "importance": 8.0,
                "category":   "user",
                "tags":       "user_instruction,preference",
                "confidence": 1.0,
                "source":     "chat",
            })
            await self.db.save_knowledge({
                "title":     "تعليمة مستخدم",
                "content":   found_instruction,
                "category":  "user",
                "importance": 8.5,
                "tags":      "user,instruction,preference",
                "source":    "chat",
            })

    # ─────────────────────────────────────────────────────────────────────────
    # بناء السياق الغني لكل استدعاء AI
    # ─────────────────────────────────────────────────────────────────────────

    async def get_rich_context(self, query: str = "", limit_lessons: int = 15, limit_knowledge: int = 10) -> str:
        """
        يبني سياقاً شاملاً من الذاكرة لحقن كل استدعاء AI به.
        البوت يتذكر كل شيء — لا شيء يُنسى.
        """
        parts = []

        # ── الدروس المكتسبة (مرتبة بالأهمية) ──────────────────────────────
        try:
            lessons = await self.db.get_recent_lessons(limit=limit_lessons)
            if lessons:
                lines = []
                for l in lessons[:limit_lessons]:
                    imp  = l.get("importance", 5.0)
                    cat  = CATEGORIES.get(l.get("category", "trade"), "")
                    text = l.get("lesson", "")[:200]
                    lines.append(f"  [{imp:.0f}/10] {cat} {text}")
                parts.append("## ذاكرة الدروس المكتسبة:\n" + "\n".join(lines))
        except Exception:
            pass

        # ── المعرفة المستمرة (bot_knowledge) ──────────────────────────────
        try:
            knowledge = await self.db.get_knowledge(limit=limit_knowledge)
            if knowledge:
                lines = []
                for k in knowledge[:limit_knowledge]:
                    title   = k.get("title", "")
                    content = k.get("content", "")[:180]
                    lines.append(f"  • {title}: {content}")
                parts.append("## المعرفة المستمرة:\n" + "\n".join(lines))
        except Exception:
            pass

        # ── تعليمات المستخدم الصريحة (الأعلى أهمية) ──────────────────────
        try:
            user_rules = await self.db.search_memory("user_instruction", limit=5)
            if user_rules:
                lines = [f"  ⚠️ {r.get('lesson','')}" for r in user_rules[:5]]
                parts.append("## تعليمات المستخدم (يجب الالتزام بها):\n" + "\n".join(lines))
        except Exception:
            pass

        # ── البحث السياقي (إذا كان هناك استعلام محدد) ───────────────────
        if query and len(query) > 3:
            try:
                relevant = await self.db.search_memory(query, limit=5)
                if relevant:
                    lines = [f"  → {r.get('lesson','')[:150]}" for r in relevant[:5]]
                    parts.append(f"## ذاكرة ذات صلة بـ '{query[:50]}':\n" + "\n".join(lines))
            except Exception:
                pass

        return "\n\n".join(parts) if parts else ""

    # ─────────────────────────────────────────────────────────────────────────
    # ملخص الذاكرة للتطبيق
    # ─────────────────────────────────────────────────────────────────────────

    async def get_memory_summary(self) -> dict:
        """ملخص شامل للذاكرة لعرضه في شاشة Brain."""
        try:
            lessons   = await self.db.get_recent_lessons(limit=200)
            knowledge = await self.db.get_knowledge(limit=100)

            # إحصائيات
            total_lessons   = len(lessons)
            total_knowledge = len(knowledge)
            wins   = sum(1 for l in lessons if l.get("outcome") == "win")
            losses = sum(1 for l in lessons if l.get("outcome") == "loss")
            user_rules = [l for l in lessons if l.get("category") == "user"]

            # أعلى دروس بالأهمية
            top_lessons = sorted(lessons, key=lambda x: float(x.get("importance", 0)), reverse=True)[:10]

            # تصنيف المعرفة
            by_category: dict = {}
            for k in knowledge:
                cat = k.get("category", "general")
                by_category.setdefault(cat, []).append(k)

            return {
                "stats": {
                    "total_lessons":   total_lessons,
                    "total_knowledge": total_knowledge,
                    "wins":            wins,
                    "losses":          losses,
                    "user_rules":      len(user_rules),
                },
                "top_lessons":    [dict(l) for l in top_lessons],
                "recent_lessons": [dict(l) for l in lessons[:30]],
                "knowledge":      [dict(k) for k in knowledge[:50]],
                "knowledge_by_category": {
                    cat: [dict(k) for k in items[:10]]
                    for cat, items in by_category.items()
                },
                "user_rules": [dict(l) for l in user_rules[:10]],
            }
        except Exception as e:
            return {"error": str(e), "stats": {}, "lessons": [], "knowledge": []}
