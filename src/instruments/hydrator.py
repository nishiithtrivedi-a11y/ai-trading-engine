"""
Instrument hydration — converting provider-native metadata rows to Instrument objects.

The InstrumentHydrator converts provider-specific instrument metadata
(e.g. Kite instrument list rows) into canonical Instrument domain objects.
Malformed or unsupported rows are skipped gracefully in batch operations.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from src.data.instrument_metadata import InstrumentType, OptionType
from src.instruments.enums import Exchange
from src.instruments.instrument import Instrument


class InstrumentHydrationError(ValueError):
    """Raised when an instrument row cannot be hydrated."""


# ---------------------------------------------------------------------------
# Kite instrument_type -> InstrumentType mapping
# ---------------------------------------------------------------------------

_KITE_TYPE_MAP: dict[str, InstrumentType] = {
    "EQ": InstrumentType.EQUITY,
    "FUT": InstrumentType.FUTURE,
    "CE": InstrumentType.OPTION,
    "PE": InstrumentType.OPTION,
    "IDX": InstrumentType.INDEX,
    "ETF": InstrumentType.ETF,
}

_KITE_OPTION_TYPE_MAP: dict[str, OptionType] = {
    "CE": OptionType.CALL,
    "PE": OptionType.PUT,
}

# String -> Exchange
_EXCHANGE_STR_MAP: dict[str, Exchange] = {
    "NSE": Exchange.NSE,
    "BSE": Exchange.BSE,
    "NFO": Exchange.NFO,
    "MCX": Exchange.MCX,
    "CDS": Exchange.CDS,
}


def _parse_expiry(raw) -> Optional[date]:
    """Parse expiry from various formats (date, str YYYY-MM-DD, or None)."""
    if raw is None:
        return None
    if isinstance(raw, date):
        return raw
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw or raw.lower() in ("", "nan", "nat", "none", "null"):
            return None
        try:
            return date.fromisoformat(raw[:10])  # handle datetime strings too
        except (ValueError, TypeError):
            return None
    return None


def _parse_float(raw) -> Optional[float]:
    """Parse float from raw value, returning None on failure."""
    if raw is None:
        return None
    try:
        val = float(raw)
        if val != val:  # NaN check
            return None
        return val
    except (ValueError, TypeError):
        return None


def _parse_int(raw) -> Optional[int]:
    """Parse int from raw value, returning None on failure."""
    if raw is None:
        return None
    try:
        val = float(raw)
        if val != val:
            return None
        return int(val)
    except (ValueError, TypeError):
        return None


class InstrumentHydrator:
    """Convert provider-native instrument metadata to Instrument objects."""

    # ------------------------------------------------------------------
    # Kite hydration
    # ------------------------------------------------------------------

    def hydrate_from_kite_row(self, row: dict) -> Optional[Instrument]:
        """Convert a single Kite instruments() row to an Instrument.

        Kite row fields:
            instrument_token, exchange_token, tradingsymbol, name,
            last_price, expiry, strike, tick_size, lot_size,
            instrument_type (EQ, FUT, CE, PE, IDX, ETF),
            segment, exchange

        Returns None if the row is malformed or unsupported.
        """
        try:
            kite_type_str = str(row.get("instrument_type", "")).strip().upper()
            if not kite_type_str:
                return None

            instrument_type = _KITE_TYPE_MAP.get(kite_type_str)
            if instrument_type is None:
                return None

            exchange_str = str(row.get("exchange", "")).strip().upper()
            exchange = _EXCHANGE_STR_MAP.get(exchange_str)
            if exchange is None:
                return None

            tradingsymbol = str(row.get("tradingsymbol", "")).strip().upper()
            if not tradingsymbol:
                return None

            expiry = _parse_expiry(row.get("expiry"))
            strike_raw = _parse_float(row.get("strike"))
            lot_size = _parse_int(row.get("lot_size"))
            tick_size = _parse_float(row.get("tick_size"))
            option_type = _KITE_OPTION_TYPE_MAP.get(kite_type_str)

            # Validate requirements before building
            if instrument_type == InstrumentType.FUTURE and expiry is None:
                return None
            if instrument_type == InstrumentType.OPTION:
                if expiry is None or strike_raw is None or option_type is None:
                    return None
                if strike_raw <= 0:
                    return None

            # For non-option instruments, Kite returns strike=0.0 as placeholder.
            # Instrument.strike must be > 0 or None, so map 0.0 -> None.
            if instrument_type != InstrumentType.OPTION:
                strike = None
            else:
                strike = strike_raw

            # Determine the canonical symbol for this instrument.
            # For derivatives (FUT/CE/PE), the Kite 'name' field contains the
            # underlying symbol (e.g. "NIFTY"), while 'tradingsymbol' is the
            # full contract name (e.g. "NIFTY26APR24500CE").
            # For equity/index/etf, tradingsymbol is the canonical symbol.
            name_str = str(row.get("name", "")).strip().upper()
            if instrument_type in (InstrumentType.FUTURE, InstrumentType.OPTION):
                # Use name (underlying) as the canonical symbol if available
                symbol = name_str if name_str else tradingsymbol
            else:
                symbol = tradingsymbol

            return Instrument(
                symbol=symbol,
                exchange=exchange,
                instrument_type=instrument_type,
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                lot_size=lot_size,
                tick_size=tick_size if tick_size and tick_size > 0 else None,
                metadata={"tradingsymbol": tradingsymbol} if tradingsymbol != symbol else {},
            )

        except Exception:
            return None

    def hydrate_from_kite_list(
        self,
        rows: list[dict],
        *,
        exchange_filter: Optional[str] = None,
    ) -> list[Instrument]:
        """Batch hydrate from Kite instrument list, skipping malformed rows.

        Parameters
        ----------
        rows:
            List of Kite instrument dicts.
        exchange_filter:
            If provided, only hydrate rows matching this exchange string.

        Returns
        -------
        List of successfully hydrated Instrument objects.
        """
        result: list[Instrument] = []
        for row in rows:
            if exchange_filter:
                row_exchange = str(row.get("exchange", "")).strip().upper()
                if row_exchange != exchange_filter.strip().upper():
                    continue
            inst = self.hydrate_from_kite_row(row)
            if inst is not None:
                result.append(inst)
        return result

    # ------------------------------------------------------------------
    # Generic dict hydration
    # ------------------------------------------------------------------

    def hydrate_from_dict(self, d: dict) -> Optional[Instrument]:
        """Generic hydration from a normalized dict (provider-agnostic).

        Expected keys:
            symbol (str), exchange (str), instrument_type (str),
            optionally: expiry (YYYY-MM-DD str or date), strike (float),
            option_type ('call'/'put'/'CE'/'PE'), lot_size (int),
            tick_size (float), underlying (str), currency (str), metadata (dict)

        Returns None if required fields are missing or invalid.
        """
        try:
            symbol = str(d.get("symbol", "")).strip().upper()
            if not symbol:
                return None

            exchange_str = str(d.get("exchange", "")).strip().upper()
            exchange = _EXCHANGE_STR_MAP.get(exchange_str)
            if exchange is None:
                return None

            itype_raw = str(d.get("instrument_type", "")).strip().lower()
            # Support both "equity" and Kite-style "EQ"
            _itype_alias = {
                "eq": "equity",
                "fut": "future",
                "ce": "option",
                "pe": "option",
                "idx": "index",
                "etf": "etf",
            }
            itype_raw = _itype_alias.get(itype_raw, itype_raw)
            try:
                instrument_type = InstrumentType(itype_raw)
            except ValueError:
                return None

            expiry = _parse_expiry(d.get("expiry"))
            strike = _parse_float(d.get("strike"))
            lot_size = _parse_int(d.get("lot_size"))
            tick_size = _parse_float(d.get("tick_size"))

            # option_type parsing
            option_type: Optional[OptionType] = None
            raw_ot = d.get("option_type")
            if raw_ot is not None:
                ot_str = str(raw_ot).strip().lower()
                _ot_alias = {"ce": "call", "pe": "put"}
                ot_str = _ot_alias.get(ot_str, ot_str)
                try:
                    option_type = OptionType(ot_str)
                except ValueError:
                    pass

            underlying = d.get("underlying")
            if underlying:
                underlying = str(underlying).strip().upper()

            currency = str(d.get("currency", "INR")).strip().upper() or "INR"
            metadata = dict(d.get("metadata", {})) if d.get("metadata") else {}

            if instrument_type == InstrumentType.FUTURE and expiry is None:
                return None
            if instrument_type == InstrumentType.OPTION:
                if expiry is None or strike is None or option_type is None:
                    return None

            return Instrument(
                symbol=symbol,
                exchange=exchange,
                instrument_type=instrument_type,
                expiry=expiry,
                strike=strike,
                option_type=option_type,
                lot_size=lot_size,
                tick_size=tick_size if tick_size and tick_size > 0 else None,
                underlying=underlying,
                currency=currency,
                metadata=metadata,
            )

        except Exception:
            return None

    # ------------------------------------------------------------------
    # Equity list hydration
    # ------------------------------------------------------------------

    def hydrate_equity_list(
        self,
        symbols: list[str],
        exchange: Exchange = Exchange.NSE,
    ) -> list[Instrument]:
        """Hydrate a list of equity symbols into Instrument objects.

        Parameters
        ----------
        symbols:
            List of equity symbol strings (case-insensitive).
        exchange:
            Exchange for all symbols (default: Exchange.NSE).

        Returns
        -------
        List of Instrument objects. Empty strings are skipped.
        """
        result: list[Instrument] = []
        for sym in symbols:
            sym_clean = str(sym).strip().upper()
            if not sym_clean:
                continue
            try:
                inst = Instrument.equity(sym_clean, exchange=exchange)
                result.append(inst)
            except Exception:
                continue
        return result
