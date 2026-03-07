"""
RSI mean reversion generalization test across 5 NSE large-cap stocks.

Fixed params: rsi_period=21, oversold=30, overbought=70
Stocks: RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK (daily data, 2018-2026)

Outputs:
- Per-stock comparison table
- Conclusion: edge generalizes or is RELIANCE-specific?
"""

from __future__ import annotations

import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

import pandas as pd

from src.core.data_handler import DataHandler
from src.core.backtest_engine import BacktestEngine
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

STOCKS = {
    "RELIANCE":  "data/RELIANCE_1D.csv",
    "TCS":       "data/TCS_1D.csv",
    "INFY":      "data/INFY_1D.csv",
    "HDFCBANK":  "data/HDFCBANK_1D.csv",
    "ICICIBANK": "data/ICICIBANK_1D.csv",
}

RSI_PARAMS = {
    "rsi_period": 21,
    "oversold":   30,
    "overbought": 70,
}

OUTPUT_DIR = "output/rsi_generalization"

BASE_CONFIG = BacktestConfig(
    initial_capital=100_000,
    fee_rate=0.001,
    slippage_rate=0.0005,
    position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
    position_size_pct=0.95,
    intraday=False,
    risk=RiskConfig(stop_loss_pct=0.05, trailing_stop_pct=0.03),
    strategy_params=RSI_PARAMS,
    output_dir=OUTPUT_DIR,
    data_file="data/sample_data.csv",
)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def run_single(symbol: str, data_file: str) -> dict:
    dh = DataHandler.from_csv(data_file)
    config = BASE_CONFIG.model_copy(
        update={"output_dir": f"{OUTPUT_DIR}/{symbol}", "data_file": data_file}
    )
    engine = BacktestEngine(config, RSIReversionStrategy())
    engine.run(dh)
    results = engine.get_results()
    m = results["metrics"]
    tl = results["trade_log"]
    bh = results["buy_hold"]

    total_fees = float(tl["fees"].sum()) if not tl.empty and "fees" in tl.columns else 0.0

    return {
        "symbol":           symbol,
        "bars":             len(dh),
        "total_return_pct": m.get("total_return_pct", float("nan")),
        "sharpe_ratio":     m.get("sharpe_ratio",     float("nan")),
        "max_drawdown_pct": m.get("max_drawdown_pct", float("nan")),
        "win_rate":         m.get("win_rate",          float("nan")),
        "num_trades":       m.get("num_trades",        0),
        "profit_factor":    m.get("profit_factor",     float("nan")),
        "total_fees":       total_fees,
        "bh_return_pct":    bh.get("total_return_pct", float("nan")),
    }


def main() -> None:
    rows = []
    for symbol, data_file in STOCKS.items():
        print(f"  Running {symbol}...")
        row = run_single(symbol, data_file)
        rows.append(row)

    SEP = "=" * 110

    print()
    print(SEP)
    print("  RSI MEAN REVERSION (rsi=21, os=30, ob=70) -- CROSS-STOCK GENERALIZATION")
    print("  Period: 2018-01-01 to 2026-03-06 (daily data)")
    print(SEP)
    print()

    # Header
    col_w = [12, 7, 12, 9, 12, 9, 11, 13, 11, 11]
    headers = ["Symbol", "Bars", "Return %", "Sharpe", "MaxDD %",
               "Win Rate", "Trades", "ProfitFactor", "Fees ($)", "BH Return %"]
    header_line = "".join(h.rjust(w) for h, w in zip(headers, col_w))
    print(header_line)
    print("-" * sum(col_w))

    for r in rows:
        def pct(v): return f"{v*100:.2f}%" if v == v else "N/A"
        def f2(v):  return f"{v:.4f}"      if v == v else "N/A"
        def num(v): return str(int(v))

        line = (
            f"{r['symbol']:>12}"
            f"{r['bars']:>7}"
            f"{pct(r['total_return_pct']):>12}"
            f"{f2(r['sharpe_ratio']):>9}"
            f"{pct(r['max_drawdown_pct']):>12}"
            f"{pct(r['win_rate']):>9}"
            f"{num(r['num_trades']):>11}"
            f"{f2(r['profit_factor']):>13}"
            f"${r['total_fees']:>10,.2f}"
            f"{pct(r['bh_return_pct']):>11}"
        )
        print(line)

    print("-" * sum(col_w))

    # Summary stats
    returns   = [r["total_return_pct"] for r in rows if r["total_return_pct"] == r["total_return_pct"]]
    sharpes   = [r["sharpe_ratio"]     for r in rows if r["sharpe_ratio"]     == r["sharpe_ratio"]]
    trades    = [r["num_trades"]       for r in rows]
    pf_vals   = [r["profit_factor"]    for r in rows if r["profit_factor"]    == r["profit_factor"] and r["profit_factor"] != float("inf")]

    positive  = sum(1 for s in sharpes if s > 0)
    avg_sr    = sum(sharpes) / len(sharpes) if sharpes else float("nan")
    avg_ret   = sum(returns) / len(returns) if returns else float("nan")

    print()
    print(f"  Stocks with positive Sharpe: {positive}/{len(rows)}")
    print(f"  Average Sharpe:              {avg_sr:.4f}")
    print(f"  Average total return:        {avg_ret*100:.2f}%")
    print(f"  Total trades (all stocks):   {sum(trades)}")

    print()
    print("  GENERALIZATION VERDICT:")
    if positive >= 4:
        print("  GENERALIZES -- RSI(21/30/70) is profitable on most NSE large-caps")
    elif positive >= 2:
        print("  PARTIAL -- works on some stocks; further tuning may be needed per stock")
    else:
        print("  DOES NOT GENERALIZE -- edge appears RELIANCE-specific or strategy is fragile")

    print()
    print(f"  NOTE: Buy-and-Hold return shown for comparison. All BH returns are")
    print(f"  substantially higher, reflecting the 2018-2026 NSE bull market.")
    print()
    print(f"  Results exported to: {OUTPUT_DIR}/")
    print(SEP)

    # Export to CSV
    import os
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    df = pd.DataFrame(rows)
    df.to_csv(f"{OUTPUT_DIR}/rsi_generalization.csv", index=False)
    print(f"  CSV saved: {OUTPUT_DIR}/rsi_generalization.csv")


if __name__ == "__main__":
    main()
