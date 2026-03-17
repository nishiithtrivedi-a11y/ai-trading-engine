"""Tests for the walk-forward testing engine (Step 9)."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.core.data_handler import DataHandler
from src.research.walk_forward import (
    WalkForwardResult,
    WalkForwardTester,
    WalkForwardWindowResult,
)
from src.strategies.sma_crossover import SMACrossoverStrategy
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _build_config(tmp_path: Path) -> BacktestConfig:
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


def _build_data(num_bars: int = 250) -> DataHandler:
    """Create synthetic uptrending data with enough bars for walk-forward."""
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


# ---------------------------------------------------------------------------
# Tests — WalkForwardWindowResult
# ---------------------------------------------------------------------------

class TestWalkForwardWindowResult:

    def test_to_dict_has_all_keys(self):
        wr = WalkForwardWindowResult(
            window_index=0,
            train_start="2024-01-01",
            train_end="2024-04-30",
            test_start="2024-05-01",
            test_end="2024-06-30",
            best_params={"fast_period": 5, "slow_period": 20},
            train_metrics={"sharpe_ratio": 1.5},
            test_metrics={"sharpe_ratio": 0.8, "total_return_pct": 0.02},
            num_train_bars=120,
            num_test_bars=60,
        )
        d = wr.to_dict()
        assert d["window_index"] == 0
        assert d["param_fast_period"] == 5
        assert d["param_slow_period"] == 20
        assert d["train_sharpe_ratio"] == 1.5
        assert d["test_sharpe_ratio"] == 0.8
        assert d["num_train_bars"] == 120
        assert d["num_test_bars"] == 60


# ---------------------------------------------------------------------------
# Tests — WalkForwardResult
# ---------------------------------------------------------------------------

class TestWalkForwardResult:

    def test_empty_result(self):
        r = WalkForwardResult()
        assert r.to_dataframe().empty
        assert r.to_dict()["num_windows"] == 0

    def test_to_dataframe_with_windows(self):
        wr = WalkForwardWindowResult(
            window_index=0,
            train_start="2024-01-01",
            train_end="2024-04-30",
            test_start="2024-05-01",
            test_end="2024-06-30",
            best_params={"fast_period": 5},
            train_metrics={"sharpe_ratio": 1.0},
            test_metrics={"sharpe_ratio": 0.5},
            num_train_bars=120,
            num_test_bars=60,
        )
        r = WalkForwardResult(windows=[wr])
        df = r.to_dataframe()
        assert len(df) == 1
        assert "param_fast_period" in df.columns


# ---------------------------------------------------------------------------
# Tests — WalkForwardTester
# ---------------------------------------------------------------------------

class TestWalkForwardTester:

    def test_validation_errors(self, tmp_path):
        config = _build_config(tmp_path)

        with pytest.raises(ValueError, match="train_size"):
            WalkForwardTester(
                base_config=config,
                strategy_class=SMACrossoverStrategy,
                param_grid={"fast_period": [5]},
                train_size=0,
                test_size=30,
            )

        with pytest.raises(ValueError, match="test_size"):
            WalkForwardTester(
                base_config=config,
                strategy_class=SMACrossoverStrategy,
                param_grid={"fast_period": [5]},
                train_size=100,
                test_size=0,
            )

        with pytest.raises(ValueError, match="param_grid"):
            WalkForwardTester(
                base_config=config,
                strategy_class=SMACrossoverStrategy,
                param_grid={},
                train_size=100,
                test_size=30,
            )

    def test_insufficient_data_raises(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(50)  # Only 50 bars

        tester = WalkForwardTester(
            base_config=config,
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10]},
            train_size=100,
            test_size=30,
            output_dir=str(tmp_path / "wf"),
        )

        with pytest.raises(ValueError, match="bars"):
            tester.run(dh)

    def test_basic_run(self, tmp_path):
        """Run walk-forward with small windows on synthetic data."""
        config = _build_config(tmp_path)
        dh = _build_data(250)

        tester = WalkForwardTester(
            base_config=config,
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10], "slow_period": [20, 30]},
            train_size=100,
            test_size=50,
            output_dir=str(tmp_path / "wf"),
        )

        result = tester.run(dh)

        assert isinstance(result, WalkForwardResult)
        assert len(result.windows) >= 1

        # Each window should have test metrics
        for w in result.windows:
            assert w.num_train_bars == 100
            assert w.num_test_bars == 50
            assert isinstance(w.best_params, dict)
            assert isinstance(w.test_metrics, dict)
            assert "total_return_pct" in w.test_metrics or "sharpe_ratio" in w.test_metrics

    def test_custom_step_size(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(300)

        tester = WalkForwardTester(
            base_config=config,
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5]},
            train_size=100,
            test_size=50,
            step_size=25,  # Overlapping test windows
            output_dir=str(tmp_path / "wf"),
        )

        result = tester.run(dh)
        # With step=25, more windows than step=50
        assert len(result.windows) >= 3

    def test_aggregate_metrics_computed(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(250)

        tester = WalkForwardTester(
            base_config=config,
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5, 10]},
            train_size=100,
            test_size=50,
            output_dir=str(tmp_path / "wf"),
        )

        result = tester.run(dh)

        agg = result.aggregate_metrics
        assert "num_windows" in agg
        assert "avg_test_return_pct" in agg
        assert "avg_test_sharpe_ratio" in agg
        assert agg["num_windows"] >= 1

    def test_exports_created(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(250)
        out_dir = tmp_path / "wf_export"

        tester = WalkForwardTester(
            base_config=config,
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5]},
            train_size=100,
            test_size=50,
            output_dir=str(out_dir),
        )

        tester.run(dh)

        assert (out_dir / "walk_forward_results.csv").exists()
        assert (out_dir / "walk_forward_results.json").exists()

        # Verify JSON is valid
        with open(out_dir / "walk_forward_results.json") as f:
            data = json.load(f)
        assert "num_windows" in data
        assert isinstance(data["windows"], list)

    def test_result_dataframe_serializable(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(250)

        tester = WalkForwardTester(
            base_config=config,
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5]},
            train_size=100,
            test_size=50,
            output_dir=str(tmp_path / "wf"),
        )

        result = tester.run(dh)
        df = result.to_dataframe()
        assert not df.empty
        # Must be JSON-serializable
        json_str = json.dumps(df.to_dict(orient="records"), default=str)
        assert isinstance(json_str, str)

    def test_get_results_returns_last_run(self, tmp_path):
        config = _build_config(tmp_path)
        dh = _build_data(250)

        tester = WalkForwardTester(
            base_config=config,
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5]},
            train_size=100,
            test_size=50,
            output_dir=str(tmp_path / "wf"),
        )

        result = tester.run(dh)
        assert tester.get_results() is result

    def test_window_boundaries_non_overlapping(self, tmp_path):
        """When step_size == test_size, test windows should not overlap."""
        config = _build_config(tmp_path)
        dh = _build_data(300)

        tester = WalkForwardTester(
            base_config=config,
            strategy_class=SMACrossoverStrategy,
            param_grid={"fast_period": [5]},
            train_size=100,
            test_size=50,
            step_size=50,
            output_dir=str(tmp_path / "wf"),
        )

        result = tester.run(dh)
        windows = result.windows

        if len(windows) >= 2:
            # Test start of window N+1 >= test end of window N
            for i in range(len(windows) - 1):
                assert windows[i + 1].test_start >= windows[i].test_end


class TestWalkForwardCloneConfig:

    def test_clone_config_uses_copy_when_model_copy_missing(self):
        class CopyOnlyConfig:
            def __init__(self):
                self.value = 1

            def copy(self, deep: bool = False):
                clone = CopyOnlyConfig()
                clone.value = self.value
                return clone

        original = CopyOnlyConfig()
        cloned = WalkForwardTester._clone_config(original)  # type: ignore[arg-type]
        cloned.value = 2

        assert original.value == 1
        assert cloned.value == 2

    def test_clone_config_falls_back_to_deepcopy_when_copy_missing(self):
        class DeepcopyOnlyConfig:
            def __init__(self):
                self.values = [1, 2, 3]

        original = DeepcopyOnlyConfig()
        cloned = WalkForwardTester._clone_config(original)  # type: ignore[arg-type]
        cloned.values.append(4)

        assert original.values == [1, 2, 3]
        assert cloned.values == [1, 2, 3, 4]

    def test_clone_config_supports_dataclass_replace_path(self):
        @dataclass
        class DataclassConfig:
            value: int
            flags: tuple[str, ...] = ("a",)

        original = DataclassConfig(value=7, flags=("x",))
        cloned = WalkForwardTester._clone_config(original)  # type: ignore[arg-type]
        cloned.value = 9

        assert original.value == 7
        assert cloned.value == 9
