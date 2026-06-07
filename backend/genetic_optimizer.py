"""
GeneticOptimizer — خوارزمية تطور ذاتي لتحسين معاملات الاستراتيجية  (T002)

تُطوّر تلقائياً:
  • عتبة الثقة الدنيا (min_confidence: 50–85)
  • حدود RSI للشراء/البيع (rsi_buy: 20–45 | rsi_sell: 55–80)
  • نسبة SL% (0.5–3.0) و TP% (1.0–8.0)
  • وزن إشارة CrowdSim (0.0–1.0)
  • متطلب تقاطع الإطارات الزمنية (1–4)

خوارزمية: (μ + λ) Evolution Strategy
  • جيل واحد = تقييم fitness كل فرد على آخر N صفقة
  • Fitness = win_rate × 2 + avg_pnl × 10 − max_drawdown × 5
  • Elitism: أفضل 20% ينجون تلقائياً
  • Mutation: Gaussian noise على كل جين
  • Crossover: uniform crossover بين الوالدين

يعمل في background thread لا يُعطّل event loop.
"""

import asyncio
import copy
import math
import os
import pickle
import random
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

GENOME_PATH = os.path.join(os.path.dirname(__file__), ".best_genome.pkl")

# ── الجينوم ───────────────────────────────────────────────────────────────────

@dataclass
class StrategyGenome:
    """معاملات استراتيجية قابلة للتطوير."""
    min_confidence:   float = 60.0    # 50–85
    rsi_buy_max:      float = 40.0    # 20–50   (شراء تحت هذا الحد)
    rsi_sell_min:     float = 60.0    # 55–80   (بيع فوق هذا الحد)
    sl_pct:           float = 1.5     # 0.5–3.0
    tp_pct:           float = 3.0     # 1.0–8.0
    crowd_weight:     float = 0.3     # 0.0–1.0
    tf_confluence:    int   = 2       # 1–4
    macd_threshold:   float = 0.0     # MACD histogram min
    bb_pct_buy_max:   float = 0.35    # BB %B ≤ this for buy signal
    bb_pct_sell_min:  float = 0.65    # BB %B ≥ this for sell signal

    # Fitness (لا تُطوَّر — نتيجة التقييم فقط)
    fitness:          float = 0.0
    generation:       int   = 0
    evaluated_at:     float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def random(cls) -> "StrategyGenome":
        return cls(
            min_confidence  = random.uniform(50, 80),
            rsi_buy_max     = random.uniform(25, 45),
            rsi_sell_min    = random.uniform(55, 75),
            sl_pct          = random.uniform(0.5, 2.5),
            tp_pct          = random.uniform(1.5, 7.0),
            crowd_weight    = random.uniform(0.0, 0.8),
            tf_confluence   = random.randint(1, 4),
            macd_threshold  = random.uniform(-0.001, 0.001),
            bb_pct_buy_max  = random.uniform(0.20, 0.45),
            bb_pct_sell_min = random.uniform(0.55, 0.80),
        )

    @classmethod
    def default(cls) -> "StrategyGenome":
        return cls()


# ── Fitness Evaluator ─────────────────────────────────────────────────────────

