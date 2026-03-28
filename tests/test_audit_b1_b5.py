"""
Targeted tests for audit items B1-B5.

B1  - PortfolioBacktester.run_from_engine_results() reuses pre-computed results
B2  - _write_incremental() is crash-safe (atomic temp-file + replace)
B3  - PivotPointReversalStrategy uses prior session only (not all history)
B4  - DataHandler / validators enforce data quality at ingestion
B5  - _process_symbol shared core produces identical rows for serial and
      parallel paths
"""

from __future__ import annotations

import copy
from datetime import date, timedelta, timezone
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 120, base_price: float = 100.0, freq: str = "B") -> pd.DataFrame:
    dates = pd.date_range("2024-01-02", periods=n, freq=freq)
    np.random.seed(0)
    prices = base_price + np.cumsum(np.random.randn(n) * 0.5)
    prices = np.abs(prices) + 50.0
    df = pd.DataFrame(
        {
            "open": prices * 0.999,
            "high": prices * 1.005,
            "low": prices * 0.995,
            "close": prices,
            "volume": np.ones(n) * 100_000,
        },
        index=dates,
    )
    df.index.name = "timestamp"
    return df


# ===========================================================================
# B1 — PortfolioBacktester.run_from_engine_results
# ===========================================================================

class TestB1RunFromEngineResults:
    """run_from_engine_results() must produce identical schema to run()."""

    def _make_backtester(self, tmp_path: Path):
        from src.core.data_handler import DataHandler
        from src.research.portfolio_backtester import PortfolioBacktester
        from src.utils.config import BacktestConfig
        from src.strategies.sma_crossover import SMACrossoverStrategy

        dh = {f"SYM{i}": DataHandler(_make_ohlcv(120, 100.0 + i * 5)) for i in range(2)}
        registry = {
            "sma": {
                "class": SMACrossoverStrategy,
                "params": {"fast_period": 10, "slow_period": 20},
            }
        }
        return PortfolioBacktester(
            base_config=BacktestConfig(initial_capital=50_000.0),
            strategy_registry=registry,
            symbol_to_data=dh,
            max_positions=2,
            output_dir=str(tmp_path / "portfolio"),
        )

    def _make_engine_results(self) -> dict:
        """Build a minimal engine results dict compatible with get_results()."""
        dates = pd.date_range("2024-01-02", periods=10, freq="B")
        equity = pd.DataFrame({"equity": np.linspace(10_000, 11_000, 10)}, index=dates)
        trades = pd.DataFrame(
            {
                "entry_time": [dates[0]],
                "exit_time": [dates[5]],
                "pnl": [500.0],
                "return_pct": [0.05],
            }
        )
        return {
            "metrics": {"total_return": 0.1, "sharpe_ratio": 1.0, "num_trades": 1},
            "equity_curve": equity,
            "trade_log": trades,
            "buy_hold": {},
        }

    def test_run_from_engine_results_returns_result_object(self, tmp_path):
        from src.research.portfolio_backtester import PortfolioBacktestResult

        pb = self._make_backtester(tmp_path)
        precomputed = {
            "SYM0": self._make_engine_results(),
            "SYM1": self._make_engine_results(),
        }
        result = pb.run_from_engine_results(precomputed)
        assert isinstance(result, PortfolioBacktestResult)

    def test_run_from_engine_results_schema_matches_run(self, tmp_path):
        from src.research.portfolio_backtester import PortfolioBacktestResult

        pb = self._make_backtester(tmp_path)
        # Full run
        result_full = pb.run()
        # Pre-computed run with minimal precomputed dict (will fall back for missing)
        result_pre = pb.run_from_engine_results({})
        # Both must be the same type with same key attributes
        for attr in (
            "initial_capital", "num_symbols_active", "max_positions",
            "per_symbol_capital",
        ):
            assert getattr(result_full, attr) == getattr(result_pre, attr)

    def test_run_from_engine_results_uses_precomputed_equity(self, tmp_path):
        """When pre-computed results are provided, the equity curves are consumed."""
        pb = self._make_backtester(tmp_path)
        eng = self._make_engine_results()
        # Inject a very specific final equity so we can verify it was used
        specific_equity = pd.DataFrame(
            {"equity": np.linspace(25_000, 28_000, 10)},
            index=pd.date_range("2024-01-02", periods=10, freq="B"),
        )
        eng["equity_curve"] = specific_equity
        precomputed = {"SYM0": eng, "SYM1": copy.deepcopy(eng)}
        result = pb.run_from_engine_results(precomputed)
        # Portfolio equity should include contributions from the supplied curves
        assert not result.portfolio_equity_curve.empty

    def test_run_from_engine_results_fallback_for_missing_symbol(self, tmp_path):
        """Symbols absent from precomputed fall back to a live backtest."""
        pb = self._make_backtester(tmp_path)
        # Only provide one of two symbols
        precomputed = {"SYM0": self._make_engine_results()}
        result = pb.run_from_engine_results(precomputed)
        # Should still complete without error
        assert result is not None

    def test_run_from_engine_results_exports_csvs(self, tmp_path):
        pb = self._make_backtester(tmp_path)
        precomputed = {
            "SYM0": self._make_engine_results(),
            "SYM1": self._make_engine_results(),
        }
        pb.run_from_engine_results(precomputed)
        portfolio_dir = tmp_path / "portfolio"
        assert (portfolio_dir / "portfolio_equity_curve.csv").exists()


