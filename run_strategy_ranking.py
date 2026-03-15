"""
Run all 30 built-in strategy candidates on a chosen symbol and rank by Sharpe.

Usage:
    python run_strategy_ranking.py                          # default: RELIANCE 1D
    python run_strategy_ranking.py data/TCS_1D.csv          # custom file
    python run_strategy_ranking.py data/INFY_1D.csv 15      # top 15
"""

from __future__ import annotations

import sys
import warnings
import logging

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

import pandas as pd

from src.core.data_handler import DataHandler
from src.research.strategy_generator import (
    StrategyGenerator,
    StrategyRanker,
    get_default_templates,
)
from src.utils.config import BacktestConfig, PositionSizingMethod, RiskConfig


def main() -> None:
    data_file = sys.argv[1] if len(sys.argv) > 1 else "data/RELIANCE_1D.csv"
    top_n = int(sys.argv[2]) if len(sys.argv) > 2 else 10

    output_dir = "output/strategy_ranking"
    symbol = data_file.split("/")[-1].replace(".csv", "")

    config = BacktestConfig(
        initial_capital=100_000,
        fee_rate=0.001,
        slippage_rate=0.0005,
        position_sizing=PositionSizingMethod.PERCENT_OF_EQUITY,
        position_size_pct=0.95,
        intraday=False,
        risk=RiskConfig(stop_loss_pct=0.05, trailing_stop_pct=0.03),
        strategy_params={},
        output_dir=output_dir,
        data_file=data_file,
    )

    dh = DataHandler.from_csv(data_file)
    print(f"Data: {symbol}  |  {len(dh)} bars  |  "
          f"{dh.data.index[0].date()} to {dh.data.index[-1].date()}")

    # Generate candidates
    gen = StrategyGenerator()
    for tpl in get_default_templates():
        gen.add_template(tpl)
    candidates = gen.get_candidates()
    print(f"Generated {len(candidates)} strategy candidates")

    # Rank
    ranker = StrategyRanker(
        base_config=config,
        rank_by="sharpe_ratio",
        top_n=top_n,
    )
    result = ranker.run(dh, candidates)

    # Report
    SEP = "=" * 100
    print()
    print(SEP)
    print(f"  STRATEGY RANKING -- {symbol}  (top {top_n} by Sharpe)")
    print(SEP)

    hdr = (f"{'Rank':>5}  {'Strategy':>22}  {'Params':>30}  "
           f"{'Sharpe':>8}  {'Return':>10}  {'MaxDD':>10}  {'Trades':>7}  {'PF':>8}")
    print(hdr)
    print("-" * 100)

    for i, r in enumerate(result.ranked_strategies, 1):
        m = r.metrics
        params = ", ".join(f"{k}={v}" for k, v in r.params.items())
        sharpe = m.get("sharpe_ratio", float("nan"))
        ret = m.get("total_return_pct", float("nan"))
        dd = m.get("max_drawdown_pct", float("nan"))
        trades = m.get("num_trades", 0)
        pf = m.get("profit_factor", float("nan"))

        ret_s = f"{ret*100:.2f}%" if ret == ret else "N/A"
        dd_s = f"{dd*100:.2f}%" if dd == dd else "N/A"
        pf_s = f"{pf:.4f}" if (pf == pf and pf != float("inf")) else "inf" if pf == float("inf") else "N/A"

        print(f"{i:>5}  {r.strategy_name:>22}  {params:>30}  "
              f"{sharpe:>8.4f}  {ret_s:>10}  {dd_s:>10}  {trades:>7}  {pf_s:>8}")

    print("-" * 100)
    print(f"\n  Results exported to: {output_dir}/")
    print(SEP)


if __name__ == "__main__":
    main()
