"""Tests for data source implementations and stubs."""

import pytest
import pandas as pd
from datetime import datetime

from src.data.sources import ZerodhaDataSource, UpstoxDataSource
from src.data.base import Timeframe


# ---------------------------------------------------------------------------
# Tests — ZerodhaDataSource (now fully implemented)
# ---------------------------------------------------------------------------

class TestZerodhaDataSource:
    """Tests for the implemented Zerodha data source.

    These tests validate instantiation, configuration, internal helpers,
    and health checks without actually calling the remote Kite API.
    """

    def test_instantiation(self):
        source = ZerodhaDataSource("key", "secret", "token")
        assert source.api_key == "key"
        assert source.api_secret == "secret"
        assert source.access_token == "token"
        assert source.exchange == "NSE"

    def test_default_parameters(self):
        source = ZerodhaDataSource("k", "s", "t")
        assert source.default_symbol == "RELIANCE"
        assert source.default_timeframe == Timeframe.DAILY
        assert source.default_days == 365

    def test_custom_parameters(self):
        source = ZerodhaDataSource(
            "k", "s", "t",
            default_symbol="TCS",
            default_timeframe=Timeframe.MINUTE_5,
            default_days=30,
            exchange="BSE",
        )
        assert source.default_symbol == "TCS"
        assert source.default_timeframe == Timeframe.MINUTE_5
        assert source.default_days == 30
        assert source.exchange == "BSE"

    def test_kite_interval_mapping(self):
        assert ZerodhaDataSource._kite_interval(Timeframe.MINUTE_1) == "minute"
        assert ZerodhaDataSource._kite_interval(Timeframe.MINUTE_5) == "5minute"
        assert ZerodhaDataSource._kite_interval(Timeframe.MINUTE_15) == "15minute"
        assert ZerodhaDataSource._kite_interval(Timeframe.HOURLY) == "60minute"
        assert ZerodhaDataSource._kite_interval(Timeframe.DAILY) == "day"

    def test_normalize_df_empty(self):
        source = ZerodhaDataSource("k", "s", "t")
        df = source._normalize_df([])
        assert isinstance(df, pd.DataFrame)
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert len(df) == 0

    def test_normalize_df_with_records(self):
        source = ZerodhaDataSource("k", "s", "t")
        records = [
            {"date": datetime(2025, 1, 2, 9, 15), "open": 100, "high": 105,
             "low": 98, "close": 103, "volume": 5000},
            {"date": datetime(2025, 1, 2, 9, 20), "open": 103, "high": 107,
             "low": 101, "close": 106, "volume": 3000},
        ]
        df = source._normalize_df(records)
        assert len(df) == 2
        assert df.index.name == "timestamp"
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]
        assert df.index.is_monotonic_increasing

    def test_normalize_df_sorts_chronologically(self):
        source = ZerodhaDataSource("k", "s", "t")
        records = [
            {"date": datetime(2025, 1, 2, 9, 20), "open": 103, "high": 107,
             "low": 101, "close": 106, "volume": 3000},
            {"date": datetime(2025, 1, 2, 9, 15), "open": 100, "high": 105,
             "low": 98, "close": 103, "volume": 5000},
        ]
        df = source._normalize_df(records)
        assert df.index[0] < df.index[1]

    def test_max_days_per_request(self):
        assert ZerodhaDataSource._max_days_per_request(Timeframe.MINUTE_1) == 60
        assert ZerodhaDataSource._max_days_per_request(Timeframe.MINUTE_5) == 100
        assert ZerodhaDataSource._max_days_per_request(Timeframe.MINUTE_15) == 100
        assert ZerodhaDataSource._max_days_per_request(Timeframe.HOURLY) == 400
        assert ZerodhaDataSource._max_days_per_request(Timeframe.DAILY) == 2000

    def test_date_chunks_single(self):
        start = datetime(2025, 1, 1)
        end = datetime(2025, 1, 10)
        chunks = ZerodhaDataSource._date_chunks(start, end, max_days=30)
        assert len(chunks) == 1
        assert chunks[0] == (start, end)

    def test_date_chunks_multiple(self):
        start = datetime(2025, 1, 1)
        end = datetime(2025, 3, 15)
        chunks = ZerodhaDataSource._date_chunks(start, end, max_days=30)
        assert len(chunks) >= 2
        assert chunks[0][0] == start
        assert chunks[-1][1] == end

    def test_health_check_missing_credentials(self):
        source = ZerodhaDataSource("", "", "")
        result = source.health_check()
        assert result["status"] == "error"
        assert result["provider"] == "zerodha"
        assert "credentials" in result["message"].lower() or "Missing" in result["message"]

    def test_health_check_with_invalid_credentials(self):
        source = ZerodhaDataSource("bad_key", "bad_secret", "bad_token")
        result = source.health_check()
        assert result["provider"] == "zerodha"
        # Will fail to connect with invalid creds
        assert result["status"] == "error"


# ---------------------------------------------------------------------------
# Tests — UpstoxDataSource (still a stub)
# ---------------------------------------------------------------------------

class TestUpstoxDataSource:

    def test_load_raises_not_implemented(self):
        source = UpstoxDataSource("key", "secret", "token")
        with pytest.raises(NotImplementedError, match="upstox-python-sdk"):
            source.load()

    def test_fetch_historical_raises_not_implemented(self):
        source = UpstoxDataSource("key", "secret", "token")
        with pytest.raises(NotImplementedError):
            source.fetch_historical(
                "RELIANCE", Timeframe.DAILY,
                datetime(2023, 1, 1), datetime(2023, 12, 31),
            )

    def test_fetch_live_raises_not_implemented(self):
        source = UpstoxDataSource("key", "secret", "token")
        with pytest.raises(NotImplementedError):
            source.fetch_live("NIFTY50")

    def test_list_instruments_raises_not_implemented(self):
        source = UpstoxDataSource("key", "secret", "token")
        with pytest.raises(NotImplementedError):
            source.list_instruments()

    def test_health_check_missing_package(self):
        source = UpstoxDataSource("key", "secret", "token")
        result = source.health_check()
        assert result["provider"] == "upstox"
        assert result["status"] == "error"

    def test_health_check_missing_credentials(self):
        source = UpstoxDataSource("", "", "")
        result = source.health_check()
        assert result["status"] == "error"
