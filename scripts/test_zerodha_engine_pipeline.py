#!/usr/bin/env python3
"""
Zerodha -> Engine Pipeline Validation
=====================================
Validates that Zerodha Kite Connect data flows correctly through the full
internal engine pipeline:

  Phase 1 ? Data Provider   : ZerodhaDataSource (live) -> schema check
  Phase 2 ? Strategy Engine : SMACrossoverStrategy bar-by-bar loop
  Phase 3 ? Backtest Engine : BacktestEngine.run() -> PerformanceMetrics

Priority for data loading:
  1. Live Zerodha API        (if ZERODHA_* env vars are set and valid)
  2. Kite-sourced CSV        (saved from smoke tests: RELIANCE_KITE_1D.csv)
  3. Standard CSV fallback   (RELIANCE_1D.csv)

Run: python scripts/test_zerodha_engine_pipeline.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Optional

# -- Project root on sys.path --------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# -- Load .env (ignore if dotenv not installed or file missing) ----------------
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass

import pandas as pd  # noqa: E402 (import after sys.path patch)

# -----------------------------------------------------------------------------
# Console helpers
# -----------------------------------------------------------------------------
DIVIDER = "-" * 54


def section(title: str) -> None:
    print(f"\n{DIVIDER}")
    print(f"  {title}")
    print(DIVIDER)


def ok(msg: str)   -> None: print(f"  [OK]   {msg}")
def warn(msg: str) -> None: print(f"  [WARN] {msg}")
def fail(msg: str) -> None: print(f"  [FAIL] {msg}")


# -----------------------------------------------------------------------------
# PHASE 1 ? DATA PROVIDER TEST
# -----------------------------------------------------------------------------
section("ZERODHA PROVIDER TEST")

df: Optional[pd.DataFrame] = None
active_source = None          # BaseDataSource that produced df
source_description = ""

# -- Attempt 1: Live Zerodha via ZerodhaDataSource ----------------------------
api_key      = os.getenv("ZERODHA_API_KEY",      "").strip()
api_secret   = os.getenv("ZERODHA_API_SECRET",   "").strip()
access_token = os.getenv("ZERODHA_ACCESS_TOKEN", "").strip()

if all([api_key, api_secret, access_token]):
    print("  Credentials found in environment ? attempting live Zerodha fetch ?")
    try:
        from src.data.sources import ZerodhaDataSource
        from src.data.base import Timeframe

        z_source = ZerodhaDataSource(
            api_key=api_key,
            api_secret=api_secret,
            access_token=access_token,
            default_symbol="RELIANCE",
            default_timeframe=Timeframe.DAILY,
            default_days=365,
            exchange="NSE",
        )
        df = z_source.load()
        active_source = z_source
        source_description = "Live Zerodha API  ->  RELIANCE daily (365 days)"
        ok("Live Zerodha fetch succeeded")
    except Exception as exc:
        warn(f"Live Zerodha fetch failed: {exc}")
        warn("Falling back to Kite-sourced CSV ?")
else:
    warn("ZERODHA_ACCESS_TOKEN not configured ? using Kite-sourced CSV data")

# -- Attempt 2: Kite-sourced CSV (saved by smoke test scripts) ----------------
if df is None:
    kite_csv_candidates = [
        ROOT / "data" / "RELIANCE_KITE_1D.csv",
        ROOT / "data" / "TCS_KITE_1D.csv",
        ROOT / "data" / "RELIANCE_KITE_5M.csv",
    ]
    for csv_path in kite_csv_candidates:
        if not csv_path.exists():
            continue
        try:
            from src.data.provider_factory import ProviderFactory
            factory = ProviderFactory.from_config()
            kite_csv_source = factory.create(
                "indian_csv",
                data_file=str(csv_path.relative_to(ROOT)),
            )
            df = kite_csv_source.load()
            active_source = kite_csv_source
            source_description = (
                f"Kite-sourced CSV  ->  {csv_path.name}"
                "  (real Zerodha data saved by smoke tests)"
            )
            ok(f"Loaded Kite-sourced CSV: {csv_path.name}")
            break
        except Exception as exc:
            warn(f"  Could not load {csv_path.name}: {exc}")

# -- Attempt 3: Standard CSV fallback -----------------------------------------
if df is None:
    fallback_path = ROOT / "data" / "RELIANCE_1D.csv"
    try:
        from src.data.provider_factory import ProviderFactory
        factory = ProviderFactory.from_config()
        fallback_source = factory.create(
            "indian_csv",
            data_file=str(fallback_path.relative_to(ROOT)),
        )
        df = fallback_source.load()
        active_source = fallback_source
        source_description = f"Standard CSV fallback  ->  {fallback_path.name}"
        ok(f"Loaded standard CSV fallback: {fallback_path.name}")
    except Exception as exc:
        fail(f"All data sources exhausted: {exc}")
        sys.exit(1)

# -- Data diagnostics ----------------------------------------------------------
print(f"\n  Source      : {source_description}")
print(f"  Shape       : {df.shape}  ({df.shape[0]} bars ? {df.shape[1]} columns)")
print(f"  Columns     : {list(df.columns)}")
print(f"  Index name  : {df.index.name!r}")
print(f"  Index type  : {type(df.index).__name__}")
print(f"  Date range  : {df.index[0]}  ->  {df.index[-1]}")
print(f"\n  First 3 rows:")
print(df.head(3).to_string())

# -- Schema assertions ---------------------------------------------------------
required_cols = {"open", "high", "low", "close", "volume"}
missing = required_cols - set(df.columns)
assert not missing,                     f"Missing OHLCV columns: {missing}"
assert df.index.name == "timestamp",    f"Expected index 'timestamp', got {df.index.name!r}"
assert not df.empty,                    "DataFrame is empty"
assert df.index.is_monotonic_increasing, "Timestamps are not sorted ascending"
ok("Schema assertions passed  (OHLCV OK  index='timestamp' OK  sorted OK  non-empty OK)")


# -----------------------------------------------------------------------------
# PHASE 2 ? STRATEGY EXECUTION TEST
# -----------------------------------------------------------------------------
section("STRATEGY EXECUTION TEST")

from src.strategies.sma_crossover import SMACrossoverStrategy  # noqa: E402
from src.strategies.base_strategy import Signal                 # noqa: E402

FAST_PERIOD = 10
SLOW_PERIOD = 30

signal_strategy = SMACrossoverStrategy(fast_period=FAST_PERIOD, slow_period=SLOW_PERIOD)
signal_strategy.initialize()
ok(f"SMACrossoverStrategy instantiated  (fast={FAST_PERIOD}, slow={SLOW_PERIOD})")

# -- Bar-by-bar signal loop (mirrors BacktestEngine's internal loop) -----------
print(f"\n  Processing {len(df)} bars bar-by-bar ?")
signals: list[Signal] = []
for i in range(len(df)):
    # Engine passes only data up to (and including) current bar ? no lookahead
    available    = df.iloc[: i + 1]
    current_bar  = df.iloc[i]
    sig = signal_strategy.on_bar(available, current_bar, i)
    signals.append(sig)

signal_labels = pd.Series(
    [s.value for s in signals],
    index=df.index,
    name="signal",
)

non_hold = [s for s in signals if s != Signal.HOLD]
counts   = signal_labels.value_counts()

print(f"\n  Signal distribution:")
for sig_name, count in counts.items():
    print(f"    {sig_name:<8}  {count:>5,}")

print(f"\n  Last 10 signals:")
print(signal_labels.tail(10).to_string())

assert len(signals) == len(df), "Signal count does not match bar count"
ok(f"{len(signals):,} bars processed  |  {len(non_hold)} actionable signals generated")


# -----------------------------------------------------------------------------
# PHASE 3 ? BACKTEST ENGINE TEST
# -----------------------------------------------------------------------------
section("BACKTEST ENGINE TEST")

from src.core.data_handler import DataHandler      # noqa: E402
from src.core.backtest_engine import BacktestEngine  # noqa: E402
from src.utils.config import BacktestConfig, ExecutionMode  # noqa: E402

# Fresh strategy instance ? each backtest run must start from a clean state
bt_strategy = SMACrossoverStrategy(fast_period=FAST_PERIOD, slow_period=SLOW_PERIOD)

# Wrap the data source in a DataHandler (calls source.load() internally)
dh = DataHandler.from_source(active_source)
ok(f"DataHandler.from_source() succeeded  ({len(dh)} bars loaded)")

# Minimal BacktestConfig ? defaults handle the rest
config = BacktestConfig(
    initial_capital=100_000.0,
    fee_rate=0.001,           # 0.1%  brokerage
    slippage_rate=0.0005,     # 0.05% slippage
    execution_mode=ExecutionMode.NEXT_BAR_OPEN,
    close_positions_at_end=True,
    strategy_params={"fast_period": FAST_PERIOD, "slow_period": SLOW_PERIOD},
)

engine = BacktestEngine(config, bt_strategy, dh)
ok("BacktestEngine instantiated")

metrics_obj = engine.run()
ok("BacktestEngine.run() completed successfully")

# -- Print performance metrics table ------------------------------------------
m = metrics_obj.metrics   # the internal dict[str, Any]

metric_rows = [
    ("Initial Capital (Rs.)",       m.get("initial_capital"),   ",.2f"),
    ("Final Portfolio Value (Rs.)", m.get("final_value"),       ",.2f"),
    ("Total Return (Rs.)",          m.get("total_return"),      ",.2f"),
    ("Total Return (%)",          m.get("total_return_pct"),  ".2%"),
    ("Annualised Return (%)",     m.get("annualized_return"), ".2%"),
    ("CAGR (%)",                  m.get("cagr"),              ".2%"),
    ("Sharpe Ratio",              m.get("sharpe_ratio"),      ".4f"),
    ("Sortino Ratio",             m.get("sortino_ratio"),     ".4f"),
    ("Max Drawdown (%)",          m.get("max_drawdown_pct"),  ".2%"),
    ("Profit Factor",             m.get("profit_factor"),     ".4f"),
    ("Total Trades",              m.get("num_trades"),        "d"),
    ("Winners",                   m.get("num_winners"),       "d"),
    ("Losers",                    m.get("num_losers"),        "d"),
    ("Win Rate (%)",              m.get("win_rate"),          ".2%"),
    ("Expectancy (Rs.)",            m.get("expectancy"),        ",.2f"),
    ("Avg Trade Return (Rs.)",      m.get("avg_trade_return"),  ",.2f"),
    ("Avg Winner (Rs.)",            m.get("avg_winner"),        ",.2f"),
    ("Avg Loser (Rs.)",             m.get("avg_loser"),         ",.2f"),
    ("Largest Winner (Rs.)",        m.get("largest_winner"),    ",.2f"),
    ("Largest Loser (Rs.)",         m.get("largest_loser"),     ",.2f"),
    ("Total Fees (Rs.)",            m.get("total_fees"),        ",.2f"),
    ("Exposure (%)",              m.get("exposure_pct"),      ".2%"),
]

print(f"\n  {'Metric':<35} {'Value':>18}")
print(f"  {'-' * 53}")
for label, val, fmt in metric_rows:
    try:
        if val is None or (isinstance(val, float) and val != val):   # None or NaN
            formatted = "N/A"
        elif fmt == "d":
            formatted = f"{int(val):>18,}"
        else:
            formatted = f"{val:>18{fmt}}"
    except Exception:
        formatted = f"{str(val):>18}"
    print(f"  {label:<35} {formatted}")

# -- Equity curve summary ------------------------------------------------------
results      = engine.get_results()
equity_curve = results.get("equity_curve")
if equity_curve is not None and not equity_curve.empty:
    eq = equity_curve["equity"]
    print(f"\n  Equity curve  : {len(equity_curve):,} data points")
    print(f"  Start value   : Rs.{eq.iloc[0]:>12,.2f}")
    print(f"  Peak value    : Rs.{eq.max():>12,.2f}")
    print(f"  End value     : Rs.{eq.iloc[-1]:>12,.2f}")
    ok("Equity curve available and non-empty")

# -- Trade log preview ---------------------------------------------------------
trade_log = results.get("trade_log")
# trade_log may be a list of dicts OR a DataFrame depending on engine version
if trade_log is None:
    warn("No trades were executed (strategy may need more warm-up bars)")
elif isinstance(trade_log, pd.DataFrame):
    tl_df = trade_log
    if tl_df.empty:
        warn("No trades were executed (strategy may need more warm-up bars)")
    else:
        for col in ("entry_time", "exit_time"):
            if col in tl_df.columns:
                tl_df = tl_df.copy()
                tl_df[col] = pd.to_datetime(tl_df[col]).dt.strftime("%Y-%m-%d")
        display_cols = [c for c in ["entry_time", "exit_time", "side", "pnl",
                                     "entry_price", "exit_price"] if c in tl_df.columns]
        last_n = min(5, len(tl_df))
        print(f"\n  Trade log (last {last_n} of {len(tl_df)}):")
        print(tl_df[display_cols].tail(last_n).to_string(index=False))
elif isinstance(trade_log, list):
    if not trade_log:
        warn("No trades were executed (strategy may need more warm-up bars)")
    else:
        tl_df = pd.DataFrame(trade_log)
        for col in ("entry_time", "exit_time"):
            if col in tl_df.columns:
                tl_df[col] = pd.to_datetime(tl_df[col]).dt.strftime("%Y-%m-%d")
        display_cols = [c for c in ["entry_time", "exit_time", "side", "pnl",
                                     "entry_price", "exit_price"] if c in tl_df.columns]
        last_n = min(5, len(tl_df))
        print(f"\n  Trade log (last {last_n} of {len(tl_df)}):")
        print(tl_df[display_cols].tail(last_n).to_string(index=False))


# -----------------------------------------------------------------------------
# VALIDATION SUMMARY
# -----------------------------------------------------------------------------
section("VALIDATION SUMMARY")

n_trades = m.get("num_trades", 0)
net_return = m.get("total_return", 0.0)
sharpe = m.get("sharpe_ratio")
sharpe_str = f"{sharpe:.4f}" if sharpe is not None and sharpe == sharpe else "N/A"

print(f"  [OK] Data source       : {source_description}")
print(f"  OK  Bars loaded       : {len(df):,}")
print(f"  OK  Schema validated  : OHLCV columns, 'timestamp' index, sorted")
print(f"  OK  Strategy          : SMACrossoverStrategy"
      f" (fast={FAST_PERIOD}, slow={SLOW_PERIOD})")
print(f"  OK  Signals generated : {len(non_hold)} actionable  /  {len(signals):,} bars")
print(f"  OK  Backtest trades   : {n_trades}")
print(f"  OK  Net P&L           : Rs.{net_return:,.2f}")
print(f"  OK  Sharpe Ratio      : {sharpe_str}")
print()
print("  +-------------------------------------------------------+")
print("  |   Zerodha -> Engine pipeline end-to-end:  PASSED     |")
print("  +-------------------------------------------------------+")
print()
