from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.scanners.universe_resolver import UniverseResolver, UniverseResolverError


def test_resolve_builtin_nifty50() -> None:
    resolver = UniverseResolver()
    symbols = resolver.resolve("nifty50")

    assert isinstance(symbols, list)
    assert len(symbols) > 0
    assert "RELIANCE.NS" in symbols
    assert "TCS.NS" in symbols


def test_resolve_builtin_banknifty_alias() -> None:
    resolver = UniverseResolver()
    symbols = resolver.resolve("nifty_bank")

    assert len(symbols) > 0
    assert "HDFCBANK.NS" in symbols
    assert "SBIN.NS" in symbols


def test_resolve_builtin_nifty_next_50() -> None:
    resolver = UniverseResolver()
    symbols = resolver.resolve("nifty_next_50")

    assert len(symbols) > 0
    assert any(sym.endswith(".NS") for sym in symbols)


def test_resolve_custom_csv(tmp_path: Path) -> None:
    file_path = tmp_path / "custom_universe.csv"
    pd.DataFrame({"symbol": ["reliance", "TCS.NS", " infy "]}).to_csv(file_path, index=False)

    resolver = UniverseResolver()
    symbols = resolver.resolve("custom", custom_universe_file=str(file_path))

    assert symbols == ["INFY.NS", "RELIANCE.NS", "TCS.NS"]


def test_normalize_symbols_consistent() -> None:
    resolver = UniverseResolver(sort_symbols=True, deduplicate=True)
    symbols = resolver.normalize_symbols(["reliance", "RELIANCE.NS", "tcs", "TCS.NS"])

    assert symbols == ["RELIANCE.NS", "TCS.NS"]


def test_normalize_symbols_preserve_order_when_sort_disabled() -> None:
    resolver = UniverseResolver(sort_symbols=False, deduplicate=True)
    symbols = resolver.normalize_symbols(["tcs", "reliance", "infy"])

    assert symbols == ["TCS.NS", "RELIANCE.NS", "INFY.NS"]


def test_resolve_custom_missing_file_raises() -> None:
    resolver = UniverseResolver()

    with pytest.raises(UniverseResolverError, match="not found"):
        resolver.resolve("custom", custom_universe_file="does_not_exist.csv")


def test_resolve_custom_without_file_raises() -> None:
    resolver = UniverseResolver()

    with pytest.raises(UniverseResolverError, match="file_path is required"):
        resolver.resolve("custom")


def test_resolve_unknown_universe_raises() -> None:
    resolver = UniverseResolver()

    with pytest.raises(UniverseResolverError, match="Unknown universe name"):
        resolver.resolve("unknown_universe")


def test_resolve_custom_bad_columns_raises(tmp_path: Path) -> None:
    file_path = tmp_path / "bad_universe.csv"
    pd.DataFrame({"name": ["Reliance", "TCS"]}).to_csv(file_path, index=False)

    resolver = UniverseResolver()

    with pytest.raises(UniverseResolverError, match="must contain"):
        resolver.resolve("custom", custom_universe_file=str(file_path))
