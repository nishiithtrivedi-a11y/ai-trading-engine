"""
Kite Connect instrument mapping layer.

Downloads the Zerodha instrument list, caches it locally, and provides
fast lookups to map engine symbols (e.g. "RELIANCE") to Kite instrument
tokens required for historical data and order placement.

Usage::

    from src.data.instrument_mapper import KiteInstrumentMapper

    mapper = KiteInstrumentMapper(kite_client)
    mapper.refresh_cache()                       # downloads + caches
    token = mapper.get_instrument_token("RELIANCE")
    token = mapper.get_instrument_token("RELIANCE.NS")  # also works
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from src.data.symbol_mapping import SymbolMapper
from src.utils.logger import setup_logger

logger = setup_logger("instrument_mapper")

# Default cache location (relative to project root)
DEFAULT_CACHE_PATH = "data/cache/kite_instruments.csv"

# Maximum cache age before a refresh warning (24 hours)
CACHE_MAX_AGE_HOURS = 24


class KiteInstrumentMapper:
    """Map engine symbols to Kite instrument tokens.

    Lazily loads the instrument cache on first lookup. Call
    ``refresh_cache()`` to download a fresh instrument list from Kite.

    Args:
        kite: Authenticated KiteConnect client instance.
        exchange: Default exchange for lookups (default: "NSE").
        cache_path: Path to the CSV cache file.
    """

    def __init__(
        self,
        kite,
        exchange: str = "NSE",
        cache_path: str = DEFAULT_CACHE_PATH,
    ) -> None:
        self._kite = kite
        self._exchange = exchange
        self._cache_path = Path(cache_path)
        self._instruments_df: Optional[pd.DataFrame] = None
        self._symbol_mapper = SymbolMapper()

    # ------------------------------------------------------------------
    # Cache management
    # ------------------------------------------------------------------

    def refresh_cache(self, exchange: Optional[str] = None) -> pd.DataFrame:
        """Download instruments from Kite and save to local CSV cache.

        Args:
            exchange: Exchange to download (default: ``self._exchange``).

        Returns:
            DataFrame of instruments.
        """
        exc = exchange or self._exchange
        logger.info(f"Downloading instruments for exchange: {exc}")

        instruments = self._kite.instruments(exc)
        df = pd.DataFrame(instruments)

        # Ensure cache directory exists
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)

        df.to_csv(self._cache_path, index=False)
        logger.info(
            f"Cached {len(df)} instruments to {self._cache_path}"
        )

        self._instruments_df = df
        return df

    def _load_cache(self) -> pd.DataFrame:
        """Load instrument cache from disk, refreshing if stale or missing."""
        if not self._cache_path.exists():
            logger.info("No instrument cache found — downloading from Kite")
            return self.refresh_cache()

        # Check staleness
        mtime = datetime.fromtimestamp(self._cache_path.stat().st_mtime)
        age_hours = (datetime.now() - mtime).total_seconds() / 3600

        if age_hours > CACHE_MAX_AGE_HOURS:
            logger.warning(
                f"Instrument cache is {age_hours:.1f}h old "
                f"(max={CACHE_MAX_AGE_HOURS}h). Consider running "
                f"refresh_cache() for the latest instruments."
            )

        df = pd.read_csv(self._cache_path)
        logger.info(f"Loaded {len(df)} instruments from cache")
        return df

    def _ensure_loaded(self) -> None:
        """Ensure the instrument DataFrame is loaded."""
        if self._instruments_df is None:
            self._instruments_df = self._load_cache()

    # ------------------------------------------------------------------
    # Lookups
    # ------------------------------------------------------------------

    def get_instrument_token(
        self,
        symbol: str,
        exchange: Optional[str] = None,
    ) -> int:
        """Resolve a trading symbol to its Kite instrument token.

        Accepts engine symbols like "RELIANCE", "RELIANCE.NS",
        "NSE_EQ|RELIANCE" — all are normalised to the base symbol
        before lookup.

        Args:
            symbol: Trading symbol in any supported format.
            exchange: Override exchange (default: ``self._exchange``).

        Returns:
            Integer instrument token.

        Raises:
            ValueError: If the symbol is not found.
        """
        self._ensure_loaded()
        exc = exchange or self._exchange
        base = self._symbol_mapper.normalize(symbol)

        mask = (
            (self._instruments_df["tradingsymbol"] == base)
            & (self._instruments_df["exchange"] == exc)
        )
        matches = self._instruments_df[mask]

        if matches.empty:
            raise ValueError(
                f"Instrument not found: {base} on {exc}. "
                f"Try refresh_cache() or check the symbol spelling."
            )

        token = int(matches.iloc[0]["instrument_token"])
        logger.debug(f"Resolved {base}@{exc} -> token {token}")
        return token

    def normalize_symbol_for_kite(self, symbol: str) -> str:
        """Convert any symbol format to Kite's bare tradingsymbol.

        Args:
            symbol: Symbol in any format (RELIANCE.NS, NSE_EQ|RELIANCE, etc.).

        Returns:
            Bare tradingsymbol (e.g. "RELIANCE").
        """
        return self._symbol_mapper.to_zerodha(symbol)

    def get_instrument_info(
        self,
        symbol: str,
        exchange: Optional[str] = None,
    ) -> dict:
        """Get full instrument metadata for a symbol.

        Args:
            symbol: Trading symbol in any supported format.
            exchange: Override exchange.

        Returns:
            Dict with all instrument fields (tradingsymbol, name,
            lot_size, tick_size, instrument_type, etc.).

        Raises:
            ValueError: If the symbol is not found.
        """
        self._ensure_loaded()
        exc = exchange or self._exchange
        base = self._symbol_mapper.normalize(symbol)

        mask = (
            (self._instruments_df["tradingsymbol"] == base)
            & (self._instruments_df["exchange"] == exc)
        )
        matches = self._instruments_df[mask]

        if matches.empty:
            raise ValueError(f"Instrument not found: {base} on {exc}")

        return matches.iloc[0].to_dict()

    def search_instruments(
        self,
        query: str,
        exchange: Optional[str] = None,
        limit: int = 20,
    ) -> pd.DataFrame:
        """Search instruments by partial name or tradingsymbol.

        Args:
            query: Partial match string (case-insensitive).
            exchange: Filter to a specific exchange.
            limit: Maximum results to return.

        Returns:
            DataFrame of matching instruments.
        """
        self._ensure_loaded()
        df = self._instruments_df
        q = query.upper()

        mask = (
            df["tradingsymbol"].str.contains(q, case=False, na=False)
            | df["name"].str.contains(q, case=False, na=False)
        )

        if exchange:
            mask = mask & (df["exchange"] == exchange)

        return df[mask].head(limit)

    @property
    def cache_path(self) -> Path:
        """Path to the local instrument cache file."""
        return self._cache_path

    @property
    def instrument_count(self) -> int:
        """Number of instruments currently loaded."""
        self._ensure_loaded()
        return len(self._instruments_df)

    # ------------------------------------------------------------------
    # Multi-segment support (Phase 2)
    # ------------------------------------------------------------------

    def refresh_all_segments(
        self,
        exchanges: Optional[list[str]] = None,
    ) -> dict[str, pd.DataFrame]:
        """Download instruments for multiple exchanges and cache results.

        Parameters
        ----------
        exchanges:
            List of exchange strings to download.
            Default: ["NSE", "BSE", "NFO", "MCX", "CDS"].

        Returns
        -------
        dict mapping exchange string -> DataFrame of instruments.
        """
        target_exchanges = exchanges or ["NSE", "BSE", "NFO", "MCX", "CDS"]
        results: dict[str, pd.DataFrame] = {}

        for exc in target_exchanges:
            logger.info(f"refresh_all_segments: downloading {exc}")
            try:
                instruments = self._kite.instruments(exc)
                df = pd.DataFrame(instruments)
                results[exc] = df
            except Exception as exc_err:
                logger.warning(f"refresh_all_segments: failed for {exc}: {exc_err}")
                results[exc] = pd.DataFrame()

        # Combine all into master cache
        if results:
            all_dfs = [df for df in results.values() if not df.empty]
            if all_dfs:
                combined = pd.concat(all_dfs, ignore_index=True)
                self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                combined.to_csv(self._cache_path, index=False)
                self._instruments_df = combined
                logger.info(f"refresh_all_segments: cached {len(combined)} total instruments")

        return results

    def get_instruments_by_segment(self, exchange: str) -> pd.DataFrame:
        """Return cached instruments for a specific exchange/segment.

        Parameters
        ----------
        exchange:
            Exchange string (e.g. "NSE", "NFO", "MCX").

        Returns
        -------
        pd.DataFrame filtered to the given exchange. Empty DataFrame if not found.
        """
        self._ensure_loaded()
        df = self._instruments_df
        if "exchange" not in df.columns:
            return pd.DataFrame()
        return df[df["exchange"] == exchange.strip().upper()].reset_index(drop=True)

    def to_instrument_object(
        self,
        row: dict,
        hydrator=None,
    ) -> Optional["Instrument"]:
        """Convert a single instrument cache row to an Instrument object.

        Parameters
        ----------
        row:
            Dict with instrument fields (tradingsymbol, exchange,
            instrument_type, expiry, strike, lot_size, tick_size, etc.).
        hydrator:
            Optional InstrumentHydrator instance. If None, creates a new one.

        Returns
        -------
        Instrument or None if hydration fails.
        """
        if hydrator is None:
            from src.instruments.hydrator import InstrumentHydrator
            hydrator = InstrumentHydrator()
        return hydrator.hydrate_from_kite_row(row)

    def hydrate_registry(
        self,
        registry,
        exchanges: Optional[list[str]] = None,
        hydrator=None,
        replace: bool = False,
    ) -> int:
        """Populate an InstrumentRegistry from the instrument cache.

        Parameters
        ----------
        registry:
            InstrumentRegistry instance to populate.
        exchanges:
            If provided, only process instruments from these exchanges.
        hydrator:
            Optional InstrumentHydrator. Created internally if None.
        replace:
            Passed to registry.add() — if True, replaces existing instruments.

        Returns
        -------
        int
            Count of instruments successfully added.
        """
        self._ensure_loaded()

        if hydrator is None:
            from src.instruments.hydrator import InstrumentHydrator
            hydrator = InstrumentHydrator()

        df = self._instruments_df
        if exchanges:
            exc_upper = [e.strip().upper() for e in exchanges]
            if "exchange" in df.columns:
                df = df[df["exchange"].isin(exc_upper)]

        rows = df.to_dict("records")
        added = 0
        for row in rows:
            inst = hydrator.hydrate_from_kite_row(row)
            if inst is None:
                continue
            try:
                registry.add(inst, replace=replace)
                added += 1
            except Exception as err:
                logger.debug(f"hydrate_registry: skipping {row.get('tradingsymbol')}: {err}")

        logger.info(f"hydrate_registry: added {added} instruments to registry")
        return added