def _evaluate_genome(genome: StrategyGenome, closed_trades: list[dict]) -> float:
    """
    Simulate genome parameters on historical closed trades.
    Returns fitness score (higher = better).
    """
    if len(closed_trades) < 5:
        return 0.0

    wins, losses = 0, 0
    pnls: list[float] = []
    peak = 0.0
    equity = 1000.0
    max_dd = 0.0

    for trade in closed_trades[-100:]:   # last 100 trades for speed
        rsi   = float(trade.get("rsi_at_entry") or 50)
        pnl   = float(trade.get("pnl") or 0)
        conf  = float(trade.get("ai_confidence") or 60)
        side  = trade.get("side", "buy")

        # Apply genome filters
        if conf < genome.min_confidence:
            continue   # would have skipped this trade
        if side == "buy" and rsi > genome.rsi_buy_max:
            continue
        if side == "sell" and rsi < genome.rsi_sell_min:
            continue

        # Simulate adjusted PnL with genome SL/TP
        entry = float(trade.get("entry_price") or 1)
        exit_ = float(trade.get("exit_price") or entry)
        actual_pct = (exit_ - entry) / entry * 100 if side == "buy" else (entry - exit_) / entry * 100

        # Clamp to genome SL/TP
        simulated_pct = max(-genome.sl_pct, min(genome.tp_pct, actual_pct))
        sim_pnl = simulated_pct / 100 * entry * float(trade.get("quantity") or 0.01)

        equity += sim_pnl
        pnls.append(sim_pnl)
        if sim_pnl > 0:
            wins += 1
        else:
            losses += 1

        if equity > peak:
            peak = equity
        dd = (peak - equity) / peak if peak > 0 else 0
        max_dd = max(max_dd, dd)

    total = wins + losses
    if total == 0:
        return 0.0

    win_rate = wins / total
    avg_pnl  = sum(pnls) / len(pnls) if pnls else 0

    # Sharpe approximation
    std = math.sqrt(sum((p - avg_pnl) ** 2 for p in pnls) / len(pnls)) if len(pnls) > 1 else 1
    sharpe = (avg_pnl / std) if std > 0 else 0

    fitness = (
        win_rate  * 40.0
        + avg_pnl * 20.0
        + sharpe  * 10.0
        - max_dd  * 30.0
        + math.log1p(total) * 2.0   # prefer genomes that take more trades (more data)
    )
    return round(fitness, 4)


# ── Evolution Engine ──────────────────────────────────────────────────────────

def _mutate(genome: StrategyGenome, strength: float = 0.15) -> StrategyGenome:
    g = copy.deepcopy(genome)
    g.min_confidence  = max(50, min(85, g.min_confidence  + random.gauss(0, strength * 10)))
    g.rsi_buy_max     = max(20, min(50, g.rsi_buy_max     + random.gauss(0, strength * 8)))
    g.rsi_sell_min    = max(50, min(80, g.rsi_sell_min    + random.gauss(0, strength * 8)))
    g.sl_pct          = max(0.5, min(3.0, g.sl_pct        + random.gauss(0, strength * 0.5)))
    g.tp_pct          = max(1.0, min(8.0, g.tp_pct        + random.gauss(0, strength * 1.0)))
    g.crowd_weight    = max(0.0, min(1.0, g.crowd_weight  + random.gauss(0, strength * 0.2)))
    g.tf_confluence   = max(1, min(4, g.tf_confluence + random.choice([-1, 0, 0, 1])))
    g.bb_pct_buy_max  = max(0.15, min(0.50, g.bb_pct_buy_max  + random.gauss(0, strength * 0.05)))
    g.bb_pct_sell_min = max(0.50, min(0.85, g.bb_pct_sell_min + random.gauss(0, strength * 0.05)))
    return g


def _crossover(a: StrategyGenome, b: StrategyGenome) -> StrategyGenome:
    child = copy.deepcopy(a)
    fields = [f for f in StrategyGenome.__dataclass_fields__ if f not in ("fitness", "generation", "evaluated_at")]
    for f in fields:
        if random.random() < 0.5:
            setattr(child, f, getattr(b, f))
    return child


def run_generation(
    population: list[StrategyGenome],
    closed_trades: list[dict],
    pop_size: int = 30,
    elite_frac: float = 0.2,
) -> list[StrategyGenome]:
    """Run one generation of evolution. CPU-bound — call via asyncio.to_thread."""

    # 1. Evaluate fitness
    for g in population:
        g.fitness = _evaluate_genome(g, closed_trades)

    # 2. Sort by fitness
    population.sort(key=lambda g: g.fitness, reverse=True)

    # 3. Elitism — keep top 20%
    n_elite = max(2, int(pop_size * elite_frac))
    elite   = population[:n_elite]

    # 4. Generate offspring
    offspring: list[StrategyGenome] = list(elite)
    while len(offspring) < pop_size:
        if random.random() < 0.7 and len(elite) >= 2:
            a, b = random.sample(elite, 2)
            child = _crossover(a, b)
        else:
            child = copy.deepcopy(random.choice(elite))
        child = _mutate(child)
        child.generation = elite[0].generation + 1 if elite else 1
        child.fitness = 0.0
        offspring.append(child)

    return offspring[:pop_size]


