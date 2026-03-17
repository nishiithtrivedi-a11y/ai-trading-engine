"""
Tests for the Instrument model — construction, validation, factory helpers,
canonical property, and to_dict().
"""
from __future__ import annotations

from datetime import date

import pytest

from src.data.instrument_metadata import InstrumentType, OptionType
from src.instruments.enums import Exchange, Segment
from src.instruments.instrument import Instrument, InstrumentError


# ---------------------------------------------------------------------------
# Equity construction
# ---------------------------------------------------------------------------

class TestEquityConstruction:
    def test_equity_factory_default_exchange(self):
        inst = Instrument.equity("RELIANCE")
        assert inst.exchange == Exchange.NSE
        assert inst.instrument_type == InstrumentType.EQUITY

    def test_equity_factory_custom_exchange(self):
        inst = Instrument.equity("TCS", exchange=Exchange.BSE)
        assert inst.exchange == Exchange.BSE

    def test_equity_symbol_uppercased(self):
        inst = Instrument.equity("reliance")
        # __post_init__ uppercases symbol
        assert inst.symbol == "RELIANCE"

    def test_equity_segment_inferred_as_cash(self):
        inst = Instrument.equity("INFY")
        assert inst.segment == Segment.CASH

    def test_equity_no_expiry_or_strike(self):
        inst = Instrument.equity("INFY")
        assert inst.expiry is None
        assert inst.strike is None
        assert inst.option_type is None

    def test_equity_canonical_format(self):
        inst = Instrument.equity("RELIANCE")
        assert inst.canonical == "NSE:RELIANCE-EQ"

    def test_equity_bse_canonical(self):
        inst = Instrument.equity("TCS", exchange=Exchange.BSE)
        assert inst.canonical == "BSE:TCS-EQ"


# ---------------------------------------------------------------------------
# Futures construction
# ---------------------------------------------------------------------------

class TestFutureConstruction:
    def test_future_factory_requires_expiry(self):
        inst = Instrument.future("NIFTY", date(2026, 4, 30))
        assert inst.expiry == date(2026, 4, 30)
        assert inst.instrument_type == InstrumentType.FUTURE

    def test_future_default_exchange_is_nfo(self):
        inst = Instrument.future("NIFTY", date(2026, 4, 30))
        assert inst.exchange == Exchange.NFO

    def test_future_segment_inferred_as_fo(self):
        inst = Instrument.future("NIFTY", date(2026, 4, 30))
        assert inst.segment == Segment.FO

    def test_future_underlying_defaults_to_symbol(self):
        inst = Instrument.future("NIFTY", date(2026, 4, 30))
        assert inst.underlying == "NIFTY"

    def test_future_canonical_format(self):
        inst = Instrument.future("NIFTY", date(2026, 4, 30))
        assert inst.canonical == "NFO:NIFTY-2026-04-30-FUT"

    def test_future_without_expiry_raises(self):
        with pytest.raises(InstrumentError, match="expiry"):
            Instrument(
                symbol="NIFTY",
                exchange=Exchange.NFO,
                instrument_type=InstrumentType.FUTURE,
            )

    def test_mcx_future_segment_is_comm(self):
        inst = Instrument.future("GOLD", date(2026, 4, 30), exchange=Exchange.MCX)
        assert inst.segment == Segment.COMM

    def test_cds_future_segment_is_curr(self):
        inst = Instrument.future("USDINR", date(2026, 4, 30), exchange=Exchange.CDS)
        assert inst.segment == Segment.CURR


# ---------------------------------------------------------------------------
# Options construction
# ---------------------------------------------------------------------------

