"""
Tests for InstrumentHydrator — Phase 2 Indian Derivatives Data Layer.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.data.instrument_metadata import InstrumentType, OptionType
from src.instruments.enums import Exchange
from src.instruments.hydrator import InstrumentHydrator, InstrumentHydrationError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def hydrator():
    return InstrumentHydrator()


def _kite_equity_row() -> dict:
    return {
        "instrument_token": 738561,
        "exchange_token": 2885,
        "tradingsymbol": "RELIANCE",
        "name": "RELIANCE INDUSTRIES",
        "last_price": 2800.0,
        "expiry": "",
        "strike": 0.0,
        "tick_size": 0.05,
        "lot_size": 1,
        "instrument_type": "EQ",
        "segment": "NSE",
        "exchange": "NSE",
    }


def _kite_future_row() -> dict:
    return {
        "instrument_token": 12345678,
        "exchange_token": 12345,
        "tradingsymbol": "NIFTY26APRFUT",
        "name": "NIFTY",
        "last_price": 24500.0,
        "expiry": "2026-04-30",
        "strike": 0.0,
        "tick_size": 0.05,
        "lot_size": 50,
        "instrument_type": "FUT",
        "segment": "NFO",
        "exchange": "NFO",
    }


def _kite_ce_row() -> dict:
    return {
        "instrument_token": 99887766,
        "exchange_token": 998877,
        "tradingsymbol": "NIFTY26APR24500CE",
        "name": "NIFTY",
        "last_price": 350.0,
        "expiry": "2026-04-30",
        "strike": 24500.0,
        "tick_size": 0.05,
        "lot_size": 50,
        "instrument_type": "CE",
        "segment": "NFO",
        "exchange": "NFO",
    }


def _kite_pe_row() -> dict:
    return {
        "instrument_token": 99887755,
        "exchange_token": 998876,
        "tradingsymbol": "NIFTY26APR24500PE",
        "name": "NIFTY",
        "last_price": 280.0,
        "expiry": "2026-04-30",
        "strike": 24500.0,
        "tick_size": 0.05,
        "lot_size": 50,
        "instrument_type": "PE",
        "segment": "NFO",
        "exchange": "NFO",
    }


# ---------------------------------------------------------------------------
# hydrate_from_kite_row — equity
# ---------------------------------------------------------------------------

class TestHydrateEquity:
    def test_equity_instrument_type(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_equity_row())
        assert inst is not None
        assert inst.instrument_type == InstrumentType.EQUITY

    def test_equity_exchange(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_equity_row())
        assert inst.exchange == Exchange.NSE

    def test_equity_symbol_uppercased(self, hydrator):
        row = _kite_equity_row()
        row["tradingsymbol"] = "reliance"
        inst = hydrator.hydrate_from_kite_row(row)
        assert inst is not None
        assert inst.symbol == "RELIANCE"

    def test_equity_no_expiry(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_equity_row())
        assert inst.expiry is None

    def test_equity_lot_size(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_equity_row())
        assert inst.lot_size == 1


# ---------------------------------------------------------------------------
# hydrate_from_kite_row — future
# ---------------------------------------------------------------------------

class TestHydrateFuture:
    def test_future_instrument_type(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_future_row())
        assert inst is not None
        assert inst.instrument_type == InstrumentType.FUTURE

    def test_future_expiry_parsed(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_future_row())
        assert inst.expiry == date(2026, 4, 30)

    def test_future_exchange_nfo(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_future_row())
        assert inst.exchange == Exchange.NFO

    def test_future_lot_size(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_future_row())
        assert inst.lot_size == 50

    def test_future_missing_expiry_returns_none(self, hydrator):
        row = _kite_future_row()
        row["expiry"] = ""
        result = hydrator.hydrate_from_kite_row(row)
        assert result is None

    def test_future_none_expiry_returns_none(self, hydrator):
        row = _kite_future_row()
        row["expiry"] = None
        result = hydrator.hydrate_from_kite_row(row)
        assert result is None


# ---------------------------------------------------------------------------
# hydrate_from_kite_row — CE option
# ---------------------------------------------------------------------------

class TestHydrateCEOption:
    def test_ce_option_type(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_ce_row())
        assert inst is not None
        assert inst.instrument_type == InstrumentType.OPTION

    def test_ce_option_type_is_call(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_ce_row())
        assert inst.option_type == OptionType.CALL

    def test_ce_strike(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_ce_row())
        assert inst.strike == 24500.0

    def test_ce_expiry(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_ce_row())
        assert inst.expiry == date(2026, 4, 30)

    def test_ce_exchange(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_ce_row())
        assert inst.exchange == Exchange.NFO


# ---------------------------------------------------------------------------
# hydrate_from_kite_row — PE option
# ---------------------------------------------------------------------------

class TestHydratePEOption:
    def test_pe_option_type_is_put(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_pe_row())
        assert inst is not None
        assert inst.option_type == OptionType.PUT

    def test_pe_strike(self, hydrator):
        inst = hydrator.hydrate_from_kite_row(_kite_pe_row())
        assert inst.strike == 24500.0

    def test_option_missing_strike_returns_none(self, hydrator):
        row = _kite_ce_row()
        row["strike"] = 0.0  # zero strike is invalid
        result = hydrator.hydrate_from_kite_row(row)
        assert result is None

    def test_option_missing_expiry_returns_none(self, hydrator):
        row = _kite_ce_row()
        row["expiry"] = None
        result = hydrator.hydrate_from_kite_row(row)
        assert result is None


# ---------------------------------------------------------------------------
# hydrate_from_kite_row — malformed rows
# ---------------------------------------------------------------------------

class TestMalformedRows:
    def test_unknown_instrument_type_returns_none(self, hydrator):
        row = _kite_equity_row()
        row["instrument_type"] = "UNKNOWN_TYPE"
        assert hydrator.hydrate_from_kite_row(row) is None

    def test_unknown_exchange_returns_none(self, hydrator):
        row = _kite_equity_row()
        row["exchange"] = "BOGUS"
        assert hydrator.hydrate_from_kite_row(row) is None

    def test_empty_tradingsymbol_returns_none(self, hydrator):
        row = _kite_equity_row()
        row["tradingsymbol"] = ""
        assert hydrator.hydrate_from_kite_row(row) is None

    def test_empty_dict_returns_none(self, hydrator):
        assert hydrator.hydrate_from_kite_row({}) is None

    def test_missing_instrument_type_returns_none(self, hydrator):
        row = _kite_equity_row()
        del row["instrument_type"]
        assert hydrator.hydrate_from_kite_row(row) is None


# ---------------------------------------------------------------------------
# hydrate_from_kite_list — batch
# ---------------------------------------------------------------------------

class TestBatchHydration:
    def test_batch_returns_valid_instruments(self, hydrator):
        rows = [_kite_equity_row(), _kite_future_row(), _kite_ce_row()]
        result = hydrator.hydrate_from_kite_list(rows)
        assert len(result) == 3

    def test_batch_skips_malformed_rows(self, hydrator):
        rows = [
            _kite_equity_row(),
            {"tradingsymbol": "", "exchange": "NSE", "instrument_type": "EQ"},
            _kite_future_row(),
        ]
        result = hydrator.hydrate_from_kite_list(rows)
        assert len(result) == 2

    def test_batch_exchange_filter(self, hydrator):
        rows = [_kite_equity_row(), _kite_future_row(), _kite_ce_row()]
        result = hydrator.hydrate_from_kite_list(rows, exchange_filter="NSE")
        assert all(i.exchange == Exchange.NSE for i in result)
        assert len(result) == 1

    def test_batch_exchange_filter_nfo(self, hydrator):
        rows = [_kite_equity_row(), _kite_future_row(), _kite_ce_row()]
        result = hydrator.hydrate_from_kite_list(rows, exchange_filter="NFO")
        assert len(result) == 2

    def test_empty_list_returns_empty(self, hydrator):
        assert hydrator.hydrate_from_kite_list([]) == []


# ---------------------------------------------------------------------------
# hydrate_from_dict
# ---------------------------------------------------------------------------

class TestHydrateFromDict:
    def test_equity_from_dict(self, hydrator):
        d = {"symbol": "RELIANCE", "exchange": "NSE", "instrument_type": "equity"}
        inst = hydrator.hydrate_from_dict(d)
        assert inst is not None
        assert inst.symbol == "RELIANCE"
        assert inst.instrument_type == InstrumentType.EQUITY

    def test_future_from_dict(self, hydrator):
        d = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "instrument_type": "future",
            "expiry": "2026-04-30",
        }
        inst = hydrator.hydrate_from_dict(d)
        assert inst is not None
        assert inst.instrument_type == InstrumentType.FUTURE
        assert inst.expiry == date(2026, 4, 30)

    def test_option_from_dict(self, hydrator):
        d = {
            "symbol": "NIFTY",
            "exchange": "NFO",
            "instrument_type": "option",
            "expiry": "2026-04-30",
            "strike": 24500.0,
            "option_type": "call",
        }
        inst = hydrator.hydrate_from_dict(d)
        assert inst is not None
        assert inst.option_type == OptionType.CALL

    def test_kite_alias_eq_in_dict(self, hydrator):
        d = {"symbol": "TCS", "exchange": "BSE", "instrument_type": "eq"}
        inst = hydrator.hydrate_from_dict(d)
        assert inst is not None
        assert inst.instrument_type == InstrumentType.EQUITY
        assert inst.exchange == Exchange.BSE

    def test_invalid_exchange_returns_none(self, hydrator):
        d = {"symbol": "X", "exchange": "BOGUS", "instrument_type": "equity"}
        assert hydrator.hydrate_from_dict(d) is None

    def test_missing_symbol_returns_none(self, hydrator):
        d = {"symbol": "", "exchange": "NSE", "instrument_type": "equity"}
        assert hydrator.hydrate_from_dict(d) is None


# ---------------------------------------------------------------------------
# hydrate_equity_list
# ---------------------------------------------------------------------------

class TestHydrateEquityList:
    def test_basic_list(self, hydrator):
        result = hydrator.hydrate_equity_list(["RELIANCE", "TCS", "INFY"])
        assert len(result) == 3
        assert all(i.instrument_type == InstrumentType.EQUITY for i in result)

    def test_default_exchange_is_nse(self, hydrator):
        result = hydrator.hydrate_equity_list(["RELIANCE"])
        assert result[0].exchange == Exchange.NSE

    def test_custom_exchange(self, hydrator):
        result = hydrator.hydrate_equity_list(["TCS"], exchange=Exchange.BSE)
        assert result[0].exchange == Exchange.BSE

    def test_empty_strings_skipped(self, hydrator):
        result = hydrator.hydrate_equity_list(["RELIANCE", "", "  ", "TCS"])
        assert len(result) == 2

    def test_empty_list(self, hydrator):
        assert hydrator.hydrate_equity_list([]) == []

    def test_symbols_uppercased(self, hydrator):
        result = hydrator.hydrate_equity_list(["reliance"])
        assert result[0].symbol == "RELIANCE"


# ---------------------------------------------------------------------------
# Exchange string mapping
# ---------------------------------------------------------------------------

class TestExchangeMapping:
    @pytest.mark.parametrize("exc_str,expected", [
        ("NSE", Exchange.NSE),
        ("BSE", Exchange.BSE),
        ("NFO", Exchange.NFO),
        ("MCX", Exchange.MCX),
        ("CDS", Exchange.CDS),
    ])
    def test_exchange_string_mapping(self, hydrator, exc_str, expected):
        row = {
            "tradingsymbol": "TEST",
            "exchange": exc_str,
            "instrument_type": "EQ",
        }
        inst = hydrator.hydrate_from_kite_row(row)
        if inst is not None:
            assert inst.exchange == expected

    @pytest.mark.parametrize("itype_str,expected_type,expected_otype", [
        ("EQ", InstrumentType.EQUITY, None),
        ("IDX", InstrumentType.INDEX, None),
        ("ETF", InstrumentType.ETF, None),
    ])
    def test_non_derivative_type_mapping(self, hydrator, itype_str, expected_type, expected_otype):
        row = {
            "tradingsymbol": "TEST",
            "exchange": "NSE",
            "instrument_type": itype_str,
        }
        inst = hydrator.hydrate_from_kite_row(row)
        assert inst is not None
        assert inst.instrument_type == expected_type
