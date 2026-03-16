from __future__ import annotations

from pathlib import Path

import pytest

from src.paper_trading.models import PaperPortfolioState
from src.paper_trading.state_store import PaperStateStore


def _empty_state(capital: float = 100_000.0) -> PaperPortfolioState:
    return PaperPortfolioState(initial_capital=capital, cash=capital)


def test_state_store_save_is_atomic_and_cleans_lock(tmp_path: Path) -> None:
    target = tmp_path / "paper_state.json"
    store = PaperStateStore(state_file=target)

    saved = store.save(_empty_state())
    assert saved == target
    assert target.exists()
    assert not (tmp_path / "paper_state.json.lock").exists()


def test_state_store_load_defaults_when_file_missing(tmp_path: Path) -> None:
    store = PaperStateStore(state_file=tmp_path / "missing.json")
    state = store.load(default_initial_capital=50_000.0)
    assert state.initial_capital == 50_000.0
    assert state.cash == 50_000.0


def test_state_store_lock_timeout_raises(tmp_path: Path) -> None:
    target = tmp_path / "paper_state.json"
    lock_path = tmp_path / "paper_state.json.lock"
    lock_path.write_text("busy", encoding="utf-8")

    store = PaperStateStore(
        state_file=target,
        lock_timeout_seconds=0.01,
        lock_poll_seconds=0.001,
    )

    with pytest.raises(TimeoutError):
        store.save(_empty_state())
