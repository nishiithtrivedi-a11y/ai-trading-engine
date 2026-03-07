from pathlib import Path

import pandas as pd
import pytest

from src.data.nse_universe import NSEUniverseError, NSEUniverseLoader, UniverseConfig


def test_get_nifty50_returns_list():
    loader = NSEUniverseLoader()
    universe = loader.get_nifty50()

    assert isinstance(universe, list)
    assert len(universe) > 0
    assert "RELIANCE.NS" in universe
    assert "TCS.NS" in universe


def test_get_banknifty_constituents_returns_list():
    loader = NSEUniverseLoader()
    universe = loader.get_banknifty_constituents()

    assert isinstance(universe, list)
    assert len(universe) > 0
    assert "HDFCBANK.NS" in universe
    assert "SBIN.NS" in universe


def test_normalize_symbol_adds_ns_suffix():
    loader = NSEUniverseLoader()
    assert loader.normalize_symbol("reliance") == "RELIANCE.NS"


def test_normalize_symbol_keeps_existing_suffix():
    loader = NSEUniverseLoader()
    assert loader.normalize_symbol("RELIANCE.NS") == "RELIANCE.NS"


def test_normalize_symbols_deduplicates():
    loader = NSEUniverseLoader()
    symbols = loader.normalize_symbols(["reliance", "RELIANCE.NS", "tcs", "TCS"])
    assert symbols.count("RELIANCE.NS") == 1
    assert symbols.count("TCS.NS") == 1


def test_normalize_symbols_preserves_order_when_sort_disabled():
    loader = NSEUniverseLoader(UniverseConfig(sort_symbols=False))
    symbols = loader.normalize_symbols(["tcs", "reliance", "infy"])
    assert symbols == ["TCS.NS", "RELIANCE.NS", "INFY.NS"]


def test_get_custom_universe_from_symbol_column(tmp_path: Path):
    file_path = tmp_path / "universe.csv"
    pd.DataFrame({"symbol": ["reliance", "tcs", "infy"]}).to_csv(file_path, index=False)

    loader = NSEUniverseLoader()
    universe = loader.get_custom_universe(file_path)

    assert universe == ["INFY.NS", "RELIANCE.NS", "TCS.NS"]


def test_get_custom_universe_from_ticker_column(tmp_path: Path):
    file_path = tmp_path / "universe.csv"
    pd.DataFrame({"ticker": ["RELIANCE.NS", "TCS.NS"]}).to_csv(file_path, index=False)

    loader = NSEUniverseLoader()
    universe = loader.get_custom_universe(file_path)

    assert universe == ["RELIANCE.NS", "TCS.NS"]


def test_get_custom_universe_missing_file_raises():
    loader = NSEUniverseLoader()

    with pytest.raises(NSEUniverseError):
        loader.get_custom_universe("does_not_exist.csv")


def test_get_custom_universe_missing_symbol_column_raises(tmp_path: Path):
    file_path = tmp_path / "bad_universe.csv"
    pd.DataFrame({"name": ["Reliance", "TCS"]}).to_csv(file_path, index=False)

    loader = NSEUniverseLoader()

    with pytest.raises(NSEUniverseError):
        loader.get_custom_universe(file_path)


def test_get_custom_universe_empty_file_raises(tmp_path: Path):
    file_path = tmp_path / "empty.csv"
    pd.DataFrame(columns=["symbol"]).to_csv(file_path, index=False)

    loader = NSEUniverseLoader()

    with pytest.raises(NSEUniverseError):
        loader.get_custom_universe(file_path)


def test_get_universe_builtin_names():
    loader = NSEUniverseLoader()
    assert "RELIANCE.NS" in loader.get_universe("nifty50")
    assert "HDFCBANK.NS" in loader.get_universe("banknifty")


def test_get_universe_custom_requires_file():
    loader = NSEUniverseLoader()

    with pytest.raises(NSEUniverseError):
        loader.get_universe("custom")


def test_unknown_universe_raises():
    loader = NSEUniverseLoader()

    with pytest.raises(NSEUniverseError):
        loader.get_universe("unknown_universe")


def test_empty_symbol_raises():
    loader = NSEUniverseLoader()

    with pytest.raises(NSEUniverseError):
        loader.normalize_symbol("   ")