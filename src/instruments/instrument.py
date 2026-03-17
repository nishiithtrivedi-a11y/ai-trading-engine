"""
Canonical Instrument model.

An Instrument is the first-class domain object for representing a tradeable
instrument in the system.  It combines exchange/segment classification with
the field set from InstrumentMetadata and provides a ``canonical`` property
that formats the instrument as a standardised symbol string.

Reuses InstrumentType and OptionType from src.data.instrument_metadata
to avoid duplicating enum definitions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

from src.data.instrument_metadata import InstrumentType, OptionType
from src.instruments.enums import Exchange, Segment


class InstrumentError(ValueError):
    """Raised when an Instrument cannot be constructed or validated."""


@dataclass
class Instrument:
    """
    Canonical instrument model.

    Parameters
    ----------
    symbol:
        Root/underlying symbol, uppercase (e.g. "RELIANCE", "NIFTY", "GOLD").
    exchange:
        Exchange enum (NSE, BSE, NFO, MCX, CDS).
    segment:
        Segment enum (CASH, FO, COMM, CURR).  If not provided, inferred
        from ``exchange`` via :meth:`Segment.from_exchange`.
    instrument_type:
        InstrumentType from src.data.instrument_metadata.
    underlying:
        Underlying asset for derivatives (e.g. "NIFTY" for NFO options).
    expiry:
        Expiry date for futures and options.
    strike:
        Strike price for options (must be > 0).
    option_type:
        OptionType.CALL or OptionType.PUT (options only).
    lot_size:
        Contract lot size (futures/options).
    tick_size:
        Minimum price movement.
    currency:
        Settlement currency (default "INR").
    """

    symbol: str
    exchange: Exchange
    instrument_type: InstrumentType
    segment: Optional[Segment] = None
    underlying: Optional[str] = None
    expiry: Optional[date] = None
    strike: Optional[float] = None
    option_type: Optional[OptionType] = None
    lot_size: Optional[int] = None
    tick_size: Optional[float] = None
    currency: str = "INR"
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        # Normalise symbol
        self.symbol = str(self.symbol).strip().upper()
        if not self.symbol:
            raise InstrumentError("symbol cannot be empty")

        # Normalise currency
        self.currency = str(self.currency).strip().upper()

        # Coerce exchange/instrument_type if strings
        if isinstance(self.exchange, str):
            self.exchange = Exchange(self.exchange.strip().upper())
        if isinstance(self.instrument_type, str):
            self.instrument_type = InstrumentType(
                self.instrument_type.strip().lower()
            )
        if isinstance(self.option_type, str) and self.option_type:
            self.option_type = OptionType(self.option_type.strip().lower())

        # Infer segment from exchange if not provided
        if self.segment is None:
            self.segment = Segment.from_exchange(self.exchange)
        elif isinstance(self.segment, str):
            self.segment = Segment(self.segment.strip().upper())

        # Validate type-specific requirements
        self._validate()

    def _validate(self) -> None:
        if self.instrument_type == InstrumentType.FUTURE and self.expiry is None:
            raise InstrumentError(
                f"Futures instruments require an expiry date: {self.symbol}"
            )
        if self.instrument_type == InstrumentType.OPTION:
            missing = [
                f for f in ("expiry", "strike", "option_type")
                if getattr(self, f) is None
            ]
            if missing:
                raise InstrumentError(
                    f"Option instruments require {missing}: {self.symbol}"
                )
        if self.strike is not None and self.strike <= 0:
            raise InstrumentError(
                f"strike must be > 0, got {self.strike}: {self.symbol}"
            )
        if self.lot_size is not None and self.lot_size < 1:
            raise InstrumentError(
                f"lot_size must be >= 1, got {self.lot_size}: {self.symbol}"
            )
        if self.tick_size is not None and self.tick_size <= 0:
            raise InstrumentError(
                f"tick_size must be > 0, got {self.tick_size}: {self.symbol}"
            )
        # Non-option instruments must not have option-only fields
        if self.instrument_type != InstrumentType.OPTION:
            if self.option_type is not None or self.strike is not None:
                raise InstrumentError(
                    "option_type and strike can only be set for option instruments"
                )

    # ------------------------------------------------------------------
    # Canonical symbol
    # ------------------------------------------------------------------

    @property
    def canonical(self) -> str:
        """Return the canonical symbol string.

        Delegates to :func:`~src.instruments.normalization.format_canonical`.
        """
        from src.instruments.normalization import format_canonical
        return format_canonical(self)

    # ------------------------------------------------------------------
    # Factory helpers
    # ------------------------------------------------------------------

    @classmethod
    def equity(
        cls,
        symbol: str,
        exchange: Exchange = Exchange.NSE,
        **kwargs,
    ) -> "Instrument":
        """Construct an equity instrument."""
        return cls(
            symbol=symbol,
            exchange=exchange,
            instrument_type=InstrumentType.EQUITY,
            **kwargs,
        )

    @classmethod
    def future(
        cls,
        symbol: str,
        expiry: date,
        exchange: Exchange = Exchange.NFO,
        underlying: Optional[str] = None,
        **kwargs,
    ) -> "Instrument":
        """Construct a futures instrument."""
        return cls(
            symbol=symbol,
            exchange=exchange,
            instrument_type=InstrumentType.FUTURE,
            underlying=underlying or symbol,
            expiry=expiry,
            **kwargs,
        )

    @classmethod
    def option(
        cls,
        symbol: str,
        expiry: date,
        strike: float,
        option_type: OptionType,
        exchange: Exchange = Exchange.NFO,
        underlying: Optional[str] = None,
        **kwargs,
    ) -> "Instrument":
        """Construct an option instrument."""
        return cls(
            symbol=symbol,
            exchange=exchange,
            instrument_type=InstrumentType.OPTION,
            underlying=underlying or symbol,
            expiry=expiry,
            strike=strike,
            option_type=option_type,
            **kwargs,
        )

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "canonical": self.canonical,
            "symbol": self.symbol,
            "exchange": self.exchange.value,
            "segment": self.segment.value if self.segment else None,
            "instrument_type": self.instrument_type.value,
            "underlying": self.underlying,
            "expiry": self.expiry.isoformat() if self.expiry else None,
            "strike": self.strike,
            "option_type": self.option_type.value if self.option_type else None,
            "lot_size": self.lot_size,
            "tick_size": self.tick_size,
            "currency": self.currency,
        }

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"Instrument(canonical={self.canonical!r})"