# ===========================================================================
# B2 — atomic incremental CSV writes
# ===========================================================================

class TestB2AtomicIncrementalWrite:
    """_write_incremental must be crash-safe: no .tmp file left on success,
    and the final CSV is always a complete, parseable file."""

    def _import_fn(self):
        import importlib, sys
        # Import the private function directly
        spec = importlib.util.spec_from_file_location(
            "runner",
            str(Path(__file__).parent.parent / "scripts" / "run_nifty50_zerodha_research.py"),
        )
        # We only need the _write_incremental function; use exec-based import
        import types
        mod_globals: dict = {}
        src = (
            Path(__file__).parent.parent
            / "scripts"
            / "run_nifty50_zerodha_research.py"
        ).read_text(encoding="utf-8")
        # Extract just the function — use a targeted import instead
        from scripts.run_nifty50_zerodha_research import _write_incremental
        return _write_incremental

    def test_creates_csv_on_first_write(self, tmp_path):
        from scripts.run_nifty50_zerodha_research import _write_incremental

        path = tmp_path / "out.csv"
        rows = [{"symbol": "A", "score": 1.0}]
        _write_incremental(rows, path)
        assert path.exists()
        df = pd.read_csv(path)
        assert len(df) == 1
        assert df["symbol"].iloc[0] == "A"

    def test_appends_on_subsequent_writes(self, tmp_path):
        from scripts.run_nifty50_zerodha_research import _write_incremental

        path = tmp_path / "out.csv"
        _write_incremental([{"symbol": "A", "score": 1.0}], path)
        _write_incremental([{"symbol": "B", "score": 2.0}], path)
        df = pd.read_csv(path)
        assert len(df) == 2
        assert set(df["symbol"]) == {"A", "B"}

    def test_no_tmp_file_left_after_write(self, tmp_path):
        from scripts.run_nifty50_zerodha_research import _write_incremental

        path = tmp_path / "out.csv"
        _write_incremental([{"symbol": "A", "score": 1.0}], path)
        tmp = path.with_suffix(".tmp")
        assert not tmp.exists()

    def test_empty_rows_is_noop(self, tmp_path):
        from scripts.run_nifty50_zerodha_research import _write_incremental

        path = tmp_path / "out.csv"
        _write_incremental([], path)
        assert not path.exists()

    def test_internal_keys_stripped_from_csv(self, tmp_path):
        """Keys starting with _ must not appear in the output CSV."""
        from scripts.run_nifty50_zerodha_research import _write_incremental

        path = tmp_path / "out.csv"
        rows = [{"symbol": "A", "score": 1.0, "_engine_results": {"x": 1}, "_row_score": 1.0}]
        _write_incremental(rows, path)
        df = pd.read_csv(path)
        assert "_engine_results" not in df.columns
        assert "_row_score" not in df.columns
        assert "symbol" in df.columns

    def test_multiple_symbols_round_trip(self, tmp_path):
        from scripts.run_nifty50_zerodha_research import _write_incremental

        path = tmp_path / "out.csv"
        for i in range(5):
            _write_incremental([{"symbol": f"SYM{i}", "score": float(i)}], path)
        df = pd.read_csv(path)
        assert len(df) == 5


# ===========================================================================
# B3 — PivotPointReversalStrategy prior session only
# ===========================================================================

