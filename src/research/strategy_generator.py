"""
Template-based strategy generation and ranking engine.

Generates strategy configurations by combining existing strategy classes
with parameter grids, backtests them, and ranks the results. This is a
deterministic, local-first system — no LLM dependency.

Architecture:
  - **StrategyTemplate**: Binds a strategy class to a parameter grid
    and a human-readable description.
  - **StrategyGenerator**: Produces all candidate configurations from
    a set of templates.
  - **StrategyRanker**: Backtests candidates and ranks them by a
    configurable metric (default: Sharpe ratio).

Designed for extensibility: add new templates by defining a
StrategyTemplate and registering it with the generator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.strategies.base_strategy import BaseStrategy
from src.utils.config import BacktestConfig
from src.utils.logger import setup_logger

logger = setup_logger("strategy_generator")


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class StrategyTemplate:
    """Defines a strategy class + parameter grid combination.

    Attributes:
        strategy_class: The strategy class to instantiate.
        param_grid: Dict of param_name → list of values.
        description: Human-readable description.
        tags: Category tags (e.g., ["trend", "momentum"]).
    """
    strategy_class: type[BaseStrategy]
    param_grid: dict[str, list[Any]]
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @property
    def name(self) -> str:
        return self.strategy_class.__name__

    def num_combinations(self) -> int:
        """Total parameter combinations in this template."""
        count = 1
        for values in self.param_grid.values():
            count *= len(values)
        return count


@dataclass
class RankedStrategy:
    """One backtested strategy with its ranking score."""
    rank: int
    strategy_name: str
    params: dict[str, Any]
    metrics: dict[str, Any]
    description: str = ""
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        row: dict[str, Any] = {
            "rank": self.rank,
            "strategy_name": self.strategy_name,
            "description": self.description,
            "tags": ",".join(self.tags),
        }
        for k, v in self.params.items():
            row[f"param_{k}"] = v
        row.update(self.metrics)
        return row


@dataclass
class GeneratorResult:
    """Complete results from strategy generation and ranking."""
    ranked_strategies: list[RankedStrategy] = field(default_factory=list)
    total_candidates: int = 0
    total_successful: int = 0
    rank_metric: str = "sharpe_ratio"

    def to_dataframe(self) -> pd.DataFrame:
        if not self.ranked_strategies:
            return pd.DataFrame()
        return pd.DataFrame([s.to_dict() for s in self.ranked_strategies])

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_candidates": self.total_candidates,
            "total_successful": self.total_successful,
            "rank_metric": self.rank_metric,
            "strategies": [s.to_dict() for s in self.ranked_strategies],
        }

    def get_top(self, n: int = 5) -> list[RankedStrategy]:
        """Return top N ranked strategies."""
        return self.ranked_strategies[:n]


# ---------------------------------------------------------------------------
# StrategyGenerator
# ---------------------------------------------------------------------------

class StrategyGenerator:
    """Generates strategy candidates from templates.

    Takes a list of StrategyTemplate objects and produces all
    parameter combinations as candidate configurations.

    Example::

        generator = StrategyGenerator()
        generator.add_template(StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10, 20], "slow_period": [30, 50]},
            description="SMA crossover with various lookback periods",
            tags=["trend"],
        ))
        candidates = generator.get_candidates()
    """

    def __init__(self) -> None:
        self._templates: list[StrategyTemplate] = []

    def add_template(self, template: StrategyTemplate) -> None:
        """Register a strategy template."""
        self._templates.append(template)
        logger.info(
            f"Added template: {template.name} "
            f"({template.num_combinations()} combinations)"
        )

    def add_templates(self, templates: list[StrategyTemplate]) -> None:
        """Register multiple templates at once."""
        for t in templates:
            self.add_template(t)

    @property
    def templates(self) -> list[StrategyTemplate]:
        return list(self._templates)

    def get_candidates(self) -> list[dict[str, Any]]:
        """Generate all candidate configurations.

        Returns:
            List of dicts, each with:
            ``strategy_class``, ``params``, ``description``, ``tags``.
        """
        import itertools

        candidates: list[dict[str, Any]] = []

        for template in self._templates:
            keys = list(template.param_grid.keys())
            values = [template.param_grid[k] for k in keys]

            for combo in itertools.product(*values):
                params = dict(zip(keys, combo))
                candidates.append({
                    "strategy_class": template.strategy_class,
                    "params": params,
                    "description": template.description,
                    "tags": template.tags,
                })

        return candidates

    def total_candidates(self) -> int:
        """Total number of candidates across all templates."""
        return sum(t.num_combinations() for t in self._templates)


# ---------------------------------------------------------------------------
# StrategyRanker
# ---------------------------------------------------------------------------

class StrategyRanker:
    """Backtests generated candidates and ranks them.

    Takes candidates from StrategyGenerator, runs each through
    BacktestEngine, collects metrics, and ranks by a configurable
    metric.

    Args:
        base_config: BacktestConfig to use as the base.
        rank_by: Metric name for ranking (default: "sharpe_ratio").
        ascending: If True, lower is better. Default False (higher = better).
        top_n: Max strategies to keep in results.
        output_dir: Where to save exports.

    Example::

        ranker = StrategyRanker(base_config=config)
        result = ranker.run(data_handler, generator.get_candidates())
        for s in result.get_top(5):
            print(s.strategy_name, s.params, s.metrics["sharpe_ratio"])
    """

    def __init__(
        self,
        base_config: BacktestConfig,
        rank_by: str = "sharpe_ratio",
        ascending: bool = False,
        top_n: int = 20,
        output_dir: str = "output/strategy_ranking",
    ) -> None:
        self.base_config = base_config
        self.rank_by = rank_by
        self.ascending = ascending
        self.top_n = top_n
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.result: Optional[GeneratorResult] = None

    def run(
        self,
        data_handler: DataHandler,
        candidates: list[dict[str, Any]],
    ) -> GeneratorResult:
        """Backtest all candidates and rank them.

        Args:
            data_handler: Data to backtest on.
            candidates: List from StrategyGenerator.get_candidates().

        Returns:
            GeneratorResult with ranked strategies.
        """
        total = len(candidates)
        logger.info(f"Ranking {total} strategy candidates by {self.rank_by}")

        results: list[dict[str, Any]] = []

        for idx, candidate in enumerate(candidates):
            strategy_class = candidate["strategy_class"]
            params = candidate["params"]
            description = candidate.get("description", "")
            tags = candidate.get("tags", [])

            logger.info(
                f"Candidate {idx + 1}/{total}: "
                f"{strategy_class.__name__} {params}"
            )

            try:
                metrics = self._run_single(strategy_class, params, data_handler)
                results.append({
                    "strategy_name": strategy_class.__name__,
                    "params": params,
                    "metrics": metrics,
                    "description": description,
                    "tags": tags,
                })
            except Exception as exc:
                logger.warning(
                    f"Candidate failed: {strategy_class.__name__} "
                    f"{params}: {exc}"
                )

        # Sort by rank metric
        results = self._sort_results(results)

        # Build ranked strategies
        ranked: list[RankedStrategy] = []
        for i, r in enumerate(results[:self.top_n]):
            ranked.append(RankedStrategy(
                rank=i + 1,
                strategy_name=r["strategy_name"],
                params=r["params"],
                metrics=r["metrics"],
                description=r.get("description", ""),
                tags=r.get("tags", []),
            ))

        self.result = GeneratorResult(
            ranked_strategies=ranked,
            total_candidates=total,
            total_successful=len(results),
            rank_metric=self.rank_by,
        )

        self._export_results()

        logger.info(
            f"Ranking complete: {len(results)} successful out of {total} candidates"
        )

        return self.result

    def get_results(self) -> Optional[GeneratorResult]:
        """Return the last ranking result."""
        return self.result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _run_single(
        self,
        strategy_class: type[BaseStrategy],
        params: dict[str, Any],
        data_handler: DataHandler,
    ) -> dict[str, Any]:
        """Run one backtest and return its metrics."""
        config = self._clone_config(self.base_config)

        strategy_params = dict(config.strategy_params or {})
        strategy_params.update(params)
        config.strategy_params = strategy_params

        strategy = strategy_class()
        engine = BacktestEngine(config, strategy)
        engine.run(data_handler)

        results = engine.get_results()
        return results.get("metrics", {})

    def _sort_results(self, results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sort results by the ranking metric."""
        def sort_key(r: dict[str, Any]) -> float:
            val = r.get("metrics", {}).get(self.rank_by)
            if val is None:
                return float("-inf") if not self.ascending else float("inf")
            try:
                f = float(val)
                if f != f:  # NaN
                    return float("-inf") if not self.ascending else float("inf")
                return f
            except (TypeError, ValueError):
                return float("-inf") if not self.ascending else float("inf")

        return sorted(results, key=sort_key, reverse=not self.ascending)

    def _export_results(self) -> None:
        """Write ranking results to CSV and JSON."""
        if self.result is None or not self.result.ranked_strategies:
            return

        df = self.result.to_dataframe()
        csv_path = self.output_dir / "strategy_ranking.csv"
        df.to_csv(csv_path, index=False)

        json_path = self.output_dir / "strategy_ranking.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.result.to_dict(), f, indent=2, default=str)

        logger.info(f"Strategy ranking CSV saved to {csv_path}")
        logger.info(f"Strategy ranking JSON saved to {json_path}")

    @staticmethod
    def _clone_config(config: BacktestConfig) -> BacktestConfig:
        """Clone a BacktestConfig safely."""
        if hasattr(config, "model_copy"):
            return config.model_copy(deep=True)
        return config.model_copy(deep=True)


