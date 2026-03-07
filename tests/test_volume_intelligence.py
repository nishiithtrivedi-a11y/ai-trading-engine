from __future__ import annotations

import pandas as pd

from src.core.data_handler import DataHandler
from src.market_intelligence.config import VolumeIntelligenceConfig
from src.market_intelligence.models import VolumeSignalType
from src.market_intelligence.volume_intelligence import VolumeIntelligenceAnalyzer


def _dh(close_values: list[float], volume_values: list[float]) -> DataHandler:
    n = len(close_values)
    df = pd.DataFrame(
        {
            "open": close_values,
            "high": [v * 1.01 for v in close_values],
            "low": [v * 0.99 for v in close_values],
            "close": close_values,
            "volume": volume_values,
        },
        index=pd.date_range("2026-01-01", periods=n, freq="D", name="timestamp"),
    )
    return DataHandler(df)


def test_volume_spike_detection() -> None:
    close = [100 + i * 0.2 for i in range(40)]
    volume = [1000.0 for _ in range(39)] + [3000.0]
    dh = _dh(close, volume)

    cfg = VolumeIntelligenceConfig(spike_lookback=20, spike_multiple_threshold=1.8)
    snap = VolumeIntelligenceAnalyzer().analyze_symbol("RELIANCE.NS", dh, cfg)

    signal_types = {s.signal_type for s in snap.signals}
    assert VolumeSignalType.SPIKE in signal_types
    assert snap.metrics["volume_ratio"] > 1.8


def test_accumulation_and_distribution_metrics_exist() -> None:
    close = [100, 101, 102, 103, 104, 103, 102, 101, 100, 99, 98, 97, 98, 99, 100]
    volume = [1500, 1600, 1700, 1800, 2000, 800, 700, 600, 500, 600, 700, 800, 1500, 1600, 1700]
    dh = _dh(close, volume)

    cfg = VolumeIntelligenceConfig(
        spike_lookback=5,
        accumulation_window=10,
        distribution_window=10,
        vw_momentum_window=5,
    )
    snap = VolumeIntelligenceAnalyzer().analyze_symbol("TCS.NS", dh, cfg)

    assert "accumulation_strength" in snap.metrics
    assert "distribution_strength" in snap.metrics
    assert "vw_momentum" in snap.metrics


def test_analyze_many_graceful() -> None:
    good = _dh([100 + i * 0.2 for i in range(30)], [1000 + i for i in range(30)])
    bad = _dh([1.0, 2.0, 3.0], [100.0, 100.0, 100.0])

    rows = VolumeIntelligenceAnalyzer().analyze_many(
        {"GOOD.NS": good, "BAD.NS": bad},
        VolumeIntelligenceConfig(spike_lookback=5),
    )
    assert len(rows) == 1
    assert rows[0].symbol == "GOOD.NS"
