from pathlib import Path

import pandas as pd
import pytest

from src.core.data_handler import DataHandler
from src.research.multi_asset_backtester import (
    AllocationMethod,
    MultiAssetBacktester,
)
from src.strategies.sma_crossover import SMACrossoverStrategy
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


def build_data(start_price: float) -> DataHandler:
    df = pd.DataFrame(
        {
            "open": [start_price + i * 0.2 for i in range(220)],
            "high": [start_price + 1 + i * 0.2 for i in range(220)],
            "low": [start_price - 1 + i * 0.2 for i in range(220)],
            "close": [start_price + i * 0.25 for i in range(220)],
            "volume": [1000 + i * 5 for i in range(220)],
        },
        index=pd.date_range("2025-01-01", periods=220, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def build_config(tmp_path: Path) -> BacktestConfig:
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
        output_dir=str(tmp_path / "single"),
        data_file="data/sample_data.csv",
    )


def test_multi_asset_backtester_runs(tmp_path: Path):
    config = build_config(tmp_path)

    symbol_to_data = {
        "RELIANCE.NS": build_data(100),
        "TCS.NS": build_data(200),
        "INFY.NS": build_data(300),
    }

    backtester = MultiAssetBacktester(
        base_config=config,
        strategy_class=SMACrossoverStrategy,
        symbol_to_data=symbol_to_data,
        allocation_method=AllocationMethod.EQUAL_WEIGHT,
        output_dir=str(tmp_path / "multi"),
    )

    results = backtester.run()

    assert "portfolio_metrics" in results
    assert "portfolio_equity_curve" in results
    assert "portfolio_trade_log" in results
    assert "symbol_results" in results

    assert len(results["symbol_results"]) == 3
    assert not results["portfolio_equity_curve"].empty


def test_equal_weight_allocation(tmp_path: Path):
    config = build_config(tmp_path)

    symbol_to_data = {
        "RELIANCE.NS": build_data(100),
        "TCS.NS": build_data(200),
    }

    backtester = MultiAssetBacktester(
        base_config=config,
        strategy_class=SMACrossoverStrategy,
        symbol_to_data=symbol_to_data,
        allocation_method=AllocationMethod.EQUAL_WEIGHT,
        output_dir=str(tmp_path / "multi"),
    )

    allocations = backtester._build_allocations()

    assert allocations["RELIANCE.NS"] == 50_000
    assert allocations["TCS.NS"] == 50_000


def test_exports_created(tmp_path: Path):
    config = build_config(tmp_path)

    symbol_to_data = {
        "RELIANCE.NS": build_data(100),
        "TCS.NS": build_data(200),
    }

    output_dir = tmp_path / "multi"

    backtester = MultiAssetBacktester(
        base_config=config,
        strategy_class=SMACrossoverStrategy,
        symbol_to_data=symbol_to_data,
        allocation_method=AllocationMethod.EQUAL_WEIGHT,
        output_dir=str(output_dir),
    )

    backtester.run()

    assert (output_dir / "portfolio_equity_curve.csv").exists()
    assert (output_dir / "portfolio_metrics.csv").exists()
    assert (output_dir / "symbol_metrics.csv").exists()


def test_portfolio_metrics_include_total_fees(tmp_path: Path):
    """portfolio_metrics must report nonzero total_fees when fee_rate > 0."""
    config = build_config(tmp_path)
    # fee_rate=0.001 is set in build_config; any trade will incur fees

    symbol_to_data = {
        "RELIANCE.NS": build_data(100),
        "TCS.NS": build_data(200),
    }

    backtester = MultiAssetBacktester(
        base_config=config,
        strategy_class=SMACrossoverStrategy,
        symbol_to_data=symbol_to_data,
        allocation_method=AllocationMethod.EQUAL_WEIGHT,
        output_dir=str(tmp_path / "multi_fees"),
    )

    results = backtester.run()
    metrics = results["portfolio_metrics"]

    assert "total_fees" in metrics, "portfolio_metrics must contain 'total_fees'"

    trade_log = results["portfolio_trade_log"]
    if not trade_log.empty and "fees" in trade_log.columns:
        expected_fees = float(trade_log["fees"].sum())
        assert metrics["total_fees"] == pytest.approx(expected_fees, rel=1e-6)
        assert metrics["total_fees"] > 0, "total_fees should be > 0 when trades occur"