# ---------------------------------------------------------------------------
# Convenience: built-in templates
# ---------------------------------------------------------------------------

def get_default_templates() -> list[StrategyTemplate]:
    """Return a set of built-in strategy templates.

    Uses the three existing strategy classes with sensible
    parameter ranges for grid search.

    Returns:
        List of StrategyTemplate objects.
    """
    from src.strategies.sma_crossover import SMACrossoverStrategy
    from src.strategies.rsi_reversion import RSIReversionStrategy
    from src.strategies.breakout import BreakoutStrategy

    return [
        StrategyTemplate(
            strategy_class=SMACrossoverStrategy,
            param_grid={
                "fast_period": [5, 10, 20],
                "slow_period": [30, 50, 100],
            },
            description="SMA crossover with various lookback windows",
            tags=["trend", "moving_average"],
        ),
        StrategyTemplate(
            strategy_class=RSIReversionStrategy,
            param_grid={
                "rsi_period": [7, 14, 21],
                "oversold": [20, 30],
                "overbought": [70, 80],
            },
            description="RSI mean reversion with tunable thresholds",
            tags=["mean_reversion", "oscillator"],
        ),
        StrategyTemplate(
            strategy_class=BreakoutStrategy,
            param_grid={
                "entry_period": [10, 20, 40],
                "exit_period": [5, 10, 20],
            },
            description="Donchian channel breakout strategy",
            tags=["breakout", "channel"],
        ),
    ]
