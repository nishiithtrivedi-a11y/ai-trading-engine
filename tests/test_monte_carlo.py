"""Tests for Monte Carlo robustness analysis (Step 10)."""

import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from src.research.monte_carlo import (
    MonteCarloAnalyzer,
    MonteCarloResult,
    MonteCarloRun,
    SimulationMode,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_trade_records(num_trades: int = 20, seed: int = 42) -> list[dict[str, Any]]:
    """Generate synthetic trade records matching backtest output format."""
    rng = np.random.default_rng(seed)
    trades = []
    for i in range(num_trades):
        net_pnl = rng.normal(50, 200)  # Mean positive, high variance
        fees = abs(rng.normal(5, 2))
        trades.append({
            "net_pnl": float(net_pnl),
            "return_pct": float(net_pnl / 100_000),
            "fees": float(fees),
            "gross_pnl": float(net_pnl + fees),
            "side": "long",
        })
    return trades


# ---------------------------------------------------------------------------
# Tests — MonteCarloRun
# ---------------------------------------------------------------------------

class TestMonteCarloRun:

    def test_to_dict(self):
        run = MonteCarloRun(
            run_index=0,
            mode="trade_reshuffle",
            final_equity=105_000.0,
            total_return_pct=0.05,
            max_drawdown_pct=0.02,
            sharpe_ratio=1.5,
            num_trades=20,
        )
        d = run.to_dict()
        assert d["run_index"] == 0
        assert d["final_equity"] == pytest.approx(105_000.0)
        assert d["mode"] == "trade_reshuffle"


# ---------------------------------------------------------------------------
# Tests — MonteCarloResult
# ---------------------------------------------------------------------------

class TestMonteCarloResult:

    def test_empty_result(self):
        r = MonteCarloResult(
            mode="trade_reshuffle",
            num_simulations=0,
            initial_capital=100_000.0,
        )
        assert r.to_dataframe().empty
        assert r.to_dict()["num_simulations"] == 0

    def test_to_dataframe_with_runs(self):
        run = MonteCarloRun(
            run_index=0,
            mode="trade_reshuffle",
            final_equity=105_000.0,
            total_return_pct=0.05,
            max_drawdown_pct=0.02,
            sharpe_ratio=1.5,
            num_trades=20,
        )
        r = MonteCarloResult(
            mode="trade_reshuffle",
            num_simulations=1,
            initial_capital=100_000.0,
            runs=[run],
        )
        df = r.to_dataframe()
        assert len(df) == 1
        assert "final_equity" in df.columns


# ---------------------------------------------------------------------------
# Tests — MonteCarloAnalyzer validation
# ---------------------------------------------------------------------------

class TestMonteCarloAnalyzerValidation:

    def test_invalid_capital(self):
        with pytest.raises(ValueError, match="initial_capital"):
            MonteCarloAnalyzer(trades=[], initial_capital=0)

    def test_invalid_num_simulations(self):
        with pytest.raises(ValueError, match="num_simulations"):
            MonteCarloAnalyzer(trades=[], num_simulations=0)

    def test_empty_trades_returns_empty_result(self, tmp_path):
        analyzer = MonteCarloAnalyzer(
            trades=[],
            initial_capital=100_000,
            num_simulations=100,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.TRADE_RESHUFFLE)
        assert result.num_simulations == 0
        assert result.runs == []

    def test_sharpe_formula_matches_expected_trade_pnl_standardization(self, tmp_path):
        trades = [{"net_pnl": 0.0, "return_pct": 0.0, "fees": 0.0}]
        analyzer = MonteCarloAnalyzer(
            trades=trades,
            initial_capital=100_000,
            num_simulations=1,
            seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        run = analyzer._build_run_from_pnls(  # noqa: SLF001
            run_index=0,
            pnls=np.array([100.0, 200.0, 300.0], dtype=float),
            mode=SimulationMode.TRADE_RESHUFFLE,
        )

        equity = np.array([100_000.0, 100_100.0, 100_300.0, 100_600.0], dtype=float)
        returns = equity[1:] / equity[:-1] - 1.0
        expected = float((np.mean(returns) / np.std(returns)) * np.sqrt(252.0))
        assert run.sharpe_ratio == pytest.approx(expected)


# ---------------------------------------------------------------------------
# Tests — Trade reshuffle mode
# ---------------------------------------------------------------------------

class TestTradeReshuffle:

    def test_basic_run(self, tmp_path):
        trades = _make_trade_records(20)
        analyzer = MonteCarloAnalyzer(
            trades=trades,
            initial_capital=100_000,
            num_simulations=100,
            seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.TRADE_RESHUFFLE)

        assert result.mode == "trade_reshuffle"
        assert result.num_simulations == 100
        assert len(result.runs) == 100

        # Each run should have the same number of trades
        for run in result.runs:
            assert run.num_trades == 20

    def test_deterministic_with_seed(self, tmp_path):
        trades = _make_trade_records(20)

        r1 = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=50, seed=123,
            output_dir=str(tmp_path / "mc1"),
        ).run(SimulationMode.TRADE_RESHUFFLE)

        r2 = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=50, seed=123,
            output_dir=str(tmp_path / "mc2"),
        ).run(SimulationMode.TRADE_RESHUFFLE)

        for a, b in zip(r1.runs, r2.runs):
            assert a.final_equity == pytest.approx(b.final_equity)

    def test_different_seeds_give_different_results(self, tmp_path):
        """Different seeds should produce different drawdown paths even
        though reshuffle mode conserves total PnL (and thus final equity)."""
        trades = _make_trade_records(20)

        r1 = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=50, seed=1,
            output_dir=str(tmp_path / "mc1"),
        ).run(SimulationMode.TRADE_RESHUFFLE)

        r2 = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=50, seed=999,
            output_dir=str(tmp_path / "mc2"),
        ).run(SimulationMode.TRADE_RESHUFFLE)

        # Max drawdown differs across reshuffles (trade order changes path)
        differ = any(
            a.max_drawdown_pct != pytest.approx(b.max_drawdown_pct)
            for a, b in zip(r1.runs, r2.runs)
        )
        assert differ

    def test_total_pnl_conserved(self, tmp_path):
        """All reshuffles should produce the same total PnL (just reordered)."""
        trades = _make_trade_records(15)
        total_pnl = sum(t["net_pnl"] for t in trades)
        expected_final = 100_000 + total_pnl

        analyzer = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=50, seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.TRADE_RESHUFFLE)

        for run in result.runs:
            assert run.final_equity == pytest.approx(expected_final, rel=1e-8)


