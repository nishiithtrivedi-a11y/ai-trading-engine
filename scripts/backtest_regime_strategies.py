#!/usr/bin/env python3
"""
Multi-symbol backtest validation for Bullish and Bearish Intraday Regime Strategies.

Runs both strategies across all available 5-minute data files (NIFTY 50 subset),
collects metrics, detects regime context, and prints a structured comparison report.

Usage:
    python scripts/backtest_regime_strategies.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import json
import pandas as pd

from src.core.backtest_engine import BacktestEngine
from src.core.data_handler import DataHandler
from src.strategies.registry import create_strategy
from src.utils.config import BacktestConfig, RiskConfig, PositionSizingMethod


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DATA_DIR = ROOT / "data"

# Symbol -> file mapping: prefer 2024 extended data, fallback to shorter files
SYMBOL_FILES: dict[str, list[str]] = {
    "RELIANCE": ["RELIANCE_5M_2024.csv", "RELIANCE_5M.csv"],
    "HDFCBANK": ["HDFCBANK_5M_2024.csv", "HDFCBANK_5M.csv"],
    "INFY":     ["INFY_5M_2024.csv", "INFY_5M.csv"],
    "ICICIBANK": ["ICICIBANK_5M_2024.csv", "ICICIBANK_5M.csv"],
    "TCS":      ["TCS_5M.csv"],
    "LT":       ["LT_5M_2024.csv"],
}

# Also test on 15m and 1h where available
MULTI_TF_FILES: dict[str, dict[str, str]] = {
    "RELIANCE": {"15m": "RELIANCE_15M.csv", "1h": "RELIANCE_1H.csv"},
    "HDFCBANK": {"15m": "HDFCBANK_15M.csv", "1h": "HDFCBANK_1H.csv"},
    "INFY":     {"15m": "INFY_15M.csv", "1h": "INFY_1H.csv"},
    "TCS":      {"15m": "TCS_15M.csv", "1h": "TCS_1H.csv"},
}

STRATEGIES = ["bullish_intraday_regime", "bearish_intraday_regime"]


def make_config(strategy_name: str, output_suffix: str, data_file: str = "data/sample_data.csv") -> BacktestConfig:
    """Create intraday backtest config appropriate for the strategy."""
    return BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0005,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.30,
        intraday=True,
        force_square_off_at_close=True,
        allow_entries_only_during_market_hours=True,
        market_timezone="Asia/Kolkata",
        risk=RiskConfig(
            stop_loss_pct=0.015,
            trailing_stop_pct=0.01,
        ),
        output_dir=f"output/regime_strategies/{output_suffix}",
        data_file=data_file,
    )


def resolve_file(symbol: str) -> Path | None:
    """Pick the best available data file for a symbol."""
    candidates = SYMBOL_FILES.get(symbol, [])
    for fname in candidates:
        p = DATA_DIR / fname
        if p.exists():
            return p
    return None


def run_single_backtest(
    strategy_name: str, symbol: str, data_path: Path, timeframe: str = "5m",
) -> dict | None:
    """Run a single backtest and return metrics dict, or None on failure."""
    try:
        dh = DataHandler.from_csv(str(data_path))
        strategy = create_strategy(strategy_name)
        suffix = f"{strategy_name}/{symbol}_{timeframe}"
        config = make_config(strategy_name, suffix, data_file=str(data_path))

        engine = BacktestEngine(config, strategy)
        metrics = engine.run(dh)

        results = engine.get_results()
        m = results.get("metrics", {})
        m["symbol"] = symbol
        m["timeframe"] = timeframe
        m["strategy"] = strategy_name
        m["num_trade_log"] = len(results.get("trade_log", []))
        return m
    except Exception as e:
        print(f"  [ERROR] {strategy_name} / {symbol} / {timeframe}: {e}")
        return None


def run_all_backtests() -> list[dict]:
    """Run all symbol x strategy x timeframe combinations."""
    all_results = []

    # Primary 5m runs
    print("=" * 70)
    print("REGIME STRATEGY BACKTEST SUITE — 5-minute data")
    print("=" * 70)

    for symbol, _ in SYMBOL_FILES.items():
        data_path = resolve_file(symbol)
        if data_path is None:
            print(f"  [SKIP] {symbol}: no data file found")
            continue

        for strat in STRATEGIES:
            print(f"  Running {strat} on {symbol} (5m) ...")
            m = run_single_backtest(strat, symbol, data_path, "5m")
            if m:
                all_results.append(m)

    # Multi-timeframe runs
    print()
    print("=" * 70)
    print("MULTI-TIMEFRAME RUNS")
    print("=" * 70)

    for symbol, tf_map in MULTI_TF_FILES.items():
        for tf_label, fname in tf_map.items():
            fpath = DATA_DIR / fname
            if not fpath.exists():
                continue
            for strat in STRATEGIES:
                print(f"  Running {strat} on {symbol} ({tf_label}) ...")
                m = run_single_backtest(strat, symbol, fpath, tf_label)
                if m:
                    all_results.append(m)

    return all_results


def print_report(results: list[dict]) -> None:
    """Print structured comparison report."""
    if not results:
        print("\nNo results to report.")
        return

    df = pd.DataFrame(results)

    print()
    print("=" * 70)
    print("BACKTEST RESULTS SUMMARY")
    print("=" * 70)

    for strat in STRATEGIES:
        subset = df[df["strategy"] == strat]
        if subset.empty:
            continue

        tag = "BULLISH" if "bullish" in strat else "BEARISH"
        print(f"\n{'-' * 70}")
        print(f"  {tag} INTRADAY REGIME STRATEGY")
        print(f"{'-' * 70}")

        for _, row in subset.iterrows():
            sym = row.get("symbol", "?")
            tf = row.get("timeframe", "?")
            trades = int(row.get("num_trades", 0))
            win_rate = row.get("win_rate", 0)
            pf = row.get("profit_factor", 0)
            ret = row.get("total_return_pct", 0)
            dd = row.get("max_drawdown_pct", 0)
            sharpe = row.get("sharpe_ratio", 0)

            print(
                f"  {sym:>10} ({tf:>3}) | "
                f"Trades: {trades:>4} | "
                f"WR: {win_rate:>6.1%} | "
                f"PF: {pf:>6.2f} | "
                f"Ret: {ret:>8.2%} | "
                f"DD: {dd:>8.2%} | "
                f"Sharpe: {sharpe:>7.3f}"
            )

        # Aggregate
        if len(subset) > 1:
            print(f"  {'-' * 66}")
            avg_wr = subset["win_rate"].mean() if "win_rate" in subset else 0
            avg_pf = subset["profit_factor"].mean() if "profit_factor" in subset else 0
            avg_ret = subset["total_return_pct"].mean() if "total_return_pct" in subset else 0
            avg_dd = subset["max_drawdown_pct"].mean() if "max_drawdown_pct" in subset else 0
            avg_sharpe = subset["sharpe_ratio"].mean() if "sharpe_ratio" in subset else 0
            total_trades = int(subset["num_trades"].sum()) if "num_trades" in subset else 0
            print(
                f"  {'AVERAGE':>10}       | "
                f"Trades: {total_trades:>4} | "
                f"WR: {avg_wr:>6.1%} | "
                f"PF: {avg_pf:>6.2f} | "
                f"Ret: {avg_ret:>8.2%} | "
                f"DD: {avg_dd:>8.2%} | "
                f"Sharpe: {avg_sharpe:>7.3f}"
            )

    # Bullish vs Bearish comparison
    print(f"\n{'=' * 70}")
    print("BULLISH vs BEARISH COMPARISON (5m only)")
    print(f"{'=' * 70}")

    fivemin = df[df["timeframe"] == "5m"]
    for strat in STRATEGIES:
        s = fivemin[fivemin["strategy"] == strat]
        tag = "BULL" if "bullish" in strat else "BEAR"
        if s.empty:
            print(f"  {tag}: no 5m results")
            continue
        print(
            f"  {tag}: "
            f"Symbols={len(s)} | "
            f"Avg WR={s['win_rate'].mean():.1%} | "
            f"Avg PF={s['profit_factor'].mean():.2f} | "
            f"Avg Ret={s['total_return_pct'].mean():.2%} | "
            f"Avg DD={s['max_drawdown_pct'].mean():.2%} | "
            f"Avg Sharpe={s['sharpe_ratio'].mean():.3f}"
        )

    # Multi-timeframe comparison
    print(f"\n{'=' * 70}")
    print("MULTI-TIMEFRAME COMPARISON")
    print(f"{'=' * 70}")

    for tf in ["5m", "15m", "1h"]:
        tf_data = df[df["timeframe"] == tf]
        if tf_data.empty:
            continue
        print(
            f"  {tf:>3}: "
            f"Runs={len(tf_data)} | "
            f"Avg WR={tf_data['win_rate'].mean():.1%} | "
            f"Avg PF={tf_data['profit_factor'].mean():.2f} | "
            f"Avg Ret={tf_data['total_return_pct'].mean():.2%} | "
            f"Avg DD={tf_data['max_drawdown_pct'].mean():.2%}"
        )


def main() -> None:
    results = run_all_backtests()
    print_report(results)

    # Save raw results
    output_path = ROOT / "output" / "regime_strategies" / "backtest_results.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        # Convert non-serializable types
        clean = []
        for r in results:
            row = {}
            for k, v in r.items():
                if isinstance(v, (int, float, str, bool, type(None))):
                    row[k] = v
                else:
                    row[k] = str(v)
            clean.append(row)
        json.dump(clean, f, indent=2, default=str)
    print(f"\nRaw results saved to: {output_path}")


if __name__ == "__main__":
    main()
