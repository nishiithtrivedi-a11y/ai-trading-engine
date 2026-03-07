"""
Monte Carlo RETURN_BOOTSTRAP robustness analysis for RSI(21,30,70) on RELIANCE daily.

Uses RETURN_BOOTSTRAP mode (sampling with replacement), which:
- Answers: what range of OUTCOMES is plausible given sampling uncertainty?
- Shows probability of loss, probability of bad drawdown, equity percentile range.

2000 simulations, seed=42.
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
from src.research.monte_carlo import MonteCarloAnalyzer, SimulationMode
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_FILE  = "data/RELIANCE_1D.csv"
OUTPUT_DIR = "output/rsi_monte_carlo"

RSI_PARAMS = {"rsi_period": 21, "oversold": 30, "overbought": 70}

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
    data_file=DATA_FILE,
)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def main() -> None:
    # 1. Run base backtest to get trade log
    dh = DataHandler.from_csv(DATA_FILE)
    engine = BacktestEngine(BASE_CONFIG, RSIReversionStrategy())
    engine.run(dh)
    results = engine.get_results()

    tl = results["trade_log"]
    base_metrics = results["metrics"]

    num_trades = base_metrics.get("num_trades", len(tl))
    base_return = base_metrics.get("total_return_pct", 0.0)
    base_sharpe = base_metrics.get("sharpe_ratio", 0.0)
    base_dd     = base_metrics.get("max_drawdown_pct", 0.0)
    final_eq    = engine.portfolio.total_value(dh.data["close"].iloc[-1])

    print(f"Base backtest: {num_trades} trades | "
          f"Return={base_return*100:.2f}%  Sharpe={base_sharpe:.4f}  MaxDD={base_dd*100:.2f}%")
    print(f"Final equity:  ${final_eq:,.2f}")

    if tl.empty or num_trades < 2:
        print("Not enough trades for Monte Carlo analysis (need >= 2).")
        return

    # 2. Prepare trade records for MonteCarloAnalyzer
    trade_records = tl.to_dict("records")

    # 3. Run Monte Carlo
    print(f"\nRunning 2000 RETURN_BOOTSTRAP simulations...")
    analyzer = MonteCarloAnalyzer(
        trades=trade_records,
        initial_capital=100_000,
        num_simulations=2000,
        seed=42,
        output_dir=OUTPUT_DIR,
    )
    mc_result = analyzer.run(SimulationMode.RETURN_BOOTSTRAP)

    # 4. Extract results
    runs_df = mc_result.to_dataframe()
    final_equities = runs_df["final_equity"].values
    max_drawdowns  = runs_df["max_drawdown_pct"].values
    summary        = mc_result.summary
    pctiles        = mc_result.percentiles

    eq_pctiles = pctiles.get("final_equity", {})
    dd_pctiles = pctiles.get("max_drawdown_pct", {})

    prob_loss = summary.get("probability_of_profit")
    # probability_of_profit is P(profit), we want P(loss)
    prob_of_loss = 1.0 - prob_loss if prob_loss is not None else float("nan")

    # Probability of drawdown worse than 15%
    prob_dd_15 = float((max_drawdowns > 0.15).sum()) / len(max_drawdowns)

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    SEP = "=" * 70

    print()
    print(SEP)
    print("  RSI(21,30,70) on RELIANCE 1D -- MONTE CARLO RETURN_BOOTSTRAP")
    print("  2000 simulations | seed=42 | sampling with replacement")
    print(SEP)

    print()
    print("--- BASE STRATEGY RESULT ---")
    print(f"  Trades:         {num_trades}")
    print(f"  Total return:   {base_return*100:.2f}%")
    print(f"  Sharpe ratio:   {base_sharpe:.4f}")
    print(f"  Max drawdown:   {base_dd*100:.2f}%")
    print(f"  Final equity:   ${final_eq:,.2f}")

    def _eq(key: str) -> float:
        v = eq_pctiles.get(key, float("nan"))
        return float(v) if v is not None else float("nan")

    def _ret(eq_val: float) -> str:
        if eq_val != eq_val:
            return "N/A"
        return f"{(eq_val/100_000-1)*100:+.2f}%"

    print()
    print("--- MONTE CARLO EQUITY OUTCOMES ---")
    print(f"  p5  (worst 5%):   ${_eq('p5'):>10,.2f}     ({_ret(_eq('p5'))})")
    print(f"  p10             : ${_eq('p10'):>10,.2f}     ({_ret(_eq('p10'))})")
    print(f"  p25             : ${_eq('p25'):>10,.2f}     ({_ret(_eq('p25'))})")
    print(f"  p50 (median)    : ${_eq('p50'):>10,.2f}     ({_ret(_eq('p50'))})")
    print(f"  p75             : ${_eq('p75'):>10,.2f}     ({_ret(_eq('p75'))})")
    print(f"  p90             : ${_eq('p90'):>10,.2f}     ({_ret(_eq('p90'))})")
    print(f"  p95 (best 5%):    ${_eq('p95'):>10,.2f}     ({_ret(_eq('p95'))})")

    def _dd(key: str) -> float:
        v = dd_pctiles.get(key, float("nan"))
        return float(v) if v is not None else float("nan")

    print()
    print("--- RISK METRICS ---")
    print(f"  Probability of loss:              {prob_of_loss*100:.1f}%")
    print(f"  Probability of profit:            {(1-prob_of_loss)*100:.1f}%")
    print(f"  Probability of DD > 15%:          {prob_dd_15*100:.1f}%")
    print(f"  Median max drawdown (p50):        {_dd('p50')*100:.2f}%")
    print(f"  Worst-case max DD (p95):          {_dd('p95')*100:.2f}%")

    print()
    print("--- INTERPRETATION ---")
    if prob_of_loss < 0.25 and eq_pctiles.get(50, 0) > 100_000:
        print("  ROBUST: > 75% of paths are profitable. Median outcome is positive.")
        print("  The edge is unlikely to be pure luck at this sample size.")
    elif prob_of_loss < 0.5:
        print("  MODERATE: Most paths are profitable but uncertainty is meaningful.")
        print("  With only", num_trades, "trades, the sample is small; edge may not persist.")
    else:
        print("  FRAGILE: Over 50% of bootstrapped paths lose money.")
        print("  The observed profit is likely noise given the tiny trade sample.")

    print()
    note = (
        "  NOTE on RETURN_BOOTSTRAP vs TRADE_RESHUFFLE:\n"
        "  - TRADE_RESHUFFLE (previous run): same total PnL every path, shows PATH risk\n"
        "  - RETURN_BOOTSTRAP (this run): samples with replacement, shows OUTCOME uncertainty\n"
        "  - With only " + str(num_trades) + " trades, bootstrap uncertainty is high by design."
    )
    print(note)
    print()
    print(f"  Results exported to: {OUTPUT_DIR}/")
    print(SEP)


if __name__ == "__main__":
    main()
