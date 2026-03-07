"""
Universe resolver for stock scanner.

Wraps NSEUniverseLoader with a small explicit interface suitable for
scanner orchestration.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from src.data.nse_universe import NSEUniverseError, NSEUniverseLoader, UniverseConfig


class UniverseResolverError(Exception):
    """Raised when resolving or validating scanner universe fails."""


@dataclass
class UniverseResolver:
    """
    Resolve and normalize scanner universe symbols.

    Args:
        exchange_suffix: Exchange suffix for normalized symbols (default .NS).
        deduplicate: Remove duplicates.
        sort_symbols: Sort symbols alphabetically.
        uppercase: Uppercase symbols.
    """

    exchange_suffix: str = ".NS"
    deduplicate: bool = True
    sort_symbols: bool = True
    uppercase: bool = True

    def __post_init__(self) -> None:
        cfg = UniverseConfig(
            exchange_suffix=self.exchange_suffix,
            deduplicate=self.deduplicate,
            sort_symbols=self.sort_symbols,
            uppercase=self.uppercase,
        )
        self._loader = NSEUniverseLoader(config=cfg)

    def resolve(self, universe_name: str, custom_universe_file: Optional[str] = None) -> list[str]:
        """
        Resolve symbols for the requested universe.

        Supported built-ins include: nifty50, banknifty, nifty_next_50.
        For custom CSV universe, pass universe_name='custom' and file path.
        """
        try:
            symbols = self._loader.get_universe(
                universe_name=universe_name,
                file_path=custom_universe_file,
            )
        except NSEUniverseError as exc:
            raise UniverseResolverError(str(exc)) from exc

        if not symbols:
            raise UniverseResolverError(
                f"Universe '{universe_name}' resolved to an empty symbol list"
            )

        return symbols

    def normalize_symbols(self, symbols: list[str]) -> list[str]:
        """Normalize ad-hoc symbol lists with resolver's configured policy."""
        try:
            return self._loader.normalize_symbols(symbols)
        except NSEUniverseError as exc:
            raise UniverseResolverError(str(exc)) from exc
