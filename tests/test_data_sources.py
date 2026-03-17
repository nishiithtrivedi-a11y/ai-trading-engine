"""Tests for data source implementations and stubs."""

import builtins
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
        assert result["status"] == "degraded"
        assert result["provider"] == "zerodha"
        assert "credentials" in result["message"].lower() or "Missing" in result["message"]

    def test_health_check_with_invalid_credentials(self):
        source = ZerodhaDataSource("bad_key", "bad_secret", "bad_token")
        result = source.health_check()
        assert result["provider"] == "zerodha"
        # Will fail to connect with invalid creds
        assert result["status"] in {"degraded", "error"}

    def test_fetch_historical_retries_transient_errors(self):
        class _StubMapper:
            @staticmethod
            def get_instrument_token(_symbol, _exchange):
                return 123456

            @staticmethod
            def normalize_symbol_for_kite(symbol):
                return symbol.replace(".NS", "")

        class _StubKite:
            def __init__(self):
                self.calls = 0

            def historical_data(self, **_kwargs):
                self.calls += 1
                if self.calls == 1:
                    raise RuntimeError("temporary timeout")
                return [
                    {
                        "date": datetime(2025, 1, 1, 9, 15),
                        "open": 100,
                        "high": 101,
                        "low": 99,
                        "close": 100.5,
                        "volume": 1000,
                    }
                ]

        source = ZerodhaDataSource("key", "secret", "token", request_retries=2)
        source._kite = _StubKite()  # type: ignore[attr-defined]
        source._instrument_mapper = _StubMapper()  # type: ignore[attr-defined]
        frame = source.fetch_historical(
            symbol="RELIANCE.NS",
            timeframe=Timeframe.DAILY,
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 2),
        )
        assert len(frame) == 1
        assert source._kite.calls == 2  # type: ignore[attr-defined]
        quality = frame.attrs.get("data_quality", {})
        assert quality.get("provider") == "zerodha"

    def test_fetch_live_returns_series_with_quality_metadata(self):
        class _StubMapper:
            @staticmethod
            def get_instrument_token(_symbol, _exchange):
                return 123456

            @staticmethod
            def normalize_symbol_for_kite(symbol):
                return symbol.replace(".NS", "")

        class _StubKite:
            def quote(self, _symbols):
                return {
                    "NSE:RELIANCE": {
                        "ohlc": {"open": 100.0, "high": 102.0, "low": 99.0, "close": 101.0},
                        "volume": 1500,
                    }
                }

        source = ZerodhaDataSource("key", "secret", "token")
        source._kite = _StubKite()  # type: ignore[attr-defined]
        source._instrument_mapper = _StubMapper()  # type: ignore[attr-defined]
        series = source.fetch_live("RELIANCE.NS")
        assert float(series["close"]) == 101.0
        quality = series.attrs.get("data_quality", {})
        assert quality.get("provider") == "zerodha"


# ---------------------------------------------------------------------------
# Tests — UpstoxDataSource (still a stub)
# ---------------------------------------------------------------------------

