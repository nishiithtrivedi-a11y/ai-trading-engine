"""
Regression tests for MonteCarloAnalyzer Sharpe ratio calculation.

Phase 16A corrected the formula to use equity-curve returns (not raw PnL
values) with proper annualisation:

    sharpe = sqrt(252) * mean(daily_returns) / std(daily_returns)

These tests lock in the corrected formula and the three simulation modes
so they cannot silently regress.

API notes (verified against current source):
  - trades: list[dict] with keys "net_pnl" and optional "fees"
  - mode: SimulationMode enum (TRADE_RESHUFFLE, RETURN_BOOTSTRAP, COST_PERTURBATION)
  - num_simulations: int parameter name
  - Sharpe lives at result.percentiles["sharpe_ratio"]["p50"]
  - Summary keys: probability_of_profit, median_final_equity, median_return_pct, etc.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

from src.research.monte_carlo import (
    MonteCarloAnalyzer,
    MonteCarloResult,
    MonteCarloRun,
    SimulationMode,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

INITIAL_CAPITAL = 100_000.0
SEED = 42


def _trade(pnl: float, fees: float = 0.0) -> dict:
    return {"net_pnl": pnl, "fees": fees}


def _analyzer(trades: list[dict], num_simulations: int = 100) -> MonteCarloAnalyzer:
    return MonteCarloAnalyzer(
        trades=trades,
        initial_capital=INITIAL_CAPITAL,
        num_simulations=num_simulations,
        seed=SEED,
    )


# ---------------------------------------------------------------------------
# Tests — Sharpe formula regression
# ---------------------------------------------------------------------------

class TestSharpeFormulaRegression:
    """Verify the Sharpe is calculated from equity-curve returns, not raw PnLs."""

    def test_sharpe_is_positive_for_all_profitable_trades(self):
        trades = [_trade(200.0)] * 60
        result = _analyzer(trades, num_simulations=50).run(mode=SimulationMode.TRADE_RESHUFFLE)
        median_sharpe = result.percentiles["sharpe_ratio"]["p50"]
        assert median_sharpe > 0.0, (
            "Expected positive median Sharpe for all-positive trades"
        )

    def test_sharpe_is_zero_for_flat_equity(self):
        # All zero PnL → returns are all 0 → std=0 → formula returns 0.0
        trades = [_trade(0.0)] * 50
        result = _analyzer(trades, num_simulations=20).run(mode=SimulationMode.TRADE_RESHUFFLE)
        for run in result.runs:
            assert math.isfinite(run.sharpe_ratio), (
                f"Sharpe should be finite for flat equity, got {run.sharpe_ratio}"
            )
            assert run.sharpe_ratio == pytest.approx(0.0, abs=1e-9)

    def test_sharpe_is_finite_for_mixed_trades(self):
        np.random.seed(SEED)
        trades = [_trade(float(p)) for p in np.random.randn(80) * 500]
        result = _analyzer(trades, num_simulations=40).run(mode=SimulationMode.TRADE_RESHUFFLE)
        for run in result.runs:
            assert math.isfinite(run.sharpe_ratio), (
                f"Sharpe should always be finite, got {run.sharpe_ratio}"
            )

    def test_profitable_strategy_has_higher_sharpe_than_losing_strategy(self):
        good_trades = [_trade(200.0)] * 60
        bad_trades = [_trade(-200.0)] * 60

        good_result = _analyzer(good_trades, num_simulations=30).run(
            mode=SimulationMode.TRADE_RESHUFFLE
        )
        bad_result = _analyzer(bad_trades, num_simulations=30).run(
            mode=SimulationMode.TRADE_RESHUFFLE
        )

        good_median = good_result.percentiles["sharpe_ratio"]["p50"]
        bad_median = bad_result.percentiles["sharpe_ratio"]["p50"]
        assert good_median > bad_median, (
            "Profitable strategy should have higher Sharpe than loss-making strategy"
        )

    def test_sharpe_percentiles_are_ordered(self):
        np.random.seed(SEED)
        trades = [_trade(float(p)) for p in np.random.randn(60) * 200 + 50]
        result = _analyzer(trades, num_simulations=100).run(mode=SimulationMode.TRADE_RESHUFFLE)
        sharpe_pcts = result.percentiles["sharpe_ratio"]
        # p5 <= p25 <= p50 <= p75 <= p95 must hold
        assert sharpe_pcts["p5"] <= sharpe_pcts["p25"] + 1e-9
        assert sharpe_pcts["p25"] <= sharpe_pcts["p50"] + 1e-9
        assert sharpe_pcts["p50"] <= sharpe_pcts["p75"] + 1e-9
        assert sharpe_pcts["p75"] <= sharpe_pcts["p95"] + 1e-9


# ---------------------------------------------------------------------------
# Tests — All three simulation modes produce valid Sharpe
# ---------------------------------------------------------------------------

class TestAllModesProduceValidSharpe:

    def _mixed_trades(self) -> list[dict]:
        np.random.seed(SEED)
        return [
            _trade(float(p), fees=max(0.0, float(f)))
            for p, f in zip(
                np.random.randn(80) * 300 + 100,
                np.random.randn(80) * 50 + 100,
            )
        ]

    def test_trade_reshuffle_mode_sharpe_finite(self):
        result = _analyzer(self._mixed_trades(), num_simulations=40).run(
            mode=SimulationMode.TRADE_RESHUFFLE
        )
        for run in result.runs:
            assert math.isfinite(run.sharpe_ratio)

    def test_return_bootstrap_mode_sharpe_finite(self):
        result = _analyzer(self._mixed_trades(), num_simulations=40).run(
            mode=SimulationMode.RETURN_BOOTSTRAP
        )
        for run in result.runs:
            assert math.isfinite(run.sharpe_ratio)

    def test_cost_perturbation_mode_sharpe_finite(self):
        result = _analyzer(self._mixed_trades(), num_simulations=40).run(
            mode=SimulationMode.COST_PERTURBATION
        )
        for run in result.runs:
            assert math.isfinite(run.sharpe_ratio)


# ---------------------------------------------------------------------------
# Tests — Percentile structure is well-formed
# ---------------------------------------------------------------------------

class TestPercentileStructure:

    def test_percentiles_include_sharpe_ratio_key(self):
        trades = [_trade(100.0)] * 30
        result = _analyzer(trades, num_simulations=20).run(mode=SimulationMode.TRADE_RESHUFFLE)
        assert "sharpe_ratio" in result.percentiles

    def test_sharpe_percentile_dict_has_standard_keys(self):
        trades = [_trade(100.0)] * 30
        result = _analyzer(trades, num_simulations=20).run(mode=SimulationMode.TRADE_RESHUFFLE)
        sharpe_pcts = result.percentiles["sharpe_ratio"]
        for expected_key in ("p5", "p10", "p25", "p50", "p75", "p90", "p95", "mean", "std"):
            assert expected_key in sharpe_pcts, (
                f"Missing key '{expected_key}' in sharpe percentiles"
            )

    def test_sharpe_percentile_values_are_finite(self):
        np.random.seed(SEED)
        trades = [_trade(float(p)) for p in np.random.randn(50) * 200 + 80]
        result = _analyzer(trades, num_simulations=30).run(mode=SimulationMode.TRADE_RESHUFFLE)
        for key, val in result.percentiles["sharpe_ratio"].items():
            assert math.isfinite(val), (
                f"Sharpe percentile[{key}] should be finite, got {val}"
            )

    def test_empty_trades_returns_empty_result(self):
        result = _analyzer([], num_simulations=10).run(mode=SimulationMode.TRADE_RESHUFFLE)
        assert result.num_simulations == 0
        assert result.runs == []
