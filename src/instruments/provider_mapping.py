"""
Provider-native symbol mapping for Indian derivatives.

Converts canonical Instrument objects to provider-specific symbol strings
and parses provider symbols back to Instruments (best-effort).

Zerodha/Kite tradingsymbol format:
  - Equity:          RELIANCE
  - Monthly future:  NIFTY26APRFUT      (SYMBOL + YY + MMM + FUT)
  - Monthly CE opt:  NIFTY26APR24500CE  (SYMBOL + YY + MMM + strike_int + CE/PE)
  - MCX future:      CRUDEOIL26APRFUT
  - CDS future:      USDINR26APRFUT

Upstox segment|symbol format:
  - NSE equity:      NSE_EQ|RELIANCE
  - NFO future:      NSE_FO|NIFTY26APRFUT
  - NFO option:      NSE_FO|NIFTY26APR24500CE
  - MCX:             MCX_FO|GOLD26APRFUT
  - CDS:             CDS_FO|USDINR26APRFUT

Weekly option format is best-effort and varies; monthly format is authoritative.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from src.data.instrument_metadata import InstrumentType, OptionType
from src.instruments.enums import Exchange
from src.instruments.instrument import Instrument


class ProviderMappingError(ValueError):
    """Raised when a symbol cannot be mapped to/from a provider format."""


# ---------------------------------------------------------------------------
# Month abbreviation lookup
# ---------------------------------------------------------------------------

_MONTH_ABBR: dict[int, str] = {
    1: "JAN", 2: "FEB", 3: "MAR", 4: "APR",
    5: "MAY", 6: "JUN", 7: "JUL", 8: "AUG",
    9: "SEP", 10: "OCT", 11: "NOV", 12: "DEC",
}

_MONTH_NAME_TO_INT: dict[str, int] = {v: k for k, v in _MONTH_ABBR.items()}

# ---------------------------------------------------------------------------
# Exchange <-> segment maps
# ---------------------------------------------------------------------------

_KITE_SEGMENT_MAP: dict[Exchange, str] = {
    Exchange.NSE: "NSE",
    Exchange.BSE: "BSE",
    Exchange.NFO: "NFO",
    Exchange.MCX: "MCX",
    Exchange.CDS: "CDS",
}

_UPSTOX_SEGMENT_MAP: dict[Exchange, str] = {
    Exchange.NSE: "NSE_EQ",
    Exchange.BSE: "BSE_EQ",
    Exchange.NFO: "NSE_FO",
    Exchange.MCX: "MCX_FO",
    Exchange.CDS: "CDS_FO",
}

# String exchange -> Exchange enum (for parsing)
_EXCHANGE_STR_MAP: dict[str, Exchange] = {
    "NSE": Exchange.NSE,
    "BSE": Exchange.BSE,
    "NFO": Exchange.NFO,
    "MCX": Exchange.MCX,
    "CDS": Exchange.CDS,
}

# ---------------------------------------------------------------------------
# Kite symbol regex patterns
# ---------------------------------------------------------------------------

# Monthly future: SYMBOL + 2-digit-year + 3-char-month + FUT
# e.g. NIFTY26APRFUT, CRUDEOIL26APRFUT
_MONTHLY_FUT_RE = re.compile(r'^([A-Z0-9]+?)(\d{2})([A-Z]{3})(FUT)$')

# Monthly option: SYMBOL + 2-digit-year + 3-char-month + integer_or_decimal_strike + CE/PE
# e.g. NIFTY26APR24500CE, USDINR26APR84CE
_MONTHLY_OPT_RE = re.compile(r'^([A-Z0-9]+?)(\d{2})([A-Z]{3})(\d+(?:\.\d+)?)(CE|PE)$')


# ---------------------------------------------------------------------------
# instrument_to_kite_symbol
# ---------------------------------------------------------------------------

def instrument_to_kite_symbol(instrument: Instrument) -> str:
    """Convert an Instrument to Kite tradingsymbol format.

    Rules:
    - EQUITY / INDEX / ETF  -> bare symbol (e.g. "RELIANCE")
    - FUTURE                -> SYMBOLYYMMMFUT (e.g. "NIFTY26APRFUT")
    - OPTION                -> SYMBOLYYMMM{strike}{CE|PE} (e.g. "NIFTY26APR24500CE")

    Weekly options follow the same monthly pattern here (best-effort).
    The Kite weekly compact format (NIFTY2524500CE) is NOT generated —
    it varies by broker API version and is documented as unsupported.

    Raises
    ------
    ProviderMappingError
        If required fields (expiry, strike, option_type) are missing.
    """
    itype = instrument.instrument_type
    symbol = instrument.symbol.upper()

    if itype in (InstrumentType.EQUITY, InstrumentType.INDEX, InstrumentType.ETF):
        return symbol

    if itype == InstrumentType.FUTURE:
        if instrument.expiry is None:
            raise ProviderMappingError(
                f"Future {symbol!r} is missing expiry — cannot generate Kite symbol"
            )
        yy = str(instrument.expiry.year)[2:]
        mmm = _MONTH_ABBR[instrument.expiry.month]
        return f"{symbol}{yy}{mmm}FUT"

    if itype == InstrumentType.OPTION:
        if instrument.expiry is None:
            raise ProviderMappingError(
                f"Option {symbol!r} is missing expiry — cannot generate Kite symbol"
            )
        if instrument.strike is None:
            raise ProviderMappingError(
                f"Option {symbol!r} is missing strike — cannot generate Kite symbol"
            )
        if instrument.option_type is None:
            raise ProviderMappingError(
                f"Option {symbol!r} is missing option_type — cannot generate Kite symbol"
            )
        yy = str(instrument.expiry.year)[2:]
        mmm = _MONTH_ABBR[instrument.expiry.month]
        # Use integer strike if it is a whole number
        strike = instrument.strike
        strike_str = str(int(strike)) if strike == int(strike) else str(strike)
        otype = "CE" if instrument.option_type == OptionType.CALL else "PE"
        return f"{symbol}{yy}{mmm}{strike_str}{otype}"

    # COMMODITY / FOREX / CRYPTO with expiry → treat as future pattern
    if instrument.expiry is not None:
        yy = str(instrument.expiry.year)[2:]
        mmm = _MONTH_ABBR[instrument.expiry.month]
        return f"{symbol}{yy}{mmm}FUT"

    # Fallback: bare symbol
    return symbol


# ---------------------------------------------------------------------------
# instrument_to_upstox_symbol
# ---------------------------------------------------------------------------

def instrument_to_upstox_symbol(instrument: Instrument) -> str:
    """Convert an Instrument to Upstox segment|symbol format.

    Format: <SEGMENT>|<KITE_SYMBOL>
    e.g. "NSE_EQ|RELIANCE", "NSE_FO|NIFTY26APRFUT"

    Raises
    ------
    ProviderMappingError
        If the exchange is not mapped or required fields are missing.
    """
    segment = _UPSTOX_SEGMENT_MAP.get(instrument.exchange)
    if segment is None:
        raise ProviderMappingError(
            f"Exchange {instrument.exchange.value!r} has no Upstox segment mapping"
        )
    kite_sym = instrument_to_kite_symbol(instrument)
    return f"{segment}|{kite_sym}"


# ---------------------------------------------------------------------------
# kite_symbol_to_instrument
# ---------------------------------------------------------------------------

def kite_symbol_to_instrument(kite_symbol: str, exchange: str) -> Instrument:
    """Parse a Kite tradingsymbol back to an Instrument (best-effort).

    Handles:
    - Monthly futures: NIFTY26APRFUT
    - Monthly options: NIFTY26APR24500CE / PE
    - Equity: RELIANCE (fallback when no derivative pattern matches)

    Parameters
    ----------
    kite_symbol:
        Kite tradingsymbol string (uppercase expected).
    exchange:
        Exchange string (NSE, BSE, NFO, MCX, CDS).

    Returns
    -------
    Instrument

    Raises
    ------
    ProviderMappingError
        If the symbol or exchange cannot be parsed.
    """
    sym = kite_symbol.strip().upper()
    exc_str = exchange.strip().upper()
    exc = _EXCHANGE_STR_MAP.get(exc_str)
    if exc is None:
        raise ProviderMappingError(
            f"Unknown exchange string {exchange!r} — cannot parse Kite symbol {kite_symbol!r}"
        )

    # Try monthly option first (more specific pattern)
    m = _MONTHLY_OPT_RE.match(sym)
    if m:
        underlying = m.group(1)
        yy = int(m.group(2))
        mmm = m.group(3)
        strike_raw = m.group(4)
        ce_pe = m.group(5)

        month = _MONTH_NAME_TO_INT.get(mmm)
        if month is None:
            raise ProviderMappingError(
                f"Unknown month abbreviation {mmm!r} in Kite symbol {kite_symbol!r}"
            )

        # Infer year: 2-digit year, assume 2000+
        year = 2000 + yy
        # Approximate expiry as last day of month (exact day not known from symbol)
        expiry = _last_day_of_month(year, month)
        strike = float(strike_raw)
        option_type = OptionType.CALL if ce_pe == "CE" else OptionType.PUT

        return Instrument.option(
            symbol=underlying,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
            exchange=exc,
        )

    # Try monthly future
    m = _MONTHLY_FUT_RE.match(sym)
    if m:
        underlying = m.group(1)
        yy = int(m.group(2))
        mmm = m.group(3)

        month = _MONTH_NAME_TO_INT.get(mmm)
        if month is None:
            raise ProviderMappingError(
                f"Unknown month abbreviation {mmm!r} in Kite symbol {kite_symbol!r}"
            )

        year = 2000 + yy
        expiry = _last_day_of_month(year, month)

        return Instrument.future(
            symbol=underlying,
            expiry=expiry,
            exchange=exc,
        )

    # Fallback: treat as equity
    return Instrument.equity(symbol=sym, exchange=exc)


# ---------------------------------------------------------------------------
# canonical_to_kite / canonical_to_upstox / kite_to_canonical
# ---------------------------------------------------------------------------

def canonical_to_kite(canonical: str) -> str:
    """Convert a canonical symbol to Kite tradingsymbol format.

    e.g. "NFO:NIFTY-2026-04-30-FUT" -> "NIFTY26APRFUT"

    Raises
    ------
    ProviderMappingError
        If the canonical symbol cannot be parsed or mapped.
    """
    from src.instruments.normalization import parse_canonical, CanonicalSymbolError
    try:
        inst = parse_canonical(canonical)
    except CanonicalSymbolError as exc:
        raise ProviderMappingError(
            f"Cannot parse canonical symbol {canonical!r}: {exc}"
        ) from exc
    return instrument_to_kite_symbol(inst)


def canonical_to_upstox(canonical: str) -> str:
    """Convert a canonical symbol to Upstox segment|symbol format.

    e.g. "NFO:NIFTY-2026-04-30-FUT" -> "NSE_FO|NIFTY26APRFUT"

    Raises
    ------
    ProviderMappingError
        If the canonical symbol cannot be parsed or mapped.
    """
    from src.instruments.normalization import parse_canonical, CanonicalSymbolError
    try:
        inst = parse_canonical(canonical)
    except CanonicalSymbolError as exc:
        raise ProviderMappingError(
            f"Cannot parse canonical symbol {canonical!r}: {exc}"
        ) from exc
    return instrument_to_upstox_symbol(inst)


def kite_to_canonical(kite_symbol: str, exchange: str) -> str:
    """Convert a Kite tradingsymbol + exchange string to canonical format.

    e.g. ("NIFTY26APRFUT", "NFO") -> "NFO:NIFTY-2026-04-30-FUT"

    Note: The expiry date in the canonical output is the last day of the
    month inferred from the Kite symbol — not the actual exchange expiry.
    Use TradingCalendar.get_monthly_expiry() to get the exact Thursday expiry.

    Raises
    ------
    ProviderMappingError
        If the symbol cannot be parsed.
    """
    inst = kite_symbol_to_instrument(kite_symbol, exchange)
    return inst.canonical


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _last_day_of_month(year: int, month: int) -> date:
    """Return the last calendar day of the given month."""
    import datetime
    if month == 12:
        return date(year, 12, 31)
    return date(year, month + 1, 1) - datetime.timedelta(days=1)


# ---------------------------------------------------------------------------
# Dhan symbol mapping
# ---------------------------------------------------------------------------

_DHAN_SEGMENT_MAP: dict[Exchange, str] = {
    Exchange.NSE: "NSE_EQ",
    Exchange.BSE: "BSE_EQ",
    Exchange.NFO: "NSE_FO",
    Exchange.MCX: "MCX",
    Exchange.CDS: "CUR",
}


def instrument_to_dhan_symbol(instrument: Instrument) -> str:
    """Convert Instrument to DhanHQ trading symbol.

    DhanHQ uses the same base tradingsymbol as Kite for most instruments.
    The key difference is the exchange segment string.
    """
    return instrument_to_kite_symbol(instrument)  # same tradingsymbol, different segment


def instrument_to_dhan_segment(instrument: Instrument) -> str:
    """Return the DhanHQ exchange segment string for an Instrument."""
    return _DHAN_SEGMENT_MAP.get(instrument.exchange, "NSE_EQ")


def canonical_to_dhan(canonical: str) -> tuple[str, str]:
    """Convert canonical symbol to (dhan_symbol, dhan_segment) tuple.

    Returns:
        (tradingsymbol, exchange_segment) e.g. ("NIFTY26APRFUT", "NSE_FO")

    Raises
    ------
    ProviderMappingError
        If the canonical symbol cannot be parsed or mapped.
    """
    from src.instruments.normalization import parse_canonical, CanonicalSymbolError
    try:
        inst = parse_canonical(canonical)
    except CanonicalSymbolError as exc:
        raise ProviderMappingError(
            f"Cannot parse canonical symbol {canonical!r}: {exc}"
        ) from exc
    return instrument_to_dhan_symbol(inst), instrument_to_dhan_segment(inst)
