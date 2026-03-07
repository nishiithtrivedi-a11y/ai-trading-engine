"""Tests for the Dashboard API layer (Step 8)."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import pytest

from src.dashboard.dashboard_api import (
    DashboardAPI,
    RealtimeDashboard,
    save_dashboard_payload,
    _safe_float,
    _safe_timestamp,
    _dataframe_to_records,
)


# ---------------------------------------------------------------------------
# Fixtures — minimal result shapes
# ---------------------------------------------------------------------------

def _make_single_asset_results() -> dict[str, Any]:
    """Minimal single-asset payload matching BacktestEngine.get_results()."""
    equity_curve = pd.DataFrame(
        {
            "equity": [100_000.0, 100_500.0, 101_200.0],
            "drawdown_pct": [0.0, 0.0, 0.0],
        },
        index=pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"]),
    )
    equity_curve.index.name = "timestamp"

    trade_log = pd.DataFrame(
        {
            "entry_timestamp": pd.to_datetime(["2025-01-01"]),
            "exit_timestamp": pd.to_datetime(["2025-01-02"]),
            "side": ["long"],
            "entry_price": [100.0],
            "exit_price": [105.0],
            "quantity": [10.0],
            "gross_pnl": [50.0],
            "net_pnl": [48.0],
            "fees": [2.0],
            "return_pct": [0.048],
            "bars_held": [1],
            "holding_minutes": [390.0],
            "exit_reason": ["strategy_exit"],
        }
    )

    return {
        "metrics": {
            "initial_capital": 100_000.0,
            "final_value": 101_200.0,
            "total_return_pct": 0.012,
            "sharpe_ratio": 1.5,
            "num_trades": 1,
            "win_rate": 1.0,
        },
        "equity_curve": equity_curve,
        "trade_log": trade_log,
        "buy_hold": {
            "buy_hold_final_value": 101_000.0,
            "buy_hold_return_pct": 0.01,
        },
    }


@dataclass
class _FakeRunResult:
    symbol: str
    metrics: dict[str, Any]
    trade_log: pd.DataFrame
    equity_curve: pd.DataFrame
    buy_hold: dict[str, Any]


def _make_multi_asset_results() -> dict[str, Any]:
    """Minimal multi-asset payload matching MultiAssetBacktester.run()."""
    idx = pd.to_datetime(["2025-01-01", "2025-01-02", "2025-01-03"])

    portfolio_eq = pd.DataFrame(
        {
            "RELIANCE.NS": [50_000.0, 50_500.0, 51_000.0],
            "TCS.NS": [50_000.0, 49_800.0, 50_200.0],
            "portfolio_equity": [100_000.0, 100_300.0, 101_200.0],
            "portfolio_return": [0.0, 0.003, 0.012],
            "portfolio_peak": [100_000.0, 100_300.0, 101_200.0],
            "portfolio_drawdown": [0.0, 0.0, 0.0],
            "portfolio_drawdown_pct": [0.0, 0.0, 0.0],
        },
        index=idx,
    )
    portfolio_eq.index.name = "timestamp"

    trade_log = pd.DataFrame(
        {
            "entry_timestamp": pd.to_datetime(["2025-01-01", "2025-01-01"]),
            "exit_timestamp": pd.to_datetime(["2025-01-02", "2025-01-03"]),
            "side": ["long", "long"],
            "entry_price": [100.0, 200.0],
            "exit_price": [105.0, 202.0],
            "quantity": [10.0, 5.0],
            "gross_pnl": [50.0, 10.0],
            "net_pnl": [48.0, 8.0],
            "fees": [2.0, 2.0],
            "return_pct": [0.048, 0.008],
            "bars_held": [1, 2],
            "holding_minutes": [390.0, 780.0],
            "exit_reason": ["strategy_exit", "strategy_exit"],
            "symbol": ["RELIANCE.NS", "TCS.NS"],
        }
    )

    corr = pd.DataFrame(
        {"RELIANCE.NS": [1.0, 0.5], "TCS.NS": [0.5, 1.0]},
        index=["RELIANCE.NS", "TCS.NS"],
    )

    symbol_results = {
        "RELIANCE.NS": _FakeRunResult(
            symbol="RELIANCE.NS",
            metrics={"final_value": 51_000.0, "num_trades": 1, "sharpe_ratio": 1.2},
            trade_log=trade_log[trade_log["symbol"] == "RELIANCE.NS"],
            equity_curve=pd.DataFrame(),
            buy_hold={},
        ),
        "TCS.NS": _FakeRunResult(
            symbol="TCS.NS",
            metrics={"final_value": 50_200.0, "num_trades": 1, "sharpe_ratio": 0.8},
            trade_log=trade_log[trade_log["symbol"] == "TCS.NS"],
            equity_curve=pd.DataFrame(),
            buy_hold={},
        ),
    }

    return {
        "symbol_results": symbol_results,
        "portfolio_equity_curve": portfolio_eq,
        "portfolio_trade_log": trade_log,
        "portfolio_metrics": {
            "num_symbols": 2,
            "allocation_method": "equal_weight",
            "initial_capital": 100_000.0,
            "final_value": 101_200.0,
            "total_return_pct": 0.012,
            "num_trades": 2,
            "win_rate": 1.0,
            "profit_factor": float("inf"),
        },
        "correlation_matrix": corr,
    }


# ---------------------------------------------------------------------------
# Tests — helper functions
# ---------------------------------------------------------------------------

class TestHelpers:

    def test_safe_timestamp_datetime(self):
        ts = pd.Timestamp("2025-01-01 09:15:00")
        assert "2025-01-01" in _safe_timestamp(ts)

    def test_safe_timestamp_none(self):
        assert _safe_timestamp(None) == ""

    def test_safe_timestamp_string_passthrough(self):
        assert _safe_timestamp("2025-01-01") == "2025-01-01"

    def test_safe_float_normal(self):
        assert _safe_float(3.14) == pytest.approx(3.14)

    def test_safe_float_nan(self):
        assert _safe_float(float("nan")) is None

    def test_safe_float_inf(self):
        assert _safe_float(float("inf")) is None

    def test_safe_float_none(self):
        assert _safe_float(None) is None

    def test_dataframe_to_records_empty(self):
        assert _dataframe_to_records(pd.DataFrame()) == []

    def test_dataframe_to_records_none(self):
        assert _dataframe_to_records(None) == []

    def test_dataframe_to_records_converts_timestamps(self):
        df = pd.DataFrame(
            {"value": [1.0]},
            index=pd.to_datetime(["2025-01-01"]),
        )
        df.index.name = "timestamp"
        records = _dataframe_to_records(df)
        assert len(records) == 1
        assert isinstance(records[0]["timestamp"], str)
        assert "2025-01-01" in records[0]["timestamp"]


# ---------------------------------------------------------------------------
# Tests — DashboardAPI with single-asset results
# ---------------------------------------------------------------------------

class TestDashboardAPISingleAsset:

    def test_detection(self):
        api = DashboardAPI(_make_single_asset_results())
        assert api.is_multi_asset is False

    def test_get_equity_curve(self):
        api = DashboardAPI(_make_single_asset_results())
        curve = api.get_equity_curve()
        assert isinstance(curve, list)
        assert len(curve) == 3
        assert "equity" in curve[0]
        # Timestamp should be a string, not a Timestamp object
        assert isinstance(curve[0]["timestamp"], str)

    def test_get_trade_log(self):
        api = DashboardAPI(_make_single_asset_results())
        trades = api.get_trade_log()
        assert isinstance(trades, list)
        assert len(trades) == 1
        assert trades[0]["side"] == "long"
        assert isinstance(trades[0]["entry_timestamp"], str)

    def test_get_strategy_metrics(self):
        api = DashboardAPI(_make_single_asset_results())
        metrics = api.get_strategy_metrics()
        assert metrics["sharpe_ratio"] == pytest.approx(1.5)
        assert metrics["num_trades"] == 1

    def test_get_portfolio_stats_fallback(self):
        api = DashboardAPI(_make_single_asset_results())
        stats = api.get_portfolio_stats()
        # For single-asset, portfolio_stats wraps the strategy metrics
        assert stats["final_value"] == pytest.approx(101_200.0)

    def test_get_symbol_metrics_empty(self):
        api = DashboardAPI(_make_single_asset_results())
        assert api.get_symbol_metrics() == {}

    def test_get_correlation_matrix_empty(self):
        api = DashboardAPI(_make_single_asset_results())
        assert api.get_correlation_matrix() == []

    def test_get_full_snapshot_is_json_serializable(self):
        api = DashboardAPI(_make_single_asset_results())
        snapshot = api.get_full_snapshot()
        # Must not raise
        json_str = json.dumps(snapshot, default=str)
        assert isinstance(json_str, str)

    def test_empty_results_handled_gracefully(self):
        api = DashboardAPI({})
        assert api.get_equity_curve() == []
        assert api.get_trade_log() == []
        assert api.get_strategy_metrics() == {}
        assert api.get_portfolio_stats() == {}


# ---------------------------------------------------------------------------
# Tests — DashboardAPI with multi-asset results
# ---------------------------------------------------------------------------

class TestDashboardAPIMultiAsset:

    def test_detection(self):
        api = DashboardAPI(_make_multi_asset_results())
        assert api.is_multi_asset is True

    def test_get_equity_curve(self):
        api = DashboardAPI(_make_multi_asset_results())
        curve = api.get_equity_curve()
        assert isinstance(curve, list)
        assert len(curve) == 3
        assert "portfolio_equity" in curve[0]

    def test_get_trade_log(self):
        api = DashboardAPI(_make_multi_asset_results())
        trades = api.get_trade_log()
        assert len(trades) == 2
        # Both trades have the "symbol" column
        symbols = {t["symbol"] for t in trades}
        assert "RELIANCE.NS" in symbols
        assert "TCS.NS" in symbols

    def test_get_portfolio_stats(self):
        api = DashboardAPI(_make_multi_asset_results())
        stats = api.get_portfolio_stats()
        assert stats["num_symbols"] == 2
        assert stats["final_value"] == pytest.approx(101_200.0)

    def test_get_symbol_metrics(self):
        api = DashboardAPI(_make_multi_asset_results())
        sm = api.get_symbol_metrics()
        assert "RELIANCE.NS" in sm
        assert "TCS.NS" in sm
        assert sm["RELIANCE.NS"]["final_value"] == pytest.approx(51_000.0)
        assert sm["TCS.NS"]["sharpe_ratio"] == pytest.approx(0.8)

    def test_get_correlation_matrix(self):
        api = DashboardAPI(_make_multi_asset_results())
        corr = api.get_correlation_matrix()
        assert isinstance(corr, list)
        assert len(corr) == 2

    def test_inf_in_metrics_handled(self):
        """profit_factor=inf should become None, not crash."""
        api = DashboardAPI(_make_multi_asset_results())
        stats = api.get_portfolio_stats()
        assert stats["profit_factor"] is None

    def test_full_snapshot_json_serializable(self):
        api = DashboardAPI(_make_multi_asset_results())
        snapshot = api.get_full_snapshot()
        json_str = json.dumps(snapshot, default=str)
        parsed = json.loads(json_str)
        assert parsed["is_multi_asset"] is True
        assert len(parsed["equity_curve"]) == 3


# ---------------------------------------------------------------------------
# Tests — RealtimeDashboard placeholder
# ---------------------------------------------------------------------------

class TestRealtimeDashboard:

    def test_push_and_get(self):
        rt = RealtimeDashboard()
        rt.push_update({"strategy_id": "sma", "equity": 100_500})
        updates = rt.get_latest_updates()
        assert len(updates) == 1
        assert updates[0]["data"]["equity"] == pytest.approx(100_500)

    def test_subscribe_and_route(self):
        rt = RealtimeDashboard()
        rt.subscribe("sma")
        rt.push_update({"strategy_id": "sma", "equity": 100_500})
        rt.push_update({"strategy_id": "rsi", "equity": 99_800})

        sma_updates = rt.get_latest_updates(strategy_id="sma")
        assert len(sma_updates) == 1
        assert sma_updates[0]["data"]["strategy_id"] == "sma"

    def test_max_updates_bounded(self):
        rt = RealtimeDashboard(max_updates=5)
        for i in range(10):
            rt.push_update({"strategy_id": "test", "tick": i})
        all_updates = rt.get_latest_updates(count=100)
        assert len(all_updates) == 5

    def test_clear(self):
        rt = RealtimeDashboard()
        rt.subscribe("sma")
        rt.push_update({"strategy_id": "sma", "equity": 100})
        rt.clear()
        assert rt.get_latest_updates() == []

    def test_get_latest_returns_newest_first(self):
        rt = RealtimeDashboard()
        rt.push_update({"strategy_id": "a", "seq": 1})
        rt.push_update({"strategy_id": "a", "seq": 2})
        rt.push_update({"strategy_id": "a", "seq": 3})
        latest = rt.get_latest_updates(count=2)
        assert latest[0]["data"]["seq"] == 3
        assert latest[1]["data"]["seq"] == 2

    def test_timestamp_added_automatically(self):
        rt = RealtimeDashboard()
        rt.push_update({"strategy_id": "x"})
        updates = rt.get_latest_updates()
        assert "timestamp" in updates[0]


# ---------------------------------------------------------------------------
# Tests — save_dashboard_payload
# ---------------------------------------------------------------------------

class TestSaveDashboardPayload:

    def test_save_single_asset(self, tmp_path):
        api = DashboardAPI(_make_single_asset_results())
        out = save_dashboard_payload(api, tmp_path / "snapshot.json")
        assert out.exists()

        with open(out, "r") as f:
            data = json.load(f)
        assert data["is_multi_asset"] is False
        assert len(data["equity_curve"]) == 3

    def test_save_multi_asset(self, tmp_path):
        api = DashboardAPI(_make_multi_asset_results())
        out = save_dashboard_payload(api, tmp_path / "sub" / "snapshot.json")
        assert out.exists()

        with open(out, "r") as f:
            data = json.load(f)
        assert data["is_multi_asset"] is True
        assert len(data["symbol_metrics"]) == 2

    def test_save_creates_parent_dirs(self, tmp_path):
        api = DashboardAPI({})
        out = save_dashboard_payload(api, tmp_path / "a" / "b" / "c.json")
        assert out.exists()
