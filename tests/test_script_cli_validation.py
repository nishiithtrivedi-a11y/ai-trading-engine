from __future__ import annotations

import sys

import pytest

from scripts import run_live_signal_pipeline, run_nifty50_zerodha_research, run_paper_trading


def test_run_nifty_fill_mode_defaults_to_next_bar(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["runner"])
    args = run_nifty50_zerodha_research.parse_args()
    assert args.use_next_bar_fill is True


def test_run_nifty_fill_mode_can_be_set_to_same_bar(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["runner", "--use-same-bar-fill"])
    args = run_nifty50_zerodha_research.parse_args()
    assert args.use_next_bar_fill is False


def test_run_nifty_execution_realism_requires_portfolio_backtest(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["runner", "--execution-realism"])
    with pytest.raises(SystemExit):
        run_nifty50_zerodha_research.parse_args()


def test_run_paper_trading_validates_paper_capital(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["runner", "--paper-capital", "0"])
    with pytest.raises(SystemExit):
        run_paper_trading.parse_args()


def test_run_live_pipeline_validates_poll_seconds(monkeypatch) -> None:
    monkeypatch.setattr(sys, "argv", ["runner", "--poll-seconds", "-5"])
    with pytest.raises(SystemExit):
        run_live_signal_pipeline.parse_args()
