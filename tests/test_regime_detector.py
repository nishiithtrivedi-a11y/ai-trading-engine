from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.core.data_handler import DataHandler
from src.data.provider_config import DataProvidersConfig, ProviderEntry
from src.data.provider_factory import ProviderFactory
from src.monitoring.config import RegimeDetectorConfig
from src.monitoring.models import RegimeState
from src.monitoring.regime_detector import RegimeDetector
from src.scanners.data_gateway import DataGateway


def _make_data(close_values: list[float]) -> DataHandler:
    count = len(close_values)
    df = pd.DataFrame(
        {
            "open": close_values,
            "high": [v * 1.01 for v in close_values],
            "low": [v * 0.99 for v in close_values],
            "close": close_values,
            "volume": [1000 + i * 10 for i in range(count)],
        },
        index=pd.date_range("2026-01-01", periods=count, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def _factory_for_csv() -> ProviderFactory:
    cfg = DataProvidersConfig(
        default_provider="csv",
        providers={"csv": ProviderEntry(enabled=True), "indian_csv": ProviderEntry(enabled=True)},
    )
    return ProviderFactory(cfg)


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
            "volume": [1000 + i * 5 for i in range(len(closes))],
        }
    )
    df.to_csv(path, index=False)


def test_detect_bullish_regime() -> None:
    close = [100 + i * 1.2 for i in range(120)]
    dh = _make_data(close)
    cfg = RegimeDetectorConfig(
        trend_fast_period=10,
        trend_slow_period=30,
        volatility_period=14,
        high_volatility_threshold=0.2,
        low_volatility_threshold=0.0001,
    )

    assessment = RegimeDetector().detect(dh, cfg)
    assert assessment.regime == RegimeState.BULLISH


def test_detect_bearish_regime() -> None:
    close = [220 - i * 1.0 for i in range(120)]
    dh = _make_data(close)
    cfg = RegimeDetectorConfig(
        trend_fast_period=10,
        trend_slow_period=30,
        volatility_period=14,
        high_volatility_threshold=0.2,
        low_volatility_threshold=0.0001,
    )

    assessment = RegimeDetector().detect(dh, cfg)
    assert assessment.regime == RegimeState.BEARISH


def test_detect_high_volatility_regime() -> None:
    close: list[float] = []
    value = 100.0
    for i in range(140):
        value = value * (1.08 if i % 2 == 0 else 0.92)
        close.append(value)

    dh = _make_data(close)
    cfg = RegimeDetectorConfig(
        trend_fast_period=10,
        trend_slow_period=30,
        volatility_period=20,
        high_volatility_threshold=0.05,
        low_volatility_threshold=0.001,
    )

    assessment = RegimeDetector().detect(dh, cfg)
    assert assessment.regime == RegimeState.HIGH_VOLATILITY


def test_detect_from_gateway_falls_back_when_benchmark_missing(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    closes = [100 + i * 0.8 for i in range(120)]
    _write_symbol_csv(data_dir, "RELIANCE.NS", closes)

    gateway = DataGateway(
        provider_name="csv",
        data_dir=str(data_dir),
        provider_factory=_factory_for_csv(),
    )

    cfg = RegimeDetectorConfig(
        benchmark_symbol="NIFTY50.NS",
        trend_fast_period=10,
        trend_slow_period=30,
        volatility_period=14,
        use_benchmark=True,
        fallback_to_symbol=True,
    )

    assessment = RegimeDetector().detect_from_gateway("RELIANCE.NS", gateway, cfg)
    assert assessment.metadata["based_on"] == "symbol_fallback"
    assert assessment.regime in {
        RegimeState.BULLISH,
        RegimeState.LOW_VOLATILITY,
        RegimeState.UNKNOWN,
    }