# ---------------------------------------------------------------------------
# Tests — Return bootstrap mode
# ---------------------------------------------------------------------------

class TestReturnBootstrap:

    def test_basic_run(self, tmp_path):
        trades = _make_trade_records(20)
        analyzer = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=100, seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.RETURN_BOOTSTRAP)

        assert result.mode == "return_bootstrap"
        assert len(result.runs) == 100

    def test_bootstrap_can_produce_varied_outcomes(self, tmp_path):
        """Bootstrap should produce different final equities since it
        samples with replacement."""
        trades = _make_trade_records(20)
        analyzer = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=100, seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.RETURN_BOOTSTRAP)

        finals = [r.final_equity for r in result.runs]
        # Should have variation
        assert max(finals) != pytest.approx(min(finals))


# ---------------------------------------------------------------------------
# Tests — Cost perturbation mode
# ---------------------------------------------------------------------------

class TestCostPerturbation:

    def test_basic_run(self, tmp_path):
        trades = _make_trade_records(20)
        analyzer = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=100, seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.COST_PERTURBATION)

        assert result.mode == "cost_perturbation"
        assert len(result.runs) == 100

    def test_cost_perturbation_produces_variation(self, tmp_path):
        trades = _make_trade_records(20)
        analyzer = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=100, seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.COST_PERTURBATION)

        finals = [r.final_equity for r in result.runs]
        assert max(finals) != pytest.approx(min(finals))


# ---------------------------------------------------------------------------
# Tests — Percentiles and summary
# ---------------------------------------------------------------------------

class TestPercentilesAndSummary:

    def test_percentiles_computed(self, tmp_path):
        trades = _make_trade_records(20)
        analyzer = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=100, seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.TRADE_RESHUFFLE)

        assert "final_equity" in result.percentiles
        assert "total_return_pct" in result.percentiles
        assert "max_drawdown_pct" in result.percentiles
        assert "sharpe_ratio" in result.percentiles

        # Check standard percentile keys
        fe = result.percentiles["final_equity"]
        assert "p5" in fe
        assert "p50" in fe
        assert "p95" in fe
        assert "mean" in fe
        assert "std" in fe

    def test_summary_has_probability_of_profit(self, tmp_path):
        trades = _make_trade_records(20)
        analyzer = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=100, seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.TRADE_RESHUFFLE)

        assert "probability_of_profit" in result.summary
        assert 0 <= result.summary["probability_of_profit"] <= 1.0
        assert "median_final_equity" in result.summary
        assert "worst_case_final_equity" in result.summary
        assert "best_case_final_equity" in result.summary


# ---------------------------------------------------------------------------
# Tests — Exports
# ---------------------------------------------------------------------------

class TestMonteCarloExports:

    def test_csv_and_json_created(self, tmp_path):
        trades = _make_trade_records(10)
        out_dir = tmp_path / "mc_export"

        analyzer = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=50, seed=42,
            output_dir=str(out_dir),
        )
        analyzer.run(SimulationMode.TRADE_RESHUFFLE)

        assert (out_dir / "monte_carlo_results.csv").exists()
        assert (out_dir / "monte_carlo_results.json").exists()

        # Verify JSON is valid and has expected structure
        with open(out_dir / "monte_carlo_results.json") as f:
            data = json.load(f)
        assert data["mode"] == "trade_reshuffle"
        assert data["num_simulations"] == 50
        assert len(data["runs"]) == 50

    def test_get_results_returns_last_run(self, tmp_path):
        trades = _make_trade_records(10)
        analyzer = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=10, seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.TRADE_RESHUFFLE)
        assert analyzer.get_results() is result

    def test_result_dataframe_json_serializable(self, tmp_path):
        trades = _make_trade_records(10)
        analyzer = MonteCarloAnalyzer(
            trades=trades, initial_capital=100_000,
            num_simulations=10, seed=42,
            output_dir=str(tmp_path / "mc"),
        )
        result = analyzer.run(SimulationMode.TRADE_RESHUFFLE)
        df = result.to_dataframe()
        json_str = json.dumps(df.to_dict(orient="records"), default=str)
        assert isinstance(json_str, str)
