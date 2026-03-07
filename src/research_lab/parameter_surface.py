"""
Parameter surface analysis for strategy candidates.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pandas as pd

from src.core.data_handler import DataHandler
from src.research.optimizer import StrategyOptimizer
from src.research_lab.config import ParameterSurfaceConfig
from src.research_lab.models import ParameterSurfacePoint, ParameterSurfaceReport
from src.strategies.base_strategy import BaseStrategy
from src.utils.config import BacktestConfig


class ParameterSurfaceAnalyzerError(Exception):
    """Raised when parameter surface analysis fails."""


@dataclass
class ParameterSurfaceAnalyzer:
    def analyze(
        self,
        strategy_class: type[BaseStrategy],
        param_grid: dict[str, list[Any]],
        base_config: BacktestConfig,
        data_handler: DataHandler,
        config: ParameterSurfaceConfig,
    ) -> ParameterSurfaceReport:
        optimizer = StrategyOptimizer(
            base_config=base_config,
            strategy_class=strategy_class,
            param_grid=param_grid,
            sort_by="sharpe_ratio",
            ascending=False,
            top_n=max(1000, len(param_grid)),
            output_dir="output/research_lab/parameter_surface_tmp",
        )
        df = optimizer.run(data_handler)
        if df.empty:
            return ParameterSurfaceReport(strategy_name=strategy_class.__name__, points=[])

        points: list[ParameterSurfacePoint] = []
        for _, row in df.iterrows():
            if bool(row.get("run_failed", False)):
                continue

            params = {
                col.replace("param_", ""): row[col]
                for col in df.columns
                if col.startswith("param_")
            }
            point = ParameterSurfacePoint(
                strategy_name=strategy_class.__name__,
                params=params,
                sharpe_ratio=float(row.get("sharpe_ratio", 0.0) or 0.0),
                max_drawdown_pct=float(row.get("max_drawdown_pct", 0.0) or 0.0),
                profit_factor=float(row.get("profit_factor", 0.0) or 0.0),
                total_return_pct=float(row.get("total_return_pct", 0.0) or 0.0),
                num_trades=int(row.get("num_trades", 0) or 0),
            )
            points.append(point)

        if not points:
            return ParameterSurfaceReport(strategy_name=strategy_class.__name__, points=[])

        valid = [p for p in points if p.num_trades >= config.min_trades_required]
        if not valid:
            valid = points

        stable_keys, unstable_keys = self._classify_regions(valid, config)
        return ParameterSurfaceReport(
            strategy_name=strategy_class.__name__,
            points=points,
            stable_region_keys=stable_keys,
            unstable_region_keys=unstable_keys,
            metadata={
                "num_points": len(points),
                "num_valid_points": len(valid),
            },
        )

    @staticmethod
    def _classify_regions(
        points: list[ParameterSurfacePoint],
        config: ParameterSurfaceConfig,
    ) -> tuple[list[str], list[str]]:
        if not points:
            return [], []

        df = pd.DataFrame(
            [
                {
                    "key": "",
                    "sharpe_ratio": p.sharpe_ratio,
                    "max_drawdown_pct": p.max_drawdown_pct,
                    "profit_factor": p.profit_factor,
                    "total_return_pct": p.total_return_pct,
                    "num_trades": p.num_trades,
                    "params": p.params,
                }
                for p in points
            ]
        )
        df["key"] = df["params"].apply(
            lambda x: "|".join(f"{k}={x[k]}" for k in sorted(x))
        )

        sharpe_top_cutoff = df["sharpe_ratio"].quantile(1 - config.stable_top_percentile)
        sharpe_bottom_cutoff = df["sharpe_ratio"].quantile(config.unstable_bottom_percentile)
        dd_median = df["max_drawdown_pct"].median()
        dd_top = df["max_drawdown_pct"].quantile(1 - config.unstable_bottom_percentile)

        stable = df[
            (df["sharpe_ratio"] >= sharpe_top_cutoff)
            & (df["max_drawdown_pct"] <= dd_median)
        ]["key"].tolist()

        unstable = df[
            (df["sharpe_ratio"] <= sharpe_bottom_cutoff)
            | (df["max_drawdown_pct"] >= dd_top)
        ]["key"].tolist()

        return stable, unstable
