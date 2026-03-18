"""
Tests for DerivativeDataFetcher and quote_normalizer — Phase 2.
"""
from __future__ import annotations

from datetime import datetime

import pandas as pd
import pytest

from src.data.derivative_data import DerivativeDataError, DerivativeDataFetcher
from src.data.quote_normalizer import (
    DataQualityFlags,
    NormalizedQuote,
    normalize_kite_ohlc_row,
    normalize_kite_quote,
    normalize_upstox_quote,
    quote_from_series,
)
from src.instruments.enums import Exchange
from src.instruments.instrument import Instrument


# ---------------------------------------------------------------------------
# DataQualityFlags
# ---------------------------------------------------------------------------

class TestDataQualityFlags:
    def test_defaults_are_false(self):
        flags = DataQualityFlags()
        assert flags.is_stale is False
        assert flags.has_oi is False
        assert flags.has_depth is False
        assert flags.has_partial_metadata is False
        assert flags.unsupported_segment is False
        assert flags.degraded_auth is False
        assert flags.missing_volume is False

    def test_notes_default_empty(self):
        flags = DataQualityFlags()
        assert flags.notes == []

    def test_flags_can_be_set(self):
        flags = DataQualityFlags(is_stale=True, has_oi=True)
        assert flags.is_stale is True
        assert flags.has_oi is True


# ---------------------------------------------------------------------------
# NormalizedQuote
# ---------------------------------------------------------------------------

class TestNormalizedQuote:
    def _make_quote(self, **kwargs) -> NormalizedQuote:
        defaults = {
            "symbol": "NSE:RELIANCE-EQ",
            "provider": "test",
            "timestamp": None,
            "last_price": 2800.0,
            "open": 2780.0,
            "high": 2820.0,
            "low": 2775.0,
            "close": 2800.0,
            "volume": 100000,
            "oi": None,
            "bid": None,
            "ask": None,
            "depth_bid_qty": None,
            "depth_ask_qty": None,
        }
        defaults.update(kwargs)
        return NormalizedQuote(**defaults)

    def test_is_complete_true(self):
        q = self._make_quote()
        assert q.is_complete is True

    def test_is_complete_false_missing_volume(self):
        q = self._make_quote(volume=None)
        assert q.is_complete is False

    def test_is_complete_false_missing_open(self):
        q = self._make_quote(open=None)
        assert q.is_complete is False

    def test_to_dict_keys(self):
        q = self._make_quote()
        d = q.to_dict()
        assert "symbol" in d
        assert "provider" in d
        assert "last_price" in d
        assert "open" in d
        assert "high" in d
        assert "low" in d
        assert "close" in d
        assert "volume" in d
        assert "oi" in d
        assert "bid" in d
        assert "ask" in d
        assert "quality" in d

    def test_to_dict_symbol(self):
        q = self._make_quote()
        assert q.to_dict()["symbol"] == "NSE:RELIANCE-EQ"

    def test_to_dict_quality_dict(self):
        q = self._make_quote()
        quality = q.to_dict()["quality"]
        assert isinstance(quality, dict)
        assert "is_stale" in quality
        assert "has_oi" in quality

    def test_to_dict_timestamp_none(self):
        q = self._make_quote()
        assert q.to_dict()["timestamp"] is None

    def test_to_dict_timestamp_isoformat(self):
        ts = datetime(2026, 3, 18, 9, 15, 0)
        q = self._make_quote(timestamp=ts)
        d = q.to_dict()
        assert "2026-03-18" in d["timestamp"]


# ---------------------------------------------------------------------------
# normalize_kite_quote
# ---------------------------------------------------------------------------

