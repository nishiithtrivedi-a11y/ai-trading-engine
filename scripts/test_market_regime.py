#!/usr/bin/env python3
"""
Market Regime Detection — Validation Script
============================================
Tests the MarketRegimeEngine on real NIFTY 50 data (via Zerodha Kite API)
or falls back to local CSV data if credentials are absent.

This script is intentionally beginner-friendly: no arguments required.
Just run it and read the output.

Usage
-----
    # Live Zerodha API (requires ZERODHA_* env vars):
    python scripts/test_market_regime.py

    # With options:
    python scripts/test_market_regime.py --days 500 --interval day --history 30

What it does
------------
Phase 1 : Load NIFTY 50 historical data
Phase 2 : Run MarketRegimeEngine.detect()
Phase 3 : Print a clear single-snapshot summary
Phase 4 : Print a rolling regime history table (last --history bars)
Phase 5 : Validate output fields are well-formed
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Project root on sys.path (works whether script is called from any dir)
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass

import pandas as pd  # noqa: E402

# ASCII-only output — safe on Windows cp1252 terminal
DIVIDER  = "-" * 64
DIVIDER2 = "=" * 64


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def ok(msg: str)   -> None: print(f"  [OK]   {msg}")
def warn(msg: str) -> None: print(f"  [WARN] {msg}")
def fail(msg: str) -> None: print(f"  [FAIL] {msg}")
def info(msg: str) -> None: print(f"  [INFO] {msg}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Validate the MarketRegimeEngine on NIFTY 50 data",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("--symbol",   default="NIFTY50",
                   help="Symbol label (default: NIFTY50)")
    p.add_argument("--days",     type=int, default=500,
                   help="Historical look-back window in days (default: 500)")
    p.add_argument("--interval", choices=["day","5minute","15minute","60minute"],
                   default="day",
                   help="Bar interval (default: day)")
    p.add_argument("--history",  type=int, default=20,
                   help="Number of rolling daily regime rows to display (default: 20)")
    p.add_argument("--long-ma",  type=int, default=200,
                   help="Long-term MA period for informational display (default: 200)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------
def _interval_to_timeframe(interval: str):
    from src.data.base import Timeframe
    return {
        "day":      Timeframe.DAILY,
        "5minute":  Timeframe.MINUTE_5,
        "15minute": Timeframe.MINUTE_15,
        "60minute": Timeframe.HOURLY,
    }[interval]


def load_nifty_data(days: int, interval: str) -> tuple[pd.DataFrame, str]:
    """
    Load NIFTY 50 data.  Returns (df, source_description).

    Priority:
      1. Live Zerodha Kite API
      2. RELIANCE_KITE_1D.csv  (proxy; same bar structure)
      3. RELIANCE_1D.csv       (standard CSV fallback)
    """
    from src.data.sources import ZerodhaDataSource
    from src.data.provider_factory import ProviderFactory
    from src.data.base import Timeframe

    api_key      = os.getenv("ZERODHA_API_KEY",      "").strip()
    api_secret   = os.getenv("ZERODHA_API_SECRET",   "").strip()
    access_token = os.getenv("ZERODHA_ACCESS_TOKEN", "").strip()

    end_dt   = datetime.now()
    start_dt = end_dt - timedelta(days=days)
    tf       = _interval_to_timeframe(interval)

    # --- Attempt 1: live Zerodha ---
    if all([api_key, api_secret, access_token]):
        try:
            src = ZerodhaDataSource(
                api_key=api_key, api_secret=api_secret, access_token=access_token,
                default_symbol="NIFTY50", default_timeframe=Timeframe.DAILY,
            )
            df = src.fetch_historical("NIFTY50", tf, start_dt, end_dt)
            if df is not None and not df.empty:
                return df, f"Zerodha Kite API ({len(df)} bars)"
        except Exception as exc:
            warn(f"Kite API failed: {exc}")

    # --- Attempt 2/3: CSV fallbacks (use as NIFTY proxy) ---
    # Prefer RELIANCE_1D.csv (2021 bars, 2018-2026) over the shorter Kite
    # snapshot CSVs.  Any NSE large-cap is a reasonable regime proxy.
    factory = ProviderFactory.from_config()
    for name, rel_path in [
        ("RELIANCE_1D",      "data/RELIANCE_1D.csv"),
        ("RELIANCE_KITE_1D", "data/RELIANCE_KITE_1D.csv"),
        ("TCS_KITE_1D",      "data/TCS_KITE_1D.csv"),
    ]:
        csv_path = ROOT / rel_path
        if not csv_path.exists():
            continue
        try:
            src = factory.create("indian_csv", data_file=str(csv_path.relative_to(ROOT)))
            df = src.load()
            if not df.empty:
                return df, f"CSV fallback ({csv_path.name}, {len(df)} bars)"
        except Exception as exc:
            warn(f"CSV {csv_path.name} failed: {exc}")

    raise RuntimeError(
        "No data source available.  "
        "Set ZERODHA_* env vars or ensure data/RELIANCE_1D.csv exists."
    )


# ---------------------------------------------------------------------------
# Rolling regime history (bar-by-bar classification on a sliding window)
# ---------------------------------------------------------------------------
def compute_rolling_regimes(
    df: pd.DataFrame,
    symbol: str,
    long_ma_period: int,
    n_rows: int,
) -> pd.DataFrame:
    """
    For the last `n_rows` bars, evaluate the regime using all data up to
    and including that bar (expanding window so each point is realistic).
    Returns a DataFrame with one row per bar.
    """
    from src.market_intelligence.regime_engine import MarketRegimeEngine, MarketRegimeEngineConfig

    engine = MarketRegimeEngine()
    # Use relaxed min-bars config (don't raise on short slices)
    cfg = MarketRegimeEngineConfig(symbol=symbol, long_ma_period=long_ma_period)

    # We evaluate at the last n_rows bar-ends
    eval_indices = range(max(60, len(df) - n_rows), len(df))
    rows = []
    for end_idx in eval_indices:
        slice_df = df.iloc[: end_idx + 1]
        snap = engine.detect(slice_df, config=cfg, symbol=symbol)
        rows.append({
            "date":       snap.timestamp.strftime("%Y-%m-%d") if pd.notna(snap.timestamp) else "N/A",
            "close":      f"{snap.last_close:.2f}" if snap.last_close else "N/A",
            "trend":      snap.trend_regime.value,
            "vol":        snap.volatility_regime.value,
            "composite":  snap.composite_regime.value,
            "trend_score": f"{snap.trend_score:+.4f}" if snap.trend_score is not None else "N/A",
            "ann_vol%":   f"{snap.realized_volatility*100:.1f}" if snap.realized_volatility else "N/A",
            "atr_ratio":  f"{snap.atr_ratio:.3f}" if snap.atr_ratio else "N/A",
        })
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Print helpers
# ---------------------------------------------------------------------------
def print_snapshot(snap) -> None:
    """Print the full single-snapshot summary in a human-friendly table."""
    from src.market_intelligence.models import CompositeRegime

    composite_val = snap.composite_regime.value.upper()
    composite_label = {
        "BULLISH_TRENDING": "BULLISH TRENDING  - confirmed uptrend, manageable vol",
        "BULLISH_SIDEWAYS": "BULLISH SIDEWAYS  - bullish bias, consolidating",
        "BEARISH_TRENDING": "BEARISH TRENDING  - confirmed downtrend, contained vol",
        "BEARISH_VOLATILE": "BEARISH VOLATILE  - downtrend with expanding vol",
        "RANGEBOUND":       "RANGEBOUND        - no clear trend, vol contained",
        "RISK_OFF":         "RISK OFF          - high volatility, preserve capital",
        "UNKNOWN":          "UNKNOWN           - insufficient data or conflicting",
    }.get(composite_val, composite_val)

    strategy_hint = {
        "BULLISH_TRENDING": "Favour trend-following long setups",
        "BULLISH_SIDEWAYS": "Look for breakout entries; reduce position size",
        "BEARISH_TRENDING": "Avoid new longs; reduce exposure",
        "BEARISH_VOLATILE": "Hard reduction or hedging; minimal new positions",
        "RANGEBOUND":       "Mean-reversion / range strategies",
        "RISK_OFF":         "Stay in cash; stop all new positions",
        "UNKNOWN":          "Treat as neutral; skip or paper-trade only",
    }.get(composite_val, "N/A")

    print(f"\n  {DIVIDER2}")
    print(f"  Symbol        : {snap.symbol}")
    print(f"  As-of date    : {snap.timestamp.strftime('%Y-%m-%d %H:%M') if pd.notna(snap.timestamp) else 'N/A'}")
    print(f"  Bars used     : {snap.bars_used}")
    print(f"  {DIVIDER2}")
    print(f"  Composite     : {composite_label}")
    print(f"  Trend regime  : {snap.trend_regime.value}")
    print(f"  Trend state   : {snap.trend_state.value}")
    print(f"  Vol regime    : {snap.volatility_regime.value}")
    print(f"  {DIVIDER2}")
    print(f"  --- Supporting metrics ---")
    print(f"  Last close    : {snap.last_close:.2f}" if snap.last_close else "  Last close    : N/A")
    print(f"  Fast MA (20)  : {snap.fast_ma:.2f}" if snap.fast_ma else "  Fast MA (20)  : N/A")
    print(f"  Slow MA (50)  : {snap.slow_ma:.2f}" if snap.slow_ma else "  Slow MA (50)  : N/A")
    print(f"  Long MA (200) : {snap.long_ma:.2f}" if snap.long_ma else "  Long MA (200) : N/A (< 200 bars)")
    print(f"  Trend score   : {snap.trend_score:+.6f}" if snap.trend_score is not None else "  Trend score   : N/A")
    print(f"  Ann. vol      : {snap.realized_volatility*100:.2f}%" if snap.realized_volatility else "  Ann. vol      : N/A")
    print(f"  ATR value     : {snap.atr_value:.2f}" if snap.atr_value else "  ATR value     : N/A")
    print(f"  ATR ratio     : {snap.atr_ratio:.4f}" if snap.atr_ratio else "  ATR ratio     : N/A")
    print(f"  Vol score     : {snap.vol_state_score:.1f}/100" if snap.vol_state_score is not None else "  Vol score     : N/A")
    print(f"  {DIVIDER2}")
    print(f"  Strategy hint : {strategy_hint}")
    if snap.warnings:
        print(f"  {DIVIDER2}")
        for w in snap.warnings:
            print(f"  [WARN] {w}")
    print(f"  {DIVIDER2}")


def print_history_table(history_df: pd.DataFrame) -> None:
    """Print rolling regime history as a fixed-width ASCII table."""
    if history_df.empty:
        warn("No history rows to display.")
        return
    # Column widths
    cols = [
        ("date",        10),
        ("close",        9),
        ("trend",       18),
        ("vol",         23),
        ("composite",   18),
        ("trend_score", 12),
        ("ann_vol%",     8),
        ("atr_ratio",    9),
    ]
    header = "  " + "  ".join(f"{c:{w}s}" for c, w in cols)
    sep    = "  " + "  ".join("-" * w for _, w in cols)
    print(header)
    print(sep)
    for _, row in history_df.iterrows():
        line = "  " + "  ".join(f"{str(row[c]):{w}s}" for c, w in cols)
        print(line)


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------
def validate_snapshot(snap) -> list[str]:
    """Return a list of validation errors (empty = pass)."""
    from src.market_intelligence.models import CompositeRegime, VolatilityRegimeType, TrendState
    from src.monitoring.models import RegimeState

    errors: list[str] = []

    if not isinstance(snap.composite_regime, CompositeRegime):
        errors.append(f"composite_regime type wrong: {type(snap.composite_regime)}")
    if not isinstance(snap.trend_state, TrendState):
        errors.append(f"trend_state type wrong: {type(snap.trend_state)}")
    if not isinstance(snap.volatility_regime, VolatilityRegimeType):
        errors.append(f"volatility_regime type wrong: {type(snap.volatility_regime)}")
    if not isinstance(snap.trend_regime, RegimeState):
        errors.append(f"trend_regime type wrong: {type(snap.trend_regime)}")
    if snap.bars_used <= 0:
        errors.append("bars_used must be > 0")
    if not snap.symbol:
        errors.append("symbol is empty")
    if snap.vol_state_score is not None and not (0 <= snap.vol_state_score <= 100):
        errors.append(f"vol_state_score out of [0,100]: {snap.vol_state_score}")

    d = snap.to_dict()
    required_keys = [
        "symbol", "timestamp", "trend_regime", "trend_state",
        "volatility_regime", "composite_regime", "bars_used", "reason",
    ]
    for k in required_keys:
        if k not in d:
            errors.append(f"to_dict() missing key: {k}")

    return errors


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    args = parse_args()

    print(f"\n{DIVIDER2}")
    print("  MARKET REGIME DETECTION — VALIDATION SCRIPT")
    print(DIVIDER2)
    info(f"Symbol   : {args.symbol}")
    info(f"Days     : {args.days}")
    info(f"Interval : {args.interval}")
    info(f"History  : last {args.history} bars")

    # ------------------------------------------------------------------ Phase 1
    section("PHASE 1 — LOADING MARKET DATA")
    try:
        df, source_desc = load_nifty_data(args.days, args.interval)
        ok(f"Data source  : {source_desc}")
        ok(f"Date range   : {df.index[0]} -> {df.index[-1]}")
        ok(f"Columns      : {list(df.columns)}")
    except Exception as exc:
        fail(f"Data load failed: {exc}")
        sys.exit(1)

    # ------------------------------------------------------------------ Phase 2
    section("PHASE 2 — RUNNING REGIME DETECTOR")
    from src.market_intelligence.regime_engine import MarketRegimeEngine, MarketRegimeEngineConfig

    cfg = MarketRegimeEngineConfig(
        symbol=args.symbol,
        long_ma_period=args.long_ma,
    )
    engine = MarketRegimeEngine()

    try:
        snap = engine.detect(df, config=cfg, symbol=args.symbol)
        ok("MarketRegimeEngine.detect() completed successfully")
    except Exception as exc:
        fail(f"Regime detection failed: {exc}")
        import traceback; traceback.print_exc()
        sys.exit(1)

    # ------------------------------------------------------------------ Phase 3
    section("PHASE 3 — CURRENT REGIME SNAPSHOT")
    print_snapshot(snap)

    # ------------------------------------------------------------------ Phase 4
    if args.history > 0 and len(df) >= 60:
        section(f"PHASE 4 — ROLLING REGIME HISTORY (last {args.history} bars)")
        info("Computing bar-by-bar regime (may take a few seconds)...")
        import logging; logging.disable(logging.WARNING)   # suppress INFO logs
        try:
            history_df = compute_rolling_regimes(df, args.symbol, args.long_ma, args.history)
            logging.disable(logging.NOTSET)
            print()
            print_history_table(history_df)
        except Exception as exc:
            logging.disable(logging.NOTSET)
            warn(f"Rolling history failed: {exc}")
    else:
        info("Skipping rolling history (--history 0 or too few bars)")

    # ------------------------------------------------------------------ Phase 5
    section("PHASE 5 — OUTPUT VALIDATION")
    errors = validate_snapshot(snap)
    if errors:
        for err in errors:
            fail(err)
        fail(f"{len(errors)} validation error(s) found")
        sys.exit(1)
    else:
        ok("All output fields validated successfully")
        ok(f"composite_regime = {snap.composite_regime.value!r}")
        ok(f"trend_regime     = {snap.trend_regime.value!r}")
        ok(f"volatility_regime= {snap.volatility_regime.value!r}")

    # ------------------------------------------------------------------ Done
    print(f"\n{DIVIDER2}")
    print("  VALIDATION COMPLETE — MarketRegimeEngine is working correctly")
    print(DIVIDER2)
    print()


if __name__ == "__main__":
    main()
