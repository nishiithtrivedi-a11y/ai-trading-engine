import pandas as pd

from src.utils.market_sessions import (
    add_session_columns,
    is_market_open,
    is_session_end,
    is_session_start,
)


def test_is_market_open_true():
    ts = pd.Timestamp("2025-01-15 10:00:00")
    assert is_market_open(ts) is True


def test_is_market_open_false_before_open():
    ts = pd.Timestamp("2025-01-15 09:00:00")
    assert is_market_open(ts) is False


def test_is_session_start_true():
    ts = pd.Timestamp("2025-01-15 09:15:00")
    assert is_session_start(ts) is True


def test_is_session_end_true():
    ts = pd.Timestamp("2025-01-15 15:30:00")
    assert is_session_end(ts) is True


def test_add_session_columns():
    df = pd.DataFrame(
        {
            "timestamp": [
                "2025-01-15 09:15:00",
                "2025-01-15 10:00:00",
                "2025-01-15 15:30:00",
            ],
            "open": [100, 101, 102],
            "high": [101, 102, 103],
            "low": [99, 100, 101],
            "close": [100.5, 101.5, 102.5],
            "volume": [1000, 1200, 900],
        }
    )

    out = add_session_columns(df)
    assert "session_date" in out.columns
    assert "in_market_hours" in out.columns
    assert bool(out["is_market_open_bar"].iloc[0]) is True
    assert bool(out["is_market_close_bar"].iloc[-1]) is True