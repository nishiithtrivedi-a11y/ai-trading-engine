"""
Instrument Registry — in-memory lookup store for Instrument objects.

The InstrumentRegistry provides:
- O(1) lookup by canonical symbol
- Linear-scan lookup by raw symbol + exchange
- Filtering by InstrumentType or Segment
- Simple iteration and length
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from src.data.instrument_metadata import InstrumentType
from src.instruments.enums import Exchange, Segment
from src.instruments.instrument import Instrument


class InstrumentRegistryError(ValueError):
    """Raised when a registry operation fails."""


class InstrumentRegistry:
    """
    In-memory registry of :class:`~src.instruments.instrument.Instrument` objects.

    Instruments are indexed by their canonical symbol string for O(1) lookup.

    Usage
    -----
        registry = InstrumentRegistry()
        registry.add(Instrument.equity("RELIANCE", Exchange.NSE))
        instr = registry.get("NSE:RELIANCE-EQ")
    """

    def __init__(self) -> None:
        # Primary index: canonical → Instrument
        self._store: dict[str, Instrument] = {}

    # ------------------------------------------------------------------
    # Mutation
    # ------------------------------------------------------------------

    def add(self, instrument: Instrument, *, replace: bool = False) -> None:
        """
        Add an instrument to the registry.

        Parameters
        ----------
        instrument:
            :class:`Instrument` instance to add.
        replace:
            If True, silently replaces any existing instrument with the same
            canonical symbol.  If False (default), raises
            :exc:`InstrumentRegistryError` on conflict.
        """
        key = instrument.canonical
        if key in self._store and not replace:
            raise InstrumentRegistryError(
                f"Instrument {key!r} is already registered. "
                "Use replace=True to overwrite."
            )
        self._store[key] = instrument

    def add_many(
        self,
        instruments: list[Instrument],
        *,
        replace: bool = False,
    ) -> None:
        """Add multiple instruments at once."""
        for instrument in instruments:
            self.add(instrument, replace=replace)

    def remove(self, canonical: str) -> None:
        """Remove an instrument by canonical symbol.  No-op if not found."""
        self._store.pop(canonical, None)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, canonical: str) -> Optional[Instrument]:
        """Return the instrument with the given canonical symbol, or None."""
        return self._store.get(canonical)

    def lookup(
        self,
        symbol: str,
        exchange: Exchange,
        instrument_type: Optional[InstrumentType] = None,
    ) -> Optional[Instrument]:
        """
        Look up an instrument by raw symbol and exchange.

        Linear scan over the registry.  Use :meth:`get` (O(1)) when the
        canonical symbol is known.

        Parameters
        ----------
        symbol:
            Raw symbol string, case-insensitive (e.g. ``"reliance"``).
        exchange:
            Exchange enum.
        instrument_type:
            If provided, further filter by instrument type.

        Returns
        -------
        Instrument or None
        """
        symbol_upper = symbol.strip().upper()
        for instr in self._store.values():
            if instr.symbol != symbol_upper:
                continue
            if instr.exchange != exchange:
                continue
            if instrument_type is not None and instr.instrument_type != instrument_type:
                continue
            return instr
        return None

    # ------------------------------------------------------------------
    # Filtering
    # ------------------------------------------------------------------

    def list_by_type(
        self, instrument_type: InstrumentType
    ) -> list[Instrument]:
        """Return all instruments of a given type."""
        return [
            i for i in self._store.values()
            if i.instrument_type == instrument_type
        ]

    def list_by_exchange(self, exchange: Exchange) -> list[Instrument]:
        """Return all instruments on a given exchange."""
        return [i for i in self._store.values() if i.exchange == exchange]

    def list_by_segment(self, segment: Segment) -> list[Instrument]:
        """Return all instruments in a given market segment."""
        return [i for i in self._store.values() if i.segment == segment]

    def all(self) -> list[Instrument]:
        """Return all registered instruments."""
        return list(self._store.values())

    # ------------------------------------------------------------------
    # Derivative filtering (Phase 2)
    # ------------------------------------------------------------------

    def list_by_underlying(
        self,
        underlying: str,
        exchange: Optional[Exchange] = None,
    ) -> list[Instrument]:
        """Return all derivatives with the given underlying symbol.

        Parameters
        ----------
        underlying:
            Underlying symbol to match (case-insensitive).
        exchange:
            If provided, further filter by exchange.

        Returns
        -------
        List of instruments whose ``symbol`` or ``underlying`` matches.
        """
        underlying_upper = underlying.strip().upper()
        result = []
        for i in self._store.values():
            sym_match = (
                i.symbol == underlying_upper
                or (i.underlying is not None and i.underlying.upper() == underlying_upper)
            )
            if not sym_match:
                continue
            if exchange is not None and i.exchange != exchange:
                continue
            result.append(i)
        return result

    def list_by_expiry(self, expiry: date) -> list[Instrument]:
        """Return all instruments with the given expiry date.

        Parameters
        ----------
        expiry:
            Exact expiry date to match.

        Returns
        -------
        List of instruments with expiry == expiry.
        """
        return [i for i in self._store.values() if i.expiry == expiry]

    def list_active_futures(self, as_of: Optional[date] = None) -> list[Instrument]:
        """Return futures with expiry >= as_of (today if None).

        Parameters
        ----------
        as_of:
            Reference date. Defaults to today.

        Returns
        -------
        List of active futures sorted by expiry ascending.
        """
        ref = as_of or date.today()
        futures = [
            i for i in self._store.values()
            if i.instrument_type == InstrumentType.FUTURE
            and i.expiry is not None
            and i.expiry >= ref
        ]
        return sorted(futures, key=lambda x: x.expiry)  # type: ignore[arg-type, return-value]

    def list_option_chain(
        self,
        underlying: str,
        expiry: date,
        exchange: Optional[Exchange] = None,
    ) -> list[Instrument]:
        """Return all options for a given underlying and expiry, sorted by strike.

        Parameters
        ----------
        underlying:
            Underlying symbol (case-insensitive).
        expiry:
            Exact expiry date.
        exchange:
            If provided, further filter by exchange.

        Returns
        -------
        List of option instruments sorted by strike ascending.
        """
        underlying_upper = underlying.strip().upper()
        result = []
        for i in self._store.values():
            if i.instrument_type != InstrumentType.OPTION:
                continue
            if i.expiry != expiry:
                continue
            sym_match = (
                i.symbol == underlying_upper
                or (i.underlying is not None and i.underlying.upper() == underlying_upper)
            )
            if not sym_match:
                continue
            if exchange is not None and i.exchange != exchange:
                continue
            result.append(i)
        return sorted(result, key=lambda x: x.strike or 0.0)

    # ------------------------------------------------------------------
    # Dunder
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        return len(self._store)

    def __contains__(self, canonical: str) -> bool:
        return canonical in self._store

    def __repr__(self) -> str:
        return f"InstrumentRegistry(count={len(self._store)})"
