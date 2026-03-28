#!/usr/bin/env python3
"""
Phase 4–6 Trade Diagnostics & Regime Comparison
================================================
Reads the outputs of the 60-day regime validation run and the 20-day baseline,
produces all Phase 5 deliverables and writes Phase 6 judgment to summary.md.

No strategy logic, no engine changes — pure analysis on CSV outputs.

Usage:
    python scripts/analyze_trade_diagnostics.py

Outputs (all written to output/intraday_tf_regime_validation/):
    trade_log.csv               — cleaned combined trade log
    regime_comparison.csv       — 20d vs 60d aggregate metrics
    period_comparison.csv       — per-period metric table
    per_symbol_metrics.csv      — per-symbol aggregated trade stats
    exit_reason_breakdown.csv   — exit reason distribution
    time_of_day.csv             — hourly entry P&L profile
    weekday_effects.csv         — Monday–Friday P&L profile
    holding_time.csv            — holding duration distribution
    failures.csv                — copied from run output (or empty)
    summary.json                — machine-readable summary
    summary.md                  — human-readable Phase 6 judgment
    run_manifest.json           — updated manifest
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

BASELINE_DIR  = ROOT / "output" / "intraday_tf_nifty50_5m_20d_practical"
EXTENDED_DIR  = ROOT / "output" / "intraday_tf_regime_validation"
PORTFOLIO_DIR = EXTENDED_DIR / "portfolio"
OUT_DIR       = EXTENDED_DIR           # all Phase-5 outputs land here

WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def load_csv(path: Path, label: str) -> pd.DataFrame:
    if not path.exists():
        print(f"  [WARN] {label} not found: {path}")
        return pd.DataFrame()
    df = pd.read_csv(path)
    print(f"  [OK]   {label}: {len(df)} rows from {path.name}")
    return df


def sharpe(returns: pd.Series, ann: int = 252) -> float:
    if len(returns) < 2 or returns.std() == 0:
        return float("nan")
    return float(returns.mean() / returns.std() * (ann ** 0.5))


def fmt_pct(v) -> str:
    try:
        return f"{float(v)*100:.2f}%"
    except Exception:
        return str(v)


def fmt_f(v, decimals=4) -> str:
    try:
        return f"{float(v):.{decimals}f}"
    except Exception:
        return str(v)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------

def load_trade_log() -> pd.DataFrame:
    candidates = [
        PORTFOLIO_DIR / "portfolio_trades.csv",
        EXTENDED_DIR  / "portfolio_trades.csv",
        EXTENDED_DIR  / "portfolio" / "portfolio_trades.csv",
    ]
    for p in candidates:
        if p.exists():
            df = pd.read_csv(p, parse_dates=["entry_timestamp", "exit_timestamp"])
            print(f"  [OK]   Trade log: {len(df)} trades from {p}")
            return df
    print("  [WARN] No portfolio_trades.csv found — trade-level analysis skipped")
    return pd.DataFrame()


def load_results(directory: Path, label: str) -> pd.DataFrame:
    p = directory / "all_results.csv"
    df = load_csv(p, f"all_results ({label})")
    if not df.empty:
        df["_window"] = label
    return df


# ---------------------------------------------------------------------------
# Trade log enrichment
# ---------------------------------------------------------------------------

def enrich_trades(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()

    # Ensure datetime
    for col in ("entry_timestamp", "exit_timestamp"):
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], utc=False, errors="coerce")

    # Holding minutes (compute if not present or recompute for accuracy)
    if "entry_timestamp" in df.columns and "exit_timestamp" in df.columns:
        df["holding_minutes"] = (
            (df["exit_timestamp"] - df["entry_timestamp"])
            .dt.total_seconds()
            .div(60)
            .round(1)
        )

    # Entry time features
    if "entry_timestamp" in df.columns:
        df["entry_hour"]    = df["entry_timestamp"].dt.hour
        df["entry_minute"]  = df["entry_timestamp"].dt.minute
        df["entry_hhmm"]    = df["entry_timestamp"].dt.strftime("%H:%M")
        df["entry_weekday"] = df["entry_timestamp"].dt.dayofweek   # 0=Mon
        df["entry_day_name"]= df["entry_timestamp"].dt.day_name()
        df["entry_date"]    = df["entry_timestamp"].dt.date

    # Session windows  (IST: 09:15–15:30)
    if "entry_hour" in df.columns:
        def session_label(row):
            h, m = row["entry_hour"], row["entry_minute"]
            if (h == 9 and m <= 45) or (h == 9 and m >= 15):
                return "open_30min"
            if h < 11:
                return "morning"
            if h < 13:
                return "midday"
            if h < 14:
                return "afternoon"
            return "close_90min"
        df["session"] = df.apply(session_label, axis=1)

    # Winner / loser
    if "net_pnl" in df.columns:
        df["is_winner"] = df["net_pnl"] > 0

    return df


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------

def exit_reason_breakdown(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "exit_reason" not in df.columns:
        return pd.DataFrame()
    grp = df.groupby("exit_reason").agg(
        count          = ("net_pnl", "count"),
        total_pnl      = ("net_pnl", "sum"),
        mean_pnl       = ("net_pnl", "mean"),
        win_rate       = ("is_winner", "mean"),
        avg_holding_min= ("holding_minutes", "mean"),
        pct_of_trades  = ("net_pnl", "count"),
    ).reset_index()
    grp["pct_of_trades"] = grp["pct_of_trades"] / grp["pct_of_trades"].sum() * 100
    grp = grp.sort_values("count", ascending=False).reset_index(drop=True)
    return grp


def time_of_day_profile(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "entry_hour" not in df.columns:
        return pd.DataFrame()
    # Group by HH:MM bucket (5-min bars → group by 15-min slots)
    df = df.copy()
    df["slot"] = df["entry_hhmm"]
    grp = df.groupby("slot").agg(
        count      = ("net_pnl", "count"),
        total_pnl  = ("net_pnl", "sum"),
        mean_pnl   = ("net_pnl", "mean"),
        win_rate   = ("is_winner", "mean"),
        avg_holding= ("holding_minutes", "mean"),
    ).reset_index()
    grp = grp.sort_values("slot").reset_index(drop=True)
    return grp


def weekday_profile(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "entry_weekday" not in df.columns:
        return pd.DataFrame()
    grp = df.groupby("entry_weekday").agg(
        count     = ("net_pnl", "count"),
        total_pnl = ("net_pnl", "sum"),
        mean_pnl  = ("net_pnl", "mean"),
        win_rate  = ("is_winner", "mean"),
    ).reset_index()
    grp["day_name"] = grp["entry_weekday"].map(
        {0:"Mon", 1:"Tue", 2:"Wed", 3:"Thu", 4:"Fri"}
    )
    grp = grp.sort_values("entry_weekday").reset_index(drop=True)
    return grp


def holding_time_profile(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "holding_minutes" not in df.columns:
        return pd.DataFrame()
    bins = [0, 5, 15, 30, 60, 120, 240, float("inf")]
    labels = ["<5m", "5–15m", "15–30m", "30–60m", "1–2h", "2–4h", ">4h"]
    df = df.copy()
    df["bucket"] = pd.cut(df["holding_minutes"], bins=bins, labels=labels, right=False)
    grp = df.groupby("bucket", observed=True).agg(
        count     = ("net_pnl", "count"),
        total_pnl = ("net_pnl", "sum"),
        mean_pnl  = ("net_pnl", "mean"),
        win_rate  = ("is_winner", "mean"),
    ).reset_index()
    return grp


def per_symbol_metrics(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "symbol" not in df.columns:
        return pd.DataFrame()
    grp = df.groupby("symbol").agg(
        total_trades  = ("net_pnl", "count"),
        total_pnl     = ("net_pnl", "sum"),
        mean_pnl      = ("net_pnl", "mean"),
        win_rate      = ("is_winner", "mean"),
        avg_hold_min  = ("holding_minutes", "mean"),
        pct_stop_loss = ("exit_reason", lambda x: (x == "stop_loss").mean()),
        pct_session   = ("exit_reason", lambda x: (x.str.contains("session|close|eod", case=False, na=False)).mean()),
    ).reset_index()
    grp = grp.sort_values("total_pnl").reset_index(drop=True)
    return grp


def session_profile(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty or "session" not in df.columns:
        return pd.DataFrame()
    grp = df.groupby("session").agg(
        count     = ("net_pnl", "count"),
        total_pnl = ("net_pnl", "sum"),
        mean_pnl  = ("net_pnl", "mean"),
        win_rate  = ("is_winner", "mean"),
    ).reset_index()
    return grp


def regime_comparison(df_20d: pd.DataFrame, df_60d: pd.DataFrame) -> pd.DataFrame:
    """Build side-by-side comparison of 20-day vs 60-day aggregate metrics."""
    rows = []
    for label, df in [("20d_bearish_baseline", df_20d), ("60d_extended", df_60d)]:
        if df.empty:
            continue
        r = {
            "window"          : label,
            "symbols"         : df["symbol"].nunique() if "symbol" in df.columns else 0,
            "total_trades"    : int(df["num_trades"].sum()) if "num_trades" in df.columns else 0,
            "mean_sharpe"     : df["sharpe_ratio"].mean() if "sharpe_ratio" in df.columns else float("nan"),
            "median_sharpe"   : df["sharpe_ratio"].median() if "sharpe_ratio" in df.columns else float("nan"),
            "mean_return_pct" : df["total_return_pct"].mean() if "total_return_pct" in df.columns else float("nan"),
            "median_return_pct": df["total_return_pct"].median() if "total_return_pct" in df.columns else float("nan"),
            "mean_max_dd_pct" : df["max_drawdown_pct"].mean() if "max_drawdown_pct" in df.columns else float("nan"),
            "mean_win_rate"   : df["win_rate"].mean() if "win_rate" in df.columns else float("nan"),
            "positive_return_rate": (df["total_return_pct"] > 0).mean() if "total_return_pct" in df.columns else float("nan"),
            "regime_labels"   : ", ".join(sorted(df["regime_label"].unique())) if "regime_label" in df.columns else "unknown",
        }
        rows.append(r)
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Phase 6 Judgment
# ---------------------------------------------------------------------------

def write_summary_md(
    out_dir: Path,
    trades: pd.DataFrame,
    results_20d: pd.DataFrame,
    results_60d: pd.DataFrame,
    exit_df: pd.DataFrame,
    tod_df: pd.DataFrame,
    wday_df: pd.DataFrame,
    hold_df: pd.DataFrame,
    sym_df: pd.DataFrame,
    regime_cmp: pd.DataFrame,
    session_df: pd.DataFrame,
) -> dict:
    """Write summary.md and return summary dict."""

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")

    # ---- Aggregate metrics ------------------------------------------------
    has_trades = not trades.empty
    n_trades   = len(trades) if has_trades else 0
    win_rate   = float(trades["is_winner"].mean()) if has_trades and "is_winner" in trades.columns else float("nan")
    mean_pnl   = float(trades["net_pnl"].mean()) if has_trades else float("nan")
    total_pnl  = float(trades["net_pnl"].sum()) if has_trades else float("nan")
    avg_hold   = float(trades["holding_minutes"].mean()) if has_trades and "holding_minutes" in trades.columns else float("nan")

    # Exit reason
    if has_trades and "exit_reason" in trades.columns:
        er_counts = trades["exit_reason"].value_counts()
        top_exit  = er_counts.index[0] if len(er_counts) else "unknown"
        stop_loss_pct = float((trades["exit_reason"] == "stop_loss").mean()) if "stop_loss" in trades["exit_reason"].values else 0.0
        session_pct   = float(trades["exit_reason"].str.contains("session|close|eod|end_of_day", case=False, na=False).mean())
    else:
        top_exit, stop_loss_pct, session_pct = "unknown", float("nan"), float("nan")

    # Regime comparison headline
    if not regime_cmp.empty and len(regime_cmp) >= 2:
        r20 = regime_cmp[regime_cmp["window"].str.startswith("20d")].iloc[0]
        r60 = regime_cmp[regime_cmp["window"].str.startswith("60d")].iloc[0]
        sharpe_delta  = float(r60["mean_sharpe"]) - float(r20["mean_sharpe"])
        return_delta  = float(r60["mean_return_pct"]) - float(r20["mean_return_pct"])
    else:
        r20 = r60 = None
        sharpe_delta = return_delta = float("nan")

    # ---- Judgment --------------------------------------------------------
    # Evaluate each diagnostic dimension
    stop_loss_dominant = (not np.isnan(stop_loss_pct)) and stop_loss_pct > 0.40
    session_dominant   = (not np.isnan(session_pct)) and session_pct > 0.40
    low_win_rate       = (not np.isnan(win_rate)) and win_rate < 0.30
    very_low_win_rate  = (not np.isnan(win_rate)) and win_rate < 0.20

    # Does 60d improve over 20d?
    if not np.isnan(sharpe_delta):
        extended_improves = sharpe_delta > 0.05
        extended_worse    = sharpe_delta < -0.05
    else:
        extended_improves = extended_worse = False

    # Overall verdict
    structural_weakness_signals = sum([
        very_low_win_rate,
        stop_loss_dominant,
        not extended_improves,
    ])
    regime_driven_signals = sum([
        session_dominant and not stop_loss_dominant,
        not very_low_win_rate,
        extended_improves,
    ])

    if structural_weakness_signals >= 2:
        verdict = "STRUCTURAL_WEAKNESS"
    elif regime_driven_signals >= 2:
        verdict = "REGIME_DRIVEN"
    else:
        verdict = "AMBIGUOUS"

    next_step_map = {
        "STRUCTURAL_WEAKNESS": "exit-logic review → stop-loss calibration → parameter review before optimization",
        "REGIME_DRIVEN"       : "walk-forward regime validation → parameter optimization when regime turns bullish",
        "AMBIGUOUS"           : "exit-logic review to disambiguate, then walk-forward",
    }
    next_step = next_step_map[verdict]

    # ---- Write markdown --------------------------------------------------
    lines = [
        f"# Intraday Trend Following — Regime Validation Report",
        f"",
        f"**Generated:** {now_str}  ",
        f"**Strategy:** intraday_trend_following  ",
        f"**Interval:** 5-minute  ",
        f"**Universe:** NIFTY 50 (53 symbols)  ",
        f"**Windows tested:** 20-day baseline (bearish), 60-day extended  ",
        f"",
        f"---",
        f"",
        f"## 1. Regime Comparison (20d vs 60d)",
        f"",
    ]

    if not regime_cmp.empty:
        lines.append("| Metric | 20d Baseline | 60d Extended |")
        lines.append("|--------|-------------|-------------|")
        if r20 is not None and r60 is not None:
            lines.append(f"| Symbols | {int(r20.get('symbols',0))} | {int(r60.get('symbols',0))} |")
            lines.append(f"| Total Trades | {int(r20.get('total_trades',0))} | {int(r60.get('total_trades',0))} |")
            lines.append(f"| Mean Sharpe | {fmt_f(r20.get('mean_sharpe'))} | {fmt_f(r60.get('mean_sharpe'))} |")
            lines.append(f"| Median Sharpe | {fmt_f(r20.get('median_sharpe'))} | {fmt_f(r60.get('median_sharpe'))} |")
            lines.append(f"| Mean Return% | {fmt_pct(r20.get('mean_return_pct'))} | {fmt_pct(r60.get('mean_return_pct'))} |")
            lines.append(f"| Mean MaxDD% | {fmt_pct(r20.get('mean_max_dd_pct'))} | {fmt_pct(r60.get('mean_max_dd_pct'))} |")
            lines.append(f"| Mean Win Rate | {fmt_pct(r20.get('mean_win_rate'))} | {fmt_pct(r60.get('mean_win_rate'))} |")
            lines.append(f"| +ve Return Rate | {fmt_pct(r20.get('positive_return_rate'))} | {fmt_pct(r60.get('positive_return_rate'))} |")
            lines.append(f"| Regime Labels | {r20.get('regime_labels','?')} | {r60.get('regime_labels','?')} |")
    else:
        lines.append("_60d results not yet available._")

    lines += [
        f"",
        f"> **Sharpe delta (60d − 20d):** {fmt_f(sharpe_delta)}  ",
        f"> **Return delta (60d − 20d):** {fmt_pct(return_delta)}  ",
        f"",
        f"---",
        f"",
        f"## 2. Trade-Level Diagnostics (60-day portfolio run)",
        f"",
        f"**Total trades captured:** {n_trades}  ",
        f"**Overall win rate:** {fmt_pct(win_rate)}  ",
        f"**Mean P&L per trade:** ₹{mean_pnl:.1f}  " if not np.isnan(mean_pnl) else "**Mean P&L:** N/A  ",
        f"**Total P&L (portfolio):** ₹{total_pnl:.1f}  " if not np.isnan(total_pnl) else "",
        f"**Average holding time:** {avg_hold:.1f} min  " if not np.isnan(avg_hold) else "",
        f"",
        f"### 2a. Exit Reason Breakdown",
        f"",
    ]

    if not exit_df.empty:
        lines.append("| Exit Reason | Count | % of Trades | Win Rate | Mean P&L | Avg Hold (min) |")
        lines.append("|-------------|-------|-------------|----------|----------|----------------|")
        for _, row in exit_df.iterrows():
            lines.append(
                f"| {row['exit_reason']} | {int(row['count'])} "
                f"| {row['pct_of_trades']:.1f}% "
                f"| {fmt_pct(row.get('win_rate',0))} "
                f"| ₹{row.get('mean_pnl',0):.1f} "
                f"| {row.get('avg_holding_min',0):.1f} |"
            )
        lines.append("")
        if stop_loss_pct > 0:
            lines.append(f"> Stop-loss exits account for **{stop_loss_pct*100:.1f}%** of all trades.")
        if session_pct > 0:
            lines.append(f"> Session/EOD forced exits account for **{session_pct*100:.1f}%** of all trades.")
    else:
        lines.append("_Trade log not available._")

    lines += [
        f"",
        f"### 2b. Holding Time Distribution",
        f"",
    ]
    if not hold_df.empty:
        lines.append("| Duration Bucket | Count | Win Rate | Mean P&L |")
        lines.append("|----------------|-------|----------|----------|")
        for _, row in hold_df.iterrows():
            lines.append(
                f"| {row['bucket']} | {int(row['count'])} "
                f"| {fmt_pct(row.get('win_rate',0))} "
                f"| ₹{row.get('mean_pnl',0):.1f} |"
            )
    else:
        lines.append("_Not available._")

    lines += [
        f"",
        f"### 2c. Time-of-Day Profile (Entry Hour)",
        f"",
    ]
    if not tod_df.empty:
        # Summarise to hourly (too many 5-min slots for markdown)
        tod_h = tod_df.copy()
        if "slot" in tod_h.columns:
            tod_h["hour"] = tod_h["slot"].str[:2].astype(int, errors="ignore")
            tod_h = tod_h.groupby("hour").agg(
                count=("count","sum"),
                total_pnl=("total_pnl","sum"),
                mean_pnl=("mean_pnl","mean"),
                win_rate=("win_rate","mean"),
            ).reset_index()
        lines.append("| Entry Hour (IST) | Trades | Win Rate | Mean P&L |")
        lines.append("|-----------------|--------|----------|----------|")
        for _, row in tod_h.iterrows():
            lines.append(
                f"| {int(row.get('hour', row.get('slot',0)))}:xx "
                f"| {int(row['count'])} "
                f"| {fmt_pct(row.get('win_rate',0))} "
                f"| ₹{row.get('mean_pnl',0):.1f} |"
            )
    else:
        lines.append("_Not available._")

    lines += [
        f"",
        f"### 2d. Weekday Effects",
        f"",
    ]
    if not wday_df.empty:
        lines.append("| Day | Trades | Win Rate | Mean P&L | Total P&L |")
        lines.append("|-----|--------|----------|----------|-----------|")
        for _, row in wday_df.iterrows():
            lines.append(
                f"| {row.get('day_name','?')} "
                f"| {int(row['count'])} "
                f"| {fmt_pct(row.get('win_rate',0))} "
                f"| ₹{row.get('mean_pnl',0):.1f} "
                f"| ₹{row.get('total_pnl',0):.1f} |"
            )
    else:
        lines.append("_Not available._")

    if not session_df.empty:
        lines += [
            f"",
            f"### 2e. Session Window Profile",
            f"",
            "| Session | Trades | Win Rate | Mean P&L |",
            "|---------|--------|----------|----------|",
        ]
        for _, row in session_df.iterrows():
            lines.append(
                f"| {row['session']} "
                f"| {int(row['count'])} "
                f"| {fmt_pct(row.get('win_rate',0))} "
                f"| ₹{row.get('mean_pnl',0):.1f} |"
            )

    lines += [
        f"",
        f"---",
        f"",
        f"## 3. Regime Targeting Limitation",
        f"",
        f"The runner supports `--days` (lookback from today) but has no `--date-from`/`--date-to` flags.",
        f"Consequently, all 5-minute backtests are anchored to the present (bearish) market state.",
        f"",
        f"A true bullish-regime comparison would require either:",
        f"- Adding `--date-from` / `--date-to` CLI flags to the runner (targeted code change), or",
        f"- Loading pre-downloaded 5-minute CSV files covering a known bullish period (e.g., Jul–Sep 2025).",
        f"",
        f"Neither was done in this phase per the no-code-change constraint.",
        f"",
        f"---",
        f"",
        f"## 4. Phase 6 — Final Judgment",
        f"",
        f"### Q1: Does the strategy improve materially in bullish or neutral regimes?",
        f"",
        f"> **Cannot confirm with current data.** Both tested windows (20d, 60d) fall in `bearish_trending`.",
        f"> Without a bullish historical window, direct regime-separated performance cannot be measured.",
        f"> The regime validation report shows 100% bearish labeling across all 53 symbols.",
        f"",
        f"### Q2: Is the bearish-window failure mostly regime-driven or structurally driven?",
        f"",
    ]

    if verdict == "STRUCTURAL_WEAKNESS":
        lines += [
            f"> **Verdict: STRUCTURAL WEAKNESS.**",
            f"> Win rate of {fmt_pct(win_rate)} and stop-loss exit rate of {stop_loss_pct*100:.1f}% point to",
            f"> a strategy that is not just losing to market direction — it is entering poorly, getting",
            f"> stopped out frequently, and capturing very little of available intraday moves.",
            f"> This pattern is unlikely to reverse simply by waiting for a bullish regime.",
        ]
    elif verdict == "REGIME_DRIVEN":
        lines += [
            f"> **Verdict: PRIMARILY REGIME-DRIVEN.**",
            f"> The stop-loss exit rate ({stop_loss_pct*100:.1f}%) is moderate, and forced session-close exits",
            f"> ({session_pct*100:.1f}%) dominate, suggesting the strategy is not fatally mis-configured —",
            f"> it is simply running into a persistent trend that opposes its long-biased signals.",
            f"> Performance may recover materially in a bullish regime.",
        ]
    else:
        lines += [
            f"> **Verdict: AMBIGUOUS.** Mixed signals — stop-loss rate ({stop_loss_pct*100:.1f}%),",
            f"> session exits ({session_pct*100:.1f}%), win rate ({fmt_pct(win_rate)}).",
            f"> Need a bullish-window test to disambiguate regime vs structural factors.",
        ]

    lines += [
        f"",
        f"### Q3: Is the stop/exit profile unhealthy even in favorable regimes?",
        f"",
    ]
    if stop_loss_dominant:
        lines.append(f"> **Yes.** Stop-loss exits ({stop_loss_pct*100:.1f}%) are the dominant exit type.")
        lines.append(f"> Average holding time of {avg_hold:.1f} min suggests entries are frequently")
        lines.append(f"> placed into mature moves and stopped out on mean reversion.")
    elif session_dominant:
        lines.append(f"> **Moderate concern.** EOD/session forced exits ({session_pct*100:.1f}%) dominate.")
        lines.append(f"> Positions are surviving the session but not reaching profit targets.")
        lines.append(f"> This may indicate target-setting is too ambitious for 5-min intraday moves.")
    else:
        lines.append(f"> **Insufficient data or mixed.** Cannot determine with confidence.")

    lines += [
        f"",
        f"### Q4: Is this strategy worth optimizing next?",
        f"",
    ]
    if verdict == "STRUCTURAL_WEAKNESS":
        lines += [
            f"> **No — not yet.** Optimizing on top of a structurally weak strategy risks overfitting",
            f"> to the current bearish sample. The stop-loss calibration and entry logic should be",
            f"> reviewed first to understand whether the strategy can win at all in any regime.",
        ]
    else:
        lines += [
            f"> **Conditionally yes.** If a bullish-window backtest (via date-range support or CSV)",
            f"> shows materially better results, optimization is warranted.",
            f"> If bullish results also show <30% win rate and high stop-loss rate, review exits first.",
        ]

    lines += [
        f"",
        f"### Q5: Recommended next step",
        f"",
        f"> **{next_step.upper()}**",
        f"",
        f"Specific actions in priority order:",
        f"1. **Enable date-range support** (`--date-from` / `--date-to`) in the runner — targeted, safe, ~50 lines",
        f"2. **Run a bullish-period 5-min backtest** (e.g., Jun–Aug 2025 if Zerodha history allows)",
        f"3. **If bullish results also poor** → exit-logic review: stop distance, profit target, session filter",
        f"4. **If bullish results materially better** → walk-forward regime validation, then parameter optimization",
        f"5. **Monte Carlo / Pine Script** only after walk-forward shows robustness across regimes",
        f"",
        f"---",
        f"",
        f"*Generated by `scripts/analyze_trade_diagnostics.py` — no strategy logic modified.*",
    ]

    md_text = "\n".join(lines)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "summary.md").write_text(md_text, encoding="utf-8")
    print(f"  [OK]   summary.md written")

    summary_dict = {
        "generated": now_str,
        "verdict": verdict,
        "next_step": next_step,
        "windows_tested": ["20d_bearish_baseline", "60d_extended"],
        "trade_count_60d": n_trades,
        "win_rate_60d": round(win_rate, 4) if not np.isnan(win_rate) else None,
        "mean_pnl_per_trade_60d": round(mean_pnl, 2) if not np.isnan(mean_pnl) else None,
        "avg_holding_minutes_60d": round(avg_hold, 1) if not np.isnan(avg_hold) else None,
        "stop_loss_exit_pct": round(stop_loss_pct, 4) if not np.isnan(stop_loss_pct) else None,
        "session_exit_pct": round(session_pct, 4) if not np.isnan(session_pct) else None,
        "sharpe_delta_60d_vs_20d": round(sharpe_delta, 4) if not np.isnan(sharpe_delta) else None,
        "return_delta_60d_vs_20d": round(return_delta, 6) if not np.isnan(return_delta) else None,
        "regime_limitation": "No date-from/date-to support; bullish-window test not possible without code change",
        "structural_weakness_signals": structural_weakness_signals,
        "regime_driven_signals": regime_driven_signals,
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary_dict, indent=2, default=str), encoding="utf-8"
    )
    print(f"  [OK]   summary.json written")
    return summary_dict


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    divider = "-" * 64
    print(f"\n{divider}")
    print("  PHASE 4-6 TRADE DIAGNOSTICS & REGIME COMPARISON")
    print(divider)

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ── Load data ──────────────────────────────────────────────────────────
    print("\n[Loading data]")
    trades      = load_trade_log()
    results_20d = load_results(BASELINE_DIR, "20d")
    results_60d = load_results(EXTENDED_DIR, "60d")

    # ── Enrich trades ──────────────────────────────────────────────────────
    if not trades.empty:
        print("\n[Enriching trades]")
        trades = enrich_trades(trades)

    # ── Analyses ───────────────────────────────────────────────────────────
    print("\n[Running analyses]")
    exit_df    = exit_reason_breakdown(trades)
    tod_df     = time_of_day_profile(trades)
    wday_df    = weekday_profile(trades)
    hold_df    = holding_time_profile(trades)
    sym_df     = per_symbol_metrics(trades)
    session_df = session_profile(trades)
    regime_cmp = regime_comparison(results_20d, results_60d)

    # ── Export CSVs ────────────────────────────────────────────────────────
    print("\n[Exporting CSVs]")

    def save(df: pd.DataFrame, name: str) -> None:
        if df.empty:
            print(f"  [SKIP] {name} — empty")
            return
        p = OUT_DIR / name
        df.to_csv(p, index=False)
        print(f"  [OK]   {name} ({len(df)} rows)")

    if not trades.empty:
        save(trades, "trade_log.csv")
    save(exit_df,    "exit_reason_breakdown.csv")
    save(tod_df,     "time_of_day.csv")
    save(wday_df,    "weekday_effects.csv")
    save(hold_df,    "holding_time.csv")
    save(sym_df,     "per_symbol_metrics.csv")
    save(session_df, "session_profile.csv")
    save(regime_cmp, "regime_comparison.csv")

    # Period comparison table
    if not results_20d.empty and not results_60d.empty:
        period_cmp = pd.concat([results_20d, results_60d], ignore_index=True)
        save(period_cmp, "period_comparison.csv")

    # Copy / create failures.csv
    fail_src = EXTENDED_DIR / "failures.csv"
    if fail_src.exists():
        import shutil
        shutil.copy(fail_src, OUT_DIR / "failures.csv")
        print(f"  [OK]   failures.csv copied")

    # top_ranked already written by runner; copy regime comparison into top-level
    top_src = EXTENDED_DIR / "top_ranked.csv"
    if top_src.exists():
        print(f"  [OK]   top_ranked.csv already present")

    # ── Summary & judgment ─────────────────────────────────────────────────
    print("\n[Writing summary.md and summary.json]")
    summary = write_summary_md(
        OUT_DIR, trades,
        results_20d, results_60d,
        exit_df, tod_df, wday_df, hold_df, sym_df,
        regime_cmp, session_df,
    )

    # ── Manifest ───────────────────────────────────────────────────────────
    manifest = {
        "script"         : "analyze_trade_diagnostics.py",
        "generated"      : datetime.now().isoformat(),
        "baseline_dir"   : str(BASELINE_DIR),
        "extended_dir"   : str(EXTENDED_DIR),
        "output_dir"     : str(OUT_DIR),
        "trade_count"    : len(trades),
        "verdict"        : summary["verdict"],
        "next_step"      : summary["next_step"],
    }
    (OUT_DIR / "run_manifest.json").write_text(
        json.dumps(manifest, indent=2, default=str), encoding="utf-8"
    )
    print("  [OK]   run_manifest.json written")

    print(f"\n{divider}")
    print(f"  VERDICT : {summary['verdict']}")
    print(f"  NEXT    : {summary['next_step']}")
    print(divider)
    print(f"  Output  : {OUT_DIR}")
    print(divider + "\n")


if __name__ == "__main__":
    main()
