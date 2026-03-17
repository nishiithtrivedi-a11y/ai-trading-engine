from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.data.provider_config import DataProvidersConfig, ProviderEntry
from src.data.provider_factory import ProviderFactory
from src.realtime.config import RealtimeConfig
from src.realtime.data_poller import DataPoller
from src.realtime.models import RealTimeMode
from src.scanners.data_gateway import DataGateway


def _write_ohlcv_csv(path: Path) -> None:
    frame = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=20, freq="D"),
            "open": [100 + i for i in range(20)],
            "high": [101 + i for i in range(20)],
            "low": [99 + i for i in range(20)],
            "close": [100.5 + i for i in range(20)],
            "volume": [1000 + i * 10 for i in range(20)],
        }
    )
    frame.to_csv(path, index=False)


def _csv_factory() -> ProviderFactory:
    cfg = DataProvidersConfig(
        default_provider="csv",
        providers={"csv": ProviderEntry(enabled=True)},
    )
    return ProviderFactory(cfg)


class _FailingFactory:
    def create(self, *_args, **_kwargs):
        raise RuntimeError("no live connection")


class _LiveSource:
    def load(self):
        return pd.DataFrame()

    def fetch_live(self, symbol: str, timeframe: str):
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "timestamp": "2026-03-07T09:30:00+05:30",
            "close": 123.45,
            "bars": 1,
        }


class _LiveSourceSymbolOnly:
    def load(self):
        return pd.DataFrame()

    def fetch_live(self, symbol: str):
        return {
            "symbol": symbol,
            "timestamp": "2026-03-07T09:30:00+05:30",
            "close": 222.22,
            "bars": 1,
        }


class _LiveFactory:
    def create(self, *_args, **_kwargs):
        return _LiveSource()


class _LiveFactorySymbolOnly:
    def create(self, *_args, **_kwargs):
        return _LiveSourceSymbolOnly()


class _LiveSourcePositionalNames:
    def load(self):
        return pd.DataFrame()

    def fetch_live(self, ticker: str, interval: str):
        return {
            "symbol": ticker,
            "timeframe": interval,
            "timestamp": "2026-03-07T09:31:00+05:30",
            "close": 333.33,
            "bars": 1,
        }


class _LiveFactoryPositionalNames:
    def create(self, *_args, **_kwargs):
        return _LiveSourcePositionalNames()


def test_off_mode_skips_polling() -> None:
    poller = DataPoller(provider_name="csv", provider_factory=_csv_factory())
    cfg = RealtimeConfig(enabled=False, mode=RealTimeMode.OFF)
    out = poller.poll(["RELIANCE.NS"], ["1D"], cfg)
    assert len(out.records) == 0
    assert out.mode == RealTimeMode.OFF
    assert out.warnings


def test_simulated_csv_polling_reads_latest_bar(tmp_path: Path) -> None:
    _write_ohlcv_csv(tmp_path / "RELIANCE_1D.csv")
    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(tmp_path),
        provider_factory=_csv_factory(),
    )
    poller = DataPoller(
        provider_name="csv",
        data_gateway=gateway,
        provider_factory=_csv_factory(),
    )
    cfg = RealtimeConfig(enabled=True, mode=RealTimeMode.SIMULATED)
    out = poller.poll(["RELIANCE.NS"], ["1D"], cfg)
    assert len(out.records) == 1
    assert out.records[0].success is True
    assert out.records[0].bars == 20
    assert out.records[0].close_price is not None


def test_polling_mode_live_create_failure_falls_back_to_historical(tmp_path: Path) -> None:
    _write_ohlcv_csv(tmp_path / "RELIANCE_1D.csv")
    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(tmp_path),
        provider_factory=_csv_factory(),
    )
    poller = DataPoller(
        provider_name="csv",
        data_gateway=gateway,
        provider_factory=_FailingFactory(),  # type: ignore[arg-type]
    )
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.POLLING,
        enable_live_provider=True,
    )
    out = poller.poll(["RELIANCE.NS"], ["1D"], cfg)
    assert len(out.records) == 1
    assert out.records[0].success is True
    assert any("fallback to historical snapshot" in w for w in out.warnings)


def test_polling_mode_uses_live_payload_if_available(tmp_path: Path) -> None:
    _write_ohlcv_csv(tmp_path / "RELIANCE_1D.csv")
    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(tmp_path),
        provider_factory=_csv_factory(),
    )
    poller = DataPoller(
        provider_name="zerodha",
        data_gateway=gateway,
        provider_factory=_LiveFactory(),  # type: ignore[arg-type]
    )
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.POLLING,
        enable_live_provider=True,
    )
    out = poller.poll(["RELIANCE.NS"], ["1D"], cfg)
    assert len(out.records) == 1
    assert out.records[0].source == "live_poll"
    assert out.records[0].close_price == 123.45


def test_polling_mode_supports_symbol_only_fetch_live_signature(tmp_path: Path) -> None:
    _write_ohlcv_csv(tmp_path / "RELIANCE_1D.csv")
    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(tmp_path),
        provider_factory=_csv_factory(),
    )
    poller = DataPoller(
        provider_name="zerodha",
        data_gateway=gateway,
        provider_factory=_LiveFactorySymbolOnly(),  # type: ignore[arg-type]
    )
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.POLLING,
        enable_live_provider=True,
    )
    out = poller.poll(["RELIANCE.NS"], ["1D"], cfg)
    assert len(out.records) == 1
    assert out.records[0].source == "live_poll"
    assert out.records[0].close_price == 222.22


def test_polling_mode_supports_positional_fetch_live_signature(tmp_path: Path) -> None:
    _write_ohlcv_csv(tmp_path / "RELIANCE_1D.csv")
    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(tmp_path),
        provider_factory=_csv_factory(),
    )
    poller = DataPoller(
        provider_name="zerodha",
        data_gateway=gateway,
        provider_factory=_LiveFactoryPositionalNames(),  # type: ignore[arg-type]
    )
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.POLLING,
        enable_live_provider=True,
    )
    out = poller.poll(["RELIANCE.NS"], ["1D"], cfg)
    assert len(out.records) == 1
    assert out.records[0].source == "live_poll"
    assert out.records[0].close_price == 333.33


def test_polling_mode_capability_guard_falls_back_when_provider_has_no_live_quotes(
    tmp_path: Path,
) -> None:
    _write_ohlcv_csv(tmp_path / "RELIANCE_1D.csv")
    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(tmp_path),
        provider_factory=_csv_factory(),
    )
    poller = DataPoller(
        provider_name="upstox",
        data_gateway=gateway,
        provider_factory=_LiveFactory(),  # should not be used due capability guard
    )
    cfg = RealtimeConfig(
        enabled=True,
        mode=RealTimeMode.POLLING,
        enable_live_provider=True,
    )
    out = poller.poll(["RELIANCE.NS"], ["1D"], cfg)
    assert len(out.records) == 1
    assert out.records[0].source == "historical_snapshot"
    assert out.records[0].success is True
    assert any("required capability set" in w for w in out.warnings)
