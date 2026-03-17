# Architecture

## System Purpose

This platform is built for quantitative trading research, paper-trading simulation, and live-safe signal generation.

It is not a live execution system today.

## Layered Architecture

1. **Data Provider Layer** (`src/data/`)
   - Provider factory and provider config
   - CSV/Indian CSV stable paths
   - Zerodha/Upstox integration-ready paths

2. **Core Research Layer** (`src/core/`, `src/research/`)
   - Backtesting engine
   - Walk-forward and Monte Carlo validation
   - Portfolio backtesting and strategy optimization

3. **Strategy Layer** (`src/strategies/`)
   - Base strategy contracts and indicator helpers
   - Strategy implementations (SMA/RSI/Breakout and extensions)

4. **Scanner/Monitoring/Decision Layer** (`src/scanners/`, `src/monitoring/`, `src/decision/`)
   - Opportunity generation and scoring
   - Regime and watchlist-aware monitoring
   - Pick engine and trade-plan construction

5. **Portfolio & Risk Planning Layer** (`src/decision/portfolio_engine.py`)
   - Capital allocation recommendations (equal/volatility/conviction weighted)
   - Position sizing recommendations (fixed-fractional/risk-per-trade/ATR fallback)
   - Portfolio constraints (capital, positions, sector, correlation, risk caps)
   - Drawdown overlays (`normal`, `reduced_risk`, `no_new_risk`)

6. **Paper Trading Layer** (`src/paper_trading/`)
   - Simulated order/fill/position lifecycle
   - Session-level PnL tracking and artifact export

7. **Live-safe Signal Layer** (`src/live/`, `src/realtime/`)
   - Fresh/latest-bar signal cycles
   - Session/watchlist artifacts and optional paper handoff
   - No order placement

8. **Execution Placeholder Layer** (`src/execution/`)
   - Cost/fill realism models used for simulation
   - Placeholder execution interface reserved for future live phase

## Flow Overview

`Provider data -> Strategy logic -> Research filtering -> Scanner/Monitoring/Decision -> Portfolio & Risk Planning -> Paper/live-safe artifacts`

## Main CLI Entry Points

- `scripts/run_nifty50_zerodha_research.py`
- `scripts/run_scanner.py`
- `scripts/run_monitoring.py`
- `scripts/run_decision.py`
- `scripts/run_paper_trading.py`
- `scripts/run_live_signal_pipeline.py`

## Backward Compatibility

Current architecture is additive by phase. Existing research and simulation workflows remain valid while new layers add orchestration and outputs.
