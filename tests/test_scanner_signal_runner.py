from __future__ import annotations

import pandas as pd
import pytest

from src.core.data_handler import DataHandler
from src.scanners.config import StrategyScanSpec
from src.scanners.signal_runner import SignalRunner, SignalRunnerError
from src.strategies.base_strategy import BaseStrategy, Signal


class BuyStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        return Signal.BUY


class HoldStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        return Signal.HOLD


class InitParamStrategy(BaseStrategy):
    def initialize(self, params=None):
        super().initialize(params)
        self._marker = self.get_param("marker", "")

    def on_bar(self, data, current_bar, bar_index):
        if getattr(self, "_marker", "") == "ok":
            return Signal.BUY
        return Signal.HOLD


class BadOutputStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        return "INVALID"


class ThresholdBuyStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        threshold = self.get_param("threshold", 125.0)
        return Signal.BUY if float(current_bar["close"]) > threshold else Signal.HOLD


class StructuredBuyStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        return Signal.HOLD

    def generate_signal(
        self,
        data,
        current_bar,
        bar_index,
        *,
        symbol=None,
        timeframe=None,
    ):
        return self.build_signal(
            action=Signal.BUY,
            current_bar=current_bar,
            symbol=symbol,
            timeframe=timeframe,
            confidence=0.42,
            rationale="structured_buy",
            tags=("scanner",),
            metadata={"source": "test"},
        )


def _build_data(num_bars: int = 20) -> DataHandler:
    df = pd.DataFrame(
        {
            "open": [100 + i for i in range(num_bars)],
            "high": [101 + i for i in range(num_bars)],
            "low": [99 + i for i in range(num_bars)],
            "close": [100.5 + i for i in range(num_bars)],
            "volume": [1000 + i * 10 for i in range(num_bars)],
        },
        index=pd.date_range("2026-01-01", periods=num_bars, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def test_actionable_buy_case() -> None:
    dh = _build_data(30)
    spec = StrategyScanSpec(strategy_class=BuyStrategy, params={})
    runner = SignalRunner()

    snap = runner.run_signal("RELIANCE.NS", "1d", spec, dh)

    assert snap.signal == "buy"
    assert snap.is_actionable is True
    assert snap.strategy_name == "BuyStrategy"


def test_non_actionable_hold_case() -> None:
    dh = _build_data(30)
    spec = StrategyScanSpec(strategy_class=HoldStrategy, params={})
    runner = SignalRunner()

    snap = runner.run_signal("RELIANCE.NS", "1D", spec, dh)

    assert snap.signal == "hold"
    assert snap.is_actionable is False


def test_strategy_init_with_params() -> None:
    dh = _build_data(30)
    spec = StrategyScanSpec(strategy_class=InitParamStrategy, params={"marker": "ok"})
    runner = SignalRunner()

    snap = runner.run_signal("TCS.NS", "1h", spec, dh)

    assert snap.signal == "buy"
    assert snap.strategy_params["marker"] == "ok"


def test_insufficient_data_returns_safe_hold() -> None:
    dh = _build_data(1)
    spec = StrategyScanSpec(strategy_class=BuyStrategy, params={})
    runner = SignalRunner(min_required_bars=5)

    snap = runner.run_signal("INFY.NS", "5m", spec, dh)

    assert snap.signal == "hold"
    assert snap.is_actionable is False
    assert snap.extras["reason"] == "insufficient_data"


def test_invalid_strategy_output_raises() -> None:
    dh = _build_data(30)
    spec = StrategyScanSpec(strategy_class=BadOutputStrategy, params={})
    runner = SignalRunner()

    with pytest.raises(SignalRunnerError, match="Unsupported strategy signal output"):
        runner.run_signal("SBIN.NS", "15m", spec, dh)


def test_bars_since_trigger_metadata_is_populated() -> None:
    dh = _build_data(30)
    spec = StrategyScanSpec(strategy_class=ThresholdBuyStrategy, params={"threshold": 125.0})
    runner = SignalRunner()

    snap = runner.run_signal("RELIANCE.NS", "1D", spec, dh)

    assert snap.is_actionable is True
    assert snap.extras["bars_since_trigger"] is not None
    assert int(snap.extras["bars_since_trigger"]) > 0


def test_rsi_strategy_metrics_attached() -> None:
    from src.strategies.rsi_reversion import RSIReversionStrategy

    dh = _build_data(50)
    spec = StrategyScanSpec(
        strategy_class=RSIReversionStrategy,
        params={"rsi_period": 14, "oversold": 30, "overbought": 70},
    )
    runner = SignalRunner()

    snap = runner.run_signal("RELIANCE.NS", "1D", spec, dh)
    # Signal can be hold/buy depending on data; metric attachment should still work.
    assert "oversold_threshold" in snap.extras or "rsi_current" in snap.extras


def test_structured_signal_metadata_and_confidence_are_preserved() -> None:
    dh = _build_data(30)
    spec = StrategyScanSpec(strategy_class=StructuredBuyStrategy, params={})
    runner = SignalRunner()

    snap = runner.run_signal("TCS.NS", "1D", spec, dh)

    assert snap.signal == "buy"
    assert float(snap.extras["confidence"]) == 0.42
    assert snap.extras["rationale"] == "structured_buy"
    assert snap.extras["tags"] == ["scanner"]
    assert snap.extras["signal_metadata"]["source"] == "test"
