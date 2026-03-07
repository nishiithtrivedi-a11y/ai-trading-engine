from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.provider_config import DataProvidersConfig, ProviderEntry
from src.data.provider_factory import ProviderFactory
from src.scanners.config import ScannerConfig, SetupMode, StrategyScanSpec
from src.scanners.data_gateway import DataGateway
from src.scanners.engine import StockScannerEngine
from src.strategies.base_strategy import BaseStrategy, Signal


class AlwaysBuyStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        return Signal.BUY


class AlwaysHoldStrategy(BaseStrategy):
    def on_bar(self, data, current_bar, bar_index):
        return Signal.HOLD


def _factory_for_csv() -> ProviderFactory:
    config = DataProvidersConfig(
        default_provider="csv",
        providers={
            "csv": ProviderEntry(enabled=True),
            "indian_csv": ProviderEntry(enabled=True),
        },
    )
    return ProviderFactory(config)


def _write_symbol_csv(data_dir: Path, symbol: str, timeframe_suffix: str = "1D") -> None:
    stem = symbol.replace(".NS", "")
    path = data_dir / f"{stem}_{timeframe_suffix}.csv"
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=40, freq="D"),
            "open": [100 + i for i in range(40)],
            "high": [101 + i for i in range(40)],
            "low": [99 + i for i in range(40)],
            "close": [100.5 + i for i in range(40)],
            "volume": [1000 + i * 10 for i in range(40)],
        }
    )
    df.to_csv(path, index=False)


def _write_universe_csv(path: Path, symbols: list[str]) -> None:
    pd.DataFrame({"symbol": symbols}).to_csv(path, index=False)


def test_small_csv_scan_returns_actionable_opportunities(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    symbols = ["RELIANCE.NS", "TCS.NS"]
    for sym in symbols:
        _write_symbol_csv(data_dir, sym, "1D")

    universe_file = tmp_path / "universe.csv"
    _write_universe_csv(universe_file, symbols)

    cfg = ScannerConfig(
        universe_name="custom",
        custom_universe_file=str(universe_file),
        provider_name="csv",
        data_dir=str(data_dir),
        min_history_bars=2,
        top_n=10,
        setup_mode=SetupMode.FIXED_PCT,
        strategy_specs=[
            StrategyScanSpec(strategy_class=AlwaysBuyStrategy, timeframes=["1D"])
        ],
    )

    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(data_dir),
        provider_factory=_factory_for_csv(),
    )

    engine = StockScannerEngine(scanner_config=cfg, data_gateway=gateway)
    result = engine.run()

    assert len(result.opportunities) == 2
    assert result.num_symbols_scanned == 2
    assert result.num_jobs == 2
    assert all(o.signal == "buy" for o in result.opportunities)


def test_ranking_applied_on_results(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    symbols = ["RELIANCE.NS", "TCS.NS"]
    for sym in symbols:
        _write_symbol_csv(data_dir, sym, "1D")

    universe_file = tmp_path / "universe.csv"
    _write_universe_csv(universe_file, symbols)

    cfg = ScannerConfig(
        universe_name="custom",
        custom_universe_file=str(universe_file),
        provider_name="csv",
        data_dir=str(data_dir),
        min_history_bars=2,
        setup_mode=SetupMode.FIXED_PCT,
        strategy_specs=[StrategyScanSpec(strategy_class=AlwaysBuyStrategy, timeframes=["1D"])],
    )

    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(data_dir),
        provider_factory=_factory_for_csv(),
    )

    result = StockScannerEngine(scanner_config=cfg, data_gateway=gateway).run()

    assert [o.rank for o in result.opportunities] == [1, 2]


def test_non_actionable_universe_results_empty(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    symbols = ["INFY.NS"]
    _write_symbol_csv(data_dir, "INFY.NS", "1D")

    universe_file = tmp_path / "universe.csv"
    _write_universe_csv(universe_file, symbols)

    cfg = ScannerConfig(
        universe_name="custom",
        custom_universe_file=str(universe_file),
        provider_name="csv",
        data_dir=str(data_dir),
        min_history_bars=2,
        setup_mode=SetupMode.FIXED_PCT,
        strategy_specs=[StrategyScanSpec(strategy_class=AlwaysHoldStrategy, timeframes=["1D"])],
    )

    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(data_dir),
        provider_factory=_factory_for_csv(),
    )

    result = StockScannerEngine(scanner_config=cfg, data_gateway=gateway).run()

    assert result.opportunities == []
    assert result.num_errors == 0


def test_missing_csv_is_collected_as_error_when_skip_enabled(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    symbols = ["RELIANCE.NS", "MISSING.NS"]
    _write_symbol_csv(data_dir, "RELIANCE.NS", "1D")

    universe_file = tmp_path / "universe.csv"
    _write_universe_csv(universe_file, symbols)

    cfg = ScannerConfig(
        universe_name="custom",
        custom_universe_file=str(universe_file),
        provider_name="csv",
        data_dir=str(data_dir),
        min_history_bars=2,
        skip_on_data_error=True,
        setup_mode=SetupMode.FIXED_PCT,
        strategy_specs=[StrategyScanSpec(strategy_class=AlwaysBuyStrategy, timeframes=["1D"])],
    )

    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(data_dir),
        provider_factory=_factory_for_csv(),
    )

    result = StockScannerEngine(scanner_config=cfg, data_gateway=gateway).run()

    assert len(result.opportunities) == 1
    assert result.num_errors >= 1


def test_scan_result_export_ready_shape(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _write_symbol_csv(data_dir, "RELIANCE.NS", "1D")

    universe_file = tmp_path / "universe.csv"
    _write_universe_csv(universe_file, ["RELIANCE.NS"])

    cfg = ScannerConfig(
        universe_name="custom",
        custom_universe_file=str(universe_file),
        provider_name="csv",
        data_dir=str(data_dir),
        min_history_bars=2,
        setup_mode=SetupMode.FIXED_PCT,
        strategy_specs=[StrategyScanSpec(strategy_class=AlwaysBuyStrategy, timeframes=["1D"])],
    )

    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(data_dir),
        provider_factory=_factory_for_csv(),
    )

    result = StockScannerEngine(scanner_config=cfg, data_gateway=gateway).run()
    payload = result.to_dict()

    assert "opportunities" in payload
    assert isinstance(payload["opportunities"], list)
    if payload["opportunities"]:
        row = payload["opportunities"][0]
        assert "symbol" in row
        assert "entry_price" in row
        assert "score" in row
        assert "score_signal" in row
        assert "score_rr" in row
        assert "score_trend" in row
        assert "score_liquidity" in row
        assert "score_freshness" in row
