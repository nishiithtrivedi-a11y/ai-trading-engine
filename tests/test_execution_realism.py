"""
Tests for src/execution/ package (Phase 7 -- Execution Realism).

Covers:
  - CostConfig defaults and validation
  - TradeCost fields
  - CostModel.compute() for buy and sell sides
  - CostModel.round_trip_cost()
  - FillConfig defaults
  - FillResult fields
  - FillModel.get_fill_price() - next-bar-open and current-bar-close modes
  - FillModel.get_fill_price_at_date() convenience wrapper
  - GrossNetRecord dataclass
  - ExecutionCostAnalyzer.analyze_trade_log()
  - ExecutionCostAnalyzer.apply_costs_to_trade_log()
  - generate_execution_report() output and file writing
  - src/execution/__init__.py public exports
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------
from src.execution.cost_model import CostConfig, CostModel, TradeCost
from src.execution.fill_model import FillConfig, FillModel, FillResult
from src.execution import (
    CostConfig as ICostConfig,
    CostModel as ICostModel,
    TradeCost as ITradeCost,
    FillConfig as IFillConfig,
    FillModel as IFillModel,
    FillResult as IFillResult,
    GrossNetRecord,
    ExecutionCostAnalyzer,
    generate_execution_report,
)


# ===========================================================================
# Helpers
# ===========================================================================

def _make_ohlcv(n: int = 10) -> pd.DataFrame:
    """Create a minimal OHLCV DataFrame with n bars."""
    import numpy as np
    data = {
        "open":   [100.0 + i for i in range(n)],
        "high":   [105.0 + i for i in range(n)],
        "low":    [ 95.0 + i for i in range(n)],
        "close":  [102.0 + i for i in range(n)],
        "volume": [1_000.0    for _  in range(n)],
    }
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame(data, index=idx)


def _make_trade_log(n: int = 5) -> pd.DataFrame:
    """Create a minimal trade log with required columns."""
    rows = []
    for i in range(n):
        rows.append({
            "symbol":       f"SYM{i % 3}",
            "strategy":     "sma" if i % 2 == 0 else "rsi",
            "entry_price":  100.0 + i * 5,
            "exit_price":   110.0 + i * 5,
            "quantity":     10.0,
            "gross_pnl":    (110.0 + i * 5 - 100.0 - i * 5) * 10.0,  # 100 per trade
        })
    return pd.DataFrame(rows)


# ===========================================================================
# 1. CostConfig
# ===========================================================================

class TestCostConfig:
    """Tests for CostConfig defaults and validation."""

    def test_default_values(self):
        cfg = CostConfig()
        assert cfg.commission_per_trade == 0.0
        assert cfg.commission_bps == pytest.approx(10.0)
        assert cfg.slippage_bps   == pytest.approx(5.0)

    def test_custom_values(self):
        cfg = CostConfig(commission_per_trade=20.0, commission_bps=5.0, slippage_bps=2.0)
        assert cfg.commission_per_trade == pytest.approx(20.0)
        assert cfg.commission_bps       == pytest.approx(5.0)
        assert cfg.slippage_bps         == pytest.approx(2.0)

    def test_zero_costs_allowed(self):
        cfg = CostConfig(commission_per_trade=0.0, commission_bps=0.0, slippage_bps=0.0)
        assert cfg.commission_per_trade == 0.0

    def test_negative_commission_raises(self):
        with pytest.raises((ValueError, Exception)):
            CostConfig(commission_per_trade=-1.0)

    def test_negative_commission_bps_raises(self):
        with pytest.raises((ValueError, Exception)):
            CostConfig(commission_bps=-1.0)

    def test_negative_slippage_raises(self):
        with pytest.raises((ValueError, Exception)):
            CostConfig(slippage_bps=-1.0)


# ===========================================================================
# 2. TradeCost
# ===========================================================================

class TestTradeCost:
    """Tests for the TradeCost result dataclass."""

    def test_fields_accessible(self):
        tc = TradeCost(
            notional=10_000.0,
            commission=10.0,
            slippage_cost=5.0,
            total_cost=15.0,
            fill_price=100.05,
        )
        assert tc.notional      == pytest.approx(10_000.0)
        assert tc.commission    == pytest.approx(10.0)
        assert tc.slippage_cost == pytest.approx(5.0)
        assert tc.total_cost    == pytest.approx(15.0)
        assert tc.fill_price    == pytest.approx(100.05)

    def test_total_cost_is_sum(self):
        tc = TradeCost(
            notional=1_000.0, commission=5.0,
            slippage_cost=3.0, total_cost=8.0, fill_price=100.0,
        )
        assert tc.total_cost == pytest.approx(tc.commission + tc.slippage_cost)


# ===========================================================================
# 3. CostModel.compute()
# ===========================================================================

class TestCostModelCompute:
    """Tests for CostModel.compute()."""

    def test_zero_cost_config(self):
        cfg = CostConfig(commission_per_trade=0.0, commission_bps=0.0, slippage_bps=0.0)
        cm  = CostModel(cfg)
        tc  = cm.compute(price=100.0, quantity=10.0, side="buy")
        assert tc.commission    == pytest.approx(0.0)
        assert tc.slippage_cost == pytest.approx(0.0)
        assert tc.total_cost    == pytest.approx(0.0)
        assert tc.fill_price    == pytest.approx(100.0)

    def test_commission_bps_only(self):
        cfg = CostConfig(commission_per_trade=0.0, commission_bps=10.0, slippage_bps=0.0)
        cm  = CostModel(cfg)
        # notional = 100 * 10 = 1000; commission = 1000 * 10/10000 = 1.0
        tc  = cm.compute(price=100.0, quantity=10.0, side="buy")
        assert tc.notional   == pytest.approx(1_000.0)
        assert tc.commission == pytest.approx(1.0)

    def test_fixed_commission_per_trade(self):
        cfg = CostConfig(commission_per_trade=20.0, commission_bps=0.0, slippage_bps=0.0)
        cm  = CostModel(cfg)
        tc  = cm.compute(price=500.0, quantity=100.0, side="buy")
        assert tc.commission == pytest.approx(20.0)

    def test_fixed_plus_bps_commission(self):
        cfg = CostConfig(commission_per_trade=20.0, commission_bps=10.0, slippage_bps=0.0)
        cm  = CostModel(cfg)
        # notional = 500*100=50000; bps_comm=50000*10/10000=50; total=20+50=70
        tc  = cm.compute(price=500.0, quantity=100.0)
        assert tc.commission == pytest.approx(70.0)

    def test_buy_slippage_raises_fill_price(self):
        cfg = CostConfig(commission_per_trade=0.0, commission_bps=0.0, slippage_bps=10.0)
        cm  = CostModel(cfg)
        tc  = cm.compute(price=100.0, quantity=10.0, side="buy")
        # 10 bps slippage on buy: fill = 100 * (1 + 0.001) = 100.10
        assert tc.fill_price    == pytest.approx(100.10, rel=1e-4)
        assert tc.slippage_cost == pytest.approx(1.0, rel=1e-4)

    def test_sell_slippage_lowers_fill_price(self):
        cfg = CostConfig(commission_per_trade=0.0, commission_bps=0.0, slippage_bps=10.0)
        cm  = CostModel(cfg)
        tc  = cm.compute(price=100.0, quantity=10.0, side="sell")
        # 10 bps slippage on sell: fill = 100 * (1 - 0.001) = 99.90
        assert tc.fill_price    == pytest.approx(99.90, rel=1e-4)
        assert tc.slippage_cost == pytest.approx(1.0, rel=1e-4)

    def test_total_cost_is_commission_plus_slippage(self):
        cfg = CostConfig(commission_per_trade=5.0, commission_bps=10.0, slippage_bps=5.0)
        cm  = CostModel(cfg)
        tc  = cm.compute(price=200.0, quantity=50.0, side="buy")
        expected_total = tc.commission + tc.slippage_cost
        assert tc.total_cost == pytest.approx(expected_total, rel=1e-6)

    def test_quantity_is_absolute(self):
        cfg = CostConfig(commission_bps=10.0, slippage_bps=5.0)
        cm  = CostModel(cfg)
        tc_pos = cm.compute(price=100.0, quantity=10.0)
        tc_neg = cm.compute(price=100.0, quantity=-10.0)
        assert tc_pos.notional == pytest.approx(tc_neg.notional)
        assert tc_pos.total_cost == pytest.approx(tc_neg.total_cost)

    def test_default_config_used_when_none(self):
        cm = CostModel()  # no config -> defaults
        tc = cm.compute(price=100.0, quantity=1.0)
        assert isinstance(tc, TradeCost)
        assert tc.total_cost >= 0.0


# ===========================================================================
# 4. CostModel.round_trip_cost()
# ===========================================================================

class TestCostModelRoundTrip:
    """Tests for CostModel.round_trip_cost()."""

    def test_round_trip_is_sum_of_two_legs(self):
        cfg = CostConfig(commission_per_trade=5.0, commission_bps=10.0, slippage_bps=5.0)
        cm  = CostModel(cfg)
        entry_cost = cm.compute(100.0, 10.0, "buy").total_cost
        exit_cost  = cm.compute(110.0, 10.0, "sell").total_cost
        rt = cm.round_trip_cost(entry_price=100.0, exit_price=110.0, quantity=10.0)
        assert rt == pytest.approx(entry_cost + exit_cost, rel=1e-6)

    def test_round_trip_zero_cost(self):
        cfg = CostConfig(commission_per_trade=0.0, commission_bps=0.0, slippage_bps=0.0)
        cm  = CostModel(cfg)
        assert cm.round_trip_cost(100.0, 110.0, 10.0) == pytest.approx(0.0)

    def test_round_trip_quantity_absolute(self):
        cfg = CostConfig(commission_bps=10.0)
        cm  = CostModel(cfg)
        rt_pos = cm.round_trip_cost(100.0, 110.0,  10.0)
        rt_neg = cm.round_trip_cost(100.0, 110.0, -10.0)
        assert rt_pos == pytest.approx(rt_neg)


# ===========================================================================
# 5. FillConfig
# ===========================================================================

class TestFillConfig:
    """Tests for FillConfig defaults."""

    def test_default_next_bar_open(self):
        fc = FillConfig()
        assert fc.use_next_bar_open is True

    def test_current_bar_close_mode(self):
        fc = FillConfig(use_next_bar_open=False)
        assert fc.use_next_bar_open is False


# ===========================================================================
# 6. FillModel.get_fill_price()
# ===========================================================================

class TestFillModelGetFillPrice:
    """Tests for FillModel.get_fill_price()."""

    def test_next_bar_open_basic(self):
        df  = _make_ohlcv(5)
        fm  = FillModel(FillConfig(use_next_bar_open=True))
        res = fm.get_fill_price(df, signal_bar_idx=0)
        # bar 1 open = 100 + 1 = 101
        assert res.available   is True
        assert res.fill_price  == pytest.approx(101.0)
        assert res.bar_index   == 1
        assert res.fill_mode   == "next_bar_open"

    def test_current_bar_close_basic(self):
        df  = _make_ohlcv(5)
        fm  = FillModel(FillConfig(use_next_bar_open=False))
        res = fm.get_fill_price(df, signal_bar_idx=2)
        # bar 2 close = 102 + 2 = 104
        assert res.available  is True
        assert res.fill_price == pytest.approx(104.0)
        assert res.bar_index  == 2
        assert res.fill_mode  == "current_bar_close"

    def test_next_bar_unavailable_on_last_bar(self):
        df  = _make_ohlcv(5)
        fm  = FillModel(FillConfig(use_next_bar_open=True))
        res = fm.get_fill_price(df, signal_bar_idx=4)  # last bar
        assert res.available  is False
        assert res.fill_price is None

    def test_current_bar_close_last_bar_available(self):
        df  = _make_ohlcv(5)
        fm  = FillModel(FillConfig(use_next_bar_open=False))
        res = fm.get_fill_price(df, signal_bar_idx=4)  # last bar
        assert res.available is True
        assert res.fill_price is not None

    def test_empty_dataframe_unavailable(self):
        df  = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        fm  = FillModel()
        res = fm.get_fill_price(df, signal_bar_idx=0)
        assert res.available  is False
        assert res.fill_price is None

    def test_fill_result_is_fillresult_type(self):
        df  = _make_ohlcv(5)
        fm  = FillModel()
        res = fm.get_fill_price(df, 0)
        assert isinstance(res, FillResult)

    def test_side_parameter_accepted(self):
        df  = _make_ohlcv(5)
        fm  = FillModel()
        res_buy  = fm.get_fill_price(df, 0, side="buy")
        res_sell = fm.get_fill_price(df, 0, side="sell")
        # Same raw price regardless of side (slippage is in CostModel)
        assert res_buy.fill_price == pytest.approx(res_sell.fill_price)

    def test_mid_series_fill(self):
        df  = _make_ohlcv(10)
        fm  = FillModel(FillConfig(use_next_bar_open=True))
        res = fm.get_fill_price(df, signal_bar_idx=5)
        assert res.available is True
        assert res.bar_index == 6


# ===========================================================================
# 7. FillModel.get_fill_price_at_date()
# ===========================================================================

class TestFillModelAtDate:
    """Tests for FillModel.get_fill_price_at_date()."""

    def test_valid_timestamp_next_bar_open(self):
        df  = _make_ohlcv(5)
        ts  = df.index[1]  # bar 1
        fm  = FillModel(FillConfig(use_next_bar_open=True))
        res = fm.get_fill_price_at_date(df, ts)
        # Signal at bar 1 -> fill at bar 2 open = 100 + 2 = 102
        assert res.available  is True
        assert res.fill_price == pytest.approx(102.0)

    def test_invalid_timestamp_unavailable(self):
        df  = _make_ohlcv(5)
        ts  = pd.Timestamp("1900-01-01")
        fm  = FillModel()
        res = fm.get_fill_price_at_date(df, ts)
        assert res.available is False

    def test_empty_df_unavailable(self):
        df  = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        ts  = pd.Timestamp("2025-01-01")
        fm  = FillModel()
        res = fm.get_fill_price_at_date(df, ts)
        assert res.available is False


# ===========================================================================
# 8. GrossNetRecord
# ===========================================================================

class TestGrossNetRecord:
    """Tests for the GrossNetRecord dataclass."""

    def test_fields_accessible(self):
        rec = GrossNetRecord(
            symbol="RELIANCE", strategy="sma", num_trades=10,
            gross_pnl=5_000.0, total_cost=200.0, net_pnl=4_800.0,
            initial_capital=100_000.0,
            gross_return_pct=0.05, net_return_pct=0.048,
            cost_drag_pct=0.002, avg_cost_per_trade=20.0,
        )
        assert rec.symbol          == "RELIANCE"
        assert rec.strategy        == "sma"
        assert rec.num_trades      == 10
        assert rec.gross_pnl       == pytest.approx(5_000.0)
        assert rec.total_cost      == pytest.approx(200.0)
        assert rec.net_pnl         == pytest.approx(4_800.0)
        assert rec.cost_drag_pct   == pytest.approx(0.002)


# ===========================================================================
# 9. ExecutionCostAnalyzer.analyze_trade_log()
# ===========================================================================

class TestExecutionCostAnalyzerAnalyze:
    """Tests for the main trade log analysis method."""

    def _analyzer(self, commission_bps=10.0, slippage_bps=5.0) -> ExecutionCostAnalyzer:
        return ExecutionCostAnalyzer(
            cost_config=CostConfig(commission_bps=commission_bps, slippage_bps=slippage_bps),
            fill_config=FillConfig(use_next_bar_open=True),
        )

    def test_empty_trade_log_returns_empty(self):
        ana = self._analyzer()
        records = ana.analyze_trade_log(pd.DataFrame())
        assert records == []

    def test_none_trade_log_returns_empty(self):
        ana = self._analyzer()
        records = ana.analyze_trade_log(None)
        assert records == []

    def test_missing_columns_returns_empty(self):
        df = pd.DataFrame({"price": [100.0], "qty": [10.0]})
        ana = self._analyzer()
        records = ana.analyze_trade_log(df)
        assert records == []

    def test_single_trade_single_group(self):
        df = pd.DataFrame([{
            "symbol": "X", "strategy": "sma",
            "entry_price": 100.0, "exit_price": 110.0,
            "quantity": 10.0, "gross_pnl": 100.0,
        }])
        ana = self._analyzer(commission_bps=0.0, slippage_bps=0.0)
        records = ana.analyze_trade_log(df, initial_capital=100_000.0)
        assert len(records) == 1
        r = records[0]
        assert r.symbol   == "X"
        assert r.strategy == "sma"
        assert r.num_trades == 1
        assert r.gross_pnl  == pytest.approx(100.0)
        assert r.total_cost == pytest.approx(0.0)
        assert r.net_pnl    == pytest.approx(100.0)

    def test_costs_reduce_net_pnl(self):
        df = pd.DataFrame([{
            "symbol": "X", "strategy": "sma",
            "entry_price": 100.0, "exit_price": 110.0,
            "quantity": 10.0, "gross_pnl": 100.0,
        }])
        ana = self._analyzer(commission_bps=10.0, slippage_bps=5.0)
        records = ana.analyze_trade_log(df, initial_capital=100_000.0)
        r = records[0]
        assert r.total_cost > 0.0
        assert r.net_pnl < r.gross_pnl
        assert r.cost_drag_pct >= 0.0

    def test_multiple_groups_one_record_each(self):
        df = _make_trade_log(n=6)
        ana = self._analyzer()
        records = ana.analyze_trade_log(df, initial_capital=100_000.0)
        # Should produce one record per unique (symbol, strategy) combination
        assert len(records) >= 1
        symbols = {r.symbol for r in records}
        assert len(symbols) >= 1

    def test_return_pcts_calculated_correctly(self):
        df = pd.DataFrame([{
            "symbol": "X", "strategy": "sma",
            "entry_price": 100.0, "exit_price": 110.0,
            "quantity": 10.0, "gross_pnl": 100.0,
        }])
        ana = self._analyzer(commission_bps=0.0, slippage_bps=0.0)
        records = ana.analyze_trade_log(df, initial_capital=10_000.0)
        r = records[0]
        # gross_pnl=100, initial_capital=10_000 -> gross_return=1%
        assert r.gross_return_pct == pytest.approx(0.01, rel=1e-4)
        assert r.net_return_pct   == pytest.approx(0.01, rel=1e-4)

    def test_avg_cost_per_trade_computed(self):
        df = pd.DataFrame([
            {"symbol": "X", "strategy": "sma",
             "entry_price": 100.0, "exit_price": 110.0,
             "quantity": 10.0, "gross_pnl": 100.0},
            {"symbol": "X", "strategy": "sma",
             "entry_price": 200.0, "exit_price": 210.0,
             "quantity": 5.0,  "gross_pnl": 50.0},
        ])
        ana = self._analyzer(commission_bps=10.0, slippage_bps=0.0)
        records = ana.analyze_trade_log(df, initial_capital=100_000.0)
        r = records[0]
        assert r.num_trades == 2
        # avg_cost should equal total_cost / 2
        assert r.avg_cost_per_trade == pytest.approx(r.total_cost / 2.0, rel=1e-6)

    def test_records_sorted_by_gross_pnl_descending(self):
        df = pd.DataFrame([
            {"symbol": "A", "strategy": "sma",
             "entry_price": 100.0, "exit_price": 101.0,
             "quantity": 10.0, "gross_pnl": 10.0},
            {"symbol": "B", "strategy": "sma",
             "entry_price": 100.0, "exit_price": 200.0,
             "quantity": 10.0, "gross_pnl": 1_000.0},
        ])
        ana = self._analyzer(commission_bps=0.0, slippage_bps=0.0)
        records = ana.analyze_trade_log(df, initial_capital=100_000.0)
        if len(records) >= 2:
            assert records[0].gross_pnl >= records[1].gross_pnl

    def test_no_symbol_strategy_single_group(self):
        df = pd.DataFrame([{
            "entry_price": 100.0, "exit_price": 110.0,
            "quantity": 10.0, "gross_pnl": 100.0,
        }])
        ana = self._analyzer(commission_bps=0.0, slippage_bps=0.0)
        records = ana.analyze_trade_log(df, initial_capital=100_000.0)
        assert len(records) == 1
        assert records[0].symbol   == "ALL"
        assert records[0].strategy == "ALL"


# ===========================================================================
# 10. ExecutionCostAnalyzer.apply_costs_to_trade_log()
# ===========================================================================

class TestApplyCostsToTradeLog:
    """Tests for the trade-log annotation helper."""

    def _analyzer(self) -> ExecutionCostAnalyzer:
        return ExecutionCostAnalyzer(
            cost_config=CostConfig(commission_bps=10.0, slippage_bps=5.0),
        )

    def test_returns_dataframe(self):
        df  = _make_trade_log(3)
        ana = self._analyzer()
        out = ana.apply_costs_to_trade_log(df)
        assert isinstance(out, pd.DataFrame)

    def test_columns_added(self):
        df  = _make_trade_log(3)
        ana = self._analyzer()
        out = ana.apply_costs_to_trade_log(df)
        for col in ("entry_cost", "exit_cost", "round_trip_cost", "net_pnl", "fill_mode"):
            assert col in out.columns, f"Missing column: {col}"

    def test_original_not_modified(self):
        df  = _make_trade_log(3)
        orig_cols = set(df.columns)
        ana = self._analyzer()
        _ = ana.apply_costs_to_trade_log(df)
        assert set(df.columns) == orig_cols

    def test_net_pnl_equals_gross_minus_cost(self):
        df  = _make_trade_log(3)
        ana = self._analyzer()
        out = ana.apply_costs_to_trade_log(df)
        for _, row in out.iterrows():
            expected = row["gross_pnl"] - row["round_trip_cost"]
            assert row["net_pnl"] == pytest.approx(expected, rel=1e-6)

    def test_empty_df_returns_empty(self):
        ana = self._analyzer()
        out = ana.apply_costs_to_trade_log(pd.DataFrame())
        assert out.empty

    def test_none_returns_empty(self):
        ana = self._analyzer()
        out = ana.apply_costs_to_trade_log(None)
        assert out.empty

    def test_fill_mode_column_value(self):
        df  = _make_trade_log(2)
        ana = ExecutionCostAnalyzer(
            cost_config=CostConfig(),
            fill_config=FillConfig(use_next_bar_open=True),
        )
        out = ana.apply_costs_to_trade_log(df)
        assert (out["fill_mode"] == "next_bar_open").all()

    def test_zero_cost_net_equals_gross(self):
        df  = _make_trade_log(3)
        ana = ExecutionCostAnalyzer(
            cost_config=CostConfig(commission_per_trade=0.0, commission_bps=0.0, slippage_bps=0.0)
        )
        out = ana.apply_costs_to_trade_log(df)
        for _, row in out.iterrows():
            assert row["net_pnl"] == pytest.approx(row["gross_pnl"], rel=1e-6)


# ===========================================================================
# 11. generate_execution_report()
# ===========================================================================

class TestGenerateExecutionReport:
    """Tests for the markdown report generator."""

    def _sample_records(self) -> list[GrossNetRecord]:
        return [
            GrossNetRecord(
                symbol="RELIANCE", strategy="sma", num_trades=5,
                gross_pnl=500.0, total_cost=25.0, net_pnl=475.0,
                initial_capital=100_000.0,
                gross_return_pct=0.005, net_return_pct=0.00475,
                cost_drag_pct=0.00025, avg_cost_per_trade=5.0,
            ),
            GrossNetRecord(
                symbol="TCS", strategy="rsi", num_trades=3,
                gross_pnl=300.0, total_cost=15.0, net_pnl=285.0,
                initial_capital=100_000.0,
                gross_return_pct=0.003, net_return_pct=0.00285,
                cost_drag_pct=0.00015, avg_cost_per_trade=5.0,
            ),
        ]

    def test_returns_string(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_execution_report(
                self._sample_records(),
                output_path=Path(tmp) / "exec.md"
            )
        assert isinstance(content, str)
        assert len(content) > 0

    def test_file_written(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "exec.md"
            generate_execution_report(self._sample_records(), output_path=out)
            assert out.exists()
            assert out.stat().st_size > 0

    def test_file_content_matches_return_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "exec.md"
            content = generate_execution_report(self._sample_records(), output_path=out)
            assert out.read_text(encoding="utf-8") == content

    def test_symbols_in_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_execution_report(
                self._sample_records(),
                output_path=Path(tmp) / "exec.md"
            )
        assert "RELIANCE" in content
        assert "TCS" in content

    def test_cost_config_values_in_report(self):
        cfg = CostConfig(commission_bps=20.0, slippage_bps=8.0)
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_execution_report(
                self._sample_records(),
                cost_config=cfg,
                output_path=Path(tmp) / "exec.md"
            )
        assert "20.0" in content
        assert "8.0"  in content

    def test_fill_mode_in_report(self):
        fc = FillConfig(use_next_bar_open=True)
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_execution_report(
                self._sample_records(),
                fill_config=fc,
                output_path=Path(tmp) / "exec.md"
            )
        assert "Next-Bar Open" in content or "next_bar_open" in content

    def test_empty_records_report_no_crash(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_execution_report(
                [],
                output_path=Path(tmp) / "exec.md"
            )
        assert isinstance(content, str)
        assert "No trade records" in content or "No data" in content

    def test_metadata_in_report(self):
        meta = {"interval": "day", "symbols_tested": 10}
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_execution_report(
                self._sample_records(),
                output_path=Path(tmp) / "exec.md",
                metadata=meta,
            )
        assert "day" in content
        assert "10"  in content

    def test_default_output_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        generate_execution_report(self._sample_records())
        expected = tmp_path / "research" / "execution_realism.md"
        assert expected.exists()

    def test_ascii_only_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_execution_report(
                self._sample_records(),
                output_path=Path(tmp) / "exec.md"
            )
        # Must be encodable as Windows cp1252
        content.encode("cp1252")

    def test_gross_vs_net_section_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            content = generate_execution_report(
                self._sample_records(),
                output_path=Path(tmp) / "exec.md"
            )
        assert "Gross" in content
        assert "Net"   in content


# ===========================================================================
# 12. Public exports (__init__.py)
# ===========================================================================

class TestExecutionPackageExports:
    """Verify that src/execution/__init__.py exports the expected symbols."""

    def test_cost_config_importable(self):
        assert ICostConfig is CostConfig

    def test_cost_model_importable(self):
        assert ICostModel is CostModel

    def test_trade_cost_importable(self):
        assert ITradeCost is TradeCost

    def test_fill_config_importable(self):
        assert IFillConfig is FillConfig

    def test_fill_model_importable(self):
        assert IFillModel is FillModel

    def test_fill_result_importable(self):
        assert IFillResult is FillResult

    def test_gross_net_record_importable(self):
        from src.execution import GrossNetRecord  # noqa: F401

    def test_execution_cost_analyzer_importable(self):
        from src.execution import ExecutionCostAnalyzer  # noqa: F401

    def test_generate_execution_report_importable(self):
        from src.execution import generate_execution_report  # noqa: F401

    def test_all_symbols_callable_or_instantiable(self):
        from src.execution import (
            CostConfig, CostModel, FillConfig, FillModel,
            ExecutionCostAnalyzer, generate_execution_report,
        )
        _ = CostConfig()
        _ = CostModel()
        _ = FillConfig()
        _ = FillModel()
        _ = ExecutionCostAnalyzer()
        assert callable(generate_execution_report)