class TestUpstoxDataSource:

    def test_load_raises_not_implemented(self, tmp_path):
        source = UpstoxDataSource("key", "secret", "token", data_dir=str(tmp_path))
        with pytest.raises(NotImplementedError, match="Upstox historical API path"):
            source.load()

    def test_fetch_historical_raises_not_implemented(self, tmp_path):
        source = UpstoxDataSource("key", "secret", "token", data_dir=str(tmp_path))
        with pytest.raises(NotImplementedError):
            source.fetch_historical(
                "RELIANCE", Timeframe.DAILY,
                datetime(2023, 1, 1), datetime(2023, 12, 31),
            )

    def test_fetch_live_raises_not_implemented(self, tmp_path):
        source = UpstoxDataSource("key", "secret", "token", data_dir=str(tmp_path))
        with pytest.raises(NotImplementedError):
            source.fetch_live("NIFTY50")

    def test_list_instruments_returns_empty_when_no_fallback_data(self, tmp_path):
        source = UpstoxDataSource("key", "secret", "token", data_dir=str(tmp_path))
        assert source.list_instruments() == []

    def test_health_check_missing_package(self, tmp_path):
        source = UpstoxDataSource("key", "secret", "token", data_dir=str(tmp_path))
        result = source.health_check()
        assert result["provider"] == "upstox"
        assert result["status"] in {"not_implemented", "degraded"}

    def test_health_check_missing_credentials(self, tmp_path):
        source = UpstoxDataSource("", "", "", data_dir=str(tmp_path))
        result = source.health_check()
        assert result["status"] in {"not_implemented", "degraded"}

    def test_health_check_reports_degraded_when_package_and_credentials_present(self, monkeypatch, tmp_path):
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "upstox_client":
                class _DummyModule:
                    pass
                return _DummyModule()
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        source = UpstoxDataSource("key", "secret", "token", data_dir=str(tmp_path))
        result = source.health_check()
        assert result["status"] == "degraded"
        assert "configured" in result["message"].lower()

    def test_health_check_not_implemented_path_has_state_key(self, tmp_path):
        """No SDK, no CSV fallback → not_implemented with state key locked in."""
        source = UpstoxDataSource("", "", "", data_dir=str(tmp_path))
        result = source.health_check()
        assert result["status"] == "not_implemented"
        assert result["state"] == "sdk_and_fallback_unavailable"
        assert result["fallback_available"] is False
        assert result["supports_historical_data"] is False

    def test_health_check_csv_fallback_path_has_state_key(self, tmp_path):
        """CSV files present without SDK → csv_fallback_only state."""
        # Create at least one CSV file so _csv_fallback_available() returns True
        (tmp_path / "RELIANCE_1D.csv").write_text(
            "timestamp,open,high,low,close,volume\n2025-01-01,100,101,99,100.5,1000\n"
        )
        source = UpstoxDataSource("", "", "", data_dir=str(tmp_path))
        result = source.health_check()
        assert result["status"] == "degraded"
        assert result["state"] == "csv_fallback_only"
        assert result["fallback_available"] is True
        assert result["supports_live_quotes"] is True

    def test_health_check_sdk_configured_state_reports_degraded(self, monkeypatch, tmp_path):
        """SDK + credentials present → sdk_present_auth_configured state."""
        real_import = builtins.__import__

        def fake_import(name, *args, **kwargs):
            if name == "upstox_client":
                class _DummyModule:
                    pass
                return _DummyModule()
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", fake_import)

        source = UpstoxDataSource("key", "secret", "token", data_dir=str(tmp_path))
        result = source.health_check()
        assert result["status"] == "degraded"
        assert result["state"] == "sdk_present_auth_configured"
        assert result["auth_degraded"] is False

    def test_upstox_csv_fallback_historical_and_live(self, tmp_path):
        file_path = tmp_path / "RELIANCE_1D.csv"
        pd.DataFrame(
            {
                "timestamp": pd.date_range("2025-01-01", periods=10, freq="D"),
                "open": [100 + i for i in range(10)],
                "high": [101 + i for i in range(10)],
                "low": [99 + i for i in range(10)],
                "close": [100.5 + i for i in range(10)],
                "volume": [1000 + i * 10 for i in range(10)],
            }
        ).to_csv(file_path, index=False)

        source = UpstoxDataSource(
            api_key="",
            api_secret="",
            access_token="",
            data_dir=str(tmp_path),
        )
        frame = source.fetch_historical(
            symbol="RELIANCE.NS",
            timeframe=Timeframe.DAILY,
            start=datetime(2025, 1, 1),
            end=datetime(2025, 1, 31),
        )
        assert len(frame) == 10
        quality = frame.attrs.get("data_quality", {})
        assert quality.get("fallback_provider") == "csv"

        live_payload = source.fetch_live("RELIANCE.NS")
        assert float(live_payload["close"]) > 0
        assert live_payload["data_quality"]["fallback_provider"] == "csv"
