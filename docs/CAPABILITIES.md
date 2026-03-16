# Capabilities

## Capability Matrix

| Capability | Status | Entry Point | Outputs | Maturity |
| --- | --- | --- | --- | --- |
| Historical backtesting | supported | `main.py`, `src/core/backtest_engine.py` | performance metrics, trade logs | stable |
| Strategy optimization | supported | `optimize_sma.py`, `src/research/optimizer.py` | ranked parameter sets | stable |
| Walk-forward testing | supported | `run_rsi_walkforward.py`, `src/research/walk_forward.py` | train/test window reports | stable |
| Monte Carlo robustness | supported | `run_rsi_monte_carlo.py`, `src/research/monte_carlo.py` | distribution metrics | stable |
| Portfolio simulation | supported | `run_multi_asset_backtest.py`, `src/research/portfolio_backtester.py` | portfolio-level metrics | stable |
| Scanner engine | supported | `src/scanners/engine.py` | ranked opportunities CSV/JSON | stable |
| Monitoring snapshots | supported | `src/monitoring/market_monitor.py` | alerts/snapshots/regime outputs | stable |
| Decision picks | supported | `src/decision/pick_engine.py` | intraday/swing/positional picks | stable |
| Market intelligence | supported | `src/market_intelligence/market_state_engine.py` | breadth/sector/volatility outputs | stable |
| Strategy research lab | supported | `src/research_lab/strategy_discovery_engine.py` | strategy score/cluster artifacts | stable |
| Paper trading | supported | `scripts/run_paper_trading.py` | orders/fills/positions/PnL/session summary | stable |
| Live-safe signal pipeline | supported | `scripts/run_live_signal_pipeline.py` | signals/watchlist/regime/paper-handoff | stable |
| Live order execution | not supported | placeholder only | none | future scope |

## Notes

- Core workflows are optimized for research correctness and simulation safety.
- All production order execution concerns are intentionally deferred.
- Safety-first defaults remain enforced across paper/live-safe runners.
