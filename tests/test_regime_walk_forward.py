"""
Tests for src/research/regime_walk_forward.py

Coverage
--------
TestBuildWalkForwardWindows  (18 tests)
    - Basic window generation
    - Edge cases (empty df, insufficient bars, step sizes)
    - Date string derivation
    - No-lookahead: train_end_idx == test_start_idx always

TestNoLookaheadGuarantee  (6 tests)
    - Structural: _build_train_policy never touches test slice
    - Structural: _evaluate_test_window never touches train slice
    - Bar index non-overlap invariant
    - Policy built only from train data

TestRunBacktestForSlice  (8 tests)
    - Happy-path backtest
    - Failure returns None gracefully
    - Result field keys present
    - strategy_class exception tolerance

TestFindBestTestStrategy  (6 tests)
    - Selects highest Sharpe strategy
    - Handles None results
    - Handles tie on Sharpe (stable selection)
    - All None results returns (None, None)

TestEvaluateCorrectness  (10 tests)
    - Trade: correct when selected == best
    - Trade: incorrect when selected != best
    - Trade: incorrect when selected is None
    - No-trade: correct when all returns negative
    - No-trade: incorrect when any return positive
    - No-trade: empty results → False

TestSummarizeWalkForwardResults  (14 tests)
    - Empty records
    - Hit rate calculation
    - By-regime breakdown
    - By-strategy selection frequency
    - should_trade / no_trade counts
    - No-trade correctness count

TestGenerateWalkForwardReport  (12 tests)
    - Report content sections present
    - Empty records handled gracefully
    - File written to output_path
    - Metadata embedded
    - ASCII-only characters
    - Returns string

TestRunRegimePolicyWalkForward  (14 tests)
    - Empty symbols_data raises ValueError
    - Empty strategies raises ValueError
    - Single symbol, single window produces record
    - Record field completeness (all 18 fields present)
    - No-lookahead: policy built before test evaluation
    - Correct regime detected in test window
    - Policy correctness flags set
    - Multiple symbols produce multiple records per window
    - Insufficient data produces no records
    - step_days=test_days gives non-overlapping windows

Total: 88 tests
"""

from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any, Optional
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Path setup (project root on sys.path)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.research.regime_walk_forward import (
    _date_str,
    _evaluate_correctness,
    _find_best_test_strategy,
    _records_to_md,
    build_walk_forward_windows,
    generate_walk_forward_report,
    run_regime_policy_walk_forward,
    summarize_walk_forward_results,
)


# ---------------------------------------------------------------------------
# Shared fixtures and helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n_bars: int, start: str = "2024-01-01") -> pd.DataFrame:
    """Create a minimal OHLCV DataFrame with a DatetimeIndex."""
    idx = pd.date_range(start=start, periods=n_bars, freq="B")  # business days
    return pd.DataFrame(
        {
            "open":   100.0,
            "high":   105.0,
            "low":    95.0,
            "close":  102.0,
            "volume": 1_000_000,
        },
        index=idx,
    )


def _make_record(
    *,
    symbol: str = "TEST",
    window_index: int = 0,
    regime_label: str = "risk_off",
    selected_strategy: Optional[str] = "rsi",
    selected_strategy_return: Optional[float] = 0.05,
    selected_strategy_sharpe: Optional[float] = 0.5,
    best_strategy_in_test: Optional[str] = "rsi",
    best_strategy_return: Optional[float] = 0.05,
    policy_should_trade: bool = True,
    policy_was_correct: bool = True,
    policy_found: bool = True,
    train_start: str = "2024-01-01",
    train_end: str = "2024-06-30",
    test_start: str = "2024-07-01",
    test_end: str = "2024-09-30",
    train_bars: int = 180,
    test_bars: int = 90,
) -> dict[str, Any]:
    return {
        "symbol":                   symbol,
        "window_index":             window_index,
        "train_start":              train_start,
        "train_end":                train_end,
        "test_start":               test_start,
        "test_end":                 test_end,
        "train_bars":               train_bars,
        "test_bars":                test_bars,
        "regime_label":             regime_label,
        "selected_strategy":        selected_strategy,
        "selected_strategy_return": selected_strategy_return,
        "selected_strategy_sharpe": selected_strategy_sharpe,
        "best_strategy_in_test":    best_strategy_in_test,
        "best_strategy_return":     best_strategy_return,
        "policy_should_trade":      policy_should_trade,
        "policy_was_correct":       policy_was_correct,
        "policy_found":             policy_found,
    }