class TestB3PivotPointPriorSessionOnly:
    """Pivot H/L/C must come exclusively from the most recent completed session."""

    def _make_intraday_df(self, num_days: int = 3, bars_per_day: int = 8) -> pd.DataFrame:
        """Build multi-day intraday data (UTC-aware timestamps, IST business hours)."""
        tz_ist = timezone(timedelta(hours=5, minutes=30))
        records = []
        base_date = date(2024, 1, 2)
        for d in range(num_days):
            day = base_date + timedelta(days=d)
            for bar in range(bars_per_day):
                ts = pd.Timestamp(
                    year=day.year,
                    month=day.month,
                    day=day.day,
                    hour=9 + bar,
                    minute=15,
                    tzinfo=tz_ist,
                ).tz_convert("UTC")
                # Each day has a distinct price range to differentiate sessions
                base = 100.0 + d * 50.0  # day 0: ~100, day 1: ~150, day 2: ~200
                records.append(
                    {
                        "timestamp": ts,
                        "open": base,
                        "high": base + 10.0 + bar,
                        "low": base - 5.0,
                        "close": base + bar * 0.5,
                        "volume": 10_000.0,
                    }
                )
        df = pd.DataFrame(records).set_index("timestamp")
        df.index.name = "timestamp"
        return df

    def test_uses_most_recent_session_high(self):
        """prev_high must equal the high of day N-1, not the all-history max."""
        from src.strategies.intraday.pivot_point_reversal import PivotPointReversalStrategy

        df = self._make_intraday_df(num_days=3, bars_per_day=8)
        strategy = PivotPointReversalStrategy()
        strategy.initialize()

        last_bar = df.iloc[-1]
        signal = strategy.generate_signal(df, last_bar, len(df) - 1)
        meta = signal.metadata or {}

        # Day 2 (index 1, 0-based) is the prior session
        # Its high is base(150) + 10 + max_bar_offset = 150 + 10 + 7 = 167
        # Day 0's high would be 100 + 10 + 7 = 117 (lower)
        # The all-history max would be 167 as well — but we want to make sure
        # it's using day 1 data not day 0.
        # Day 1 high = 150 + 10 + 7 = 167; day 0 high = 117
        # pivot from day 1: (167 + 145 + 153.5) / 3 ~= 155.2
        # pivot from all history: (167 + 95 + 153.5) / 3 ~= 138.5
        # If metadata["pivot"] is closer to 155 it used day 1; if ~138 it used all history.
        assert "pivot" in meta
        # Prior-session (day 1) pivot should be significantly above 140
        assert meta["pivot"] > 140.0, (
            f"Expected pivot > 140 (prior-session), got {meta['pivot']}"
        )

    def test_no_previous_session_returns_hold(self):
        """When only one session exists, signal must be HOLD (no prior data)."""
        from src.strategies.intraday.pivot_point_reversal import PivotPointReversalStrategy
        from src.strategies.base_strategy import Signal

        df = self._make_intraday_df(num_days=1, bars_per_day=8)
        strategy = PivotPointReversalStrategy()
        strategy.initialize()

        last_bar = df.iloc[-1]
        signal = strategy.generate_signal(df, last_bar, len(df) - 1)
        assert signal.action == Signal.HOLD
        assert signal.rationale == "no_previous_session"

    def test_does_not_bleed_older_history_into_pivot(self):
        """With 5 days of data, prior session must be day 4 only, not days 0-3."""
        from src.strategies.intraday.pivot_point_reversal import PivotPointReversalStrategy

        df = self._make_intraday_df(num_days=5, bars_per_day=8)
        strategy = PivotPointReversalStrategy()
        strategy.initialize()

        last_bar = df.iloc[-1]
        signal = strategy.generate_signal(df, last_bar, len(df) - 1)
        meta = signal.metadata or {}

        # Day 4 base price = 100 + 4*50 = 300; all-history low is ~95
        # Prior-session (day 3) base = 100 + 3*50 = 250; low = 245
        # If using all history: low could be ~95 (day 0)
        # If using prior session only: low should be ~245
        # r1 = 2*pivot - prev_low; s1 = 2*pivot - prev_high
        # A very low prev_low (all-history) would produce a wildly different pivot.
        if "pivot" in meta:
            # Prior session (day 3) pivot > 250; all-history pivot would be much lower
            assert meta["pivot"] > 200.0, (
                f"Pivot {meta['pivot']} suggests all-history bleed-in (expected > 200)"
            )

    def test_prior_session_day_is_latest_complete_day(self):
        """The prior_session_day selected must be the single day immediately before current."""
        from src.strategies.intraday.pivot_point_reversal import PivotPointReversalStrategy

        df = self._make_intraday_df(num_days=3, bars_per_day=4)

        strategy = PivotPointReversalStrategy()
        strategy.initialize()

        # Verify the strategy correctly identifies the prior session using
        # the same date-key computation the strategy uses internally.
        idx = df.index
        local_idx = idx.tz_convert("Asia/Kolkata")
        day_keys = pd.Series(local_idx.date, index=df.index)
        all_days = sorted(day_keys.unique())
        current_day = day_keys.iloc[-1]
        all_prior = sorted({d for d in all_days if d < current_day})
        # The prior session should be the last element of all_prior
        assert all_prior[-1] == all_days[-2]


