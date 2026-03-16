"""
Regime Policy Walk-Forward Validation.

Validates the regime-driven strategy selection policy out-of-sample by
repeatedly:

  1. Slicing each symbol's full OHLCV DataFrame into a TRAIN window.
  2. Running all strategies on all symbols' train slices; detecting each
     symbol's regime from train data; building a **frozen** RegimePolicy.
  3. Slicing each symbol's full DataFrame into a TEST window (strictly
     after train_end — no bar appears in both windows).
  4. Running all strategies on all symbols' test slices; detecting each
     symbol's regime from test data; applying the frozen policy to select
     a strategy; comparing the selection to the actual best strategy.

NO-LOOKAHEAD GUARANTEE
-----------------------
  * The frozen policy is built exclusively from train-window OHLCV data.
  * Test-window OHLCV is never examined until after the policy is frozen.
  * This is enforced structurally: ``_build_train_policy()`` and
    ``_evaluate_test_window()`` are separate functions; no data crosses
    the boundary.

RELATIONSHIP TO walk_forward.py
---------------------------------
  * ``WalkForwardTester`` (walk_forward.py) validates strategy *parameters*
    using StrategyOptimizer grid-search.
  * This module validates the *regime-driven strategy selection policy*:
    given a detected regime, does the policy pick the right strategy?

RECORD FIELDS (per (symbol, window) pair)
------------------------------------------
  symbol                   : str        — symbol processed
  window_index             : int        — 0-based rolling window index
  train_start              : str        — ISO date of first training bar
  train_end                : str        — ISO date of last training bar
  test_start               : str        — ISO date of first test bar
  test_end                 : str        — ISO date of last test bar
  train_bars               : int        — bars in train slice
  test_bars                : int        — bars in test slice
  regime_label             : str        — composite regime detected from test data
  selected_strategy        : str|None   — policy's recommended strategy (None = no-trade)
  selected_strategy_return : float|None — test-window total_return_pct for selection
  selected_strategy_sharpe : float|None — test-window sharpe_ratio for selection
  best_strategy_in_test    : str|None   — strategy with highest Sharpe in test window
  best_strategy_return     : float|None — best strategy's test-window total_return_pct
  policy_should_trade      : bool       — whether policy advised trading
  policy_was_correct       : bool       — True when the policy made the correct call
  policy_found             : bool       — False when the regime had no policy entry

POLICY CORRECTNESS DEFINITION
-------------------------------
  * Trade decision (policy_should_trade=True):
    ``policy_was_correct`` = (selected_strategy == best_strategy_in_test)
  * No-trade decision (policy_should_trade=False):
    ``policy_was_correct`` = all strategies posted negative total_return_pct
    in the test window (i.e. trading truly should have been avoided).
"""

from __future__ import annotations

import copy
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import pandas as pd

from src.decision.regime_policy import (
    RegimePolicy,
    RegimePolicyBuilder,
    select_for_regime,
)
from src.research.regime_analysis import analyze_by_regime
from src.utils.logger import setup_logger

logger = setup_logger("regime_walk_forward")

# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------