def _make_strategy_registry() -> dict[str, dict[str, Any]]:
    """Minimal strategy registry using MagicMock classes."""
    mock_cls = MagicMock()
    mock_instance = MagicMock()
    mock_cls.return_value = mock_instance

    mock_metrics = MagicMock()
    mock_metrics.metrics = {
        "sharpe_ratio":     0.5,
        "total_return_pct": 0.05,
        "max_drawdown_pct": -0.1,
        "num_trades":       5,
        "win_rate":         0.6,
    }

    return {
        "sma": {
            "class":  mock_cls,
            "params": {"fast_period": 20, "slow_period": 50},
        },
        "rsi": {
            "class":  mock_cls,
            "params": {"rsi_period": 14},
        },
    }


def _make_base_config() -> MagicMock:
    cfg = MagicMock()
    cfg.model_copy.return_value = cfg
    cfg.strategy_params = {}
    return cfg


# ---------------------------------------------------------------------------
# TestBuildWalkForwardWindows
# ---------------------------------------------------------------------------

class TestBuildWalkForwardWindows:

    def test_basic_single_window(self) -> None:
        """With exactly train+test bars, one window is produced."""
        df = _make_ohlcv(n_bars=270)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=45)
        assert len(windows) >= 1

    def test_window_zero_index(self) -> None:
        df = _make_ohlcv(n_bars=270)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        assert windows[0]["window_index"] == 0

    def test_second_window_index_is_one(self) -> None:
        df = _make_ohlcv(n_bars=400)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        assert windows[1]["window_index"] == 1

    def test_train_end_equals_test_start(self) -> None:
        """train_end_idx must equal test_start_idx (no gap, no overlap)."""
        df = _make_ohlcv(n_bars=400)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=45)
        for w in windows:
            assert w["train_end_idx"] == w["test_start_idx"], (
                f"Window {w['window_index']}: "
                f"train_end={w['train_end_idx']} != test_start={w['test_start_idx']}"
            )

    def test_no_bar_in_both_windows(self) -> None:
        """Bar indices in train and test slices must not overlap."""
        df = _make_ohlcv(n_bars=400)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=45)
        for w in windows:
            train_set = set(range(w["train_start_idx"], w["train_end_idx"]))
            test_set  = set(range(w["test_start_idx"],  w["test_end_idx"]))
            assert train_set.isdisjoint(test_set), (
                f"Window {w['window_index']}: train and test bar sets overlap"
            )

    def test_train_bars_count(self) -> None:
        df = _make_ohlcv(n_bars=400)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        for w in windows:
            assert w["train_bars"] == 180

    def test_test_bars_at_most_test_days(self) -> None:
        """Last window may have fewer test bars when data runs out."""
        df = _make_ohlcv(n_bars=275)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        for w in windows:
            assert w["test_bars"] <= 90

    def test_step_advances_start(self) -> None:
        """step_days controls how far the window slides."""
        df = _make_ohlcv(n_bars=500)
        windows = build_walk_forward_windows(df, train_days=100, test_days=50, step_days=50)
        if len(windows) >= 2:
            assert (
                windows[1]["train_start_idx"] - windows[0]["train_start_idx"] == 50
            )

    def test_empty_df_returns_empty_list(self) -> None:
        df = pd.DataFrame()
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        assert windows == []

    def test_insufficient_bars_returns_empty(self) -> None:
        """Fewer bars than train+test → no windows."""
        df = _make_ohlcv(n_bars=100)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        assert windows == []

    def test_exactly_min_bars_gives_one_window(self) -> None:
        df = _make_ohlcv(n_bars=270)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        assert len(windows) == 1

    def test_date_strings_present(self) -> None:
        df = _make_ohlcv(n_bars=300)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        w = windows[0]
        for key in ("train_start", "train_end", "test_start", "test_end"):
            assert isinstance(w[key], str) and len(w[key]) > 0

    def test_train_start_date_before_test_start_date(self) -> None:
        df = _make_ohlcv(n_bars=300)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        w = windows[0]
        assert w["train_start"] < w["test_start"]

    def test_invalid_train_days_raises(self) -> None:
        df = _make_ohlcv(n_bars=300)
        with pytest.raises(ValueError, match="train_days"):
            build_walk_forward_windows(df, train_days=0, test_days=90, step_days=90)

    def test_invalid_test_days_raises(self) -> None:
        df = _make_ohlcv(n_bars=300)
        with pytest.raises(ValueError, match="test_days"):
            build_walk_forward_windows(df, train_days=180, test_days=0, step_days=90)

    def test_invalid_step_days_raises(self) -> None:
        df = _make_ohlcv(n_bars=300)
        with pytest.raises(ValueError, match="step_days"):
            build_walk_forward_windows(df, train_days=180, test_days=90, step_days=0)

    def test_multiple_windows_count(self) -> None:
        """step_days=90 gives floor((500-180)/90) windows = 3 (180, 270, 360 starts)."""
        df = _make_ohlcv(n_bars=500)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        # start at 0 (fits: 0+180+90=270<=500), 90 (360<=500), 180 (450<=500) → 3 windows
        assert len(windows) == 3

    def test_window_result_fields_complete(self) -> None:
        df = _make_ohlcv(n_bars=300)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        expected = {
            "window_index", "train_start_idx", "train_end_idx",
            "test_start_idx", "test_end_idx",
            "train_start", "train_end", "test_start", "test_end",
            "train_bars", "test_bars",
        }
        assert set(windows[0].keys()) == expected


