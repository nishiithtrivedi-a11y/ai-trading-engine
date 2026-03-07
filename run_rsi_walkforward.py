"""
Walk-forward validation for RSI mean reversion on RELIANCE daily data.

Train: 500 bars | Test: 100 bars | Step: 100 bars
Optimize on: sharpe_ratio
Parameter grid:
  rsi_period  = [14, 21, 28]
  oversold    = [25, 30, 35]
  overbought  = [65, 70, 75]
"""

from __future__ import annotations

import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

import pandas as pd

from src.core.data_handler import DataHandler
from src.research.walk_forward import WalkForwardTester
from src.strategies.rsi_reversion import RSIReversionStrategy
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

DATA_FILE = "data/RELIANCE_1D.csv"
OUTPUT_DIR = "output/rsi_walkforward"

PARAM_GRID = {
    "rsi_period": [14, 21, 28],
    "oversold":   [25, 30, 35],
    "overbought": [65, 70, 75],
}

BASE_CONFIG = BacktestConfig(
    initial_capital=100_000,
    fee_rate=0.001,
    slippage_rate=0.0005,
    position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
    position_size_pct=0.95,
    intraday=False,
    risk=RiskConfig(stop_loss_pct=0.05, trailing_stop_pct=0.03),
    strategy_params={},
    output_dir=OUTPUT_DIR,
    data_file=DATA_FILE,
)


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

def main() -> None:
    dh = DataHandler.from_csv(DATA_FILE)
    start = dh.data.index[0].date()
    end   = dh.data.index[-1].date()
    print(f"Data loaded: {len(dh)} bars  ({start} to {end})")

    tester = WalkForwardTester(
        base_config=BASE_CONFIG,
        strategy_class=RSIReversionStrategy,
        param_grid=PARAM_GRID,
        train_size=500,
        test_size=100,
        step_size=100,
        optimize_target="sharpe_ratio",
        output_dir=OUTPUT_DIR,
    )

    result = tester.run(dh)

    # -----------------------------------------------------------------------
    # Report
    # -----------------------------------------------------------------------
    SEP = "=" * 108

    print()
    print(SEP)
    print("  RSI MEAN REVERSION -- WALK-FORWARD VALIDATION (RELIANCE 1D)")
    print(SEP)
    print(f"  Train: 500 bars | Test: 100 bars | Step: 100 bars")
    print(f"  Grid : rsi_period={PARAM_GRID['rsi_period']}  "
          f"oversold={PARAM_GRID['oversold']}  overbought={PARAM_GRID['overbought']}")
    print(f"  Total combinations per window: 27")
    print()

    windows = result.windows
    hdr = (f"{'Win':>4}  {'Train start':>12} {'Train end':>12}  "
           f"{'Test start':>12} {'Test end':>12}  "
           f"{'Best params':>26}  {'Train Sr':>9}  {'Test Sr':>9}  {'Test Trades':>12}")
    print(hdr)
    print("-" * 110)

    train_sharpes: list[float] = []
    test_sharpes:  list[float] = []

    for w in windows:
        best = w.best_params or {}
        params_str = (
            f"rsi={best.get('rsi_period','?')},"
            f"os={best.get('oversold','?')},"
            f"ob={best.get('overbought','?')}"
        )
        train_sr = w.train_metrics.get("sharpe_ratio")
        test_sr  = w.test_metrics.get("sharpe_ratio")
        test_trades = w.test_metrics.get("num_trades", 0)

        if train_sr is None: train_sr = float("nan")
        if test_sr  is None: test_sr  = float("nan")

        train_sharpes.append(train_sr)
        test_sharpes.append(test_sr)

        print(f"{w.window_index:>4}  "
              f"{str(w.train_start):>12} {str(w.train_end):>12}  "
              f"{str(w.test_start):>12} {str(w.test_end):>12}  "
              f"{params_str:>26}  {train_sr:>9.4f}  {test_sr:>9.4f}  {test_trades:>12}")

    print("-" * 110)

    valid_train = [s for s in train_sharpes if s == s]
    valid_test  = [s for s in test_sharpes  if s == s]

    avg_train = sum(valid_train) / len(valid_train) if valid_train else float("nan")
    avg_test  = sum(valid_test)  / len(valid_test)  if valid_test  else float("nan")

    agg = result.aggregate_metrics
    agg_sr = agg.get("avg_test_sharpe")

    print()
    print(f"  Windows run:              {len(windows)}")
    print(f"  Avg train Sharpe:         {avg_train:.4f}")
    print(f"  Avg OOS test Sharpe:      {avg_test:.4f}")
    if agg_sr is not None:
        print(f"  Aggregate OOS Sharpe:     {float(agg_sr):.4f}")

    positive_test_windows = sum(1 for s in valid_test if s > 0)
    zero_trade_windows    = sum(1 for w in windows if w.test_metrics.get("num_trades", 0) == 0)

    print(f"  Positive OOS windows:     {positive_test_windows}/{len(valid_test)}")
    print(f"  Zero-trade OOS windows:   {zero_trade_windows}/{len(windows)}")

    # Robustness verdict
    print()
    print("  ROBUSTNESS ASSESSMENT:")
    if avg_train == avg_train and avg_test == avg_test:
        gap = avg_train - avg_test
        print(f"  Train-to-test Sharpe gap: {gap:.4f}")
        if gap < 0.3 and avg_test > 0:
            print("  Verdict: ROBUST -- low overfitting gap, positive OOS Sharpe")
        elif gap < 0.5 and avg_test > -0.1:
            print("  Verdict: MODERATE -- some train/test gap; monitor carefully")
        else:
            print("  Verdict: OVERFIT -- large train/test gap or negative OOS Sharpe")

    print()
    print(f"  Results exported to: {OUTPUT_DIR}/")
    print(SEP)


if __name__ == "__main__":
    main()
