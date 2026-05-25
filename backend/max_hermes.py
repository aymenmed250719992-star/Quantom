"""
MaxHermes — وكيل الذاكرة الدائمة والتعلم الآلي

مُستوحى من مفهوم MaxHermes: وكيل ذكي لا ينسى أبداً.

القدرات:
• ذاكرة دائمة من كل صفقة ومحادثة
• تعلم تلقائي مستمر
• تحليل ملفات Excel / CSV لبيانات السوق
• توليد تقارير مالية احترافية
• استدعاء الدروس المناسبة في الوقت المناسب
"""

import io
import json
import time
from datetime import datetime, timedelta
from typing import Any, Optional


class MaxHermes:
    """
    وكيل الذاكرة الذكية — يتذكر كل شيء ويتعلم باستمرار.
    يعمل كـ "قسم الأرشيف والتحليل" في الشركة.
    """

    _instance: Optional["MaxHermes"] = None

    def __init__(self, db: Any) -> None:
        self.db          = db
        self.session_log: list[dict] = []
        self.excel_cache: list[dict] = []

    @classmethod
    def get_instance(cls, db: Any = None) -> "MaxHermes":
        if cls._instance is None:
            if db is None:
                raise ValueError("MaxHermes requires db on first init")
            cls._instance = cls(db)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        cls._instance = None

    # ─────────────────────────────────────────────────────────────────────────
    # تحليل ملفات Excel / CSV
    # ─────────────────────────────────────────────────────────────────────────

    async def analyze_excel(self, file_bytes: bytes, filename: str = "data.xlsx") -> dict:
        """
        يحلل ملف Excel أو CSV ويستخرج رؤى مالية.
        Returns dict with insights, stats, recommendations.
        """
        try:
            import pandas as pd

            ext = filename.lower().split(".")[-1]
            if ext in ("xlsx", "xls"):
                try:
                    import openpyxl
                    df = pd.read_excel(io.BytesIO(file_bytes))
                except ImportError:
                    df = pd.read_csv(io.BytesIO(file_bytes))
            else:
                df = pd.read_csv(io.BytesIO(file_bytes))

            stats = {}
            insights = []
            recommendations = []

            # إحصاءات أساسية
            numeric_cols = df.select_dtypes(include="number").columns.tolist()
            for col in numeric_cols[:10]:
                col_data = df[col].dropna()
                if len(col_data) == 0:
                    continue
                stats[col] = {
                    "mean":   round(float(col_data.mean()), 4),
                    "max":    round(float(col_data.max()),  4),
                    "min":    round(float(col_data.min()),  4),
                    "std":    round(float(col_data.std()),  4) if len(col_data) > 1 else 0,
                    "count":  len(col_data),
                }

            # البحث عن أعمدة PnL / Profit
            pnl_col = None
            for c in df.columns:
                if any(kw in c.lower() for kw in ["pnl", "profit", "loss", "return", "ربح", "خسارة"]):
                    pnl_col = c
                    break

            if pnl_col and pnl_col in df.columns:
                pnl_data = df[pnl_col].dropna()
                wins  = (pnl_data > 0).sum()
                total = len(pnl_data)
                win_rate = round(wins / total * 100, 1) if total > 0 else 0
                total_pnl = round(float(pnl_data.sum()), 4)
                best  = round(float(pnl_data.max()),  4)
                worst = round(float(pnl_data.min()),  4)

                insights.append(f"📊 إجمالي الصفقات: {total} | نسبة الفوز: {win_rate}%")
                insights.append(f"💰 إجمالي PnL: ${total_pnl:+.2f} | أفضل: ${best} | أسوأ: ${worst}")

                if win_rate >= 60:
                    recommendations.append("✅ استراتيجية رابحة — استمر واحافظ على إدارة المخاطر")
                elif win_rate >= 50:
                    recommendations.append("⚠️ نسبة فوز متوسطة — راجع نسبة المخاطرة/المكافأة")
                else:
                    recommendations.append("❌ نسبة فوز ضعيفة — راجع الاستراتيجية الكاملة")

            # تحليل الأعمدة الزمنية
            date_cols = [c for c in df.columns if any(k in c.lower() for k in ["date", "time", "تاريخ"])]
            if date_cols:
                insights.append(f"📅 بيانات زمنية محددة: {date_cols[0]}")
                insights.append(f"   من: {df[date_cols[0]].iloc[0]} إلى: {df[date_cols[0]].iloc[-1]}")

            # البحث عن أعمدة العملات
            symbol_cols = [c for c in df.columns if any(k in c.lower() for k in ["symbol", "pair", "coin", "عملة"])]
            if symbol_cols:
                top_symbols = df[symbol_cols[0]].value_counts().head(5).to_dict()
                insights.append(f"🪙 أكثر الأصول تداولاً: {list(top_symbols.keys())}")

            result = {
                "filename":        filename,
                "rows":            len(df),
                "columns":         len(df.columns),
                "column_names":    df.columns.tolist()[:20],
                "stats":           stats,
                "insights":        insights,
                "recommendations": recommendations,
                "analyzed_at":     datetime.utcnow().isoformat(),
            }

            # حفظ في الذاكرة
            cache_entry = {"filename": filename, "result": result, "time": time.time()}
            self.excel_cache.append(cache_entry)
            if len(self.excel_cache) > 10:
                self.excel_cache = self.excel_cache[-10:]

            # حفظ ملخص في bot_knowledge
            if insights:
                try:
                    await self.db.save_knowledge({
                        "title":      f"تحليل Excel: {filename}",
                        "content":    "\n".join(insights[:5]),
                        "category":   "market",
                        "importance": 7.0,
                        "tags":       "excel,analysis",
                        "source":     "max_hermes",
                    })
                except Exception:
                    pass

            return result

        except ImportError as e:
            return {"error": f"مكتبة pandas غير موجودة: {e}", "filename": filename}
        except Exception as e:
            return {"error": str(e), "filename": filename}

    # ─────────────────────────────────────────────────────────────────────────
    # توليد تقرير مالي
    # ─────────────────────────────────────────────────────────────────────────

    async def generate_report(self, period_days: int = 7) -> dict:
        """يُولّد تقريراً مالياً شاملاً للفترة المحددة."""
        try:
            trades    = await self.db.get_trades(limit=500)
            since     = datetime.utcnow() - timedelta(days=period_days)
            since_str = since.isoformat()

            recent = [
                t for t in trades
                if t.get("created_at", "") >= since_str
            ]
            closed = [t for t in recent if t.get("status") == "closed"]
            open_t = [t for t in recent if t.get("status") == "open"]

            wins   = [t for t in closed if float(t.get("pnl") or 0) > 0]
            losses = [t for t in closed if float(t.get("pnl") or 0) <= 0]
            total_pnl = sum(float(t.get("pnl") or 0) for t in closed)
            win_rate  = round(len(wins) / len(closed) * 100, 1) if closed else 0

            # أفضل وأسوأ صفقة
            best_trade  = max(closed, key=lambda t: float(t.get("pnl") or 0), default=None) if closed else None
            worst_trade = min(closed, key=lambda t: float(t.get("pnl") or 0), default=None) if closed else None

            # توزيع الأصول
            symbols: dict[str, int] = {}
            for t in recent:
                sym = t.get("symbol", "UNKNOWN")
                symbols[sym] = symbols.get(sym, 0) + 1

            top_symbols = sorted(symbols.items(), key=lambda x: x[1], reverse=True)[:5]

            # التعلم من الخسائر
            loss_reasons = []
            for t in losses[:5]:
                reason = t.get("reason", t.get("ai_reason", ""))
                if reason:
                    loss_reasons.append(reason[:80])

            # الدروس المستفادة
            try:
                lessons = await self.db.get_lessons(limit=10)
                recent_lessons = [l.get("lesson", "") for l in lessons[:5]]
            except Exception:
                recent_lessons = []

            report = {
                "period_days":     period_days,
                "generated_at":    datetime.utcnow().isoformat(),
                "summary": {
                    "total_trades":  len(recent),
                    "closed_trades": len(closed),
                    "open_trades":   len(open_t),
                    "wins":          len(wins),
                    "losses":        len(losses),
                    "win_rate":      win_rate,
                    "total_pnl":     round(total_pnl, 4),
                },
                "best_trade": {
                    "symbol": best_trade.get("symbol") if best_trade else None,
                    "pnl":    round(float(best_trade.get("pnl") or 0), 4) if best_trade else None,
                } if best_trade else None,
                "worst_trade": {
                    "symbol": worst_trade.get("symbol") if worst_trade else None,
                    "pnl":    round(float(worst_trade.get("pnl") or 0), 4) if worst_trade else None,
                } if worst_trade else None,
                "top_symbols":     top_symbols,
                "loss_reasons":    loss_reasons,
                "recent_lessons":  recent_lessons,
                "health": self._assess_health(win_rate, total_pnl, len(closed)),
            }

            return report

        except Exception as e:
            return {"error": str(e), "period_days": period_days}

    def _assess_health(self, win_rate: float, total_pnl: float, n_trades: int) -> dict:
        """تقييم صحة الأداء."""
        if n_trades < 5:
            return {"status": "insufficient_data", "label": "بيانات غير كافية ⚪", "score": 50}

        score = 50
        score += (win_rate - 50) * 0.8
        if total_pnl > 0:
            score += min(20, total_pnl * 0.1)
        else:
            score += max(-20, total_pnl * 0.1)

        score = max(0, min(100, score))

        if score >= 75:
            label = "ممتاز 🟢"
            status = "excellent"
        elif score >= 60:
            label = "جيد 🟡"
            status = "good"
        elif score >= 45:
            label = "متوسط 🟠"
            status = "average"
        else:
            label = "ضعيف 🔴"
            status = "poor"

        return {"status": status, "label": label, "score": round(score, 1)}

    # ─────────────────────────────────────────────────────────────────────────
    # استدعاء الدروس الذكية
    # ─────────────────────────────────────────────────────────────────────────

    async def get_relevant_lessons(self, symbol: str, action: str) -> list[str]:
        """يجلب الدروس المناسبة لصفقة معينة."""
        try:
            lessons = await self.db.search_memory(f"{symbol} {action}")
            return [l.get("lesson", "") for l in lessons[:5] if l.get("lesson")]
        except Exception:
            return []

    async def get_rich_context(self, symbol: str = "", action: str = "") -> str:
        """يبني سياقاً غنياً من الذاكرة لدعم قرار AI."""
        try:
            from memory_engine import MemoryEngine
            me = MemoryEngine(self.db)
            return await me.get_rich_context(symbol=symbol)
        except Exception:
            return ""

    async def log_decision(self, source: str, decision: dict) -> None:
        """يسجل قرار AI في الجلسة."""
        self.session_log.append({
            "source":    source,
            "decision":  decision,
            "timestamp": time.time(),
        })
        if len(self.session_log) > 200:
            self.session_log = self.session_log[-200:]

    def get_session_log(self, limit: int = 20) -> list[dict]:
        return self.session_log[-limit:]

    def get_status(self) -> dict:
        return {
            "session_decisions": len(self.session_log),
            "excel_analyzed":    len(self.excel_cache),
            "last_excel":        self.excel_cache[-1]["filename"] if self.excel_cache else None,
            "active":            True,
        }
