#!/usr/bin/env python3
"""
DRAS v3.2 Research-Validation Script
======================================
Runs the standalone backtest_dras() function across multiple symbols and
parameter variants. Produces output artifacts in:
  output/dras_multi_symbol_bullish_validation/

Safety: Research / observation only. No real orders ever placed.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import pandas as pd

from src.strategies.intraday.dynamic_regime_adaptive_system_strategy import (
    DRASConfig,
    backtest_dras,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_DIR = ROOT / "output" / "dras_multi_symbol_bullish_validation"
DATA_DIR = ROOT / "data"

SYMBOLS = ["RELIANCE", "ICICIBANK", "HDFCBANK", "INFY", "TCS"]

SENSITIVITY_VARIANTS = [
    {
        "label": "default",
        "params": {},
    },
    {
        "label": "relaxed_wick_vol",
        "params": {"wick_percent": 0.3, "vol_mult": 1.0},
    },
    {
        "label": "relaxed_adx",
        "params": {"adx_threshold": 15},
    },
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

def load_csv(symbol: str) -> pd.DataFrame | None:
    """Load 5-minute OHLCV CSV for a symbol. Returns None on failure."""
    candidates = [
        DATA_DIR / f"{symbol}_5M.csv",
        DATA_DIR / f"{symbol}_KITE_5M.csv",
    ]
    for path in candidates:
        if path.exists():
            df = pd.read_csv(path)
            print(f"  [OK] Loaded {path.name}: {len(df)} rows")
            return df
    print(f"  [MISS] No 5M CSV found for {symbol}")
    return None


# ---------------------------------------------------------------------------
# Run single backtest
# ---------------------------------------------------------------------------

def run_one(symbol: str, df: pd.DataFrame, cfg_params: dict, label: str) -> dict:
    """Run backtest_dras and return a flat result dict."""
    cfg = DRASConfig(**cfg_params)
    try:
        _, trades_df, summary = backtest_dras(df, cfg)
        return {
            "symbol": symbol,
            "variant": label,
            "total_trades": summary["total_trades"],
            "wins": summary["wins"],
            "losses": summary["losses"],
            "win_rate_pct": summary["win_rate_pct"],
            "profit_factor": summary["profit_factor"],
            "net_profit": summary["net_profit"],
            "net_profit_pct": summary["net_profit_pct"],
            "max_drawdown_pct": summary["max_drawdown_pct"],
            "expectancy": summary["expectancy"],
            "initial_capital": summary["initial_capital"],
            "final_equity": summary["final_equity"],
            "error": None,
        }
    except Exception as exc:
        print(f"  [ERROR] {symbol} / {label}: {exc}")
        return {
            "symbol": symbol,
            "variant": label,
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "net_profit": 0.0,
            "net_profit_pct": 0.0,
            "max_drawdown_pct": 0.0,
            "expectancy": 0.0,
            "initial_capital": 100_000.0,
            "final_equity": 100_000.0,
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"\n{'='*60}")
    print("  DRAS v3.2 Research-Validation Run")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}\n")

    # Load data
    print("--- Loading Data ---")
    data_map: dict[str, pd.DataFrame] = {}
    for sym in SYMBOLS:
        df = load_csv(sym)
        if df is not None:
            data_map[sym] = df
    print()

    if not data_map:
        print("[FATAL] No data loaded. Exiting.")
        sys.exit(1)

    # Phase 3: Default runs on all symbols
    print("--- Phase 3: Default Parameter Validation (all symbols) ---")
    default_results: list[dict] = []
    for sym in SYMBOLS:
        if sym not in data_map:
            continue
        print(f"  Running default DRAS on {sym}...")
        result = run_one(sym, data_map[sym], {}, "default")
        default_results.append(result)
        print(
            f"    trades={result['total_trades']}  "
            f"win_rate={result['win_rate_pct']:.1f}%  "
            f"PF={result['profit_factor']:.3f}  "
            f"net_pnl={result['net_profit']:.0f}  "
            f"maxDD={result['max_drawdown_pct']:.2f}%"
        )
    print()

    # Phase 4: Sensitivity on RELIANCE only
    print("--- Phase 4: Sensitivity Check (RELIANCE only) ---")
    sensitivity_results: list[dict] = []
    rel_df = data_map.get("RELIANCE")
    if rel_df is not None:
        for variant in SENSITIVITY_VARIANTS:
            label = variant["label"]
            params = variant["params"]
            print(f"  Running variant '{label}' on RELIANCE...")
            result = run_one("RELIANCE", rel_df, params, label)
            sensitivity_results.append(result)
            print(
                f"    trades={result['total_trades']}  "
                f"win_rate={result['win_rate_pct']:.1f}%  "
                f"PF={result['profit_factor']:.3f}  "
                f"net_pnl={result['net_profit']:.0f}  "
                f"maxDD={result['max_drawdown_pct']:.2f}%"
            )
    print()

    # Combine all_results (default across all symbols + sensitivity)
    all_results = default_results + [r for r in sensitivity_results if r["variant"] != "default"]

    # ---------------------------------------------------------------------------
    # Save artifacts
    # ---------------------------------------------------------------------------
    print("--- Saving Output Artifacts ---")

    # all_results.csv
    all_df = pd.DataFrame(all_results)
    all_df.to_csv(OUTPUT_DIR / "all_results.csv", index=False)
    print(f"  [OK] all_results.csv ({len(all_df)} rows)")

    # per_symbol_metrics.csv — aggregate default runs per symbol
    default_df = pd.DataFrame(default_results)
    if not default_df.empty:
        default_df.to_csv(OUTPUT_DIR / "per_symbol_metrics.csv", index=False)
        print(f"  [OK] per_symbol_metrics.csv ({len(default_df)} rows)")

    # sensitivity_summary.csv
    sens_df = pd.DataFrame(sensitivity_results)
    if not sens_df.empty:
        sens_df.to_csv(OUTPUT_DIR / "sensitivity_summary.csv", index=False)
        print(f"  [OK] sensitivity_summary.csv ({len(sens_df)} rows)")

    # summary.json
    total_default_trades = sum(r["total_trades"] for r in default_results)
    symbols_with_trades = [r["symbol"] for r in default_results if r["total_trades"] > 0]

    summary_json = {
        "run_date": datetime.now().isoformat(),
        "strategy": "DRAS v3.2",
        "data_period": "2025-12-10 to 2026-03-13 (~60 trading days)",
        "timeframe": "5minute",
        "initial_capital": 100_000,
        "symbols_tested": list(data_map.keys()),
        "total_default_trades_all_symbols": total_default_trades,
        "symbols_with_at_least_1_trade": symbols_with_trades,
        "default_results": default_results,
        "sensitivity_results": sensitivity_results,
    }
    with open(OUTPUT_DIR / "summary.json", "w") as f:
        json.dump(summary_json, f, indent=2, default=str)
    print("  [OK] summary.json")

    # run_manifest.json
    manifest = {
        "script": "scripts/run_dras_validation.py",
        "run_date": datetime.now().isoformat(),
        "git_branch": "claude/dras-python-port-reliance-validation",
        "symbols": SYMBOLS,
        "variants": [v["label"] for v in SENSITIVITY_VARIANTS],
        "output_dir": str(OUTPUT_DIR),
        "files_written": [
            "all_results.csv",
            "per_symbol_metrics.csv",
            "sensitivity_summary.csv",
            "summary.json",
            "summary.md",
            "run_manifest.json",
        ],
    }
    with open(OUTPUT_DIR / "run_manifest.json", "w") as f:
        json.dump(manifest, f, indent=2)
    print("  [OK] run_manifest.json")

    # summary.md
    _write_summary_md(default_results, sensitivity_results, summary_json)
    print("  [OK] summary.md")
    print()

    # ---------------------------------------------------------------------------
    # Phase 6: Final Judgment
    # ---------------------------------------------------------------------------
    print("--- Phase 6: Final Judgment ---")
    _print_judgment(default_results, sensitivity_results)

    print(f"\nAll outputs written to: {OUTPUT_DIR}\n")


def _write_summary_md(
    default_results: list[dict],
    sensitivity_results: list[dict],
    meta: dict,
) -> None:
    lines: list[str] = [
        "# DRAS v3.2 Research Validation — Summary Report",
        "",
        f"**Run date:** {meta['run_date'][:19]}",
        f"**Data period:** {meta['data_period']}",
        f"**Timeframe:** {meta['timeframe']}",
        f"**Initial capital:** Rs. {meta['initial_capital']:,}",
        "",
        "---",
        "",
        "## Phase 3 — Default Parameter Results (All Symbols)",
        "",
        "| Symbol | Trades | Win% | PF | Net P&L (Rs) | Net P&L% | Max DD% | Expectancy |",
        "|--------|--------|------|----|-------------|----------|---------|------------|",
    ]
    for r in default_results:
        lines.append(
            f"| {r['symbol']} "
            f"| {r['total_trades']} "
            f"| {r['win_rate_pct']:.1f}% "
            f"| {r['profit_factor']:.3f} "
            f"| {r['net_profit']:,.0f} "
            f"| {r['net_profit_pct']:.2f}% "
            f"| {r['max_drawdown_pct']:.2f}% "
            f"| {r['expectancy']:.2f} |"
        )

    total_trades = sum(r["total_trades"] for r in default_results)
    lines += [
        "",
        f"**Total trades across all symbols:** {total_trades}",
        "",
        "---",
        "",
        "## Phase 4 — Sensitivity Check (RELIANCE Only)",
        "",
        "| Variant | Trades | Win% | PF | Net P&L (Rs) | Max DD% |",
        "|---------|--------|------|----|-------------|---------|",
    ]
    for r in sensitivity_results:
        lines.append(
            f"| {r['variant']} "
            f"| {r['total_trades']} "
            f"| {r['win_rate_pct']:.1f}% "
            f"| {r['profit_factor']:.3f} "
            f"| {r['net_profit']:,.0f} "
            f"| {r['max_drawdown_pct']:.2f}% |"
        )

    lines += [
        "",
        "---",
        "",
        "## Phase 6 — Judgment",
        "",
    ]

    total = sum(r["total_trades"] for r in default_results)
    syms_with_trades = [r["symbol"] for r in default_results if r["total_trades"] > 0]
    syms_no_trades = [r["symbol"] for r in default_results if r["total_trades"] == 0]

    lines += [
        f"- **Total default trades (5 symbols, ~60 trading days):** {total}",
        f"- **Symbols with at least 1 trade:** {syms_with_trades or 'none'}",
        f"- **Symbols with zero trades:** {syms_no_trades}",
        "",
    ]

    sens_default = next((r for r in sensitivity_results if r["variant"] == "default"), None)
    sens_wick = next((r for r in sensitivity_results if r["variant"] == "relaxed_wick_vol"), None)
    sens_adx = next((r for r in sensitivity_results if r["variant"] == "relaxed_adx"), None)

    if sens_default and sens_wick:
        delta = (sens_wick["total_trades"] or 0) - (sens_default["total_trades"] or 0)
        lines.append(
            f"- **Relaxed wick/vol vs default on RELIANCE:** "
            f"{sens_wick['total_trades']} vs {sens_default['total_trades']} trades "
            f"(delta +{delta})"
        )
    if sens_default and sens_adx:
        delta = (sens_adx["total_trades"] or 0) - (sens_default["total_trades"] or 0)
        lines.append(
            f"- **Relaxed ADX (15) vs default on RELIANCE:** "
            f"{sens_adx['total_trades']} vs {sens_default['total_trades']} trades "
            f"(delta +{delta})"
        )

    # Verdicts
    if total == 0:
        verdict = "WEAK — Zero trades in 60 trading days. Default parameters are too restrictive for available data."
        next_step = (
            "Register DRAS in the strategy registry with relaxed defaults "
            "(wick_percent=0.3, vol_mult=1.0, adx_threshold=15) and retest "
            "on a longer dataset (300+ trading days) before further investment."
        )
    elif total < 10:
        verdict = "BORDERLINE — Very few trades. Default parameters are highly restrictive."
        next_step = (
            "Test with relaxed parameters on a longer dataset. "
            "Consider whether the data range contains enough trending regimes."
        )
    elif total >= 20:
        # Evaluate quality
        pf_vals = [r["profit_factor"] for r in default_results if r["total_trades"] > 0]
        avg_pf = sum(pf_vals) / len(pf_vals) if pf_vals else 0
        if avg_pf >= 1.3:
            verdict = "PROMISING — Sufficient trades and positive edge detected."
            next_step = "Register DRAS in strategy registry. Run full NIFTY-50 research sweep."
        else:
            verdict = "BORDERLINE — Sufficient trades but weak edge (avg PF < 1.3)."
            next_step = "Investigate exit logic. Consider ATR-multiplier tuning."
    else:
        verdict = "BORDERLINE — Some trades but below 20-trade threshold for statistical confidence."
        next_step = "Extend data history to 300+ trading days and rerun validation."

    lines += [
        "",
        f"**Verdict:** {verdict}",
        "",
        f"**Recommended next step:** {next_step}",
        "",
        "---",
        "_Report auto-generated by scripts/run_dras_validation.py_",
    ]

    with open(OUTPUT_DIR / "summary.md", "w") as f:
        f.write("\n".join(lines))


def _print_judgment(default_results: list[dict], sensitivity_results: list[dict]) -> None:
    total = sum(r["total_trades"] for r in default_results)
    syms_with_trades = [r["symbol"] for r in default_results if r["total_trades"] > 0]

    print(f"  Q1. Enough trades (target 20+)?  Total = {total}  -> {'YES' if total >= 20 else 'NO'}")

    pf_vals = [r["profit_factor"] for r in default_results if r["total_trades"] > 0 and r["profit_factor"] > 0]
    avg_pf = sum(pf_vals) / len(pf_vals) if pf_vals else 0
    print(f"  Q2. Promising edge? Avg PF = {avg_pf:.3f}  -> {'YES (PF>=1.2)' if avg_pf >= 1.2 else 'WEAK'}")

    sens_default = next((r for r in sensitivity_results if r["variant"] == "default"), None)
    sens_wick = next((r for r in sensitivity_results if r["variant"] == "relaxed_wick_vol"), None)
    if sens_default and sens_wick:
        restrictive = (sens_wick["total_trades"] or 0) > (sens_default["total_trades"] or 0) * 1.5
        print(f"  Q3. Defaults too restrictive? Relaxed-wick trades={sens_wick['total_trades']} vs default={sens_default['total_trades']}  -> {'YES' if restrictive else 'MARGINAL'}")
    else:
        print("  Q3. Defaults too restrictive? -> N/A (no sensitivity data)")

    broad = len(syms_with_trades)
    print(f"  Q4. Broad across symbols? {broad}/{len(default_results)} symbols have trades  -> {'BROAD' if broad >= 3 else 'CONCENTRATED'}")

    # Overall
    if total == 0:
        print("  Q5. DRAS overall: WEAK — zero trades on available data")
        print("  Q6. Next step: Relax wick_percent/vol_mult/adx_threshold; acquire longer intraday history")
    elif total < 10:
        print("  Q5. DRAS overall: BORDERLINE — very few trades")
        print("  Q6. Next step: Relax parameters; acquire longer intraday history (300+ days)")
    elif avg_pf >= 1.2:
        print("  Q5. DRAS overall: PROMISING")
        print("  Q6. Next step: Register DRAS in registry; run full NIFTY-50 sweep")
    else:
        print("  Q5. DRAS overall: BORDERLINE")
        print("  Q6. Next step: Longer data window + investigate entry/exit quality")


if __name__ == "__main__":
    main()
