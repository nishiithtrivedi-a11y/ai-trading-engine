"""
Instrument metadata scaffolding for provider/runtime capability validation.

This module is intentionally lightweight and does not implement derivatives
trading logic. It provides explicit metadata models and validation helpers
to make future instrument support less ad hoc.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class InstrumentMetadataError(ValueError):
    """Raised when instrument metadata is invalid or incomplete."""


class InstrumentType(str, Enum):
    EQUITY = "equity"
    ETF = "etf"
    INDEX = "index"
    FUTURE = "future"
    OPTION = "option"
    COMMODITY = "commodity"
    FOREX = "forex"
    CRYPTO = "crypto"


class OptionType(str, Enum):
    CALL = "call"
    PUT = "put"


@dataclass
class TradingSessionProfile:
    """Simple session profile for an instrument/market."""

    timezone: str = "Asia/Kolkata"
    open_time: str = "09:15"
    close_time: str = "15:30"

    def __post_init__(self) -> None:
        if not _is_hhmm(self.open_time):
            raise InstrumentMetadataError("open_time must be in HH:MM format")
        if not _is_hhmm(self.close_time):
            raise InstrumentMetadataError("close_time must be in HH:MM format")


@dataclass
class InstrumentMetadata:
    """
    Metadata contract for an instrument.

    Notes:
    - This model is a validation/scaffolding layer, not an execution contract.
    - For options/futures, required metadata is enforced explicitly.
    """

    symbol: str
    instrument_type: InstrumentType | str = InstrumentType.EQUITY
    exchange: str = "NSE"
    currency: str = "INR"
    lot_size: int = 1
    tick_size: float = 0.05
    expiry_date: date | None = None
    strike: float | None = None
    option_type: OptionType | str | None = None
    session_profile: TradingSessionProfile = field(default_factory=TradingSessionProfile)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.symbol = str(self.symbol).strip().upper()
        if not self.symbol:
            raise InstrumentMetadataError("symbol cannot be empty")

        self.instrument_type = normalize_instrument_type(self.instrument_type)
        self.exchange = str(self.exchange).strip().upper()
        self.currency = str(self.currency).strip().upper()

        if int(self.lot_size) < 1:
            raise InstrumentMetadataError("lot_size must be >= 1")
        self.lot_size = int(self.lot_size)

        if float(self.tick_size) <= 0:
            raise InstrumentMetadataError("tick_size must be > 0")
        self.tick_size = float(self.tick_size)

        if self.option_type is not None and not isinstance(self.option_type, OptionType):
            self.option_type = OptionType(str(self.option_type).strip().lower())

        self._validate_type_requirements()

    def _validate_type_requirements(self) -> None:
        required = required_metadata_fields(self.instrument_type)
        missing: list[str] = []
        for field_name in required:
            value = getattr(self, field_name)
            if value is None:
                missing.append(field_name)

        if missing:
            raise InstrumentMetadataError(
                f"{self.instrument_type.value} instruments require metadata fields: {missing}"
            )

        if self.instrument_type != InstrumentType.OPTION:
            # Keep option metadata clean for non-option instruments.
            if self.option_type is not None or self.strike is not None:
                raise InstrumentMetadataError(
                    "option_type/strike can only be set for option instruments"
                )

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "instrument_type": self.instrument_type.value,
            "exchange": self.exchange,
            "currency": self.currency,
            "lot_size": self.lot_size,
            "tick_size": self.tick_size,
            "expiry_date": self.expiry_date.isoformat() if self.expiry_date else None,
            "strike": self.strike,
            "option_type": self.option_type.value if self.option_type else None,
            "session_profile": {
                "timezone": self.session_profile.timezone,
                "open_time": self.session_profile.open_time,
                "close_time": self.session_profile.close_time,
            },
            "metadata": dict(self.metadata),
        }


def normalize_instrument_type(value: InstrumentType | str) -> InstrumentType:
    if isinstance(value, InstrumentType):
        return value
    return InstrumentType(str(value).strip().lower())


def required_metadata_fields(instrument_type: InstrumentType | str) -> tuple[str, ...]:
    kind = normalize_instrument_type(instrument_type)
    if kind == InstrumentType.FUTURE:
        return ("expiry_date",)
    if kind == InstrumentType.OPTION:
        return ("expiry_date", "strike", "option_type")
    return ()


def _is_hhmm(value: str) -> bool:
    text = str(value).strip()
    parts = text.split(":")
    if len(parts) != 2:
        return False
    if len(parts[0]) != 2 or len(parts[1]) != 2:
        return False
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except ValueError:
        return False
    return 0 <= hour <= 23 and 0 <= minute <= 59
