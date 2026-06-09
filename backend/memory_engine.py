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
        conf    = int(trade.get("confidence", 0))
        regime  = trade.get("market_condition", "unknown")
        win     = pnl > 0
        outcome = "win" if win else "loss"

        # أهمية الدرس بناءً على حجم الربح/الخسارة
        importance = min(10.0, 5.0 + abs(pnl) * 0.5)

        # صياغة الدرس مع تضمين النظام السوقي
        direction = "ربحت" if win else "خسرت"
        lesson = (
            f"{direction} على {symbol} {side}: ${pnl:+.4f} — "
            f"نمط: {pattern or 'غير محدد'} — "
            f"ثقة: {conf}% — سوق: {regime}"
        )

        # استخراج قاعدة للمستقبل
        rule = self._extract_rule_from_trade(trade, win, pnl)
        if rule:
            lesson += f" | قاعدة: {rule}"

        await self.db.save_lesson({
            "lesson":           lesson,
            "symbol":           symbol,
            "market_condition": regime,
            "pattern":          pattern,
            "outcome":          outcome,
            "importance":       importance,
            "category":         "trade",
            "tags":             f"{symbol},{outcome},{side.lower()},{pattern},{regime}",
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

        # تحديث إحصائيات الأنماط تلقائياً
        await self.update_pattern_knowledge(pattern, symbol, win, pnl, conf)

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

    async def update_pattern_knowledge(self, pattern: str, symbol: str, win: bool, pnl: float, conf: int) -> None:
        """
        بعد كل صفقة مغلقة: يُحدّث معدل نجاح كل نمط في bot_knowledge.
        هذا يبني ذاكرة الأنماط تدريجياً عبر الزمن.
        """
        if not pattern:
            return
        try:
            # ابحث عن معرفة موجودة لهذا النمط
            existing = await self.db.search_memory(f"أداء_نمط_{pattern}", limit=1)
            if not existing:
                existing = await self.db.get_knowledge(limit=200)
                existing = [k for k in existing if k.get("tags", "").find(f"pattern_perf_{pattern}") >= 0]

            if existing:
                rec = existing[0]
                content = rec.get("content", "")
                # استخرج الإحصائيات الموجودة
                import re as _re
                wins_m   = _re.search(r"wins=(\d+)",   content)
                losses_m = _re.search(r"losses=(\d+)", content)
                prev_wins   = int(wins_m.group(1))   if wins_m   else 0
                prev_losses = int(losses_m.group(1)) if losses_m else 0
            else:
                prev_wins, prev_losses = 0, 0

            new_wins   = prev_wins   + (1 if win else 0)
            new_losses = prev_losses + (0 if win else 1)
            total      = new_wins + new_losses
            wr         = new_wins / total * 100 if total > 0 else 0.0
            avg_pnl    = pnl  # يمكن تحسينه لاحقاً بالمتوسط المتراكم

            content = (
                f"wins={new_wins} losses={new_losses} total={total} "
                f"win_rate={wr:.1f}% avg_pnl={avg_pnl:+.4f} "
                f"last_conf={conf}%"
            )
            importance = min(9.0, 5.0 + total * 0.3 + wr * 0.02)

            await self.db.save_knowledge({
                "title":      f"أداء نمط: {pattern} على {symbol}",
                "content":    content,
                "category":   "pattern",
                "importance": importance,
                "tags":       f"pattern_perf_{pattern},{symbol},auto_stats",
                "source":     "trade_analysis",
            })
        except Exception as e:
            print(f"[Memory] update_pattern_knowledge error: {e}")

    # ─────────────────────────────────────────────────────────────────────────
    # استخراج معرفة من المحادثات
    # ─────────────────────────────────────────────────────────────────────────

    async def extract_from_conversation(self, user_msg: str, bot_reply: str) -> None:
        """
        يستخرج حقائق وتعليمات وتفضيلات من كل رسالة.
        نسخة محسّنة: تستخرج أنواعاً أكثر من المعلومات.
        """
        user_lower = user_msg.lower()

        # ── ١. تعليمات صريحة (أعلى أولوية) ─────────────────────────────────
        instruction_patterns = [
            r"(لا تفتح|لا تتداول|تجنّب|ابتعد عن)\s+(.+)",
            r"(دائماً|دائما|اعتمد على|استخدم)\s+(.+)",
            r"(أفضّل|أفضل|أريد|أحب)\s+(.+)",
            r"(ركز على|اهتم بـ?|خصص)\s+(.+)",
            r"(عندما|إذا|متى)\s+(.+فافعل|.+قم بـ?|.+استخدم)",
            r"(remember|always|never|stop|don't|do not)\s+(.+)",
            r"(تذكر|احفظ|لا تنسى)\s+(.+)",
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
                "importance": 9.0,
                "category":   "user",
                "tags":       "user_instruction,preference,high_priority",
                "confidence": 1.0,
                "source":     "chat",
            })
            await self.db.save_knowledge({
                "title":      "تعليمة مستخدم",
                "content":    found_instruction,
                "category":   "user",
                "importance": 9.0,
                "tags":       "user,instruction,preference",
                "source":     "chat",
            })

        # ── ٢. تفضيلات العملات المذكورة ──────────────────────────────────
        coin_mentions = re.findall(
            r"\b(BTC|ETH|BNB|SOL|XRP|ADA|DOGE|DOT|MATIC|AVAX|LINK|UNI|bitcoin|ethereum|solana)\b",
            user_msg, re.IGNORECASE
        )
        if coin_mentions:
            coins_str = ", ".join(set(c.upper() for c in coin_mentions))
            # احفظ فقط إذا كانت الرسالة تحتوي على سياق واضح
            if any(kw in user_lower for kw in ["ركز", "فضّل", "اشتر", "focus", "prefer", "buy", "sell", "trade"]):
                await self.db.save_knowledge({
                    "title":      f"اهتمام بعملات: {coins_str}",
                    "content":    f"المستخدم أشار إلى: {coins_str} في السياق: {user_msg[:150]}",
                    "category":   "user",
                    "importance": 6.0,
                    "tags":       f"coins,{coins_str.lower().replace(', ', ',')},user_preference",
                    "source":     "chat",
                })

        # ── ٣. معلومات استراتيجية من ردود البوت ───────────────────────────
        strategy_kw = ["mean_reversion", "trend_following", "breakout", "scalping",
                       "mean reversion", "trend following", "انعكاس", "اتجاه", "اختراق"]
        for kw in strategy_kw:
            if kw in bot_reply.lower():
                await self.db.save_knowledge({
                    "title":      f"استراتيجية مذكورة: {kw}",
                    "content":    f"السياق: {bot_reply[:200]}",
                    "category":   "strategy",
                    "importance": 5.0,
                    "tags":       f"strategy,{kw.replace(' ','_')},auto_extracted",
                    "source":     "chat_reply",
                })
                break  # واحدة تكفي لكل رسالة

    # ─────────────────────────────────────────────────────────────────────────
    # بناء السياق الغني لكل استدعاء AI
    # ─────────────────────────────────────────────────────────────────────────

    async def get_rich_context(self, query: str = "", limit_lessons: int = 15, limit_knowledge: int = 10) -> str:
        """
        يبني سياقاً شاملاً من الذاكرة لحقن كل استدعاء AI به.
        نسخة محسّنة: تضمّن أنماط الأداء + النظام السوقي + trend الأداء الأخير.
        """
        parts = []

        # ── ٠. تعليمات المستخدم (الأعلى أولوية — تأتي أولاً) ─────────────
        try:
            user_rules = await self.db.search_memory("user_instruction", limit=7)
            if user_rules:
                lines = [f"  ⚠️ {r.get('lesson','')[:200]}" for r in user_rules[:7]]
                parts.append("## ⚠️ تعليمات المستخدم الصريحة (غير قابلة للتجاوز):\n" + "\n".join(lines))
        except Exception:
            pass

        # ── ١. أداء الأنماط المكتسبة (احتمالات النجاح لكل نمط) ───────────
        try:
            pattern_knowledge = await self.db.get_knowledge(category="pattern", limit=15)
            if pattern_knowledge:
                lines = []
                for pk in sorted(pattern_knowledge, key=lambda x: float(x.get("importance", 0)), reverse=True)[:8]:
                    title   = pk.get("title", "")
                    content = pk.get("content", "")[:120]
                    lines.append(f"  📊 {title}: {content}")
                parts.append("## إحصائيات الأنماط المكتسبة:\n" + "\n".join(lines))
        except Exception:
            pass

        # ── ٢. الدروس المكتسبة مرتبة بالأهمية ──────────────────────────
        try:
            lessons = await self.db.get_recent_lessons(limit=limit_lessons * 2)
            if lessons:
                # رتّب بالأهمية ثم خذ الأفضل
                top = sorted(lessons, key=lambda x: float(x.get("importance", 0)), reverse=True)[:limit_lessons]
                lines = []
                for l in top:
                    imp  = l.get("importance", 5.0)
                    cat  = CATEGORIES.get(l.get("category", "trade"), "")
                    text = l.get("lesson", "")[:200]
                    regime = l.get("market_condition", "")
                    regime_tag = f" [{regime}]" if regime and regime != "unknown" else ""
                    lines.append(f"  [{imp:.0f}/10] {cat}{regime_tag} {text}")
                parts.append("## الدروس المكتسبة (الأعلى أهمية):\n" + "\n".join(lines))

                # ── trend الأداء الأخير (آخر 10 صفقات) ──────────────────
                recent_trades = [l for l in lessons[:20] if l.get("category") == "trade"]
                if len(recent_trades) >= 3:
                    recent_wins   = sum(1 for l in recent_trades[:10] if l.get("outcome") == "win")
                    recent_losses = sum(1 for l in recent_trades[:10] if l.get("outcome") == "loss")
                    recent_total  = recent_wins + recent_losses
                    if recent_total > 0:
                        recent_wr = recent_wins / recent_total * 100
                        trend_txt = "📈 متصاعد" if recent_wr >= 60 else ("📉 منخفض" if recent_wr < 45 else "➡️ مستقر")
                        parts.append(f"## أداء الصفقات الأخيرة ({recent_total} صفقة):\n"
                                     f"  Win Rate: {recent_wr:.1f}% | {trend_txt} | "
                                     f"انتصارات: {recent_wins} | خسائر: {recent_losses}")
        except Exception:
            pass

        # ── ٣. المعرفة المستمرة (استراتيجيات + قواعد) ───────────────────
        try:
            knowledge = await self.db.get_knowledge(limit=limit_knowledge + 5)
            # استثني أنماط الأداء (تمّت تغطيتها أعلاه)
            knowledge = [k for k in knowledge if "pattern_perf" not in k.get("tags", "")]
            if knowledge:
                lines = []
                for k in knowledge[:limit_knowledge]:
                    title   = k.get("title", "")
                    content = k.get("content", "")[:180]
                    lines.append(f"  • {title}: {content}")
                parts.append("## المعرفة المستمرة:\n" + "\n".join(lines))
        except Exception:
            pass

        # ── ٤. البحث السياقي (إذا كان هناك استعلام محدد) ──────────────
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
    # تحليل وتوحيد الذاكرة التلقائي (كل 6 ساعات)
    # ─────────────────────────────────────────────────────────────────────────

    async def consolidate_lessons(self) -> str:
        """
        يُقلّص الدروس المتكررة ويستخلص منها قواعد استراتيجية راسخة.
        يعمل تلقائياً كل 6 ساعات عبر الـ scheduler.
        يعيد ملخصاً نصياً لما تمّ.
        """
        try:
            lessons = await self.db.get_recent_lessons(limit=300)
            if len(lessons) < 10:
                return ""

            closed_trades = [l for l in lessons if l.get("category") == "trade" and l.get("outcome") in ("win", "loss")]
            if len(closed_trades) < 5:
                return ""

            wins   = [l for l in closed_trades if l.get("outcome") == "win"]
            losses = [l for l in closed_trades if l.get("outcome") == "loss"]
            total  = len(closed_trades)
            wr     = len(wins) / total * 100 if total > 0 else 0

            # ── استخلاص قواعد من الأنماط الفائزة ───────────────────────
            winning_patterns: dict[str, int] = {}
            losing_patterns:  dict[str, int] = {}
            for l in wins:
                p = l.get("pattern", "")
                if p:
                    winning_patterns[p] = winning_patterns.get(p, 0) + 1
            for l in losses:
                p = l.get("pattern", "")
                if p:
                    losing_patterns[p] = losing_patterns.get(p, 0) + 1

            # ── أفضل وأسوأ نمطَين ────────────────────────────────────
            best  = sorted(winning_patterns.items(), key=lambda x: x[1], reverse=True)[:2]
            worst = sorted(losing_patterns.items(),  key=lambda x: x[1], reverse=True)[:2]

            summary_parts = [f"تحليل {total} صفقة — نسبة النجاح: {wr:.1f}%"]
            if best:
                best_str = ", ".join(f"{p}({n}✅)" for p, n in best)
                await self.db.save_knowledge({
                    "title":      "أنماط الفوز المُدمَجة",
                    "content":    f"أكثر الأنماط نجاحاً: {best_str} | معدل الفوز الكلي: {wr:.1f}%",
                    "category":   "strategy",
                    "importance": 8.0,
                    "tags":       "consolidation,winning_patterns,auto_analysis",
                    "source":     "memory_consolidation",
                })
                summary_parts.append(f"أنماط فائزة: {best_str}")

            if worst:
                worst_str = ", ".join(f"{p}({n}❌)" for p, n in worst)
                await self.db.save_knowledge({
                    "title":      "أنماط الخسارة المُدمَجة",
                    "content":    f"أكثر الأنماط خسارة: {worst_str} — يُنصح بتقليل الاعتماد عليها",
                    "category":   "risk",
                    "importance": 7.5,
                    "tags":       "consolidation,losing_patterns,auto_analysis",
                    "source":     "memory_consolidation",
                })
                summary_parts.append(f"أنماط خاسرة: {worst_str}")

            # ── سجّل درساً استراتيجياً شاملاً ───────────────────────
            meta_lesson = " | ".join(summary_parts)
            await self.db.save_lesson({
                "lesson":     f"[تحليل تلقائي] {meta_lesson}",
                "symbol":     "PORTFOLIO",
                "pattern":    "meta_consolidation",
                "outcome":    "win" if wr >= 50 else "loss",
                "importance": 9.0,
                "category":   "strategy",
                "tags":       "auto_consolidation,meta_analysis,portfolio",
                "confidence": 0.95,
                "source":     "memory_engine",
            })

            return meta_lesson

        except Exception as e:
            print(f"[Memory] consolidate_lessons error: {e}")
            return ""

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
