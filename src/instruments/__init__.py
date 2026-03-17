"""
Instrument Master — canonical instrument model, registry, and symbol normalisation.

This package provides:
- Instrument: canonical instrument model (extends InstrumentMetadata semantics)
- Exchange / Segment enums: NSE, BSE, NFO, MCX, CDS + CASH, FO, COMM, CURR
- InstrumentRegistry: in-memory registry with lookup by canonical symbol
- TradingCalendar: trading day helpers and expiry stubs
- Normalisation: canonical format parser/formatter + provider hook stubs

Reuses InstrumentType and OptionType from src.data.instrument_metadata
to avoid duplicating enum definitions.
"""

from src.instruments.enums import Exchange, Segment
from src.instruments.instrument import Instrument
from src.instruments.registry import InstrumentRegistry
from src.instruments.calendar import TradingCalendar
from src.instruments.normalization import (
    parse_canonical,
    format_canonical,
    to_provider_symbol,
    CanonicalSymbolError,
)

__all__ = [
    "Exchange",
    "Segment",
    "Instrument",
    "InstrumentRegistry",
    "TradingCalendar",
    "parse_canonical",
    "format_canonical",
    "to_provider_symbol",
    "CanonicalSymbolError",
]
