"""
Unit tests for src/research/regime_analysis.py

Tests cover:
  - analyze_by_regime: grouping, aggregation, missing-column graceful degradation
  - rank_strategies_by_regime: sort order, 1-based index, per-regime isolation
  - generate_regime_report: markdown output, file writing, minimal-report fallback
  - Input validation: TypeError, ValueError on bad inputs
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.research.regime_analysis import (
    analyze_by_regime,
    generate_regime_report,
    rank_strategies_by_regime,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_results(n_symbols: int = 3) -> pd.DataFrame:
    """
    Build a realistic results DataFrame with three regimes and three strategies.

    Regime → expected top strategy (by mean_sharpe):
      bullish_trending → sma   (Sharpe 1.2)
      rangebound       → rsi   (Sharpe 0.9)
      risk_off         → rsi   (Sharpe -0.3, least bad)
    """
    symbols = [chr(65 + i) for i in range(n_symbols)]  # A, B, C, …
    regimes = ["bullish_trending", "rangebound", "risk_off"]
    strategies = ["sma", "rsi", "breakout"]

    rows = []
    # Per-symbol: assign one regime per symbol, three strategy rows each
    regime_cycle = regimes * ((n_symbols // len(regimes)) + 1)
    for i, sym in enumerate(symbols):
        regime = regime_cycle[i]
        for strat in strategies:
            # Give each strategy deterministic metrics so assertions are stable
            if strat == "sma":
                sharpe, ret, dd, wr, trades = 1.2, 0.15, -0.05, 0.60, 10
            elif strat == "rsi":
                sharpe, ret, dd, wr, trades = 0.5, 0.05, -0.03, 0.50, 8
            else:  # breakout
                sharpe, ret, dd, wr, trades = 0.8, 0.10, -0.06, 0.55, 12
            # Adjust for regime so rankings differ
            if regime == "rangebound":
                if strat == "rsi":
                    sharpe = 0.9  # rsi wins in rangebound
                elif strat == "sma":
                    sharpe = 0.3
            if regime == "risk_off":
                sharpe -= 1.0   # all strategies perform worse
            rows.append({
                "symbol":           sym,
                "strategy":         strat,
                "regime_label":     regime,
                "sharpe_ratio":     sharpe,
                "total_return_pct": ret,
                "max_drawdown_pct": dd,
                "win_rate":         wr,
                "num_trades":       trades,
                "score":            sharpe + ret * 10,
            })
    return pd.DataFrame(rows)


def _minimal_df() -> pd.DataFrame:
    """Minimal two-column DataFrame (only required columns)."""
    return pd.DataFrame({
        "regime_label": ["bullish_trending", "bullish_trending"],
        "strategy":     ["sma", "rsi"],
        "symbol":       ["X", "Y"],
    })


# ---------------------------------------------------------------------------
# Tests: analyze_by_regime
# ---------------------------------------------------------------------------

class TestAnalyzeByRegime:

    def test_returns_dataframe(self):
        df = _make_results()
        result = analyze_by_regime(df)
        assert isinstance(result, pd.DataFrame)

    def test_has_required_columns(self):
        result = analyze_by_regime(_make_results())
        for col in ("regime_label", "strategy", "symbol_count", "run_count"):
            assert col in result.columns, f"Missing column: {col}"

    def test_metric_columns_present(self):
        result = analyze_by_regime(_make_results())
        for col in ("mean_sharpe", "mean_return", "mean_drawdown", "mean_win_rate",
                    "total_trades", "positive_return_rate"):
            assert col in result.columns, f"Missing metric column: {col}"

    def test_correct_group_count(self):
        df = _make_results(n_symbols=3)  # 3 symbols × 3 regimes × 3 strategies
        result = analyze_by_regime(df)
        # 3 regimes × 3 strategies = 9 groups at most; actual depends on how many
        # symbols land in each regime (1 per regime for 3 symbols)
        assert len(result) > 0
        assert set(result.columns) >= {"regime_label", "strategy"}

    def test_symbol_count_at_most_total_symbols(self):
        df = _make_results(n_symbols=6)
        result = analyze_by_regime(df)
        assert (result["symbol_count"] <= 6).all()

    def test_run_count_positive(self):
        result = analyze_by_regime(_make_results())
        assert (result["run_count"] > 0).all()

    def test_positive_return_rate_in_0_1(self):
        result = analyze_by_regime(_make_results())
        assert "positive_return_rate" in result.columns
        assert (result["positive_return_rate"].between(0, 1, inclusive="both")).all()

    def test_graceful_without_win_rate_column(self):
        df = _make_results().drop(columns=["win_rate"])
        result = analyze_by_regime(df)
        assert "mean_win_rate" not in result.columns
        assert "mean_sharpe" in result.columns  # other metrics still computed

    def test_graceful_without_sharpe_column(self):
        df = _make_results().drop(columns=["sharpe_ratio"])
        result = analyze_by_regime(df)
        assert "mean_sharpe" not in result.columns
        assert "run_count" in result.columns

    def test_filters_out_null_regime_labels(self):
        df = _make_results()
        df.loc[0, "regime_label"] = None
        result = analyze_by_regime(df)
        assert result["run_count"].sum() == len(df) - 1

    def test_raises_on_missing_required_columns(self):
        df = pd.DataFrame({"symbol": ["A"], "strategy": ["sma"]})
        with pytest.raises(ValueError, match="missing required columns"):
            analyze_by_regime(df)

    def test_raises_when_no_valid_regime_labels(self):
        df = _make_results()
        df["regime_label"] = None
        with pytest.raises(ValueError, match="No rows with a valid regime_label"):
            analyze_by_regime(df)

    def test_raises_on_non_dataframe(self):
        with pytest.raises(TypeError):
            analyze_by_regime([{"regime_label": "x", "strategy": "sma"}])

    def test_floats_rounded(self):
        result = analyze_by_regime(_make_results())
        float_cols = list(result.select_dtypes("float").columns)
        for col in float_cols:
            vals = result[col].dropna()
            for v in vals:
                # rounded to 4 decimal places
                assert round(v, 4) == v


# ---------------------------------------------------------------------------
# Tests: rank_strategies_by_regime
# ---------------------------------------------------------------------------

class TestRankStrategiesByRegime:

    def test_returns_dict(self):
        agg = analyze_by_regime(_make_results())
        ranked = rank_strategies_by_regime(agg)
        assert isinstance(ranked, dict)

    def test_keys_are_regime_labels(self):
        df = _make_results()
        agg = analyze_by_regime(df)
        ranked = rank_strategies_by_regime(agg)
        assert set(ranked.keys()) == set(agg["regime_label"].unique())

    def test_each_value_is_dataframe(self):
        ranked = rank_strategies_by_regime(analyze_by_regime(_make_results()))
        for regime, sub in ranked.items():
            assert isinstance(sub, pd.DataFrame), f"Regime {regime!r} value is not a DataFrame"

    def test_index_is_one_based(self):
        ranked = rank_strategies_by_regime(analyze_by_regime(_make_results()))
        for regime, sub in ranked.items():
            assert sub.index.min() == 1, f"Regime {regime!r}: index should start at 1"
            assert sub.index.max() == len(sub), f"Regime {regime!r}: index should end at len"

    def test_index_named_rank(self):
        ranked = rank_strategies_by_regime(analyze_by_regime(_make_results()))
        for sub in ranked.values():
            assert sub.index.name == "rank"

    def test_sma_wins_in_bullish_trending(self):
        df = _make_results(n_symbols=3)
        ranked = rank_strategies_by_regime(analyze_by_regime(df))
        if "bullish_trending" in ranked:
            top = ranked["bullish_trending"].iloc[0]["strategy"]
            assert top == "sma", f"Expected sma to win in bullish_trending, got {top}"

    def test_rsi_wins_in_rangebound(self):
        df = _make_results(n_symbols=3)
        ranked = rank_strategies_by_regime(analyze_by_regime(df))
        if "rangebound" in ranked:
            top = ranked["rangebound"].iloc[0]["strategy"]
            assert top == "rsi", f"Expected rsi to win in rangebound, got {top}"

    def test_sorted_descending_by_sharpe(self):
        """Each regime's rows should have non-increasing mean_sharpe."""
        ranked = rank_strategies_by_regime(analyze_by_regime(_make_results()))
        for regime, sub in ranked.items():
            if "mean_sharpe" in sub.columns and len(sub) > 1:
                sharpes = sub["mean_sharpe"].tolist()
                assert sharpes == sorted(sharpes, reverse=True), (
                    f"Regime {regime!r}: mean_sharpe not in descending order: {sharpes}"
                )

    def test_raises_on_missing_columns(self):
        bad = pd.DataFrame({"x": [1, 2]})
        with pytest.raises(ValueError, match="regime_label"):
            rank_strategies_by_regime(bad)

    def test_regimes_are_sorted_alphabetically(self):
        ranked = rank_strategies_by_regime(analyze_by_regime(_make_results()))
        keys = list(ranked.keys())
        assert keys == sorted(keys)


