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
        "--strategies", nargs="+",
        choices=["sma", "rsi", "breakout"],
        default=["sma", "rsi", "breakout"],
        help="Which strategies to run (default: all three).",
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
    return p.parse_args()


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
def build_strategy_registry(optimize: bool) -> dict[str, dict[str, Any]]:
    """
    Returns a dict keyed by strategy short name containing:
      class      - the strategy class
      params     - default parameters for single-run mode
      param_grid - grid for StrategyOptimizer (used when --optimize)
    """
    from src.strategies.sma_crossover import SMACrossoverStrategy
    from src.strategies.rsi_reversion import RSIReversionStrategy
    from src.strategies.breakout import BreakoutStrategy

    return {
        "sma": {
            "class": SMACrossoverStrategy,
            "params": {"fast_period": 20, "slow_period": 50},
            "param_grid": {
                "fast_period": [10, 20],
                "slow_period": [30, 50, 100],
            },
        },
        "rsi": {
            "class": RSIReversionStrategy,
            "params": {"rsi_period": 14, "oversold": 30, "overbought": 70},
            "param_grid": {
                "rsi_period": [14],
                "oversold":   [25, 30],
                "overbought": [70, 75],
            },
        },
        "breakout": {
            "class": BreakoutStrategy,
            "params": {"entry_period": 20, "exit_period": 10},
            "param_grid": {
                "entry_period": [20, 40],
                "exit_period":  [10, 15],
            },
        },
    }


# ---------------------------------------------------------------------------
# Composite ranking score
# ---------------------------------------------------------------------------
SHARPE_W    = 1.0   # sharpe_ratio weight
RETURN_W    = 100.0 # total_return_pct weight  (decimal, e.g. 0.12 for 12%)
DRAWDOWN_P  = 50.0  # max_drawdown_pct penalty (decimal)
MIN_TRADES  = 3     # minimum trades required to be included in ranking


def compute_score(row: dict[str, Any]) -> float:
    sharpe   = row.get("sharpe_ratio")    or 0.0
    ret      = row.get("total_return_pct") or 0.0
    dd       = row.get("max_drawdown_pct") or 0.0
    # drawdown is stored as a negative fraction (e.g. -0.25 for 25% dd)
    # apply penalty on magnitude
    score = (SHARPE_W * sharpe) + (RETURN_W * ret) - (DRAWDOWN_P * abs(dd))
    return round(score, 6)


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


def _regime_md_section(snap: Any) -> list[str]:
    """Render a MarketRegimeSnapshot as Markdown lines for summary.md."""
    lines: list[str] = []
    lines.append("")
    lines.append("## Market Regime (at time of research run)")
    lines.append("")
    lines.append(f"| Field | Value |")
    lines.append(f"| --- | --- |")
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
) -> None:
    """Write all_results.csv, top_ranked.csv, and summary.md."""
    output_dir.mkdir(parents=True, exist_ok=True)
    elapsed = time.time() - start_time

    if not all_rows:
        warn("No results to export — all backtests failed.")
        return

    df_all = pd.DataFrame(all_rows)

    # -----------------------------------------------------------------------
    # all_results.csv — every symbol x strategy combination
    # -----------------------------------------------------------------------
    all_path = output_dir / "all_results.csv"
    df_all.to_csv(all_path, index=False)
    ok(f"Written: {all_path}  ({len(df_all)} rows)")

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
    lines.append(f"**Strategies tested:** {', '.join(args.strategies)}  ")
    lines.append(f"**Optimised:** {'Yes' if args.optimize else 'No'}  ")
    lines.append(f"**Total results:** {len(df_all)} ({len(df_valid)} passed min-trades filter)  ")
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
        lines.extend(_regime_md_section(regime_snap))

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
    start_time = time.time()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    section("NIFTY 50 ZERODHA RESEARCH RUNNER")
    info(f"Interval     : {args.interval}")
    info(f"Look-back    : {args.days} days")
    info(f"Strategies   : {', '.join(args.strategies)}")
    info(f"Optimize     : {args.optimize}")
    info(f"Symbols limit: {args.symbols_limit or 'all'}")
    info(f"Top-N        : {args.top_n}")
    info(f"Regime detect: {getattr(args, 'include_regime', False)}")
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
    registry = build_strategy_registry(args.optimize)
    selected = {k: v for k, v in registry.items() if k in args.strategies}
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
    # Main research loop
    # -----------------------------------------------------------------------
    section("RUNNING BACKTESTS")
    all_rows: list[dict] = []
    total_combos = len(symbols) * len(selected)
    combo_num    = 0
    skipped      = 0

    for sym_idx, symbol in enumerate(symbols):
        print(f"\n  [{sym_idx + 1}/{len(symbols)}] {symbol}")

        # Fetch data for this symbol
        df = fetch_symbol_df(symbol, z_source, timeframe, start_dt, end_dt, fallback_dfs)
        if df is None or df.empty:
            warn(f"    No data for {symbol} - skipping all strategies")
            skipped += len(selected)
            continue

        info(f"    Data: {len(df)} bars  ({df.index[0]} -> {df.index[-1]})")

        # Run each strategy
        for strat_name, strat_def in selected.items():
            combo_num += 1
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
    info(f"Skipped / failed             : {skipped}")

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
    # Export reports
    # -----------------------------------------------------------------------
    section("EXPORTING REPORTS")
    export_results(all_rows, args.top_n, output_dir, args, start_time, regime_snap=regime_snap)

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
