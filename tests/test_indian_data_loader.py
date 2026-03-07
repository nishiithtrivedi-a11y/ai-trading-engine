"""Tests for the Indian market CSV data loader."""

import tempfile
from datetime import datetime
from pathlib import Path

import pandas as pd
import pytest

from src.data.base import Timeframe
from src.data.indian_data_loader import IndianCSVDataSource, NSE_OPEN, NSE_CLOSE


def _write_csv(path: str, content: str) -> None:
    """Write CSV content to a file."""
    Path(path).write_text(content.strip() + "\n")


class TestColumnNormalization:

    def test_lowercase_columns(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
timestamp,open,high,low,close,volume
2023-01-02 09:15:00,100,102,99,101,1000
2023-01-02 09:20:00,101,103,100,102,1100
""")
        source = IndianCSVDataSource(str(csv))
        df = source.load()
        assert list(df.columns) == ["open", "high", "low", "close", "volume"]

    def test_uppercase_columns(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
Date,Open,High,Low,Close,Volume
2023-01-02,100,102,99,101,1000
2023-01-03,101,103,100,102,1100
""")
        source = IndianCSVDataSource(str(csv))
        df = source.load()
        assert "open" in df.columns
        assert "close" in df.columns

    def test_ltp_renamed_to_close(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
Date,Open,High,Low,LTP,Volume
2023-01-02,100,102,99,101,1000
2023-01-03,101,103,100,102,1100
""")
        source = IndianCSVDataSource(str(csv))
        df = source.load()
        assert "close" in df.columns
        assert df["close"].iloc[0] == 101

    def test_traded_qty_renamed_to_volume(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
Date,Open,High,Low,Close,Traded Qty
2023-01-02,100,102,99,101,1000
2023-01-03,101,103,100,102,1100
""")
        source = IndianCSVDataSource(str(csv))
        df = source.load()
        assert "volume" in df.columns


class TestTimestampParsing:

    def test_standard_format(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
timestamp,open,high,low,close,volume
2023-01-02 09:15:00,100,102,99,101,1000
2023-01-02 09:20:00,101,103,100,102,1100
""")
        source = IndianCSVDataSource(str(csv))
        df = source.load()
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_indian_dd_mm_yyyy_format(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
date,open,high,low,close,volume
02-01-2023,100,102,99,101,1000
03-01-2023,101,103,100,102,1100
""")
        source = IndianCSVDataSource(str(csv))
        df = source.load()
        assert isinstance(df.index, pd.DatetimeIndex)
        # Should parse as Jan 2 and Jan 3
        assert df.index[0].month == 1
        assert df.index[0].day == 2

    def test_indian_dd_slash_mm_yyyy_with_time(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
datetime,open,high,low,close,volume
02/01/2023 09:15,100,102,99,101,1000
02/01/2023 09:20,101,103,100,102,1100
""")
        source = IndianCSVDataSource(str(csv))
        df = source.load()
        assert isinstance(df.index, pd.DatetimeIndex)

    def test_no_timestamp_column_raises(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
price,open,high,low,close,volume
1,100,102,99,101,1000
""")
        source = IndianCSVDataSource(str(csv))
        with pytest.raises(ValueError, match="No timestamp column found"):
            source.load()


class TestTimezoneNormalization:

    def test_naive_timestamps_localized_to_ist(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
timestamp,open,high,low,close,volume
2023-01-02 09:15:00,100,102,99,101,1000
2023-01-02 09:20:00,101,103,100,102,1100
""")
        source = IndianCSVDataSource(str(csv))
        df = source.load()
        assert df.index.tz is not None
        assert str(df.index.tz) == "Asia/Kolkata"

    def test_utc_timestamps_converted_to_ist(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
timestamp,open,high,low,close,volume
2023-01-02 03:45:00+00:00,100,102,99,101,1000
2023-01-02 03:50:00+00:00,101,103,100,102,1100
""")
        source = IndianCSVDataSource(str(csv))
        df = source.load()
        assert str(df.index.tz) == "Asia/Kolkata"
        # 03:45 UTC = 09:15 IST
        assert df.index[0].hour == 9
        assert df.index[0].minute == 15

    def test_already_ist_no_change(self, tmp_path):
        csv = tmp_path / "data.csv"
        _write_csv(str(csv), """
timestamp,open,high,low,close,volume
2023-01-02 09:15:00+05:30,100,102,99,101,1000
2023-01-02 09:20:00+05:30,101,103,100,102,1100
""")
        source = IndianCSVDataSource(str(csv))
        df = source.load()
        assert str(df.index.tz) == "Asia/Kolkata"
        assert df.index[0].hour == 9
        assert df.index[0].minute == 15


