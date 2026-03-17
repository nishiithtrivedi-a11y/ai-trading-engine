"""
Monte Carlo robustness analysis for backtesting results.

Provides three simulation modes to stress-test strategy robustness:
  1. **Trade reshuffle** — randomly reorder the sequence of closed trades
     and rebuild the equity curve. Tests whether performance depends on
     the specific ordering of wins/losses.
  2. **Return bootstrap** — sample trade returns with replacement to
     construct synthetic equity curves. Tests the distribution of
     possible outcomes.
  3. **Cost perturbation** — add random noise to fees/slippage and
     re-compute net PnL for each trade. Tests sensitivity to
     transaction cost assumptions.

All simulations are deterministic when a seed is supplied.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Optional

import numpy as np
import pandas as pd

from src.utils.logger import setup_logger

logger = setup_logger("monte_carlo")


# ---------------------------------------------------------------------------
# Enums and data classes
# ---------------------------------------------------------------------------

class SimulationMode(str, Enum):
    """Monte Carlo simulation mode."""
    TRADE_RESHUFFLE = "trade_reshuffle"
    RETURN_BOOTSTRAP = "return_bootstrap"
    COST_PERTURBATION = "cost_perturbation"


@dataclass
class MonteCarloRun:
    """One simulation run result."""
    run_index: int
    mode: str
    final_equity: float
    total_return_pct: float
    max_drawdown_pct: float
    sharpe_ratio: float
    num_trades: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_index": self.run_index,
            "mode": self.mode,
            "final_equity": self.final_equity,
            "total_return_pct": self.total_return_pct,
            "max_drawdown_pct": self.max_drawdown_pct,
            "sharpe_ratio": self.sharpe_ratio,
            "num_trades": self.num_trades,
        }


@dataclass
class MonteCarloResult:
    """Aggregated Monte Carlo simulation results."""
    mode: str
    num_simulations: int
    initial_capital: float
    runs: list[MonteCarloRun] = field(default_factory=list)
    percentiles: dict[str, dict[str, float]] = field(default_factory=dict)
    summary: dict[str, Any] = field(default_factory=dict)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert all runs to a DataFrame."""
        if not self.runs:
            return pd.DataFrame()
        return pd.DataFrame([r.to_dict() for r in self.runs])

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "num_simulations": self.num_simulations,
            "initial_capital": self.initial_capital,
            "percentiles": self.percentiles,
            "summary": self.summary,
            "runs": [r.to_dict() for r in self.runs],
        }


# ---------------------------------------------------------------------------
# MonteCarloAnalyzer
# ---------------------------------------------------------------------------

