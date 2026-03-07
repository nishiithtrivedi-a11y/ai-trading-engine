from __future__ import annotations

import pandas as pd

from src.core.data_handler import DataHandler
from src.market_intelligence.config import SectorRotationConfig
from src.market_intelligence.models import SectorRotationState
from src.market_intelligence.sector_rotation import SectorRotationAnalyzer


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


def test_sector_rotation_ranking() -> None:
    data = {
        "A.NS": _dh([100 + i * 0.9 for i in range(180)]),  # strong
        "B.NS": _dh([100 + i * 0.8 for i in range(180)]),  # strong
        "C.NS": _dh([100 + i * 0.3 for i in range(180)]),  # weaker
        "D.NS": _dh([100 + i * 0.2 for i in range(180)]),
    }
    sector_map = {"Tech": ["A.NS", "B.NS"], "Banks": ["C.NS", "D.NS"]}
    benchmark = _dh([100 + i * 0.4 for i in range(180)])

    cfg = SectorRotationConfig(lookback_windows=[20, 60, 120])
    rows = SectorRotationAnalyzer().analyze(sector_map, data, cfg, benchmark_data=benchmark)

    assert len(rows) == 2
    assert rows[0].sector == "Tech"
    assert rows[0].rank == 1
    assert rows[0].state in {
        SectorRotationState.LEADING,
        SectorRotationState.WEAKENING,
        SectorRotationState.LAGGING,
    }


def test_sector_rotation_without_benchmark() -> None:
    data = {
        "A.NS": _dh([100 + i * 0.5 for i in range(120)]),
        "B.NS": _dh([100 + i * 0.2 for i in range(120)]),
    }
    sector_map = {"Energy": ["A.NS"], "IT": ["B.NS"]}
    cfg = SectorRotationConfig(lookback_windows=[20, 60], lookback_weights={20: 0.6, 60: 0.4})

    rows = SectorRotationAnalyzer().analyze(sector_map, data, cfg, benchmark_data=None)
    assert len(rows) == 2
    assert all(row.benchmark_relative_return is None for row in rows)
