"""
Unit tests for src/market_intelligence/relative_strength.py

Test classes:
  TestComputeRelativeStrength        - core metric computation
  TestRankSymbolsByStrength          - sorting / ranking
  TestSelectTopSymbols               - top-N selection
  TestRelativeStrengthMetrics        - individual metric accuracy
  TestCompositeScore                 - z-score composition
  TestBenchmarkIntegration           - benchmark relative-return
  TestEdgeCases                      - empty input, single symbol, short series
  TestGenerateRelativeStrengthReport - markdown report generation
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from src.market_intelligence.relative_strength import (
    RelativeStrengthRecord,
    compute_relative_strength,
    rank_symbols_by_strength,
    select_top_symbols,
    generate_relative_strength_report,
)


# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv(
    n: int = 90,
    start_price: float = 100.0,
    trend: float = 0.5,
    seed: int = 42,
) -> pd.DataFrame:
    """Create synthetic OHLCV with controllable trend and volatility."""
    np.random.seed(seed)
    dates = pd.date_range("2024-01-02", periods=n, freq="B")
    prices = start_price + trend * np.arange(n) + np.random.randn(n) * 0.3
    prices = np.abs(prices) + 1.0
    return pd.DataFrame({
        "open":   prices * 0.999,
        "high":   prices * 1.002,
        "low":    prices * 0.998,
        "close":  prices,
        "volume": np.random.randint(10_000, 50_000, n).astype(float),
    }, index=dates)


def _make_universe(
    n_symbols: int = 5,
    n_bars: int = 90,
    trends: list[float] | None = None,
) -> dict[str, pd.DataFrame]:
    if trends is None:
        trends = [i * 0.3 for i in range(n_symbols)]
    return {
        f"SYM{i}": _make_ohlcv(n_bars, trend=trends[i], seed=i)
        for i in range(n_symbols)
    }


# ===========================================================================
# TestComputeRelativeStrength
# ===========================================================================

class TestComputeRelativeStrength:
    """Core compute_relative_strength() tests."""

    def test_returns_dataframe(self):
        uni = _make_universe(3)
        df = compute_relative_strength(uni)
        assert isinstance(df, pd.DataFrame)

    def test_one_row_per_symbol(self):
        uni = _make_universe(5)
        df = compute_relative_strength(uni)
        assert len(df) == 5

    def test_expected_columns_present(self):
        uni = _make_universe(3)
        df = compute_relative_strength(uni)
        expected = {
            "symbol", "momentum_return", "trend_slope",
            "relative_return", "vol_adjusted_return",
            "rolling_strength_score", "lookback_bars",
        }
        assert expected.issubset(set(df.columns))

    def test_symbol_column_contains_all_symbols(self):
        uni = _make_universe(4)
        df = compute_relative_strength(uni)
        assert set(df["symbol"].tolist()) == set(uni.keys())

    def test_empty_input_returns_empty_dataframe(self):
        df = compute_relative_strength({})
        assert df.empty

    def test_lookback_bars_recorded(self):
        uni = _make_universe(2, n_bars=50)
        df = compute_relative_strength(uni, lookback=30)
        assert (df["lookback_bars"] == 30).all()

    def test_lookback_bars_capped_at_available_data(self):
        uni = {"SYM0": _make_ohlcv(20)}
        df = compute_relative_strength(uni, lookback=90)
        # 20 bars available, lookback=90 -> uses all 20
        assert df["lookback_bars"].iloc[0] == 20

    def test_sorted_by_score_descending(self):
        uni = _make_universe(5, trends=[0.5, -0.5, 0.1, 1.0, -1.0])
        df = compute_relative_strength(uni)
        scores = df["rolling_strength_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_no_lookahead_uses_tail_bars(self):
        """Using lookback=10 on 100 bars should only see last 10."""
        df_sym = _make_ohlcv(100)
        # Make early bars very low and recent bars very high
        df_sym["close"].iloc[:90] = 1.0    # early = flat low
        df_sym["close"].iloc[90:] = 200.0  # last 10 = high
        uni = {"SYM": df_sym}
        rs = compute_relative_strength(uni, lookback=10)
        # Lookback sees only the last 10 bars (all close = 200), so momentum ~ 0
        assert rs["lookback_bars"].iloc[0] == 10
        # momentum_return should be near 0 (200/200 - 1 = 0)
        assert abs(rs["momentum_return"].iloc[0]) < 0.01


# ===========================================================================
# TestRelativeStrengthMetrics
# ===========================================================================

class TestRelativeStrengthMetrics:
    """Individual metric accuracy tests."""

    def test_momentum_return_rising_symbol(self):
        """A rising price series should have positive momentum_return."""
        df_sym = _make_ohlcv(90, start_price=100.0, trend=1.0)
        rs = compute_relative_strength({"SYM": df_sym}, lookback=90)
        assert rs["momentum_return"].iloc[0] > 0.0

    def test_momentum_return_falling_symbol(self):
        """A falling price series should have negative momentum_return."""
        df_sym = _make_ohlcv(90, start_price=200.0, trend=-1.0, seed=99)
        rs = compute_relative_strength({"SYM": df_sym}, lookback=90)
        assert rs["momentum_return"].iloc[0] < 0.0

    def test_trend_slope_rising(self):
        """Linear uptrend should produce positive trend_slope."""
        dates = pd.date_range("2024-01-02", periods=50, freq="B")
        prices = np.linspace(100, 150, 50)
        df_sym = pd.DataFrame({"close": prices}, index=dates)
        rs = compute_relative_strength({"SYM": df_sym}, lookback=50)
        assert rs["trend_slope"].iloc[0] > 0.0

    def test_trend_slope_falling(self):
        """Linear downtrend should produce negative trend_slope."""
        dates = pd.date_range("2024-01-02", periods=50, freq="B")
        prices = np.linspace(150, 100, 50)
        df_sym = pd.DataFrame({"close": prices}, index=dates)
        rs = compute_relative_strength({"SYM": df_sym}, lookback=50)
        assert rs["trend_slope"].iloc[0] < 0.0

    def test_vol_adjusted_return_finite(self):
        """vol_adjusted_return should be a finite float for normal data."""
        uni = _make_universe(3)
        rs = compute_relative_strength(uni, lookback=90)
        for val in rs["vol_adjusted_return"]:
            assert np.isfinite(val)

    def test_relative_return_zero_without_benchmark(self):
        """With no benchmark, relative_return must be 0 for all symbols."""
        uni = _make_universe(3)
        rs = compute_relative_strength(uni)
        assert (rs["relative_return"] == 0.0).all()

    def test_momentum_return_matches_manual(self):
        """Verify momentum_return against manual calculation."""
        dates = pd.date_range("2024-01-02", periods=10, freq="B")
        prices = [100.0] * 5 + [120.0] * 5
        df_sym = pd.DataFrame({"close": prices}, index=dates)
        rs = compute_relative_strength({"SYM": df_sym}, lookback=10)
        expected = 120.0 / 100.0 - 1.0  # = 0.2
        assert rs["momentum_return"].iloc[0] == pytest.approx(expected, rel=1e-4)

    def test_lookback_bars_reflects_actual_used(self):
        uni = _make_universe(2, n_bars=100)
        rs = compute_relative_strength(uni, lookback=60)
        assert (rs["lookback_bars"] == 60).all()


# ===========================================================================
# TestCompositeScore
# ===========================================================================

class TestCompositeScore:
    """Composite z-score rolling_strength_score tests."""

    def test_score_is_zero_for_single_symbol(self):
        """Single-symbol universe: z-score undefined -> score=0."""
        uni = {"SYM": _make_ohlcv(90)}
        rs = compute_relative_strength(uni)
        assert rs["rolling_strength_score"].iloc[0] == 0.0

    def test_score_mean_is_approximately_zero(self):
        """Across multiple symbols, mean z-score should be ~0."""
        uni = _make_universe(10)
        rs = compute_relative_strength(uni, lookback=90)
        assert abs(rs["rolling_strength_score"].mean()) < 0.5

    def test_best_trending_symbol_has_highest_score(self):
        """The symbol with the strongest uptrend should rank first."""
        uni = {
            "WEAK":   _make_ohlcv(90, trend=0.1,  seed=0),
            "STRONG": _make_ohlcv(90, trend=2.0,  seed=1),
            "DOWN":   _make_ohlcv(90, trend=-1.0, seed=2),
        }
        rs = compute_relative_strength(uni, lookback=90)
        top_sym = rs.iloc[0]["symbol"]
        assert top_sym == "STRONG"

    def test_lowest_score_for_downtrend(self):
        """The symbol with a strong downtrend should rank last."""
        uni = {
            "UP":   _make_ohlcv(90, trend=1.5, seed=10),
            "FLAT": _make_ohlcv(90, trend=0.0, seed=11),
            "DOWN": _make_ohlcv(90, trend=-2.0, seed=12),
        }
        rs = compute_relative_strength(uni, lookback=90)
        bottom_sym = rs.iloc[-1]["symbol"]
        assert bottom_sym == "DOWN"

    def test_score_is_numeric(self):
        uni = _make_universe(4)
        rs = compute_relative_strength(uni)
        for val in rs["rolling_strength_score"]:
            assert isinstance(val, (int, float)) and np.isfinite(val)


# ===========================================================================
# TestBenchmarkIntegration
# ===========================================================================

class TestBenchmarkIntegration:
    """Tests for relative_return vs benchmark."""

    def _make_benchmark(
        self, n: int = 90, trend: float = 0.5, start: float = 1000.0
    ) -> pd.Series:
        dates = pd.date_range("2024-01-02", periods=n, freq="B")
        prices = start + trend * np.arange(n) + np.random.randn(n) * 0.1
        return pd.Series(prices, index=dates, name="benchmark_close")

    def test_relative_return_nonzero_with_benchmark(self):
        uni = _make_universe(3)
        bm = self._make_benchmark()
        rs = compute_relative_strength(uni, benchmark_series=bm)
        # At least some symbols should have nonzero relative_return
        # (unless they all exactly match benchmark return - very unlikely)
        assert not (rs["relative_return"] == 0.0).all()

    def test_relative_return_above_benchmark_is_positive(self):
        """Symbol outperforming benchmark should have positive relative_return."""
        dates = pd.date_range("2024-01-02", periods=60, freq="B")
        # Symbol: +50% gain
        sym_prices = np.linspace(100, 150, 60)
        df_sym = pd.DataFrame({"close": sym_prices}, index=dates)
        # Benchmark: +10% gain
        bm_prices = pd.Series(np.linspace(1000, 1100, 60), index=dates)
        rs = compute_relative_strength({"SYM": df_sym}, lookback=60, benchmark_series=bm_prices)
        # Symbol momentum = 0.5; benchmark momentum = 0.1; relative = 0.4
        assert rs["relative_return"].iloc[0] > 0.0

    def test_relative_return_below_benchmark_is_negative(self):
        """Symbol underperforming benchmark should have negative relative_return."""
        dates = pd.date_range("2024-01-02", periods=60, freq="B")
        sym_prices = np.linspace(100, 105, 60)   # +5%
        df_sym = pd.DataFrame({"close": sym_prices}, index=dates)
        bm_prices = pd.Series(np.linspace(1000, 1300, 60), index=dates)  # +30%
        rs = compute_relative_strength({"SYM": df_sym}, lookback=60, benchmark_series=bm_prices)
        assert rs["relative_return"].iloc[0] < 0.0

    def test_benchmark_missing_index_graceful(self):
        """Benchmark with completely different index: fallback to 0."""
        uni = {"SYM": _make_ohlcv(60)}
        # Benchmark with index that has no overlap
        future_dates = pd.date_range("2030-01-01", periods=60, freq="B")
        bm = pd.Series(np.ones(60) * 1000, index=future_dates)
        # Should not raise; relative_return may be 0 due to missing alignment
        rs = compute_relative_strength(uni, benchmark_series=bm)
        assert isinstance(rs, pd.DataFrame)
        assert "relative_return" in rs.columns


# ===========================================================================
# TestRankSymbolsByStrength
# ===========================================================================

class TestRankSymbolsByStrength:
    """rank_symbols_by_strength() tests."""

    def test_returns_dataframe(self):
        uni = _make_universe(3)
        rs = compute_relative_strength(uni)
        ranked = rank_symbols_by_strength(rs)
        assert isinstance(ranked, pd.DataFrame)

    def test_sorted_descending(self):
        uni = _make_universe(5)
        rs = compute_relative_strength(uni)
        ranked = rank_symbols_by_strength(rs)
        scores = ranked["rolling_strength_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_same_rows_as_input(self):
        uni = _make_universe(4)
        rs = compute_relative_strength(uni)
        ranked = rank_symbols_by_strength(rs)
        assert len(ranked) == len(rs)

    def test_empty_input_returns_empty(self):
        result = rank_symbols_by_strength(pd.DataFrame())
        assert result.empty

    def test_missing_score_column_returns_unchanged(self):
        df = pd.DataFrame({"symbol": ["A", "B"], "momentum_return": [0.1, 0.2]})
        result = rank_symbols_by_strength(df)
        # Should return unchanged (with warning)
        assert list(result["symbol"]) == ["A", "B"]

    def test_reset_index_after_sort(self):
        uni = _make_universe(5)
        rs = compute_relative_strength(uni)
        ranked = rank_symbols_by_strength(rs)
        assert list(ranked.index) == list(range(len(ranked)))


# ===========================================================================
# TestSelectTopSymbols
# ===========================================================================

class TestSelectTopSymbols:
    """select_top_symbols() tests."""

    def test_returns_list(self):
        uni = _make_universe(5)
        rs = compute_relative_strength(uni)
        result = select_top_symbols(rs, n=3)
        assert isinstance(result, list)

    def test_returns_correct_count(self):
        uni = _make_universe(10)
        rs = compute_relative_strength(uni)
        assert len(select_top_symbols(rs, n=5)) == 5

    def test_returns_at_most_n(self):
        uni = _make_universe(3)
        rs = compute_relative_strength(uni)
        # Ask for more than available
        result = select_top_symbols(rs, n=10)
        assert len(result) <= 3

    def test_top_symbol_is_strongest(self):
        uni = {
            "STRONG": _make_ohlcv(90, trend=3.0, seed=0),
            "WEAK":   _make_ohlcv(90, trend=0.1, seed=1),
            "DOWN":   _make_ohlcv(90, trend=-1.0, seed=2),
        }
        rs = compute_relative_strength(uni, lookback=90)
        top = select_top_symbols(rs, n=1)
        assert top[0] == "STRONG"

    def test_empty_dataframe_returns_empty_list(self):
        result = select_top_symbols(pd.DataFrame(), n=5)
        assert result == []

    def test_missing_symbol_column_returns_empty_list(self):
        df = pd.DataFrame({"rolling_strength_score": [1.0, 2.0]})
        result = select_top_symbols(df, n=1)
        assert result == []

    def test_n_one_returns_single_symbol(self):
        uni = _make_universe(5)
        rs = compute_relative_strength(uni)
        result = select_top_symbols(rs, n=1)
        assert len(result) == 1

    def test_symbols_in_list_are_strings(self):
        uni = _make_universe(4)
        rs = compute_relative_strength(uni)
        tops = select_top_symbols(rs, n=4)
        for sym in tops:
            assert isinstance(sym, str)

    def test_no_duplicates_in_top_list(self):
        uni = _make_universe(5)
        rs = compute_relative_strength(uni)
        tops = select_top_symbols(rs, n=5)
        assert len(tops) == len(set(tops))


# ===========================================================================
# TestEdgeCases
# ===========================================================================

class TestEdgeCases:
    """Edge case tests for robustness."""

    def test_symbol_missing_close_column_skipped(self):
        """Symbol without 'close' column should be silently skipped."""
        uni = {
            "VALID":   _make_ohlcv(90),
            "NO_CLOSE": pd.DataFrame({"open": [100.0], "high": [101.0]}),
        }
        rs = compute_relative_strength(uni)
        assert "VALID" in rs["symbol"].tolist()
        assert "NO_CLOSE" not in rs["symbol"].tolist()

    def test_symbol_with_one_bar_skipped(self):
        """Symbol with < 2 bars cannot compute return -> skipped."""
        uni = {
            "VALID": _make_ohlcv(30),
            "TINY":  pd.DataFrame({"close": [100.0]},
                                  index=pd.DatetimeIndex(["2024-01-02"])),
        }
        rs = compute_relative_strength(uni)
        assert "TINY" not in rs["symbol"].tolist()
        assert "VALID" in rs["symbol"].tolist()

    def test_all_symbols_invalid_returns_empty(self):
        uni = {
            "BAD1": pd.DataFrame({"open": [100.0]}),
            "BAD2": pd.DataFrame({"open": [200.0]}),
        }
        rs = compute_relative_strength(uni)
        assert rs.empty

    def test_symbol_with_nan_closes(self):
        """Symbol with NaN close values should still process (dropna applied)."""
        df = _make_ohlcv(90)
        df["close"].iloc[0:5] = float("nan")
        uni = {"SYM": df}
        rs = compute_relative_strength(uni, lookback=90)
        # Should not raise; result may have < 90 lookback_bars
        assert isinstance(rs, pd.DataFrame)

    def test_very_short_lookback(self):
        uni = _make_universe(3, n_bars=50)
        rs = compute_relative_strength(uni, lookback=3)
        assert len(rs) == 3
        assert (rs["lookback_bars"] == 3).all()

    def test_lookback_exceeds_all_symbol_lengths(self):
        uni = _make_universe(3, n_bars=10)
        rs = compute_relative_strength(uni, lookback=100)
        # Should use all 10 bars
        assert (rs["lookback_bars"] == 10).all()

    def test_flat_price_series(self):
        """Flat prices: momentum_return = 0, trend_slope = 0."""
        dates = pd.date_range("2024-01-02", periods=30, freq="B")
        df = pd.DataFrame({"close": [100.0] * 30}, index=dates)
        rs = compute_relative_strength({"FLAT": df}, lookback=30)
        assert rs["momentum_return"].iloc[0] == pytest.approx(0.0, abs=1e-9)


# ===========================================================================
# TestGenerateRelativeStrengthReport
# ===========================================================================

class TestGenerateRelativeStrengthReport:
    """Markdown report generation tests."""

    def _make_rs_df(self, n: int = 5) -> pd.DataFrame:
        uni = _make_universe(n)
        return compute_relative_strength(uni, lookback=90)

    def test_report_returns_string(self, tmp_path):
        rs_df = self._make_rs_df()
        content = generate_relative_strength_report(
            rs_df, output_path=tmp_path / "rs.md"
        )
        assert isinstance(content, str)
        assert len(content) > 100

    def test_report_file_written(self, tmp_path):
        rs_df = self._make_rs_df()
        out = tmp_path / "rs.md"
        generate_relative_strength_report(rs_df, output_path=out)
        assert out.exists()

    def test_report_contains_header(self, tmp_path):
        rs_df = self._make_rs_df()
        content = generate_relative_strength_report(rs_df, output_path=tmp_path / "rs.md")
        assert "Relative Strength Analysis" in content

    def test_report_contains_ranked_section(self, tmp_path):
        rs_df = self._make_rs_df()
        content = generate_relative_strength_report(rs_df, output_path=tmp_path / "rs.md")
        assert "Ranked Symbols by Relative Strength" in content

    def test_report_contains_top_10_section(self, tmp_path):
        rs_df = self._make_rs_df()
        content = generate_relative_strength_report(rs_df, output_path=tmp_path / "rs.md")
        assert "Top 10 Strongest Symbols" in content

    def test_report_contains_metric_definitions(self, tmp_path):
        rs_df = self._make_rs_df()
        content = generate_relative_strength_report(rs_df, output_path=tmp_path / "rs.md")
        assert "Metric Definitions" in content

    def test_report_contains_caveats(self, tmp_path):
        rs_df = self._make_rs_df()
        content = generate_relative_strength_report(rs_df, output_path=tmp_path / "rs.md")
        assert "Caveats" in content

    def test_report_contains_symbol_names(self, tmp_path):
        rs_df = self._make_rs_df(3)
        content = generate_relative_strength_report(rs_df, output_path=tmp_path / "rs.md")
        for sym in ["SYM0", "SYM1", "SYM2"]:
            assert sym in content

    def test_report_ascii_only(self, tmp_path):
        """Report must be ASCII-only for Windows cp1252 compatibility."""
        rs_df = self._make_rs_df()
        content = generate_relative_strength_report(rs_df, output_path=tmp_path / "rs.md")
        non_ascii = [c for c in content if ord(c) >= 128]
        assert non_ascii == [], f"Non-ASCII chars found: {non_ascii}"

    def test_report_with_metadata(self, tmp_path):
        rs_df = self._make_rs_df()
        content = generate_relative_strength_report(
            rs_df,
            output_path=tmp_path / "rs.md",
            metadata={"lookback_bars": 90, "benchmark_symbol": "NIFTY50"},
        )
        assert "90" in content
        assert "NIFTY50" in content

    def test_report_empty_dataframe(self, tmp_path):
        """Empty DataFrame should still produce a valid (minimal) report."""
        content = generate_relative_strength_report(
            pd.DataFrame(), output_path=tmp_path / "rs.md"
        )
        assert isinstance(content, str)
        assert "Relative Strength Analysis" in content

    def test_report_default_path_created(self, tmp_path, monkeypatch):
        """generate_relative_strength_report should create parent dirs."""
        out = tmp_path / "research" / "relative_strength_analysis.md"
        rs_df = self._make_rs_df()
        generate_relative_strength_report(rs_df, output_path=out)
        assert out.exists()


# ===========================================================================
# TestRelativeStrengthRecord
# ===========================================================================

class TestRelativeStrengthRecord:
    """Sanity tests for the RelativeStrengthRecord dataclass."""

    def test_record_creation(self):
        r = RelativeStrengthRecord(
            symbol="RELIANCE",
            momentum_return=0.12,
            trend_slope=0.002,
            relative_return=0.05,
            vol_adjusted_return=1.8,
            rolling_strength_score=1.2,
            lookback_bars=90,
        )
        assert r.symbol == "RELIANCE"
        assert r.momentum_return == pytest.approx(0.12)
        assert r.lookback_bars == 90