class MonteCarloAnalyzer:
    """Monte Carlo simulation engine for strategy robustness testing.

    Accepts a list of trade dicts (from backtest results) and an initial
    capital, then runs N simulations in the specified mode.

    Args:
        trades: List of trade dicts. Each must have at least ``net_pnl``
            and ``return_pct`` keys. Optionally ``fees`` for cost mode.
        initial_capital: Starting equity.
        num_simulations: Number of Monte Carlo iterations.
        seed: Random seed for reproducibility.
        output_dir: Where to save exports.

    Example::

        analyzer = MonteCarloAnalyzer(
            trades=trade_records,
            initial_capital=100_000,
            num_simulations=1000,
            seed=42,
        )
        result = analyzer.run(SimulationMode.TRADE_RESHUFFLE)
    """

    PERCENTILE_LEVELS = [5, 10, 25, 50, 75, 90, 95]

    def __init__(
        self,
        trades: list[dict[str, Any]],
        initial_capital: float = 100_000.0,
        num_simulations: int = 1000,
        seed: Optional[int] = None,
        output_dir: str = "output/monte_carlo",
    ) -> None:
        if initial_capital <= 0:
            raise ValueError("initial_capital must be > 0")
        if num_simulations < 1:
            raise ValueError("num_simulations must be >= 1")

        self.trades = trades
        self.initial_capital = initial_capital
        self.num_simulations = num_simulations
        self.seed = seed
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self._rng = np.random.default_rng(seed)
        self.result: Optional[MonteCarloResult] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, mode: SimulationMode = SimulationMode.TRADE_RESHUFFLE) -> MonteCarloResult:
        """Execute Monte Carlo simulation.

        Args:
            mode: Which simulation mode to use.

        Returns:
            MonteCarloResult with per-run and aggregate statistics.
        """
        if not self.trades:
            logger.warning("No trades provided — returning empty result")
            self.result = MonteCarloResult(
                mode=mode.value,
                num_simulations=0,
                initial_capital=self.initial_capital,
            )
            return self.result

        logger.info(
            f"Monte Carlo: {self.num_simulations} simulations, "
            f"mode={mode.value}, trades={len(self.trades)}"
        )

        runs: list[MonteCarloRun] = []

        for i in range(self.num_simulations):
            if mode == SimulationMode.TRADE_RESHUFFLE:
                run = self._reshuffle_run(i)
            elif mode == SimulationMode.RETURN_BOOTSTRAP:
                run = self._bootstrap_run(i)
            elif mode == SimulationMode.COST_PERTURBATION:
                run = self._cost_perturbation_run(i)
            else:
                raise ValueError(f"Unknown mode: {mode}")
            runs.append(run)

        self.result = MonteCarloResult(
            mode=mode.value,
            num_simulations=self.num_simulations,
            initial_capital=self.initial_capital,
            runs=runs,
        )

        # Compute percentiles and summary
        self.result.percentiles = self._compute_percentiles(runs)
        self.result.summary = self._compute_summary(runs)

        self._export_results()

        logger.info(
            f"Monte Carlo complete: "
            f"median final equity = {self.result.percentiles.get('final_equity', {}).get('p50', 'N/A')}"
        )

        return self.result

    def get_results(self) -> Optional[MonteCarloResult]:
        """Return the last simulation result."""
        return self.result

    # ------------------------------------------------------------------
    # Simulation modes
    # ------------------------------------------------------------------

    def _reshuffle_run(self, run_index: int) -> MonteCarloRun:
        """Randomly reorder trades and rebuild equity curve."""
        pnls = [t["net_pnl"] for t in self.trades]
        shuffled = self._rng.permutation(pnls)
        return self._build_run_from_pnls(run_index, shuffled, SimulationMode.TRADE_RESHUFFLE)

    def _bootstrap_run(self, run_index: int) -> MonteCarloRun:
        """Sample trades with replacement."""
        n = len(self.trades)
        indices = self._rng.integers(0, n, size=n)
        pnls = np.array([self.trades[i]["net_pnl"] for i in indices])
        return self._build_run_from_pnls(run_index, pnls, SimulationMode.RETURN_BOOTSTRAP)

    def _cost_perturbation_run(self, run_index: int) -> MonteCarloRun:
        """Add random noise to fees and recompute net PnL."""
        pnls = []
        for t in self.trades:
            original_fees = t.get("fees", 0.0)
            # Perturb fees by +/- 50% (uniform)
            noise_factor = 1.0 + self._rng.uniform(-0.5, 0.5)
            perturbed_fees = original_fees * noise_factor
            fee_delta = perturbed_fees - original_fees

            # Adjust net_pnl: more fees = less PnL
            adjusted_pnl = t["net_pnl"] - fee_delta
            pnls.append(adjusted_pnl)

        return self._build_run_from_pnls(
            run_index, np.array(pnls), SimulationMode.COST_PERTURBATION
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _build_run_from_pnls(
        self,
        run_index: int,
        pnls: np.ndarray,
        mode: SimulationMode,
    ) -> MonteCarloRun:
        """Build a MonteCarloRun from a sequence of PnLs."""
        equity = np.empty(len(pnls) + 1)
        equity[0] = self.initial_capital
        for i, pnl in enumerate(pnls):
            equity[i + 1] = equity[i] + pnl

        final_equity = float(equity[-1])
        total_return_pct = (final_equity - self.initial_capital) / self.initial_capital

        # Max drawdown
        peak = np.maximum.accumulate(equity)
        drawdown_pct = np.where(peak > 0, (peak - equity) / peak, 0.0)
        max_dd_pct = float(np.max(drawdown_pct))

        # Sharpe from equity-return series (explicit annualization order):
        # sharpe = sqrt(252) * (mean(return) / std(return))
        returns = pd.Series(equity, dtype=float).pct_change().dropna().to_numpy()
        if len(returns) > 1:
            ret_std = float(np.std(returns))
            ret_mean = float(np.mean(returns))
            if np.isfinite(ret_std) and ret_std > 0.0 and np.isfinite(ret_mean):
                sharpe = float((ret_mean / ret_std) * np.sqrt(252.0))
            else:
                sharpe = 0.0
        else:
            sharpe = 0.0

        return MonteCarloRun(
            run_index=run_index,
            mode=mode.value,
            final_equity=final_equity,
            total_return_pct=total_return_pct,
            max_drawdown_pct=max_dd_pct,
            sharpe_ratio=sharpe,
            num_trades=len(pnls),
        )

    def _compute_percentiles(self, runs: list[MonteCarloRun]) -> dict[str, dict[str, float]]:
        """Compute percentiles for key metrics across runs."""
        metrics_arrays: dict[str, list[float]] = {
            "final_equity": [r.final_equity for r in runs],
            "total_return_pct": [r.total_return_pct for r in runs],
            "max_drawdown_pct": [r.max_drawdown_pct for r in runs],
            "sharpe_ratio": [r.sharpe_ratio for r in runs],
        }

        percentiles: dict[str, dict[str, float]] = {}
        for metric_name, values in metrics_arrays.items():
            arr = np.array(values)
            pct_dict: dict[str, float] = {}
            for p in self.PERCENTILE_LEVELS:
                pct_dict[f"p{p}"] = float(np.percentile(arr, p))
            pct_dict["mean"] = float(np.mean(arr))
            pct_dict["std"] = float(np.std(arr))
            percentiles[metric_name] = pct_dict

        return percentiles

    def _compute_summary(self, runs: list[MonteCarloRun]) -> dict[str, Any]:
        """Compute high-level summary statistics."""
        finals = [r.final_equity for r in runs]
        returns = [r.total_return_pct for r in runs]

        profitable_runs = sum(1 for r in returns if r > 0)
        probability_of_profit = profitable_runs / len(runs) if runs else 0.0

        return {
            "num_simulations": len(runs),
            "probability_of_profit": probability_of_profit,
            "median_final_equity": float(np.median(finals)),
            "median_return_pct": float(np.median(returns)),
            "worst_case_final_equity": float(np.min(finals)),
            "best_case_final_equity": float(np.max(finals)),
            "worst_case_return_pct": float(np.min(returns)),
            "best_case_return_pct": float(np.max(returns)),
        }

    def _export_results(self) -> None:
        """Write results to CSV and JSON."""
        if self.result is None or not self.result.runs:
            return

        df = self.result.to_dataframe()
        csv_path = self.output_dir / "monte_carlo_results.csv"
        df.to_csv(csv_path, index=False)

        json_path = self.output_dir / "monte_carlo_results.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.result.to_dict(), f, indent=2, default=str)

        logger.info(f"Monte Carlo CSV saved to {csv_path}")
        logger.info(f"Monte Carlo JSON saved to {json_path}")
