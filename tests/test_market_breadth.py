from __future__ import annotations

import pandas as pd

from src.core.data_handler import DataHandler
from src.market_intelligence.config import BreadthConfig
from src.market_intelligence.market_breadth import MarketBreadthAnalyzer
from src.market_intelligence.models import BreadthState


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


def test_market_breadth_metrics_basic() -> None:
    data = {
        "A.NS": _dh([100, 101, 102, 103, 104]),
        "B.NS": _dh([100, 99, 98, 97, 96]),
        "C.NS": _dh([100, 100, 100, 100, 100]),
    }
    cfg = BreadthConfig(moving_average_period=3, ad_line_lookback=5, new_high_low_lookback=5)
    snap = MarketBreadthAnalyzer().analyze(data, cfg)

    assert snap.metrics.advancing_count == 1
    assert snap.metrics.declining_count == 1
    assert snap.metrics.unchanged_count == 1
    assert snap.metrics.universe_size == 3
    assert snap.breadth_state in {BreadthState.STRONG, BreadthState.NEUTRAL, BreadthState.WEAK}


def test_market_breadth_state_strong() -> None:
    data = {
        "A.NS": _dh([100, 101, 102, 103, 104, 105]),
        "B.NS": _dh([100, 101, 102, 103, 104, 106]),
        "C.NS": _dh([100, 100.5, 101, 102, 103, 104]),
    }
    cfg = BreadthConfig(
        moving_average_period=3,
        strong_ad_ratio_threshold=1.0,
        strong_pct_above_ma_threshold=50.0,
    )
    snap = MarketBreadthAnalyzer().analyze(data, cfg)
    assert snap.breadth_state == BreadthState.STRONG


def test_market_breadth_empty_universe_returns_unknown() -> None:
    cfg = BreadthConfig()
    snap = MarketBreadthAnalyzer().analyze({}, cfg)
    assert snap.breadth_state == BreadthState.UNKNOWN
    assert snap.metrics.universe_size == 0
