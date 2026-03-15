"""
Unit tests for src/decision/regime_policy.py

Tests cover:
  - RegimePolicyBuilder.build(): policy construction, thresholds, no-trade logic
  - Ranking and preferred-strategy selection
  - Allowed / suppressed strategy categorisation
  - risk_off auto no-trade behaviour
  - RegimePolicy: serialisation (to_dict, to_json, from_dict, save_json, load_json)
  - select_for_regime(): runtime hook, unknown regime fallback
  - generate_policy_report(): markdown output, file writing
  - Graceful handling of small / incomplete datasets
  - Deterministic output ordering (alphabetical ties, stable sort)
  - Input validation: TypeError, ValueError on bad inputs
"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pandas as pd
import pytest

from src.decision.regime_policy import (
    MIN_RUN_COUNT,
    NO_TRADE_POS_RATE_MAX,
    NO_TRADE_SHARPE_MAX,
    POS_RETURN_RATE_MIN,
    RISK_OFF_AUTO_NO_TRADE,
    SHARPE_ALLOWED_MIN,
    SHARPE_PREFERRED_MIN,
    SHARPE_SUPPRESSED_BELOW,
    RegimePolicy,
    RegimePolicyBuilder,
    RegimePolicyDecision,
    RegimePolicyEntry,
    generate_policy_report,
    select_for_regime,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

def _make_agg_df(
    regimes: list[str] | None = None,
    strategies: list[str] | None = None,
    sharpes: dict[tuple[str, str], float] | None = None,
    returns: dict[tuple[str, str], float] | None = None,
    run_counts: dict[tuple[str, str], int] | None = None,
    pos_rates: dict[tuple[str, str], float] | None = None,
) -> pd.DataFrame:
    """
    Build a synthetic agg_df (output of analyze_by_regime) for testing.

    Default: 3 regimes x 3 strategies with a mix of good/bad performance.
    Regime defaults:
      bullish_trending -> sma wins clearly (sharpe 1.2)
      rangebound       -> rsi wins (sharpe 0.8)
      risk_off         -> all negative (worst regime)
    """
    if regimes is None:
        regimes = ["bullish_trending", "rangebound", "risk_off"]
    if strategies is None:
        strategies = ["sma", "rsi", "breakout"]

    # Default sharpes: bullish_trending favours sma, rangebound favours rsi,
    # risk_off is bad for all
    default_sharpes: dict[tuple[str, str], float] = {
        ("bullish_trending", "sma"):      1.20,
        ("bullish_trending", "rsi"):      0.30,
        ("bullish_trending", "breakout"): 0.85,
        ("rangebound",       "sma"):      0.10,
        ("rangebound",       "rsi"):      0.80,
        ("rangebound",       "breakout"): 0.20,
        ("risk_off",         "sma"):     -0.80,
        ("risk_off",         "rsi"):     -0.60,
        ("risk_off",         "breakout"):-0.90,
    }
    default_returns: dict[tuple[str, str], float] = {
        ("bullish_trending", "sma"):      0.15,
        ("bullish_trending", "rsi"):      0.03,
        ("bullish_trending", "breakout"): 0.10,
        ("rangebound",       "sma"):      0.01,
        ("rangebound",       "rsi"):      0.08,
        ("rangebound",       "breakout"): 0.02,
        ("risk_off",         "sma"):     -0.12,
        ("risk_off",         "rsi"):     -0.06,
        ("risk_off",         "breakout"):-0.18,
    }
    default_pos_rates: dict[tuple[str, str], float] = {
        ("bullish_trending", "sma"):      0.80,
        ("bullish_trending", "rsi"):      0.40,
        ("bullish_trending", "breakout"): 0.60,
        ("rangebound",       "sma"):      0.30,
        ("rangebound",       "rsi"):      0.70,
        ("rangebound",       "breakout"): 0.40,
        ("risk_off",         "sma"):      0.10,
        ("risk_off",         "rsi"):      0.20,
        ("risk_off",         "breakout"): 0.10,
    }
    default_run_counts: dict[tuple[str, str], int] = {
        (r, s): 5 for r in regimes for s in strategies
    }

    rows = []
    for regime in regimes:
        for strat in strategies:
            key = (regime, strat)
            rows.append({
                "regime_label":        regime,
                "strategy":            strat,
                "run_count":           (run_counts or default_run_counts).get(key, 5),
                "symbol_count":        (run_counts or default_run_counts).get(key, 5),
                "mean_sharpe":         (sharpes or default_sharpes).get(key, 0.0),
                "mean_return":         (returns or default_returns).get(key, 0.0),
                "mean_drawdown":       -0.10,
                "positive_return_rate":(pos_rates or default_pos_rates).get(key, 0.5),
                "total_trades":        10,
            })
    return pd.DataFrame(rows)


def _builder(**kwargs) -> RegimePolicyBuilder:
    return RegimePolicyBuilder(**kwargs)


# ---------------------------------------------------------------------------
# Tests: RegimePolicyBuilder.build()
# ---------------------------------------------------------------------------

class TestRegimePolicyBuilder:

    def test_returns_regime_policy(self):
        agg = _make_agg_df()
        policy = _builder().build(agg)
        assert isinstance(policy, RegimePolicy)

    def test_entries_keyed_by_regime(self):
        agg = _make_agg_df()
        policy = _builder().build(agg)
        assert set(policy.entries.keys()) == {"bullish_trending", "rangebound", "risk_off"}

    def test_each_entry_is_regime_policy_entry(self):
        policy = _builder().build(_make_agg_df())
        for label, entry in policy.entries.items():
            assert isinstance(entry, RegimePolicyEntry), f"{label} entry is not RegimePolicyEntry"

    def test_entries_sorted_alphabetically(self):
        policy = _builder().build(_make_agg_df())
        keys = list(policy.entries.keys())
        assert keys == sorted(keys)

    def test_preferred_strategy_bullish_trending_is_sma(self):
        policy = _builder().build(_make_agg_df())
        entry = policy.entries["bullish_trending"]
        assert entry.preferred_strategy == "sma"

    def test_preferred_strategy_rangebound_is_rsi(self):
        policy = _builder().build(_make_agg_df())
        entry = policy.entries["rangebound"]
        assert entry.preferred_strategy == "rsi"

    def test_risk_off_no_trade_by_default(self):
        """Default risk_off sharpes are all negative: should_trade=False."""
        policy = _builder().build(_make_agg_df())
        entry = policy.entries["risk_off"]
        assert entry.should_trade is False

    def test_risk_off_trade_when_strategy_clears_threshold(self):
        """If one strategy in risk_off clears SHARPE_PREFERRED_MIN, allow trading."""
        sharpes = {
            ("risk_off", "sma"):     0.10,   # > 0.0 -> clears preferred min
            ("risk_off", "rsi"):    -0.60,
            ("risk_off", "breakout"):-0.90,
        }
        agg = _make_agg_df(
            regimes=["risk_off"],
            sharpes=sharpes,
            pos_rates={("risk_off", "sma"): 0.50,
                       ("risk_off", "rsi"): 0.20,
                       ("risk_off", "breakout"): 0.10},
        )
        policy = _builder().build(agg)
        assert policy.entries["risk_off"].should_trade is True
        assert policy.entries["risk_off"].preferred_strategy == "sma"

    def test_no_trade_when_all_strategies_universally_bad(self):
        """Any regime with all strategies well below thresholds -> should_trade=False."""
        bad_sharpes = {
            ("bearish_volatile", "sma"):     -0.80,
            ("bearish_volatile", "rsi"):     -0.70,
            ("bearish_volatile", "breakout"):-0.90,
        }
        bad_pos = {k: 0.10 for k in bad_sharpes}
        agg = _make_agg_df(
            regimes=["bearish_volatile"],
            sharpes=bad_sharpes,
            pos_rates=bad_pos,
        )
        policy = _builder().build(agg)
        assert policy.entries["bearish_volatile"].should_trade is False

    def test_trade_when_some_strategies_acceptable(self):
        """Regime where at least one strategy clears allowed threshold."""
        policy = _builder().build(_make_agg_df())
        entry = policy.entries["bullish_trending"]
        assert entry.should_trade is True

    def test_ranked_strategies_descending_sharpe(self):
        policy = _builder().build(_make_agg_df())
        entry = policy.entries["bullish_trending"]
        sharpes_in_order = [
            _make_agg_df()[
                (_make_agg_df()["regime_label"] == "bullish_trending") &
                (_make_agg_df()["strategy"] == s)
            ]["mean_sharpe"].iloc[0]
            for s in entry.ranked_strategies
        ]
        assert sharpes_in_order == sorted(sharpes_in_order, reverse=True)

    def test_allowed_strategies_meet_thresholds(self):
        policy = _builder().build(_make_agg_df())
        agg = _make_agg_df()
        for regime, entry in policy.entries.items():
            for strat in entry.allowed_strategies:
                row = agg[(agg["regime_label"] == regime) & (agg["strategy"] == strat)]
                assert not row.empty
                assert float(row["mean_sharpe"].iloc[0]) >= SHARPE_ALLOWED_MIN
                assert float(row["positive_return_rate"].iloc[0]) >= POS_RETURN_RATE_MIN

    def test_suppressed_strategies_below_threshold(self):
        policy = _builder().build(_make_agg_df())
        agg = _make_agg_df()
        for regime, entry in policy.entries.items():
            for strat in entry.suppressed_strategies:
                row = agg[(agg["regime_label"] == regime) & (agg["strategy"] == strat)]
                assert not row.empty
                assert float(row["mean_sharpe"].iloc[0]) < SHARPE_SUPPRESSED_BELOW

    def test_no_preferred_strategy_when_all_below_preferred_min(self):
        """If all strategies in a regime have mean_sharpe < 0.0, no preferred."""
        sharpes = {
            ("rangebound", "sma"):     -0.10,
            ("rangebound", "rsi"):     -0.05,
            ("rangebound", "breakout"):-0.15,
        }
        pos_rates = {k: 0.30 for k in sharpes}
        agg = _make_agg_df(regimes=["rangebound"], sharpes=sharpes, pos_rates=pos_rates)
        policy = _builder().build(agg)
        assert policy.entries["rangebound"].preferred_strategy is None

    def test_insufficient_run_count_excluded(self):
        """Strategies with run_count < MIN_RUN_COUNT are not allowed or preferred."""
        run_counts = {
            ("bullish_trending", "sma"):      2,  # below MIN_RUN_COUNT=3
            ("bullish_trending", "rsi"):      5,
            ("bullish_trending", "breakout"): 5,
        }
        sharpes = {
            ("bullish_trending", "sma"):      2.0,  # best sharpe but too few runs
            ("bullish_trending", "rsi"):      0.50,
            ("bullish_trending", "breakout"): 0.80,
        }
        pos_rates = {k: 0.60 for k in sharpes}
        agg = _make_agg_df(
            regimes=["bullish_trending"],
            sharpes=sharpes, run_counts=run_counts, pos_rates=pos_rates,
        )
        policy = _builder().build(agg)
        entry = policy.entries["bullish_trending"]
        # sma has best sharpe but not enough runs -> must not be preferred/allowed
        assert "sma" not in entry.allowed_strategies
        assert entry.preferred_strategy != "sma"

    def test_rationale_is_non_empty_string(self):
        policy = _builder().build(_make_agg_df())
        for entry in policy.entries.values():
            assert isinstance(entry.rationale, str)
            assert len(entry.rationale) > 0

    def test_source_metrics_contains_all_strategies(self):
        policy = _builder().build(_make_agg_df())
        for label, entry in policy.entries.items():
            # Source metrics should have a key per strategy seen in this regime
            assert len(entry.source_metrics) > 0
            for strat in entry.ranked_strategies:
                assert strat in entry.source_metrics

    def test_generated_at_is_set(self):
        policy = _builder().build(_make_agg_df())
        assert isinstance(policy.generated_at, str)
        assert len(policy.generated_at) > 0

    def test_metadata_passed_through(self):
        meta = {"symbols_tested": 20, "interval": "day"}
        policy = _builder().build(_make_agg_df(), metadata=meta)
        assert policy.metadata["symbols_tested"] == 20
        assert policy.metadata["interval"] == "day"

    def test_source_description_passed_through(self):
        desc = "Test description"
        policy = _builder().build(_make_agg_df(), source_description=desc)
        assert policy.source_description == desc

    def test_single_regime_single_strategy(self):
        agg = pd.DataFrame([{
            "regime_label": "rangebound",
            "strategy": "rsi",
            "run_count": 5,
            "mean_sharpe": 0.80,
            "mean_return": 0.08,
            "mean_drawdown": -0.05,
            "positive_return_rate": 0.70,
        }])
        policy = _builder().build(agg)
        assert "rangebound" in policy
        entry = policy.entries["rangebound"]
        assert entry.preferred_strategy == "rsi"
        assert entry.should_trade is True

    def test_raises_on_non_dataframe(self):
        with pytest.raises(TypeError):
            _builder().build([{"regime_label": "x", "strategy": "sma"}])

    def test_raises_on_missing_required_columns(self):
        bad = pd.DataFrame({"x": [1, 2]})
        with pytest.raises(ValueError, match="regime_label"):
            _builder().build(bad)

    def test_custom_thresholds_respected(self):
        """Builder respects custom threshold kwargs."""
        agg = _make_agg_df()
        # Set a very high preferred_min so no strategy qualifies
        policy = _builder(sharpe_preferred_min=5.0).build(agg)
        for entry in policy.entries.values():
            assert entry.preferred_strategy is None

    def test_risk_off_auto_no_trade_disabled(self):
        """When risk_off_auto_no_trade=False, risk_off follows general logic."""
        # risk_off with one strategy above SHARPE_ALLOWED_MIN
        sharpes = {
            ("risk_off", "sma"):     -0.20,  # above -0.25 allowed_min
            ("risk_off", "rsi"):     -0.60,
            ("risk_off", "breakout"):-0.80,
        }
        pos_rates = {
            ("risk_off", "sma"):     0.30,   # above POS_RETURN_RATE_MIN
            ("risk_off", "rsi"):     0.15,
            ("risk_off", "breakout"):0.10,
        }
        agg = _make_agg_df(regimes=["risk_off"], sharpes=sharpes, pos_rates=pos_rates)
        policy = _builder(risk_off_auto_no_trade=False).build(agg)
        # General logic: sma is allowed (sharpe > -0.25, pos_rate > 0.25)
        # Universal no-trade not triggered because sma is acceptable
        assert policy.entries["risk_off"].should_trade is True

    def test_deterministic_on_repeated_calls(self):
        """Calling build twice on same input produces identical policy."""
        agg = _make_agg_df()
        p1 = _builder().build(agg)
        p2 = _builder().build(agg)
        assert p1.to_json() == p2.to_json()

    def test_tie_breaking_alphabetical(self):
        """When two strategies have identical metrics, alphabetical order is used."""
        agg = pd.DataFrame([
            {"regime_label": "rangebound", "strategy": "zzz_strat",
             "run_count": 5, "mean_sharpe": 0.50, "mean_return": 0.05,
             "mean_drawdown": -0.10, "positive_return_rate": 0.60},
            {"regime_label": "rangebound", "strategy": "aaa_strat",
             "run_count": 5, "mean_sharpe": 0.50, "mean_return": 0.05,
             "mean_drawdown": -0.10, "positive_return_rate": 0.60},
        ])
        policy = _builder().build(agg)
        ranked = policy.entries["rangebound"].ranked_strategies
        # Same sharpe -> alphabetical: aaa_strat before zzz_strat
        assert ranked == ["aaa_strat", "zzz_strat"]


# ---------------------------------------------------------------------------
# Tests: RegimePolicy serialisation
# ---------------------------------------------------------------------------

class TestRegimePolicySerialisation:

    def test_to_dict_returns_dict(self):
        p = _builder().build(_make_agg_df())
        d = p.to_dict()
        assert isinstance(d, dict)

    def test_to_dict_has_required_top_keys(self):
        d = _builder().build(_make_agg_df()).to_dict()
        for key in ("generated_at", "source_description", "metadata", "thresholds", "regimes"):
            assert key in d, f"Missing top-level key: {key!r}"

    def test_to_dict_thresholds_embedded(self):
        d = _builder().build(_make_agg_df()).to_dict()
        thresholds = d["thresholds"]
        assert thresholds["MIN_RUN_COUNT"]        == MIN_RUN_COUNT
        assert thresholds["SHARPE_PREFERRED_MIN"] == SHARPE_PREFERRED_MIN

    def test_to_json_is_valid_json(self):
        j = _builder().build(_make_agg_df()).to_json()
        parsed = json.loads(j)
        assert isinstance(parsed, dict)

    def test_to_json_ascii_safe(self):
        j = _builder().build(_make_agg_df()).to_json()
        j.encode("ascii")  # raises if non-ASCII chars present

    def test_from_dict_roundtrip(self):
        original = _builder().build(_make_agg_df())
        d = original.to_dict()
        restored = RegimePolicy.from_dict(d)
        assert set(restored.entries.keys()) == set(original.entries.keys())
        for label in original.entries:
            o = original.entries[label]
            r = restored.entries[label]
            assert o.preferred_strategy == r.preferred_strategy
            assert o.allowed_strategies  == r.allowed_strategies
            assert o.suppressed_strategies == r.suppressed_strategies
            assert o.should_trade        == r.should_trade

    def test_save_and_load_json(self):
        original = _builder().build(_make_agg_df())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.json"
            original.save_json(path)
            assert path.exists()
            loaded = RegimePolicy.load_json(path)
        assert len(loaded.entries) == len(original.entries)
        for label in original.entries:
            assert loaded.entries[label].preferred_strategy == original.entries[label].preferred_strategy
            assert loaded.entries[label].should_trade == original.entries[label].should_trade

    def test_load_json_raises_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            RegimePolicy.load_json("/nonexistent/path/policy.json")

    def test_save_json_creates_parent_dirs(self):
        original = _builder().build(_make_agg_df())
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "deep" / "policy.json"
            original.save_json(path)
            assert path.exists()

    def test_contains_operator(self):
        policy = _builder().build(_make_agg_df())
        assert "bullish_trending" in policy
        assert "nonexistent_regime" not in policy

    def test_len_operator(self):
        policy = _builder().build(_make_agg_df())
        assert len(policy) == 3

    def test_get_returns_none_for_unknown_regime(self):
        policy = _builder().build(_make_agg_df())
        assert policy.get("does_not_exist") is None


# ---------------------------------------------------------------------------
# Tests: select_for_regime()
# ---------------------------------------------------------------------------

class TestSelectForRegime:

    def _policy(self) -> RegimePolicy:
        return _builder().build(_make_agg_df())

    def test_returns_decision(self):
        d = select_for_regime("bullish_trending", ["sma", "rsi", "breakout"], self._policy())
        assert isinstance(d, RegimePolicyDecision)

    def test_preferred_strategy_in_decision(self):
        d = select_for_regime("bullish_trending", ["sma", "rsi", "breakout"], self._policy())
        assert d.preferred_strategy == "sma"

    def test_should_trade_false_in_risk_off(self):
        d = select_for_regime("risk_off", ["sma", "rsi", "breakout"], self._policy())
        assert d.should_trade is False

    def test_no_trade_gives_empty_allowed(self):
        d = select_for_regime("risk_off", ["sma", "rsi", "breakout"], self._policy())
        assert d.allowed_strategies == []

    def test_unknown_regime_fallback(self):
        """Regime not in policy returns fallback with policy_found=False."""
        d = select_for_regime("unknown_regime_xyz", ["sma", "rsi"], self._policy())
        assert d.policy_found is False
        assert d.should_trade is True   # conservative: don't block unknown
        assert sorted(d.allowed_strategies) == ["rsi", "sma"]

    def test_available_strategies_intersected(self):
        """Only strategies available to the caller appear in the decision."""
        d = select_for_regime("bullish_trending", ["sma"], self._policy())
        # allowed must be subset of available
        assert all(s in {"sma"} for s in d.allowed_strategies)

    def test_preferred_filtered_when_not_available(self):
        """If preferred strategy is not available, preferred is None."""
        # sma is preferred in bullish_trending; pass only rsi
        d = select_for_regime("bullish_trending", ["rsi", "breakout"], self._policy())
        assert d.preferred_strategy != "sma"

    def test_explanation_is_non_empty(self):
        d = select_for_regime("rangebound", ["sma", "rsi", "breakout"], self._policy())
        assert isinstance(d.explanation, str)
        assert len(d.explanation) > 0

    def test_detected_regime_preserved(self):
        d = select_for_regime("rangebound", ["rsi"], self._policy())
        assert d.detected_regime == "rangebound"

    def test_raises_on_bad_policy_type(self):
        with pytest.raises(TypeError):
            select_for_regime("bullish_trending", ["sma"], policy={"fake": "dict"})


# ---------------------------------------------------------------------------
# Tests: generate_policy_report()
# ---------------------------------------------------------------------------

class TestGeneratePolicyReport:

    def _policy(self) -> RegimePolicy:
        return _builder().build(_make_agg_df())

    def test_returns_string(self):
        content = generate_policy_report(self._policy())
        assert isinstance(content, str)

    def test_content_non_empty(self):
        assert len(generate_policy_report(self._policy())) > 100

    def test_contains_required_sections(self):
        content = generate_policy_report(self._policy())
        for section in (
            "# Regime-Driven Strategy Selection Policy",
            "## Policy Metadata",
            "## Policy Thresholds",
            "## Summary Table",
            "## Per-Regime Policy Detail",
            "## Notes and Caveats",
        ):
            assert section in content, f"Section missing: {section!r}"

    def test_all_regimes_in_report(self):
        content = generate_policy_report(self._policy())
        for regime in ("bullish_trending", "rangebound", "risk_off"):
            assert regime in content

    def test_file_written_to_output_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "policy.md"
            generate_policy_report(self._policy(), output_path=path)
            assert path.exists()
            assert path.stat().st_size > 0

    def test_file_content_matches_return_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policy.md"
            content = generate_policy_report(self._policy(), output_path=path)
            assert path.read_text(encoding="utf-8") == content

    def test_default_output_path(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        generate_policy_report(self._policy())
        default = tmp_path / "research" / "regime_policy.md"
        assert default.exists()

    def test_summary_table_present(self):
        content = generate_policy_report(self._policy())
        assert "| Regime | Preferred | Allowed | Suppressed | Trade? |" in content

    def test_report_ascii_safe(self):
        content = generate_policy_report(self._policy())
        content.encode("ascii")  # raises UnicodeEncodeError if non-ASCII

    def test_raises_on_non_policy(self):
        with pytest.raises(TypeError):
            generate_policy_report("not_a_policy")


# ---------------------------------------------------------------------------
# Tests: edge cases and graceful handling
# ---------------------------------------------------------------------------

class TestEdgeCases:

    def test_single_strategy_becomes_preferred_if_good(self):
        agg = pd.DataFrame([{
            "regime_label": "bullish_trending",
            "strategy": "sma",
            "run_count": 10,
            "mean_sharpe": 1.50,
            "mean_return": 0.20,
            "mean_drawdown": -0.05,
            "positive_return_rate": 0.90,
        }])
        policy = _builder().build(agg)
        entry = policy.entries["bullish_trending"]
        assert entry.preferred_strategy == "sma"
        assert "sma" in entry.allowed_strategies
        assert entry.should_trade is True

    def test_all_strategies_suppressed(self):
        """All strategies far below threshold -> all suppressed, no-trade."""
        sharpes = {
            ("risk_off", "sma"):     -0.90,
            ("risk_off", "rsi"):     -0.70,
            ("risk_off", "breakout"):-0.95,
        }
        pos_rates = {k: 0.05 for k in sharpes}
        agg = _make_agg_df(regimes=["risk_off"], sharpes=sharpes, pos_rates=pos_rates)
        policy = _builder().build(agg)
        entry = policy.entries["risk_off"]
        # All below SHARPE_SUPPRESSED_BELOW (-0.5)
        assert set(entry.suppressed_strategies) == {"sma", "rsi", "breakout"}
        assert entry.should_trade is False

    def test_no_positive_return_rate_column(self):
        """Graceful when positive_return_rate column is absent."""
        agg = pd.DataFrame([{
            "regime_label": "rangebound",
            "strategy": "rsi",
            "run_count": 5,
            "mean_sharpe": 0.80,
            "mean_return": 0.08,
            "mean_drawdown": -0.05,
            # no positive_return_rate column
        }])
        # Default pos_return_rate in _extract_records is 0.0 -> below 0.25 threshold
        policy = _builder().build(agg)
        entry = policy.entries["rangebound"]
        # With pos_return_rate defaulting to 0.0, rsi fails the allowed check
        assert "rsi" not in entry.allowed_strategies

    def test_no_mean_sharpe_column(self):
        """Graceful when mean_sharpe column is absent (defaults to -inf)."""
        agg = pd.DataFrame([{
            "regime_label": "rangebound",
            "strategy": "rsi",
            "run_count": 5,
            "mean_return": 0.08,
            # no mean_sharpe
        }])
        policy = _builder().build(agg)
        # Without mean_sharpe, default is -inf -> not preferred, not allowed
        assert policy.entries["rangebound"].preferred_strategy is None
        assert policy.entries["rangebound"].allowed_strategies == []

    def test_multiple_regimes_isolated(self):
        """Policy for one regime does not bleed into another."""
        policy = _builder().build(_make_agg_df())
        bt = policy.entries["bullish_trending"]
        rb = policy.entries["rangebound"]
        # bullish_trending prefers sma; rangebound prefers rsi
        assert bt.preferred_strategy != rb.preferred_strategy

    def test_unknown_regime_in_data(self):
        """unknown regime label is handled like any other regime."""
        agg = _make_agg_df(regimes=["unknown"])
        policy = _builder().build(agg)
        assert "unknown" in policy.entries

    def test_empty_available_strategies_in_select(self):
        """select_for_regime with empty available list returns empty allowed."""
        policy = _builder().build(_make_agg_df())
        d = select_for_regime("bullish_trending", [], policy)
        assert d.allowed_strategies == []
        assert d.preferred_strategy is None
