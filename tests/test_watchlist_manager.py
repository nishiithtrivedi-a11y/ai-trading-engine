from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from src.monitoring.config import WatchlistDefinition
from src.monitoring.watchlist_manager import WatchlistManager, WatchlistManagerError


def test_load_watchlist_from_symbols_normalizes_and_dedupes() -> None:
    manager = WatchlistManager()
    definition = WatchlistDefinition(
        name="custom",
        symbols=["reliance", "TCS.NS", "RELIANCE.NS"],
        tags=["swing"],
        default_timeframes=["1d", "1D"],
    )
    watchlist = manager.load_watchlist(definition)

    assert watchlist.name == "custom"
    assert watchlist.symbols == ["RELIANCE.NS", "TCS.NS"]
    assert watchlist.items[0].default_timeframes == ["1D"]


def test_load_watchlist_from_builtin_universe() -> None:
    manager = WatchlistManager()
    definition = WatchlistDefinition(name="banknifty", universe_name="banknifty")
    watchlist = manager.load_watchlist(definition)

    assert len(watchlist.items) > 0
    assert any(item.symbol == "HDFCBANK.NS" for item in watchlist.items)


def test_load_watchlist_from_csv(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.csv"
    pd.DataFrame({"symbol": ["reliance", "tcs", "reliance"]}).to_csv(path, index=False)

    manager = WatchlistManager()
    watchlist = manager.load_from_csv(path, name="csv_list")

    assert watchlist.name == "csv_list"
    assert watchlist.symbols == ["RELIANCE.NS", "TCS.NS"]


def test_load_watchlist_from_json_dict_payload(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    payload = {
        "name": "json_watchlist",
        "symbols": ["infy", "itc", "ITC.NS"],
        "tags": ["intraday"],
        "default_timeframes": ["15m"],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")

    manager = WatchlistManager()
    watchlist = manager.load_from_json(path)

    assert watchlist.name == "json_watchlist"
    assert watchlist.symbols == ["INFY.NS", "ITC.NS"]
    assert watchlist.items[0].tags == ["intraday"]


def test_invalid_watchlist_csv_raises(tmp_path: Path) -> None:
    path = tmp_path / "bad.csv"
    pd.DataFrame({"name": ["RELIANCE"]}).to_csv(path, index=False)
    manager = WatchlistManager()

    with pytest.raises(WatchlistManagerError):
        manager.load_from_csv(path)


def test_unsupported_file_format_raises(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.txt"
    path.write_text("RELIANCE", encoding="utf-8")

    with pytest.raises(ValueError):
        WatchlistDefinition(name="bad", file_path=str(path), file_format="txt")
