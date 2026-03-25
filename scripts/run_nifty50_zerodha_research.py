#!/usr/bin/env python3
"""
NIFTY 50 Zerodha Research Runner
==================================
Fetches historical OHLCV data for the NIFTY 50 universe from Zerodha
Kite Connect (or a CSV fallback), runs multiple strategies against every
symbol, ranks results with a composite score, and exports clean reports.

Data priority (same as the pipeline validation script):
  1. Live Zerodha Kite API  (requires ZERODHA_* env vars)
  2. Kite-sourced CSV files  (data/RELIANCE_KITE_1D.csv etc.)
  3. Standard CSV fallback   (data/RELIANCE_1D.csv)

Usage examples
--------------
# Quick smoke-test on 5 symbols (1 year, daily bars):
  python scripts/run_nifty50_zerodha_research.py --symbols-limit 5

# Full NIFTY 50 run with optimisation:
  python scripts/run_nifty50_zerodha_research.py --optimize

# Intraday research (60-min bars, 90 days):
  python scripts/run_nifty50_zerodha_research.py --interval 60minute --days 90

Outputs (all written to --output-dir, default: output/nifty50_research/):
  all_results.csv   - every symbol x strategy combination
  top_ranked.csv    - best combinations filtered by composite score
  summary.md        - human-readable markdown report
"""

from __future__ import annotations

import argparse
import os
import sys
import time
import traceback
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Project root on sys.path
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env silently
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass

import pandas as pd  # noqa: E402
from src.runtime import (  # noqa: E402
    RunMode,
    RunnerValidationError,
    assert_artifact_contract,
    enforce_runtime_safety,
    get_artifact_contract,
    normalize_fee_inputs,
    write_output_manifest,
)

# ---------------------------------------------------------------------------
# Console helpers (ASCII-only for Windows cp1252 compatibility)
# ---------------------------------------------------------------------------
DIVIDER = "-" * 60


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def ok(msg: str)   -> None: print(f"  [OK]   {msg}")
def warn(msg: str) -> None: print(f"  [WARN] {msg}")
def fail(msg: str) -> None: print(f"  [FAIL] {msg}")
def info(msg: str) -> None: print(f"  [INFO] {msg}")


# ---------------------------------------------------------------------------
# CLI arguments
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="NIFTY 50 multi-strategy research runner via Zerodha",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--symbols-limit", type=int, default=0, metavar="N",
        help="Test only the first N symbols (0 = all 53). Useful for smoke tests.",
    )
    p.add_argument(
        "--days", type=int, default=365,
        help="Look-back window in calendar days (default: 365).",
    )
    p.add_argument(
        "--interval", choices=["day", "5minute", "15minute", "60minute"],
        default="day",
        help="Bar interval (default: day).",
    )
    p.add_argument(
        "--strategy", nargs="+",
        default=[],
        help="Specific strategies to run (e.g. 'sma_crossover').",
    )
    p.add_argument(
        "--package", nargs="+",
        default=[],
        help="Strategy packages to run (e.g. 'positional', 'swing').",
    )
    p.add_argument(
        "--top-n", type=int, default=20,
        help="How many rows to include in top_ranked.csv (default: 20).",
    )
    p.add_argument(
        "--output-dir", type=str, default="output/nifty50_research",
        help="Directory for output files (default: output/nifty50_research).",
    )
    p.add_argument(
        "--optimize", action="store_true",
        help="Run parameter grid-search per symbol (slow; uses StrategyOptimizer).",
    )
    p.add_argument(
        "--initial-capital", type=float, default=100_000.0,
        help="Initial portfolio capital in Rs. (default: 100,000).",
    )
    p.add_argument(
        "--fee-rate", type=float, default=0.001,
        help="Brokerage fee rate (default: 0.001 = 0.10%%).",
    )
    p.add_argument(
        "--slippage-rate", type=float, default=0.0005,
        help="Slippage rate (default: 0.0005 = 0.05%%).",
    )
    p.add_argument(
        "--include-regime", action="store_true",
        help=(
            "Detect the current market regime using the first fetched symbol "
            "and include it in summary.md. Adds ~1 second. Disabled by default."
        ),
    )
    p.add_argument(
        "--regime-filter", action="store_true",
        help=(
            "Skip strategies that are incompatible with the detected market regime. "
            "Requires --include-regime. When regime is UNKNOWN all strategies run. "
            "Disabled by default; existing behaviour is fully preserved without this flag."
        ),
    )
    p.add_argument(
        "--regime-analysis", action="store_true",
        help=(
            "Detect regime independently per-symbol and run regime-segmented "
            "performance analysis after the backtest loop. Generates a markdown "
            "research report at research/regime_validation.md. "
            "Orthogonal to --include-regime and --regime-filter. "
            "Disabled by default; zero behaviour change when absent."
        ),
    )
    p.add_argument(
        "--build-regime-policy", action="store_true",
        help=(
            "Build a deterministic regime-driven strategy selection policy from "
            "the regime analysis results. Requires --regime-analysis. "
            "Generates research/regime_policy.json and research/regime_policy.md. "
            "Disabled by default; zero behaviour change when absent."
        ),
    )
    p.add_argument(
        "--policy-output", type=str, default=None,
        metavar="PATH",
        help=(
            "Custom output path for the regime policy JSON artifact. "
            "Defaults to research/regime_policy.json when --build-regime-policy "
            "is active. Ignored when --build-regime-policy is absent."
        ),
    )
    p.add_argument(
        "--walk-forward-regime", action="store_true",
        help=(
            "Run regime policy walk-forward validation after the main backtest "
            "loop.  For each rolling window the policy is built from train-window "
            "data only (no lookahead) and then evaluated on the held-out test "
            "window.  Generates research/regime_walk_forward.md. "
            "Automatically enables --regime-analysis. "
            "Disabled by default; zero behaviour change when absent."
        ),
    )
    p.add_argument(
        "--train-days", type=int, default=180, metavar="N",
        help=(
            "Number of bars in each walk-forward training window "
            "(default: 180, approximately 6 months of daily bars). "
            "Only used when --walk-forward-regime is active."
        ),
    )
    p.add_argument(
        "--test-days", type=int, default=90, metavar="N",
        help=(
            "Number of bars in each walk-forward test window "
            "(default: 90, approximately 3 months of daily bars). "
            "Only used when --walk-forward-regime is active."
        ),
    )
    p.add_argument(
        "--step-days", type=int, default=45, metavar="N",
        help=(
            "Number of bars to advance the window start between walk-forward "
            "iterations (default: 45).  A value equal to --test-days gives "
            "non-overlapping test windows. "
            "Only used when --walk-forward-regime is active."
        ),
    )
    # ---- Phase 5: Relative Strength / Top-Stock Selection ----
    p.add_argument(
        "--top-n-symbols", type=int, default=0, metavar="N",
        help=(
            "After the main research loop, compute relative strength scores for "
            "all symbols and rank them.  When N > 0, the top-N names are printed "
            "and highlighted in the report.  Generates "
            "research/relative_strength_analysis.md. "
            "Disabled by default (0 = off)."
        ),
    )
    p.add_argument(
        "--relative-strength-lookback", type=int, default=90, metavar="N",
        help=(
            "Look-back window in bars for relative strength computation "
            "(default: 90 bars ~= 3 months of daily data). "
            "Only used when --top-n-symbols is active."
        ),
    )
    p.add_argument(
        "--benchmark-symbol", type=str, default="", metavar="SYM",
        help=(
            "Optional symbol to use as a benchmark for relative-return "
            "computation (e.g. 'NIFTY50').  When provided, each symbol's "
            "momentum return is compared to the benchmark's momentum return. "
            "Ignored when empty."
        ),
    )
    # ---- Phase 4: Portfolio-Level Backtest ----
    p.add_argument(
        "--portfolio-backtest", action="store_true",
        help=(
            "Run a portfolio-level backtest after the main research loop. "
            "Allocates total capital equally across up to --max-positions symbols, "
            "selects strategy per symbol (via regime policy if available), and "
            "generates research/portfolio_backtest.md. "
            "Disabled by default; zero behaviour change when absent."
        ),
    )
    p.add_argument(
        "--max-positions", type=int, default=10, metavar="N",
        help=(
            "Maximum concurrent portfolio positions (default: 10). "
            "Limits the number of symbols active in --portfolio-backtest. "
            "Capital is allocated across active symbols by default."
        ),
    )
    # ---- Phase 6: Risk Engine ----
    p.add_argument(
        "--enable-risk-management", action="store_true",
        help=(
            "Enable portfolio-level risk guardrails after the main backtest. "
            "Runs validate_portfolio_risk() against the portfolio equity curve "
            "and generates research/risk_engine_validation.md. "
            "Disabled by default; zero behaviour change when absent."
        ),
    )
    p.add_argument(
        "--max-risk-per-trade", type=float, default=0.01, metavar="F",
        help=(
            "Maximum fraction of portfolio equity to risk per trade (default: 0.01 = 1%%). "
            "Only used when --enable-risk-management is active."
        ),
    )
    p.add_argument(
        "--max-portfolio-exposure", type=float, default=0.20, metavar="F",
        help=(
            "Maximum fraction of portfolio equity deployed simultaneously "
            "(default: 0.20 = 20%%). "
            "Only used when --enable-risk-management is active."
        ),
    )
    p.add_argument(
        "--max-drawdown", type=float, default=0.15, metavar="F",
        help=(
            "Portfolio drawdown kill-switch threshold (default: 0.15 = 15%%). "
            "New entries are blocked when drawdown exceeds this level. "
            "Only used when --enable-risk-management is active."
        ),
    )
    p.add_argument(
        "--max-concurrent-positions", type=int, default=10, metavar="N",
        help=(
            "Hard cap on simultaneous open positions (default: 10). "
            "Only used when --enable-risk-management is active."
        ),
    )
    # ---- Phase 7: Execution Realism / Cost Modeling ----
    p.add_argument(
        "--execution-realism", action="store_true",
        help=(
            "Apply realistic execution costs (commission + slippage) to the "
            "portfolio trade log and generate a gross vs net comparison.  "
            "Requires --portfolio-backtest to produce a trade log.  "
            "Generates research/execution_realism.md. "
            "Disabled by default; zero behaviour change when absent."
        ),
    )
    p.add_argument(
        "--commission-bps", type=float, default=10.0, metavar="F",
        help=(
            "Proportional commission in basis points of notional value "
            "(default: 10.0 bps = 0.10%%). "
            "Only used when --execution-realism is active."
        ),
    )
    p.add_argument(
        "--slippage-bps", type=float, default=5.0, metavar="F",
        help=(
            "Slippage / market-impact in basis points of notional value "
            "(default: 5.0 bps = 0.05%%). "
            "Only used when --execution-realism is active."
        ),
    )
    fill_mode = p.add_mutually_exclusive_group()
    fill_mode.add_argument(
        "--use-next-bar-fill", dest="use_next_bar_fill", action="store_true",
        help=(
            "Fill trades at the next bar's open price (default). "
            "This is the realistic mode consistent with NEXT_BAR_OPEN execution. "
            "Only used when --execution-realism is active."
        ),
    )
    fill_mode.add_argument(
        "--use-same-bar-fill", dest="use_next_bar_fill", action="store_false",
        help=(
            "Fill trades on same-bar close for sensitivity analysis. "
            "Only used when --execution-realism is active."
        ),
    )
    p.set_defaults(use_next_bar_fill=True)

    args = p.parse_args()

    if args.symbols_limit < 0:
        p.error("--symbols-limit must be >= 0")
    if args.days < 1:
        p.error("--days must be >= 1")
    if args.top_n < 1:
        p.error("--top-n must be >= 1")
    if args.train_days < 1 or args.test_days < 1 or args.step_days < 1:
        p.error("--train-days, --test-days, and --step-days must all be >= 1")
    if args.max_positions < 1:
        p.error("--max-positions must be >= 1")
    if args.max_concurrent_positions < 1:
        p.error("--max-concurrent-positions must be >= 1")
    if args.top_n_symbols < 0:
        p.error("--top-n-symbols must be >= 0")
    if args.relative_strength_lookback < 1:
        p.error("--relative-strength-lookback must be >= 1")
    if args.fee_rate < 0 or args.slippage_rate < 0:
        p.error("--fee-rate and --slippage-rate must be >= 0")
    try:
        normalize_fee_inputs(
            commission_bps=args.commission_bps,
            slippage_bps=args.slippage_bps,
            fee_rate=args.fee_rate,
            slippage_rate=args.slippage_rate,
        )
    except RunnerValidationError as exc:
        p.error(str(exc))
    if not 0 < args.max_risk_per_trade <= 1:
        p.error("--max-risk-per-trade must be in (0, 1]")
    if not 0 < args.max_portfolio_exposure <= 1:
        p.error("--max-portfolio-exposure must be in (0, 1]")
    if not 0 < args.max_drawdown <= 1:
        p.error("--max-drawdown must be in (0, 1]")
    if args.execution_realism and not args.portfolio_backtest:
        p.error("--execution-realism requires --portfolio-backtest")

    return args