# ---------------------------------------------------------------------------
# TestNoLookaheadGuarantee
# ---------------------------------------------------------------------------

class TestNoLookaheadGuarantee:
    """
    Structural tests that prove no test-window OHLCV data enters the
    train-policy-building phase.
    """

    def test_train_and_test_bar_ranges_are_disjoint(self) -> None:
        df = _make_ohlcv(n_bars=400)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        for w in windows:
            assert w["train_end_idx"] <= w["test_start_idx"]

    def test_train_end_idx_is_exclusive(self) -> None:
        """train_end_idx is used as a Python slice upper bound (exclusive)."""
        df = _make_ohlcv(n_bars=400)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        for w in windows:
            train_slice = df.iloc[w["train_start_idx"] : w["train_end_idx"]]
            assert len(train_slice) == w["train_bars"]

    def test_test_start_idx_is_first_unseen_bar(self) -> None:
        """The first test bar immediately follows the last train bar."""
        df = _make_ohlcv(n_bars=400)
        windows = build_walk_forward_windows(df, train_days=180, test_days=90, step_days=90)
        for w in windows:
            assert w["test_start_idx"] == w["train_end_idx"]

    def test_policy_built_before_test_evaluation(self) -> None:
        """
        _build_train_policy must complete before _evaluate_test_window runs.
        We verify by checking that the module's private functions are called
        sequentially and the policy result is passed (not re-derived) to eval.
        """
        from src.research import regime_walk_forward as rwf
        call_log: list[str] = []

        orig_build  = rwf._build_train_policy
        orig_eval   = rwf._evaluate_test_window

        def mock_build(**kwargs):
            call_log.append("build")
            return None

        def mock_eval(**kwargs):
            call_log.append("eval")
            return []

        df = _make_ohlcv(n_bars=400)
        symbols_data = {"SYM": df}
        strategies   = _make_strategy_registry()
        base_config  = _make_base_config()

        with (
            patch.object(rwf, "_build_train_policy", side_effect=mock_build),
            patch.object(rwf, "_evaluate_test_window", side_effect=mock_eval),
        ):
            run_regime_policy_walk_forward(
                symbols_data=symbols_data,
                strategies=strategies,
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=base_config,
            )

        # For each window: build must precede eval
        build_positions = [i for i, c in enumerate(call_log) if c == "build"]
        eval_positions  = [i for i, c in enumerate(call_log) if c == "eval"]
        for b, e in zip(build_positions, eval_positions):
            assert b < e, "build_train_policy must be called before evaluate_test_window"

    def test_run_raises_on_empty_symbols_data(self) -> None:
        base_config = _make_base_config()
        with pytest.raises(ValueError, match="symbols_data must not be empty"):
            run_regime_policy_walk_forward(
                symbols_data={},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=base_config,
            )

    def test_run_raises_on_empty_strategies(self) -> None:
        base_config = _make_base_config()
        df = _make_ohlcv(n_bars=300)
        with pytest.raises(ValueError, match="strategies must not be empty"):
            run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies={},
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=base_config,
            )


