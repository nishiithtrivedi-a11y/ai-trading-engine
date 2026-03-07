"""Tests for placeholder data source stubs."""

import pytest

from src.data.sources import ZerodhaDataSource, UpstoxDataSource


class TestZerodhaDataSource:

    def test_load_raises_not_implemented(self):
        source = ZerodhaDataSource("key", "secret", "token")
        with pytest.raises(NotImplementedError, match="kiteconnect"):
            source.load()

    def test_fetch_historical_raises_not_implemented(self):
        from datetime import datetime
        from src.data.base import Timeframe

        source = ZerodhaDataSource("key", "secret", "token")
        with pytest.raises(NotImplementedError):
            source.fetch_historical(
                "RELIANCE", Timeframe.DAILY,
                datetime(2023, 1, 1), datetime(2023, 12, 31),
            )

    def test_fetch_live_raises_not_implemented(self):
        source = ZerodhaDataSource("key", "secret", "token")
        with pytest.raises(NotImplementedError):
            source.fetch_live("RELIANCE")


class TestUpstoxDataSource:

    def test_load_raises_not_implemented(self):
        source = UpstoxDataSource("key", "secret", "token")
        with pytest.raises(NotImplementedError, match="upstox-python-sdk"):
            source.load()

    def test_fetch_historical_raises_not_implemented(self):
        from datetime import datetime
        from src.data.base import Timeframe

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