class TestNormalizeKiteQuote:
    def _full_kite_quote(self) -> dict:
        return {
            "last_price": 24500.0,
            "ohlc": {"open": 24400.0, "high": 24600.0, "low": 24350.0, "close": 24490.0},
            "volume": 5000000,
            "oi": 150000,
            "depth": {
                "buy": [{"price": 24498.0, "quantity": 500, "orders": 3}],
                "sell": [{"price": 24502.0, "quantity": 400, "orders": 2}],
            },
            "timestamp": "2026-03-18T15:30:00",
        }

    def test_basic_fields(self):
        q = normalize_kite_quote("NFO:NIFTY-2026-04-30-FUT", self._full_kite_quote())
        assert q.last_price == 24500.0
        assert q.open == 24400.0
        assert q.high == 24600.0
        assert q.low == 24350.0
        assert q.close == 24490.0
        assert q.volume == 5000000

    def test_provider_is_zerodha(self):
        q = normalize_kite_quote("NSE:RELIANCE-EQ", self._full_kite_quote())
        assert q.provider == "zerodha"

    def test_oi_present(self):
        q = normalize_kite_quote("NFO:NIFTY-2026-04-30-FUT", self._full_kite_quote())
        assert q.oi == 150000
        assert q.quality.has_oi is True

    def test_depth_present(self):
        q = normalize_kite_quote("NFO:NIFTY-2026-04-30-FUT", self._full_kite_quote())
        assert q.quality.has_depth is True
        assert q.bid == 24498.0
        assert q.ask == 24502.0

    def test_missing_oi_flag(self):
        kq = self._full_kite_quote()
        del kq["oi"]
        q = normalize_kite_quote("NFO:NIFTY-2026-04-30-FUT", kq)
        assert q.quality.has_oi is False
        assert q.oi is None

    def test_missing_depth_flag(self):
        kq = self._full_kite_quote()
        del kq["depth"]
        q = normalize_kite_quote("NFO:NIFTY-2026-04-30-FUT", kq)
        assert q.quality.has_depth is False
        assert q.bid is None
        assert q.ask is None

    def test_missing_volume_flag(self):
        kq = self._full_kite_quote()
        kq["volume"] = 0
        q = normalize_kite_quote("NFO:NIFTY-2026-04-30-FUT", kq)
        assert q.quality.missing_volume is True

    def test_raw_preserved(self):
        kq = self._full_kite_quote()
        q = normalize_kite_quote("NSE:RELIANCE-EQ", kq)
        assert q.raw == kq

    def test_is_complete(self):
        q = normalize_kite_quote("NFO:NIFTY-2026-04-30-FUT", self._full_kite_quote())
        assert q.is_complete is True


# ---------------------------------------------------------------------------
# normalize_kite_ohlc_row
# ---------------------------------------------------------------------------

class TestNormalizeKiteOhlcRow:
    def test_basic_row(self):
        row = {
            "date": "2026-03-18",
            "open": 24400.0,
            "high": 24600.0,
            "low": 24350.0,
            "close": 24490.0,
            "volume": 5000000,
        }
        q = normalize_kite_ohlc_row("NFO:NIFTY-2026-04-30-FUT", row)
        assert q.open == 24400.0
        assert q.close == 24490.0
        assert q.last_price == 24490.0  # close used as last_price

    def test_with_oi(self):
        row = {
            "date": "2026-03-18",
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
            "volume": 1000,
            "oi": 50000,
        }
        q = normalize_kite_ohlc_row("NFO:NIFTY-2026-04-30-FUT", row)
        assert q.oi == 50000
        assert q.quality.has_oi is True

    def test_is_complete(self):
        row = {
            "date": "2026-03-18",
            "open": 100.0,
            "high": 110.0,
            "low": 95.0,
            "close": 105.0,
            "volume": 1000,
        }
        q = normalize_kite_ohlc_row("NSE:RELIANCE-EQ", row)
        assert q.is_complete is True


# ---------------------------------------------------------------------------
# normalize_upstox_quote
# ---------------------------------------------------------------------------

