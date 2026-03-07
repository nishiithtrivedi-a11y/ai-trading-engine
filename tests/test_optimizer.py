from pathlib import Path

import pandas as pd

from src.core.data_handler import DataHandler
from src.research.optimizer import StrategyOptimizer
from src.strategies.sma_crossover import SMACrossoverStrategy
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


def build_test_config(tmp_path: Path) -> BacktestConfig:
    return BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0005,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.95,
        intraday=False,
        risk=RiskConfig(
            stop_loss_pct=0.05,
            trailing_stop_pct=0.03,
        ),
        strategy_params={
            "fast_period": 10,
            "slow_period": 30,
        },
        output_dir=str(tmp_path / "backtest"),
        data_file="data/sample_data.csv",
    )


def build_sample_data() -> DataHandler:
    df = pd.DataFrame(
        {
            "open": [100 + i * 0.2 for i in range(200)],
            "high": [101 + i * 0.2 for i in range(200)],
            "low": [99 + i * 0.2 for i in range(200)],
            "close": [100 + i * 0.25 for i in range(200)],
            "volume": [1000 + (i * 5) for i in range(200)],
        },
        index=pd.date_range("2025-01-01", periods=200, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def test_optimizer_runs_grid_search(tmp_path: Path):
    config = build_test_config(tmp_path)
    data_handler = build_sample_data()

    optimizer = StrategyOptimizer(
        base_config=config,
        strategy_class=SMACrossoverStrategy,
        param_grid={
            "fast_period": [5, 10],
            "slow_period": [20, 30],
        },
        output_dir=str(tmp_path / "optimization"),
        sort_by="sharpe_ratio",
        ascending=False,
        top_n=3,
    )

    results_df = optimizer.run(data_handler)

    assert not results_df.empty
    assert len(results_df) == 4
    assert "param_fast_period" in results_df.columns
    assert "param_slow_period" in results_df.columns


def test_optimizer_best_result(tmp_path: Path):
    config = build_test_config(tmp_path)
    data_handler = build_sample_data()

    optimizer = StrategyOptimizer(
        base_config=config,
        strategy_class=SMACrossoverStrategy,
        param_grid={
            "fast_period": [5],
            "slow_period": [20],
        },
        output_dir=str(tmp_path / "optimization"),
    )

    optimizer.run(data_handler)
    best = optimizer.get_best_result()

    assert best is not None
    assert best["param_fast_period"] == 5
    assert best["param_slow_period"] == 20


def test_optimizer_exports_files(tmp_path: Path):
    config = build_test_config(tmp_path)
    data_handler = build_sample_data()
    out_dir = tmp_path / "optimization"

    optimizer = StrategyOptimizer(
        base_config=config,
        strategy_class=SMACrossoverStrategy,
        param_grid={
            "fast_period": [5],
            "slow_period": [20],
        },
        output_dir=str(out_dir),
    )

    optimizer.run(data_handler)

    assert (out_dir / "optimization_results.csv").exists()
    assert (out_dir / "optimization_results.json").exists()
    assert (out_dir / "top_results.csv").exists()