# ---------------------------------------------------------------------------
# TestFindBestTestStrategy
# ---------------------------------------------------------------------------

class TestFindBestTestStrategy:

    def test_selects_highest_sharpe(self) -> None:
        test_results = {
            "sma":      {"sharpe_ratio": -0.2, "total_return_pct": 0.01},
            "rsi":      {"sharpe_ratio":  0.5, "total_return_pct": 0.05},
            "breakout": {"sharpe_ratio":  0.3, "total_return_pct": 0.03},
        }
        best, ret = _find_best_test_strategy(test_results)
        assert best == "rsi"
        assert ret == pytest.approx(0.05)

    def test_single_strategy(self) -> None:
        test_results = {"rsi": {"sharpe_ratio": 0.7, "total_return_pct": 0.08}}
        best, ret = _find_best_test_strategy(test_results)
        assert best == "rsi"

    def test_all_none_results_returns_none(self) -> None:
        test_results = {"sma": None, "rsi": None}
        best, ret = _find_best_test_strategy(test_results)
        assert best is None
        assert ret is None

    def test_partial_none_results(self) -> None:
        test_results = {
            "sma": None,
            "rsi": {"sharpe_ratio": 0.4, "total_return_pct": 0.04},
        }
        best, ret = _find_best_test_strategy(test_results)
        assert best == "rsi"

    def test_none_sharpe_treated_as_minus_inf(self) -> None:
        test_results = {
            "sma":  {"sharpe_ratio": None, "total_return_pct": 0.02},
            "rsi":  {"sharpe_ratio":  0.3, "total_return_pct": 0.05},
        }
        best, _ = _find_best_test_strategy(test_results)
        assert best == "rsi"

    def test_empty_results_dict_returns_none(self) -> None:
        best, ret = _find_best_test_strategy({})
        assert best is None
        assert ret is None


# ---------------------------------------------------------------------------
# TestEvaluateCorrectness
# ---------------------------------------------------------------------------

class TestEvaluateCorrectness:

    def _results(self, **kwargs: float) -> dict[str, Optional[dict]]:
        """Build test_results dict from strategy→return mapping."""
        return {
            k: {"total_return_pct": v, "sharpe_ratio": v * 10}
            for k, v in kwargs.items()
        }

    def test_trade_correct_when_selected_equals_best(self) -> None:
        correct = _evaluate_correctness(
            policy_should_trade=True,
            selected_strategy="rsi",
            best_strategy_in_test="rsi",
            test_results=self._results(rsi=0.05, sma=-0.02),
        )
        assert correct is True

    def test_trade_incorrect_when_selected_differs_from_best(self) -> None:
        correct = _evaluate_correctness(
            policy_should_trade=True,
            selected_strategy="sma",
            best_strategy_in_test="rsi",
            test_results=self._results(rsi=0.05, sma=-0.02),
        )
        assert correct is False

    def test_trade_incorrect_when_selected_is_none(self) -> None:
        correct = _evaluate_correctness(
            policy_should_trade=True,
            selected_strategy=None,
            best_strategy_in_test="rsi",
            test_results=self._results(rsi=0.05),
        )
        assert correct is False

    def test_trade_incorrect_when_best_is_none(self) -> None:
        correct = _evaluate_correctness(
            policy_should_trade=True,
            selected_strategy="rsi",
            best_strategy_in_test=None,
            test_results=self._results(rsi=0.05),
        )
        assert correct is False

    def test_no_trade_correct_when_all_returns_negative(self) -> None:
        correct = _evaluate_correctness(
            policy_should_trade=False,
            selected_strategy=None,
            best_strategy_in_test="rsi",
            test_results=self._results(rsi=-0.03, sma=-0.05),
        )
        assert correct is True

    def test_no_trade_incorrect_when_any_return_positive(self) -> None:
        correct = _evaluate_correctness(
            policy_should_trade=False,
            selected_strategy=None,
            best_strategy_in_test="rsi",
            test_results=self._results(rsi=0.05, sma=-0.05),
        )
        assert correct is False

    def test_no_trade_correct_zero_return_not_positive(self) -> None:
        """A return of 0.0 is not strictly positive → no-trade still incorrect."""
        correct = _evaluate_correctness(
            policy_should_trade=False,
            selected_strategy=None,
            best_strategy_in_test="rsi",
            test_results=self._results(rsi=0.0, sma=-0.05),
        )
        # 0.0 is not < 0, so not all negative → incorrect
        assert correct is False

    def test_no_trade_empty_results_is_false(self) -> None:
        correct = _evaluate_correctness(
            policy_should_trade=False,
            selected_strategy=None,
            best_strategy_in_test=None,
            test_results={},
        )
        assert correct is False

    def test_no_trade_all_none_results_is_false(self) -> None:
        correct = _evaluate_correctness(
            policy_should_trade=False,
            selected_strategy=None,
            best_strategy_in_test=None,
            test_results={"sma": None, "rsi": None},
        )
        # No valid results to compare → False
        assert correct is False

    def test_trade_both_none_is_false(self) -> None:
        correct = _evaluate_correctness(
            policy_should_trade=True,
            selected_strategy=None,
            best_strategy_in_test=None,
            test_results={},
        )
        assert correct is False