class TestTimeframeDetection:

    def _make_intraday_csv(self, tmp_path, freq: str) -> str:
        """Generate an intraday CSV with the given frequency."""
        dates = pd.date_range("2023-01-02 09:15", periods=20, freq=freq)
        df = pd.DataFrame({
            "timestamp": dates,
            "open": range(100, 120),
            "high": range(101, 121),
            "low": range(99, 119),
            "close": range(100, 120),
            "volume": [1000] * 20,
        })
        csv = tmp_path / "data.csv"
        df.to_csv(str(csv), index=False)
        return str(csv)

    def test_detect_1min(self, tmp_path):
        csv = self._make_intraday_csv(tmp_path, "1min")
        source = IndianCSVDataSource(csv)
        source.load()
        assert source.detected_timeframe == Timeframe.MINUTE_1

    def test_detect_5min(self, tmp_path):
        csv = self._make_intraday_csv(tmp_path, "5min")
        source = IndianCSVDataSource(csv)
        source.load()
        assert source.detected_timeframe == Timeframe.MINUTE_5

    def test_detect_15min(self, tmp_path):
        csv = self._make_intraday_csv(tmp_path, "15min")
        source = IndianCSVDataSource(csv)
        source.load()
        assert source.detected_timeframe == Timeframe.MINUTE_15

    def test_detect_hourly(self, tmp_path):
        csv = self._make_intraday_csv(tmp_path, "1h")
        source = IndianCSVDataSource(csv)
        source.load()
        assert source.detected_timeframe == Timeframe.HOURLY

    def test_detect_daily(self, tmp_path):
        dates = pd.date_range("2023-01-02", periods=20, freq="B")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": range(100, 120),
            "high": range(101, 121),
            "low": range(99, 119),
            "close": range(100, 120),
            "volume": [1000] * 20,
        })
        csv = tmp_path / "data.csv"
        df.to_csv(str(csv), index=False)
        source = IndianCSVDataSource(str(csv))
        source.load()
        assert source.detected_timeframe == Timeframe.DAILY


class TestSessionValidation:

    def test_all_bars_within_session(self, tmp_path, caplog):
        dates = pd.date_range("2023-01-02 09:15", periods=10, freq="5min")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": range(100, 110),
            "high": range(101, 111),
            "low": range(99, 109),
            "close": range(100, 110),
            "volume": [1000] * 10,
        })
        csv = tmp_path / "data.csv"
        df.to_csv(str(csv), index=False)

        source = IndianCSVDataSource(str(csv))
        source.load()
        assert "outside NSE session" not in caplog.text

    def test_bars_outside_session_warned(self, tmp_path, caplog):
        import logging
        caplog.set_level(logging.WARNING)

        # Create bars that include pre-market (08:00) and post-market (16:00)
        timestamps = [
            "2023-01-02 08:00:00",
            "2023-01-02 09:15:00",
            "2023-01-02 10:00:00",
            "2023-01-02 15:30:00",
            "2023-01-02 16:00:00",
        ]
        df = pd.DataFrame({
            "timestamp": timestamps,
            "open": [100, 101, 102, 103, 104],
            "high": [101, 102, 103, 104, 105],
            "low": [99, 100, 101, 102, 103],
            "close": [100, 101, 102, 103, 104],
            "volume": [1000] * 5,
        })
        csv = tmp_path / "data.csv"
        df.to_csv(str(csv), index=False)

        source = IndianCSVDataSource(str(csv))
        source.load()
        assert "outside NSE session" in caplog.text


class TestFullLoad:

    def test_roundtrip_load(self, tmp_path):
        """Test full load pipeline returns valid DataFrame."""
        dates = pd.date_range("2023-01-02 09:15", periods=50, freq="5min")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": range(100, 150),
            "high": range(101, 151),
            "low": range(99, 149),
            "close": range(100, 150),
            "volume": [1000] * 50,
        })
        csv = tmp_path / "data.csv"
        df.to_csv(str(csv), index=False)

        source = IndianCSVDataSource(str(csv))
        result = source.load()

        assert isinstance(result, pd.DataFrame)
        assert isinstance(result.index, pd.DatetimeIndex)
        assert result.index.name == "timestamp"
        assert len(result) == 50
        assert list(result.columns) == ["open", "high", "low", "close", "volume"]
        assert result.index.tz is not None

    def test_file_not_found_raises(self):
        source = IndianCSVDataSource("nonexistent.csv")
        with pytest.raises(FileNotFoundError):
            source.load()

    def test_data_handler_from_source_integration(self, tmp_path):
        """Test that DataHandler.from_source works with IndianCSVDataSource."""
        from src.core.data_handler import DataHandler

        dates = pd.date_range("2023-01-02 09:15", periods=20, freq="5min")
        df = pd.DataFrame({
            "timestamp": dates,
            "open": range(100, 120),
            "high": range(101, 121),
            "low": range(99, 119),
            "close": range(100, 120),
            "volume": [1000] * 20,
        })
        csv = tmp_path / "data.csv"
        df.to_csv(str(csv), index=False)

        source = IndianCSVDataSource(str(csv))
        handler = DataHandler.from_source(source)

        assert len(handler) == 20
        bar = handler.get_current_bar()
        assert bar["open"] == 100
