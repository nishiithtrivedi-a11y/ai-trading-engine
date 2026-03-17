"""
NSE symbol normalization and mapping layer.

Canonical internal representation:
- Yahoo/NSE style exchange suffix (default): ``RELIANCE.NS``

Provider adapters translate canonical symbols at boundaries:
- Zerodha: ``RELIANCE``
- Upstox: ``NSE_EQ|RELIANCE``
- CSV filename stems: ``RELIANCE``
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional


# Known exchange suffixes
_EXCHANGE_SUFFIXES = {".NS", ".BO", ".NFO"}

# Upstox exchange prefixes
_UPSTOX_PREFIXES = {"NSE_EQ", "BSE_EQ", "NSE_FO", "NSE_INDEX"}

# Exchange-prefixed symbols
_EXCHANGE_COLON_PREFIXES = {"NSE", "BSE", "NFO", "NSE_EQ", "BSE_EQ", "NSE_FO", "NSE_INDEX"}


class SymbolMapper:
    """Normalize and convert symbols between provider formats.

    Usage:
        mapper = SymbolMapper()
        mapper.to_yahoo("RELIANCE")       # -> "RELIANCE.NS"
        mapper.to_zerodha("RELIANCE.NS")  # -> "RELIANCE"
        mapper.to_upstox("RELIANCE")      # -> "NSE_EQ|RELIANCE"
        mapper.from_filename("RELIANCE_1D.csv")  # -> "RELIANCE"
    """

    def __init__(self, default_exchange: str = ".NS") -> None:
        self.default_exchange = default_exchange
        self._aliases: Dict[str, str] = {}

    def normalize(self, symbol: str) -> str:
        """Strip exchange suffixes/prefixes to get the base symbol.

        Examples:
            "RELIANCE.NS"       -> "RELIANCE"
            "NSE_EQ|RELIANCE"   -> "RELIANCE"
            "RELIANCE"          -> "RELIANCE"
            "reliance"          -> "RELIANCE"
        """
        s = symbol.strip().upper()

        # Check alias table first
        if s in self._aliases:
            return self._aliases[s]

        # Strip Yahoo-style suffix (.NS, .BO)
        for suffix in _EXCHANGE_SUFFIXES:
            if s.endswith(suffix):
                return s[: -len(suffix)]

        # Strip Upstox-style prefix (NSE_EQ|RELIANCE)
        if "|" in s:
            parts = s.split("|", 1)
            if parts[0] in _UPSTOX_PREFIXES:
                return parts[1]

        # Strip exchange-prefixed symbols (NSE:RELIANCE)
        if ":" in s:
            parts = s.split(":", 1)
            if parts[0] in _EXCHANGE_COLON_PREFIXES:
                return parts[1]

        return s

    def to_canonical(self, symbol: str, exchange_suffix: Optional[str] = None) -> str:
        """Convert any provider/display format into canonical internal symbol."""
        base = self.normalize(symbol)
        suffix = str(exchange_suffix or self.default_exchange).strip().upper()
        if not suffix.startswith("."):
            suffix = f".{suffix}"
        return f"{base}{suffix}"

    def to_yahoo(self, symbol: str, exchange: Optional[str] = None) -> str:
        """Convert to Yahoo Finance format (e.g. RELIANCE.NS)."""
        base = self.normalize(symbol)
        suffix = exchange or self.default_exchange
        return f"{base}{suffix}"

    def to_zerodha(self, symbol: str) -> str:
        """Convert to Zerodha format (bare symbol, e.g. RELIANCE)."""
        return self.normalize(symbol)

    def to_upstox(
        self, symbol: str, segment: str = "NSE_EQ"
    ) -> str:
        """Convert to Upstox format (e.g. NSE_EQ|RELIANCE)."""
        base = self.normalize(symbol)
        return f"{segment}|{base}"

    def to_provider_symbol(self, provider_name: str, symbol: str) -> str:
        """
        Translate canonical/display symbol into provider boundary format.

        Returns:
            csv/indian_csv -> base symbol for filename mapping
            zerodha        -> bare symbol
            upstox         -> NSE_EQ|<base>
            default        -> canonical symbol
        """
        provider = str(provider_name).strip().lower()
        if provider in {"csv", "indian_csv"}:
            return self.normalize(symbol)
        if provider == "zerodha":
            return self.to_zerodha(symbol)
        if provider == "upstox":
            return self.to_upstox(symbol)
        return self.to_canonical(symbol)

    def from_provider_symbol(self, provider_name: str, symbol: str) -> str:
        """Translate provider symbol into canonical internal representation."""
        _ = str(provider_name).strip().lower()
        return self.to_canonical(symbol)

    def from_filename(self, filename: str) -> str:
        """Extract base symbol from a data filename.

        Examples:
            "RELIANCE_1D.csv"  -> "RELIANCE"
            "TCS_5m.csv"       -> "TCS"
            "NIFTY_BANK_1D.csv" -> "NIFTY_BANK"
            "data/INFY_1D.csv" -> "INFY"
        """
        # Strip directory path
        name = filename.replace("\\", "/").split("/")[-1]
        # Strip extension
        name = re.sub(r"\.\w+$", "", name)
        # Strip trailing timeframe pattern (_1D, _5m, _15m, _1h, _1M)
        name = re.sub(r"_(?:1[mMhD]|5[mM]|15[mM]|1D)$", "", name)
        return name.upper()

    def add_alias(self, alias: str, canonical: str) -> None:
        """Register a symbol alias.

        Args:
            alias: The alternate name (e.g. "NIFTY 50").
            canonical: The canonical base symbol (e.g. "NIFTY50").
        """
        self._aliases[alias.strip().upper()] = canonical.strip().upper()

    def batch_normalize(self, symbols: List[str]) -> List[str]:
        """Normalize a list of symbols, removing duplicates."""
        seen = set()
        result = []
        for sym in symbols:
            base = self.normalize(sym)
            if base not in seen:
                seen.add(base)
                result.append(base)
        return result

    def batch_to_yahoo(self, symbols: List[str]) -> List[str]:
        """Convert a list of symbols to Yahoo format."""
        return [self.to_yahoo(s) for s in symbols]
