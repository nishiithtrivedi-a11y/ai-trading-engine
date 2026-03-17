"""
Tests for symbol normalization — format_canonical / parse_canonical round-trips,
CanonicalSymbolError cases, and to_provider_symbol stub.
"""
from __future__ import annotations

from datetime import date

import pytest

from src.data.instrument_metadata import InstrumentType, OptionType
from src.instruments.enums import Exchange
from src.instruments.instrument import Instrument
from src.instruments.normalization import (
    CanonicalSymbolError,
    format_canonical,
    parse_canonical,
    to_provider_symbol,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _equity(symbol: str, exchange: Exchange = Exchange.NSE) -> Instrument:
    return Instrument.equity(symbol, exchange=exchange)


def _future(symbol: str, expiry: date, exchange: Exchange = Exchange.NFO) -> Instrument:
    return Instrument.future(symbol, expiry, exchange=exchange)


def _call(symbol: str, expiry: date, strike: float, exchange: Exchange = Exchange.NFO) -> Instrument:
    return Instrument.option(symbol, expiry, strike, OptionType.CALL, exchange=exchange)


def _put(symbol: str, expiry: date, strike: float, exchange: Exchange = Exchange.NFO) -> Instrument:
    return Instrument.option(symbol, expiry, strike, OptionType.PUT, exchange=exchange)


# ---------------------------------------------------------------------------
# format_canonical
# ---------------------------------------------------------------------------

class TestFormatCanonical:
    def test_equity_nse(self):
        assert format_canonical(_equity("RELIANCE")) == "NSE:RELIANCE-EQ"

    def test_equity_bse(self):
        assert format_canonical(_equity("TCS", Exchange.BSE)) == "BSE:TCS-EQ"

    def test_future_nfo(self):
        assert (
            format_canonical(_future("NIFTY", date(2026, 4, 30)))
            == "NFO:NIFTY-2026-04-30-FUT"
        )

    def test_future_mcx(self):
        assert (
            format_canonical(_future("GOLD", date(2026, 4, 30), Exchange.MCX))
            == "MCX:GOLD-2026-04-30-FUT"
        )

    def test_future_cds(self):
        assert (
            format_canonical(_future("USDINR", date(2026, 4, 30), Exchange.CDS))
            == "CDS:USDINR-2026-04-30-FUT"
        )

    def test_call_option(self):
        assert (
            format_canonical(_call("NIFTY", date(2026, 4, 30), 24500.0))
            == "NFO:NIFTY-2026-04-30-24500-CE"
        )

    def test_put_option(self):
        assert (
            format_canonical(_put("BANKNIFTY", date(2026, 4, 30), 48000.0))
            == "NFO:BANKNIFTY-2026-04-30-48000-PE"
        )

    def test_call_decimal_strike(self):
        canonical = format_canonical(_call("NIFTY", date(2026, 4, 30), 24500.5))
        assert "24500.5" in canonical
        assert canonical.endswith("-CE")

    def test_equity_lowercase_symbol_is_uppercased(self):
        inst = _equity("reliance")  # __post_init__ uppercases; double-check format
        assert format_canonical(inst) == "NSE:RELIANCE-EQ"

    def test_index_instrument(self):
        inst = Instrument(
            symbol="NIFTY50",
            exchange=Exchange.NSE,
            instrument_type=InstrumentType.INDEX,
        )
        assert format_canonical(inst) == "NSE:NIFTY50-IDX"

    def test_etf_instrument(self):
        inst = Instrument(
            symbol="NIFTYBEES",
            exchange=Exchange.NSE,
            instrument_type=InstrumentType.ETF,
        )
        assert format_canonical(inst) == "NSE:NIFTYBEES-ETF"


# ---------------------------------------------------------------------------
# parse_canonical
# ---------------------------------------------------------------------------

class TestParseCanonical:
    def test_parse_equity(self):
        inst = parse_canonical("NSE:RELIANCE-EQ")
        assert inst.symbol == "RELIANCE"
        assert inst.exchange == Exchange.NSE
        assert inst.instrument_type == InstrumentType.EQUITY

    def test_parse_bse_equity(self):
        inst = parse_canonical("BSE:TCS-EQ")
        assert inst.exchange == Exchange.BSE

    def test_parse_future(self):
        inst = parse_canonical("NFO:NIFTY-2026-04-30-FUT")
        assert inst.symbol == "NIFTY"
        assert inst.exchange == Exchange.NFO
        assert inst.instrument_type == InstrumentType.FUTURE
        assert inst.expiry == date(2026, 4, 30)

    def test_parse_call_option(self):
        inst = parse_canonical("NFO:NIFTY-2026-04-30-24500-CE")
        assert inst.symbol == "NIFTY"
        assert inst.instrument_type == InstrumentType.OPTION
        assert inst.option_type == OptionType.CALL
        assert inst.strike == 24500.0
        assert inst.expiry == date(2026, 4, 30)

    def test_parse_put_option(self):
        inst = parse_canonical("NFO:BANKNIFTY-2026-04-30-48000-PE")
        assert inst.option_type == OptionType.PUT
        assert inst.strike == 48000.0

    def test_parse_index(self):
        inst = parse_canonical("NSE:NIFTY50-IDX")
        assert inst.instrument_type == InstrumentType.INDEX

    def test_parse_etf(self):
        inst = parse_canonical("NSE:NIFTYBEES-ETF")
        assert inst.instrument_type == InstrumentType.ETF

    def test_parse_mcx_future(self):
        inst = parse_canonical("MCX:GOLD-2026-04-30-FUT")
        assert inst.exchange == Exchange.MCX

    def test_parse_cds_future(self):
        inst = parse_canonical("CDS:USDINR-2026-04-30-FUT")
        assert inst.exchange == Exchange.CDS


# ---------------------------------------------------------------------------
# Round-trip: format → parse → format
# ---------------------------------------------------------------------------

class TestRoundTrip:
    @pytest.mark.parametrize(
        "canonical",
        [
            "NSE:RELIANCE-EQ",
            "BSE:TCS-EQ",
            "NFO:NIFTY-2026-04-30-FUT",
            "MCX:GOLD-2026-04-30-FUT",
            "CDS:USDINR-2026-04-30-FUT",
            "NFO:NIFTY-2026-04-30-24500-CE",
            "NFO:BANKNIFTY-2026-04-30-48000-PE",
            "NSE:NIFTY50-IDX",
            "NSE:NIFTYBEES-ETF",
        ],
    )
    def test_round_trip(self, canonical: str):
        parsed = parse_canonical(canonical)
        reformatted = format_canonical(parsed)
        assert reformatted == canonical, (
            f"Round-trip failed: {canonical!r} → parsed → {reformatted!r}"
        )

    def test_instrument_canonical_property_matches_format_canonical(self):
        inst = _future("NIFTY", date(2026, 4, 30))
        assert inst.canonical == format_canonical(inst)


# ---------------------------------------------------------------------------
# CanonicalSymbolError cases
# ---------------------------------------------------------------------------

class TestCanonicalSymbolError:
    def test_missing_colon_raises(self):
        with pytest.raises(CanonicalSymbolError, match="':'"):
            parse_canonical("NSE-RELIANCE-EQ")

    def test_unknown_exchange_raises(self):
        with pytest.raises(CanonicalSymbolError, match="Unknown exchange"):
            parse_canonical("BOGUS:RELIANCE-EQ")

    def test_unparseable_pattern_raises(self):
        with pytest.raises(CanonicalSymbolError):
            parse_canonical("NFO:NIFTY-NOTADATE-FUT")

    def test_option_invalid_strike_raises(self):
        with pytest.raises(CanonicalSymbolError, match="strike"):
            parse_canonical("NFO:NIFTY-2026-04-30-NOTSTRIKE-CE")

    def test_empty_string_raises(self):
        with pytest.raises(CanonicalSymbolError):
            parse_canonical("")

    def test_only_colon_raises(self):
        with pytest.raises((CanonicalSymbolError, ValueError)):
            parse_canonical(":")

    def test_is_value_error_subclass(self):
        assert issubclass(CanonicalSymbolError, ValueError)


# ---------------------------------------------------------------------------
# to_provider_symbol stub
# ---------------------------------------------------------------------------

class TestToProviderSymbol:
    def test_raises_not_implemented(self):
        with pytest.raises(NotImplementedError):
            to_provider_symbol("NSE:RELIANCE-EQ", "zerodha")

    def test_raises_for_any_provider(self):
        for provider in ("zerodha", "upstox", "angel", "unknown"):
            with pytest.raises(NotImplementedError):
                to_provider_symbol("NSE:TCS-EQ", provider)

    def test_error_message_contains_provider(self):
        with pytest.raises(NotImplementedError, match="zerodha"):
            to_provider_symbol("NSE:INFY-EQ", "zerodha")

    def test_error_message_contains_canonical(self):
        with pytest.raises(NotImplementedError, match="NSE:HDFC-EQ"):
            to_provider_symbol("NSE:HDFC-EQ", "upstox")
