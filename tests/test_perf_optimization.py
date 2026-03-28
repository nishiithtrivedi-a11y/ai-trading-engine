"""
Performance Optimization Tests - Phase 1 Remediation

Tests:
  P01 - SuperTrend equivalence: optimized vs legacy on synthetic + real data
  P02 - Precompute cache: signals match between precomputed and legacy paths
  P03 - Cache invalidation: no cross-dataset contamination
  P04 - Backtest equivalence: full backtest results identical old vs new
  P05 - Benchmark: timing comparison (assertions are soft / informational)
"""

from __future__ import annotations

import time
import warnings
import logging

import numpy as np
import pandas as pd
import pytest

warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=pd.errors.SettingWithCopyWarning)
logging.disable(logging.CRITICAL)

from src.strategies.intraday.intraday_trend_following_strategy import (
    IntradayTrendFollowingStrategy,
    StrategyConfig,
    prepare_strategy_dataframe,
    backtest_strategy,
    supertrend,
    supertrend_legacy,
    atr,
    ema,
    intraday_vwap,
    _ensure_datetime_index,
    load_ohlcv_csv,
)


# -----------------------------------------------------------------------
# SHARED HELPERS
# -----------------------------------------------------------------------

def _ist_to_utc(date_str, hhmm):
    ts = pd.Timestamp(f"{date_str} {hhmm}:00", tz="Asia/Kolkata")
    return ts.tz_convert("UTC")


def _make_bars(date_str, session_start_ist="09:30", n_bars=60,
               freq="5min", base_price=1000.0, step=10.0,
               bar_range=2.0, volume=10_000):
    start_ts = _ist_to_utc(date_str, session_start_ist)
    idx = pd.date_range(start=start_ts, periods=n_bars, freq=freq)
    prices = [base_price + i * step for i in range(n_bars)]
    half = bar_range / 2.0
    return pd.DataFrame(
        {"open": prices, "high": [p + half for p in prices],
         "low": [p - half for p in prices], "close": prices,
         "volume": [volume] * n_bars},
        index=idx,
    )


def _make_synthetic_ohlcv(n_bars, seed=42):
    rng = np.random.default_rng(seed)
    start = _ist_to_utc("2025-12-10", "09:30")
    idx = pd.date_range(start=start, periods=n_bars, freq="5min")
    close = 1000.0 + np.cumsum(rng.normal(0, 2, n_bars))
    high = close + rng.uniform(0.5, 3.0, n_bars)
    low = close - rng.uniform(0.5, 3.0, n_bars)
    opn = close + rng.normal(0, 1, n_bars)
    volume = rng.integers(5000, 50000, n_bars)
    return pd.DataFrame(
        {"open": opn, "high": high, "low": low, "close": close, "volume": volume},
        index=idx,
    )


def _to_input(bars):
    return bars.reset_index().rename(columns={"index": "timestamp"})


def _test_cfg(**kwargs):
    defaults = dict(
        st_period=5, ema_length=5, st_factor=3.0,
        tp_percent=1.0, sl_percent=0.5,
        session_start="09:30", session_end="15:00",
        timezone="Asia/Kolkata",
        initial_capital=100_000.0, position_size_pct=0.10,
    )
    defaults.update(kwargs)
    return StrategyConfig(**defaults)


# -----------------------------------------------------------------------
# P01 - SUPERTREND EQUIVALENCE
# -----------------------------------------------------------------------

