from __future__ import annotations

import pytest

from src.monitoring.config import (
    AlertEngineConfig,
    MonitoringConfig,
    MonitoringExportConfig,
    RegimeDetectorConfig,
    RelativeStrengthConfig,
    SnapshotConfig,
    WatchlistDefinition,
)
from src.monitoring.models import ScheduleMode, ScheduleSpec
from src.scanners.config import ScannerConfig


def test_watchlist_definition_requires_source() -> None:
    with pytest.raises(ValueError):
        WatchlistDefinition(name="empty")


def test_watchlist_definition_normalizes_inputs() -> None:
    wl = WatchlistDefinition(
        name="swing list",
        symbols=[" reliance.ns ", "TCS.NS", ""],
        tags=[" Swing ", "swing", "Positional"],
        default_timeframes=["1d", "60m"],
    )
    assert wl.symbols == ["RELIANCE.NS", "TCS.NS"]
    assert wl.tags == ["swing", "swing", "positional"]
    assert wl.default_timeframes == ["1D", "1h"]


def test_regime_detector_config_normalizes_timeframe() -> None:
    cfg = RegimeDetectorConfig(timeframe="daily")
    assert cfg.timeframe == "1D"


def test_relative_strength_weights_are_normalized() -> None:
    cfg = RelativeStrengthConfig(
        lookback_windows=[20, 60],
        lookback_weights={20: 2.0, 60: 1.0},
    )
    assert sum(cfg.lookback_weights.values()) == pytest.approx(1.0)
    assert cfg.lookback_weights[20] == pytest.approx(2.0 / 3.0)


def test_alert_config_validation() -> None:
    with pytest.raises(ValueError):
        AlertEngineConfig(min_opportunity_score=90, high_priority_score=80)

    valid = AlertEngineConfig(min_opportunity_score=70, high_priority_score=85)
    assert valid.enabled is True


def test_snapshot_config_validation() -> None:
    with pytest.raises(ValueError):
        SnapshotConfig(top_n=0)

    cfg = SnapshotConfig(top_n=5, min_score=50.0)
    assert cfg.top_n == 5


def test_export_config_requires_at_least_one_format() -> None:
    with pytest.raises(ValueError):
        MonitoringExportConfig(write_csv=False, write_json=False)


def test_monitoring_config_enabled_watchlists() -> None:
    cfg = MonitoringConfig(
        scanner_config=ScannerConfig(),
        watchlists=[
            WatchlistDefinition(name="a", symbols=["RELIANCE.NS"], enabled=True),
            WatchlistDefinition(name="b", symbols=["TCS.NS"], enabled=False),
        ],
        schedule=ScheduleSpec(name="manual", mode=ScheduleMode.MANUAL),
    )
    enabled = cfg.get_enabled_watchlists()
    assert len(enabled) == 1
    assert enabled[0].name == "a"
