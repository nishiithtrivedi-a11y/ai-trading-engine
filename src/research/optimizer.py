"""
Strategy optimization engine for parameter sweeps / grid search.

Runs repeated backtests over combinations of strategy parameters,
collects results, ranks them, and exports them to CSV / JSON.

Designed to work with the existing BacktestEngine and BacktestConfig.
"""

from __future__ import annotations

import copy
import itertools
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Optional

import pandas as pd

from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.strategies.base_strategy import BaseStrategy
from src.utils.config import BacktestConfig
from src.utils.logger import setup_logger

logger = setup_logger("optimizer")


@dataclass
class OptimizationResult:
    """One completed parameter-combination result."""
    strategy_name: str
    params: dict[str, Any]
    metrics: dict[str, Any]

    def to_flat_dict(self) -> dict[str, Any]:
        row = {"strategy_name": self.strategy_name}
        for key, value in self.params.items():
            row[f"param_{key}"] = value
        row.update(self.metrics)
        return row


class StrategyOptimizer:
    """
    Grid-search optimizer for strategies.

    Example:
        optimizer = StrategyOptimizer(
            base_config=config,
            strategy_class=SMACrossoverStrategy,
            param_grid={
                "fast_period": [5, 10, 20],
                "slow_period": [30, 50, 100],
            },
        )

        df = optimizer.run(data_handler)
    """

    def __init__(
        self,
        base_config: BacktestConfig,
        strategy_class: type[BaseStrategy],
        param_grid: dict[str, list[Any]],
        output_dir: str = "output/optimization",
        sort_by: str = "sharpe_ratio",
        ascending: bool = False,
        top_n: int = 20,
    ) -> None:
        if not param_grid:
            raise ValueError("param_grid cannot be empty.")

        self.base_config = base_config
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.output_dir = Path(output_dir)
        self.sort_by = sort_by
        self.ascending = ascending
        self.top_n = top_n

        self.results: list[OptimizationResult] = []
        self.results_df: pd.DataFrame = pd.DataFrame()

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, data_handler: Optional[DataHandler] = None) -> pd.DataFrame:
        """
        Run grid search across all parameter combinations.

        Args:
            data_handler: Shared data handler to reuse across runs.

        Returns:
            DataFrame of all optimization results.
        """
        combinations = list(self._generate_param_combinations())
        total = len(combinations)

        logger.info(
            f"Starting optimization for {self.strategy_class.__name__} "
            f"with {total} parameter combinations"
        )

        all_rows: list[dict[str, Any]] = []

        for idx, params in enumerate(combinations, start=1):
            logger.info(f"Optimization run {idx}/{total}: {params}")

            try:
                run_result = self._run_single(params, data_handler=data_handler)
                self.results.append(run_result)
                all_rows.append(run_result.to_flat_dict())
            except Exception as exc:
                logger.exception(f"Optimization run failed for params={params}: {exc}")
                failed_row = {
                    "strategy_name": self.strategy_class.__name__,
                    **{f"param_{k}": v for k, v in params.items()},
                    "run_failed": True,
                    "error": str(exc),
                }
                all_rows.append(failed_row)

        self.results_df = pd.DataFrame(all_rows)

        if not self.results_df.empty and self.sort_by in self.results_df.columns:
            self.results_df = self.results_df.sort_values(
                by=self.sort_by,
                ascending=self.ascending,
                na_position="last",
            ).reset_index(drop=True)

        self._export_results()

        logger.info(
            f"Optimization complete. Successful runs: "
            f"{len([r for r in all_rows if not r.get('run_failed', False)])}"
        )

        return self.results_df

    def get_top_results(self, top_n: Optional[int] = None) -> pd.DataFrame:
        """Return top N sorted rows."""
        if self.results_df.empty:
            return pd.DataFrame()

        n = top_n or self.top_n
        return self.results_df.head(n).copy()

    def get_best_result(self) -> Optional[dict[str, Any]]:
        """Return best single row as dict."""
        if self.results_df.empty:
            return None
        return self.results_df.iloc[0].to_dict()

    def print_summary(self, top_n: Optional[int] = None) -> None:
        """Print top optimization results."""
        if self.results_df.empty:
            print("No optimization results available.")
            return

        n = top_n or self.top_n
        top_df = self.get_top_results(n)

        print("\n" + "=" * 100)
        print(f"OPTIMIZATION SUMMARY — {self.strategy_class.__name__}")
        print("=" * 100)

        display_columns = [
            col for col in [
                "strategy_name",
                *[f"param_{k}" for k in self.param_grid.keys()],
                "total_return_pct",
                "annualized_return",
                "sharpe_ratio",
                "sortino_ratio",
                "max_drawdown_pct",
                "win_rate",
                "profit_factor",
                "num_trades",
                "avg_bars_held",
                "total_fees",
            ]
            if col in top_df.columns
        ]

        if display_columns:
            print(top_df[display_columns].to_string(index=False))
        else:
            print(top_df.to_string(index=False))

        print("=" * 100 + "\n")

    def _run_single(
        self,
        params: dict[str, Any],
        data_handler: Optional[DataHandler] = None,
    ) -> OptimizationResult:
        """
        Run one backtest with one parameter set.
        """
        config = self._clone_config(self.base_config)

        strategy_params = dict(getattr(config, "strategy_params", {}) or {})
        strategy_params.update(params)
        config.strategy_params = strategy_params

        # Keep each run isolated
        strategy = self.strategy_class()
        engine = BacktestEngine(config, strategy)
        engine.run(data_handler)

        results = engine.get_results()
        metrics = results.get("metrics", {})

        return OptimizationResult(
            strategy_name=strategy.name,
            params=params,
            metrics=metrics,
        )

    def _generate_param_combinations(self) -> Iterable[dict[str, Any]]:
        """
        Generate cartesian product of param grid.
        """
        keys = list(self.param_grid.keys())
        values = [self.param_grid[key] for key in keys]

        for combo in itertools.product(*values):
            yield dict(zip(keys, combo))

    def _export_results(self) -> None:
        """Save CSV + JSON exports."""
        if self.results_df.empty:
            return

        csv_path = self.output_dir / "optimization_results.csv"
        json_path = self.output_dir / "optimization_results.json"
        top_csv_path = self.output_dir / "top_results.csv"

        self.results_df.to_csv(csv_path, index=False)

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.results_df.to_dict(orient="records"), f, indent=2, default=str)

        self.get_top_results().to_csv(top_csv_path, index=False)

        logger.info(f"Saved optimization CSV: {csv_path}")
        logger.info(f"Saved optimization JSON: {json_path}")
        logger.info(f"Saved top results CSV: {top_csv_path}")

    @staticmethod
    def _clone_config(config: BacktestConfig) -> BacktestConfig:
        """
        Clone BacktestConfig safely across dataclass / Pydantic variants.
        """
        if hasattr(config, "model_copy"):
            return config.model_copy(deep=True)
        if hasattr(config, "copy"):
            try:
                return config.copy(deep=True)
            except TypeError:
                return config.copy()
        return copy.deepcopy(config)