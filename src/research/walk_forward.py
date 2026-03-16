"""
Walk-forward testing engine for out-of-sample strategy validation.

Splits the data into rolling train/test windows, optimizes strategy
parameters on the training window, then evaluates on the test window.
This avoids overfitting by ensuring the strategy is always tested on
unseen data.

Reuses StrategyOptimizer for the training-window optimization and
BacktestEngine for the test-window evaluation.
"""

from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.research.optimizer import StrategyOptimizer
from src.strategies.base_strategy import BaseStrategy
from src.utils.config import BacktestConfig
from src.utils.logger import setup_logger

logger = setup_logger("walk_forward")


# ---------------------------------------------------------------------------
# Result data classes
# ---------------------------------------------------------------------------

@dataclass
class WalkForwardWindowResult:
    """Result from one train/test window."""

    window_index: int
    train_start: str
    train_end: str
    test_start: str
    test_end: str
    best_params: dict[str, Any]
    train_metrics: dict[str, Any]
    test_metrics: dict[str, Any]
    num_train_bars: int
    num_test_bars: int

    def to_dict(self) -> dict[str, Any]:
        """Flatten to a JSON-serializable dict."""
        row: dict[str, Any] = {
            "window_index": self.window_index,
            "train_start": self.train_start,
            "train_end": self.train_end,
            "test_start": self.test_start,
            "test_end": self.test_end,
            "num_train_bars": self.num_train_bars,
            "num_test_bars": self.num_test_bars,
        }
        for k, v in self.best_params.items():
            row[f"param_{k}"] = v
        for k, v in self.train_metrics.items():
            row[f"train_{k}"] = v
        for k, v in self.test_metrics.items():
            row[f"test_{k}"] = v
        return row


