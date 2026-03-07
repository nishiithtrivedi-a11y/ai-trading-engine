import pandas as pd

from src.strategies.base_strategy import BaseStrategy, Signal


class DummyStrategy(BaseStrategy):
    def on_bar(self, data: pd.DataFrame, current_bar: pd.Series, bar_index: int) -> Signal:
        return Signal.HOLD


def test_session_vwap_resets_each_day():
    df = pd.DataFrame(
        {
            "timestamp": [
                "2025-01-15 09:15:00",
                "2025-01-15 09:20:00",
                "2025-01-16 09:15:00",
                "2025-01-16 09:20:00",
            ],
            "open": [100, 101, 200, 201],
            "high": [101, 102, 201, 202],
            "low": [99, 100, 199, 200],
            "close": [100, 102, 200, 202],
            "volume": [10, 10, 10, 10],
        }
    )

    vwap = BaseStrategy.vwap(df)

    assert round(float(vwap.iloc[0]), 4) == 100.0
    assert round(float(vwap.iloc[1]), 4) == 101.0
    assert round(float(vwap.iloc[2]), 4) == 200.0
    assert round(float(vwap.iloc[3]), 4) == 201.0


def test_typical_price_vwap_returns_series():
    df = pd.DataFrame(
        {
            "timestamp": [
                "2025-01-15 09:15:00",
                "2025-01-15 09:20:00",
            ],
            "open": [100, 101],
            "high": [101, 102],
            "low": [99, 100],
            "close": [100, 102],
            "volume": [10, 20],
        }
    )

    vwap = BaseStrategy.typical_price_vwap(df)
    assert len(vwap) == 2
    assert vwap.name == "vwap"