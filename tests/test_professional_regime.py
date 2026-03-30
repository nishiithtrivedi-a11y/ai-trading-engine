from __future__ import annotations

import numpy as np
import pandas as pd

from src.market_intelligence.professional_regime import (
    ProfessionalRegime,
    ProfessionalRegimeClassifier,
    legacy_to_professional_regime,
)


def _make_ohlcv(
    *,
    bars: int = 320,
    slope: float = 0.08,
    noise_scale: float = 0.15,
) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    idx = pd.date_range("2024-01-01", periods=bars, freq="5min", tz="UTC")
    base = 100.0 + np.arange(bars) * slope
    noise = rng.normal(0.0, noise_scale, size=bars)
    close = base + noise
    open_ = close + rng.normal(0.0, noise_scale * 0.2, size=bars)
    high = np.maximum(open_, close) + np.abs(rng.normal(0.0, noise_scale * 0.8, size=bars))
    low = np.minimum(open_, close) - np.abs(rng.normal(0.0, noise_scale * 0.8, size=bars))
    volume = rng.integers(1000, 2000, size=bars)
    return pd.DataFrame(
        {
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": volume,
        },
        index=idx,
    )


def test_legacy_mapping_smoke() -> None:
    assert legacy_to_professional_regime("bullish_trending") == ProfessionalRegime.BULL_TREND
    assert legacy_to_professional_regime("bearish_volatile") == ProfessionalRegime.BEAR_VOLATILE
    assert legacy_to_professional_regime("rangebound") == ProfessionalRegime.SIDEWAYS_RANGE


def test_classifier_identifies_bullish_regime() -> None:
    clf = ProfessionalRegimeClassifier()
    df = _make_ohlcv(slope=0.12, noise_scale=0.10)
    snap = clf.detect(df, symbol="RELIANCE")
    assert snap.regime in {ProfessionalRegime.BULL_TREND, ProfessionalRegime.BULL_VOLATILE}


def test_classifier_can_detect_reversal() -> None:
    clf = ProfessionalRegimeClassifier()
    first = _make_ohlcv(bars=180, slope=-0.12, noise_scale=0.08)
    second = _make_ohlcv(bars=180, slope=0.18, noise_scale=0.16)
    second.index = pd.date_range(first.index[-1] + pd.Timedelta(minutes=5), periods=180, freq="5min", tz="UTC")
    df = pd.concat([first, second], axis=0)

    snap = clf.detect(df, symbol="INFY")
    assert snap.regime in {
        ProfessionalRegime.REVERSAL,
        ProfessionalRegime.BULL_VOLATILE,
        ProfessionalRegime.BEAR_VOLATILE,
        ProfessionalRegime.BULL_TREND,
    }


def test_classifier_missing_columns_returns_unknown() -> None:
    clf = ProfessionalRegimeClassifier()
    idx = pd.date_range("2024-01-01", periods=150, freq="5min", tz="UTC")
    df = pd.DataFrame({"close": np.linspace(100, 101, 150)}, index=idx)
    snap = clf.detect(df, symbol="TEST")
    assert snap.regime == ProfessionalRegime.UNKNOWN
