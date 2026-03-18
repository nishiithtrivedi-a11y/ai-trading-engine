"""
Derivative-aware data fetching layer.

DerivativeDataFetcher routes derivative data requests to the appropriate
provider methods (primarily Zerodha/Kite). It wraps ZerodhaDataSource and
adds derivative-specific routing logic.

IMPORTANT: This module does NOT add execution behavior — it is data-only.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import TYPE_CHECKING, Optional

import pandas as pd

from src.data.instrument_metadata import InstrumentType
from src.data.quote_normalizer import NormalizedQuote, normalize_kite_quote
from src.instruments.enums import Exchange
from src.instruments.instrument import Instrument

if TYPE_CHECKING:
    from src.data.base import Timeframe
    from src.data.instrument_mapper import KiteInstrumentMapper
    from src.data.sources import ZerodhaDataSource
    from src.instruments.registry import InstrumentRegistry


class DerivativeDataError(ValueError):
    """Raised when a derivative data request cannot be fulfilled."""


class DerivativeDataFetcher:
    """Route derivative data requests to the appropriate provider methods.

    Wraps ZerodhaDataSource and adds derivative-specific routing.
    Does NOT add execution behavior.

    Parameters
    ----------
    zerodha_source:
        ZerodhaDataSource instance. If None, all live/historical fetch
        calls raise DerivativeDataError.
    instrument_mapper:
        KiteInstrumentMapper for token lookup. Optional.
    """

    def __init__(
        self,
        zerodha_source: Optional["ZerodhaDataSource"] = None,
        instrument_mapper: Optional["KiteInstrumentMapper"] = None,
    ) -> None:
        self._zerodha = zerodha_source
        self._mapper = instrument_mapper

    # ------------------------------------------------------------------
    # Historical data
    # ------------------------------------------------------------------

    def fetch_instrument_history(
        self,
        instrument: Instrument,
        timeframe: "Timeframe",
        start: datetime,
        end: datetime,
    ) -> pd.DataFrame:
        """Fetch historical OHLCV data for any instrument type.

        Routes to provider based on instrument.exchange.
        Currently supported: NSE, BSE, NFO, MCX, CDS via ZerodhaDataSource.

        Parameters
        ----------
        instrument:
            Canonical Instrument to fetch data for.
        timeframe:
            Timeframe enum (MINUTE_1, MINUTE_5, etc.).
        start:
            Start datetime.
        end:
            End datetime.

        Returns
        -------
        pd.DataFrame
            OHLCV DataFrame.

        Raises
        ------
        DerivativeDataError
            If no data source is configured or the provider cannot serve the request.
        """
        if self._zerodha is None:
            raise DerivativeDataError(
                f"No ZerodhaDataSource configured — cannot fetch historical data "
                f"for {instrument.canonical!r}. "
                "Instantiate DerivativeDataFetcher with a valid zerodha_source."
            )

        # Build provider symbol for Kite
        try:
            from src.instruments.provider_mapping import instrument_to_kite_symbol
            kite_sym = instrument_to_kite_symbol(instrument)
        except Exception as exc:
            raise DerivativeDataError(
                f"Cannot convert {instrument.canonical!r} to Kite symbol: {exc}"
            ) from exc

        # Determine exchange string for Kite
        exchange_str = instrument.exchange.value

        try:
            df = self._zerodha.get_historical_data(
                symbol=kite_sym,
                timeframe=timeframe,
                start=start,
                end=end,
                exchange=exchange_str,
            )
            return df
        except Exception as exc:
            raise DerivativeDataError(
                f"Failed to fetch historical data for {instrument.canonical!r} "
                f"from Zerodha: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Live quote
    # ------------------------------------------------------------------

    def fetch_instrument_quote(
        self,
        instrument: Instrument,
    ) -> NormalizedQuote:
        """Fetch the latest quote for an instrument.

        Returns a NormalizedQuote with DataQualityFlags set appropriately.
        If the Zerodha source is unavailable, raises DerivativeDataError.

        Parameters
        ----------
        instrument:
            Canonical Instrument to quote.

        Returns
        -------
        NormalizedQuote

        Raises
        ------
        DerivativeDataError
            If no data source is configured or the quote cannot be fetched.
        """
        if self._zerodha is None:
            raise DerivativeDataError(
                f"No ZerodhaDataSource configured — cannot fetch quote "
                f"for {instrument.canonical!r}."
            )

        try:
            from src.instruments.provider_mapping import instrument_to_kite_symbol
            kite_sym = instrument_to_kite_symbol(instrument)
        except Exception as exc:
            raise DerivativeDataError(
                f"Cannot convert {instrument.canonical!r} to Kite symbol: {exc}"
            ) from exc

        exchange_str = instrument.exchange.value
        kite_key = f"{exchange_str}:{kite_sym}"

        try:
            raw_quotes = self._zerodha._kite.quote([kite_key])
            raw = raw_quotes.get(kite_key, {})
            return normalize_kite_quote(instrument.canonical, raw)
        except Exception as exc:
            raise DerivativeDataError(
                f"Failed to fetch quote for {instrument.canonical!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Contract resolution
    # ------------------------------------------------------------------

    def resolve_active_contract(
        self,
        underlying: str,
        exchange: Exchange,
        instrument_type: InstrumentType,
        registry: Optional["InstrumentRegistry"] = None,
        as_of: Optional[date] = None,
    ) -> Optional[Instrument]:
        """Find the nearest active contract for a derivative underlying.

        Parameters
        ----------
        underlying:
            Underlying symbol (e.g. "NIFTY").
        exchange:
            Exchange to search (e.g. Exchange.NFO).
        instrument_type:
            InstrumentType.FUTURE or InstrumentType.OPTION.
        registry:
            InstrumentRegistry to search. If None, returns None.
        as_of:
            Reference date. Defaults to today.

        Returns
        -------
        Instrument or None
            The nearest active contract, or None if not found.
        """
        if registry is None:
            return None

        from src.instruments.contracts import ContractResolver
        resolver = ContractResolver()

        if instrument_type == InstrumentType.FUTURE:
            futures = resolver.resolve_active_futures(
                registry=registry,
                underlying=underlying,
                exchange=exchange,
                as_of=as_of,
            )
            return futures[0] if futures else None

        # For options: return first active option for this underlying
        ref = as_of or date.today()
        underlying_upper = underlying.strip().upper()
        candidates = [
            i for i in registry.all()
            if i.instrument_type == instrument_type
            and i.exchange == exchange
            and i.symbol == underlying_upper
            and i.expiry is not None
            and i.expiry >= ref
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda x: x.expiry)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Static utility
    # ------------------------------------------------------------------

    @staticmethod
    def instrument_to_provider_symbol(instrument: Instrument, provider: str) -> str:
        """Convert an instrument to its provider-native symbol string.

        Parameters
        ----------
        instrument:
            Canonical Instrument object.
        provider:
            Provider name (e.g. "zerodha", "upstox").

        Returns
        -------
        str
            Provider-native symbol string.
        """
        from src.instruments.normalization import to_provider_symbol
        return to_provider_symbol(instrument.canonical, provider)


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

def fetch_instrument_history(
    instrument: Instrument,
    timeframe: "Timeframe",
    start: datetime,
    end: datetime,
    zerodha_source: Optional["ZerodhaDataSource"] = None,
) -> pd.DataFrame:
    """Module-level convenience wrapper for DerivativeDataFetcher.

    Parameters
    ----------
    instrument:
        Canonical Instrument to fetch.
    timeframe:
        Timeframe enum.
    start:
        Start datetime.
    end:
        End datetime.
    zerodha_source:
        ZerodhaDataSource instance (optional).

    Returns
    -------
    pd.DataFrame

    Raises
    ------
    DerivativeDataError
        If no source is provided or the fetch fails.
    """
    fetcher = DerivativeDataFetcher(zerodha_source=zerodha_source)
    return fetcher.fetch_instrument_history(instrument, timeframe, start, end)
