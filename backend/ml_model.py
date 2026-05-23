"""
TradingMLModel — Real machine learning for trade signal filtering.

Algorithm: Gradient Boosting Classifier (sklearn)
  - Uses gradient descent on an ensemble of decision trees
  - Identical in principle to XGBoost / LightGBM
  - Handles small datasets well (works with as few as 10 samples)
  - Outputs calibrated win probabilities (0.0 – 1.0)

Features (9 inputs):
  [0] RSI(14)                  0–100
  [1] MACD histogram ×1000     scaled for tree splits
  [2] Bollinger %B             0–1
  [3] AI confidence            0–100
  [4] log(volume+1)            normalized volume
  [5] Price change % (15m)     momentum
  [6] Market condition         0=up 1=down 2=sideways 3=volatile
  [7] Side                     0=buy 1=sell
  [8] Hour of day (UTC)        0–23

Label: 1 = trade won (PNL > 0), 0 = trade lost
"""

import math
import os
import pickle
from datetime import datetime, timezone
from typing import Optional

MODEL_PATH = os.path.join(os.path.dirname(__file__), "ml_model.pkl")
STATS_PATH = os.path.join(os.path.dirname(__file__), "ml_stats.pkl")

MARKET_MAP = {
    "trending_up": 0,  "bullish": 0,
    "trending_down": 1, "bearish": 1,
    "sideways": 2,     "ranging": 2,  "neutral": 2,
    "volatile": 3,     "high_volatility": 3,
}

FEATURE_NAMES = [
    "RSI", "MACD_hist×1k", "BB_%B", "AI_conf",
    "log_volume", "price_chg%", "market_cond", "side", "hour_utc",
]

MIN_SAMPLES = 10     # minimum closed trades before ML kicks in
RETRAIN_EVERY = 5    # retrain after every N new closed trades


def _log_vol(v: float) -> float:
    return math.log1p(max(0.0, v))


def _market_code(mc: str) -> int:
    return MARKET_MAP.get(str(mc).lower().replace(" ", "_"), 2)


def _side_code(side: str) -> int:
    return 0 if str(side).lower() == "buy" else 1


