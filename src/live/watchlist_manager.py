"""
Watchlist and universe resolution for the live signal pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.data.nse_universe import NSEUniverseLoader


class LiveWatchlistError(Exception):
    """Raised when watchlist resolution fails."""


@dataclass
class LiveWatchlistManager:
    loader: Optional[NSEUniverseLoader] = None

    def __post_init__(self) -> None:
        self.loader = self.loader or NSEUniverseLoader()

    def resolve(
        self,
        *,
        universe_name: str,
        symbols: Optional[list[str]] = None,
        custom_universe_file: Optional[str] = None,
        symbols_limit: Optional[int] = None,
    ) -> list[str]:
        if symbols:
            resolved = self.loader.normalize_symbols(symbols)
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