class TestOptionConstruction:
    def test_option_factory_call(self):
        inst = Instrument.option("NIFTY", date(2026, 4, 30), 24500.0, OptionType.CALL)
        assert inst.option_type == OptionType.CALL
        assert inst.strike == 24500.0
        assert inst.instrument_type == InstrumentType.OPTION

    def test_option_factory_put(self):
        inst = Instrument.option("NIFTY", date(2026, 4, 30), 24500.0, OptionType.PUT)
        assert inst.option_type == OptionType.PUT

    def test_option_string_ce_alias(self):
        inst = Instrument.option("NIFTY", date(2026, 4, 30), 24500.0, "CE")
        assert inst.option_type == OptionType.CALL

    def test_option_string_pe_alias(self):
        inst = Instrument.option("NIFTY", date(2026, 4, 30), 24500.0, "PE")
        assert inst.option_type == OptionType.PUT

    def test_option_canonical_call(self):
        inst = Instrument.option("NIFTY", date(2026, 4, 30), 24500.0, OptionType.CALL)
        assert inst.canonical == "NFO:NIFTY-2026-04-30-24500-CE"

    def test_option_canonical_put(self):
        inst = Instrument.option("BANKNIFTY", date(2026, 4, 30), 48000.0, OptionType.PUT)
        assert inst.canonical == "NFO:BANKNIFTY-2026-04-30-48000-PE"

    def test_option_missing_expiry_raises(self):
        with pytest.raises(InstrumentError, match="expiry"):
            Instrument(
                symbol="NIFTY",
                exchange=Exchange.NFO,
                instrument_type=InstrumentType.OPTION,
                strike=24500.0,
                option_type=OptionType.CALL,
            )

    def test_option_missing_strike_raises(self):
        with pytest.raises(InstrumentError, match="strike"):
            Instrument(
                symbol="NIFTY",
                exchange=Exchange.NFO,
                instrument_type=InstrumentType.OPTION,
                expiry=date(2026, 4, 30),
                option_type=OptionType.CALL,
            )

    def test_option_missing_option_type_raises(self):
        with pytest.raises(InstrumentError, match="option_type"):
            Instrument(
                symbol="NIFTY",
                exchange=Exchange.NFO,
                instrument_type=InstrumentType.OPTION,
                expiry=date(2026, 4, 30),
                strike=24500.0,
            )

    def test_option_decimal_strike_canonical(self):
        inst = Instrument.option("NIFTY", date(2026, 4, 30), 24500.5, OptionType.CALL)
        # Strike has a decimal component — check it's preserved
        assert "24500.5" in inst.canonical

    def test_equity_with_option_type_raises(self):
        with pytest.raises(InstrumentError):
            Instrument(
                symbol="RELIANCE",
                exchange=Exchange.NSE,
                instrument_type=InstrumentType.EQUITY,
                option_type=OptionType.CALL,
            )


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

class TestValidation:
    def test_zero_strike_raises(self):
        with pytest.raises(InstrumentError, match="strike must be > 0"):
            Instrument(
                symbol="NIFTY",
                exchange=Exchange.NFO,
                instrument_type=InstrumentType.OPTION,
                expiry=date(2026, 4, 30),
                strike=0.0,
                option_type=OptionType.CALL,
            )

    def test_negative_strike_raises(self):
        with pytest.raises(InstrumentError, match="strike must be > 0"):
            Instrument(
                symbol="NIFTY",
                exchange=Exchange.NFO,
                instrument_type=InstrumentType.OPTION,
                expiry=date(2026, 4, 30),
                strike=-100.0,
                option_type=OptionType.CALL,
            )

    def test_lot_size_zero_raises(self):
        with pytest.raises(InstrumentError, match="lot_size"):
            Instrument.equity("INFY", lot_size=0)

    def test_lot_size_positive_accepted(self):
        inst = Instrument.equity("INFY", lot_size=50)
        assert inst.lot_size == 50

    def test_tick_size_zero_raises(self):
        with pytest.raises(InstrumentError, match="tick_size"):
            Instrument.equity("INFY", tick_size=0.0)

    def test_tick_size_positive_accepted(self):
        inst = Instrument.equity("INFY", tick_size=0.05)
        assert inst.tick_size == 0.05

    def test_string_exchange_coerced(self):
        inst = Instrument(
            symbol="RELIANCE",
            exchange="NSE",  # type: ignore[arg-type]
            instrument_type=InstrumentType.EQUITY,
        )
        assert inst.exchange == Exchange.NSE

    def test_string_instrument_type_coerced(self):
        inst = Instrument(
            symbol="RELIANCE",
            exchange=Exchange.NSE,
            instrument_type="equity",  # type: ignore[arg-type]
        )
        assert inst.instrument_type == InstrumentType.EQUITY


# ---------------------------------------------------------------------------
# Metadata and currency
# ---------------------------------------------------------------------------

class TestMetadata:
    def test_default_currency_is_inr(self):
        inst = Instrument.equity("HDFC")
        assert inst.currency == "INR"

    def test_custom_metadata(self):
        inst = Instrument.equity("HDFC", metadata={"sector": "banking"})
        assert inst.metadata["sector"] == "banking"

    def test_metadata_defaults_empty_dict(self):
        inst = Instrument.equity("HDFC")
        assert inst.metadata == {}