class TradingMLModel:
    """
    Singleton ML model.  Call get_instance() everywhere to avoid
    loading the model from disk on every scan.
    """

    _instance: Optional["TradingMLModel"] = None

    @classmethod
    def get_instance(cls) -> "TradingMLModel":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ──────────────────────────────────────────────────────────────────────────

    def __init__(self) -> None:
        self._model = None
        self.is_trained = False
        self.n_samples = 0         # samples used in last training run
        self.n_features = 9
        self.feature_importances: list[tuple[str, float]] = []
        self._closed_since_last_train = 0  # counter for incremental retraining
        self._load()

    # ── Feature engineering ──────────────────────────────────────────────────

    def build_features_from_indicators(
        self,
        indicators: dict,
        side: str,
        ai_confidence: float,
    ) -> list[float]:
        """Used at inference time (before opening a new trade)."""
        return [
            float(indicators.get("rsi", 50)),
            float(indicators.get("macd_histogram", 0)) * 1000,
            float(indicators.get("bb_pct", 0.5)),
            float(ai_confidence),
            _log_vol(float(indicators.get("volume", 0))),
            float(indicators.get("price_change_pct", 0)),
            float(_market_code(indicators.get("market_condition", "sideways"))),
            float(_side_code(side)),
            float(datetime.now(timezone.utc).hour),
        ]

    def build_features_from_trade(self, trade: dict) -> Optional[list[float]]:
        """Used at training time (from stored trade columns)."""
        if trade.get("rsi_at_entry") is None:
            return None  # old trade without ML columns — skip
        return [
            float(trade.get("rsi_at_entry") or 50),
            float(trade.get("macd_hist_at_entry") or 0) * 1000,
            float(trade.get("bb_pct_at_entry") or 0.5),
            float(trade.get("ai_confidence") or 70),
            _log_vol(float(trade.get("volume_at_entry") or 0)),
            float(trade.get("price_chg_pct_at_entry") or 0),
            float(_market_code(trade.get("market_condition", "sideways"))),
            float(_side_code(trade.get("side", "buy"))),
            float(trade.get("entry_hour_utc") or 12),
        ]

    # ── Training ─────────────────────────────────────────────────────────────

    def train(self, closed_trades: list[dict]) -> bool:
        """
        Train on all closed trades that have ML feature columns saved.
        Returns True if training succeeded.
        """
        from sklearn.ensemble import GradientBoostingClassifier
        from sklearn.preprocessing import StandardScaler
        import numpy as np

        samples = []
        labels = []

        for t in closed_trades:
            feats = self.build_features_from_trade(t)
            if feats is None:
                continue
            pnl = float(t.get("pnl") or 0)
            labels.append(1 if pnl > 0 else 0)
            samples.append(feats)

        if len(samples) < MIN_SAMPLES:
            print(f"[ML] Not enough samples yet ({len(samples)}/{MIN_SAMPLES}) — skipping training")
            return False

        X = np.array(samples, dtype=float)
        y = np.array(labels, dtype=int)

        # Gradient Boosting — real gradient descent on decision trees
        model = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.05,
            max_depth=3,
            subsample=0.8,
            min_samples_leaf=2,
            random_state=42,
        )
        model.fit(X, y)

        self._model = model
        self.is_trained = True
        self.n_samples = len(samples)
        self._closed_since_last_train = 0

        # Feature importances
        importances = model.feature_importances_
        self.feature_importances = sorted(
            zip(FEATURE_NAMES, importances.tolist()),
            key=lambda x: x[1],
            reverse=True,
        )

        win_count = int(y.sum())
        print(
            f"[ML] ✅ GradientBoosting trained: {len(samples)} samples "
            f"({win_count} wins / {len(samples)-win_count} losses) | "
            f"top feature: {self.feature_importances[0][0] if self.feature_importances else '?'}"
        )

        self._save()
        return True

    def should_retrain(self) -> bool:
        """Returns True when enough new closed trades have accumulated."""
        self._closed_since_last_train += 1
        return self._closed_since_last_train >= RETRAIN_EVERY

    # ── Inference ────────────────────────────────────────────────────────────

    def predict_win_prob(
        self,
        indicators: dict,
        side: str,
        ai_confidence: float,
    ) -> Optional[float]:
        """
        Returns predicted win probability [0.0, 1.0] or None if model
        is not trained yet.
        """
        if not self.is_trained or self._model is None:
            return None

        import numpy as np
        feats = self.build_features_from_indicators(indicators, side, ai_confidence)
        X = np.array([feats], dtype=float)
        prob = float(self._model.predict_proba(X)[0][1])
        return round(prob, 4)

    def adjusted_confidence(
        self,
        gemini_conf: float,
        ml_prob: Optional[float],
        weight: float = 0.4,
    ) -> float:
        """
        Blend Gemini confidence with ML win probability.
        weight=0.4 means ML contributes 40%, Gemini contributes 60%.
        As n_samples grows, ML weight increases (max 0.6).
        """
        if ml_prob is None:
            return gemini_conf
        dynamic_weight = min(0.6, weight + (self.n_samples - MIN_SAMPLES) * 0.005)
        ml_score = ml_prob * 100
        blended = gemini_conf * (1 - dynamic_weight) + ml_score * dynamic_weight
        return round(blended, 1)

    # ── Persistence ──────────────────────────────────────────────────────────

    def _save(self) -> None:
        try:
            with open(MODEL_PATH, "wb") as f:
                pickle.dump(self._model, f)
            with open(STATS_PATH, "wb") as f:
                pickle.dump({
                    "n_samples": self.n_samples,
                    "feature_importances": self.feature_importances,
                    "is_trained": self.is_trained,
                }, f)
            print(f"[ML] Model saved → {MODEL_PATH}")
        except Exception as e:
            print(f"[ML] Save error: {e}")

    def _load(self) -> None:
        try:
            if os.path.exists(MODEL_PATH):
                with open(MODEL_PATH, "rb") as f:
                    self._model = pickle.load(f)
                self.is_trained = True
            if os.path.exists(STATS_PATH):
                with open(STATS_PATH, "rb") as f:
                    stats = pickle.load(f)
                self.n_samples = stats.get("n_samples", 0)
                self.feature_importances = stats.get("feature_importances", [])
            if self.is_trained:
                print(f"[ML] Model loaded from disk — {self.n_samples} samples")
        except Exception as e:
            print(f"[ML] Load error (starting fresh): {e}")
            self.is_trained = False
            self._model = None

    # ── Status report ────────────────────────────────────────────────────────

    def status_dict(self) -> dict:
        return {
            "is_trained": self.is_trained,
            "n_samples": self.n_samples,
            "min_samples_needed": MIN_SAMPLES,
            "samples_until_first_train": max(0, MIN_SAMPLES - self.n_samples),
            "feature_importances": self.feature_importances[:5],
            "algorithm": "GradientBoostingClassifier",
        }