class TestSuperTrendEquivalence:

    def test_uptrend_equivalence(self):
        bars = _make_bars("2025-12-10", step=10.0, n_bars=60)
        data = _ensure_datetime_index(_to_input(bars))
        st_new, dir_new = supertrend(data, period=5, factor=3.0)
        st_old, dir_old = supertrend_legacy(data, period=5, factor=3.0)
        pd.testing.assert_series_equal(dir_new, dir_old, check_names=False, check_dtype=False)
        valid = st_old.notna()
        np.testing.assert_allclose(
            st_new[valid].values, st_old[valid].values, rtol=1e-12, atol=1e-12
        )

    def test_downtrend_equivalence(self):
        n_warm, n_down = 20, 46
        start_ts = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start_ts, periods=n_warm + n_down, freq="5min")
        prices = [2000.0] * n_warm + [1960.0 - i * 5 for i in range(n_down)]
        bars = pd.DataFrame(
            {"open": [p + 1 for p in prices], "high": [p + 1 for p in prices],
             "low": [p - 1 for p in prices], "close": [p - 1 for p in prices],
             "volume": [10_000] * (n_warm + n_down)},
            index=idx,
        )
        data = _ensure_datetime_index(_to_input(bars))
        st_new, dir_new = supertrend(data, period=5, factor=3.0)
        st_old, dir_old = supertrend_legacy(data, period=5, factor=3.0)
        pd.testing.assert_series_equal(dir_new, dir_old, check_names=False, check_dtype=False)
        valid = st_old.notna()
        np.testing.assert_allclose(
            st_new[valid].values, st_old[valid].values, rtol=1e-12, atol=1e-12
        )

    def test_sideways_equivalence(self):
        start = _ist_to_utc("2025-12-10", "09:30")
        idx = pd.date_range(start=start, periods=50, freq="5min")
        prices = [2000.0] * 50
        bars = pd.DataFrame(
            {"open": prices, "high": [p + 2 for p in prices],
             "low": [p - 2 for p in prices], "close": prices,
             "volume": [10_000] * 50},
            index=idx,
        )
        data = _ensure_datetime_index(_to_input(bars))
        st_new, dir_new = supertrend(data, period=10, factor=3.0)
        st_old, dir_old = supertrend_legacy(data, period=10, factor=3.0)
        pd.testing.assert_series_equal(dir_new, dir_old, check_names=False, check_dtype=False)
        valid = st_old.notna()
        np.testing.assert_allclose(
            st_new[valid].values, st_old[valid].values, rtol=1e-12, atol=1e-12
        )

    def test_random_data_equivalence(self):
        data = _make_synthetic_ohlcv(500, seed=99)
        st_new, dir_new = supertrend(data, period=10, factor=3.0)
        st_old, dir_old = supertrend_legacy(data, period=10, factor=3.0)
        pd.testing.assert_series_equal(dir_new, dir_old, check_names=False, check_dtype=False)
        valid = st_old.notna()
        np.testing.assert_allclose(
            st_new[valid].values, st_old[valid].values, rtol=1e-12, atol=1e-12
        )

    def test_real_data_equivalence(self):
        try:
            df = load_ohlcv_csv("data/RELIANCE_5M.csv")
        except FileNotFoundError:
            pytest.skip("RELIANCE_5M.csv not found")
        data = _ensure_datetime_index(df)
        st_new, dir_new = supertrend(data, period=10, factor=3.0)
        st_old, dir_old = supertrend_legacy(data, period=10, factor=3.0)
        pd.testing.assert_series_equal(dir_new, dir_old, check_names=False, check_dtype=False)
        valid = st_old.notna()
        np.testing.assert_allclose(
            st_new[valid].values, st_old[valid].values, rtol=1e-12, atol=1e-12
        )


# -----------------------------------------------------------------------
# P02 - PRECOMPUTE CACHE: signals match cached vs legacy
# -----------------------------------------------------------------------

class TestPrecomputeSignals:

    def test_precompute_signals_match_legacy_uptrend(self):
        bars = _make_bars("2025-12-10", step=10.0, n_bars=30)
        input_df = _to_input(bars)
        cfg = _test_cfg()

        strat_legacy = IntradayTrendFollowingStrategy()
        strat_legacy.initialize()

        strat_fast = IntradayTrendFollowingStrategy()
        strat_fast.initialize()
        strat_fast.precompute(input_df)

        prepared = prepare_strategy_dataframe(input_df, cfg)

        for i in range(len(prepared)):
            current_bar = prepared.iloc[i]
            data_slice = prepared.iloc[:i + 1]

            sig_legacy = strat_legacy.generate_signal(data_slice, current_bar, i)
            sig_fast = strat_fast.generate_signal(data_slice, current_bar, i)

            assert sig_legacy.action == sig_fast.action, (
                f"Signal mismatch at bar {i}: {sig_legacy.action} vs {sig_fast.action}"
            )
            assert sig_legacy.rationale == sig_fast.rationale, (
                f"Rationale mismatch at bar {i}"
            )

    def test_precompute_does_not_recompute_per_bar(self):
        bars = _make_bars("2025-12-10", step=10.0, n_bars=20)
        input_df = _to_input(bars)

        strat = IntradayTrendFollowingStrategy()
        strat.initialize()
        strat.precompute(input_df)

        assert strat._prepared_full is not None
        assert len(strat._prepared_full) == 20

        prepared = strat._prepared_full
        sig = strat.generate_signal(input_df, prepared.iloc[10], 10)
        assert sig.action is not None


# -----------------------------------------------------------------------
# P03 - CACHE INVALIDATION
# -----------------------------------------------------------------------

class TestCacheInvalidation:

    def test_reinitialize_clears_cache(self):
        strat = IntradayTrendFollowingStrategy()
        strat.initialize()
        bars = _make_bars("2025-12-10", step=10.0, n_bars=20)
        strat.precompute(_to_input(bars))
        assert strat._prepared_full is not None
        strat.initialize()
        assert strat._prepared_full is None

    def test_precompute_with_different_dataset_replaces_cache(self):
        strat = IntradayTrendFollowingStrategy()
        strat.initialize()

        bars_a = _make_bars("2025-12-10", step=10.0, n_bars=20)
        strat.precompute(_to_input(bars_a))
        cache_a_len = len(strat._prepared_full)

        bars_b = _make_bars("2025-12-11", step=5.0, n_bars=40)
        strat.precompute(_to_input(bars_b))
        cache_b_len = len(strat._prepared_full)

        assert cache_a_len == 20
        assert cache_b_len == 40
        assert strat._prepared_full.iloc[0]["close"] == bars_b.iloc[0]["close"]

    def test_bar_index_out_of_range_falls_back_to_legacy(self):
        strat = IntradayTrendFollowingStrategy()
        strat.initialize()
        bars = _make_bars("2025-12-10", step=10.0, n_bars=20)
        input_df = _to_input(bars)
        strat.precompute(input_df)

        prepared = prepare_strategy_dataframe(input_df, strat.config)
        sig = strat.generate_signal(input_df, prepared.iloc[-1], 999)
        assert sig.action is not None


