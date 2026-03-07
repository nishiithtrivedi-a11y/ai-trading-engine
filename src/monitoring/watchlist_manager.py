"""
Watchlist management utilities for Phase 4 monitoring.

Supports local/config-driven watchlists and scanner universe-backed lists.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pandas as pd

from src.monitoring.config import WatchlistDefinition
from src.monitoring.models import Watchlist, WatchlistItem
from src.scanners.universe_resolver import UniverseResolver, UniverseResolverError


class WatchlistManagerError(Exception):
    """Raised when watchlist loading or validation fails."""


@dataclass
class WatchlistManager:
    universe_resolver: Optional[UniverseResolver] = None

    def __post_init__(self) -> None:
        self._resolver = self.universe_resolver or UniverseResolver()

    def load_watchlist(self, definition: WatchlistDefinition) -> Watchlist:
        symbols: list[str] = []
        source_parts: list[str] = []

        if definition.symbols:
            symbols.extend(definition.symbols)
            source_parts.append("symbols")

        if definition.universe_name:
            resolved = self._resolve_universe(definition.universe_name)
            symbols.extend(resolved)
            source_parts.append(f"universe:{definition.universe_name}")

        if definition.file_path:
            file_symbols = self._load_symbols_from_file(definition.file_path, definition.file_format)
            symbols.extend(file_symbols)
            source_parts.append(f"file:{definition.file_path}")

        if not symbols:
            raise WatchlistManagerError(
                f"Watchlist '{definition.name}' resolved to no symbols from configured sources"
            )

        normalized = self._normalize_symbols(symbols)
        items = [
            WatchlistItem(
                symbol=sym,
                tags=list(definition.tags),
                notes=definition.notes,
                default_timeframes=list(definition.default_timeframes),
            )
            for sym in normalized
        ]
        return Watchlist(
            name=definition.name,
            items=items,
            source=" + ".join(source_parts) if source_parts else "custom",
            notes=definition.notes,
            metadata={"definition": definition.name},
        )

    def load_many(self, definitions: list[WatchlistDefinition]) -> dict[str, Watchlist]:
        watchlists: dict[str, Watchlist] = {}
        for definition in definitions:
            watchlist = self.load_watchlist(definition)
            watchlists[watchlist.name] = watchlist
        return watchlists

    def load_from_csv(self, path: str | Path, name: str = "csv_watchlist") -> Watchlist:
        symbols = self._load_symbols_from_csv(path)
        normalized = self._normalize_symbols(symbols)
        return Watchlist(
            name=name,
            items=[WatchlistItem(symbol=s) for s in normalized],
            source=f"file:{path}",
        )

    def load_from_json(self, path: str | Path, name: Optional[str] = None) -> Watchlist:
        path_obj = Path(path)
        if not path_obj.exists():
            raise WatchlistManagerError(f"Watchlist JSON file not found: {path_obj}")

        try:
            payload = json.loads(path_obj.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            raise WatchlistManagerError(f"Failed to parse watchlist JSON {path_obj}: {exc}") from exc

        if isinstance(payload, list):
            symbols = [str(v) for v in payload]
            watchlist_name = name or path_obj.stem
            normalized = self._normalize_symbols(symbols)
            return Watchlist(
                name=watchlist_name,
                items=[WatchlistItem(symbol=s) for s in normalized],
                source=f"file:{path_obj}",
            )

        if not isinstance(payload, dict):
            raise WatchlistManagerError("Watchlist JSON must be an object or a list of symbols")

        symbols = payload.get("symbols")
        items_payload = payload.get("items")

        if symbols is None and items_payload is not None:
            symbols = [row.get("symbol") for row in items_payload if isinstance(row, dict)]
        if symbols is None:
            raise WatchlistManagerError("Watchlist JSON must contain 'symbols' or 'items'")

        definition = WatchlistDefinition(
            name=name or payload.get("name") or path_obj.stem,
            symbols=[str(s) for s in symbols if s is not None],
            tags=[str(t) for t in payload.get("tags", [])],
            notes=str(payload.get("notes", "")),
            default_timeframes=[str(tf) for tf in payload.get("default_timeframes", [])],
        )
        watchlist = self.load_watchlist(definition)
        watchlist.source = f"file:{path_obj}"
        return watchlist

    @staticmethod
    def to_dict(watchlist: Watchlist) -> dict:
        return watchlist.to_dict()

    def _resolve_universe(self, universe_name: str) -> list[str]:
        try:
            return self._resolver.resolve(universe_name=universe_name)
        except UniverseResolverError as exc:
            raise WatchlistManagerError(f"Failed to resolve universe '{universe_name}': {exc}") from exc

    def _normalize_symbols(self, symbols: list[str]) -> list[str]:
        try:
            return self._resolver.normalize_symbols(symbols)
        except UniverseResolverError as exc:
            raise WatchlistManagerError(f"Failed to normalize watchlist symbols: {exc}") from exc

    def _load_symbols_from_file(self, path: str, file_format: Optional[str]) -> list[str]:
        fmt = (file_format or Path(path).suffix.lstrip(".")).strip().lower()
        if fmt == "csv":
            return self._load_symbols_from_csv(path)
        if fmt == "json":
            watchlist = self.load_from_json(path)
            return watchlist.symbols
        raise WatchlistManagerError(
            f"Unsupported watchlist file format '{fmt}' for {path}. Supported: csv, json"
        )

    @staticmethod
    def _load_symbols_from_csv(path: str | Path) -> list[str]:
        path_obj = Path(path)
        if not path_obj.exists():
            raise WatchlistManagerError(f"Watchlist CSV file not found: {path_obj}")

        try:
            df = pd.read_csv(path_obj)
        except Exception as exc:  # noqa: BLE001
            raise WatchlistManagerError(f"Failed to read watchlist CSV {path_obj}: {exc}") from exc

        if df.empty:
            raise WatchlistManagerError(f"Watchlist CSV file is empty: {path_obj}")

        symbol_col = None
        candidates = {"symbol", "ticker", "tradingsymbol", "instrument", "security"}
        for col in df.columns:
            if str(col).strip().lower() in candidates:
                symbol_col = col
                break

        if symbol_col is None:
            raise WatchlistManagerError(
                "Watchlist CSV must contain one of these columns: "
                "symbol, ticker, tradingsymbol, instrument, security"
            )

        symbols = [str(s) for s in df[symbol_col].dropna().astype(str).tolist() if str(s).strip()]
        if not symbols:
            raise WatchlistManagerError(f"No valid symbols found in watchlist CSV: {path_obj}")

        return symbols
