"""Tests for the DataHandler module."""

import pandas as pd
import numpy as np
import pytest

from src.core.data_handler import DataHandler
from src.utils.validators import DataValidationError


def make_ohlcv(n: int = 50, start_price: float = 100.0) -> pd.DataFrame:
    """Create a simple OHLCV DataFrame for testing."""
    dates = pd.bdate_range("2023-01-01", periods=n)
    prices = start_price + np.cumsum(np.random.default_rng(42).normal(0, 1, n))
    prices = np.maximum(prices, 1.0)

    df = pd.DataFrame({
        "open": prices + np.random.default_rng(1).uniform(-0.5, 0.5, n),
        "high": prices + np.abs(np.random.default_rng(2).normal(1, 0.5, n)),
        "low": prices - np.abs(np.random.default_rng(3).normal(1, 0.5, n)),
        "close": prices,
        "volume": np.random.default_rng(4).integers(1000, 100000, n),
    }, index=dates)
    df.index.name = "timestamp"

    # Ensure OHLC consistency
    df["high"] = df[["open", "high", "close"]].max(axis=1) + 0.01
    df["low"] = df[["open", "low", "close"]].min(axis=1) - 0.01
    df["low"] = df["low"].clip(lower=0.01)

    return df


class TestDataHandler:

    def test_load_from_dataframe(self):
        df = make_ohlcv(50)
        dh = DataHandler(data=df)
        assert len(dh) == 50

    def test_get_current_bar(self):
        df = make_ohlcv(50)
        dh = DataHandler(data=df)
        bar = dh.get_current_bar()
        assert "open" in bar.index
        assert "close" in bar.index

    def test_advance_and_has_next(self):
        df = make_ohlcv(5)
        dh = DataHandler(data=df)
        assert dh.has_next()
        for _ in range(4):
            assert dh.advance()
        assert not dh.has_next()
        assert not dh.advance()

    def test_get_lookback(self):
        df = make_ohlcv(20)
        dh = DataHandler(data=df)
        dh.current_index = 10
        lookback = dh.get_lookback(5)
        assert len(lookback) == 5
        assert lookback.index[-1] == df.index[10]

    def test_lookback_at_start_clipped(self):
        df = make_ohlcv(20)
        dh = DataHandler(data=df)
        dh.current_index = 2
        lookback = dh.get_lookback(10)
        assert len(lookback) == 3  # Only bars 0, 1, 2

    def test_get_data_up_to_current(self):
        df = make_ohlcv(20)
        dh = DataHandler(data=df)
        dh.current_index = 5
        data = dh.get_data_up_to_current()
        assert len(data) == 6  # Bars 0-5 inclusive

    def test_reset(self):
        df = make_ohlcv(10)
        dh = DataHandler(data=df)
        dh.current_index = 5
        dh.reset()
        assert dh.current_index == 0

    def test_rejects_empty_dataframe(self):
        df = pd.DataFrame()
        with pytest.raises(DataValidationError, match="empty"):
            DataHandler(data=df)

    def test_rejects_missing_columns(self):
        df = pd.DataFrame({
            "open": [1],
            "close": [1],
        }, index=pd.DatetimeIndex(["2023-01-01"]))
        df.index.name = "timestamp"

        with pytest.raises(DataValidationError, match="Missing required columns"):
            DataHandler(data=df)

    def test_rejects_duplicate_timestamps(self):
        dates = pd.DatetimeIndex(["2023-01-01", "2023-01-01", "2023-01-03"])
        df = pd.DataFrame({
            "open": [10, 11, 12],
            "high": [11, 12, 13],
            "low": [9, 10, 11],
            "close": [10.5, 11.5, 12.5],
            "volume": [100, 200, 300],
        }, index=dates)
        df.index.name = "timestamp"

        with pytest.raises(DataValidationError, match="duplicate"):
            DataHandler(data=df)

    def test_rejects_negative_prices(self):
        dates = pd.DatetimeIndex(["2023-01-01", "2023-01-02"])
        df = pd.DataFrame({
            "open": [10, -5],
            "high": [11, 12],
            "low": [9, 10],
            "close": [10.5, 11.5],
            "volume": [100, 200],
        }, index=dates)
        df.index.name = "timestamp"

        with pytest.raises(DataValidationError, match="non-positive"):
            DataHandler(data=df)

    def test_sorts_unsorted_data(self):
        dates = pd.DatetimeIndex(["2023-01-03", "2023-01-01", "2023-01-02"])
        df = pd.DataFrame({
            "open": [12, 10, 11],
            "high": [13, 11, 12],
            "low": [11, 9, 10],
            "close": [12.5, 10.5, 11.5],
            "volume": [300, 100, 200],
        }, index=dates)
        df.index.name = "timestamp"

        dh = DataHandler(data=df)
        assert dh.data.index[0] == pd.Timestamp("2023-01-01")
        assert dh.data.index[-1] == pd.Timestamp("2023-01-03")