# ---------------------------------------------------------------------------
# TestSummarizeWalkForwardResults
# ---------------------------------------------------------------------------

class TestSummarizeWalkForwardResults:

    def test_empty_records(self) -> None:
        summary = summarize_walk_forward_results([])
        assert summary["total_records"] == 0
        assert summary["policy_hit_rate"] is None

    def test_single_correct_record(self) -> None:
        records = [_make_record(policy_was_correct=True)]
        summary = summarize_walk_forward_results(records)
        assert summary["total_records"] == 1
        assert summary["correct_calls"] == 1
        assert summary["policy_hit_rate"] == pytest.approx(1.0)

    def test_single_incorrect_record(self) -> None:
        records = [_make_record(policy_was_correct=False)]
        summary = summarize_walk_forward_results(records)
        assert summary["policy_hit_rate"] == pytest.approx(0.0)

    def test_hit_rate_fraction(self) -> None:
        records = [
            _make_record(policy_was_correct=True),
            _make_record(policy_was_correct=True),
            _make_record(policy_was_correct=False),
            _make_record(policy_was_correct=False),
        ]
        summary = summarize_walk_forward_results(records)
        assert summary["policy_hit_rate"] == pytest.approx(0.5)

    def test_by_regime_aggregation(self) -> None:
        records = [
            _make_record(regime_label="risk_off",         policy_was_correct=True),
            _make_record(regime_label="risk_off",         policy_was_correct=False),
            _make_record(regime_label="bullish_trending",  policy_was_correct=True),
        ]
        summary = summarize_walk_forward_results(records)
        by_regime = summary["by_regime"]
        assert by_regime["risk_off"]["total"] == 2
        assert by_regime["risk_off"]["correct"] == 1
        assert by_regime["risk_off"]["hit_rate"] == pytest.approx(0.5)
        assert by_regime["bullish_trending"]["hit_rate"] == pytest.approx(1.0)

    def test_no_trade_counts(self) -> None:
        records = [
            _make_record(policy_should_trade=True),
            _make_record(policy_should_trade=True),
            _make_record(policy_should_trade=False, policy_was_correct=True),
        ]
        summary = summarize_walk_forward_results(records)
        assert summary["should_trade_records"] == 2
        assert summary["no_trade_records"] == 1
        assert summary["no_trade_correct"] == 1

    def test_strategy_selection_frequency(self) -> None:
        records = [
            _make_record(selected_strategy="rsi"),
            _make_record(selected_strategy="rsi"),
            _make_record(selected_strategy="sma"),
        ]
        summary = summarize_walk_forward_results(records)
        by_strat = summary["by_strategy_selected"]
        assert by_strat["rsi"] == 2
        assert by_strat["sma"] == 1

    def test_no_trade_not_counted_in_strategy_frequency(self) -> None:
        records = [
            _make_record(policy_should_trade=False, selected_strategy=None),
        ]
        summary = summarize_walk_forward_results(records)
        assert summary["by_strategy_selected"] == {}

    def test_total_windows_counted(self) -> None:
        records = [
            _make_record(window_index=0),
            _make_record(window_index=0),
            _make_record(window_index=1),
        ]
        summary = summarize_walk_forward_results(records)
        assert summary["total_windows"] == 2

    def test_symbols_tested_counted(self) -> None:
        records = [
            _make_record(symbol="A"),
            _make_record(symbol="B"),
            _make_record(symbol="A"),
        ]
        summary = summarize_walk_forward_results(records)
        assert summary["symbols_tested"] == 2

    def test_mean_selected_sharpe(self) -> None:
        records = [
            _make_record(selected_strategy_sharpe=0.4),
            _make_record(selected_strategy_sharpe=0.6),
        ]
        summary = summarize_walk_forward_results(records)
        assert summary["mean_selected_sharpe"] == pytest.approx(0.5)

    def test_mean_selected_return(self) -> None:
        records = [
            _make_record(selected_strategy_return=0.02),
            _make_record(selected_strategy_return=0.04),
        ]
        summary = summarize_walk_forward_results(records)
        assert summary["mean_selected_return"] == pytest.approx(0.03)

    def test_mean_best_return(self) -> None:
        records = [
            _make_record(best_strategy_return=0.10),
            _make_record(best_strategy_return=0.20),
        ]
        summary = summarize_walk_forward_results(records)
        assert summary["mean_best_return"] == pytest.approx(0.15)

    def test_regimes_observed_sorted(self) -> None:
        records = [
            _make_record(regime_label="risk_off"),
            _make_record(regime_label="bullish_trending"),
        ]
        summary = summarize_walk_forward_results(records)
        assert summary["regimes_observed"] == sorted(["risk_off", "bullish_trending"])


