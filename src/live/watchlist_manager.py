"""
Watchlist and universe resolution for the live signal pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.data.nse_universe import NSEUniverseLoader
from src.data.symbol_mapping import SymbolMapper


class LiveWatchlistError(Exception):
    """Raised when watchlist resolution fails."""


@dataclass
class LiveWatchlistManager:
    loader: Optional[NSEUniverseLoader] = None
    symbol_mapper: Optional[SymbolMapper] = None

    def __post_init__(self) -> None:
        self.loader = self.loader or NSEUniverseLoader()
        self.symbol_mapper = self.symbol_mapper or SymbolMapper()

    def resolve(
        self,
        *,
        universe_name: str,
        symbols: Optional[list[str]] = None,
        custom_universe_file: Optional[str] = None,
        symbols_limit: Optional[int] = None,
    ) -> list[str]:
        if symbols:
            rows = [self.symbol_mapper.to_canonical(symbol) for symbol in symbols if str(symbol).strip()]
            resolved = list(dict.fromkeys(rows))
        else:
            try:
                resolved = self.loader.get_universe(
                    universe_name=universe_name,
                    file_path=custom_universe_file,
                )
            except Exception as exc:  # noqa: BLE001
                raise LiveWatchlistError(
                    f"Failed to resolve universe '{universe_name}': {exc}"
                ) from exc

        if symbols_limit is not None and symbols_limit > 0:
            resolved = resolved[: int(symbols_limit)]

        if not resolved:
            raise LiveWatchlistError("Resolved watchlist is empty")

        return resolved