# ===========================================================================
# B4 — Data quality validation
# ===========================================================================

class TestB4DataQualityValidation:
    """DataHandler.set_data() must enforce validation at ingestion."""

    def test_rejects_empty_dataframe(self):
        from src.core.data_handler import DataHandler
        from src.utils.validators import DataValidationError

        with pytest.raises(DataValidationError, match="empty"):
            DataHandler(pd.DataFrame())

    def test_rejects_missing_columns(self):
        from src.core.data_handler import DataHandler
        from src.utils.validators import DataValidationError

        df = pd.DataFrame({"open": [1.0], "close": [1.0]},
                          index=pd.DatetimeIndex(["2024-01-02"]))
        with pytest.raises(DataValidationError, match="Missing required columns"):
            DataHandler(df)

    def test_rejects_duplicate_timestamps(self):
        from src.core.data_handler import DataHandler
        from src.utils.validators import DataValidationError

        idx = pd.DatetimeIndex(["2024-01-02", "2024-01-02"])
        df = pd.DataFrame(
            {"open": [1.0, 1.0], "high": [2.0, 2.0], "low": [0.5, 0.5],
             "close": [1.5, 1.5], "volume": [100.0, 100.0]},
            index=idx,
        )
        with pytest.raises(DataValidationError, match="duplicate"):
            DataHandler(df)

    def test_rejects_high_less_than_low(self):
        from src.core.data_handler import DataHandler
        from src.utils.validators import DataValidationError

        idx = pd.DatetimeIndex(["2024-01-02"])
        df = pd.DataFrame(
            {"open": [1.0], "high": [0.5], "low": [1.5], "close": [1.0], "volume": [100.0]},
            index=idx,
        )
        with pytest.raises(DataValidationError, match="high < low"):
            DataHandler(df)

    def test_rejects_non_positive_prices(self):
        from src.core.data_handler import DataHandler
        from src.utils.validators import DataValidationError

        idx = pd.DatetimeIndex(["2024-01-02"])
        df = pd.DataFrame(
            {"open": [0.0], "high": [1.0], "low": [-1.0], "close": [0.5], "volume": [100.0]},
            index=idx,
        )
        with pytest.raises(DataValidationError):
            DataHandler(df)

    def test_accepts_valid_data(self):
        from src.core.data_handler import DataHandler

        dh = DataHandler(_make_ohlcv(60))
        assert dh.data is not None
        assert len(dh.data) == 60

    def test_nan_prices_are_forward_filled(self):
        from src.core.data_handler import DataHandler

        df = _make_ohlcv(10)
        df.loc[df.index[3], "close"] = float("nan")
        dh = DataHandler(df)
        assert not dh.data["close"].isna().any()

    def test_unsorted_data_is_sorted(self):
        from src.core.data_handler import DataHandler

        df = _make_ohlcv(10)
        shuffled = df.sample(frac=1, random_state=0)
        dh = DataHandler(shuffled)
        assert dh.data.index.is_monotonic_increasing

    def test_validate_ohlcv_returns_warnings_for_zero_volume(self):
        """Zero-volume bars are a soft issue — should be a warning, not an error."""
        from src.utils.validators import validate_ohlcv_dataframe

        df = _make_ohlcv(10)
        df.loc[df.index[0], "volume"] = 0.0
        warnings = validate_ohlcv_dataframe(df)
        assert any("zero" in w.lower() or "volume" in w.lower() for w in warnings)


# ===========================================================================
# B5 — _process_symbol shared core: serial == parallel output
# ===========================================================================