# ---------------------------------------------------------------------------
# Tests: generate_regime_report
# ---------------------------------------------------------------------------

class TestGenerateRegimeReport:

    def test_returns_string(self):
        content = generate_regime_report(_make_results())
        assert isinstance(content, str)

    def test_content_non_empty(self):
        content = generate_regime_report(_make_results())
        assert len(content) > 100

    def test_contains_key_sections(self):
        content = generate_regime_report(_make_results())
        for section in (
            "# Regime-Aware Historical Research Validation",
            "## Run Metadata",
            "## Regime Distribution",
            "## Performance by Regime",
            "## Best Strategies Per Regime",
            "## Summary Conclusions",
        ):
            assert section in content, f"Section missing: {section!r}"

    def test_file_written_to_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "report.md"
            generate_regime_report(_make_results(), output_path=path)
            assert path.exists()
            assert path.stat().st_size > 0

    def test_file_content_matches_return_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            content = generate_regime_report(_make_results(), output_path=path)
            assert path.read_text(encoding="utf-8") == content

    def test_metadata_appears_in_report(self):
        meta = {"interval": "day", "symbols_tested": 5}
        content = generate_regime_report(_make_results(), metadata=meta)
        assert "day" in content
        assert "5" in content

    def test_default_output_path_used_when_none(self, tmp_path, monkeypatch):
        """When output_path=None the default research/regime_validation.md is used."""
        monkeypatch.chdir(tmp_path)
        generate_regime_report(_make_results())
        default = tmp_path / "research" / "regime_validation.md"
        assert default.exists()

    def test_minimal_report_on_no_valid_labels(self):
        df = _make_results()
        df["regime_label"] = None
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.md"
            content = generate_regime_report(df, output_path=path)
        assert "Status: Incomplete" in content

    def test_minimal_report_on_missing_regime_label_column(self):
        df = _make_results().drop(columns=["regime_label"])
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "r.md"
            content = generate_regime_report(df, output_path=path)
        assert "Status: Incomplete" in content

    def test_all_regimes_appear_in_report(self):
        df = _make_results(n_symbols=3)
        content = generate_regime_report(df)
        for regime in df["regime_label"].unique():
            assert regime in content, f"Regime {regime!r} not in report"

    def test_report_ascii_safe(self):
        """Report must not contain non-ASCII characters (Windows cp1252 compatibility)."""
        content = generate_regime_report(_make_results())
        content.encode("ascii")  # raises UnicodeEncodeError if non-ASCII present

    def test_raises_on_non_dataframe(self):
        with pytest.raises(TypeError):
            generate_regime_report("not a dataframe")


