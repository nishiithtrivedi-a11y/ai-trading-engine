from __future__ import annotations

import pandas as pd

from src.core.data_handler import DataHandler
from src.market_intelligence.config import VolatilityRegimeConfig
from src.market_intelligence.models import VolatilityRegimeType
from src.market_intelligence.volatility_regime import VolatilityRegimeAnalyzer


def _dh(close_values: list[float]) -> DataHandler:
    n = len(close_values)
    df = pd.DataFrame(
        {
            "open": close_values,
            "high": [v * 1.01 for v in close_values],
            "low": [v * 0.99 for v in close_values],
            "close": close_values,
            "volume": [1000 + i for i in range(n)],
        },
        index=pd.date_range("2026-01-01", periods=n, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def test_detect_low_or_contraction_regime() -> None:
    close = [100 + i * 0.1 for i in range(140)]
    dh = _dh(close)
    cfg = VolatilityRegimeConfig(
        atr_period=14,
        atr_baseline_period=60,
        realized_vol_window=20,
        low_vol_threshold=0.02,
        high_vol_threshold=0.08,
        contraction_atr_ratio=0.95,
    )

    snap = VolatilityRegimeAnalyzer().detect("NIFTY50.NS", dh, cfg)
    assert snap.regime in {VolatilityRegimeType.LOW, VolatilityRegimeType.CONTRACTION}
    assert 0 <= snap.state_score <= 100


def test_detect_high_or_expanding_regime() -> None:
    close: list[float] = []
    x = 100.0
    for i in range(180):
        x = x * (1.06 if i % 2 == 0 else 0.94)
        close.append(x)

    dh = _dh(close)
    cfg = VolatilityRegimeConfig(
        atr_period=14,
        atr_baseline_period=60,
        realized_vol_window=20,
        low_vol_threshold=0.01,
        high_vol_threshold=0.03,
        expansion_atr_ratio=1.05,
    )
    snap = VolatilityRegimeAnalyzer().detect("NIFTY50.NS", dh, cfg)
    assert snap.regime in {VolatilityRegimeType.HIGH, VolatilityRegimeType.EXPANDING}
