"""
Exchange and Segment enums for Indian market instrument classification.

Notes
-----
InstrumentType (EQUITY, FUTURE, OPTION, etc.) and OptionType (CALL, PUT)
are intentionally kept in ``src.data.instrument_metadata`` to avoid
duplicating definitions.  Import them from there when needed:

    from src.data.instrument_metadata import InstrumentType, OptionType
"""

from __future__ import annotations

from enum import Enum


class Exchange(str, Enum):
    """Primary exchange / segment identifier used in canonical symbols."""

    NSE = "NSE"   # National Stock Exchange — equity and index
    BSE = "BSE"   # Bombay Stock Exchange — equity and index
    NFO = "NFO"   # NSE Futures & Options segment
    MCX = "MCX"   # Multi Commodity Exchange
    CDS = "CDS"   # Currency Derivatives Segment (NSE)

    @classmethod
    def _missing_(cls, value: object) -> "Exchange | None":
        if isinstance(value, str):
            normalised = value.strip().upper()
            for member in cls:
                if member.value == normalised:
                    return member
        return None


class Segment(str, Enum):
    """
    High-level market segment grouping.

    Segment maps exchanges to broad asset classes for capability routing:

    - CASH  : spot equity / ETF / index (NSE, BSE)
    - FO    : futures and options on equities/indices (NFO)
    - COMM  : commodities futures/options (MCX)
    - CURR  : currency derivatives (CDS)
    """

    CASH = "CASH"
    FO = "FO"
    COMM = "COMM"
    CURR = "CURR"

    @classmethod
    def from_exchange(cls, exchange: Exchange) -> "Segment":
        """Infer the default segment from an exchange."""
        _MAP: dict[Exchange, Segment] = {
            Exchange.NSE: cls.CASH,
            Exchange.BSE: cls.CASH,
            Exchange.NFO: cls.FO,
            Exchange.MCX: cls.COMM,
            Exchange.CDS: cls.CURR,
        }
        segment = _MAP.get(exchange)
        if segment is None:
            raise ValueError(f"Cannot infer segment for exchange {exchange!r}")
        return segment
