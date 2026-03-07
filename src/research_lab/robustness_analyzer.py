"""
Robustness analysis for strategy candidates.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.research.monte_carlo import MonteCarloAnalyzer, SimulationMode
from src.research.walk_forward import WalkForwardTester
from src.research_lab.config import RobustnessAnalyzerConfig
from src.research_lab.models import RobustnessReport
from src.strategies.base_strategy import BaseStrategy
from src.utils.config import BacktestConfig


class RobustnessAnalyzerError(Exception):
    """Raised when robustness analysis fails."""


def _clamp(value: float, lower: float = 0.0, upper: float = 100.0) -> float:
    return max(lower, min(upper, float(value)))


def _clone_config(config: BacktestConfig) -> BacktestConfig:
    if hasattr(config, "model_copy"):
        return config.model_copy(deep=True)
    return copy.deepcopy(config)


@dataclass
class RobustnessAnalyzer:
    def analyze(
        self,
        strategy_class: type[BaseStrategy],
        params: dict[str, Any],
        base_config: BacktestConfig,
        data_handler: DataHandler,
        config: RobustnessAnalyzerConfig,
    ) -> RobustnessReport:
        baseline_metrics, trade_log = self._run_backtest(
            strategy_class=strategy_class,
            params=params,
            base_config=base_config,
            data_handler=data_handler,
        )

        walk_forward_score = self._walk_forward_score(
            strategy_class=strategy_class,
            params=params,
            base_config=base_config,
            data_handler=data_handler,
            config=config,
        )

        monte_carlo_score = self._monte_carlo_score(
            trade_log=trade_log,
            initial_capital=float(base_config.initial_capital),
            config=config,
        )

        noise_score = self._noise_resilience_score(
            strategy_class=strategy_class,
            params=params,
            base_config=base_config,
            data_handler=data_handler,
            baseline_return=float(baseline_metrics.get("total_return_pct", 0.0) or 0.0),
            noise_std=float(config.noise_injection_std),
        )

        stability_score = self._parameter_stability_score(
            strategy_class=strategy_class,
            params=params,
            base_config=base_config,
            data_handler=data_handler,
            perturbation_pct=float(config.parameter_perturbation_pct),
        )

        weights = config.overall_weights
        overall = (
            weights.get("walk_forward", 0.0) * walk_forward_score
            + weights.get("monte_carlo", 0.0) * monte_carlo_score
            + weights.get("noise_resilience", 0.0) * noise_score
            + weights.get("parameter_stability", 0.0) * stability_score
        )

        return RobustnessReport(
            strategy_name=strategy_class.__name__,
            params=dict(params),
            walk_forward_score=walk_forward_score,
            monte_carlo_score=monte_carlo_score,
            noise_resilience_score=noise_score,
            parameter_stability_score=stability_score,
            overall_robustness_score=_clamp(overall),
            notes=[],
            metadata={"baseline_metrics": baseline_metrics},
        )

    def _run_backtest(
        self,
        strategy_class: type[BaseStrategy],
        params: dict[str, Any],
        base_config: BacktestConfig,
        data_handler: DataHandler,
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        cfg = _clone_config(base_config)
        strategy_params = dict(cfg.strategy_params or {})
        strategy_params.update(params)
        cfg.strategy_params = strategy_params

        strategy = strategy_class()
        engine = BacktestEngine(cfg, strategy)
        engine.run(data_handler)
        results = engine.get_results()
        trade_log_raw = results.get("trade_log", [])
        if isinstance(trade_log_raw, pd.DataFrame):
            trade_log = trade_log_raw.to_dict(orient="records")
        elif isinstance(trade_log_raw, list):
            trade_log = trade_log_raw
        elif trade_log_raw is None:
            trade_log = []
        else:
            # Keep downstream consumers stable even if engine format changes.
            trade_log = list(trade_log_raw)
        return results.get("metrics", {}), trade_log

    def _walk_forward_score(
        self,
        strategy_class: type[BaseStrategy],
        params: dict[str, Any],
        base_config: BacktestConfig,
        data_handler: DataHandler,
        config: RobustnessAnalyzerConfig,
    ) -> float:
        grid = {
            key: self._perturb_values(value, config.parameter_perturbation_pct)
            for key, value in params.items()
            if isinstance(value, (int, float))
        }
        if not grid:
            grid = {"_dummy": [1]}

        tester = WalkForwardTester(
            base_config=base_config,
            strategy_class=strategy_class,
            param_grid=grid,
            train_size=config.walk_forward_train_size,
            test_size=config.walk_forward_test_size,
            step_size=config.walk_forward_step_size,
            optimize_target="sharpe_ratio",
            output_dir="output/research_lab/walk_forward_tmp",
        )
        result = tester.run(data_handler)
        sharpe = float(result.aggregate_metrics.get("avg_test_sharpe_ratio") or 0.0)
        return _clamp(((sharpe + 1.0) / 3.0) * 100.0)

    def _monte_carlo_score(
        self,
        trade_log: list[dict[str, Any]],
        initial_capital: float,
        config: RobustnessAnalyzerConfig,
    ) -> float:
        if len(trade_log) == 0:
            return 0.0
        analyzer = MonteCarloAnalyzer(
            trades=trade_log,
            initial_capital=initial_capital,
            num_simulations=config.monte_carlo_simulations,
            seed=config.monte_carlo_seed,
            output_dir="output/research_lab/monte_carlo_tmp",
        )
        result = analyzer.run(SimulationMode.RETURN_BOOTSTRAP)
        prob = float(result.summary.get("probability_of_profit") or 0.0)
        median_return = float(result.summary.get("median_return_pct") or 0.0)
        score = prob * 80.0 + _clamp((median_return + 0.2) / 0.4 * 20.0)
        return _clamp(score)

    def _noise_resilience_score(
        self,
        strategy_class: type[BaseStrategy],
        params: dict[str, Any],
        base_config: BacktestConfig,
        data_handler: DataHandler,
        baseline_return: float,
        noise_std: float,
    ) -> float:
        if noise_std <= 0:
            return 100.0

        noisy_df = data_handler.data.copy()
        rng = np.random.default_rng(42)
        noise = rng.normal(0.0, noise_std, size=len(noisy_df))
        noisy_df["close"] = noisy_df["close"].astype(float) * (1.0 + noise)
        noisy_df["open"] = noisy_df["open"].astype(float) * (1.0 + noise)
        noisy_df["high"] = noisy_df[["open", "close"]].max(axis=1) * 1.001
        noisy_df["low"] = noisy_df[["open", "close"]].min(axis=1) * 0.999
        noisy_handler = DataHandler(noisy_df)

        metrics, _ = self._run_backtest(strategy_class, params, base_config, noisy_handler)
        noisy_return = float(metrics.get("total_return_pct", 0.0) or 0.0)

        diff = abs(noisy_return - baseline_return)
        return _clamp(100.0 - diff * 400.0)

    def _parameter_stability_score(
        self,
        strategy_class: type[BaseStrategy],
        params: dict[str, Any],
        base_config: BacktestConfig,
        data_handler: DataHandler,
        perturbation_pct: float,
    ) -> float:
        numeric_params = {k: v for k, v in params.items() if isinstance(v, (int, float))}
        if not numeric_params:
            return 60.0

        returns: list[float] = []
        for key, value in numeric_params.items():
            for direction in (-1.0, 1.0):
                perturbed = dict(params)
                new_value = value * (1.0 + direction * perturbation_pct)
                if isinstance(value, int):
                    new_value = max(1, int(round(new_value)))
                perturbed[key] = new_value
                metrics, _ = self._run_backtest(strategy_class, perturbed, base_config, data_handler)
                returns.append(float(metrics.get("total_return_pct", 0.0) or 0.0))

        if not returns:
            return 50.0
        std = float(np.std(returns))
        median_ret = float(np.median(returns))
        score = (100.0 - std * 400.0) + _clamp((median_ret + 0.1) / 0.2 * 20.0)
        return _clamp(score)

    @staticmethod
    def _perturb_values(value: float | int, pct: float) -> list[float | int]:
        low = value * (1.0 - pct)
        high = value * (1.0 + pct)
        if isinstance(value, int):
            return sorted({max(1, int(round(low))), int(value), max(1, int(round(high)))})
        return sorted({float(low), float(value), float(high)})
