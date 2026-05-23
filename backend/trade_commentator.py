"""
Trade Commentator — يولّد تعليقاً صوتياً بالعربية لكل صفقة تُفتح أو تُغلق
ويحفظه تلقائياً في جدول conversations (screen=brain, type=trade_auto)
"""

import asyncio
import time
from typing import Any, Optional

_LAST_COMMENT_TIME: float = 0.0
_MIN_INTERVAL = 8.0  # لا تزيد على تعليق كل 8 ثوانٍ


OPEN_PROMPT = """\
أنت عقل روبوت التداول الإسلامي — تتحدث بضمير المتكلم مع صاحبك مباشرة.

فتحتَ للتوّ صفقة شراء جديدة. اشرح قرارك في 3-4 جمل بالعربية فقط:
• لماذا اخترتَ هذه العملة الآن؟
• ما المؤشرات التقنية التي رجّحت القرار؟
• أين السعر المستهدف ومتى تتوقع الوصول؟
• ما مستوى ثقتك وسبب ذلك؟

كن صريحاً ومختصراً — لا مقدمات، ابدأ مباشرةً بالتحليل.
لا تذكر كلمة "أفهم" أو "بالطبع" أو "شكراً".

بيانات الصفقة:
{trade_context}
"""

CLOSE_WIN_PROMPT = """\
أنت عقل روبوت التداول الإسلامي — تتحدث بضمير المتكلم مع صاحبك مباشرة.

أغلقتَ للتوّ صفقة رابحة. علّق عليها في 3-4 جمل بالعربية:
• ما الذي سار بشكل صحيح في هذه الصفقة؟
• ما الدرس المستفاد لتكرار هذا النجاح؟
• كيف ستوظّف هذا الربح في الاستراتيجية القادمة؟

ابدأ بكلمة إيجابية مقتضبة ثم التحليل مباشرة.

بيانات الصفقة:
{trade_context}
"""

CLOSE_LOSS_PROMPT = """\
أنت عقل روبوت التداول الإسلامي — تتحدث بضمير المتكلم مع صاحبك مباشرة.

أُغلقت للتوّ صفقة خاسرة (Stop Loss). اشرح ما حدث في 3-4 جمل بالعربية:
• ما الذي لم يسر كما توقعت؟
• هل هناك علامات حذّر منها السوق أغفلتَها؟
• ماذا ستغيّر في قراراتك القادمة بناءً على هذه الخسارة؟

كن صادقاً وموضوعياً — الخسارة جزء من التداول الحلال المنضبط.

بيانات الصفقة:
{trade_context}
"""


def _build_trade_context(trade: dict, current_price: Optional[float] = None) -> str:
    sym     = trade.get("symbol", "?")
    side    = trade.get("side", "buy")
    entry   = float(trade.get("entry_price") or 0)
    sl      = float(trade.get("stop_loss_price") or 0)
    tp      = float(trade.get("take_profit_price") or 0)
    conf    = trade.get("ai_confidence", 0)
    reason  = str(trade.get("ai_reasoning") or "").strip()[:200]
    pattern = trade.get("pattern", "")
    cond    = trade.get("market_condition", "")
    pnl     = trade.get("pnl")
    exit_p  = trade.get("exit_price") or current_price

    rsi     = trade.get("rsi_at_entry")
    macd    = trade.get("macd_hist_at_entry")
    bb_pct  = trade.get("bb_pct_at_entry")

    lines = [
        f"العملة: {sym} | الاتجاه: {'شراء' if side=='buy' else 'بيع'}",
        f"سعر الدخول: ${entry:.4f}" + (f" | سعر الخروج: ${float(exit_p):.4f}" if exit_p else ""),
        f"Stop Loss: ${sl:.4f} | Take Profit: ${tp:.4f}",
        f"ثقة AI: {conf}% | النمط: {pattern or '—'} | حالة السوق: {cond or '—'}",
    ]
    if rsi is not None:   lines.append(f"RSI: {rsi:.1f}")
    if macd is not None:  lines.append(f"MACD Histogram: {macd:.6f}")
    if bb_pct is not None: lines.append(f"Bollinger %B: {bb_pct:.2f}")
    if pnl is not None:   lines.append(f"PnL: ${float(pnl):+.4f} USDT")
    if reason:            lines.append(f"تحليل AI: {reason}")
    return "\n".join(lines)