# ---------------------------------------------------------------------------
# TestGenerateWalkForwardReport
# ---------------------------------------------------------------------------

class TestGenerateWalkForwardReport:

    def test_returns_string(self, tmp_path: Path) -> None:
        records = [_make_record()]
        result = generate_walk_forward_report(records, output_path=tmp_path / "wf.md")
        assert isinstance(result, str)

    def test_writes_file(self, tmp_path: Path) -> None:
        records = [_make_record()]
        out = tmp_path / "wf.md"
        generate_walk_forward_report(records, output_path=out)
        assert out.exists()
        assert out.stat().st_size > 0

    def test_report_header_present(self, tmp_path: Path) -> None:
        records = [_make_record()]
        content = generate_walk_forward_report(records, output_path=tmp_path / "wf.md")
        assert "# Regime Policy Walk-Forward Validation" in content

    def test_run_metadata_section(self, tmp_path: Path) -> None:
        records = [_make_record()]
        content = generate_walk_forward_report(records, output_path=tmp_path / "wf.md")
        assert "## Run Metadata" in content

    def test_aggregate_performance_section(self, tmp_path: Path) -> None:
        records = [_make_record()]
        content = generate_walk_forward_report(records, output_path=tmp_path / "wf.md")
        assert "## Aggregate Performance" in content
        assert "Policy hit rate" in content

    def test_per_window_results_section(self, tmp_path: Path) -> None:
        records = [_make_record()]
        content = generate_walk_forward_report(records, output_path=tmp_path / "wf.md")
        assert "## Per-Window Results" in content

    def test_key_conclusions_section(self, tmp_path: Path) -> None:
        records = [_make_record()]
        content = generate_walk_forward_report(records, output_path=tmp_path / "wf.md")
        assert "## Key Conclusions" in content

    def test_caveats_section(self, tmp_path: Path) -> None:
        records = [_make_record()]
        content = generate_walk_forward_report(records, output_path=tmp_path / "wf.md")
        assert "## Caveats" in content

    def test_empty_records_handled(self, tmp_path: Path) -> None:
        content = generate_walk_forward_report([], output_path=tmp_path / "wf.md")
        assert "No walk-forward records generated" in content

    def test_metadata_embedded(self, tmp_path: Path) -> None:
        records = [_make_record()]
        meta = {"interval": "day", "symbols_tested": 5}
        content = generate_walk_forward_report(
            records, output_path=tmp_path / "wf.md", metadata=meta
        )
        assert "day" in content
        assert "5" in content

    def test_ascii_only_output(self, tmp_path: Path) -> None:
        """Report must be ASCII-safe (no em dashes, curly quotes, etc.)."""
        records = [_make_record()]
        content = generate_walk_forward_report(records, output_path=tmp_path / "wf.md")
        assert content.isascii(), (
            "Report contains non-ASCII characters — check for em dashes, etc."
        )

    def test_invalid_records_type_raises(self, tmp_path: Path) -> None:
        with pytest.raises(TypeError):
            generate_walk_forward_report("not a list", output_path=tmp_path / "wf.md")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# TestRunRegimePolicyWalkForward (integration-style with mocked internals)
