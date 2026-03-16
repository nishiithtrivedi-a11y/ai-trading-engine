from __future__ import annotations

from datetime import date

import pytest

from src.data.instrument_metadata import (
    InstrumentMetadata,
    InstrumentMetadataError,
    InstrumentType,
    OptionType,
    TradingSessionProfile,
    normalize_instrument_type,
    required_metadata_fields,
)


def test_equity_metadata_defaults_are_valid() -> None:
    meta = InstrumentMetadata(symbol="RELIANCE.NS")
    assert meta.symbol == "RELIANCE.NS"
    assert meta.instrument_type == InstrumentType.EQUITY
    assert meta.exchange == "NSE"
    assert meta.currency == "INR"
    assert meta.lot_size == 1


def test_future_metadata_requires_expiry() -> None:
    with pytest.raises(InstrumentMetadataError, match="require metadata fields"):
        InstrumentMetadata(
            symbol="NIFTY24MARFUT",
            instrument_type=InstrumentType.FUTURE,
        )


def test_option_metadata_requires_expiry_strike_and_option_type() -> None:
    with pytest.raises(InstrumentMetadataError, match="require metadata fields"):
        InstrumentMetadata(
            symbol="NIFTY24MAR22000CE",
            instrument_type=InstrumentType.OPTION,
            expiry_date=date(2026, 3, 26),
        )


def test_option_metadata_valid_when_required_fields_present() -> None:
    meta = InstrumentMetadata(
        symbol="NIFTY24MAR22000CE",
        instrument_type=InstrumentType.OPTION,
        expiry_date=date(2026, 3, 26),
        strike=22000.0,
        option_type=OptionType.CALL,
        lot_size=50,
        tick_size=0.05,
    )
    assert meta.instrument_type == InstrumentType.OPTION
    assert meta.option_type == OptionType.CALL
    assert meta.strike == 22000.0


def test_non_option_rejects_option_specific_fields() -> None:
    with pytest.raises(InstrumentMetadataError, match="only be set for option"):
        InstrumentMetadata(
            symbol="RELIANCE.NS",
            instrument_type=InstrumentType.EQUITY,
            strike=2500.0,
        )


def test_invalid_lot_size_and_tick_size_raise() -> None:
    with pytest.raises(InstrumentMetadataError, match="lot_size"):
        InstrumentMetadata(symbol="RELIANCE.NS", lot_size=0)

    with pytest.raises(InstrumentMetadataError, match="tick_size"):
        InstrumentMetadata(symbol="RELIANCE.NS", tick_size=0.0)


def test_session_profile_validates_time_format() -> None:
    with pytest.raises(InstrumentMetadataError, match="HH:MM"):
        TradingSessionProfile(open_time="9:15", close_time="15:30")


def test_helper_functions_return_expected_values() -> None:
    assert normalize_instrument_type("ETF") == InstrumentType.ETF
    assert required_metadata_fields(InstrumentType.EQUITY) == ()
    assert required_metadata_fields(InstrumentType.FUTURE) == ("expiry_date",)
    assert required_metadata_fields(InstrumentType.OPTION) == (
        "expiry_date",
        "strike",
        "option_type",
    )

