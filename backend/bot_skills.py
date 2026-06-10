"""
bot_skills.py — نظام مهارات البوت الكامل
البوت يستطيع تنفيذ هذه المهارات عند الطلب من المستخدم.
كل مهارة تُعيد نتيجة + تتعلم منها وتحفظها في الذاكرة.
"""
from __future__ import annotations
import asyncio
import math
import re
from datetime import datetime, timedelta
from typing import Any


# ─────────────────────────────────────────────────────────────────────────────
# Skill Registry
# ─────────────────────────────────────────────────────────────────────────────

SKILL_REGISTRY: dict[str, str] = {
    "calculate":         "احسب تعبيراً رياضياً أو ربح/خسارة صفقة",
    "portfolio":         "تحليل المحفظة الكاملة — ربح/خسارة، توزيع، أفضل/أسوأ",
    "weekly_report":     "تقرير الأداء الأسبوعي الكامل",
    "pattern_report":    "تقرير أداء الأنماط التقنية المستخدمة",
    "strategy_compare":  "مقارنة أداء الاستراتيجيات المختلفة",
    "market_scan":       "فحص السوق الآن وتحديد أفضل فرص",
    "set_rule":          "تحديد قاعدة دائمة يلتزم بها البوت",
    "risk_check":        "فحص مستوى المخاطرة الحالي وتقديم توصيات",
    "explain_trade":     "شرح منطق صفقة معينة بالتفصيل",
    "learning_summary":  "ملخص ما تعلّمه البوت حتى الآن",
    # ── خوادم خارجية ─────────────────────────────────────────────────────────
    "hf_inference":      "تشغيل نموذج AI على HuggingFace (تحليل مشاعر، ترجمة، تصنيف...)",
    "hf_space":          "استدعاء أي Space على HuggingFace لتنفيذ مهمة خارجية",
    "web_fetch":         "جلب بيانات من أي رابط خارجي (أسعار، أخبار، APIs مجانية)",
}


def get_skills_prompt() -> str:
    """نص يُضاف لـ system prompt يشرح المهارات المتاحة."""
    lines = []
    for name, desc in SKILL_REGISTRY.items():
        lines.append(f"[SKILL: {name}=<params>]  ← {desc}")
    return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Skill: Calculate
# ─────────────────────────────────────────────────────────────────────────────