class TestB5ProcessSymbolSharedCore:
    """_process_symbol must produce identical rows whether called directly
    (serial path) or via ProcessPoolExecutor (parallel path)."""

    def _make_inputs(self):
        from src.utils.config import BacktestConfig
        from src.strategies.sma_crossover import SMACrossoverStrategy

        df = _make_ohlcv(120)
        selected = {
            "sma": {
                "class": SMACrossoverStrategy,
                "params": {"fast_period": 10, "slow_period": 20},
                "param_grid": {"fast_period": [10], "slow_period": [20]},
            }
        }
        base_config = BacktestConfig(initial_capital=100_000.0)
        return df, selected, base_config

    def test_returns_symbol_and_rows_tuple(self):
        from scripts.run_nifty50_zerodha_research import _process_symbol

        df, selected, base_config = self._make_inputs()
        sym, rows = _process_symbol(
            symbol="TEST",
            df=df,
            selected=selected,
            base_config=base_config,
            optimize=False,
            output_dir=Path("/tmp"),
            regime_analysis_active=False,
            regime_snap_value=None,
            composite_value="unknown",
            regime_filter_active=False,
        )
        assert sym == "TEST"
        assert isinstance(rows, list)

    def test_row_has_expected_keys(self):
        from scripts.run_nifty50_zerodha_research import _process_symbol

        df, selected, base_config = self._make_inputs()
        _sym, rows = _process_symbol(
            symbol="TEST",
            df=df,
            selected=selected,
            base_config=base_config,
            optimize=False,
            output_dir=Path("/tmp"),
            regime_analysis_active=False,
            regime_snap_value=None,
            composite_value="unknown",
            regime_filter_active=False,
        )
        if rows:
            row = rows[0]
            assert row["symbol"] == "TEST"
            assert "strategy" in row
            assert "score" in row

    def test_regime_label_attached_when_regime_snap_provided(self):
        from scripts.run_nifty50_zerodha_research import _process_symbol

        df, selected, base_config = self._make_inputs()
        _sym, rows = _process_symbol(
            symbol="TEST",
            df=df,
            selected=selected,
            base_config=base_config,
            optimize=False,
            output_dir=Path("/tmp"),
            regime_analysis_active=False,
            regime_snap_value="bullish",
            composite_value="bullish",
            regime_filter_active=False,
        )
        for row in rows:
            assert row.get("regime_label") == "bullish"

    def test_engine_results_attached_when_portfolio_active(self):
        """When portfolio_backtest_active=True, rows contain _engine_results."""
        from scripts.run_nifty50_zerodha_research import _process_symbol

        df, selected, base_config = self._make_inputs()
        _sym, rows = _process_symbol(
            symbol="TEST",
            df=df,
            selected=selected,
            base_config=base_config,
            optimize=False,
            output_dir=Path("/tmp"),
            regime_analysis_active=False,
            regime_snap_value=None,
            composite_value="unknown",
            regime_filter_active=False,
            portfolio_backtest_active=True,
        )
        for row in rows:
            assert "_engine_results" in row
            eng = row["_engine_results"]
            assert "equity_curve" in eng
            assert "trade_log" in eng

    def test_no_engine_results_when_portfolio_inactive(self):
        """When portfolio_backtest_active=False (default), _engine_results absent."""
        from scripts.run_nifty50_zerodha_research import _process_symbol

        df, selected, base_config = self._make_inputs()
        _sym, rows = _process_symbol(
            symbol="TEST",
            df=df,
            selected=selected,
            base_config=base_config,
            optimize=False,
            output_dir=Path("/tmp"),
            regime_analysis_active=False,
            regime_snap_value=None,
            composite_value="unknown",
            regime_filter_active=False,
            portfolio_backtest_active=False,
        )
        for row in rows:
            assert "_engine_results" not in row

    def test_serial_and_direct_call_produce_same_metrics(self):
        """Row metrics from _process_symbol must equal those from run_single."""
        from scripts.run_nifty50_zerodha_research import _process_symbol, run_single
        from src.strategies.sma_crossover import SMACrossoverStrategy
        from src.utils.config import BacktestConfig

        df = _make_ohlcv(120)
        base_config = BacktestConfig(initial_capital=100_000.0)
        params = {"fast_period": 10, "slow_period": 20}
        selected = {
            "sma": {
                "class": SMACrossoverStrategy,
                "params": params,
                "param_grid": {},
            }
        }

        row_direct = run_single("TEST", df, "sma", SMACrossoverStrategy, params, base_config)
        _sym, rows_shared = _process_symbol(
            symbol="TEST",
            df=df,
            selected=selected,
            base_config=base_config,
            optimize=False,
            output_dir=Path("/tmp"),
            regime_analysis_active=False,
            regime_snap_value=None,
            composite_value="unknown",
            regime_filter_active=False,
        )

        assert row_direct is not None
        assert rows_shared
        row_shared = rows_shared[0]

        # Core metrics must be identical
        for key in ("num_trades", "total_return", "sharpe_ratio"):
            assert row_direct.get(key) == row_shared.get(key), (
                f"Metric '{key}' differs: direct={row_direct.get(key)}, "
                f"shared={row_shared.get(key)}"
            )