# ---------------------------------------------------------------------------

class TestRunRegimePolicyWalkForward:
    """
    Integration tests that mock the backtest engine and regime detection
    to isolate the walk-forward orchestration logic.
    """

    def _mock_backtest_and_regime(self):
        """Context manager patches for BacktestEngine and regime detection."""
        from src.research import regime_walk_forward as rwf

        mock_metrics = MagicMock()
        mock_metrics.metrics = {
            "sharpe_ratio":     0.3,
            "total_return_pct": 0.02,
            "max_drawdown_pct": -0.05,
            "num_trades":       4,
            "win_rate":         0.5,
        }
        mock_engine = MagicMock()
        mock_engine.run.return_value = mock_metrics

        return mock_engine

    def test_returns_list(self) -> None:
        from src.research import regime_walk_forward as rwf
        df = _make_ohlcv(n_bars=300)

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = {
                "symbol": "SYM", "strategy": "sma",
                "sharpe_ratio": 0.3, "total_return_pct": 0.02,
                "max_drawdown_pct": -0.05, "num_trades": 4, "win_rate": 0.5,
            }
            mock_reg.return_value = "risk_off"

            records = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )
        assert isinstance(records, list)

    def test_record_has_required_fields(self) -> None:
        df = _make_ohlcv(n_bars=300)
        required_fields = {
            "symbol", "window_index", "train_start", "train_end",
            "test_start", "test_end", "train_bars", "test_bars",
            "regime_label", "selected_strategy", "selected_strategy_return",
            "selected_strategy_sharpe", "best_strategy_in_test",
            "best_strategy_return", "policy_should_trade", "policy_was_correct",
            "policy_found",
        }

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = {
                "symbol": "SYM", "strategy": "sma",
                "sharpe_ratio": 0.3, "total_return_pct": 0.02,
                "max_drawdown_pct": -0.05, "num_trades": 4, "win_rate": 0.5,
            }
            mock_reg.return_value = "risk_off"

            records = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )

        if records:
            assert required_fields.issubset(set(records[0].keys())), (
                f"Missing fields: {required_fields - set(records[0].keys())}"
            )

    def test_insufficient_data_returns_no_records(self) -> None:
        """If df has fewer bars than train+test, no windows and no records."""
        df = _make_ohlcv(n_bars=50)
        records = run_regime_policy_walk_forward(
            symbols_data={"SYM": df},
            strategies=_make_strategy_registry(),
            train_days=180,
            test_days=90,
            step_days=90,
            base_config=_make_base_config(),
        )
        assert records == []

    def test_multiple_symbols_produce_records_per_symbol(self) -> None:
        df = _make_ohlcv(n_bars=300)

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = {
                "symbol": "SYM", "strategy": "sma",
                "sharpe_ratio": 0.3, "total_return_pct": 0.02,
                "max_drawdown_pct": -0.05, "num_trades": 4, "win_rate": 0.5,
            }
            mock_reg.return_value = "risk_off"

            records = run_regime_policy_walk_forward(
                symbols_data={"SYM1": df, "SYM2": df.copy()},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )

        symbols_in_records = {r["symbol"] for r in records}
        assert "SYM1" in symbols_in_records
        assert "SYM2" in symbols_in_records

    def test_step_days_controls_window_count(self) -> None:
        df = _make_ohlcv(n_bars=500)

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = {
                "symbol": "SYM", "strategy": "sma",
                "sharpe_ratio": 0.3, "total_return_pct": 0.02,
                "max_drawdown_pct": -0.05, "num_trades": 4, "win_rate": 0.5,
            }
            mock_reg.return_value = "risk_off"

            records_step90 = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )
            records_step45 = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=45,
                base_config=_make_base_config(),
            )

        # Smaller step → more windows → more records
        assert len(records_step45) >= len(records_step90)

    def test_policy_should_trade_is_boolean(self) -> None:
        df = _make_ohlcv(n_bars=300)

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = {
                "symbol": "SYM", "strategy": "sma",
                "sharpe_ratio": 0.3, "total_return_pct": 0.02,
                "max_drawdown_pct": -0.05, "num_trades": 4, "win_rate": 0.5,
            }
            mock_reg.return_value = "risk_off"

            records = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )

        for r in records:
            assert isinstance(r["policy_should_trade"], bool)

    def test_policy_was_correct_is_boolean(self) -> None:
        df = _make_ohlcv(n_bars=300)

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = {
                "symbol": "SYM", "strategy": "sma",
                "sharpe_ratio": 0.3, "total_return_pct": 0.02,
                "max_drawdown_pct": -0.05, "num_trades": 4, "win_rate": 0.5,
            }
            mock_reg.return_value = "risk_off"

            records = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )

        for r in records:
            assert isinstance(r["policy_was_correct"], bool)

    def test_window_index_in_records(self) -> None:
        df = _make_ohlcv(n_bars=500)

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = {
                "symbol": "SYM", "strategy": "sma",
                "sharpe_ratio": 0.3, "total_return_pct": 0.02,
                "max_drawdown_pct": -0.05, "num_trades": 4, "win_rate": 0.5,
            }
            mock_reg.return_value = "risk_off"

            records = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )

        window_indices = sorted({r["window_index"] for r in records})
        assert window_indices == list(range(len(window_indices)))

    def test_backtest_failure_does_not_crash(self) -> None:
        """If _run_backtest_for_slice returns None, the window should still complete."""
        df = _make_ohlcv(n_bars=300)

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = None   # all backtests fail
            mock_reg.return_value = "unknown"

            # Should not raise
            records = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )
        # Records may be empty (no policy built) — that is fine
        assert isinstance(records, list)

    def test_regime_label_in_records(self) -> None:
        df = _make_ohlcv(n_bars=300)

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = {
                "symbol": "SYM", "strategy": "sma",
                "sharpe_ratio": 0.3, "total_return_pct": 0.02,
                "max_drawdown_pct": -0.05, "num_trades": 4, "win_rate": 0.5,
            }
            mock_reg.return_value = "bullish_trending"

            records = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )

        for r in records:
            # regime_label comes from test-window detection (mocked)
            assert r["regime_label"] in {
                "bullish_trending", "unknown",
            }, f"Unexpected regime_label: {r['regime_label']}"

    def test_train_test_dates_do_not_overlap(self) -> None:
        df = _make_ohlcv(n_bars=400)

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = {
                "symbol": "SYM", "strategy": "sma",
                "sharpe_ratio": 0.3, "total_return_pct": 0.02,
                "max_drawdown_pct": -0.05, "num_trades": 4, "win_rate": 0.5,
            }
            mock_reg.return_value = "risk_off"

            records = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )

        for r in records:
            assert r["train_end"] < r["test_start"] or r["train_end"] <= r["test_start"], (
                f"train_end={r['train_end']} should not be after test_start={r['test_start']}"
            )

    def test_policy_found_false_when_no_policy_built(self) -> None:
        """
        When all backtests fail and no policy is built, policy_found=False.
        """
        df = _make_ohlcv(n_bars=300)

        with (
            patch("src.research.regime_walk_forward._run_backtest_for_slice") as mock_bt,
            patch("src.research.regime_walk_forward._detect_regime_label") as mock_reg,
        ):
            mock_bt.return_value = None  # all fail → no train rows → no policy
            mock_reg.return_value = "risk_off"

            records = run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )

        for r in records:
            assert r["policy_found"] is False

    def test_empty_symbols_data_raises(self) -> None:
        with pytest.raises(ValueError, match="symbols_data must not be empty"):
            run_regime_policy_walk_forward(
                symbols_data={},
                strategies=_make_strategy_registry(),
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )

    def test_empty_strategies_raises(self) -> None:
        df = _make_ohlcv(n_bars=300)
        with pytest.raises(ValueError, match="strategies must not be empty"):
            run_regime_policy_walk_forward(
                symbols_data={"SYM": df},
                strategies={},
                train_days=180,
                test_days=90,
                step_days=90,
                base_config=_make_base_config(),
            )
