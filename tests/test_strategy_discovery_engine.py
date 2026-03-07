from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.data_handler import DataHandler
from src.research_lab.config import (
    ResearchLabGeneratorConfig,
    RobustnessAnalyzerConfig,
    StrategyClusterConfig,
    StrategyDiscoveryConfig,
)
from src.research_lab.strategy_discovery_engine import StrategyDiscoveryEngine
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
            "open": [100 + i * 0.25 for i in range(num_bars)],
            "high": [101 + i * 0.25 for i in range(num_bars)],
            "low": [99 + i * 0.25 for i in range(num_bars)],
            "close": [100 + i * 0.3 for i in range(num_bars)],
            "volume": [1000 + i * 4 for i in range(num_bars)],
        },
        index=pd.date_range("2024-01-01", periods=num_bars, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def test_strategy_discovery_engine_happy_path(tmp_path: Path) -> None:
    cfg = StrategyDiscoveryConfig(
        generator=ResearchLabGeneratorConfig(
            use_default_templates=False,
            strategy_param_grids={
                "SMACrossoverStrategy": {"fast_period": [5, 10], "slow_period": [30]},
            },
            max_candidates=10,
        ),
        robustness=RobustnessAnalyzerConfig(
            walk_forward_train_size=100,
            walk_forward_test_size=30,
            walk_forward_step_size=30,
            monte_carlo_simulations=10,
            noise_injection_std=0.002,
            parameter_perturbation_pct=0.05,
        ),
        cluster=StrategyClusterConfig(similarity_threshold=0.9),
        top_n=5,
    )

    result = StrategyDiscoveryEngine().run(
        base_config=_build_config(tmp_path),
        data_handler=_build_data(),
        config=cfg,
        export=False,
    )

    assert result.total_candidates == 2
    assert result.total_evaluated >= 1
    assert len(result.strategy_scores) >= 1
    assert isinstance(result.strategy_clusters, list)
    assert isinstance(result.robustness_reports, list)