# ---------------------------------------------------------------------------
# Interval -> Timeframe mapping
# ---------------------------------------------------------------------------
def interval_to_timeframe(interval: str):
    from src.data.base import Timeframe
    mapping = {
        "day":      Timeframe.DAILY,
        "5minute":  Timeframe.MINUTE_5,
        "15minute": Timeframe.MINUTE_15,
        "60minute": Timeframe.HOURLY,
    }
    tf = mapping.get(interval)
    if tf is None:
        raise ValueError(f"Unknown interval: {interval!r}. Valid: {list(mapping)}")
    return tf


# ---------------------------------------------------------------------------
# Strategy registry
# ---------------------------------------------------------------------------
def build_strategy_registry(strategies: list[str], packages: list[str]) -> dict[str, dict[str, Any]]:
    """
    Returns a dict keyed by canonical strategy name containing:
      class      - the strategy class
      params     - default parameters for single-run mode
      param_grid - grid for StrategyOptimizer (used when --optimize)
    """
    from src.strategies.registry import resolve_package, resolve_strategy, UnsupportedStrategyError

    unique_specs = {}

    for pkg in packages:
        for spec in resolve_package(pkg):
            unique_specs[spec.key] = spec

    for strat in strategies:
        try:
            spec = resolve_strategy(strat)
            unique_specs[spec.key] = spec
        except UnsupportedStrategyError as e:
            warn(f"Warning: {e}")

    if not unique_specs:
        if not strategies and not packages:
            # Default fallback for simple runs
            for strat in ["sma_crossover", "rsi_reversion", "breakout"]:
                try:
                    spec = resolve_strategy(strat)
                    unique_specs[spec.key] = spec
                except Exception:
                    pass
        if not unique_specs:
            raise ValueError("No runnable strategies resolved.")

    # Apply known parameter grids for historical compatibility, otherwise fallback to single-point grid
    _KNOWN_GRIDS = {
        "sma_crossover": {
            "fast_period": [10, 20],
            "slow_period": [30, 50, 100],
        },
        "rsi_reversion": {
            "rsi_period": [14],
            "oversold":   [25, 30],
            "overbought": [70, 75],
        },
        "breakout": {
            "entry_period": [20, 40],
            "exit_period":  [10, 15],
        },
    }

    return {
        key: {
            "class": spec.strategy_class,
            "params": dict(spec.params),
            "param_grid": _KNOWN_GRIDS.get(key, {k: [v] for k, v in spec.params.items()}),
        }
        for key, spec in unique_specs.items()
    }


# ---------------------------------------------------------------------------
# Composite ranking score
# ---------------------------------------------------------------------------
SHARPE_W    = 1.0   # sharpe_ratio weight
RETURN_W    = 100.0 # total_return_pct weight  (decimal, e.g. 0.12 for 12%)
DRAWDOWN_P  = 50.0  # max_drawdown_pct penalty (decimal)
MIN_TRADES  = 3     # minimum trades required to be included in ranking

# ---------------------------------------------------------------------------
# Regime-aware filtering  (Phases 3 & 4)
# ---------------------------------------------------------------------------
# Maps each strategy short-name to the CompositeRegime *values* that are
# compatible with it.  UNKNOWN is always included so that an ambiguous
# regime never blocks a strategy (conservative / safe default).
# Keyed by the same strings used in build_strategy_registry().
_REGIME_ALLOWED: dict[str, frozenset] = {
    "sma_crossover": frozenset({"bullish_trending", "bullish_sideways", "unknown"}),
    "breakout":      frozenset({"bullish_trending", "bullish_sideways", "unknown"}),
    "rsi_reversion": frozenset({"rangebound",       "bullish_sideways", "unknown"}),
}

# CompositeRegime.value -> nearest RegimeState.value.
# Documented adapter so future callers can bridge MarketRegimeSnapshot to the
# Phase-5 RegimeFilter (src.decision.regime_filter) without re-implementing
# the mapping.  NOT used by the research runner itself.
_COMPOSITE_TO_REGIME_STATE: dict[str, str] = {
    "bullish_trending": "bullish",
    "bullish_sideways": "low_volatility",
    "bearish_trending": "bearish",
    "bearish_volatile": "bearish",
    "rangebound":       "rangebound",
    "risk_off":         "high_volatility",
    "unknown":          "unknown",
}


def compute_score(row: dict[str, Any]) -> float:
    sharpe   = row.get("sharpe_ratio")    or 0.0
    ret      = row.get("total_return_pct") or 0.0
    dd       = row.get("max_drawdown_pct") or 0.0
    # drawdown is stored as a negative fraction (e.g. -0.25 for 25% dd)
    # apply penalty on magnitude
    score = (SHARPE_W * sharpe) + (RETURN_W * ret) - (DRAWDOWN_P * abs(dd))
    return round(score, 6)


def is_strategy_allowed(
    strategy_name: str,
    composite_regime_value: str,
) -> tuple[bool, str]:
    """
    Return (allowed, reason) for a strategy in the current composite regime.

    Parameters
    ----------
    strategy_name : str
        Short key matching build_strategy_registry(): "sma", "rsi", "breakout".
    composite_regime_value : str
        The .value string of a CompositeRegime (e.g. "bullish_trending").

    Returns
    -------
    (bool, str)
        True + reason if the strategy is compatible with the regime.
        False + reason if the strategy is blocked.
        Strategies not present in _REGIME_ALLOWED are allowed by default
        (open-world assumption: don't block novel strategies).
    """
    allowed_set = _REGIME_ALLOWED.get(strategy_name)
    if allowed_set is None:
        return True, f"'{strategy_name}' not in filter table; allowed by default"
    if composite_regime_value in allowed_set:
        return True, f"{strategy_name} compatible with {composite_regime_value}"
    return False, (
        f"{strategy_name} blocked in '{composite_regime_value}' "
        f"(allowed: {sorted(allowed_set)})"
    )