class TestNormalizeUpstoxQuote:
    def test_basic_upstox_fields(self):
        uq = {
            "last_price": 2800.0,
            "open": 2780.0,
            "high": 2820.0,
            "low": 2775.0,
            "close": 2800.0,
            "volume": 100000,
        }
        q = normalize_upstox_quote("NSE:RELIANCE-EQ", uq)
        assert q.last_price == 2800.0
        assert q.open == 2780.0
        assert q.provider == "upstox"

    def test_partial_metadata_flag(self):
        uq = {"last_price": 100.0}
        q = normalize_upstox_quote("NSE:TEST-EQ", uq)
        assert q.quality.has_partial_metadata is True

    def test_ltp_alias(self):
        uq = {"ltp": 2800.0, "open": 2780.0, "high": 2820.0, "low": 2775.0, "close": 2800.0}
        q = normalize_upstox_quote("NSE:RELIANCE-EQ", uq)
        assert q.last_price == 2800.0

    def test_no_oi(self):
        uq = {"last_price": 100.0, "open": 99.0, "high": 101.0, "low": 98.0, "close": 100.0}
        q = normalize_upstox_quote("NSE:TEST-EQ", uq)
        assert q.quality.has_oi is False


# ---------------------------------------------------------------------------
# quote_from_series
# ---------------------------------------------------------------------------

class TestQuoteFromSeries:
    def test_basic_series(self):
        s = pd.Series({"open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 5000})
        q = quote_from_series("NSE:TEST-EQ", s, provider="csv")
        assert q.open == 100.0
        assert q.close == 105.0
        assert q.volume == 5000
        assert q.provider == "csv"

    def test_is_complete(self):
        s = pd.Series({"open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 5000})
        q = quote_from_series("NSE:TEST-EQ", s)
        assert q.is_complete is True

    def test_missing_volume_flag(self):
        s = pd.Series({"open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 0})
        q = quote_from_series("NSE:TEST-EQ", s)
        assert q.quality.missing_volume is True

    def test_last_price_falls_back_to_close(self):
        s = pd.Series({"open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0, "volume": 5000})
        q = quote_from_series("NSE:TEST-EQ", s)
        assert q.last_price == 105.0

    def test_oi_field(self):
        s = pd.Series({
            "open": 100.0, "high": 110.0, "low": 95.0, "close": 105.0,
            "volume": 5000, "oi": 25000
        })
        q = quote_from_series("NFO:NIFTY-2026-04-30-FUT", s)
        assert q.oi == 25000
        assert q.quality.has_oi is True


# ---------------------------------------------------------------------------
# DerivativeDataFetcher
# ---------------------------------------------------------------------------

class TestDerivativeDataFetcher:
    def test_no_source_fetch_history_raises(self):
        from src.data.base import Timeframe
        fetcher = DerivativeDataFetcher()
        inst = Instrument.equity("RELIANCE", exchange=Exchange.NSE)
        with pytest.raises(DerivativeDataError):
            fetcher.fetch_instrument_history(
                inst, Timeframe.DAILY,
                datetime(2026, 1, 1), datetime(2026, 3, 1)
            )

    def test_no_source_fetch_quote_raises(self):
        fetcher = DerivativeDataFetcher()
        inst = Instrument.equity("RELIANCE", exchange=Exchange.NSE)
        with pytest.raises(DerivativeDataError):
            fetcher.fetch_instrument_quote(inst)

    def test_instrument_to_provider_symbol_zerodha(self):
        inst = Instrument.equity("RELIANCE", exchange=Exchange.NSE)
        result = DerivativeDataFetcher.instrument_to_provider_symbol(inst, "zerodha")
        assert result == "RELIANCE"

    def test_instrument_to_provider_symbol_upstox(self):
        inst = Instrument.equity("RELIANCE", exchange=Exchange.NSE)
        result = DerivativeDataFetcher.instrument_to_provider_symbol(inst, "upstox")
        assert result == "NSE_EQ|RELIANCE"

    def test_resolve_active_contract_no_registry(self):
        from src.data.instrument_metadata import InstrumentType
        fetcher = DerivativeDataFetcher()
        result = fetcher.resolve_active_contract(
            "NIFTY", Exchange.NFO, InstrumentType.FUTURE
        )
        assert result is None

    def test_derivative_data_error_is_value_error(self):
        assert issubclass(DerivativeDataError, ValueError)
