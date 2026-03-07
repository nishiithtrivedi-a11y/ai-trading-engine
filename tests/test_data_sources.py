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

    def test_list_instruments_raises_not_implemented(self):
        source = ZerodhaDataSource("key", "secret", "token")
        with pytest.raises(NotImplementedError):
            source.list_instruments()

    def test_health_check_missing_package(self):
        source = ZerodhaDataSource("key", "secret", "token")
        result = source.health_check()
        assert result["provider"] == "zerodha"
        # kiteconnect is not installed in test env
        assert result["status"] == "error"

    def test_health_check_missing_credentials(self):
        source = ZerodhaDataSource("", "", "")
        result = source.health_check()
        assert result["status"] == "error"


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