# ---------------------------------------------------------------------------
# Single-symbol single-strategy backtest (no optimisation)
# ---------------------------------------------------------------------------
def run_single(
    symbol: str,
    df: pd.DataFrame,
    strategy_name: str,
    strategy_class,
    params: dict[str, Any],
    base_config,
) -> Optional[dict[str, Any]]:
    """
    Run a single backtest for one symbol + strategy + param set.
    Returns a flat result dict or None on failure.
    """
    from src.core.data_handler import DataHandler
    from src.core.backtest_engine import BacktestEngine

    try:
        strategy = strategy_class(**params)
        cfg = base_config.model_copy(deep=True)
        cfg.strategy_params = params

        dh = DataHandler(df)
        engine = BacktestEngine(cfg, strategy, dh)
        metrics_obj = engine.run()
        m = metrics_obj.metrics

        row: dict[str, Any] = {
            "symbol":           symbol,
            "strategy":         strategy_name,
            "optimized":        False,
        }
        # embed default params
        for k, v in params.items():
            row[f"param_{k}"] = v
        # core metrics
        for key in (
            "total_return", "total_return_pct", "annualized_return", "cagr",
            "sharpe_ratio", "sortino_ratio", "max_drawdown", "max_drawdown_pct",
            "profit_factor", "num_trades", "num_winners", "num_losers",
            "win_rate", "expectancy", "avg_trade_return",
            "avg_winner", "avg_loser", "largest_winner", "largest_loser",
            "total_fees", "exposure_pct", "initial_capital", "final_value",
        ):
            row[key] = m.get(key)

        row["score"] = compute_score(row)
        return row

    except Exception as exc:
        warn(f"    Backtest failed for {symbol}/{strategy_name}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Single-symbol single-strategy with grid-search (optimisation mode)
# ---------------------------------------------------------------------------
def run_optimized(
    symbol: str,
    df: pd.DataFrame,
    strategy_name: str,
    strategy_class,
    param_grid: dict[str, list],
    base_config,
    output_dir: Path,
) -> Optional[dict[str, Any]]:
    """
    Run StrategyOptimizer grid-search for one symbol + strategy.
    Returns the best flat result dict or None on failure.
    """
    from src.core.data_handler import DataHandler
    from src.research.optimizer import StrategyOptimizer

    try:
        dh = DataHandler(df)
        opt_output = str(output_dir / "optimizer_cache" / symbol / strategy_name)
        optimizer = StrategyOptimizer(
            base_config=base_config,
            strategy_class=strategy_class,
            param_grid=param_grid,
            output_dir=opt_output,
            sort_by="sharpe_ratio",
            ascending=False,
            top_n=1,
        )
        optimizer.run(dh)
        best = optimizer.get_best_result()
        if best is None:
            return None

        # best is already a flat dict; param keys are prefixed with "param_"
        row: dict[str, Any] = {
            "symbol":   symbol,
            "strategy": strategy_name,
            "optimized": True,
        }
        row.update(best)   # merges param_* and metric keys
        row["score"] = compute_score(row)
        return row

    except Exception as exc:
        warn(f"    Optimization failed for {symbol}/{strategy_name}: {exc}")
        return None


# ---------------------------------------------------------------------------
# Market regime detection helper (optional, for --include-regime)
# ---------------------------------------------------------------------------
def detect_market_regime(df: pd.DataFrame, symbol: str = "NIFTY50") -> Optional[Any]:
    """
    Run MarketRegimeEngine on the supplied DataFrame.
    Returns a MarketRegimeSnapshot or None on failure.
    Kept as a standalone helper so the main backtest loop is not affected.
    """
    try:
        from src.market_intelligence.regime_engine import (
            MarketRegimeEngine,
            MarketRegimeEngineConfig,
        )
        cfg = MarketRegimeEngineConfig(symbol=symbol, long_ma_period=200)
        snap = MarketRegimeEngine().detect(df, config=cfg, symbol=symbol)
        return snap
    except Exception as exc:
        warn(f"Regime detection failed: {exc}")
        return None


def _regime_md_section(
    snap: Any,
    filter_active: bool = False,
    regime_skipped: int = 0,
) -> list[str]:
    """
    Render a MarketRegimeSnapshot as Markdown lines for summary.md.

    Parameters
    ----------
    snap : MarketRegimeSnapshot
        Output of MarketRegimeEngine.detect().
    filter_active : bool
        True when --regime-filter was active for this run.
    regime_skipped : int
        Number of (symbol, strategy) combinations skipped by the filter.
    """
    lines: list[str] = []
    lines.append("")
    lines.append("## Market Regime (at time of research run)")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("| --- | --- |")
    lines.append(f"| Symbol | {snap.symbol} |")
    lines.append(f"| As-of date | {snap.timestamp.strftime('%Y-%m-%d')} |")
    lines.append(f"| **Composite regime** | **{snap.composite_regime.value}** |")
    lines.append(f"| Trend regime | {snap.trend_regime.value} |")
    lines.append(f"| Trend state | {snap.trend_state.value} |")
    lines.append(f"| Volatility regime | {snap.volatility_regime.value} |")
    if snap.trend_score is not None:
        lines.append(f"| Trend score | {snap.trend_score:+.4f} |")
    if snap.realized_volatility is not None:
        lines.append(f"| Annualized vol | {snap.realized_volatility*100:.2f}% |")
    if snap.atr_ratio is not None:
        lines.append(f"| ATR ratio | {snap.atr_ratio:.4f} |")
    if snap.last_close is not None:
        lines.append(f"| Last close | {snap.last_close:.2f} |")
    if snap.fast_ma is not None:
        lines.append(f"| Fast MA (20) | {snap.fast_ma:.2f} |")
    if snap.slow_ma is not None:
        lines.append(f"| Slow MA (50) | {snap.slow_ma:.2f} |")
    if snap.long_ma is not None:
        lines.append(f"| Long MA (200) | {snap.long_ma:.2f} |")
    if snap.warnings:
        lines.append(f"| Warnings | {'; '.join(snap.warnings)} |")
    lines.append(f"| Regime filter active | {'Yes' if filter_active else 'No'} |")
    if filter_active:
        lines.append(f"| Combinations skipped by filter | {regime_skipped} |")
    lines.append("")

    # Strategy hint
    hint = {
        "bullish_trending": "Favour trend-following long setups.",
        "bullish_sideways": "Look for breakout entries; reduce position size.",
        "bearish_trending": "Avoid new longs; reduce exposure.",
        "bearish_volatile": "Hard reduction or hedging; minimal new positions.",
        "rangebound":       "Mean-reversion / range strategies.",
        "risk_off":         "Stay in cash; stop all new positions.",
        "unknown":          "Treat as neutral; skip or paper-trade only.",
    }.get(snap.composite_regime.value, "")
    if hint:
        lines.append(f"> **Strategy hint:** {hint}")
        lines.append("")

    # Strategy allow/block table (shown when filter was active)
    if filter_active:
        composite_val = snap.composite_regime.value
        lines.append("### Strategy Allow / Block Table")
        lines.append("")
        lines.append("| Strategy | Regime | Decision | Allowed regimes |")
        lines.append("| --- | --- | --- | --- |")
        for strat_name, allowed_set in sorted(_REGIME_ALLOWED.items()):
            decision = "ALLOWED" if composite_val in allowed_set else "BLOCKED"
            allowed_str = ", ".join(sorted(allowed_set))
            lines.append(
                f"| {strat_name} | {composite_val} | {decision} | {allowed_str} |"
            )
        lines.append("")

    lines.append("---")
    return lines


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------
def load_zerodha_source(api_key: str, api_secret: str, access_token: str):
    """Return a configured ZerodhaDataSource (no symbol chosen yet)."""
    from src.data.sources import ZerodhaDataSource
    from src.data.base import Timeframe
    return ZerodhaDataSource(
        api_key=api_key,
        api_secret=api_secret,
        access_token=access_token,
        default_symbol="RELIANCE",
        default_timeframe=Timeframe.DAILY,
        default_days=365,
        exchange="NSE",
    )


def fetch_symbol_df(
    symbol: str,
    z_source,
    timeframe,
    start: datetime,
    end: datetime,
    fallback_dfs: dict[str, pd.DataFrame],
) -> Optional[pd.DataFrame]:
    """
    Fetch OHLCV for `symbol`.  Tries live Zerodha first, then falls back
    to any pre-loaded DataFrames in `fallback_dfs`.
    Returns None if all attempts fail.
    """
    # strip .NS if present (KiteInstrumentMapper handles this internally,
    # but let's be explicit so normalisation logs are clean)
    bare = symbol.replace(".NS", "")

    # --- Attempt 1: live Kite API ---
    if z_source is not None:
        try:
            df = z_source.fetch_historical(bare, timeframe, start, end)
            if df is not None and not df.empty:
                return df
        except Exception as exc:
            warn(f"    Kite fetch failed for {bare}: {exc}")

    # --- Attempt 2: fallback DataFrames (from CSVs) ---
    if fallback_dfs:
        # Use the first/only fallback (typically RELIANCE data) as a proxy.
        # In a real run without API credentials, data is identical for every
        # symbol — good enough to validate the full pipeline end-to-end.
        first_df = next(iter(fallback_dfs.values()))
        warn(f"    Using CSV fallback data for {bare}")
        return first_df.copy()

    return None


def load_csv_fallbacks() -> dict[str, pd.DataFrame]:
    """
    Load any Kite-sourced or standard CSV files found in data/.
    Returns a dict mapping filename stem -> DataFrame.
    """
    from src.data.provider_factory import ProviderFactory

    candidates = [
        ROOT / "data" / "RELIANCE_KITE_1D.csv",
        ROOT / "data" / "TCS_KITE_1D.csv",
        ROOT / "data" / "RELIANCE_1D.csv",
    ]
    loaded: dict[str, pd.DataFrame] = {}
    factory = ProviderFactory.from_config()
    for csv_path in candidates:
        if not csv_path.exists():
            continue
        try:
            src = factory.create(
                "indian_csv",
                data_file=str(csv_path.relative_to(ROOT)),
            )
            df = src.load()
            loaded[csv_path.stem] = df
            info(f"  Loaded CSV fallback: {csv_path.name} ({len(df)} bars)")
        except Exception as exc:
            warn(f"  Could not load {csv_path.name}: {exc}")
    return loaded


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def export_results(
    all_rows: list[dict],
    top_n: int,
    output_dir: Path,
    args: argparse.Namespace,
    start_time: float,
    regime_snap: Optional[Any] = None,
    regime_filter_active: bool = False,
    regime_skipped: int = 0,
) -> dict[str, Path]:
    """Write all_results.csv, top_ranked.csv, and summary.md."""
    output_dir.mkdir(parents=True, exist_ok=True)
    elapsed = time.time() - start_time
    exports: dict[str, Path] = {}

    if not all_rows:
        warn("No results to export — all backtests failed.")
        return exports

    df_all = pd.DataFrame(all_rows)

    # -----------------------------------------------------------------------
    # all_results.csv — every symbol x strategy combination
    # -----------------------------------------------------------------------
    all_path = output_dir / "all_results.csv"
    df_all.to_csv(all_path, index=False)
    ok(f"Written: {all_path}  ({len(df_all)} rows)")
    exports["all_results"] = all_path

    # -----------------------------------------------------------------------
    # Filter by min_trades threshold, then rank by score
    # -----------------------------------------------------------------------
    df_valid = df_all[df_all["num_trades"].fillna(0) >= MIN_TRADES].copy()
    df_valid.sort_values("score", ascending=False, inplace=True)

    # -----------------------------------------------------------------------
    # top_ranked.csv — best N combinations
    # -----------------------------------------------------------------------
    top_path = output_dir / "top_ranked.csv"
    df_top = df_valid.head(top_n)
    df_top.to_csv(top_path, index=False)
    ok(f"Written: {top_path}  ({len(df_top)} rows)")
    exports["top_ranked"] = top_path

    # -----------------------------------------------------------------------
    # Best strategy per symbol
    # -----------------------------------------------------------------------
    best_per_symbol = (
        df_valid.sort_values("score", ascending=False)
        .drop_duplicates(subset="symbol")
        .sort_values("score", ascending=False)
    )

    # -----------------------------------------------------------------------
    # Best symbols per strategy
    # -----------------------------------------------------------------------
    best_per_strategy: dict[str, pd.DataFrame] = {}
    for strat in df_valid["strategy"].unique():
        sub = df_valid[df_valid["strategy"] == strat].head(5)
        best_per_strategy[strat] = sub

    # -----------------------------------------------------------------------
    # summary.md
    # -----------------------------------------------------------------------
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines: list[str] = []
    lines.append("# NIFTY 50 Research Run Summary")
    lines.append("")
    lines.append(f"**Run date:** {now_str}  ")
    lines.append(f"**Elapsed:** {elapsed:.1f}s  ")
    lines.append(f"**Interval:** {args.interval}  ")
    lines.append(f"**Look-back:** {args.days} days  ")
    lines.append(f"**Strategy arguments:** {', '.join(args.strategy)}  ")
    lines.append(f"**Package arguments:** {', '.join(args.package)}  ")
    lines.append(f"**Optimised:** {'Yes' if args.optimize else 'No'}  ")
    lines.append(f"**Total results:** {len(df_all)} ({len(df_valid)} passed min-trades filter)  ")
    if regime_filter_active:
        lines.append(f"**Regime-filtered (skipped):** {regime_skipped}  ")
    regime_label = regime_snap.composite_regime.value if regime_snap is not None else "N/A"
    lines.append(f"**Market regime:** {regime_label}  ")
    lines.append("")
    lines.append("---")

    # -- Score formula
    lines.append("")
    lines.append("## Scoring Formula")
    lines.append("")
    lines.append("```")
    lines.append(
        f"score = Sharpe x {SHARPE_W} "
        f"+ total_return_pct x {RETURN_W} "
        f"- |max_drawdown_pct| x {DRAWDOWN_P}"
    )
    lines.append(f"Minimum trades required: {MIN_TRADES}")
    lines.append("```")
    lines.append("")
    lines.append("---")

    # -- Market regime (optional) ------------------------------------------
    if regime_snap is not None:
        lines.extend(_regime_md_section(
            regime_snap,
            filter_active=regime_filter_active,
            regime_skipped=regime_skipped,
        ))

    # -- Overall top N
    lines.append("")
    lines.append(f"## Top {min(top_n, len(df_top))} Overall (by Score)")
    lines.append("")
    display_cols = [
        "symbol", "strategy", "score",
        "sharpe_ratio", "total_return_pct", "max_drawdown_pct",
        "num_trades", "win_rate", "profit_factor",
    ]
    avail_cols = [c for c in display_cols if c in df_top.columns]
    lines.append(_df_to_md(df_top[avail_cols].head(top_n)))
    lines.append("")
    lines.append("---")

    # -- Best strategy per symbol
    lines.append("")
    lines.append("## Best Strategy Per Symbol")
    lines.append("")
    bps_cols = [c for c in display_cols if c in best_per_symbol.columns]
    lines.append(_df_to_md(best_per_symbol[bps_cols]))
    lines.append("")
    lines.append("---")

    # -- Best symbols per strategy
    for strat_name, sub_df in best_per_strategy.items():
        lines.append("")
        lines.append(f"## Top Symbols for Strategy: {strat_name.upper()}")
        lines.append("")
        bss_cols = [c for c in display_cols if c in sub_df.columns]
        lines.append(_df_to_md(sub_df[bss_cols]))
        lines.append("")
        lines.append("---")

    # -- Failed symbols
    failed_symbols = [
        r["symbol"] for r in all_rows if r.get("num_trades") is None
    ]
    if failed_symbols:
        lines.append("")
        lines.append("## Failed / No-Trade Symbols")
        lines.append("")
        lines.append("The following symbols produced no actionable backtest result:")
        for sym in sorted(set(failed_symbols)):
            lines.append(f"- {sym}")
        lines.append("")

    md_path = output_dir / "summary.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    ok(f"Written: {md_path}")
    exports["summary"] = md_path
    return exports


def _df_to_md(df: pd.DataFrame) -> str:
    """Convert a DataFrame to a Markdown table string."""
    if df.empty:
        return "_No data._"

    def _fmt(v: Any) -> str:
        if v is None or (isinstance(v, float) and v != v):
            return "N/A"
        if isinstance(v, float):
            return f"{v:.4f}"
        return str(v)

    header = "| " + " | ".join(str(c) for c in df.columns) + " |"
    sep    = "| " + " | ".join("---" for _ in df.columns) + " |"
    rows   = [
        "| " + " | ".join(_fmt(v) for v in row) + " |"
        for row in df.itertuples(index=False, name=None)
    ]
    return "\n".join([header, sep] + rows)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    args = parse_args()
    enforce_runtime_safety(
        RunMode.RESEARCH,
        explicit_enable_flag=True,
        execution_requested=False,
    )
    start_time = time.time()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    section("NIFTY 50 ZERODHA RESEARCH RUNNER")
    info(f"Interval     : {args.interval}")
    info(f"Look-back    : {args.days} days")
    info(f"Strategy     : {', '.join(args.strategy)}")
    info(f"Package      : {', '.join(args.package)}")
    info(f"Optimize     : {args.optimize}")
    info(f"Symbols limit: {args.symbols_limit or 'all'}")
    info(f"Top-N        : {args.top_n}")
    info(f"Backtest fee : {args.fee_rate:.6f} (fraction)")
    info(f"Backtest slip: {args.slippage_rate:.6f} (fraction)")
    info(f"Regime detect: {getattr(args, 'include_regime', False)}")
    info(f"Regime filter: {getattr(args, 'regime_filter', False)}")
    info(f"Regime anlys : {getattr(args, 'regime_analysis', False)}")
    info(f"Regime policy: {getattr(args, 'build_regime_policy', False)}")
    info(f"Walk-forward : {getattr(args, 'walk_forward_regime', False)}")
    if getattr(args, "walk_forward_regime", False):
        info(f"  train-days : {args.train_days}")
        info(f"  test-days  : {args.test_days}")
        info(f"  step-days  : {args.step_days}")
    info(f"Rel strength : {getattr(args, 'top_n_symbols', 0) > 0}")
    if getattr(args, "top_n_symbols", 0) > 0:
        info(f"  top-n      : {args.top_n_symbols}")
        info(f"  lookback   : {args.relative_strength_lookback}")
        info(f"  benchmark  : {args.benchmark_symbol or 'none'}")
    info(f"Portfolio bt : {getattr(args, 'portfolio_backtest', False)}")
    if getattr(args, "portfolio_backtest", False):
        info(f"  max-pos    : {args.max_positions}")
    info(f"Risk mgmt    : {getattr(args, 'enable_risk_management', False)}")
    if getattr(args, "enable_risk_management", False):
        info(f"  max-risk   : {args.max_risk_per_trade:.2%}")
        info(f"  max-exp    : {args.max_portfolio_exposure:.2%}")
        info(f"  max-dd     : {args.max_drawdown:.2%}")
        info(f"  max-pos    : {args.max_concurrent_positions}")
    info(f"Exec realism : {getattr(args, 'execution_realism', False)}")
    if getattr(args, "execution_realism", False):
        info(f"  comm-bps   : {args.commission_bps:.1f}")
        info(f"  slip-bps   : {args.slippage_bps:.1f}")
        info(f"  next-bar   : {getattr(args, 'use_next_bar_fill', True)}")
        info("  note       : commission/slippage bps apply only to execution-realism analysis")
    info(f"Output dir   : {output_dir.resolve()}")

    # -----------------------------------------------------------------------
    # Build base BacktestConfig
    # -----------------------------------------------------------------------
    from src.utils.config import BacktestConfig, ExecutionMode

    base_config = BacktestConfig(
        initial_capital=args.initial_capital,
        fee_rate=args.fee_rate,
        slippage_rate=args.slippage_rate,
        execution_mode=ExecutionMode.NEXT_BAR_OPEN,
        close_positions_at_end=True,
    )

    # -----------------------------------------------------------------------
    # Strategy registry
    # -----------------------------------------------------------------------
    selected = build_strategy_registry(strategies=args.strategy, packages=args.package)
    ok(f"Loaded {len(selected)} strategy definitions: {list(selected)}")

    # -----------------------------------------------------------------------
    # Universe
    # -----------------------------------------------------------------------
    section("LOADING NIFTY 50 UNIVERSE")
    from src.data.nse_universe import NSEUniverseLoader

    loader = NSEUniverseLoader()
    symbols_ns = loader.get_universe("nifty50")   # returns ['ADANIENT.NS', ...]
    # Convert to bare tradingsymbols (Zerodha / NSE format, no .NS suffix)
    symbols = [s.replace(".NS", "") for s in symbols_ns]

    if args.symbols_limit and args.symbols_limit > 0:
        symbols = symbols[: args.symbols_limit]
        warn(f"Symbol limit applied: using {len(symbols)} of {len(symbols_ns)} symbols")
    ok(f"Universe loaded: {len(symbols)} symbols")
    info(f"Symbols: {', '.join(symbols)}")

    # -----------------------------------------------------------------------
    # Data source setup
    # -----------------------------------------------------------------------
    section("DATA SOURCE SETUP")
    timeframe = interval_to_timeframe(args.interval)
    end_dt    = datetime.now()
    start_dt  = end_dt - timedelta(days=args.days)

    api_key      = os.getenv("ZERODHA_API_KEY",      "").strip()
    api_secret   = os.getenv("ZERODHA_API_SECRET",   "").strip()
    access_token = os.getenv("ZERODHA_ACCESS_TOKEN", "").strip()

    z_source = None
    if all([api_key, api_secret, access_token]):
        try:
            z_source = load_zerodha_source(api_key, api_secret, access_token)
            ok("Live Zerodha Kite API configured")
        except Exception as exc:
            warn(f"Could not create ZerodhaDataSource: {exc}")
            warn("Falling back to CSV data")
    else:
        warn("ZERODHA_* env vars not set - will use CSV fallback data")

    fallback_dfs = load_csv_fallbacks()
    if not fallback_dfs and z_source is None:
        fail("No data source available - set ZERODHA_* vars or add CSV files to data/")
        sys.exit(1)

    if z_source is not None:
        info(f"Primary source : Live Zerodha Kite API  (interval={args.interval}, days={args.days})")
    else:
        info(f"Primary source : CSV fallback  ({list(fallback_dfs)})")

    # -----------------------------------------------------------------------
    # Market regime detection (optional --include-regime flag)
    # -----------------------------------------------------------------------
    regime_snap = None
    if getattr(args, "include_regime", False):
        section("MARKET REGIME DETECTION")
        # Use the first symbol as a market proxy (e.g. RELIANCE or HDFCBANK
        # as NIFTY constituent); fall back to CSV data if live API fails.
        regime_symbol = symbols[0] if symbols else "RELIANCE"
        info(f"Detecting regime using {regime_symbol} as market proxy ...")
        regime_df = fetch_symbol_df(regime_symbol, z_source, timeframe, start_dt, end_dt, fallback_dfs)
        if regime_df is not None and not regime_df.empty:
            regime_snap = detect_market_regime(regime_df, symbol=regime_symbol)
            if regime_snap is not None:
                ok(f"Composite regime : {regime_snap.composite_regime.value}")
                ok(f"Trend regime     : {regime_snap.trend_regime.value}")
                ok(f"Vol regime       : {regime_snap.volatility_regime.value}")
                if regime_snap.trend_score is not None:
                    ok(f"Trend score      : {regime_snap.trend_score:+.4f}")
                if regime_snap.realized_volatility is not None:
                    ok(f"Annualized vol   : {regime_snap.realized_volatility*100:.2f}%")
            else:
                warn("Regime detection returned None — summary will omit regime section")
        else:
            warn(f"Could not load data for regime symbol {regime_symbol}")

    # -----------------------------------------------------------------------
    # Activate regime filter (optional --regime-filter flag)
    # -----------------------------------------------------------------------
    regime_filter_active = getattr(args, "regime_filter", False)
    if regime_filter_active and not getattr(args, "include_regime", False):
        warn("--regime-filter requires --include-regime; filter disabled for this run")
        regime_filter_active = False
    if regime_filter_active and regime_snap is None:
        warn("Regime detection failed; --regime-filter disabled for this run")
        regime_filter_active = False

    # Pre-compute composite value string once (safe even when regime_snap is None)
    composite_value = (
        regime_snap.composite_regime.value if regime_snap is not None else "unknown"
    )

    if regime_filter_active:
        section("REGIME FILTER PREVIEW")
        info(f"Active composite regime : {composite_value}")
        for sn in selected:
            allowed_flag, reason = is_strategy_allowed(sn, composite_value)
            status = "ALLOWED" if allowed_flag else "BLOCKED"
            info(f"  {sn:<12} -> {status}  ({reason})")

    # -----------------------------------------------------------------------
    # Regime analysis flag (orthogonal to --include-regime / --regime-filter)
    # When active: detect regime per-symbol for accurate historical tagging.
    # -----------------------------------------------------------------------
    regime_analysis_active = getattr(args, "regime_analysis", False)
    if regime_analysis_active:
        info(
            "Regime analysis enabled: regime_label will be detected per-symbol "
            "from each symbol's own OHLCV data (end-of-period snapshot)."
        )

    # -----------------------------------------------------------------------
    # Regime policy build flag (requires --regime-analysis)
    # When active: build a deterministic strategy selection policy from the
    # aggregated regime analysis results after the backtest loop.
    # -----------------------------------------------------------------------
    build_regime_policy_active = getattr(args, "build_regime_policy", False)
    if build_regime_policy_active and not regime_analysis_active:
        warn(
            "--build-regime-policy requires --regime-analysis; "
            "enabling --regime-analysis automatically."
        )
        regime_analysis_active = True
    policy_output_path: Optional[Path] = (
        Path(args.policy_output)
        if getattr(args, "policy_output", None)
        else Path("research") / "regime_policy.json"
    )

    # -----------------------------------------------------------------------
    # Walk-forward regime validation flag (auto-enables --regime-analysis)
    # When active: run rolling train/test walk-forward policy validation
    # after the backtest loop.  Symbol DataFrames are cached during the loop.
    # -----------------------------------------------------------------------
    walk_forward_active = getattr(args, "walk_forward_regime", False)
    if walk_forward_active and not regime_analysis_active:
        warn(
            "--walk-forward-regime requires --regime-analysis; "
            "enabling --regime-analysis automatically."
        )
        regime_analysis_active = True

    # Cache pre-fetched DataFrames for walk-forward (populated in loop below)
    symbols_df_cache: dict[str, Any] = {}

    # -----------------------------------------------------------------------
    # Main research loop
    # -----------------------------------------------------------------------
    section("RUNNING BACKTESTS")
    all_rows: list[dict] = []
    total_combos = len(symbols) * len(selected)
    combo_num    = 0
    skipped      = 0
    regime_skipped = 0

    for sym_idx, symbol in enumerate(symbols):
        print(f"\n  [{sym_idx + 1}/{len(symbols)}] {symbol}")

        # Fetch data for this symbol
        df = fetch_symbol_df(symbol, z_source, timeframe, start_dt, end_dt, fallback_dfs)
        if df is None or df.empty:
            warn(f"    No data for {symbol} - skipping all strategies")
            skipped += len(selected)
            continue

        info(f"    Data: {len(df)} bars  ({df.index[0]} -> {df.index[-1]})")

        # Cache DataFrame for walk-forward validation (when active)
        if walk_forward_active:
            symbols_df_cache[symbol] = df

        # -------------------------------------------------------------------
        # Per-symbol regime label for result row tagging
        #
        # --regime-analysis: detect regime from THIS symbol's own OHLCV data
        #   → accurate historical label for each symbol's test period
        # --include-regime only: reuse the global (first-symbol) regime label
        #   → preserves original single-regime-per-run behaviour
        # Neither flag: no regime_label added to rows
        # -------------------------------------------------------------------
        sym_regime_label = "unknown"   # safe default used only when analysis active
        if regime_analysis_active:
            sym_snap = detect_market_regime(df, symbol=symbol)
            if sym_snap is not None:
                sym_regime_label = sym_snap.composite_regime.value
                info(
                    f"    Regime ({symbol}): {sym_regime_label} "
                    f"| trend={sym_snap.trend_regime.value} "
                    f"| vol={sym_snap.volatility_regime.value}"
                )
            else:
                warn(f"    Regime detection failed for {symbol}; label set to 'unknown'")
        elif regime_snap is not None:
            # --include-regime only: uniform label from first-symbol detection
            sym_regime_label = composite_value

        # Run each strategy
        for strat_name, strat_def in selected.items():
            combo_num += 1

            # --- Regime gate (active only when --regime-filter was given) ---
            if regime_filter_active:
                allowed_flag, filter_reason = is_strategy_allowed(strat_name, composite_value)
                if not allowed_flag:
                    print(
                        f"    ({combo_num}/{total_combos}) Strategy: {strat_name}"
                        f"  -> SKIPPED [{filter_reason}]"
                    )
                    regime_skipped += 1
                    continue

            print(f"    ({combo_num}/{total_combos}) Strategy: {strat_name}", end="  ", flush=True)

            if args.optimize:
                row = run_optimized(
                    symbol=symbol,
                    df=df,
                    strategy_name=strat_name,
                    strategy_class=strat_def["class"],
                    param_grid=strat_def["param_grid"],
                    base_config=base_config,
                    output_dir=output_dir,
                )
            else:
                row = run_single(
                    symbol=symbol,
                    df=df,
                    strategy_name=strat_name,
                    strategy_class=strat_def["class"],
                    params=strat_def["params"],
                    base_config=base_config,
                )

            if row is not None:
                # Tag regime_label when any regime detection was active.
                # When --regime-analysis: per-symbol label (most precise).
                # When --include-regime only: global label (original behaviour).
                if regime_analysis_active or regime_snap is not None:
                    row["regime_label"] = sym_regime_label
                all_rows.append(row)
                trades = row.get("num_trades", 0) or 0
                score  = row.get("score", float("nan"))
                print(f"-> trades={trades}  score={score:.3f}")
            else:
                print("-> FAILED")
                skipped += 1

    # -----------------------------------------------------------------------
    # Results summary (console)
    # -----------------------------------------------------------------------
    section("RESULTS SUMMARY")
    info(f"Total combinations attempted : {total_combos}")
    info(f"Successful results           : {len(all_rows)}")
    info(f"Regime-filtered (skipped)    : {regime_skipped}")
    info(f"Backtest failures / no data  : {skipped}")

    if all_rows:
        df_all = pd.DataFrame(all_rows)
        df_valid = df_all[df_all["num_trades"].fillna(0) >= MIN_TRADES].copy()
        df_valid.sort_values("score", ascending=False, inplace=True)

        print(f"\n  {'Rank':<5} {'Symbol':<16} {'Strategy':<12} {'Score':>8} "
              f"{'Sharpe':>8} {'Return%':>9} {'MaxDD%':>8} {'Trades':>7}")
        print(f"  {'-'*75}")
        for rank, (_, row) in enumerate(df_valid.head(args.top_n).iterrows(), 1):
            ret_pct = (row.get('total_return_pct') or 0.0) * 100
            dd_pct  = abs((row.get('max_drawdown_pct') or 0.0)) * 100
            sharpe  = row.get('sharpe_ratio') or 0.0
            trades  = int(row.get('num_trades') or 0)
            score   = row.get('score') or 0.0
            print(
                f"  {rank:<5} {row['symbol']:<16} {row['strategy']:<12} "
                f"{score:>8.3f} {sharpe:>8.3f} {ret_pct:>8.1f}% "
                f"{dd_pct:>7.1f}% {trades:>7}"
            )

    # -----------------------------------------------------------------------
    # Regime-segmented analysis (optional --regime-analysis flag)
    # -----------------------------------------------------------------------
    if regime_analysis_active and all_rows:
        section("REGIME ANALYSIS")
        from src.research.regime_analysis import generate_regime_report as _gen_report

        regime_report_path = Path("research") / "regime_validation.md"
        report_meta: dict = {
            "interval":         args.interval,
            "days":             args.days,
            "symbols_tested":   len(symbols),
            "strategies":       ", ".join(list(selected.keys())),
            "regime_label_scope": "per-symbol end-of-period composite regime",
            "output_dir":       str(output_dir),
        }
        try:
            df_rows = pd.DataFrame(all_rows)
            valid_labelled = df_rows[df_rows["regime_label"].notna()] if "regime_label" in df_rows.columns else pd.DataFrame()

            # Console distribution preview
            if not valid_labelled.empty:
                dist = valid_labelled.groupby("regime_label").size()
                info("Regime distribution across all result rows:")
                for regime_val, count in dist.items():
                    info(f"  {regime_val:<22} {count} run(s)")
            else:
                warn("No regime labels found in result rows - report will be minimal")

            _gen_report(df_rows, output_path=regime_report_path, metadata=report_meta)
            ok(f"Regime analysis report: {regime_report_path.resolve()}")
        except Exception as exc:
            warn(f"Regime analysis failed: {exc}")
    elif regime_analysis_active and not all_rows:
        warn("--regime-analysis enabled but no results produced; skipping report")

    # -----------------------------------------------------------------------
    # Regime policy build (optional --build-regime-policy flag)
    # Requires --regime-analysis to have populated all_rows with regime labels.
    # -----------------------------------------------------------------------
    if build_regime_policy_active and all_rows:
        section("REGIME POLICY BUILD")
        from src.research.regime_analysis import analyze_by_regime as _analyze
        from src.decision.regime_policy import (
            RegimePolicyBuilder as _Builder,
            generate_policy_report as _gen_policy_report,
        )

        policy_md_path = policy_output_path.with_suffix(".md")
        policy_meta: dict = {
            "interval":       args.interval,
            "days":           args.days,
            "symbols_tested": len(symbols),
            "strategies":     ", ".join(list(selected.keys())),
            "source_report":  "research/regime_validation.md",
        }
        try:
            df_rows_policy = pd.DataFrame(all_rows)
            agg_df = _analyze(df_rows_policy)

            builder = _Builder()
            policy = builder.build(
                agg_df,
                source_description=(
                    f"Built from {len(symbols)} NIFTY symbols, "
                    f"{args.interval} interval, {args.days} days"
                ),
                metadata=policy_meta,
            )

            # JSON artifact
            policy.save_json(policy_output_path)
            ok(f"Regime policy JSON  : {policy_output_path.resolve()}")

            # Markdown report
            _gen_policy_report(policy, output_path=policy_md_path)
            ok(f"Regime policy report: {policy_md_path.resolve()}")

            # Console summary
            info("Policy summary:")
            for label, entry in sorted(policy.entries.items()):
                trade_flag = "TRADE" if entry.should_trade else "NO-TRADE"
                pref = entry.preferred_strategy or "none"
                allow = ", ".join(entry.allowed_strategies) or "none"
                info(f"  [{trade_flag:<8}] {label:<22} preferred={pref:<12} allowed=[{allow}]")

        except Exception as exc:
            warn(f"Regime policy build failed: {exc}")

    elif build_regime_policy_active and not all_rows:
        warn("--build-regime-policy enabled but no results produced; skipping policy build")

    # -----------------------------------------------------------------------
    # Regime policy walk-forward validation (optional --walk-forward-regime)
    # Requires: symbols_df_cache populated during the loop above.
    # Policy is built only from train-window data (no lookahead guaranteed).
    # -----------------------------------------------------------------------
    if walk_forward_active and symbols_df_cache:
        section("REGIME POLICY WALK-FORWARD VALIDATION")
        from src.research.regime_walk_forward import (
            run_regime_policy_walk_forward as _run_wf,
            summarize_walk_forward_results as _summarize_wf,
            generate_walk_forward_report   as _gen_wf_report,
        )

        wf_train_days = args.train_days
        wf_test_days  = args.test_days
        wf_step_days  = args.step_days
        min_required  = wf_train_days + wf_test_days

        info(f"Walk-forward parameters: train={wf_train_days}, test={wf_test_days}, step={wf_step_days}")
        info(f"Symbols with cached data: {len(symbols_df_cache)}")

        # Warn if any symbol has insufficient bars
        insufficient = [
            sym for sym, df in symbols_df_cache.items()
            if len(df) < min_required
        ]
        if insufficient:
            warn(
                f"{len(insufficient)} symbol(s) have fewer than {min_required} bars "
                f"and may yield no windows: {insufficient[:5]}"
                + (" ..." if len(insufficient) > 5 else "")
            )

        wf_report_path = Path("research") / "regime_walk_forward.md"
        wf_meta: dict = {
            "interval":       args.interval,
            "days":           args.days,
            "symbols_tested": len(symbols_df_cache),
            "strategies":     ", ".join(list(selected.keys())),
            "train_days":     wf_train_days,
            "test_days":      wf_test_days,
            "step_days":      wf_step_days,
        }

        try:
            wf_records = _run_wf(
                symbols_data=symbols_df_cache,
                strategies=selected,
                train_days=wf_train_days,
                test_days=wf_test_days,
                step_days=wf_step_days,
                base_config=base_config,
            )

            if wf_records:
                wf_summary = _summarize_wf(wf_records)
                hit_rate   = wf_summary.get("policy_hit_rate")
                hit_str    = f"{hit_rate*100:.1f}%" if hit_rate is not None else "N/A"
                ok(f"Walk-forward records    : {len(wf_records)}")
                ok(f"Windows completed       : {wf_summary.get('total_windows', 0)}")
                ok(f"Policy hit rate         : {hit_str}")
                info(f"  Correct calls        : {wf_summary.get('correct_calls', 0)} / {wf_summary.get('total_records', 0)}")
                info(f"  Should-trade         : {wf_summary.get('should_trade_records', 0)}")
                info(f"  No-trade decisions   : {wf_summary.get('no_trade_records', 0)}")
                by_regime_wf = wf_summary.get("by_regime", {})
                if by_regime_wf:
                    info("  Hit rate by regime:")
                    for rl, d in sorted(by_regime_wf.items()):
                        hr = d.get("hit_rate")
                        hr_s = f"{hr*100:.1f}%" if hr is not None else "N/A"
                        info(f"    {rl:<22} {d['correct']}/{d['total']} ({hr_s})")

                _gen_wf_report(wf_records, output_path=wf_report_path, metadata=wf_meta)
                ok(f"Walk-forward report     : {wf_report_path.resolve()}")
            else:
                warn(
                    "Walk-forward produced no records. "
                    f"Ensure each symbol has >= {min_required} bars "
                    f"(train_days={wf_train_days} + test_days={wf_test_days}). "
                    f"Current --days={args.days}."
                )

        except Exception as exc:
            warn(f"Walk-forward validation failed: {exc}")
            if getattr(args, "verbose", False):
                import traceback as _tb
                _tb.print_exc()

    elif walk_forward_active and not symbols_df_cache:
        warn(
            "--walk-forward-regime enabled but no symbol data was cached "
            "(all symbols may have failed data fetch); skipping walk-forward"
        )

    # -----------------------------------------------------------------------
    # Relative Strength / Top-Stock Selection (optional --top-n-symbols)
    # Ranks all symbols by a composite relative strength score.
    # -----------------------------------------------------------------------
    rs_top_n = getattr(args, "top_n_symbols", 0)
    if rs_top_n and rs_top_n > 0:
        section("RELATIVE STRENGTH ANALYSIS")
        from src.market_intelligence.relative_strength import (
            compute_relative_strength as _compute_rs,
            select_top_symbols as _select_top,
            generate_relative_strength_report as _gen_rs_report,
        )

        _rs_lookback = getattr(args, "relative_strength_lookback", 90)
        _rs_benchmark_sym = getattr(args, "benchmark_symbol", "").strip()

        # Build symbol -> OHLCV dict from cache or re-fetch
        _rs_sym_ohlcv: dict = {}
        for sym in symbols:
            if sym in symbols_df_cache:
                _rs_sym_ohlcv[sym] = symbols_df_cache[sym]
            elif fallback_dfs:
                df_sym = fetch_symbol_df(sym, z_source, timeframe, start_dt, end_dt, fallback_dfs)
                if df_sym is not None and not df_sym.empty:
                    _rs_sym_ohlcv[sym] = df_sym

        if not _rs_sym_ohlcv:
            warn("Relative strength: no OHLCV data available; skipping.")
        else:
            # Optional benchmark series
            _rs_benchmark_series = None
            if _rs_benchmark_sym and _rs_benchmark_sym in _rs_sym_ohlcv:
                _rs_benchmark_series = _rs_sym_ohlcv[_rs_benchmark_sym]["close"]
                info(f"Benchmark series: {_rs_benchmark_sym}")
            elif _rs_benchmark_sym:
                warn(f"Benchmark symbol '{_rs_benchmark_sym}' not in data cache; "
                     "relative_return will be 0.")

            try:
                info(
                    f"Computing relative strength for {len(_rs_sym_ohlcv)} symbols "
                    f"(lookback={_rs_lookback} bars)..."
                )
                rs_df = _compute_rs(
                    symbol_to_ohlcv=_rs_sym_ohlcv,
                    lookback=_rs_lookback,
                    benchmark_series=_rs_benchmark_series,
                )

                if not rs_df.empty:
                    top_syms = _select_top(rs_df, n=rs_top_n)
                    ok(f"Top {rs_top_n} by relative strength: {top_syms}")

                    info("Relative strength ranking:")
                    for rank_i, (_, row) in enumerate(rs_df.head(rs_top_n).iterrows(), 1):
                        sym_name = row.get("symbol", "?")
                        score    = row.get("rolling_strength_score", float("nan"))
                        mom      = row.get("momentum_return", float("nan"))
                        info(
                            f"  {rank_i}. {sym_name:<16} "
                            f"score={score:+.4f}  momentum={mom:+.2%}"
                        )

                    _rs_report_path = Path("research") / "relative_strength_analysis.md"
                    _rs_meta: dict = {
                        "lookback_bars": _rs_lookback,
                        "benchmark_symbol": _rs_benchmark_sym or "none",
                        "symbols_analysed": len(_rs_sym_ohlcv),
                        "top_n_requested": rs_top_n,
                        "interval": args.interval,
                    }
                    _gen_rs_report(rs_df, output_path=_rs_report_path, metadata=_rs_meta)
                    ok(f"Relative strength report: {_rs_report_path.resolve()}")
                else:
                    warn("Relative strength computation produced no results.")

            except Exception as exc:
                warn(f"Relative strength analysis failed: {exc}")
                if getattr(args, "verbose", False):
                    traceback.print_exc()

    # -----------------------------------------------------------------------
    # Portfolio-level backtest (optional --portfolio-backtest flag)
    # Uses the cached symbol DataFrames (populated in loop above).
    # Requires at least one successful backtest result row.
    # -----------------------------------------------------------------------
    portfolio_backtest_active = getattr(args, "portfolio_backtest", False)

    # Ensure symbols_df_cache is populated (reuse walk-forward cache if active,
    # otherwise re-build it from symbols that produced successful results).
    if portfolio_backtest_active and not symbols_df_cache and all_rows:
        info("Building symbol data cache for portfolio backtest (re-fetching)...")
        for row in all_rows:
            sym = row.get("symbol")
            if sym and sym not in symbols_df_cache:
                df_sym = fetch_symbol_df(
                    sym, z_source, timeframe, start_dt, end_dt, fallback_dfs
                )
                if df_sym is not None and not df_sym.empty:
                    symbols_df_cache[sym] = df_sym

    if portfolio_backtest_active and symbols_df_cache:
        section("PORTFOLIO-LEVEL BACKTEST")
        from src.core.data_handler import DataHandler as _DataHandler
        from src.research.portfolio_backtester import (
            PortfolioBacktester as _PBacktester,
            generate_portfolio_report as _gen_portfolio_report,
        )

        # Optionally load the regime policy built earlier in this run.
        _portfolio_policy = None
        if build_regime_policy_active and policy_output_path.exists():
            try:
                from src.decision.regime_policy import RegimePolicy as _RegimePolicy
                _portfolio_policy = _RegimePolicy.load_json(policy_output_path)
                info("Regime policy loaded for portfolio strategy selection")
            except Exception as _exc:
                warn(f"Could not load regime policy for portfolio backtest: {_exc}")

        # Build symbol -> DataHandler mapping from cache
        _sym_to_dh = {
            sym: _DataHandler(df_cached)
            for sym, df_cached in symbols_df_cache.items()
        }

        _max_pos = getattr(args, "max_positions", 10)
        _portfolio_output = str(output_dir / "portfolio")
        _pb = _PBacktester(
            base_config=base_config,
            strategy_registry=selected,
            symbol_to_data=_sym_to_dh,
            max_positions=_max_pos,
            regime_policy=_portfolio_policy,
            output_dir=_portfolio_output,
        )

        info(
            f"Running portfolio backtest: {len(_sym_to_dh)} symbols, "
            f"max_positions={_max_pos}, "
            f"regime_policy={'Yes' if _portfolio_policy else 'No'}"
        )

        try:
            _pb_result = _pb.run()

            ok(f"Portfolio return    : {_pb_result.portfolio_return_pct * 100:.2f}%")
            ok(f"Portfolio Sharpe    : {_pb_result.sharpe_ratio:.4f}")
            ok(f"Portfolio MaxDD     : {_pb_result.max_drawdown_pct * 100:.2f}%")
            ok(f"Portfolio turnover  : {_pb_result.turnover:.2f}x")
            info(f"  Active symbols   : {_pb_result.num_symbols_active}")
            info(f"  Total trades     : {_pb_result.num_trades}")
            info(f"  Win rate         : {_pb_result.win_rate * 100:.1f}%")

            _pb_report_path = Path("research") / "portfolio_backtest.md"
            _pb_meta: dict = {
                "interval":      args.interval,
                "days":          args.days,
                "symbols_tested": len(_sym_to_dh),
                "strategies":    ", ".join(list(selected.keys())),
                "max_positions": _max_pos,
                "regime_policy_used": bool(_portfolio_policy),
            }
            _gen_portfolio_report(
                _pb_result,
                output_path=_pb_report_path,
                metadata=_pb_meta,
            )
            ok(f"Portfolio report    : {_pb_report_path.resolve()}")
            ok(f"Portfolio CSVs      : {_portfolio_output}/")

        except Exception as exc:
            warn(f"Portfolio backtest failed: {exc}")
            if getattr(args, "verbose", False):
                traceback.print_exc()

    elif portfolio_backtest_active and not symbols_df_cache:
        warn(
            "--portfolio-backtest enabled but no symbol data was cached; "
            "ensure at least one symbol fetched data successfully."
        )

    # -----------------------------------------------------------------------
    # Risk engine validation (optional --enable-risk-management flag)
    # Runs post-hoc risk checks against the portfolio equity curve (when
    # --portfolio-backtest was also active) or against an empty curve.
    # Generates research/risk_engine_validation.md.
    # -----------------------------------------------------------------------
    risk_mgmt_active = getattr(args, "enable_risk_management", False)
    if risk_mgmt_active:
        section("RISK ENGINE VALIDATION")
        from src.risk.risk_engine import (
            PortfolioRiskConfig as _RiskCfg,
            validate_portfolio_risk as _validate_risk,
            generate_risk_report as _gen_risk_report,
        )

        _risk_config = _RiskCfg(
            max_risk_per_trade_pct=getattr(args, "max_risk_per_trade", 0.01),
            max_portfolio_exposure_pct=getattr(args, "max_portfolio_exposure", 0.20),
            max_drawdown_pct=getattr(args, "max_drawdown", 0.15),
            max_concurrent_positions=getattr(args, "max_concurrent_positions", 10),
        )

        info(
            f"Risk config  : max_risk={_risk_config.max_risk_per_trade_pct:.2%}  "
            f"max_exposure={_risk_config.max_portfolio_exposure_pct:.2%}  "
            f"max_dd={_risk_config.max_drawdown_pct:.2%}  "
            f"max_pos={_risk_config.max_concurrent_positions}"
        )

        # Use portfolio equity curve from this run if available
        _risk_equity_curve = None
        _pb_res = locals().get("_pb_result")
        if _pb_res is not None:
            try:
                if not _pb_res.portfolio_equity_curve.empty:
                    _risk_equity_curve = _pb_res.portfolio_equity_curve
                    info(
                        f"Equity curve : {len(_risk_equity_curve)} bars "
                        f"(from portfolio backtest)"
                    )
            except Exception:
                pass

        if _risk_equity_curve is None:
            info(
                "No portfolio equity curve available; "
                "risk checks will use an empty curve.  "
                "Run with --portfolio-backtest to validate against real equity."
            )

        try:
            _risk_violations = _validate_risk(
                _risk_equity_curve if _risk_equity_curve is not None else pd.DataFrame(),
                _risk_config,
            )

            if not _risk_violations:
                ok("Validation   : PASS - no violations detected")
            else:
                warn(f"Validation   : {len(_risk_violations)} violation(s) detected")
                for _v in _risk_violations:
                    warn(f"  -> {_v}")

            _risk_report_path = Path("research") / "risk_engine_validation.md"
            _risk_meta: dict = {
                "interval":           args.interval,
                "days":               args.days,
                "symbols_tested":     len(symbols),
                "strategies":         ", ".join(list(selected.keys())),
                "portfolio_backtest": portfolio_backtest_active,
            }
            _gen_risk_report(
                _risk_config,
                _risk_violations,
                equity_curve=_risk_equity_curve,
                output_path=_risk_report_path,
                metadata=_risk_meta,
            )
            ok(f"Risk report  : {_risk_report_path.resolve()}")

        except Exception as exc:
            warn(f"Risk engine validation failed: {exc}")
            if getattr(args, "verbose", False):
                traceback.print_exc()

    # -----------------------------------------------------------------------
    # Execution Realism / Cost Modeling (optional --execution-realism flag)
    # Applies realistic commission + slippage costs to the portfolio trade log
    # and compares gross vs net P&L.  Requires --portfolio-backtest trade log.
    # Generates research/execution_realism.md.
    # -----------------------------------------------------------------------
    exec_realism_active = getattr(args, "execution_realism", False)
    if exec_realism_active:
        section("EXECUTION REALISM / COST MODELING")
        from src.execution import (
            CostConfig as _CostCfg,
            FillConfig as _FillCfg,
            ExecutionCostAnalyzer as _CostAnalyzer,
            generate_execution_report as _gen_exec_report,
        )

        _commission_bps = getattr(args, "commission_bps", 10.0)
        _slippage_bps   = getattr(args, "slippage_bps",   5.0)
        _next_bar_fill  = getattr(args, "use_next_bar_fill", True)

        _exec_cost_cfg = _CostCfg(
            commission_bps=_commission_bps,
            slippage_bps=_slippage_bps,
        )
        _exec_fill_cfg = _FillCfg(use_next_bar_open=_next_bar_fill)

        info(
            f"Cost config  : commission={_commission_bps:.1f} bps, "
            f"slippage={_slippage_bps:.1f} bps, "
            f"fill={'next_bar_open' if _next_bar_fill else 'current_bar_close'}"
        )

        # Pull trade log from this run's portfolio backtest if available
        _exec_trade_log = None
        _exec_initial_capital = args.initial_capital
        _pb_res_exec = locals().get("_pb_result")
        if _pb_res_exec is not None:
            try:
                if not _pb_res_exec.trade_log.empty:
                    _exec_trade_log = _pb_res_exec.trade_log
                    _exec_initial_capital = _pb_res_exec.initial_capital
                    info(f"Trade log    : {len(_exec_trade_log)} trades from portfolio backtest")
            except Exception:
                pass

        if _exec_trade_log is None:
            warn(
                "--execution-realism requires a trade log from --portfolio-backtest. "
                "Run with --portfolio-backtest to enable cost analysis."
            )
        else:
            try:
                _exec_analyzer = _CostAnalyzer(
                    cost_config=_exec_cost_cfg,
                    fill_config=_exec_fill_cfg,
                )
                _exec_records = _exec_analyzer.analyze_trade_log(
                    _exec_trade_log,
                    initial_capital=_exec_initial_capital,
                )

                if _exec_records:
                    # Aggregate summary
                    _total_gross = sum(r.gross_pnl  for r in _exec_records)
                    _total_cost  = sum(r.total_cost for r in _exec_records)
                    _total_net   = sum(r.net_pnl    for r in _exec_records)
                    _cap         = _exec_initial_capital or 1.0
                    ok(f"Gross P&L    : {_total_gross:,.2f}  ({_total_gross / _cap:.2%})")
                    ok(f"Total costs  : {_total_cost:,.2f}  ({_total_cost / _cap:.2%})")
                    ok(f"Net P&L      : {_total_net:,.2f}  ({_total_net / _cap:.2%})")
                    info(f"Cost drag    : {(_total_gross - _total_net) / _cap:.4%} of capital")

                    # Top 5 by gross P&L
                    info("Top groups by gross P&L:")
                    for _r in _exec_records[:5]:
                        info(
                            f"  {_r.symbol:<16} {_r.strategy:<12} "
                            f"gross={_r.gross_return_pct:+.2%}  "
                            f"net={_r.net_return_pct:+.2%}  "
                            f"drag={_r.cost_drag_pct:.4%}"
                        )
                else:
                    warn("No execution cost records produced (trade log may be empty).")

                _exec_report_path = Path("research") / "execution_realism.md"
                _exec_meta: dict = {
                    "interval":           args.interval,
                    "days":               args.days,
                    "symbols_tested":     len(symbols),
                    "strategies":         ", ".join(list(selected.keys())),
                    "commission_bps":     _commission_bps,
                    "slippage_bps":       _slippage_bps,
                    "fill_mode":          "next_bar_open" if _next_bar_fill else "current_bar_close",
                }
                _gen_exec_report(
                    _exec_records,
                    cost_config=_exec_cost_cfg,
                    fill_config=_exec_fill_cfg,
                    output_path=_exec_report_path,
                    metadata=_exec_meta,
                )
                ok(f"Exec report  : {_exec_report_path.resolve()}")

            except Exception as exc:
                warn(f"Execution realism analysis failed: {exc}")
                if getattr(args, "verbose", False):
                    traceback.print_exc()

    # -----------------------------------------------------------------------
    # Export reports
    # -----------------------------------------------------------------------
    section("EXPORTING REPORTS")
    exports = export_results(
        all_rows, args.top_n, output_dir, args, start_time,
        regime_snap=regime_snap,
        regime_filter_active=regime_filter_active,
        regime_skipped=regime_skipped,
    )
    if exports:
        contract = get_artifact_contract(RunMode.RESEARCH)
        _manifest_artifacts: dict[str, str | Path] = dict(exports)
        _manifest_artifacts["run_manifest"] = output_dir / "run_manifest.json"
        _manifest_path = write_output_manifest(
            output_dir=output_dir,
            run_mode=RunMode.RESEARCH,
            provider_name="zerodha",
            artifacts=_manifest_artifacts,
            metadata={
                "interval": args.interval,
                "days": args.days,
                "symbols_limit": args.symbols_limit,
                "execution_realism": bool(args.execution_realism),
                "portfolio_backtest": bool(args.portfolio_backtest),
            },
            contract_id=contract.contract_id,
            expected_artifacts=contract.required_names,
            schema_version=contract.schema_version,
            safety_mode=contract.safety_mode,
        )
        try:
            assert_artifact_contract(
                run_mode=RunMode.RESEARCH,
                output_dir=output_dir,
                manifest_path=_manifest_path,
            )
        except Exception as exc:  # noqa: BLE001
            fail(f"Artifact contract validation failed: {exc}")
            raise SystemExit(1)
        ok(f"Written: {_manifest_path}")

    elapsed = time.time() - start_time
    section("DONE")
    ok(f"Research run completed in {elapsed:.1f}s")
    ok(f"Output directory: {output_dir.resolve()}")
    print()
    print("  +----------------------------------------------------------+")
    print("  |   NIFTY 50 Zerodha Research Runner:  COMPLETE           |")
    print("  +----------------------------------------------------------+")
    print()


# ---------------------------------------------------------------------------
if __name__ == "__main__":
    main()
