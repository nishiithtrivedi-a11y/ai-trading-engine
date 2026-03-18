"""
Active contract resolution and option chain utilities.

ContractResolver provides utilities for filtering, grouping, and resolving
derivative contracts (futures and options) from an Instrument list.
It does NOT perform execution — purely data/filtering logic.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Optional

from src.data.instrument_metadata import InstrumentType
from src.instruments.calendar import TradingCalendar
from src.instruments.enums import Exchange
from src.instruments.instrument import Instrument

if TYPE_CHECKING:
    from src.instruments.registry import InstrumentRegistry


class ContractNotFoundError(ValueError):
    """Raised when a requested contract cannot be resolved."""


class ContractResolver:
    """Utilities for resolving active derivative contracts.

    Parameters
    ----------
    calendar:
        TradingCalendar instance for expiry validation.
        Defaults to a new TradingCalendar with standard NSE holidays.
    """

    def __init__(self, calendar: Optional[TradingCalendar] = None) -> None:
        self._calendar = calendar or TradingCalendar()

    # ------------------------------------------------------------------
    # Active contract filtering
    # ------------------------------------------------------------------

    def get_active_contracts(
        self,
        instruments: list[Instrument],
        as_of: Optional[date] = None,
    ) -> list[Instrument]:
        """Filter to instruments with expiry >= as_of (today if None).

        Instruments without an expiry date (e.g. equities) are excluded.

        Parameters
        ----------
        instruments:
            List of Instrument objects to filter.
        as_of:
            Reference date. Defaults to today.

        Returns
        -------
        List of instruments whose expiry is >= as_of.
        """
        ref = as_of or date.today()
        return [
            i for i in instruments
            if i.expiry is not None and i.expiry >= ref
        ]

    def get_nearest_expiry(
        self,
        instruments: list[Instrument],
        as_of: Optional[date] = None,
    ) -> Optional[date]:
        """Return the nearest upcoming expiry from a list of instruments.

        Parameters
        ----------
        instruments:
            List of Instrument objects.
        as_of:
            Reference date. Defaults to today.

        Returns
        -------
        The nearest expiry date, or None if no active contracts exist.
        """
        active = self.get_active_contracts(instruments, as_of=as_of)
        if not active:
            return None
        expiries = [i.expiry for i in active if i.expiry is not None]
        return min(expiries) if expiries else None

    def list_expiries(
        self,
        instruments: list[Instrument],
        as_of: Optional[date] = None,
    ) -> list[date]:
        """Return sorted list of unique upcoming expiry dates.

        Parameters
        ----------
        instruments:
            List of Instrument objects.
        as_of:
            Reference date. Defaults to today.

        Returns
        -------
        Sorted list of unique expiry dates for active instruments.
        """
        active = self.get_active_contracts(instruments, as_of=as_of)
        unique: set[date] = {i.expiry for i in active if i.expiry is not None}
        return sorted(unique)

    def filter_by_expiry(
        self,
        instruments: list[Instrument],
        expiry: date,
    ) -> list[Instrument]:
        """Return instruments matching a specific expiry date.

        Parameters
        ----------
        instruments:
            List of Instrument objects.
        expiry:
            Exact expiry date to match.

        Returns
        -------
        List of instruments with expiry == expiry.
        """
        return [i for i in instruments if i.expiry == expiry]

    # ------------------------------------------------------------------
    # Option chain utilities
    # ------------------------------------------------------------------

    def get_option_chain(
        self,
        instruments: list[Instrument],
        expiry: date,
    ) -> dict[str, list[Instrument]]:
        """Group options by type for a given expiry.

        Parameters
        ----------
        instruments:
            List of Instrument objects (can include non-options; they are skipped).
        expiry:
            Expiry date to filter on.

        Returns
        -------
        Dict with keys "calls" and "puts", each containing a list of
        Instrument objects sorted by strike ascending.
        """
        from src.data.instrument_metadata import OptionType

        options = [
            i for i in instruments
            if i.instrument_type == InstrumentType.OPTION and i.expiry == expiry
        ]
        calls = sorted(
            [o for o in options if o.option_type == OptionType.CALL],
            key=lambda x: x.strike or 0.0,
        )
        puts = sorted(
            [o for o in options if o.option_type == OptionType.PUT],
            key=lambda x: x.strike or 0.0,
        )
        return {"calls": calls, "puts": puts}

    def get_strikes(
        self,
        instruments: list[Instrument],
        expiry: date,
    ) -> list[float]:
        """Return sorted unique strikes for a given expiry.

        Parameters
        ----------
        instruments:
            List of Instrument objects.
        expiry:
            Expiry date to filter on.

        Returns
        -------
        Sorted list of unique strike prices.
        """
        options = [
            i for i in instruments
            if i.instrument_type == InstrumentType.OPTION
            and i.expiry == expiry
            and i.strike is not None
        ]
        unique_strikes: set[float] = {i.strike for i in options}  # type: ignore[misc]
        return sorted(unique_strikes)

    # ------------------------------------------------------------------
    # Registry-based resolution
    # ------------------------------------------------------------------

    def resolve_active_futures(
        self,
        registry: "InstrumentRegistry",
        underlying: str,
        exchange: Exchange = Exchange.NFO,
        as_of: Optional[date] = None,
    ) -> list[Instrument]:
        """Find active futures for an underlying from the registry.

        Parameters
        ----------
        registry:
            InstrumentRegistry to query.
        underlying:
            Underlying symbol (case-insensitive, e.g. "NIFTY").
        exchange:
            Exchange to filter on (default: Exchange.NFO).
        as_of:
            Reference date. Defaults to today.

        Returns
        -------
        List of active futures sorted by expiry ascending.
        """
        underlying_upper = underlying.strip().upper()
        ref = as_of or date.today()

        futures = [
            i for i in registry.all()
            if i.instrument_type == InstrumentType.FUTURE
            and i.exchange == exchange
            and i.symbol == underlying_upper
            and i.expiry is not None
            and i.expiry >= ref
        ]
        return sorted(futures, key=lambda x: x.expiry)  # type: ignore[arg-type, return-value]
