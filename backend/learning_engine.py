"""
learning_engine.py — محرك التعلم الخارق
يُطوّر البوت نفسه تلقائياً بناءً على نتائجه الحقيقية.
يعمل كل ساعة ويُعدّل الاستراتيجية، الثقة، والأنماط.
"""
from __future__ import annotations
import json
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database import DatabaseClient
    from agent_core import AgentMemory


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

STRATEGY_OPTIONS = [
    "mean_reversion",
    "trend_following",
    "momentum_breakout",
    "scalping",
    "conservative",
]

MIN_TRADES_FOR_SWITCH = 5   # لا نُغيّر الاستراتيجية إلا بعد هذا العدد من الصفقات
EMERGENCY_LOSS_STREAK = 4   # عدد الخسائر المتتالية الذي يُوقف البوت


# ─────────────────────────────────────────────────────────────────────────────
# Core Learning Engine
# ─────────────────────────────────────────────────────────────────────────────

class LearningEngine:
    """
    المحرك الرئيسي للتعلم التلقائي.
    يُطوّر البوت نفسه بناءً على بياناته الحقيقية.
    """

    def __init__(self, db: "DatabaseClient", mem: "AgentMemory | None" = None):
        self.db  = db
        self.mem = mem

    # ── ١. تكيّف الاستراتيجية تلقائياً ───────────────────────────────────────

    async def auto_adjust_strategy(self) -> dict:
        """
        يحلل آخر N صفقة ويُعدّل الاستراتيجية تلقائياً.
        يُعيد dict يصف ما تغيّر.
        """
        result = {"changed": False, "reason": "", "old": "", "new": "", "insights": []}
        if not self.mem:
            return result

        trades = await self.db.get_trades(limit=100)
        closed = [t for t in trades if t.get("status") == "closed"]
        if len(closed) < MIN_TRADES_FOR_SWITCH:
            result["reason"] = f"صفقات غير كافية ({len(closed)}/{MIN_TRADES_FOR_SWITCH})"
            return result

        recent = closed[:20]   # آخر 20 صفقة فقط للتكيّف السريع

        # ── احسب win-rate الأخير ───────────────────────────────────────────
        wins        = sum(1 for t in recent if float(t.get("pnl") or 0) > 0)
        total       = len(recent)
        recent_wr   = wins / total * 100 if total > 0 else 0
        current_strat = self.mem._current_strategy

        # ── احسب win-rate لكل استراتيجية/نمط ────────────────────────────
        strat_perf: dict[str, dict] = {}
        for t in closed[:50]:
            s   = t.get("strategy") or t.get("pattern") or "unknown"
            pnl = float(t.get("pnl") or 0)
            if s not in strat_perf:
                strat_perf[s] = {"wins": 0, "total": 0, "pnl": 0.0}
            strat_perf[s]["total"] += 1
            if pnl > 0:
                strat_perf[s]["wins"] += 1
            strat_perf[s]["pnl"] += pnl

        # ── ابحث عن أفضل استراتيجية (≥ 5 صفقات) ────────────────────────
        best_strat = current_strat
        best_wr    = recent_wr
        for s, v in strat_perf.items():
            if v["total"] >= 5:
                wr = v["wins"] / v["total"] * 100
                if wr > best_wr and s in STRATEGY_OPTIONS:
                    best_wr    = wr
                    best_strat = s

        # ── قرار التغيير ─────────────────────────────────────────────────
        switched = False
        if recent_wr < 40 and len(recent) >= 8:
            # أداء سيء جداً — انتقل لـ conservative أو لأفضل استراتيجية
            if current_strat != "conservative":
                new_strat = best_strat if best_strat != current_strat else "conservative"
                old_strat = current_strat
                self.mem.set_strategy(new_strat, confidence=0.6)
                switched  = True
                reason    = f"Win Rate منخفض جداً ({recent_wr:.0f}%) — انتقلت تلقائياً من {old_strat} → {new_strat}"
                result.update({"changed": True, "old": old_strat, "new": new_strat, "reason": reason})
                result["insights"].append(f"⚠️ {reason}")
                await self._save_learning_insight(reason, "auto_strategy_switch")

        elif recent_wr > 72 and best_strat == current_strat:
            # أداء ممتاز — ارفع الثقة
            if self.mem._strategy_confidence < 0.95:
                old_conf = self.mem._strategy_confidence
                new_conf = min(0.95, old_conf + 0.05)
                self.mem._strategy_confidence = new_conf
                self.mem._save_state()
                reason = f"أداء ممتاز ({recent_wr:.0f}%) — رفعت ثقتي في {current_strat} إلى {new_conf:.0%}"
                result["insights"].append(f"📈 {reason}")
                result["reason"] = reason
                await self._save_learning_insight(reason, "confidence_boost")

        elif best_strat != current_strat and best_wr > recent_wr + 15 and best_wr > 60:
            # استراتيجية أخرى تؤدي أفضل بفارق كبير
            old_strat = current_strat
            self.mem.set_strategy(best_strat, confidence=0.75)
            switched  = True
            reason    = f"استراتيجية {best_strat} تؤدي أفضل ({best_wr:.0f}% > {recent_wr:.0f}%) — تبديل تلقائي"
            result.update({"changed": True, "old": old_strat, "new": best_strat, "reason": reason})
            result["insights"].append(f"🔄 {reason}")
            await self._save_learning_insight(reason, "auto_strategy_upgrade")

        # ── دائماً: تحديث الأنماط بناءً على الأداء ──────────────────────
        pattern_insights = await self._update_pattern_scores()
        result["insights"].extend(pattern_insights)

        return result

    # ── ٢. تعديل حد الثقة تلقائياً ─────────────────────────────────────────

    async def evolve_confidence_threshold(self, current_threshold: int) -> dict:
        """
        يعدّل حد الثقة المطلوب للدخول في صفقة بناءً على الأداء الأخير.
        يُعيد dict مع القيمة الجديدة والسبب.
        """
        result = {"changed": False, "old": current_threshold, "new": current_threshold, "reason": ""}

        trades = await self.db.get_trades(limit=60)
        closed = [t for t in trades if t.get("status") == "closed"]
        if len(closed) < 8:
            return result

        recent  = closed[:15]
        wins    = sum(1 for t in recent if float(t.get("pnl") or 0) > 0)
        wr      = wins / len(recent) * 100

        # نتحقق من متوسط الثقة عند النجاح والفشل
        win_confs  = [int(t.get("confidence", 0)) for t in recent if float(t.get("pnl") or 0) > 0]
        loss_confs = [int(t.get("confidence", 0)) for t in recent if float(t.get("pnl") or 0) <= 0]

        avg_win_conf  = sum(win_confs)  / len(win_confs)  if win_confs  else current_threshold
        avg_loss_conf = sum(loss_confs) / len(loss_confs) if loss_confs else current_threshold

        new_threshold = current_threshold
        if wr < 40 and avg_loss_conf < current_threshold + 10:
            # الخسائر عند ثقة مرتفعة — ارفع الحد
            new_threshold = min(80, current_threshold + 5)
            reason = f"Win Rate {wr:.0f}% — رفعت حد الثقة من {current_threshold}% إلى {new_threshold}%"
        elif wr > 70 and avg_win_conf > current_threshold + 15:
            # الانتصارات بثقة عالية جداً — يمكن خفض الحد قليلاً لمزيد من الفرص
            new_threshold = max(45, current_threshold - 3)
            reason = f"Win Rate {wr:.0f}% ممتاز — خفضت حد الثقة قليلاً إلى {new_threshold}%"
        else:
            return result

        result.update({"changed": True, "new": new_threshold, "reason": reason})
        await self._save_learning_insight(reason, "threshold_evolution")
        return result

    # ── ٣. استخراج درس عميق من النظام السوقي ──────────────────────────────

    async def learn_market_regime_mapping(self) -> list[str]:
        """
        يتعلم أي استراتيجية تعمل في أي نظام سوقي (trending/ranging/volatile).
        يُعيد قائمة رسائل توضيحية.
        """
        insights = []
        trades = await self.db.get_trades(limit=200)
        closed = [t for t in trades if t.get("status") == "closed" and t.get("market_condition")]

        if len(closed) < 10:
            return insights

        regime_map: dict[str, dict] = {}
        for t in closed:
            regime = t.get("market_condition", "unknown")
            strat  = t.get("strategy") or t.get("pattern") or "unknown"
            pnl    = float(t.get("pnl") or 0)
            key    = f"{regime}|{strat}"
            if key not in regime_map:
                regime_map[key] = {"wins": 0, "total": 0, "pnl": 0.0}
            regime_map[key]["total"] += 1
            if pnl > 0:
                regime_map[key]["wins"] += 1
            regime_map[key]["pnl"] += pnl

        # ابحث عن مجموعات ذات أداء مميز
        for key, v in regime_map.items():
            if v["total"] < 4:
                continue
            regime, strat = key.split("|", 1)
            wr = v["wins"] / v["total"] * 100

            if wr >= 65 or wr <= 30:
                direction = "تعمل جيداً" if wr >= 65 else "لا تعمل"
                insight = (
                    f"استراتيجية {strat} {direction} في سوق {regime} "
                    f"({wr:.0f}% WR من {v['total']} صفقة)"
                )
                await self.db.save_knowledge({
                    "title":      f"نظام سوقي: {regime} + {strat}",
                    "content":    insight,
                    "category":   "strategy",
                    "importance": 7.5 if wr >= 65 else 8.5,
                    "tags":       f"regime_mapping,{regime},{strat},auto_learned",
                    "source":     "learning_engine",
                })
                insights.append(insight)

        return insights[:5]

    # ── ٤. تحديث نقاط الأنماط في AgentMemory ───────────────────────────────

    async def _update_pattern_scores(self) -> list[str]:
        """
        يُحدّث mem._pattern_scores بناءً على البيانات الحقيقية في DB.
        """
        insights = []
        if not self.mem:
            return insights

        knowledge = await self.db.get_knowledge(category="pattern", limit=50)
        import re
        for k in knowledge:
            content  = k.get("content", "")
            tags     = k.get("tags", "")
            wr_match = re.search(r"win_rate=([\d.]+)%", content)
            tot_match= re.search(r"total=(\d+)", content)
            if not wr_match:
                continue

            wr    = float(wr_match.group(1))
            total = int(tot_match.group(1)) if tot_match else 0

            # استخرج اسم النمط من tags
            for tag in tags.split(","):
                if tag.startswith("pattern_perf_"):
                    pattern_name = tag[len("pattern_perf_"):]
                    if pattern_name and total >= 3:
                        old_score = self.mem._pattern_scores.get(pattern_name, {}).get("win_rate", 50)
                        # تحديث نقدي (exponential moving average)
                        new_score = 0.7 * wr + 0.3 * old_score
                        if pattern_name not in self.mem._pattern_scores:
                            self.mem._pattern_scores[pattern_name] = {"wins": 0, "losses": 0, "total": 0, "win_rate": 50.0}
                        self.mem._pattern_scores[pattern_name]["win_rate"] = round(new_score, 1)
                        self.mem._pattern_scores[pattern_name]["total"]    = total

                        if abs(new_score - old_score) > 10:
                            direction = "تحسّن" if new_score > old_score else "تراجع"
                            insights.append(f"📊 نمط {pattern_name}: {direction} ({old_score:.0f}% → {new_score:.0f}%)")
                    break

        if insights:
            self.mem._save_state()

        return insights

    # ── ٥. تحليل عميق للبوت: هل يتعلم فعلاً؟ ─────────────────────────────

    async def deep_self_analysis(self) -> str:
        """
        يُحلّل البوت نفسه ويُعيد رسالة تشخيصية شاملة.
        """
        trades  = await self.db.get_trades(limit=200)
        closed  = [t for t in trades if t.get("status") == "closed"]
        lessons = await self.db.get_recent_lessons(limit=100)

        if len(closed) < 3:
            return "البوت لا يزال في مرحلة التعلم المبكرة — يحتاج المزيد من الصفقات"

        total_pnl = sum(float(t.get("pnl") or 0) for t in closed)
        wins      = sum(1 for t in closed if float(t.get("pnl") or 0) > 0)
        wr        = wins / len(closed) * 100 if closed else 0

        # هل تحسّن البوت بمرور الوقت؟
        first_half = closed[len(closed)//2:]
        sec_half   = closed[:len(closed)//2]
        wr_first   = sum(1 for t in first_half if float(t.get("pnl") or 0) > 0) / len(first_half) * 100 if first_half else 0
        wr_second  = sum(1 for t in sec_half   if float(t.get("pnl") or 0) > 0) / len(sec_half)   * 100 if sec_half else 0
        improving  = wr_second > wr_first

        analysis = (
            f"📊 تحليل أداء البوت الذاتي:\n"
            f"• {len(closed)} صفقة مغلقة | Win Rate: {wr:.1f}% | PnL: ${total_pnl:+.4f}\n"
            f"• Win Rate النصف الأول: {wr_first:.1f}% | النصف الثاني: {wr_second:.1f}%\n"
            f"• {'✅ البوت يتحسن مع الوقت' if improving else '⚠️ الأداء لم يتحسن بعد — يحتاج مزيداً من البيانات'}\n"
            f"• الدروس المحفوظة: {len(lessons)}"
        )

        await self._save_learning_insight(
            f"تحليل ذاتي: Win Rate {wr:.1f}% | {'متحسن' if improving else 'ثابت'}",
            "deep_self_analysis"
        )

        return analysis

    # ── Helper ──────────────────────────────────────────────────────────────

    async def _save_learning_insight(self, insight: str, source: str) -> None:
        """يحفظ درساً مستخلصاً من التعلم الذاتي."""
        try:
            await self.db.save_lesson({
                "lesson":     f"[تعلم تلقائي] {insight}",
                "symbol":     "SELF",
                "pattern":    source,
                "outcome":    "win",
                "importance": 8.0,
                "category":   "strategy",
                "tags":       f"auto_learning,{source}",
                "confidence": 0.85,
                "source":     "learning_engine",
            })
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# Convenience function for scheduler
# ─────────────────────────────────────────────────────────────────────────────

async def run_auto_learning(db, mem=None, current_threshold: int = 55) -> dict:
    """
    دالة رئيسية تُشغَّل كل ساعة من الـ scheduler.
    تُعيد ملخص التغييرات.
    """
    engine  = LearningEngine(db, mem)
    results = {}

    # ١. تكيّف الاستراتيجية
    strat_result = await engine.auto_adjust_strategy()
    results["strategy"] = strat_result

    # ٢. تعديل حد الثقة
    thresh_result = await engine.evolve_confidence_threshold(current_threshold)
    results["threshold"] = thresh_result

    # ٣. تعلم النظام السوقي (كل 3 ساعات — نتحقق من الوقت خارجياً)
    regime_insights = await engine.learn_market_regime_mapping()
    results["regime_insights"] = regime_insights

    return results