async def skill_calculate(params: str) -> dict[str, Any]:
    """
    يحسب تعبيرات رياضية بأمان — يدعم حسابات التداول.
    مثال: calculate=100*0.03  أو  calculate=pnl(buy,42000,43500,0.1)
    """
    params = params.strip()
    result_val: float | None = None
    explanation = ""

    # ── حساب PnL مخصص ─────────────────────────────────────────────────────
    pnl_match = re.search(
        r"pnl\(\s*(buy|sell)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*,\s*([\d.]+)\s*\)",
        params, re.IGNORECASE
    )
    if pnl_match:
        side     = pnl_match.group(1).lower()
        entry    = float(pnl_match.group(2))
        exit_p   = float(pnl_match.group(3))
        qty      = float(pnl_match.group(4))
        if side == "buy":
            result_val = (exit_p - entry) * qty
        else:
            result_val = (entry - exit_p) * qty
        pct = (result_val / (entry * qty) * 100) if entry * qty > 0 else 0
        explanation = (
            f"صفقة {side.upper()} | دخول: {entry} | خروج: {exit_p} | كمية: {qty}\n"
            f"الربح/الخسارة: ${result_val:+.4f} ({pct:+.2f}%)"
        )
    else:
        # ── حساب رياضي آمن ───────────────────────────────────────────────
        safe_expr = re.sub(r"[^0-9+\-*/().%^ e]", "", params)
        safe_expr = safe_expr.replace("^", "**").replace("%", "/100")
        if safe_expr:
            try:
                result_val = float(eval(safe_expr, {"__builtins__": {}, "math": math, "sqrt": math.sqrt, "abs": abs, "round": round}))
                explanation = f"{params} = {result_val}"
            except Exception as e:
                return {"ok": False, "error": f"تعبير غير صالح: {e}", "input": params}

    if result_val is None:
        return {"ok": False, "error": "لم أستطع فهم الحساب", "input": params}

    return {
        "ok":          True,
        "skill":       "calculate",
        "result":      result_val,
        "formatted":   explanation or f"{result_val:,.6f}",
        "display":     f"🧮 **الحساب:** {explanation or f'{params} = {result_val:,.4f}'}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Skill: Portfolio Analysis
# ─────────────────────────────────────────────────────────────────────────────

async def skill_portfolio(db, params: str = "") -> dict[str, Any]:
    """تحليل شامل للمحفظة — أرباح، خسائر، توزيع، أفضل/أسوأ صفقات."""
    try:
        trades = await db.get_trades(limit=500)
        closed = [t for t in trades if t.get("status") == "closed"]
        open_t = [t for t in trades if t.get("status") == "open"]

        if not closed:
            return {
                "ok":      True,
                "skill":   "portfolio",
                "display": "📊 **تحليل المحفظة:** لا توجد صفقات مغلقة بعد — ابدأ التداول أولاً",
                "data":    {},
            }

        total_pnl   = sum(float(t.get("pnl") or 0) for t in closed)
        wins        = [t for t in closed if float(t.get("pnl") or 0) > 0]
        losses      = [t for t in closed if float(t.get("pnl") or 0) <= 0]
        win_rate    = len(wins) / len(closed) * 100 if closed else 0

        best_trade  = max(closed, key=lambda t: float(t.get("pnl") or 0))
        worst_trade = min(closed, key=lambda t: float(t.get("pnl") or 0))

        avg_win  = sum(float(t.get("pnl") or 0) for t in wins)   / len(wins)   if wins   else 0
        avg_loss = sum(float(t.get("pnl") or 0) for t in losses) / len(losses) if losses else 0

        # Profit factor
        gross_profit = sum(float(t.get("pnl") or 0) for t in wins)
        gross_loss   = abs(sum(float(t.get("pnl") or 0) for t in losses))
        pf           = gross_profit / gross_loss if gross_loss > 0 else float("inf")

        # Per-symbol breakdown
        symbol_pnl: dict[str, float] = {}
        for t in closed:
            sym = t.get("symbol", "?")
            symbol_pnl[sym] = symbol_pnl.get(sym, 0.0) + float(t.get("pnl") or 0)
        best_sym  = max(symbol_pnl, key=symbol_pnl.get) if symbol_pnl else "—"
        worst_sym = min(symbol_pnl, key=symbol_pnl.get) if symbol_pnl else "—"

        display = (
            f"📊 **تحليل المحفظة الكاملة**\n\n"
            f"• الصفقات المغلقة: {len(closed)} | المفتوحة: {len(open_t)}\n"
            f"• إجمالي الربح/الخسارة: **${total_pnl:+.4f}**\n"
            f"• نسبة النجاح: **{win_rate:.1f}%** ({len(wins)}✅ / {len(losses)}❌)\n"
            f"• متوسط الربح: ${avg_win:+.4f} | متوسط الخسارة: ${avg_loss:+.4f}\n"
            f"• Profit Factor: {pf:.2f}x\n"
            f"• أفضل صفقة: {best_trade.get('symbol','?')} ${float(best_trade.get('pnl',0)):+.4f}\n"
            f"• أسوأ صفقة: {worst_trade.get('symbol','?')} ${float(worst_trade.get('pnl',0)):+.4f}\n"
            f"• أفضل عملة: {best_sym} (${symbol_pnl.get(best_sym,0):+.4f})\n"
            f"• أسوأ عملة: {worst_sym} (${symbol_pnl.get(worst_sym,0):+.4f})"
        )

        return {
            "ok":      True,
            "skill":   "portfolio",
            "display": display,
            "data": {
                "total_pnl": round(total_pnl, 4),
                "win_rate":  round(win_rate, 1),
                "closed":    len(closed),
                "open":      len(open_t),
                "profit_factor": round(pf, 2),
                "best_symbol": best_sym,
                "worst_symbol": worst_sym,
            },
        }
    except Exception as e:
        return {"ok": False, "skill": "portfolio", "error": str(e), "display": f"❌ فشل تحليل المحفظة: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Skill: Weekly Report
# ─────────────────────────────────────────────────────────────────────────────

async def skill_weekly_report(db) -> dict[str, Any]:
    """تقرير الأداء الأسبوعي الكامل مع مقارنة بالأسبوع السابق."""
    try:
        trades = await db.get_trades(limit=500)
        closed = [t for t in trades if t.get("status") == "closed"]

        now       = datetime.utcnow()
        week_ago  = now - timedelta(days=7)
        week2_ago = now - timedelta(days=14)

        def parse_dt(t: dict) -> datetime:
            raw = t.get("closed_at") or t.get("created_at") or ""
            try:
                return datetime.fromisoformat(raw.replace("Z",""))
            except Exception:
                return datetime.min

        this_week = [t for t in closed if parse_dt(t) >= week_ago]
        last_week = [t for t in closed if week2_ago <= parse_dt(t) < week_ago]

        def week_stats(tlist: list) -> dict:
            pnl  = sum(float(t.get("pnl") or 0) for t in tlist)
            wins = sum(1 for t in tlist if float(t.get("pnl") or 0) > 0)
            wr   = wins / len(tlist) * 100 if tlist else 0
            return {"total": len(tlist), "pnl": pnl, "wins": wins, "wr": wr}

        tw = week_stats(this_week)
        lw = week_stats(last_week)

        pnl_delta = tw["pnl"] - lw["pnl"]
        wr_delta  = tw["wr"]  - lw["wr"]
        trend_emoji = "📈" if pnl_delta >= 0 else "📉"

        display = (
            f"📅 **تقرير الأسبوع الحالي** ({now.strftime('%d/%m/%Y')})\n\n"
            f"**هذا الأسبوع:**\n"
            f"• صفقات: {tw['total']} | Win Rate: {tw['wr']:.1f}% | PnL: ${tw['pnl']:+.4f}\n\n"
            f"**الأسبوع السابق:**\n"
            f"• صفقات: {lw['total']} | Win Rate: {lw['wr']:.1f}% | PnL: ${lw['pnl']:+.4f}\n\n"
            f"**التغيير:** {trend_emoji} PnL {pnl_delta:+.4f}$ | Win Rate {wr_delta:+.1f}%\n"
        )

        # Top lessons this week
        try:
            lessons = await db.get_recent_lessons(limit=50)
            week_lessons = [l for l in lessons if parse_dt(l) >= week_ago]
            if week_lessons:
                top = week_lessons[:3]
                display += "\n**أبرز دروس هذا الأسبوع:**\n"
                for l in top:
                    display += f"• {l.get('lesson','')[:120]}\n"
        except Exception:
            pass

        return {
            "ok": True, "skill": "weekly_report",
            "display": display,
            "data": {"this_week": tw, "last_week": lw, "pnl_delta": round(pnl_delta, 4)},
        }
    except Exception as e:
        return {"ok": False, "skill": "weekly_report", "error": str(e), "display": f"❌ فشل توليد التقرير: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Skill: Pattern Report
# ─────────────────────────────────────────────────────────────────────────────

async def skill_pattern_report(db) -> dict[str, Any]:
    """تقرير أداء الأنماط التقنية مرتباً من الأفضل للأسوأ."""
    try:
        knowledge = await db.get_knowledge(category="pattern", limit=50)
        if not knowledge:
            # حاول بناءه من الصفقات
            trades  = await db.get_trades(limit=500)
            closed  = [t for t in trades if t.get("status") == "closed"]
            pattern_map: dict[str, dict] = {}
            for t in closed:
                p   = t.get("pattern", "unknown")
                pnl = float(t.get("pnl") or 0)
                if p not in pattern_map:
                    pattern_map[p] = {"wins": 0, "losses": 0, "pnl": 0.0}
                if pnl > 0:
                    pattern_map[p]["wins"] += 1
                else:
                    pattern_map[p]["losses"] += 1
                pattern_map[p]["pnl"] += pnl

            if not pattern_map:
                return {"ok": True, "skill": "pattern_report",
                        "display": "📊 **تقرير الأنماط:** لا توجد بيانات بعد", "data": {}}

            rows = []
            for p, v in pattern_map.items():
                total = v["wins"] + v["losses"]
                wr    = v["wins"] / total * 100 if total > 0 else 0
                rows.append({"pattern": p, "wins": v["wins"], "losses": v["losses"], "wr": wr, "pnl": v["pnl"]})
        else:
            rows = []
            for k in knowledge:
                content = k.get("content", "")
                wins_m   = re.search(r"wins=(\d+)", content)
                losses_m = re.search(r"losses=(\d+)", content)
                wr_m     = re.search(r"win_rate=([\d.]+)%", content)
                wins   = int(wins_m.group(1))   if wins_m   else 0
                losses = int(losses_m.group(1)) if losses_m else 0
                wr     = float(wr_m.group(1))   if wr_m     else 0.0
                title  = k.get("title", "").replace("أداء نمط: ", "").split(" على ")[0]
                rows.append({"pattern": title, "wins": wins, "losses": losses, "wr": wr, "pnl": 0.0})

        rows.sort(key=lambda x: x["wr"], reverse=True)

        lines = ["📊 **تقرير الأنماط التقنية:**\n"]
        for i, r in enumerate(rows[:10]):
            emoji = "🏆" if i == 0 else ("✅" if r["wr"] >= 60 else ("⚠️" if r["wr"] >= 45 else "❌"))
            total = r["wins"] + r["losses"]
            lines.append(
                f"{emoji} **{r['pattern']}**: {r['wr']:.0f}% WR "
                f"({r['wins']}✅/{r['losses']}❌ من {total} صفقة)"
            )

        return {
            "ok": True, "skill": "pattern_report",
            "display": "\n".join(lines),
            "data": {"patterns": rows[:10]},
        }
    except Exception as e:
        return {"ok": False, "skill": "pattern_report", "error": str(e), "display": f"❌ فشل تقرير الأنماط: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Skill: Strategy Compare
# ─────────────────────────────────────────────────────────────────────────────

async def skill_strategy_compare(db) -> dict[str, Any]:
    """مقارنة أداء الاستراتيجيات بناءً على الصفقات المغلقة."""
    try:
        trades = await db.get_trades(limit=500)
        closed = [t for t in trades if t.get("status") == "closed"]
        if not closed:
            return {"ok": True, "skill": "strategy_compare",
                    "display": "📊 لا توجد بيانات كافية بعد", "data": {}}

        strat_map: dict[str, dict] = {}
        for t in closed:
            s   = t.get("strategy") or t.get("pattern") or "unknown"
            pnl = float(t.get("pnl") or 0)
            if s not in strat_map:
                strat_map[s] = {"wins": 0, "total": 0, "pnl": 0.0}
            strat_map[s]["total"] += 1
            if pnl > 0:
                strat_map[s]["wins"] += 1
            strat_map[s]["pnl"] += pnl

        rows = []
        for s, v in strat_map.items():
            wr = v["wins"] / v["total"] * 100 if v["total"] > 0 else 0
            rows.append({"strategy": s, "total": v["total"], "wr": wr, "pnl": v["pnl"]})
        rows.sort(key=lambda x: x["wr"], reverse=True)

        lines = ["📊 **مقارنة الاستراتيجيات:**\n"]
        for r in rows[:6]:
            emoji = "🏆" if r["wr"] >= 65 else ("✅" if r["wr"] >= 50 else "❌")
            lines.append(f"{emoji} **{r['strategy']}**: {r['wr']:.0f}% WR | {r['total']} صفقة | ${r['pnl']:+.4f}")

        best = rows[0]["strategy"] if rows else "—"
        lines.append(f"\n💡 **التوصية:** استخدم **{best}** — الأفضل أداءً")

        return {
            "ok": True, "skill": "strategy_compare",
            "display": "\n".join(lines),
            "data": {"strategies": rows, "best": best},
        }
    except Exception as e:
        return {"ok": False, "skill": "strategy_compare", "error": str(e), "display": f"❌ خطأ: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Skill: Set Rule
# ─────────────────────────────────────────────────────────────────────────────

async def skill_set_rule(db, rule: str) -> dict[str, Any]:
    """يحفظ قاعدة دائمة في ذاكرة البوت — يلتزم بها إلى الأبد."""
    if not rule or len(rule) < 5:
        return {"ok": False, "skill": "set_rule", "error": "القاعدة فارغة أو قصيرة جداً",
                "display": "❌ أدخل قاعدة واضحة ومحددة"}
    try:
        await db.save_lesson({
            "lesson":     f"قاعدة دائمة من المستخدم: {rule}",
            "symbol":     "GLOBAL",
            "pattern":    "user_rule",
            "outcome":    "instruction",
            "importance": 10.0,
            "category":   "user",
            "tags":       "user_rule,permanent,high_priority,user_instruction",
            "confidence": 1.0,
            "source":     "skill_set_rule",
        })
        await db.save_knowledge({
            "title":      f"قاعدة دائمة: {rule[:60]}",
            "content":    rule,
            "category":   "user",
            "importance": 10.0,
            "tags":       "user_rule,permanent,high_priority",
            "source":     "skill_set_rule",
        })
        return {
            "ok": True, "skill": "set_rule",
            "display": f"✅ **تمّ حفظ القاعدة إلى الأبد:**\n\n> {rule}\n\nسأتذكرها في كل صفقة قادمة.",
            "data": {"rule": rule},
        }
    except Exception as e:
        return {"ok": False, "skill": "set_rule", "error": str(e), "display": f"❌ فشل الحفظ: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Skill: Risk Check
# ─────────────────────────────────────────────────────────────────────────────

async def skill_risk_check(db, mem=None) -> dict[str, Any]:
    """فحص مستوى المخاطرة الحالي وتقديم توصيات واضحة."""
    try:
        trades = await db.get_trades(limit=100)
        open_t = [t for t in trades if t.get("status") == "open"]
        closed = [t for t in trades if t.get("status") == "closed"]

        risk_score   = 0
        risk_factors = []
        recommendations = []

        # فحص ١: الصفقات المفتوحة
        if len(open_t) > 5:
            risk_score += 30
            risk_factors.append(f"⚠️ {len(open_t)} صفقة مفتوحة — كثيرة جداً")
            recommendations.append("أغلق بعض الصفقات المفتوحة")
        elif len(open_t) > 3:
            risk_score += 15
            risk_factors.append(f"⚠️ {len(open_t)} صفقات مفتوحة — مرتفع قليلاً")

        # فحص ٢: السلسلة الحمراء
        if mem:
            losses_streak = mem._consecutive_losses
            if losses_streak >= 4:
                risk_score += 40
                risk_factors.append(f"🚨 {losses_streak} خسائر متتالية")
                recommendations.append("توقف مؤقت للمراجعة — لا تفتح صفقات جديدة الآن")
            elif losses_streak >= 2:
                risk_score += 20
                risk_factors.append(f"⚠️ {losses_streak} خسائر متتالية")
                recommendations.append("خفّض حجم الصفقات التالية")

        # فحص ٣: أداء آخر 10 صفقات
        if len(closed) >= 5:
            recent_10   = closed[:10]
            recent_wr   = sum(1 for t in recent_10 if float(t.get("pnl") or 0) > 0) / len(recent_10) * 100
            if recent_wr < 35:
                risk_score += 30
                risk_factors.append(f"🚨 Win Rate الأخير: {recent_wr:.0f}% — خطر عالٍ")
                recommendations.append("غيّر الاستراتيجية فوراً")
            elif recent_wr < 50:
                risk_score += 15
                risk_factors.append(f"⚠️ Win Rate الأخير: {recent_wr:.0f}% — منخفض")

        risk_level = "منخفض ✅" if risk_score < 25 else ("متوسط ⚠️" if risk_score < 55 else "عالٍ 🚨")

        display = (
            f"🛡️ **فحص المخاطرة**\n\n"
            f"• مستوى الخطر: **{risk_level}** ({risk_score}/100)\n"
            f"• الصفقات المفتوحة: {len(open_t)}\n"
        )
        if risk_factors:
            display += "\n**عوامل الخطر:**\n" + "\n".join(f"  {f}" for f in risk_factors)
        if recommendations:
            display += "\n\n**التوصيات الفورية:**\n" + "\n".join(f"  → {r}" for r in recommendations)
        if not risk_factors:
            display += "\n✅ المخاطرة تحت السيطرة — كل شيء يسير بشكل جيد"

        return {
            "ok": True, "skill": "risk_check",
            "display": display,
            "data": {"risk_score": risk_score, "risk_level": risk_level, "open_trades": len(open_t)},
        }
    except Exception as e:
        return {"ok": False, "skill": "risk_check", "error": str(e), "display": f"❌ فشل فحص المخاطرة: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Skill: Learning Summary
# ─────────────────────────────────────────────────────────────────────────────

async def skill_learning_summary(db) -> dict[str, Any]:
    """ملخص كامل لما تعلّمه البوت — الدروس، القواعد، المعرفة."""
    try:
        lessons   = await db.get_recent_lessons(limit=200)
        knowledge = await db.get_knowledge(limit=100)

        total_lessons   = len(lessons)
        user_rules      = [l for l in lessons if "user_rule" in l.get("tags", "") or "user_instruction" in l.get("tags", "")]
        trade_lessons   = [l for l in lessons if l.get("category") == "trade"]
        strategy_know   = [k for k in knowledge if k.get("category") == "strategy"]
        pattern_know    = [k for k in knowledge if k.get("category") == "pattern"]

        wins   = sum(1 for l in trade_lessons if l.get("outcome") == "win")
        losses = sum(1 for l in trade_lessons if l.get("outcome") == "loss")

        # أهم 5 دروس
        top_lessons = sorted(lessons, key=lambda x: float(x.get("importance", 0)), reverse=True)[:5]

        display = (
            f"🧠 **ملخص ذاكرة البوت**\n\n"
            f"• إجمالي الدروس المحفوظة: **{total_lessons}**\n"
            f"• دروس الصفقات: {len(trade_lessons)} ({wins}✅ / {losses}❌)\n"
            f"• قواعد المستخدم الدائمة: **{len(user_rules)}** قاعدة\n"
            f"• معرفة استراتيجية: {len(strategy_know)} عنصر\n"
            f"• إحصائيات أنماط: {len(pattern_know)} نمط\n"
        )

        if user_rules:
            display += "\n**قواعدك الدائمة:**\n"
            for r in user_rules[:5]:
                lesson_text = r.get("lesson", "").replace("قاعدة دائمة من المستخدم: ", "").replace("تعليمة المستخدم: ", "")
                display += f"  📌 {lesson_text[:100]}\n"

        if top_lessons:
            display += "\n**أهم 5 دروس:**\n"
            for l in top_lessons:
                display += f"  • [{l.get('importance', 0):.0f}/10] {l.get('lesson', '')[:100]}\n"

        return {
            "ok": True, "skill": "learning_summary",
            "display": display,
            "data": {
                "total_lessons": total_lessons,
                "user_rules": len(user_rules),
                "strategy_knowledge": len(strategy_know),
                "pattern_stats": len(pattern_know),
            },
        }
    except Exception as e:
        return {"ok": False, "skill": "learning_summary", "error": str(e), "display": f"❌ خطأ: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Skill: Market Scan
# ─────────────────────────────────────────────────────────────────────────────

async def skill_market_scan(db, params: str = "") -> dict[str, Any]:
    """
    يشغّل فحص السوق الفوري ويُعيد النتائج.
    يحاول استخدام ExchangeClient للحصول على بيانات حقيقية.
    """
    try:
        symbols_env = params.strip() or "BTC/USDT,ETH/USDT,BNB/USDT,SOL/USDT"
        syms = [s.strip() for s in symbols_env.split(",") if s.strip()][:6]

        from bybit_client import ExchangeClient
        client = ExchangeClient.get_instance()
        signals = []

        for sym in syms:
            try:
                price = await client.get_current_price(sym)
                if price and price > 0:
                    signals.append({"symbol": sym, "price": price, "status": "ok"})
            except Exception:
                signals.append({"symbol": sym, "price": None, "status": "unavailable"})

        lines = ["🔍 **فحص السوق الآن:**\n"]
        for s in signals:
            if s["price"]:
                lines.append(f"  • {s['symbol']}: ${s['price']:,.4f}")
            else:
                lines.append(f"  • {s['symbol']}: غير متاح حالياً")

        lines.append("\n💡 استخدم Autopilot لفحص الإشارات الكاملة تلقائياً")

        return {
            "ok": True, "skill": "market_scan",
            "display": "\n".join(lines),
            "data": {"signals": signals, "symbols_scanned": len(syms)},
        }
    except Exception as e:
        return {"ok": False, "skill": "market_scan", "error": str(e), "display": f"❌ فشل فحص السوق: {e}"}


# ─────────────────────────────────────────────────────────────────────────────
# Skill Dispatcher
# ─────────────────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────────────────
# Skill: HF Inference — تشغيل نموذج على HuggingFace
# ─────────────────────────────────────────────────────────────────────────────

async def skill_hf_inference(db, params: str) -> dict[str, Any]:
    """
    يشغّل نموذج AI على HuggingFace Inference API.
    params: "model=sentiment,text=البيتكوين سيرتفع"
            أو "sentiment: النص" أو "summarize: النص"
    """
    from hf_client import hf_inference, RECOMMENDED_MODELS, analyze_sentiment

    params = params.strip()
    model = "sentiment"
    text  = params

    # Parse "model=X,text=Y" or "task: text"
    if "model=" in params:
        for part in params.split(","):
            part = part.strip()
            if part.startswith("model="):
                model = part[6:].strip()
            elif part.startswith("text="):
                text = part[5:].strip()
    elif ":" in params:
        parts = params.split(":", 1)
        model = parts[0].strip()
        text  = parts[1].strip()

    if not text:
        return {"ok": False, "skill": "hf_inference", "display": "❌ يلزم نص للتحليل"}

    # Use quick sentiment helper
    if model.lower() in ("sentiment", "مشاعر"):
        result_str = await analyze_sentiment(text, db)
        return {
            "ok": True, "skill": "hf_inference",
            "model": RECOMMENDED_MODELS.get("sentiment", "sentiment"),
            "display": f"📊 تحليل المشاعر:\n«{text[:80]}»\n→ {result_str}",
        }

    result = await hf_inference(model, text, db=db)
    if not result["ok"]:
        return {"ok": False, "skill": "hf_inference", "display": f"❌ {result.get('error', 'فشل')}"}

    raw = result.get("result", "")
    display_result = str(raw)[:500] if not isinstance(raw, str) else raw[:500]
    return {
        "ok": True, "skill": "hf_inference",
        "model": result.get("model", model),
        "display": f"🤗 نتيجة {model}:\n{display_result}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Skill: HF Space — استدعاء Space خارجي
# ─────────────────────────────────────────────────────────────────────────────

async def skill_hf_space(db, params: str) -> dict[str, Any]:
    """
    يستدعي HuggingFace Space API.
    params: "space_id=owner/name,data=النص"
            أو "owner/name: البيانات"
    """
    from hf_client import hf_space_call

    params = params.strip()
    space_id = ""
    data_val  = ""
    api_name  = "/predict"

    if "space_id=" in params or "space=" in params:
        for part in params.split(","):
            part = part.strip()
            if part.startswith(("space_id=", "space=")):
                space_id = part.split("=", 1)[1].strip()
            elif part.startswith("data="):
                data_val = part[5:].strip()
            elif part.startswith("api="):
                api_name = part[4:].strip()
    elif "/" in params:
        parts = params.split(":", 1)
        space_id = parts[0].strip()
        data_val = parts[1].strip() if len(parts) > 1 else ""

    if not space_id:
        return {"ok": False, "skill": "hf_space", "display": "❌ يلزم تحديد Space ID مثل: owner/name"}

    result = await hf_space_call(space_id, api_name=api_name, data=[data_val] if data_val else [], db=db)
    if not result["ok"]:
        return {"ok": False, "skill": "hf_space", "display": f"❌ تعذّر الاتصال بـ {space_id}: {result.get('error', '')}"}

    raw = result.get("result", "")
    display_result = (raw.get("data", raw) if isinstance(raw, dict) else raw)
    return {
        "ok": True, "skill": "hf_space",
        "space": space_id,
        "display": f"🚀 نتيجة Space {space_id}:\n{str(display_result)[:600]}",
    }


# ─────────────────────────────────────────────────────────────────────────────
# Skill: Web Fetch — جلب بيانات من رابط خارجي
# ─────────────────────────────────────────────────────────────────────────────

async def skill_web_fetch(params: str) -> dict[str, Any]:
    """
    يجلب بيانات من أي URL خارجي مجاناً بلا مفتاح.
    params: URL كامل أو اسم مختصر (bitcoin_price, eth_price, crypto_news)
    """
    from hf_client import web_fetch, fetch_crypto_price

    params = params.strip()

    # Shortcuts for common tasks
    shortcuts = {
        "bitcoin_price":  "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd&include_24hr_change=true",
        "eth_price":      "https://api.coingecko.com/api/v3/simple/price?ids=ethereum&vs_currencies=usd&include_24hr_change=true",
        "bnb_price":      "https://api.coingecko.com/api/v3/simple/price?ids=binancecoin&vs_currencies=usd&include_24hr_change=true",
        "crypto_fear":    "https://api.alternative.me/fng/?limit=1",
        "btc_dominance":  "https://api.coingecko.com/api/v3/global",
        "top_coins":      "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&order=market_cap_desc&per_page=5&page=1",
    }

    url = shortcuts.get(params.lower().replace(" ", "_"), params)

    if not url.startswith("http"):
        return {"ok": False, "skill": "web_fetch", "display": f"❌ رابط غير صحيح: {params}"}

    result = await web_fetch(url)
    if not result["ok"]:
        return {"ok": False, "skill": "web_fetch", "display": f"❌ فشل جلب البيانات: {result.get('error', '')}"}

    content = result.get("content", "")

    # Format common responses nicely
    display = ""
    if "coingecko" in url and "simple/price" in url:
        try:
            prices = []
            for coin, data in content.items():
                chg = data.get("usd_24h_change", 0) or 0
                arrow = "▲" if chg >= 0 else "▼"
                prices.append(f"{coin.upper()}: ${data['usd']:,.2f}  {arrow}{abs(chg):.2f}%")
            display = "💰 أسعار العملات:\n" + "\n".join(prices)
        except Exception:
            display = str(content)[:500]
    elif "fng" in url:
        try:
            fng = content["data"][0]
            display = f"😱 مؤشر الخوف والطمع:\n{fng['value']} — {fng['value_classification']}"
        except Exception:
            display = str(content)[:500]
    elif "global" in url:
        try:
            d = content.get("data", {})
            btc_dom = d.get("market_cap_percentage", {}).get("btc", 0)
            total   = d.get("total_market_cap", {}).get("usd", 0)
            display = f"🌍 السوق الكلي:\nهيمنة BTC: {btc_dom:.1f}%\nإجمالي السوق: ${total/1e9:.1f}B"
        except Exception:
            display = str(content)[:500]
    elif "markets" in url:
        try:
            lines = []
            for c in content[:5]:
                chg = c.get("price_change_percentage_24h", 0) or 0
                arrow = "▲" if chg >= 0 else "▼"
                lines.append(f"{c['symbol'].upper()}: ${c['current_price']:,.4g}  {arrow}{abs(chg):.1f}%")
            display = "🏆 أفضل 5 عملات:\n" + "\n".join(lines)
        except Exception:
            display = str(content)[:500]
    else:
        display = f"📡 البيانات من {url}:\n{str(content)[:500]}"

    return {
        "ok": True, "skill": "web_fetch",
        "url": url,
        "display": display,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Dispatch
# ─────────────────────────────────────────────────────────────────────────────

async def dispatch_skill(skill_name: str, params: str, db, mem=None) -> dict[str, Any]:
    """
    ينفّذ المهارة المطلوبة ويُعيد النتيجة.
    يُستدعى من brain_chat_endpoint في main.py.
    """
    name = skill_name.strip().lower()
    try:
        if name == "calculate":
            return await skill_calculate(params)
        elif name == "portfolio":
            return await skill_portfolio(db, params)
        elif name == "weekly_report":
            return await skill_weekly_report(db)
        elif name == "pattern_report":
            return await skill_pattern_report(db)
        elif name == "strategy_compare":
            return await skill_strategy_compare(db)
        elif name == "set_rule":
            return await skill_set_rule(db, params)
        elif name == "risk_check":
            return await skill_risk_check(db, mem)
        elif name == "market_scan":
            return await skill_market_scan(db, params)
        elif name == "learning_summary":
            return await skill_learning_summary(db)
        elif name == "hf_inference":
            return await skill_hf_inference(db, params)
        elif name == "hf_space":
            return await skill_hf_space(db, params)
        elif name == "web_fetch":
            return await skill_web_fetch(params)
        else:
            return {
                "ok": False, "skill": name,
                "error": f"مهارة غير معروفة: {name}",
                "display": f"❓ لا أعرف مهارة '{name}'. المهارات المتاحة: {', '.join(SKILL_REGISTRY.keys())}",
            }
    except Exception as e:
        return {"ok": False, "skill": name, "error": str(e), "display": f"❌ خطأ في تنفيذ {name}: {e}"}