# ── GeneticOptimizer Singleton ────────────────────────────────────────────────

class GeneticOptimizer:

    _instance: Optional["GeneticOptimizer"] = None

    POPULATION_SIZE = 30
    GENERATIONS_PER_RUN = 10
    MIN_TRADES_REQUIRED = 20
    RUN_INTERVAL_HOURS = 24.0

    @classmethod
    def get_instance(cls) -> "GeneticOptimizer":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self) -> None:
        self._population: list[StrategyGenome] = [StrategyGenome.random() for _ in range(self.POPULATION_SIZE)]
        self._best: StrategyGenome = StrategyGenome.default()
        self._last_run: float = 0.0
        self._generation: int = 0
        self._running: bool = False
        self._load_best()
        print(f"[GA] GeneticOptimizer ready — best fitness: {self._best.fitness:.3f}")

    def get_best_genome(self) -> StrategyGenome:
        return self._best

    def should_run(self) -> bool:
        return (time.time() - self._last_run) > (self.RUN_INTERVAL_HOURS * 3600)

    async def maybe_evolve(self, closed_trades: list[dict]) -> Optional[StrategyGenome]:
        """Run evolution if conditions are met. Non-blocking."""
        if self._running:
            return None
        if len(closed_trades) < self.MIN_TRADES_REQUIRED:
            return None
        if not self.should_run():
            return None

        self._running = True
        try:
            best = await asyncio.to_thread(self._evolve_sync, closed_trades)
            return best
        finally:
            self._running = False
            self._last_run = time.time()

    def _evolve_sync(self, closed_trades: list[dict]) -> StrategyGenome:
        """Synchronous evolution loop — runs in thread."""
        pop = list(self._population)

        for gen_idx in range(self.GENERATIONS_PER_RUN):
            pop = run_generation(pop, closed_trades, self.POPULATION_SIZE)
            best_in_gen = pop[0]
            self._generation = gen_idx + 1
            print(f"[GA] Gen {self._generation} | best fitness: {best_in_gen.fitness:.3f} | "
                  f"conf≥{best_in_gen.min_confidence:.0f} SL={best_in_gen.sl_pct:.1f}% TP={best_in_gen.tp_pct:.1f}%")

        self._population = pop
        candidate = pop[0]

        if candidate.fitness > self._best.fitness:
            print(f"[GA] 🏆 New best genome! fitness {self._best.fitness:.3f} → {candidate.fitness:.3f}")
            self._best = candidate
            self._save_best()

        return self._best

    def _save_best(self) -> None:
        try:
            with open(GENOME_PATH, "wb") as f:
                pickle.dump(self._best, f)
        except Exception as e:
            print(f"[GA] Save error: {e}")

    def _load_best(self) -> None:
        try:
            if os.path.exists(GENOME_PATH):
                with open(GENOME_PATH, "rb") as f:
                    self._best = pickle.load(f)
                print(f"[GA] Loaded best genome — fitness: {self._best.fitness:.3f}")
        except Exception as e:
            print(f"[GA] Load error: {e}")

    def status(self) -> dict:
        return {
            "generation":       self._generation,
            "population_size":  len(self._population),
            "last_run":         self._last_run,
            "is_running":       self._running,
            "best_fitness":     self._best.fitness,
            "best_genome":      self._best.to_dict(),
            "next_run_in_hours": max(0, self.RUN_INTERVAL_HOURS - (time.time() - self._last_run) / 3600),
        }