# Minimum bars in a slice for a backtest to be attempted
_MIN_TRAIN_BARS: int = 30
_MIN_TEST_BARS:  int = 10


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def build_walk_forward_windows(
    df: pd.DataFrame,
    train_days: int,
    test_days: int,
    step_days: int,
) -> list[dict[str, Any]]:
    """
    Generate rolling walk-forward window boundaries from a reference DataFrame.

    Bar-index based slicing; ``train_days``, ``test_days``, and ``step_days``
    are treated as approximate bar counts (for daily OHLCV, 1 bar ≈ 1
    trading day, which is approximately equal to 1 calendar day of data).

    Parameters
    ----------
    df : pd.DataFrame
        Reference OHLCV DataFrame with a DatetimeIndex.  Used only to derive
        the total number of available bars; its data is not read here.
    train_days : int
        Number of bars in each training window.  Must be >= 1.
    test_days : int
        Number of bars in each test window.  Must be >= 1.
    step_days : int
        Number of bars to advance the window start between iterations.
        Must be >= 1.  A value equal to ``test_days`` gives non-overlapping
        test windows (standard walk-forward).

    Returns
    -------
    list[dict]
        One dict per generated window, each containing:

        ``window_index``    — 0-based integer index
        ``train_start_idx`` — inclusive bar index of train start
        ``train_end_idx``   — exclusive bar index of train end
        ``test_start_idx``  — inclusive bar index of test start
        ``test_end_idx``    — exclusive bar index of test end
        ``train_start``     — ISO date string of first training bar
        ``train_end``       — ISO date string of last training bar
        ``test_start``      — ISO date string of first test bar
        ``test_end``        — ISO date string of last test bar
        ``train_bars``      — actual bars in train slice
        ``test_bars``       — actual bars in test slice

    Raises
    ------
    ValueError
        If any of ``train_days``, ``test_days``, or ``step_days`` is < 1.
    """
    if train_days < 1:
        raise ValueError(f"train_days must be >= 1; got {train_days}")
    if test_days < 1:
        raise ValueError(f"test_days must be >= 1; got {test_days}")
    if step_days < 1:
        raise ValueError(f"step_days must be >= 1; got {step_days}")

    if df.empty:
        return []

    total_bars = len(df)
    windows: list[dict[str, Any]] = []
    start = 0
    window_index = 0

    while start + train_days + test_days <= total_bars:
        train_start_idx = start
        train_end_idx   = start + train_days
        test_start_idx  = train_end_idx
        test_end_idx    = min(test_start_idx + test_days, total_bars)

        train_slice = df.iloc[train_start_idx:train_end_idx]
        test_slice  = df.iloc[test_start_idx:test_end_idx]

        windows.append({
            "window_index":    window_index,
            "train_start_idx": train_start_idx,
            "train_end_idx":   train_end_idx,
            "test_start_idx":  test_start_idx,
            "test_end_idx":    test_end_idx,
            "train_start":     _date_str(train_slice, first=True),
            "train_end":       _date_str(train_slice, first=False),
            "test_start":      _date_str(test_slice,  first=True),
            "test_end":        _date_str(test_slice,  first=False),
            "train_bars":      len(train_slice),
            "test_bars":       len(test_slice),
        })
        start        += step_days
        window_index += 1

    return windows


def run_regime_policy_walk_forward(
    symbols_data: dict[str, pd.DataFrame],
    strategies: dict[str, dict[str, Any]],
    train_days: int,
    test_days: int,
    step_days: int,
    base_config: Any,
) -> list[dict[str, Any]]:
    """
    Run regime policy walk-forward validation across all symbols and windows.

    For each rolling window the function:

    1. Builds a **frozen** :class:`~src.decision.regime_policy.RegimePolicy`
       from all symbols' train-slice backtest results.  Regime labels are
       detected from each symbol's *train* OHLCV data only.
    2. Evaluates the frozen policy on each symbol's *test* slice, detecting
       the test-window regime and comparing the policy's strategy selection
       to the actual best-performing strategy in that window.

    Parameters
    ----------
    symbols_data : dict[str, pd.DataFrame]
        Pre-fetched OHLCV DataFrames keyed by symbol name.  All DataFrames
        must cover at least ``train_days + test_days`` bars.
    strategies : dict[str, dict]
        Strategy registry mapping short name → ``{class, params}`` dicts,
        as returned by ``build_strategy_registry()`` in the research runner.
    train_days : int
        Number of bars per training window.
    test_days : int
        Number of bars per test window.
    step_days : int
        Bar advance between windows (``test_days`` gives non-overlapping
        test windows).
    base_config : BacktestConfig
        Shared backtest configuration cloned per-run; never mutated.

    Returns
    -------
    list[dict]
        Per-(symbol, window) records.  See module docstring for field list.

    Raises
    ------
    ValueError
        If ``symbols_data`` or ``strategies`` is empty.
    """
    if not symbols_data:
        raise ValueError("symbols_data must not be empty")
    if not strategies:
        raise ValueError("strategies must not be empty")

    # Use the first symbol as the window reference (all symbols cover the same
    # date range when fetched from the runner; bar counts may differ slightly).
    reference_df = next(iter(symbols_data.values()))
    windows = build_walk_forward_windows(reference_df, train_days, test_days, step_days)

    if not windows:
        logger.warning(
            "No walk-forward windows generated: "
            f"total_bars={len(reference_df)}, "
            f"train_days={train_days}, test_days={test_days}. "
            "Ensure total data >= train_days + test_days."
        )
        return []

    strategy_names = list(strategies.keys())
    all_records: list[dict[str, Any]] = []

    logger.info(
        f"Walk-forward: {len(windows)} window(s), "
        f"{len(symbols_data)} symbol(s), "
        f"train={train_days}, test={test_days}, step={step_days}"
    )

    for win in windows:
        win_idx = win["window_index"]
        logger.info(
            f"Window {win_idx}: "
            f"train [{win['train_start']} .. {win['train_end']}] "
            f"| test [{win['test_start']} .. {win['test_end']}]"
        )

        # ------------------------------------------------------------------ #
        # PHASE 1 — BUILD TRAIN POLICY (strictly no lookahead)
        #
        # For each symbol, slice its DataFrame to the train window, run all
        # strategies, detect regime from the train slice, and tag each result
        # row.  Then aggregate all symbols' train rows and build a frozen
        # policy.  No test-window data is touched in this phase.
        # ------------------------------------------------------------------ #
        frozen_policy = _build_train_policy(
            symbols_data=symbols_data,
            strategies=strategies,
            win=win,
            base_config=base_config,
            win_idx=win_idx,
        )

        # ------------------------------------------------------------------ #
        # PHASE 2 — EVALUATE TEST WINDOW (frozen policy only)
        #
        # For each symbol, slice its DataFrame to the test window, run all
        # strategies for comparison, detect regime from the test slice, apply
        # the frozen policy, and record results.
        # ------------------------------------------------------------------ #
        window_records = _evaluate_test_window(
            symbols_data=symbols_data,
            strategies=strategies,
            strategy_names=strategy_names,
            frozen_policy=frozen_policy,
            win=win,
            base_config=base_config,
            win_idx=win_idx,
        )
        all_records.extend(window_records)

    logger.info(
        f"Walk-forward complete: {len(windows)} window(s), "
        f"{len(symbols_data)} symbol(s), "
        f"{len(all_records)} record(s) produced"
    )
    return all_records