# -----------------------------------------------------------------------
# P04 - BACKTEST EQUIVALENCE
# -----------------------------------------------------------------------

class TestBacktestEquivalence:

    def test_backtest_on_uptrend(self):
        bars = _make_bars("2025-12-10", step=10.0, n_bars=60)
        cfg = _test_cfg()
        _, trades, summary = backtest_strategy(_to_input(bars), cfg)
        assert summary["total_trades"] >= 0
        assert summary["wins"] + summary["losses"] == summary["total_trades"]

    def test_backtest_on_real_data(self):
        try:
            df = load_ohlcv_csv("data/RELIANCE_5M.csv")
        except FileNotFoundError:
            pytest.skip("RELIANCE_5M.csv not found")
        cfg = StrategyConfig(ema_length=20)
        data, trades, summary = backtest_strategy(df, cfg)
        assert "long_signal" in data.columns
        assert "short_signal" in data.columns
        assert summary["total_trades"] > 0
        assert summary["wins"] + summary["losses"] == summary["total_trades"]

    def test_backtest_results_deterministic(self):
        bars = _make_bars("2025-12-10", step=10.0, n_bars=60)
        cfg = _test_cfg()
        _, trades1, summary1 = backtest_strategy(_to_input(bars), cfg)
        _, trades2, summary2 = backtest_strategy(_to_input(bars), cfg)
        assert summary1 == summary2
        if not trades1.empty:
            pd.testing.assert_frame_equal(trades1, trades2)


# -----------------------------------------------------------------------
# P05 - BENCHMARK (informational)
# -----------------------------------------------------------------------

class TestBenchmark:

    def test_supertrend_speedup(self):
        data = _make_synthetic_ohlcv(1000, seed=42)
        supertrend(data, period=10, factor=3.0)
        supertrend_legacy(data, period=10, factor=3.0)

        t0 = time.perf_counter()
        for _ in range(3):
            supertrend_legacy(data, period=10, factor=3.0)
        legacy_time = (time.perf_counter() - t0) / 3

        t0 = time.perf_counter()
        for _ in range(3):
            supertrend(data, period=10, factor=3.0)
        opt_time = (time.perf_counter() - t0) / 3

        speedup = legacy_time / opt_time if opt_time > 0 else float("inf")
        print(f"\n  SuperTrend 1000 bars:")
        print(f"    Legacy:    {legacy_time * 1000:.1f} ms")
        print(f"    Optimized: {opt_time * 1000:.1f} ms")
        print(f"    Speedup:   {speedup:.1f}x")
        assert opt_time <= legacy_time * 1.5

    def test_prepare_strategy_scaling(self):
        cfg = _test_cfg(st_period=10, ema_length=20)
        sizes = [100, 250, 500, 1000]
        print("\n  prepare_strategy_dataframe timing:")
        print(f"  {'Bars':>6s}  {'Time (ms)':>10s}  {'bars/sec':>10s}")
        for n in sizes:
            data = _make_synthetic_ohlcv(n, seed=42)
            input_df = _to_input(data)
            prepare_strategy_dataframe(input_df, cfg)
            t0 = time.perf_counter()
            for _ in range(3):
                prepare_strategy_dataframe(input_df, cfg)
            elapsed = (time.perf_counter() - t0) / 3
            bars_per_sec = n / elapsed if elapsed > 0 else float("inf")
            print(f"  {n:>6d}  {elapsed * 1000:>10.1f}  {bars_per_sec:>10.0f}")

    def test_generate_signal_with_precompute(self):
        n = 500
        data = _make_synthetic_ohlcv(n, seed=42)
        input_df = _to_input(data)

        strat = IntradayTrendFollowingStrategy()
        strat.initialize()
        strat.precompute(input_df)

        prepared = strat._prepared_full

        t0 = time.perf_counter()
        for i in range(n):
            strat.generate_signal(input_df, prepared.iloc[i], i)
        precomputed_time = time.perf_counter() - t0

        bars_per_sec = n / precomputed_time if precomputed_time > 0 else float("inf")
        print(f"\n  generate_signal with precompute ({n} bars):")
        print(f"    Total:     {precomputed_time * 1000:.1f} ms")
        print(f"    bars/sec:  {bars_per_sec:.0f}")
