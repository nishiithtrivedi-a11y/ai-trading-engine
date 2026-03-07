from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.data.provider_config import DataProvidersConfig, ProviderEntry
from src.data.provider_factory import ProviderFactory
from src.scanners.data_gateway import DataGateway, ScannerDataGatewayError


def _write_ohlcv_csv(path: Path) -> None:
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=20, freq="D"),
            "open": [100 + i for i in range(20)],
            "high": [101 + i for i in range(20)],
            "low": [99 + i for i in range(20)],
            "close": [100.5 + i for i in range(20)],
            "volume": [1000 + i * 10 for i in range(20)],
        }
    )
    df.to_csv(path, index=False)


def _factory_for_csv() -> ProviderFactory:
    config = DataProvidersConfig(
        default_provider="csv",
        providers={
            "csv": ProviderEntry(enabled=True),
            "indian_csv": ProviderEntry(enabled=True),
        },
    )
    return ProviderFactory(config)


def _factory_for_upstox() -> ProviderFactory:
    config = DataProvidersConfig(
        default_provider="upstox",
        providers={
            "upstox": ProviderEntry(
                enabled=True,
                api_key="k",
                api_secret="s",
                access_token="t",
            )
        },
    )
    return ProviderFactory(config)


def test_csv_path_resolution_daily(tmp_path: Path) -> None:
    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(tmp_path),
        provider_factory=_factory_for_csv(),
    )

    path = gateway.resolve_csv_path("RELIANCE.NS", "1D")
    assert path == tmp_path / "RELIANCE_1D.csv"


def test_csv_path_resolution_intraday_suffix(tmp_path: Path) -> None:
    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(tmp_path),
        provider_factory=_factory_for_csv(),
    )

    path = gateway.resolve_csv_path("RELIANCE.NS", "5m")
    assert path == tmp_path / "RELIANCE_5M.csv"


def test_successful_csv_loading_returns_datahandler(tmp_path: Path) -> None:
    file_path = tmp_path / "RELIANCE_1D.csv"
    _write_ohlcv_csv(file_path)

    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(tmp_path),
        provider_factory=_factory_for_csv(),
    )

    dh = gateway.load_data("RELIANCE.NS", "1d")
    assert len(dh) == 20
    assert "close" in dh.data.columns


def test_missing_csv_file_raises_scanner_error(tmp_path: Path) -> None:
    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(tmp_path),
        provider_factory=_factory_for_csv(),
    )

    with pytest.raises(ScannerDataGatewayError, match="CSV data not found"):
        gateway.load_data("RELIANCE.NS", "1D")


def test_unsupported_provider_historical_fetch_is_graceful() -> None:
    gateway = DataGateway(
        provider_name="upstox",
        data_dir="data",
        provider_factory=_factory_for_upstox(),
    )

    with pytest.raises(
        ScannerDataGatewayError,
        match="does not support historical fetch yet",
    ):
        gateway.load_data("RELIANCE.NS", "1D")


def test_timeframe_normalization_and_mapping() -> None:
    assert DataGateway.normalize_timeframe("1d") == "1D"
    assert DataGateway.normalize_timeframe("60m") == "1h"
    assert DataGateway.timeframe_to_file_suffix("1D") == "1D"
    assert DataGateway.timeframe_to_file_suffix("5m") == "5M"


@pytest.mark.parametrize(
    "symbol,expected",
    [
        ("RELIANCE.NS", "RELIANCE"),
        ("reliance", "RELIANCE"),
        ("NSE_EQ|TCS", "TCS"),
    ],
)
def test_symbol_filename_normalization(symbol: str, expected: str) -> None:
    gateway = DataGateway(provider_name="csv", provider_factory=_factory_for_csv())
    assert gateway.symbol_to_file_stem(symbol) == expected


def test_invalid_timeframe_raises() -> None:
    gateway = DataGateway(provider_name="csv", provider_factory=_factory_for_csv())
    with pytest.raises(ValueError):
        gateway.resolve_csv_path("RELIANCE.NS", "2h")