def _rule_based_comment(trade: dict, event: str) -> str:
    sym  = trade.get("symbol", "?").replace("/USDT", "")
    conf = trade.get("ai_confidence", 0)
    pnl  = trade.get("pnl")
    sl   = float(trade.get("stop_loss_price") or 0)
    tp   = float(trade.get("take_profit_price") or 0)

    if event == "open":
        return (
            f"📊 فتحتُ صفقة شراء على {sym} بثقة {conf}%.\n"
            f"• Stop Loss: ${sl:.4f} | Take Profit: ${tp:.4f}\n"
            f"• المؤشرات تدعم دخولاً بالاتجاه الحالي.\n"
            f"أراقب السعر بانتظام وسأُبلّغك عند أي تغيير."
        )
    elif event == "close_win":
        return (
            f"✅ أغلقتُ {sym} برباح ${float(pnl):+.4f}!\n"
            f"• النمط نجح — سأحتفظ بهذا التوقيت في ذاكرتي.\n"
            f"• الاستراتيجية الحالية تعمل بشكل جيد."
        )
    else:
        return (
            f"🔴 وصل {sym} إلى Stop Loss — خسارة ${float(pnl or 0):+.4f}.\n"
            f"• حجم الخسارة ضمن إدارة المخاطر المحددة.\n"
            f"• سأراجع المؤشرات وأتعلم من هذا القرار."
        )


async def generate_trade_comment(
    db: Any,
    trade: dict,
    event: str,  # "open" | "close_win" | "close_loss"
    current_price: Optional[float] = None,
) -> None:
    """
    يولّد تعليقاً AI على الصفقة ويحفظه مباشرةً في جدول conversations.
    يعمل بشكل غير متزامن (fire-and-forget) ولا يُبطّئ حلقة التداول.
    """
    global _LAST_COMMENT_TIME

    # Rate-limit: لا تزيد على تعليق كل 8 ثوانٍ
    now = time.time()
    if now - _LAST_COMMENT_TIME < _MIN_INTERVAL:
        return
    _LAST_COMMENT_TIME = now

    trade_ctx = _build_trade_context(trade, current_price)

    if event == "open":
        prompt = OPEN_PROMPT.format(trade_context=trade_ctx)
        icon   = "📊"
        label  = "تحليل الدخول"
    elif event == "close_win":
        prompt = CLOSE_WIN_PROMPT.format(trade_context=trade_ctx)
        icon   = "✅"
        label  = "تقرير ربح"
    else:
        prompt = CLOSE_LOSS_PROMPT.format(trade_context=trade_ctx)
        icon   = "🔴"
        label  = "تحليل الخسارة"

    sym = trade.get("symbol", "?").replace("/USDT", "")

    try:
        from ai_agent import AIAgent
        agent = AIAgent.get_instance()
        slot  = agent._get_slot()

        if slot:
            try:
                text = slot.call(
                    "أنت عقل روبوت التداول — تحليل مختصر بالعربية فقط.",
                    prompt,
                    temperature=0.7,
                )
                slot.success_calls += 1
            except Exception as e:
                slot.failed_calls += 1
                err = str(e).lower()
                if any(x in err for x in ["429", "quota", "rate", "exhausted"]):
                    slot.mark_exhausted(180)
                text = _rule_based_comment(trade, event)
        else:
            text = _rule_based_comment(trade, event)

        header = f"{icon} **{label} — {sym}**\n\n"
        full_text = header + text.strip()

        await db.save_message(
            role="assistant",
            content=full_text,
            screen="brain",
            provider=slot.provider if slot else "rule-based",
            session_id="auto",
            metadata={
                "type":   "trade_auto",
                "event":  event,
                "symbol": trade.get("symbol", ""),
                "pnl":    float(trade.get("pnl") or 0) if trade.get("pnl") is not None else None,
            },
        )
        print(f"[Commentator] {icon} {sym} {event} comment saved ✅")

    except Exception as e:
        print(f"[Commentator] Error generating comment: {e}")


def fire_trade_comment(db: Any, trade: dict, event: str, current_price: Optional[float] = None) -> None:
    """
    Fire-and-forget wrapper — يُطلق التعليق في الخلفية بدون انتظار.
    استخدمه من أي مكان غير async.
    """
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(generate_trade_comment(db, trade, event, current_price))
        else:
            loop.run_until_complete(generate_trade_comment(db, trade, event, current_price))
    except Exception as e:
        print(f"[Commentator] fire error: {e}")
