"""
Canonical symbol normalisation for the Instrument Master.

Canonical format
----------------
The canonical symbol format uniquely identifies an instrument across all
supported asset classes:

    EXCHANGE:UNDERLYING[-EXPIRY-SUFFIX]

Examples:

    NSE:RELIANCE-EQ                    # NSE equity
    BSE:TCS-EQ                         # BSE equity
    NFO:NIFTY-2026-04-30-FUT           # NFO future (expiry YYYY-MM-DD)
    NFO:NIFTY-2026-04-30-24500-CE      # NFO call option (strike CE/PE)
    NFO:BANKNIFTY-2026-04-30-48000-PE  # NFO put option
    MCX:GOLD-2026-04-30-FUT            # MCX commodity future
    CDS:USDINR-2026-04-30-FUT          # CDS forex future

Provider mapping hooks
----------------------
``to_provider_symbol()`` converts a canonical symbol to a provider-specific
format (Zerodha, Upstox, etc.).  Stub implementations raise NotImplementedError
until the provider-specific logic is wired in.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from src.data.instrument_metadata import InstrumentType, OptionType
from src.instruments.enums import Exchange, Segment


class CanonicalSymbolError(ValueError):
    """Raised when a canonical symbol cannot be parsed or formatted."""


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

def format_canonical(instrument: "Instrument") -> str:  # noqa: F821 — forward ref
    """
    Format an Instrument as its canonical symbol string.

    Parameters
    ----------
    instrument:
        :class:`~src.instruments.instrument.Instrument` instance.

    Returns
    -------
    str
        Canonical symbol e.g. ``"NSE:RELIANCE-EQ"`` or
        ``"NFO:NIFTY-2026-04-30-24500-CE"``.
    """
    exchange = instrument.exchange.value
    symbol = instrument.symbol.upper()
    itype = instrument.instrument_type

    if itype == InstrumentType.EQUITY:
        return f"{exchange}:{symbol}-EQ"

    if itype == InstrumentType.FUTURE:
        expiry = _format_expiry(instrument.expiry)
        return f"{exchange}:{symbol}-{expiry}-FUT"

    if itype == InstrumentType.OPTION:
        expiry = _format_expiry(instrument.expiry)
        strike = _format_strike(instrument.strike)
        otype = "CE" if instrument.option_type == OptionType.CALL else "PE"
        return f"{exchange}:{symbol}-{expiry}-{strike}-{otype}"

    if itype == InstrumentType.INDEX:
        return f"{exchange}:{symbol}-IDX"

    if itype == InstrumentType.ETF:
        return f"{exchange}:{symbol}-ETF"

    if itype in (InstrumentType.COMMODITY, InstrumentType.FOREX, InstrumentType.CRYPTO):
        if instrument.expiry is not None:
            expiry = _format_expiry(instrument.expiry)
            return f"{exchange}:{symbol}-{expiry}-FUT"
        return f"{exchange}:{symbol}"

    # Fallback
    return f"{exchange}:{symbol}"


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def parse_canonical(canonical: str) -> "Instrument":  # noqa: F821
    """
    Parse a canonical symbol string into an :class:`~src.instruments.instrument.Instrument`.

    Parameters
    ----------
    canonical:
        A string in the canonical format, e.g. ``"NSE:RELIANCE-EQ"`` or
        ``"NFO:NIFTY-2026-04-30-24500-CE"``.

    Returns
    -------
    Instrument

    Raises
    ------
    CanonicalSymbolError
        If the string is not in recognised canonical format.
    """
    from src.instruments.instrument import Instrument

    if ":" not in canonical:
        raise CanonicalSymbolError(
            f"Canonical symbol must contain ':' separator: {canonical!r}"
        )

    exchange_str, rest = canonical.split(":", 1)

    try:
        exchange = Exchange(exchange_str.strip().upper())
    except ValueError:
        raise CanonicalSymbolError(
            f"Unknown exchange {exchange_str!r} in canonical symbol {canonical!r}"
        ) from None

    parts = rest.strip().split("-")

    if not parts:
        raise CanonicalSymbolError(f"Empty instrument spec in canonical symbol {canonical!r}")

    # Equity: SYMBOL-EQ  or  Index: SYMBOL-IDX  or  ETF: SYMBOL-ETF
    if parts[-1] in ("EQ", "IDX", "ETF"):
        symbol = "-".join(parts[:-1]).upper()
        suffix_map = {
            "EQ": InstrumentType.EQUITY,
            "IDX": InstrumentType.INDEX,
            "ETF": InstrumentType.ETF,
        }
        return Instrument(
            symbol=symbol,
            exchange=exchange,
            instrument_type=suffix_map[parts[-1]],
        )

    # Future: SYMBOL-YYYY-MM-DD-FUT  (e.g. NIFTY-2026-04-30-FUT)
    if parts[-1] == "FUT" and len(parts) >= 5:
        expiry = _parse_expiry_from_parts(parts[-4:-1])
        symbol = "-".join(parts[: len(parts) - 4]).upper()
        return Instrument(
            symbol=symbol,
            exchange=exchange,
            instrument_type=InstrumentType.FUTURE,
            expiry=expiry,
        )

    # Option: SYMBOL-YYYY-MM-DD-STRIKE-CE/PE
    if parts[-1] in ("CE", "PE") and len(parts) >= 6:
        option_type = OptionType.CALL if parts[-1] == "CE" else OptionType.PUT
        try:
            strike = float(parts[-2])
        except ValueError:
            raise CanonicalSymbolError(
                f"Invalid strike {parts[-2]!r} in canonical symbol {canonical!r}"
            ) from None
        expiry = _parse_expiry_from_parts(parts[-5:-2])
        symbol = "-".join(parts[: len(parts) - 5]).upper()
        return Instrument(
            symbol=symbol,
            exchange=exchange,
            instrument_type=InstrumentType.OPTION,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
        )

    # Simple: EXCHANGE:SYMBOL (no suffix — fallback to equity)
    if len(parts) == 1:
        return Instrument(
            symbol=parts[0].upper(),
            exchange=exchange,
            instrument_type=InstrumentType.EQUITY,
        )

    raise CanonicalSymbolError(
        f"Cannot parse canonical symbol {canonical!r}. "
        "Expected formats: NSE:SYM-EQ, NFO:SYM-YYYY-MM-DD-FUT, "
        "NFO:SYM-YYYY-MM-DD-STRIKE-CE/PE"
    )


# ---------------------------------------------------------------------------
# Provider mapping hooks (stubs)
# ---------------------------------------------------------------------------

def to_provider_symbol(canonical: str, provider: str) -> str:
    """
    Convert a canonical symbol to a provider-specific trading symbol.

    Parameters
    ----------
    canonical:
        Canonical symbol string (e.g. ``"NSE:RELIANCE-EQ"``).
    provider:
        Provider name (e.g. ``"zerodha"``, ``"upstox"``, ``"csv"``).

    Returns
    -------
    str
        Provider-native symbol string.

    Raises
    ------
    ProviderMappingError
        If the canonical symbol cannot be mapped for the given provider.
    NotImplementedError
        If the provider is not yet supported.
    """
    from src.instruments.provider_mapping import (
        canonical_to_kite,
        canonical_to_upstox,
        ProviderMappingError,
    )

    p = str(provider).strip().lower()

    if p in ("zerodha", "kite"):
        return canonical_to_kite(canonical)

    if p == "upstox":
        return canonical_to_upstox(canonical)

    if p in ("csv", "indian_csv"):
        # For CSV providers, return the bare symbol part of the canonical
        inst = parse_canonical(canonical)
        return inst.symbol

    raise NotImplementedError(
        f"Provider symbol mapping for '{provider}' is not yet implemented. "
        f"Cannot convert canonical symbol '{canonical}' to {provider} format."
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------

def _format_expiry(expiry: Optional[date]) -> str:
    if expiry is None:
        raise CanonicalSymbolError("Expiry date is required for this instrument type")
    return expiry.strftime("%Y-%m-%d")


def _format_strike(strike: Optional[float]) -> str:
    if strike is None:
        raise CanonicalSymbolError("Strike is required for option instruments")
    # Format: integer if whole number, else decimal
    if strike == int(strike):
        return str(int(strike))
    return f"{strike:.2f}".rstrip("0").rstrip(".")


_DATE_RE = re.compile(r"^\d{4}$")  # year part of YYYY-MM-DD triplet


def _parse_expiry_from_parts(parts: list[str]) -> date:
    """Parse YYYY, MM, DD from a 3-element list of string parts."""
    if len(parts) != 3:
        raise CanonicalSymbolError(
            f"Expected 3 date parts (YYYY, MM, DD), got {parts!r}"
        )
    try:
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except (ValueError, TypeError) as exc:
        raise CanonicalSymbolError(
            f"Invalid date parts {parts!r}: {exc}"
        ) from exc
