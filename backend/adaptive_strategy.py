"""
Adaptive Strategy Engine — adjusts the bot's confidence threshold
dynamically to achieve the user's target win rate.
"""

import os
from typing import Any


class AdaptiveStrategy:
    def __init__(self, db: Any):
        self.db = db
        self.min_threshold = 60
        self.max_threshold = 90
        self.review_every_n_trades = 5

    async def maybe_adjust(
        self,
        current_threshold: int,
        target_win_rate: float,
        broadcast_fn=None,
    ) -> int:
        """
        Review last N closed trades and adjust confidence threshold
        to bring actual win rate closer to the target.
        Returns new threshold.
        """
        trades = await self.db.get_trades(limit=50)
        closed = [t for t in trades if t.get("status") == "closed"]

        if len(closed) < self.review_every_n_trades:
            return current_threshold

        # Only adjust every N trades
        if len(closed) % self.review_every_n_trades != 0:
            return current_threshold

        # Use last 20 trades for the evaluation window
        recent = closed[:20]
        wins = sum(1 for t in recent if (t.get("pnl") or 0) > 0)
        actual_win_rate = (wins / len(recent)) * 100 if recent else 0

        new_threshold = current_threshold
        adjustment_msg = ""

        if actual_win_rate < target_win_rate - 5:
            # Performing below target → be more selective
            increase = min(5, int((target_win_rate - actual_win_rate) / 3))
            new_threshold = min(self.max_threshold, current_threshold + increase)
            adjustment_msg = (
                f"⚡ Adaptive Engine: Win rate {actual_win_rate:.1f}% < target "
                f"{target_win_rate:.1f}% → Raising confidence threshold "
                f"{current_threshold}% → {new_threshold}% (more selective)"
            )
        elif actual_win_rate > target_win_rate + 12:
            # Performing well above target → can be slightly less selective for more trades
            new_threshold = max(self.min_threshold, current_threshold - 2)
            adjustment_msg = (
                f"✅ Adaptive Engine: Win rate {actual_win_rate:.1f}% > target "
                f"{target_win_rate:.1f}% → Lowering threshold "
                f"{current_threshold}% → {new_threshold}% (slightly more trades)"
            )
        else:
            adjustment_msg = (
                f"🎯 Adaptive Engine: Win rate {actual_win_rate:.1f}% on track "
                f"(target: {target_win_rate:.1f}%) — threshold stays at {current_threshold}%"
            )

        if broadcast_fn and adjustment_msg:
            import json
            await broadcast_fn(json.dumps({"type": "adaptive", "message": adjustment_msg}))

        # Update env so new Gemini instances pick it up
        os.environ["MIN_CONFIDENCE_SCORE"] = str(new_threshold)
        return new_threshold

    async def get_performance_report(self, target_win_rate: float) -> dict:
        """Generate a performance report vs the target win rate."""
        trades = await self.db.get_trades(limit=100)
        all_closed = [t for t in trades if t.get("status") == "closed"]
        open_trades = [t for t in trades if t.get("status") == "open"]

        if not all_closed:
            return {
                "total_closed": 0,
                "wins": 0,
                "losses": 0,
                "actual_win_rate": 0.0,
                "target_win_rate": target_win_rate,
                "on_target": False,
                "total_pnl": 0.0,
                "best_trade": None,
                "worst_trade": None,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "profit_factor": 0.0,
                "open_count": len(open_trades),
            }

        wins = [t for t in all_closed if (t.get("pnl") or 0) > 0]
        losses = [t for t in all_closed if (t.get("pnl") or 0) <= 0]
        total_pnl = sum(float(t.get("pnl") or 0) for t in all_closed)

        win_pnl = sum(float(t.get("pnl") or 0) for t in wins)
        loss_pnl = abs(sum(float(t.get("pnl") or 0) for t in losses))

        profit_factor = win_pnl / loss_pnl if loss_pnl > 0 else (float("inf") if win_pnl > 0 else 0.0)

        best = max(all_closed, key=lambda t: float(t.get("pnl") or 0), default=None)
        worst = min(all_closed, key=lambda t: float(t.get("pnl") or 0), default=None)

        actual_win_rate = (len(wins) / len(all_closed)) * 100

        return {
            "total_closed": len(all_closed),
            "wins": len(wins),
            "losses": len(losses),
            "actual_win_rate": round(actual_win_rate, 2),
            "target_win_rate": target_win_rate,
            "on_target": actual_win_rate >= target_win_rate,
            "total_pnl": round(total_pnl, 4),
            "best_trade": {
                "symbol": best.get("symbol"),
                "pnl": round(float(best.get("pnl") or 0), 4),
            } if best else None,
            "worst_trade": {
                "symbol": worst.get("symbol"),
                "pnl": round(float(worst.get("pnl") or 0), 4),
            } if worst else None,
            "avg_win": round(win_pnl / len(wins), 4) if wins else 0.0,
            "avg_loss": round(loss_pnl / len(losses), 4) if losses else 0.0,
            "profit_factor": round(profit_factor, 2),
            "open_count": len(open_trades),
        }
