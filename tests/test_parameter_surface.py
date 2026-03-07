from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.data_handler import DataHandler
from src.research_lab.config import ParameterSurfaceConfig
from src.research_lab.parameter_surface import ParameterSurfaceAnalyzer
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
            "open": [100 + i * 0.25 for i in range(num_bars)],
            "high": [101 + i * 0.25 for i in range(num_bars)],
            "low": [99 + i * 0.25 for i in range(num_bars)],
            "close": [100 + i * 0.3 for i in range(num_bars)],
            "volume": [1000 + i * 5 for i in range(num_bars)],
        },
        index=pd.date_range("2024-01-01", periods=num_bars, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def test_parameter_surface_report_basic(tmp_path: Path) -> None:
    report = ParameterSurfaceAnalyzer().analyze(
        strategy_class=SMACrossoverStrategy,
        param_grid={"fast_period": [5, 10], "slow_period": [30]},
        base_config=_build_config(tmp_path),
        data_handler=_build_data(),
        config=ParameterSurfaceConfig(stable_top_percentile=0.5, unstable_bottom_percentile=0.5),
    )
    assert report.strategy_name == "SMACrossoverStrategy"
    assert len(report.points) == 2
    assert isinstance(report.stable_region_keys, list)
    assert isinstance(report.unstable_region_keys, list)
