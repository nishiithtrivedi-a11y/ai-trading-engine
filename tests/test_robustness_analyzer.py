from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.data_handler import DataHandler
from src.research_lab.config import RobustnessAnalyzerConfig
from src.research_lab.robustness_analyzer import RobustnessAnalyzer
from src.strategies.sma_crossover import SMACrossoverStrategy
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


def _build_config(tmp_path: Path) -> BacktestConfig:
    return BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0005,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.95,
        intraday=False,
        risk=RiskConfig(stop_loss_pct=0.05, trailing_stop_pct=0.03),
        strategy_params={},
        output_dir=str(tmp_path / "backtest"),
        data_file="data/sample_data.csv",
    )


def _build_data(num_bars: int = 220) -> DataHandler:
    df = pd.DataFrame(
        {
            "open": [100 + i * 0.2 for i in range(num_bars)],
            "high": [101 + i * 0.2 for i in range(num_bars)],
            "low": [99 + i * 0.2 for i in range(num_bars)],
            "close": [100 + i * 0.25 for i in range(num_bars)],
            "volume": [1000 + i * 5 for i in range(num_bars)],
        },
        index=pd.date_range("2024-01-01", periods=num_bars, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def test_robustness_report_scores_in_bounds(tmp_path: Path) -> None:
    report = RobustnessAnalyzer().analyze(
        strategy_class=SMACrossoverStrategy,
        params={"fast_period": 10, "slow_period": 30},
        base_config=_build_config(tmp_path),
        data_handler=_build_data(),
        config=RobustnessAnalyzerConfig(
            walk_forward_train_size=100,
            walk_forward_test_size=30,
            walk_forward_step_size=30,
            monte_carlo_simulations=10,
            noise_injection_std=0.002,
            parameter_perturbation_pct=0.05,
        ),
    )

    assert 0 <= report.walk_forward_score <= 100
    assert 0 <= report.monte_carlo_score <= 100
    assert 0 <= report.overall_robustness_score <= 100
