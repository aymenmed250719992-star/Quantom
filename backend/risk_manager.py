import os

from dotenv import load_dotenv

load_dotenv()


class RiskManager:
    def __init__(self):
        self.max_risk_percent = float(os.environ.get("MAX_RISK_PERCENT", 1.5))
        if self.max_risk_percent > 3.0:
            self.max_risk_percent = 3.0
            print("WARNING: MAX_RISK_PERCENT capped at 3.0% for safety")

    def calculate_position_size(
        self,
        total_balance: float,
        entry_price: float,
        stop_loss_percent: float,
    ) -> float:
        """Calculate safe position size based on risk per trade.

        Uses the formula: quantity = (balance * risk%) / (entry * sl%)
        Caps position at 50% of balance as additional safety measure.
        """
        if total_balance <= 0 or entry_price <= 0 or stop_loss_percent <= 0:
            return 0.0

        max_risk_amount = total_balance * (self.max_risk_percent / 100)
        stop_loss_distance = entry_price * (stop_loss_percent / 100)
        quantity = max_risk_amount / stop_loss_distance

        max_position_value = total_balance * 0.5
        max_quantity = max_position_value / entry_price
        quantity = min(quantity, max_quantity)

        return round(quantity, 6)

    def calculate_stop_loss_price(
        self,
        entry_price: float,
        side: str,
        stop_loss_percent: float,
    ) -> float:
        if side == "buy":
            return round(entry_price * (1 - stop_loss_percent / 100), 4)
        return round(entry_price * (1 + stop_loss_percent / 100), 4)

    def calculate_take_profit_price(
        self,
        entry_price: float,
        side: str,
        take_profit_percent: float,
    ) -> float:
        if side == "buy":
            return round(entry_price * (1 + take_profit_percent / 100), 4)
        return round(entry_price * (1 - take_profit_percent / 100), 4)

    def validate_risk(self, position_value: float, total_balance: float) -> bool:
        if total_balance <= 0:
            return False
        risk_pct = (position_value / total_balance) * 100
        return risk_pct <= (self.max_risk_percent * 33)

    def estimate_pnl(
        self,
        side: str,
        entry_price: float,
        exit_price: float,
        quantity: float,
    ) -> float:
        if side == "buy":
            return round((exit_price - entry_price) * quantity, 4)
        return round((entry_price - exit_price) * quantity, 4)
