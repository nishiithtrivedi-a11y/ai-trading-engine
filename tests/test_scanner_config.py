from __future__ import annotations

import pytest

from src.scanners.config import ExportConfig, ScannerConfig, StrategyScanSpec, normalize_timeframe
from src.strategies.base_strategy import BaseStrategy, Signal


class DummyStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        return Signal.HOLD


def test_normalize_timeframe_aliases() -> None:
    assert normalize_timeframe("1d") == "1D"
    assert normalize_timeframe("60m") == "1h"
    assert normalize_timeframe("15m") == "15m"


def test_normalize_timeframe_invalid_raises() -> None:
    with pytest.raises(ValueError):
        normalize_timeframe("2h")


def test_export_config_requires_at_least_one_format() -> None:
    with pytest.raises(ValueError):
        ExportConfig(write_csv=False, write_json=False)


def test_strategy_scan_spec_normalizes_timeframes() -> None:
    spec = StrategyScanSpec(
        strategy_class=DummyStrategy,
        timeframes=["1d", "60m"],
    )
    assert spec.timeframes == ["1D", "1h"]
    assert spec.strategy_name == "DummyStrategy"


def test_scanner_config_validates_and_normalizes_weights() -> None:
    cfg = ScannerConfig(
        score_weights={"signal": 2.0, "risk_reward": 1.0},
    )
    assert cfg.timeframes == ["5m", "15m", "1h", "1D"]
    assert cfg.score_weights["signal"] == pytest.approx(2.0 / 3.0)
    assert cfg.score_weights["risk_reward"] == pytest.approx(1.0 / 3.0)


def test_scanner_config_negative_weight_raises() -> None:
    with pytest.raises(ValueError):
        ScannerConfig(score_weights={"signal": -1.0, "risk_reward": 1.0})


def test_get_effective_timeframes_uses_spec_override() -> None:
    cfg = ScannerConfig(timeframes=["1D"])
    spec = StrategyScanSpec(strategy_class=DummyStrategy, timeframes=["15m"])
    assert cfg.get_effective_timeframes(spec) == ["15m"]


def test_get_effective_timeframes_falls_back_to_global() -> None:
    cfg = ScannerConfig(timeframes=["1D", "1h"])
    spec = StrategyScanSpec(strategy_class=DummyStrategy)
    assert cfg.get_effective_timeframes(spec) == ["1D", "1h"]