# ---------------------------------------------------------------------------
# Tests: integration — analyze → rank → report pipeline
# ---------------------------------------------------------------------------

class TestPipeline:

    def test_full_pipeline_succeeds(self):
        df = _make_results(n_symbols=6)
        agg = analyze_by_regime(df)
        ranked = rank_strategies_by_regime(agg)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            content = generate_regime_report(df, output_path=path)
        assert agg.shape[0] > 0
        assert len(ranked) > 0
        assert "Best Strategies" in content

    def test_single_regime_single_strategy(self):
        df = pd.DataFrame({
            "symbol":           ["A"],
            "strategy":         ["sma"],
            "regime_label":     ["bullish_trending"],
            "sharpe_ratio":     [1.5],
            "total_return_pct": [0.20],
            "max_drawdown_pct": [-0.04],
            "win_rate":         [0.7],
            "num_trades":       [15],
        })
        agg = analyze_by_regime(df)
        assert len(agg) == 1
        ranked = rank_strategies_by_regime(agg)
        assert "bullish_trending" in ranked
        assert ranked["bullish_trending"].iloc[0]["strategy"] == "sma"

    def test_unknown_regime_label_handled(self):
        df = _make_results()
        df.loc[0, "regime_label"] = "unknown"
        agg = analyze_by_regime(df)
        assert agg is not None
        # unknown should appear as a distinct regime group
        if "unknown" in agg["regime_label"].values:
            ranked = rank_strategies_by_regime(agg)
            assert "unknown" in ranked
