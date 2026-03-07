from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.monitoring.config import (
    AlertEngineConfig,
    MonitoringConfig,
    RegimeDetectorConfig,
    RelativeStrengthConfig,
    SnapshotConfig,
    WatchlistDefinition,
)
from src.monitoring.market_monitor import MarketMonitor
from src.scanners.config import ScannerConfig, SetupMode, StrategyScanSpec
from src.strategies.base_strategy import BaseStrategy, Signal


class AlwaysBuyStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        return Signal.BUY


def _write_symbol_csv(data_dir: Path, symbol: str, closes: list[float]) -> None:
    stem = symbol.replace(".NS", "")
    path = data_dir / f"{stem}_1D.csv"
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=len(closes), freq="D"),
            "open": closes,
            "high": [v * 1.01 for v in closes],
            "low": [v * 0.99 for v in closes],
            "close": closes,
            "volume": [1000 + i * 8 for i in range(len(closes))],
        }
    )
    df.to_csv(path, index=False)


def _scanner_config(data_dir: Path) -> ScannerConfig:
    return ScannerConfig(
        provider_name="csv",
        data_dir=str(data_dir),
        universe_name="nifty50",
        min_history_bars=2,
        setup_mode=SetupMode.FIXED_PCT,
        strategy_specs=[StrategyScanSpec(strategy_class=AlwaysBuyStrategy, timeframes=["1D"])],
    )


def test_market_monitor_happy_path_csv_scan(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _write_symbol_csv(data_dir, "RELIANCE.NS", [100 + i * 0.8 for i in range(180)])
    _write_symbol_csv(data_dir, "TCS.NS", [100 + i * 0.5 for i in range(180)])
    _write_symbol_csv(data_dir, "NIFTY50.NS", [100 + i * 0.3 for i in range(180)])

    cfg = MonitoringConfig(
        scanner_config=_scanner_config(data_dir),
        watchlists=[
            WatchlistDefinition(name="focus", symbols=["RELIANCE.NS", "TCS.NS"]),
        ],
        alerts=AlertEngineConfig(min_opportunity_score=0.0, high_priority_score=95.0),
        regime=RegimeDetectorConfig(benchmark_symbol="NIFTY50.NS"),
        relative_strength=RelativeStrengthConfig(benchmark_symbol="NIFTY50.NS"),
        snapshot=SnapshotConfig(top_n=5, min_score=0.0),
    )

    monitor = MarketMonitor(config=cfg)
    result = monitor.run(export=False, watchlist_names=["focus"])

    assert result.scan_result is not None
    assert result.scan_result.num_symbols_scanned == 2
    assert len(result.scan_result.opportunities) == 2
    assert result.snapshot is not None
    assert len(result.snapshot.top_picks) >= 1
    assert len(result.relative_strength) == 2
    assert result.regime_assessment is not None


def test_market_monitor_graceful_when_benchmark_missing(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    _write_symbol_csv(data_dir, "INFY.NS", [100 + i * 0.4 for i in range(180)])

    cfg = MonitoringConfig(
        scanner_config=_scanner_config(data_dir),
        watchlists=[WatchlistDefinition(name="single", symbols=["INFY.NS"])],
        alerts=AlertEngineConfig(min_opportunity_score=0.0),
        regime=RegimeDetectorConfig(
            benchmark_symbol="MISSINGBENCH.NS",
            use_benchmark=True,
            fallback_to_symbol=True,
        ),
        relative_strength=RelativeStrengthConfig(
            benchmark_symbol="MISSINGBENCH.NS",
            allow_missing_benchmark=True,
        ),
    )

    result = MarketMonitor(config=cfg).run(export=False, watchlist_names=["single"])
    assert result.scan_result is not None
    assert result.regime_assessment is not None
    assert len(result.relative_strength) == 1