@dataclass
class WalkForwardResult:
    """Aggregated results across all walk-forward windows."""

    windows: list[WalkForwardWindowResult] = field(default_factory=list)
    aggregate_metrics: dict[str, Any] = field(default_factory=dict)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert all window results to a DataFrame."""
        if not self.windows:
            return pd.DataFrame()
        return pd.DataFrame([w.to_dict() for w in self.windows])

    def to_dict(self) -> dict[str, Any]:
        """Full snapshot as a dict."""
        return {
            "num_windows": len(self.windows),
            "aggregate_metrics": self.aggregate_metrics,
            "windows": [w.to_dict() for w in self.windows],
        }


# ---------------------------------------------------------------------------
# WalkForwardTester
# ---------------------------------------------------------------------------

class WalkForwardTester:
    """Rolling walk-forward optimization and out-of-sample testing.

    Splits the full dataset into overlapping train/test windows and:
      1. Optimizes strategy parameters on each training window
         (using StrategyOptimizer grid search).
      2. Evaluates the best parameters on the subsequent test window
         (using BacktestEngine).
      3. Collects per-window and aggregate results.

    Args:
        base_config: Shared BacktestConfig (strategy_params are overridden
            per window by the optimizer).
        strategy_class: The strategy class to optimize.
        param_grid: Parameter grid for StrategyOptimizer.
        train_size: Number of bars in each training window.
        test_size: Number of bars in each test window.
        step_size: How many bars to slide forward between windows.
            Defaults to ``test_size`` (non-overlapping test windows).
        optimize_target: Metric name to rank optimizer results.
        output_dir: Where to write exports.

    Example::

        tester = WalkForwardTester(
            base_config=config,
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
            train_size=120,
            test_size=30,
        )
        result = tester.run(data_handler)
        result.to_dataframe()
    """

    def __init__(
        self,
        base_config: BacktestConfig,
        strategy_class: type[BaseStrategy],
        param_grid: dict[str, list[Any]],
        train_size: int,
        test_size: int,
        step_size: Optional[int] = None,
        optimize_target: str = "sharpe_ratio",
        output_dir: str = "output/walk_forward",
    ) -> None:
        if train_size < 1:
            raise ValueError("train_size must be >= 1")
        if test_size < 1:
            raise ValueError("test_size must be >= 1")
        if not param_grid:
            raise ValueError("param_grid cannot be empty")

        self.base_config = base_config
        self.strategy_class = strategy_class
        self.param_grid = param_grid
        self.train_size = train_size
        self.test_size = test_size
        self.step_size = step_size or test_size
        self.optimize_target = optimize_target
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.result = WalkForwardResult()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(self, data_handler: DataHandler) -> WalkForwardResult:
        """Execute the walk-forward test.

        Args:
            data_handler: DataHandler with full dataset loaded.

        Returns:
            WalkForwardResult with per-window and aggregate metrics.
        """
        full_data = data_handler.data
        total_bars = len(full_data)
        min_required = self.train_size + self.test_size

        if total_bars < min_required:
            raise ValueError(
                f"Dataset has {total_bars} bars but walk-forward requires "
                f"at least {min_required} (train_size={self.train_size} + "
                f"test_size={self.test_size})"
            )

        windows = self._build_windows(total_bars)
        logger.info(
            f"Walk-forward: {len(windows)} windows, "
            f"train={self.train_size}, test={self.test_size}, "
            f"step={self.step_size}"
        )

        self.result = WalkForwardResult()

        for idx, (train_start, train_end, test_start, test_end) in enumerate(windows):
            logger.info(
                f"Window {idx + 1}/{len(windows)}: "
                f"train [{train_start}:{train_end}], "
                f"test [{test_start}:{test_end}]"
            )

            train_df = full_data.iloc[train_start:train_end].copy()
            test_df = full_data.iloc[test_start:test_end].copy()

            window_result = self._run_window(
                window_index=idx,
                train_df=train_df,
                test_df=test_df,
            )
            self.result.windows.append(window_result)

        # Compute aggregate metrics across windows
        self.result.aggregate_metrics = self._compute_aggregates()

        # Export
        self._export_results()

        logger.info(
            f"Walk-forward complete: {len(self.result.windows)} windows, "
            f"avg test Sharpe = "
            f"{self.result.aggregate_metrics.get('avg_test_sharpe_ratio', 'N/A')}"
        )

        return self.result

    def get_results(self) -> WalkForwardResult:
        """Return the last run's results."""
        return self.result

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_windows(
        self, total_bars: int
    ) -> list[tuple[int, int, int, int]]:
        """Generate (train_start, train_end, test_start, test_end) tuples.

        train_end and test_end are exclusive (slice-style).
        """
        windows: list[tuple[int, int, int, int]] = []
        start = 0

        while start + self.train_size + self.test_size <= total_bars:
            train_start = start
            train_end = start + self.train_size
            test_start = train_end
            test_end = min(test_start + self.test_size, total_bars)

            windows.append((train_start, train_end, test_start, test_end))
            start += self.step_size

        return windows

    def _run_window(
        self,
        window_index: int,
        train_df: pd.DataFrame,
        test_df: pd.DataFrame,
    ) -> WalkForwardWindowResult:
        """Optimize on train_df, evaluate on test_df."""

        # ---- TRAIN: optimize parameters ----
        train_dh = DataHandler(train_df)
        optimizer = StrategyOptimizer(
            base_config=self.base_config,
            strategy_class=self.strategy_class,
            param_grid=self.param_grid,
            output_dir=str(self.output_dir / f"window_{window_index}" / "train"),
            sort_by=self.optimize_target,
            ascending=False,
            top_n=1,
        )
        optimizer.run(train_dh)
        best_row = optimizer.get_best_result()

        if best_row is None:
            logger.warning(f"Window {window_index}: optimizer returned no results")
            best_params: dict[str, Any] = {}
            train_metrics: dict[str, Any] = {}
        else:
            best_params = {
                k.replace("param_", ""): v
                for k, v in best_row.items()
                if k.startswith("param_")
            }
            train_metrics = {
                k: v for k, v in best_row.items()
                if not k.startswith("param_") and k != "strategy_name"
            }

        # ---- TEST: run best params on test window ----
        test_dh = DataHandler(test_df)
        test_config = self._clone_config(self.base_config)

        # Merge best_params into strategy_params
        strategy_params = dict(test_config.strategy_params or {})
        strategy_params.update(best_params)
        test_config.strategy_params = strategy_params

        strategy = self.strategy_class()
        engine = BacktestEngine(test_config, strategy)
        engine.run(test_dh)
        test_results = engine.get_results()
        test_metrics = test_results.get("metrics", {})

        # Timestamp labels for readability
        train_start_ts = str(train_df.index[0]) if len(train_df) > 0 else ""
        train_end_ts = str(train_df.index[-1]) if len(train_df) > 0 else ""
        test_start_ts = str(test_df.index[0]) if len(test_df) > 0 else ""
        test_end_ts = str(test_df.index[-1]) if len(test_df) > 0 else ""

        return WalkForwardWindowResult(
            window_index=window_index,
            train_start=train_start_ts,
            train_end=train_end_ts,
            test_start=test_start_ts,
            test_end=test_end_ts,
            best_params=best_params,
            train_metrics=train_metrics,
            test_metrics=test_metrics,
            num_train_bars=len(train_df),
            num_test_bars=len(test_df),
        )

    def _compute_aggregates(self) -> dict[str, Any]:
        """Compute summary statistics across all test windows."""
        if not self.result.windows:
            return {}

        test_returns = []
        test_sharpes = []
        test_win_rates = []
        test_num_trades = []

        for w in self.result.windows:
            m = w.test_metrics
            ret = m.get("total_return_pct")
            if ret is not None:
                test_returns.append(float(ret))
            sharpe = m.get("sharpe_ratio")
            if sharpe is not None:
                test_sharpes.append(float(sharpe))
            wr = m.get("win_rate")
            if wr is not None:
                test_win_rates.append(float(wr))
            nt = m.get("num_trades")
            if nt is not None:
                test_num_trades.append(int(nt))

        def _safe_mean(vals: list) -> Optional[float]:
            return sum(vals) / len(vals) if vals else None

        def _safe_min(vals: list) -> Optional[float]:
            return min(vals) if vals else None

        def _safe_max(vals: list) -> Optional[float]:
            return max(vals) if vals else None

        return {
            "num_windows": len(self.result.windows),
            "avg_test_return_pct": _safe_mean(test_returns),
            "min_test_return_pct": _safe_min(test_returns),
            "max_test_return_pct": _safe_max(test_returns),
            "avg_test_sharpe_ratio": _safe_mean(test_sharpes),
            "min_test_sharpe_ratio": _safe_min(test_sharpes),
            "max_test_sharpe_ratio": _safe_max(test_sharpes),
            "avg_test_win_rate": _safe_mean(test_win_rates),
            "total_test_trades": sum(test_num_trades) if test_num_trades else 0,
        }

    def _export_results(self) -> None:
        """Write walk-forward results to CSV and JSON."""
        if not self.result.windows:
            return

        df = self.result.to_dataframe()
        csv_path = self.output_dir / "walk_forward_results.csv"
        df.to_csv(csv_path, index=False)

        json_path = self.output_dir / "walk_forward_results.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(self.result.to_dict(), f, indent=2, default=str)

        logger.info(f"Walk-forward results saved to {csv_path}")
        logger.info(f"Walk-forward JSON saved to {json_path}")

    @staticmethod
    def _clone_config(config: BacktestConfig) -> BacktestConfig:
        """Clone a BacktestConfig safely."""
        if hasattr(config, "model_copy"):
            return config.model_copy(deep=True)
        if hasattr(config, "copy"):
            try:
                return config.copy(deep=True)
            except TypeError:
                return config.copy()
        return copy.deepcopy(config)