def summarize_walk_forward_results(
    records: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Aggregate walk-forward records into summary metrics.

    Parameters
    ----------
    records : list[dict]
        Output of :func:`run_regime_policy_walk_forward`.

    Returns
    -------
    dict containing:

    ``total_records``        — total (symbol, window) pairs
    ``total_windows``        — distinct window indices
    ``symbols_tested``       — distinct symbols
    ``correct_calls``        — records where ``policy_was_correct=True``
    ``policy_hit_rate``      — correct_calls / total_records
    ``mean_selected_sharpe`` — mean Sharpe of selected strategies (when not None)
    ``mean_selected_return`` — mean return of selected strategies
    ``mean_best_return``     — mean return of best strategies (upper bound)
    ``should_trade_records`` — records where policy said trade
    ``no_trade_records``     — records where policy said no-trade
    ``no_trade_correct``     — no-trade records that were truly correct
    ``regimes_observed``     — sorted list of distinct regime labels
    ``by_regime``            — {regime: {total, correct, hit_rate}}
    ``by_strategy_selected`` — {strategy: count selected}
    """
    if not records:
        return {
            "total_records":   0,
            "policy_hit_rate": None,
        }

    n       = len(records)
    correct = sum(1 for r in records if r.get("policy_was_correct", False))

    should_trade_count = sum(
        1 for r in records if r.get("policy_should_trade", True)
    )
    no_trade_count = n - should_trade_count
    no_trade_correct = sum(
        1 for r in records
        if (not r.get("policy_should_trade", True))
        and r.get("policy_was_correct", False)
    )

    # Float metric aggregation
    selected_sharpes = [
        r["selected_strategy_sharpe"]
        for r in records
        if r.get("selected_strategy_sharpe") is not None
    ]
    selected_returns = [
        r["selected_strategy_return"]
        for r in records
        if r.get("selected_strategy_return") is not None
    ]
    best_returns = [
        r["best_strategy_return"]
        for r in records
        if r.get("best_strategy_return") is not None
    ]

    def _safe_mean(vals: list[float]) -> Optional[float]:
        return round(sum(vals) / len(vals), 4) if vals else None

    # Per-regime breakdown
    by_regime: dict[str, dict[str, Any]] = {}
    for r in records:
        rl = r.get("regime_label", "unknown") or "unknown"
        if rl not in by_regime:
            by_regime[rl] = {"total": 0, "correct": 0}
        by_regime[rl]["total"] += 1
        if r.get("policy_was_correct"):
            by_regime[rl]["correct"] += 1
    for d in by_regime.values():
        d["hit_rate"] = (
            round(d["correct"] / d["total"], 4) if d["total"] > 0 else None
        )

    # Per-strategy selection frequency
    by_strategy: dict[str, int] = {}
    for r in records:
        ss = r.get("selected_strategy")
        if ss is not None:
            by_strategy[ss] = by_strategy.get(ss, 0) + 1

    windows_seen  = sorted({r.get("window_index", 0) for r in records})
    symbols_seen  = sorted({r.get("symbol", "")     for r in records})

    return {
        "total_records":        n,
        "total_windows":        len(windows_seen),
        "symbols_tested":       len(symbols_seen),
        "correct_calls":        correct,
        "policy_hit_rate":      round(correct / n, 4),
        "mean_selected_sharpe": _safe_mean(selected_sharpes),
        "mean_selected_return": _safe_mean(selected_returns),
        "mean_best_return":     _safe_mean(best_returns),
        "should_trade_records": should_trade_count,
        "no_trade_records":     no_trade_count,
        "no_trade_correct":     no_trade_correct,
        "regimes_observed":     sorted(by_regime.keys()),
        "by_regime":            by_regime,
        "by_strategy_selected": by_strategy,
    }


def generate_walk_forward_report(
    records: list[dict[str, Any]],
    output_path: Optional[str | Path] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """
    Generate a markdown walk-forward validation report and optionally save it.

    Sections produced:

    * Run Metadata
    * Window Configuration
    * Aggregate Performance
    * Performance by Regime
    * Strategy Selection Frequency
    * Per-Window Results (detail table)
    * Key Conclusions
    * Caveats

    Parameters
    ----------
    records : list[dict]
        Output of :func:`run_regime_policy_walk_forward`.
    output_path : str or Path, optional
        Where to save the markdown file.  Defaults to
        ``research/regime_walk_forward.md``.
    metadata : dict, optional
        Extra context embedded in the report header.

    Returns
    -------
    str
        Full markdown content (also written to ``output_path``).
    """
    if not isinstance(records, list):
        raise TypeError(
            f"records must be a list of dicts; got {type(records)}"
        )

    output_path = (
        Path(output_path)
        if output_path
        else Path("research") / "regime_walk_forward.md"
    )
    metadata = dict(metadata) if metadata else {}

    summary = summarize_walk_forward_results(records)
    lines   = _build_wf_report_lines(records, summary, metadata)
    content = "\n".join(lines)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")
    return content


# ---------------------------------------------------------------------------
# Private: phase helpers
# ---------------------------------------------------------------------------

def _build_train_policy(
    *,
    symbols_data: dict[str, pd.DataFrame],
    strategies: dict[str, dict[str, Any]],
    win: dict[str, Any],
    base_config: Any,
    win_idx: int,
) -> Optional[RegimePolicy]:
    """
    Build a frozen RegimePolicy from all symbols' train-window data.

    No test-window data is accessed here.

    Returns None when insufficient train results are available.
    """
    train_rows: list[dict[str, Any]] = []

    for symbol, full_df in symbols_data.items():
        train_df = full_df.iloc[
            win["train_start_idx"] : win["train_end_idx"]
        ].copy()

        if len(train_df) < _MIN_TRAIN_BARS:
            logger.debug(
                f"  Window {win_idx} | {symbol}: "
                f"train slice too short ({len(train_df)} bars) - skipped"
            )
            continue

        # Detect regime from TRAIN data only
        train_regime = _detect_regime_label(train_df, symbol=symbol)

        # Run all strategies on train slice
        for strat_name, strat_def in strategies.items():
            result = _run_backtest_for_slice(
                symbol=symbol,
                df=train_df,
                strategy_name=strat_name,
                strategy_class=strat_def["class"],
                params=strat_def.get("params", {}),
                base_config=base_config,
            )
            if result is not None:
                result["regime_label"] = train_regime
                train_rows.append(result)

    if not train_rows:
        logger.warning(
            f"  Window {win_idx}: no train results produced; "
            "policy cannot be built for this window"
        )
        return None

    try:
        train_df_all = pd.DataFrame(train_rows)
        agg_df = analyze_by_regime(train_df_all)
        policy = RegimePolicyBuilder().build(
            agg_df,
            source_description=(
                f"Walk-forward window {win_idx}: "
                f"{win['train_start']} to {win['train_end']}"
            ),
        )
        logger.debug(
            f"  Window {win_idx}: policy built — "
            f"{len(policy.entries)} regime(s): "
            f"{list(policy.entries.keys())}"
        )
        return policy

    except Exception as exc:
        logger.warning(
            f"  Window {win_idx}: policy build failed — {exc}"
        )
        return None


def _evaluate_test_window(
    *,
    symbols_data: dict[str, pd.DataFrame],
    strategies: dict[str, dict[str, Any]],
    strategy_names: list[str],
    frozen_policy: Optional[RegimePolicy],
    win: dict[str, Any],
    base_config: Any,
    win_idx: int,
) -> list[dict[str, Any]]:
    """
    Evaluate the frozen policy on each symbol's test window.

    Runs all strategies on the test slice for comparison, detects the
    test-window regime, applies the frozen policy, and records results.
    """
    records: list[dict[str, Any]] = []

    for symbol, full_df in symbols_data.items():
        test_df = full_df.iloc[
            win["test_start_idx"] : win["test_end_idx"]
        ].copy()

        if len(test_df) < _MIN_TEST_BARS:
            logger.debug(
                f"  Window {win_idx} | {symbol}: "
                f"test slice too short ({len(test_df)} bars) — skipped"
            )
            continue

        # Run ALL strategies on test slice (evaluation only; not used to
        # modify or re-build the frozen policy)
        test_results: dict[str, Optional[dict[str, Any]]] = {}
        for strat_name, strat_def in strategies.items():
            test_results[strat_name] = _run_backtest_for_slice(
                symbol=symbol,
                df=test_df,
                strategy_name=strat_name,
                strategy_class=strat_def["class"],
                params=strat_def.get("params", {}),
                base_config=base_config,
            )

        # Detect regime from TEST slice (after policy is frozen)
        test_regime = _detect_regime_label(test_df, symbol=symbol)

        # Apply frozen policy
        if frozen_policy is not None:
            decision = select_for_regime(
                regime_label=test_regime,
                available_strategies=strategy_names,
                policy=frozen_policy,
            )
            policy_found        = decision.policy_found
            policy_should_trade = decision.should_trade

            if policy_should_trade:
                # Preferred first, then first allowed, else None
                selected_strategy: Optional[str] = (
                    decision.preferred_strategy
                    or (
                        decision.allowed_strategies[0]
                        if decision.allowed_strategies
                        else None
                    )
                )
            else:
                selected_strategy = None  # no-trade
        else:
            # No policy could be built for this window
            policy_found        = False
            policy_should_trade = True   # no blocking without a policy
            selected_strategy   = None

        # Best strategy in test (by Sharpe)
        best_strategy_in_test, best_strategy_return = _find_best_test_strategy(
            test_results
        )

        # Resolve selected strategy's metrics
        selected_return: Optional[float] = None
        selected_sharpe: Optional[float] = None
        if (
            selected_strategy is not None
            and test_results.get(selected_strategy) is not None
        ):
            sel_row         = test_results[selected_strategy]
            selected_return = sel_row.get("total_return_pct")
            selected_sharpe = sel_row.get("sharpe_ratio")

        # Evaluate policy correctness
        policy_was_correct = _evaluate_correctness(
            policy_should_trade=policy_should_trade,
            selected_strategy=selected_strategy,
            best_strategy_in_test=best_strategy_in_test,
            test_results=test_results,
        )

        records.append({
            "symbol":                   symbol,
            "window_index":             win_idx,
            "train_start":              win["train_start"],
            "train_end":                win["train_end"],
            "test_start":               win["test_start"],
            "test_end":                 win["test_end"],
            "train_bars":               win["train_bars"],
            "test_bars":                win["test_bars"],
            "regime_label":             test_regime,
            "selected_strategy":        selected_strategy,
            "selected_strategy_return": selected_return,
            "selected_strategy_sharpe": selected_sharpe,
            "best_strategy_in_test":    best_strategy_in_test,
            "best_strategy_return":     best_strategy_return,
            "policy_should_trade":      policy_should_trade,
            "policy_was_correct":       policy_was_correct,
            "policy_found":             policy_found,
        })

    return records


# ---------------------------------------------------------------------------
# Private: single-backtest helper
# ---------------------------------------------------------------------------

def _run_backtest_for_slice(
    symbol: str,
    df: pd.DataFrame,
    strategy_name: str,
    strategy_class: Any,
    params: dict[str, Any],
    base_config: Any,
) -> Optional[dict[str, Any]]:
    """
    Run a single backtest on a DataFrame slice.

    Returns a minimal flat result dict containing the key performance
    metrics needed for regime analysis and walk-forward evaluation,
    or ``None`` if the backtest fails for any reason.
    """
    from src.core.backtest_engine import BacktestEngine
    from src.core.data_handler import DataHandler

    try:
        strategy = strategy_class(**params)
        if hasattr(base_config, "model_copy"):
            cfg = base_config.model_copy(deep=True)
        elif hasattr(base_config, "copy"):
            try:
                cfg = base_config.copy(deep=True)
            except TypeError:
                cfg = base_config.copy()
        else:
            cfg = copy.deepcopy(base_config)
        cfg.strategy_params = params

        dh           = DataHandler(df)
        engine       = BacktestEngine(cfg, strategy, dh)
        metrics_obj  = engine.run()
        m            = metrics_obj.metrics

        return {
            "symbol":           symbol,
            "strategy":         strategy_name,
            "sharpe_ratio":     m.get("sharpe_ratio"),
            "total_return_pct": m.get("total_return_pct"),
            "max_drawdown_pct": m.get("max_drawdown_pct"),
            "num_trades":       m.get("num_trades"),
            "win_rate":         m.get("win_rate"),
        }

    except Exception as exc:
        logger.debug(
            f"  Backtest failed [{symbol}/{strategy_name}]: {exc}"
        )
        return None


# ---------------------------------------------------------------------------
# Private: regime detection helper
# ---------------------------------------------------------------------------

def _detect_regime_label(df: pd.DataFrame, symbol: str = "SYMBOL") -> str:
    """
    Detect the composite market regime from a DataFrame slice.

    Returns
    -------
    str
        ``CompositeRegime.value`` string (e.g. ``"risk_off"``), or
        ``"unknown"`` when detection fails for any reason.
    """
    try:
        from src.market_intelligence.regime_engine import (
            MarketRegimeEngine,
            MarketRegimeEngineConfig,
        )
        cfg  = MarketRegimeEngineConfig(symbol=symbol, long_ma_period=200)
        snap = MarketRegimeEngine().detect(df, config=cfg, symbol=symbol)
        if snap is not None:
            return snap.composite_regime.value
    except Exception as exc:
        logger.debug(f"  Regime detection failed [{symbol}]: {exc}")
    return "unknown"


# ---------------------------------------------------------------------------
# Private: correctness and ranking helpers
# ---------------------------------------------------------------------------

def _find_best_test_strategy(
    test_results: dict[str, Optional[dict[str, Any]]],
) -> tuple[Optional[str], Optional[float]]:
    """
    Identify the strategy with the highest Sharpe ratio in the test window.

    Returns
    -------
    (best_strategy_name, best_strategy_total_return_pct)
        Both are ``None`` when no strategy produced a valid result.
    """
    best_name:   Optional[str]   = None
    best_sharpe: float           = float("-inf")
    best_return: Optional[float] = None

    for strat_name, result in test_results.items():
        if result is None:
            continue
        sharpe = result.get("sharpe_ratio")
        if sharpe is None:
            sharpe = float("-inf")
        if sharpe > best_sharpe:
            best_sharpe = sharpe
            best_name   = strat_name
            best_return = result.get("total_return_pct")

    return best_name, best_return


def _evaluate_correctness(
    *,
    policy_should_trade: bool,
    selected_strategy: Optional[str],
    best_strategy_in_test: Optional[str],
    test_results: dict[str, Optional[dict[str, Any]]],
) -> bool:
    """
    Determine whether the policy made the correct call.

    Trade decision
        Correct when the selected strategy matches the best strategy
        in the test window (highest Sharpe).

    No-trade decision
        Correct when ALL strategies posted a negative ``total_return_pct``
        in the test window (i.e. staying out was genuinely beneficial).
    """
    if not policy_should_trade:
        # No-trade: correct when every strategy posted a negative return
        valid_results = [r for r in test_results.values() if r is not None]
        if not valid_results:
            # Nothing to compare against; treat as unknown → not correct
            return False
        return all(
            (r.get("total_return_pct") or 0.0) < 0
            for r in valid_results
        )

    # Trade: correct when selection matches best
    if selected_strategy is None or best_strategy_in_test is None:
        return False
    return selected_strategy == best_strategy_in_test


# ---------------------------------------------------------------------------
# Private: date string helper
# ---------------------------------------------------------------------------

def _date_str(df: pd.DataFrame, *, first: bool) -> str:
    """Return an ISO date string for the first or last bar of a DataFrame."""
    if df.empty:
        return ""
    ts = df.index[0] if first else df.index[-1]
    if hasattr(ts, "date"):
        return str(ts.date())
    return str(ts)


# ---------------------------------------------------------------------------
# Private: report generation
# ---------------------------------------------------------------------------

def _build_wf_report_lines(
    records: list[dict[str, Any]],
    summary: dict[str, Any],
    metadata: dict[str, Any],
) -> list[str]:
    """Assemble all sections of the walk-forward markdown report."""
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []

    hit_rate     = summary.get("policy_hit_rate")
    hit_rate_str = f"{hit_rate * 100:.1f}%" if hit_rate is not None else "N/A"

    # ------------------------------------------------------------------
    # Header / metadata
    # ------------------------------------------------------------------
    lines += [
        "# Regime Policy Walk-Forward Validation",
        "",
        "## Run Metadata",
        "",
        "| Field | Value |",
        "| --- | --- |",
        f"| Generated | {now} |",
        f"| Methodology | Rolling train/test windows - no lookahead |",
    ]
    for key, val in metadata.items():
        lines.append(f"| {str(key).replace('_', ' ').title()} | {val} |")
    lines += [
        f"| Total Records | {summary.get('total_records', 0)} |",
        f"| Total Windows | {summary.get('total_windows', 0)} |",
        f"| Symbols Tested | {summary.get('symbols_tested', 0)} |",
        "",
        "---",
    ]

    # ------------------------------------------------------------------
    # Window configuration
    # ------------------------------------------------------------------
    if records:
        first_r = records[0]
        last_r  = records[-1]
        lines += [
            "",
            "## Window Configuration",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| First train start | {first_r.get('train_start', 'N/A')} |",
            f"| Last test end | {last_r.get('test_end', 'N/A')} |",
            f"| Train bars per window | {first_r.get('train_bars', 'N/A')} |",
            f"| Test bars per window | {first_r.get('test_bars', 'N/A')} |",
            f"| Number of windows | {summary.get('total_windows', 'N/A')} |",
            "",
            "---",
        ]

    # ------------------------------------------------------------------
    # Aggregate performance
    # ------------------------------------------------------------------
    lines += [
        "",
        "## Aggregate Performance",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Policy hit rate | **{hit_rate_str}** |",
        f"| Correct calls | {summary.get('correct_calls', 0)} / {summary.get('total_records', 0)} |",
        f"| Should-trade decisions | {summary.get('should_trade_records', 0)} |",
        f"| No-trade decisions | {summary.get('no_trade_records', 0)} |",
        f"| No-trade correct | {summary.get('no_trade_correct', 0)} |",
    ]

    mean_sel_sharpe = summary.get("mean_selected_sharpe")
    if mean_sel_sharpe is not None:
        lines.append(f"| Mean selected strategy Sharpe | {mean_sel_sharpe:.4f} |")

    mean_sel_ret = summary.get("mean_selected_return")
    if mean_sel_ret is not None:
        lines.append(f"| Mean selected strategy return | {mean_sel_ret:.4f} |")

    mean_best_ret = summary.get("mean_best_return")
    if mean_best_ret is not None:
        lines.append(f"| Mean best strategy return (upper bound) | {mean_best_ret:.4f} |")

    lines += ["", "---"]

    # ------------------------------------------------------------------
    # Performance by regime
    # ------------------------------------------------------------------
    by_regime = summary.get("by_regime", {})
    if by_regime:
        lines += [
            "",
            "## Performance by Regime",
            "",
            "| Regime | Total | Correct | Hit Rate |",
            "| --- | --- | --- | --- |",
        ]
        for regime, d in sorted(by_regime.items()):
            hr_str = (
                f"{d['hit_rate'] * 100:.1f}%"
                if d.get("hit_rate") is not None
                else "N/A"
            )
            lines.append(
                f"| {regime} | {d['total']} | {d['correct']} | {hr_str} |"
            )
        lines += ["", "---"]

    # ------------------------------------------------------------------
    # Strategy selection frequency
    # ------------------------------------------------------------------
    by_strat = summary.get("by_strategy_selected", {})
    if by_strat:
        lines += [
            "",
            "## Strategy Selection Frequency",
            "",
            "| Strategy | Times Selected |",
            "| --- | --- |",
        ]
        for strat, count in sorted(by_strat.items(), key=lambda x: -x[1]):
            lines.append(f"| {strat} | {count} |")
        lines += ["", "---"]

    # ------------------------------------------------------------------
    # Per-window detail table
    # ------------------------------------------------------------------
    if records:
        lines += [
            "",
            "## Per-Window Results",
            "",
            "> Each row is one (symbol, window) combination.",
            "> `policy_was_correct`: True = policy made the right call.",
            "",
        ]
        df_rec = pd.DataFrame(records)
        display_cols = [
            c for c in [
                "symbol", "window_index", "test_start", "test_end",
                "regime_label", "selected_strategy",
                "selected_strategy_sharpe",
                "best_strategy_in_test", "best_strategy_return",
                "policy_should_trade", "policy_was_correct",
            ]
            if c in df_rec.columns
        ]
        lines.append(_records_to_md(df_rec[display_cols]))
        lines += ["", "---"]

    # ------------------------------------------------------------------
    # Key conclusions
    # ------------------------------------------------------------------
    lines += ["", "## Key Conclusions", ""]
    if summary.get("total_records", 0) == 0:
        lines.append("- No walk-forward records generated.")
    else:
        if hit_rate is not None:
            if hit_rate >= 0.6:
                assessment = (
                    "The policy shows reasonable out-of-sample predictive ability."
                )
            elif hit_rate >= 0.4:
                assessment = (
                    "The policy shows mixed out-of-sample results; "
                    "interpret with caution."
                )
            else:
                assessment = (
                    "The policy shows limited out-of-sample predictive ability; "
                    "consider expanding the symbol set or revising thresholds."
                )
            lines.append(f"- **Policy hit rate: {hit_rate_str}** - {assessment}")

        n_sym = summary.get("symbols_tested", 0)
        n_win = summary.get("total_windows", 0)
        lines.append(
            f"- Validated across {n_sym} symbol(s) and {n_win} rolling window(s)."
        )

        regimes = summary.get("regimes_observed", [])
        if regimes:
            lines.append(
                f"- Regimes observed in test windows: {', '.join(regimes)}."
            )

        no_trade = summary.get("no_trade_records", 0)
        if no_trade > 0:
            nt_correct = summary.get("no_trade_correct", 0)
            lines.append(
                f"- No-trade decisions: {no_trade} "
                f"({nt_correct} confirmed correct - all strategies posted "
                "negative returns in those windows)."
            )

    lines += [
        "",
        "---",
        "",
        "## Caveats",
        "",
        "- Walk-forward windows use bar-index slicing; "
          "1 bar ~= 1 trading day for daily-interval data.",
        "- The policy is built from all symbols' train data combined; "
          "small symbol counts yield thin policies.",
        "- Policy correctness is defined strictly: selected strategy must "
          "match the highest-Sharpe strategy in the test window.",
        "- No-trade correctness requires ALL strategies to post negative returns.",
        "- Sample sizes from a typical research run are small; treat results "
          "as directional guidance, not statistical certainty.",
        "- Past regime-strategy relationships may not persist in future "
          "market conditions.",
        "- This output must not be used for live trading.",
        "",
        "_Generated by the NIFTY 50 Zerodha Research Runner with "
          "`--walk-forward-regime` enabled._",
    ]
    return lines


def _records_to_md(df: pd.DataFrame) -> str:
    """Convert a records DataFrame to a Markdown table string."""
    if df.empty:
        return "_No records._"

    def _fmt(v: Any) -> str:
        if v is None or (isinstance(v, float) and v != v):
            return "N/A"
        if isinstance(v, bool):
            return str(v)
        if isinstance(v, float):
            return f"{v:.4f}"
        if isinstance(v, int):
            return str(v)
        return str(v)

    col_names = list(df.columns)
    header    = "| " + " | ".join(str(c) for c in col_names) + " |"
    sep       = "| " + " | ".join("---" for _ in col_names) + " |"
    rows      = [
        "| " + " | ".join(_fmt(v) for v in row) + " |"
        for row in df.itertuples(index=False, name=None)
    ]
    return "\n".join([header, sep] + rows)
